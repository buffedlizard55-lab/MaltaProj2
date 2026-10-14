#!/usr/bin/env python3
"""Reproduce session 57e26db7's independent current-snapshot audit.

Standard library only; no network. Reads the committed c64 collector snapshot and generated board,
independently filters the open inventory, checks every row and source, then writes report.json and a
mobile HTML report. Exit status is non-zero if any check fails.
"""
from __future__ import annotations

from datetime import datetime, timezone
import html
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SNAPSHOT = ROOT / "data" / "c64a5e19" / "snapshot.json"
BOARD = ROOT / "data" / "c64a5e19" / "board.json"
REPORT = HERE / "report.json"
INDEX = HERE / "index.html"
MAX_SPREAD = 0.10


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def check(checks, name, passed, detail):
    checks.append({"name": name, "status": "pass" if passed else "fail", "detail": detail})


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def pct(value):
    return f"{value * 100:.1f}%" if isinstance(value, (int, float)) else "—"


def build():
    snap, board = load(SNAPSHOT), load(BOARD)
    now = parse_time(snap["collected_to_utc"])
    expected = {
        str(f["fixture_id"])
        for f in snap["hotspawn"]["fixtures"]
        if f.get("status") == "scheduled"
        and parse_time(f.get("lock_utc") or f["start_utc"]) > now
    }
    rows = board.get("open") or []
    actual = {r["fixture_id"] for r in rows}
    checks = []
    check(checks, "snapshot provenance",
          board.get("generated_utc") == snap.get("collected_to_utc"),
          f"board={board.get('generated_utc')} snapshot={snap.get('collected_to_utc')}")
    check(checks, "complete open inventory", actual == expected,
          f"independent={len(expected)} board={len(actual)} missing={sorted(expected-actual)} extra={sorted(actual-expected)}")

    bad_lines = []
    bad_sources = []
    fallback_without_evidence = []
    for row in rows:
        line = row.get("line")
        if line:
            valid = (line.get("pick_team") in (row.get("team_a"), row.get("team_b"))
                     and isinstance(line.get("prob_a"), (int, float))
                     and isinstance(line.get("prob_b"), (int, float))
                     and abs(line["prob_a"] + line["prob_b"] - 1) < 0.001
                     and line.get("pick_prob") == max(line["prob_a"], line["prob_b"]))
        else:
            valid = bool(row.get("flags")) and "no_line_unverified" in row.get("flags", [])
        if not valid:
            bad_lines.append(row["fixture_id"])
        sources = row.get("sources") or []
        if (not sources or any(not str(s.get("url", "")).startswith("https://") for s in sources)
                or not any(not str(s.get("label", "")).startswith("HotSpawn") for s in sources)):
            bad_sources.append(row["fixture_id"])
        if line and line.get("tier") == "C" and not (row.get("fallback") or {}).get("evidence"):
            fallback_without_evidence.append(row["fixture_id"])
    check(checks, "pick/probability arithmetic", not bad_lines,
          "all rows valid" if not bad_lines else f"invalid={bad_lines}")
    check(checks, "source link on every row", not bad_sources,
          "all rows include non-HotSpawn evidence" if not bad_sources else f"invalid={bad_sources}")
    check(checks, "fallback evidence", not fallback_without_evidence,
          "every tier-C row documents evidence" if not fallback_without_evidence else f"invalid={fallback_without_evidence}")

    blob = json.dumps(board).casefold()
    forbidden = [key for key in ("pick_pct", "picked_percent", "crowd_percent", "hotspawn_percent") if key in blob]
    check(checks, "HotSpawn discovery only", not forbidden,
          "no crowd-percentage field" if not forbidden else f"forbidden={forbidden}")

    access = (snap.get("access_log") or {}).get("polymarket") or {}
    accepted = [q for q in snap.get("quotes", []) if q.get("source_key") == "polymarket"]
    rejected = [r for r in snap.get("rejected_quotes", []) if r.get("source_key") == "polymarket"]
    discovery_ok = (access.get("tag_id") == 100780 and access.get("status") == 200
                    and not access.get("truncated")
                    and len(accepted) + len(rejected) == access.get("match_winner_candidates"))
    check(checks, "Polymarket numeric match discovery", discovery_ok,
          f"tag={access.get('tag_id')} rows={access.get('market_rows')} accepted={len(accepted)} fallback_only={len(rejected)}")
    tight_ok = all(isinstance(q.get("bid_ask_spread"), (int, float))
                   and q["bid_ask_spread"] <= MAX_SPREAD for q in accepted)
    wide_ok = all((r.get("quote") or {}).get("bid_ask_spread") is None
                  or (r.get("quote") or {}).get("bid_ask_spread") > MAX_SPREAD for r in rejected)
    check(checks, "exchange quality separation", tight_ok and wide_ok,
          f"featured <= {MAX_SPREAD:.2f}; fallback-only > {MAX_SPREAD:.2f} or missing")

    by_id = {r["fixture_id"]: r for r in rows}
    forze = by_id.get("1079624")
    if forze:
        evidence = (forze.get("fallback") or {}).get("evidence") or []
        kinds = {e.get("kind") for e in evidence}
        ok = (bool(kinds & {"exact_roster_market_price", "wide_exchange_exact_roster_price"})
              and "exact_roster_identity" in kinds and "originated_sibling_vrs_range" not in kinds)
        check(checks, "FORZE Reload/LFO 10 evidence priority", ok,
              "direct Sökerorg market + exact-roster sources; no sibling estimate")
    wrot = [r for r in rows if "WROTBERRY" in (r.get("team_a"), r.get("team_b"))]
    if wrot:
        academy_numeric = []
        has_poly = True
        for row in wrot:
            evidence = (row.get("fallback") or {}).get("evidence") or []
            has_poly = has_poly and any("Polymarket" in e.get("source", "") for e in evidence)
            for item in evidence:
                if "WBT Academy" in (item.get("names_at_source") or []) and (
                        "prob_team_a" in item or "prob_team_a_normalised_mid" in item):
                    academy_numeric.append(row["fixture_id"])
        check(checks, "WROTBERRY identity fail-closed", has_poly and not academy_numeric,
              f"WBT prices preserved; WBT Academy numeric use={academy_numeric or 'none'}")

    fixture_rows = []
    for row in rows:
        line = row.get("line") or {}
        fixture_rows.append({
            "fixture_id": row["fixture_id"],
            "start_utc": row["start_utc"],
            "competition": row.get("competition"),
            "team_a": row["team_a"],
            "team_b": row["team_b"],
            "pick": line.get("pick_team"),
            "pick_probability": line.get("pick_prob"),
            "prob_a": line.get("prob_a"),
            "prob_b": line.get("prob_b"),
            "tier": line.get("tier") or "D",
            "flags": row.get("flags") or [],
            "sources": row.get("sources") or [],
        })
    report = {
        "session": "57e26db7",
        "status": "pass" if all(c["status"] == "pass" for c in checks) else "fail",
        "snapshot_collected_utc": snap["collected_to_utc"],
        "snapshot_path": "data/c64a5e19/snapshot.json",
        "board_path": "data/c64a5e19/board.json",
        "summary": board.get("summary"),
        "polymarket": {
            "tag_id": access.get("tag_id"),
            "market_rows": access.get("market_rows"),
            "accepted_tight_books": len(accepted),
            "fallback_only_wide_books": len(rejected),
            "access_url": access.get("url"),
        },
        "checks": checks,
        "fixtures": fixture_rows,
    }
    return report


