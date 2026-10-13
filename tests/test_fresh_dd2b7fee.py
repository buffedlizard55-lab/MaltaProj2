#!/usr/bin/env python3
"""Tests for session dd2b7fee's fresh pick'em board.

Guards the evidence-first contract:
  * the builder regenerates cleanly from the two input snapshots,
  * every lobby fixture in the current window appears exactly once in board.json,
  * every priced row carries >=1 official source URL; unpriced rows have none,
  * probabilities are sane and consistently computed for the PICKED side,
  * Hotspawn crowd pick-percentage fields are never consumed or rendered,
  * rendered pages are mobile-first and fully source-linked.
"""
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAP = ROOT / "data" / "dd2b7fee" / "lines_snapshot.json"
BOARD = ROOT / "data" / "dd2b7fee" / "board.json"
FX = ROOT / "data" / "hotspawn_matches.json"
BUILDER = ROOT / "scripts" / "dd2b7fee" / "build_board.py"
PAGES = [
    ROOT / "fresh" / "index.html",
    ROOT / "fresh" / "cs2" / "index.html",
    ROOT / "fresh" / "flagged" / "index.html",
    ROOT / "fresh" / "method" / "index.html",
]
WINDOW_START = "2026-10-13T20:00"


def run_builder():
    out = subprocess.run([sys.executable, str(BUILDER)], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, f"builder failed:\n{out.stdout}\n{out.stderr}"
    return out


def window_fixture_ids():
    fx = json.loads(FX.read_text())
    ids = []
    for m in fx["matches"]:
        if m.get("sport") != "cs2":
            continue
        if m.get("status") not in ("scheduled", "started"):
            continue
        if m.get("status") == "scheduled":
            st = m.get("scheduled_start_time") or ""
            if not st.startswith("2026-10-1") or st < WINDOW_START:
                continue
        ids.append(int(m["fixture_id"]))
    return sorted(ids)


def test_builder_runs_and_emits_pages():
    run_builder()
    for p in PAGES:
        assert p.exists() and p.stat().st_size > 5000, f"missing/thin page {p}"
    assert BOARD.exists(), "board.json missing"


def test_snapshot_integrity():
    snap = json.loads(SNAP.read_text())
    for src in ("bovada", "pinnacle", "kalshi", "hltv_analytics", "polymarket"):
        assert src in snap["sources"], f"source {src} missing"
    assert snap["retrieval_window_utc"].startswith("2026-10-13")
    assert snap["inventory_basis"]["fixtures_current_window_cs2"] >= 30
    # raw quote presence
    assert len(snap["sources"]["bovada"]["markets"]) >= 9
    assert len(snap["sources"]["kalshi"]["markets"]) >= 18
    assert len(snap["sources"]["pinnacle"]["markets"]) >= 10


def test_full_lobby_coverage():
    run_builder()
    board = json.loads(BOARD.read_text())
    want = window_fixture_ids()
    got = sorted(r["id"] for r in board["rows"])
    assert got == want, f"coverage mismatch: want {want}, got {got}"
    assert len(board["rows"]) >= 30


def test_every_priced_row_is_source_linked():
    board = json.loads(BOARD.read_text())
    priced = [r for r in board["rows"] if r["p"] is not None]
    assert len(priced) >= 15, "expected at least 15 priced rows"
    for r in priced:
        urls = [q[3] for q in r["quotes"]]
        assert urls, f"row {r['id']} priced without sources"
        for u in urls:
            assert u.startswith("https://"), f"non-official link in row {r['id']}: {u}"
    for r in board["rows"]:
        if r["p"] is None and r["kind"] in ("series", "seed"):
            assert r["quotes"] == [], f"blank row {r['id']} unexpectedly carries quotes"


def test_probability_consistency():
    board = json.loads(BOARD.read_text())
    for r in board["rows"]:
        p = r["p"]
        if p is None:
            assert r["p_pick"] is None
            continue
        assert 0.0 < p < 1.0, f"row {r['id']} bad p {p}"
        lo, hi = r["band"]
        assert lo <= p <= hi + 1e-9, f"row {r['id']} p outside source band"
        assert abs(r["p_pick"] - max(p, 1 - p)) < 1e-9
        assert 0.5 < r["p_pick"] < 1.0
        assert r["pname"] in (r["a"], r["b"])
        assert (r["pick"] == "a") == (p >= 0.5)


def test_no_crowd_percent_anywhere():
    builder_src = BUILDER.read_text()
    assert "pick_pct" not in builder_src, "builder references Hotspawn crowd pick fields"
    run_builder()
    for p in PAGES:
        t = p.read_text()
        assert "pick_pct" not in t and "picked_percent" not in t, f"crowd field leaked into {p.name}"
    board = json.loads(BOARD.read_text())
    assert "pick_pct" not in json.dumps(board), "crowd fields leaked into board.json"


def test_mobile_first_and_links():
    run_builder()
    for p in PAGES:
        t = p.read_text()
        assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in t, f"{p.name} not mobile-first"
        assert "https://play.hotspawn.com/lobby" in t
        hrefs = re.findall(r'href="([^"]+)"', t)
        assert hrefs, f"{p.name} has no links"
        for h in hrefs:
            assert not h.startswith("javascript:"), f"bad href in {p.name}"


def test_flagged_page_publish():
    t = (ROOT / "fresh" / "flagged" / "index.html").read_text()
    # the load-bearing flags must be present
    for needle in ("Start-time disagreement", "pulled intraday", "seed quotes", "Polymarket",
                   "EAC Extra", "WBT Academy"):
        assert needle in t, f"flag '{needle}' missing from flagged page"


def test_picks_detect_regeneration():
    """board.json regeneration must be deterministic for identical inputs."""
    run_builder()
    b1 = json.loads(BOARD.read_text())
    run_builder()
    b2 = json.loads(BOARD.read_text())
    assert [[r["id"], r["p"], r["pname"]] for r in b1["rows"]] == [[r["id"], r["p"], r["pname"]] for r in b2["rows"]]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    sys.exit(1 if failed else 0)
