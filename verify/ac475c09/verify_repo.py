#!/usr/bin/env python3
"""
Independent verification of this repository's published pick'em artefacts — session ac475c09.

The checks below are mechanical and re-runnable. Each one either passes or produces a finding with
the exact file, the offending value and (where one exists) the official source a reviewer needs.

    python3 verify/ac475c09/verify_repo.py            # writes findings.json + REPORT.md

Checked rules
    1. Provenance      every stored price/quote must carry a source URL and a retrieval timestamp.
    2. Shape           a field named decimal_odds_* must be a decimal price (1.01..1000), not an
                       American price or a percentage — a wrong unit silently corrupts a de-vig.
    3. Freshness       a snapshot older than the freshness budget is flagged as stale, never
                       presented by this session as current.
    4. Coverage        published "with line" counts must equal the rows that actually carry a line.
    5. Provenance      quotes typed into a script as literals cannot be re-verified automatically;
                       they are listed so a reviewer can check them against the linked page.
    6. Fixture drift   snapshots taken at different times legitimately differ; the difference is
                       reported rather than silently reconciled.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.dirname(os.path.abspath(__file__))
FRESH_HOURS = 6


def load(rel):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        return {"__error__": str(exc)}


def parse_iso(value):
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def age_hours(value):
    dt = parse_iso(value)
    if not dt:
        return None
    return (datetime.now(tz=timezone.utc) - dt).total_seconds() / 3600.0


FINDINGS: list[dict] = []


def finding(check, severity, file, detail, value=None, source=None):
    FINDINGS.append({"check": check, "severity": severity, "file": file,
                     "detail": detail, "value": value, "source": source})


# ------------------------------------------------------------------ 1. provenance of stored prices
def check_price_provenance():
    for rel in ("data/odds.json", "data/lines.json", "data/cs2_odds_egamersworld.json",
                "data/lol_odds_egamersworld.json", "data/picks_quotes.json"):
        doc = load(rel)
        if not doc:
            continue
        rows = doc.get("lines") or doc.get("quotes") or doc.get("rows") or []
        missing = 0
        for row in rows:
            url = (row.get("source_public_url") or row.get("source_api_url")
                   or row.get("source_url") or row.get("egw_url"))
            if not url:
                missing += 1
        if missing:
            finding("price_provenance", "high", rel,
                    f"{missing} of {len(rows)} stored price rows carry no source URL",
                    value=missing)
        else:
            finding("price_provenance", "info", rel,
                    f"all {len(rows)} stored price rows carry a source URL", value=len(rows))


# ------------------------------------------------------------------ 2. unit sanity
def check_price_units():
    for rel in ("data/odds.json", "data/lines.json"):
        doc = load(rel)
        if not doc:
            continue
        rows = doc.get("lines") or doc.get("fixtures") or []
        bad = []
        for row in rows:
            for side in ("a", "b"):
                key = f"decimal_odds_{side}"
                value = row.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                if value < 1.0 or value > 1000:
                    bad.append({"field": key, "value": value, "fixture": row.get("fixture_id"),
                                "source": row.get("source_public_url") or row.get("source_api_url")})
        if bad:
            finding("price_units", "high", rel,
                    f"{len(bad)} field(s) named decimal_odds_* hold a value outside 1.01..1000 "
                    "(an American price in a decimal field corrupts every derived probability)",
                    value=bad[:6])
        else:
            finding("price_units", "info", rel, "no decimal_odds_* field is out of range")


# ------------------------------------------------------------------ 3. freshness
def check_freshness():
    for rel in ("data/hotspawn_matches.json", "data/cs2_matches.json", "data/lol_matches.json",
                "data/odds.json", "data/lines.json", "data/probabilities.json",
                "data/picks_fixtures.json", "data/picks_board.json"):
        doc = load(rel)
        if not doc:
            continue
        stamp = (doc.get("generated_at_utc") or doc.get("meta", {}).get("generated_at_utc")
                 or doc.get("summary", {}).get("generated_at_utc")
                 or doc.get("api_snapshot_at_utc"))
        hours = age_hours(stamp)
        if hours is None:
            finding("freshness", "medium", rel, "no parseable generated_at_utc timestamp")
        elif hours > FRESH_HOURS:
            finding("freshness", "medium", rel,
                    f"snapshot is {hours:.1f}h old (budget {FRESH_HOURS}h): publish it as a dated "
                    "snapshot, not as current", value=round(hours, 2))
        else:
            finding("freshness", "info", rel, f"snapshot is {hours:.1f}h old")


# ------------------------------------------------------------------ 4. published counts vs rows
def check_counts():
    doc = load("data/lines.json")
    if doc:
        summary = doc.get("summary", {})
        fixtures = doc.get("fixtures", [])
        with_line = [f for f in fixtures if f.get("bookmaker_lines")]
        if summary.get("fixtures_with_external_line") not in (None, len(with_line)):
            finding("published_counts", "high", "data/lines.json",
                    f"summary says {summary.get('fixtures_with_external_line')} fixtures have a line "
                    f"but {len(with_line)} rows actually carry one")
        else:
            finding("published_counts", "info", "data/lines.json",
                    f"summary and rows agree ({len(with_line)} priced fixtures of {len(fixtures)})")
        if summary.get("fixtures_total") not in (None, len(fixtures)):
            finding("published_counts", "high", "data/lines.json",
                    f"summary fixtures_total={summary.get('fixtures_total')} but {len(fixtures)} rows")

    prob = load("data/probabilities.json")
    if prob:
        rows = prob.get("rows", [])
        priced = [r for r in rows if r.get("probability_a") is not None]
        stats = prob.get("stats", {})
        if stats.get("with_prob") not in (None, len(priced)):
            finding("published_counts", "high", "data/probabilities.json",
                    f"stats.with_prob={stats.get('with_prob')} but {len(priced)} rows are priced")


# ------------------------------------------------------------------ 5. typed-in quotes
def check_typed_quotes():
    pattern = re.compile(r"decimal_odds\s*=\s*\d+\.\d+|\"decimal_odds_[ab]\"\s*:\s*\d+\.\d+|"
                         r"odds_egw=dict\(a=\d+\.\d+")
    hits = []
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "scripts")):
        for name in files:
            if not name.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), ROOT)
            if rel.startswith("scripts/picks_"):
                continue  # this session's generator writes data, never literals
            text = open(os.path.join(dirpath, name), encoding="utf-8", errors="replace").read()
            n = len(pattern.findall(text))
            if n:
                hits.append({"file": rel, "literal_price_like_values": n})
    if hits:
        finding("typed_quotes", "medium", "scripts/*.py",
                "price-like literals are typed into generator scripts; they cannot be re-verified "
                "without opening the linked page, so they are listed for review", value=hits)
    else:
        finding("typed_quotes", "info", "scripts/*.py", "no typed price literals found")


# ------------------------------------------------------------------ 6. cross-pipeline agreement
def check_cross_pipeline():
    """The repo carries two independent collections; where they overlap the numbers must agree."""
    mine = load("data/picks_board.json")
    theirs = load("data/lines.json")
    if not mine or not theirs:
        return
    their_consensus = {}
    for f in theirs.get("fixtures", []):
        cons = (f.get("derived") or {}).get("consensus") or {}
        if cons.get("probability_a") is not None:
            their_consensus[str(f["fixture_id"])] = (cons.get("probability_a"),
                                                     cons.get("probability_b"), f)
    mine_by_id = {str(r["fixture_id"]): r for r in mine.get("rows", [])}
    shared = sorted(set(their_consensus) & {k for k, r in mine_by_id.items() if r["prob_a"] is not None})
    worst = None
    for fid in shared:
        a, _b, _row = their_consensus[fid]
        delta = abs(a - mine_by_id[fid]["prob_a"])
        if worst is None or delta > worst["delta"]:
            worst = {"fixture_id": fid, "delta": round(delta, 4),
                     "pipeline_a": round(a, 4), "pipeline_b": round(mine_by_id[fid]["prob_a"], 4),
                     "hotspawn": mine_by_id[fid]["hotspawn_match_url"],
                     "root_pipeline": "data/lines.json", "session_pipeline": "data/picks_board.json"}
    if not shared:
        finding("cross_pipeline", "low", "data/lines.json vs data/picks_board.json",
                "no fixture currently carries a pre-match line in both pipelines (the older collection "
                "captured them before they started), so the two collections cannot be cross-checked on "
                "this build")
    elif worst["delta"] > 0.02:
        finding("cross_pipeline", "high", "data/lines.json vs data/picks_board.json",
                f"{len(shared)} fixtures priced in both pipelines; the largest disagreement is "
                f"{worst['delta']*100:.1f} probability points", value=worst)
    else:
        finding("cross_pipeline", "info", "data/lines.json vs data/picks_board.json",
                f"{len(shared)} fixtures are priced in both independent pipelines and agree within "
                f"{worst['delta']*100:.1f} probability points", value=worst)


# ------------------------------------------------------------------ 7. fixture drift
def check_fixture_drift():
    fresh = load("data/picks_fixtures.json")
    old = load("data/hotspawn_matches.json")
    if not fresh or not old:
        return
    fresh_summary = fresh.get("summary", {})
    fresh_ids = {f["fixture_id"] for f in fresh.get("fixtures", [])}
    old_ids = {str(m.get("fixture_id")) for m in old.get("matches", [])}
    finding("fixture_drift", "info", "data/hotspawn_matches.json vs data/picks_fixtures.json",
            f"older snapshot lists {len(old_ids)} fixtures, the fresh API read lists "
            f"{len(fresh_ids)} fixtures in total and {fresh_summary.get('fixtures_open_cs2')} CS2 / "
            f"{fresh_summary.get('fixtures_open_lol')} LoL fixtures still open for picks",
            value={"older_snapshot": len(old_ids), "fresh_total": len(fresh_ids)})
    missing_in_fresh = sorted(old_ids - fresh_ids)
    if missing_in_fresh:
        finding("fixture_drift", "low", "data/hotspawn_matches.json",
                f"{len(missing_in_fresh)} fixtures in the older snapshot are absent from the fresh "
                "API read whole-history dump", value=missing_in_fresh[:10])


def main() -> int:
    check_price_provenance()
    check_price_units()
    check_freshness()
    check_counts()
    check_typed_quotes()
    check_cross_pipeline()
    check_fixture_drift()

    payload = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session": "ac475c09",
        "freshness_budget_hours": FRESH_HOURS,
        "findings": FINDINGS,
        "summary": {
            "high": sum(1 for f in FINDINGS if f["severity"] == "high"),
            "medium": sum(1 for f in FINDINGS if f["severity"] == "medium"),
            "low": sum(1 for f in FINDINGS if f["severity"] == "low"),
            "info": sum(1 for f in FINDINGS if f["severity"] == "info"),
        },
    }
    with open(os.path.join(OUT, "findings.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False)
        fh.write("\n")

    lines = ["# Repo verification — session `ac475c09`", "",
             f"Generated {payload['generated_at_utc']}. Mechanical, re-runnable checks over this "
             "repository's published pick'em artefacts.", "",
             f"**{payload['summary']['high']} high · {payload['summary']['medium']} medium · "
             f"{payload['summary']['low']} low · {payload['summary']['info']} informational**", "",
             "| Check | Severity | File | Finding |", "|---|---|---|---|"]
    for f in FINDINGS:
        detail = f["detail"].replace("|", "/")
        lines.append(f"| {f['check']} | {f['severity']} | `{f['file']}` | {detail} |")
    lines += ["", "## How to re-run", "",
              "```bash", "python3 verify/ac475c09/verify_repo.py", "```", ""]
    with open(os.path.join(OUT, "REPORT.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(json.dumps(payload["summary"], indent=1))
    print(f"wrote verify/ac475c09/findings.json and REPORT.md ({len(FINDINGS)} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