def render(report):
    check_rows = "".join(
        f'<tr><td><span class="{c["status"]}">{esc(c["status"].upper())}</span></td><td>{esc(c["name"])}</td><td>{esc(c["detail"])}</td></tr>'
        for c in report["checks"])
    fixture_rows = []
    for row in report["fixtures"]:
        links = " · ".join(f'<a href="{esc(s["url"])}">{esc(s["label"])}</a>' for s in row["sources"])
        flags = ", ".join(row["flags"]) or "none"
        fixture_rows.append(
            f'<tr><td data-l="Fixture"><b>{esc(row["team_a"])} vs {esc(row["team_b"])}</b><br><small>{esc(row["fixture_id"])} · {esc(row["competition"])} · {esc(row["start_utc"])}</small></td>'
            f'<td data-l="Probability">{esc(row["team_a"])} {pct(row["prob_a"])}<br>{esc(row["team_b"])} {pct(row["prob_b"])}</td>'
            f'<td data-l="Pick"><b>{esc(row["pick"] or "blank")}</b> {pct(row["pick_probability"])}<br>Tier {esc(row["tier"])}</td>'
            f'<td data-l="Flags"><small>{esc(flags)}</small></td><td data-l="Sources"><small>{links}</small></td></tr>')
    p = report["polymarket"]
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Independent every-match audit · 57e26db7</title><style>
:root{{--bg:#0f1218;--card:#171b23;--line:#2b3342;--txt:#e8ebf1;--mut:#9aa3b2;--ok:#3ddc97;--bad:#ff6b6b}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);font:15px/1.45 system-ui,sans-serif}}main{{max-width:1180px;margin:auto;padding:16px}}a{{color:#69b4ff}}h1{{font-size:24px}}.note{{background:var(--card);border-left:3px solid #69b4ff;padding:12px;border-radius:6px}}table{{width:100%;border-collapse:collapse;background:var(--card);margin:12px 0}}th,td{{border-bottom:1px solid var(--line);padding:9px;text-align:left;vertical-align:top}}th{{color:var(--mut)}}.pass{{color:var(--ok);font-weight:800}}.fail{{color:var(--bad);font-weight:800}}small{{color:var(--mut)}}@media(max-width:760px){{table.fixtures thead{{display:none}}table.fixtures tr{{display:block;border-bottom:2px solid var(--line)}}table.fixtures td{{display:block;border:0;padding:5px 10px}}table.fixtures td:before{{content:attr(data-l);display:block;color:var(--mut);font-size:11px;text-transform:uppercase}}}}</style></head><body><main>
<p><a href="../../picks-every-match/index.html">← Every-match picks</a> · <a href="../../picks-every-match/flagged.html">Flagged for Review</a> · <a href="report.json">Machine-readable report</a></p>
<h1>Independent current-snapshot audit</h1><p class="note"><b>Status: <span class="{esc(report["status"])}">{esc(report["status"].upper())}</span></b><br>Snapshot {esc(report["snapshot_collected_utc"])} · independently checked {len(report["fixtures"])} open fixtures. Polymarket numeric tag {esc(p["tag_id"])} returned {esc(p["market_rows"])} full-match candidates: {esc(p["accepted_tight_books"])} tight/featured and {esc(p["fallback_only_wide_books"])} wide/fallback-only.</p>
<h2>Checks</h2><div style="overflow:auto"><table><thead><tr><th>Status</th><th>Check</th><th>Result</th></tr></thead><tbody>{check_rows}</tbody></table></div>
<h2>Every open row</h2><p>Team labels below remain HotSpawn's inventory labels. External source labels and all irregularities remain visible through source links and flags.</p><table class="fixtures"><thead><tr><th>Fixture</th><th>Win probabilities</th><th>Pick</th><th>Flags</th><th>Sources</th></tr></thead><tbody>{''.join(fixture_rows)}</tbody></table>
<p><small>Reproduce: <code>python3 audits/57e26db7/verify.py</code>. Standard library only; no network. HotSpawn crowd percentages are not read.</small></p></main></body></html>'''


def main():
    report = build()
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    INDEX.write_text(render(report), encoding="utf-8")
    print(f"57e26db7 audit: {report['status']} · {len(report['fixtures'])} open fixtures · {len(report['checks'])} checks")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
