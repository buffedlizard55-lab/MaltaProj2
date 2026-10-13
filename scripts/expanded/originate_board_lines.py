#!/usr/bin/env python3
"""Originate labelled, non-market line estimates for CS2 fixtures that no external book prices.

Requirement being served: "we need to originate our own lines for all matches". An originated
line must never be confused with a market price, so it is written into a *separate* field
(`originated_estimate`) and is never placed in the `consensus`/`pick` fields that drive the
market view. On the site it is rendered in its own column with an explicit warning.

Rating input: Valve's official Counter-Strike Regional Standings (VRS) markdown files from
github.com/ValveSoftware/counter-strike_regional_standings — the same rating Valve uses for
invitations. The snapshot date used is recorded per run and the raw files are saved as evidence
under data/expanded/vrs/.

Model (documented, reproducible, and clearly an approximation):
    p(a beats b) = 1 / (1 + 10 ** (-(R_a - R_b) / SCALE))
with R = VRS points and SCALE = 400 (Elo-style logistic). SCALE is a modelling assumption, not
a published Valve quantity; it is stated on the site next to every originated number. Teams
without VRS points get no originated estimate at all (blank + flagged), and LoL fixtures get
none because no equivalent official rating exists.

Usage: python3 scripts/expanded/originate_board_lines.py [--lines data/expanded/lines.json]
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lines_core import same_team  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "expanded"
VRS_DIR = DATA / "vrs"
SCALE = 400.0
UA = "MaltaProj2-pickem-board/1.0 (research; contact via repository)"

VRS_REPO = "ValveSoftware/counter-strike_regional_standings"
VRS_BRANCH = "main"
VRS_DIR_PATH = "live/2026"
REGIONS = ("global", "europe", "americas", "asia")


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_get(url: str, raw_json: bool = False) -> bytes | None:
    headers = {"User-Agent": UA, "Accept": "application/vnd.github.raw" if raw_json else "*/*"}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=40,
                                    context=ssl.create_default_context()) as r:
            return r.read()
    except Exception:  # noqa: BLE001
        return None


def list_vrs_snapshots() -> dict[str, str]:
    """Return {region: snapshot_date} for the newest standings file per region."""
    url = (f"https://api.github.com/repos/{VRS_REPO}/git/trees/{VRS_BRANCH}?recursive=1")
    body = http_get(url, raw_json=True)
    if not body:
        return {}
    try:
        tree = json.loads(body.decode("utf-8", "replace")).get("tree") or []
    except Exception:  # noqa: BLE001
        return {}
    newest: dict[str, str] = {}
    for node in tree:
        path = str(node.get("path") or "")
        m = re.match(rf"{VRS_DIR_PATH}/standings_([a-z]+)_(\d{{4}}_\d{{2}}_\d{{2}})\.md$", path)
        if not m:
            continue
        region, date = m.group(1), m.group(2)
        if region not in REGIONS:
            continue
        if region not in newest or date > newest[region]:
            newest[region] = date
    return newest


def fetch_vrs_file(region: str, date: str) -> tuple[str | None, dict]:
    """Fetch one standings markdown file, trying raw then the contents API.

    The contents API is asked for the raw media type, so its body is the markdown itself; some
    proxies/allow-lists answer that request with the default JSON envelope instead, so both
    shapes are accepted and the response is validated by actually parsing a table out of it.
    """
    raw_url = f"https://raw.githubusercontent.com/{VRS_REPO}/{VRS_BRANCH}/{VRS_DIR_PATH}/standings_{region}_{date}.md"
    api_url = f"https://api.github.com/repos/{VRS_REPO}/contents/{VRS_DIR_PATH}/standings_{region}_{date}.md"
    meta = {"region": region, "snapshot": date, "raw_url": raw_url, "api_url": api_url}
    candidates: list[tuple[str, str]] = []
    body = http_get(raw_url)
    if body:
        candidates.append(("raw.githubusercontent.com", body.decode("utf-8", "replace")))
    blob = http_get(api_url, raw_json=True)
    if blob:
        txt = blob.decode("utf-8", "replace")
        if '"content"' in txt[:4000] and "base64" in txt[:4000]:
            try:
                candidates.append(("api.github.com contents (base64)",
                                   base64.b64decode(json.loads(txt)["content"]).decode("utf-8", "replace")))
            except Exception as exc:  # noqa: BLE001
                meta["error_api"] = f"decode failed: {exc}"
        else:
            candidates.append(("api.github.com contents (raw)", txt))
    for how, text in candidates:
        if len(parse_standings(text)) > 0:
            meta["fetched_via"] = how
            meta["bytes"] = len(text)
            VRS_DIR.mkdir(parents=True, exist_ok=True)
            (VRS_DIR / f"standings_{region}_{date}.md").write_text(text, encoding="utf-8")
            return text, meta
    meta["error"] = meta.get("error_api") or "no readable standings table in any response"
    return None, meta


def parse_standings(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        m = re.match(r"\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", line)
        if m:
            rows.append({"standing": int(m.group(1)), "points": int(m.group(2)),
                         "team": m.group(3).strip()})
    return rows


def logistic(points_a: float, points_b: float) -> float:
    return 1.0 / (1.0 + 10 ** (-(points_a - points_b) / SCALE))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", default=str(DATA / "lines.json"))
    args = ap.parse_args()
    lines_path = Path(args.lines)
    if not lines_path.exists():
        print("no lines.json — run collect_lines.py first")
        return 1
    doc = json.loads(lines_path.read_text(encoding="utf-8"))

    snapshots = list_vrs_snapshots()
    ratings: dict[str, dict] = {}
    evidence = []
    for region in REGIONS:
        date = snapshots.get(region)
        if not date:
            evidence.append({"region": region, "error": "no snapshot found"})
            continue
        text, meta = fetch_vrs_file(region, date)
        if text is None:
            evidence.append(meta)
            continue
        rows = parse_standings(text)
        for r in rows:
            r["region"] = region
            ratings.setdefault(r["team"], r)
        meta["teams"] = len(rows)
        evidence.append(meta)

    originated = 0
    skipped_no_rating = 0
    for row in doc["fixtures"]:
        if row.get("game") != "CS2":
            row["originated_estimate"] = {
                "available": False,
                "reason": "no official rating source is used for this game — market line only",
            }
            continue
        if row.get("quotes"):
            row["originated_estimate"] = {
                "available": False,
                "reason": "external market line available — the market value is the one shown",
            }
            continue
        if not row.get("is_future"):
            row["originated_estimate"] = {
                "available": False,
                "reason": "fixture start time has passed — no estimate published",
            }
            continue
        a = b = None
        a_name = b_name = None
        for name, rec in ratings.items():
            if a is None and same_team(name, row["team_a"]):
                a, a_name = rec, name
            if b is None and same_team(name, row["team_b"]):
                b, b_name = rec, name
        if not a or not b:
            skipped_no_rating += 1
            missing = [t for t, r in ((row["team_a"], a), (row["team_b"], b)) if not r]
            row["originated_estimate"] = {
                "available": False,
                "reason": "no Valve VRS rating for: " + ", ".join(missing),
            }
            continue
        pa = logistic(a["points"], b["points"])
        row["originated_estimate"] = {
            "available": True,
            "label": "ORIGINATED MODEL — not a market price",
            "method": ("Bradley-Terry / Elo-style logistic on Valve VRS points: "
                       "p = 1/(1+10^(-(Ra-Rb)/400)); scale 400 is a model assumption"),
            "team_a_points": a["points"], "team_a_standing": a["standing"],
            "team_a_region": a["region"], "team_a_vrs_name": a_name,
            "team_b_points": b["points"], "team_b_standing": b["standing"],
            "team_b_region": b["region"], "team_b_vrs_name": b_name,
            "prob_a": round(pa, 4), "prob_b": round(1 - pa, 4),
            "pick": row["team_a"] if pa >= 0.5 else row["team_b"],
            "pick_probability": round(max(pa, 1 - pa), 4),
            "sources": [
                {"label": f"Valve VRS {a['region']} standings {a.get('snapshot', '')}".strip(),
                 "url": next((e.get("raw_url") for e in evidence
                              if e.get("region") == a["region"]), None)},
                {"label": f"Valve VRS {b['region']} standings {b.get('snapshot', '')}".strip(),
                 "url": next((e.get("raw_url") for e in evidence
                              if e.get("region") == b["region"]), None)},
            ],
        }
        originated += 1

    doc["origination"] = {
        "generated_at_utc": now_iso(),
        "rating_source": f"https://github.com/{VRS_REPO} (official Valve regional standings)",
        "model": f"p = 1/(1+10^(-(Ra-Rb)/{SCALE:.0f})) on VRS points; scale is a modelling assumption",
        "warning": ("Originated values are model output, not bookmaker prices. They are shown in a "
                    "separate column and never mixed into the market consensus."),
        "snapshots": snapshots,
        "evidence": evidence,
        "counts": {"originated_estimates": originated,
                   "no_rating_available": skipped_no_rating,
                   "fixtures": len(doc["fixtures"])},
    }
    lines_path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"originated estimates: {originated}; without rating: {skipped_no_rating}; "
          f"snapshots: {snapshots}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
