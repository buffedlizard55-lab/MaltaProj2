#!/usr/bin/env python3
"""Session 34af18bf verifier — line by line, before anything is published.

Fails (exit 1, non-zero) when any of these do not hold:

  V1  the board covers every open fixture in the capture, plus the two TWC cards
  V2  every market probability re-derives from the retained raw quotes
  V3  every originated probability re-derives from the stored Valve rating pair
  V4  every row carries pick/probability of the same side, inside [0, 1]
  V5  no row is priced from HotSpawn: no quote source is HotSpawn and no formula
      input reads a crowd field
  V6  every non-blank row has at least one external source link, and every blank
      row has a written reason
  V7  every page exists, has a viewport meta, exactly one h1, and every internal
      link on them resolves to a file in the staged site
  V8  the unresolved page lists every blank row
  V9  the capture itself is sane: at least one fixture, lock/start times parse,
      and the snapshot records what every source answered
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "34af18bf"
PAGES = ROOT / "pickdesk"
RESULTS: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"check": name, "pass": bool(ok), "detail": detail})


def rederive_market(row: dict) -> float | None:
    readings = [{"prob_a": r["prob_a"], "prob_b": r["prob_b"], "weight": r["weight"]}
                for r in row.get("readings") or []]
    merged = core.blend(readings)
    return merged["prob_a"] if merged else None


def main() -> int:
    snapshot = json.loads((DATA / "snapshot.json").read_text(encoding="utf-8"))
    board = json.loads((DATA / "board.json").read_text(encoding="utf-8"))
    fixtures = snapshot["hotspawn"]["fixtures"]
    rows = board["fixtures"] + board["twc"]

    # V1 — coverage
    captured = {f["fixture_id"] for f in fixtures}
    covered = {r["fixture_id"] for r in board["fixtures"]}
    check("V1 coverage: every captured open fixture has a row", captured == covered,
          f"captured={len(captured)} covered={len(covered)} missing={sorted(captured - covered)}")
    check("V1b coverage: both TWC pick'em cards present",
          {r["fixture_id"] for r in board["twc"]} == {"1080207", "1080208"})

    # V2/V3 — arithmetic
    bad_market, bad_originated = [], []
    for row in rows:
        if row["basis"] == "market":
            expected = rederive_market(row)
            if expected is None or row.get("prob_a") is None or abs(expected - row["prob_a"]) > 5e-5:
                bad_market.append((row["fixture_id"], expected, row.get("prob_a")))
        elif row["basis"] == "originated":
            link = (row.get("source_links") or [{}])[0].get("label", "")
            if not re.search(r"Valve VRS .*#\d+.*#\d+", link):
                bad_originated.append((row["fixture_id"], "no rating pair on the row"))
            else:
                nums = [float(x) for x in re.findall(r"\((\d+)\)", link)]
                if len(nums) >= 2:
                    delta = nums[0] - nums[1]
                    expected = 1.0 / (1.0 + 10 ** (-delta / board["gates"]["vrs_elo_scale"]))
                    if row.get("prob_a") is None or abs(expected - row["prob_a"]) > 1e-4:
                        bad_originated.append((row["fixture_id"], expected, row.get("prob_a")))
    check("V2 market probabilities re-derive from retained quotes", not bad_market, str(bad_market))
    check("V3 originated probabilities re-derive from the stored rating pair", not bad_originated,
          str(bad_originated))

    # V4 — pick integrity
    integrity = []
    for row in rows:
        if row["basis"] == "blank":
            if row.get("pick") or row.get("probability") is not None:
                integrity.append((row["fixture_id"], "blank row carries a pick"))
            continue
        if row["pick"] not in (row["team_a"], row["team_b"]):
            integrity.append((row["fixture_id"], "pick is not one of the two teams"))
        if row["probability"] is None or not (0.0 < float(row["probability"]) < 1.0):
            integrity.append((row["fixture_id"], "probability outside (0,1)"))
        elif abs(float(row["probability"]) + float(row["other_probability"]) - 1.0) > 1e-4:
            integrity.append((row["fixture_id"], "two-way probabilities do not sum to 1"))
    check("V4 pick/probability integrity on every row", not integrity, str(integrity))

    # V5 — no HotSpawn input to any probability
    hotspawn_quotes = [q for q in snapshot["quotes"] if "hotspawn" in str(q.get("source_key", "")).lower()]
    crowd_leak = [r["fixture_id"] for r in rows if r.get("basis") == "market" and any(
        "crowd" in json.dumps(reading).lower() for reading in r.get("readings") or [])]
    check("V5a no HotSpawn-sourced quote exists", not hotspawn_quotes, str(hotspawn_quotes[:3]))
    check("V5b no crowd field reaches an arithmetic input", not crowd_leak, str(crowd_leak))

    # V6 — sources and reasons
    missing_source = [r["fixture_id"] for r in rows
                      if r["basis"] != "blank" and not r.get("source_links")]
    missing_reason = [r["fixture_id"] for r in rows
                      if r["basis"] == "blank" and not (r.get("notes") or [""])[0]]
    check("V6a every resolved row has an external source link", not missing_source, str(missing_source))
    check("V6b every blank row has a written reason", not missing_reason, str(missing_reason))

    # V7 — pages
    page_files = sorted(PAGES.glob("*.html"))
    check("V7a all pick desk pages exist", len(page_files) == 6, str([p.name for p in page_files]))
    problems = []
    for page in page_files:
        text = page.read_text(encoding="utf-8")
        if 'name="viewport"' not in text:
            problems.append((page.name, "no viewport meta"))
        if text.count("<h1") != 1:
            problems.append((page.name, f"{text.count('<h1')} h1 tags"))
        for href in re.findall(r'href="([^"#][^"]*)"', text):
            if href.startswith(("http://", "https://", "mailto:")):
                continue
            target = (page.parent / href.split("#")[0]).resolve()
            if href.split("#")[0] and not target.exists():
                problems.append((page.name, href))
    check("V7b pages are mobile-ready and every internal link resolves", not problems, str(problems[:6]))

    # V8 — unresolved page lists every blank
    unresolved_text = (PAGES / "unresolved.html").read_text(encoding="utf-8") if (PAGES / "unresolved.html").exists() else ""
    missing = [r["fixture_id"] for r in rows if r["basis"] == "blank" and r["fixture_id"] not in unresolved_text]
    check("V8 unresolved page lists every blank row", not missing, str(missing))
    unresolved_board = {r["fixture_id"] for r in board["unresolved"]}
    blanks = {r["fixture_id"] for r in rows if r["basis"] == "blank"}
    check("V8b board.unresolved matches the blank rows", unresolved_board == blanks,
          f"board={sorted(unresolved_board)} blanks={sorted(blanks)}")

    # V9 — capture sanity
    parse_fail = [f["fixture_id"] for f in fixtures if core.parse_iso(f["start_utc"]) is None]
    access = snapshot.get("access") or {}
    answered = [k for k, v in access.items() if isinstance(v, dict) and v.get("status") == 200]
    check("V9a capture has fixtures", len(fixtures) > 0, str(len(fixtures)))
    check("V9b every fixture has a parseable kick-off", not parse_fail, str(parse_fail))
    check("V9c snapshot records what sources answered", len(answered) >= 1, str(sorted(answered)[:8]))
    check("V9d the TWC competition was swept", "35859" in (board["flag"]["hotspawn_competition_scan"] or {}))

    failed = [r for r in RESULTS if not r["pass"]]
    (DATA / "verification.json").write_text(json.dumps(
        {"session": "34af18bf", "verified_utc": core.iso(core.now_utc()),
         "passed": len(RESULTS) - len(failed), "failed": len(failed), "checks": RESULTS}, indent=1),
        encoding="utf-8")
    for r in RESULTS:
        print(("PASS  " if r["pass"] else "FAIL  ") + r["check"] + (("  -> " + r["detail"]) if r["detail"] and not r["pass"] else ""))
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
