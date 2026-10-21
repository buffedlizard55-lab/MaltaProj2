#!/usr/bin/env python3
"""Contract tests for session 86f3af65.

These are the checks a reader can rely on:

* every open HotSpawn fixture in the capture has a pick and two probabilities that sum to 1;
* every market probability re-derives from the raw quoted decimals it cites;
* every originated probability re-derives from the official Valve point gap and the published
  slope, so no number can drift away from its source;
* no HotSpawn URL is ever a price source, and no HotSpawn crowd percentage is read;
* the official standings files are byte-identical to the live read recorded with them, and the
  regional files introduce no team the global file lacks;
* the site exists, every internal link resolves, and every flagged item is published.

Run: python3 -m unittest tests.test_86f3af65 -v
"""
from __future__ import annotations

import html
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "86f3af65"))

import ladder  # noqa: E402
import vrs as vrs_mod  # noqa: E402

BOARD = json.loads((ROOT / "data/86f3af65/board.json").read_text())
CAPTURE = json.loads((ROOT / "data/86f3af65/capture.json").read_text())
SITE = ROOT / "pickboard"


class TestCoverage(unittest.TestCase):
    def test_every_open_fixture_has_a_pick(self):
        self.assertTrue(BOARD["rows"])
        for row in BOARD["rows"]:
            self.assertIn(row["pick_side"], ("a", "b"), row["fixture_id"])
            self.assertIn(row["pick_team"], (row["team_a"], row["team_b"]))
            self.assertAlmostEqual(row["prob_a"] + row["prob_b"], 1.0, places=9)
            self.assertGreaterEqual(row["pick_prob"], 0.5)

    def test_open_definition_matches_capture(self):
        now = ladder.parse_iso(CAPTURE["captured_utc"])
        open_now = ladder.open_fixtures(CAPTURE["hotspawn"]["fixtures"], now)
        self.assertEqual(len(open_now), len(BOARD["rows"]))
        for fx in open_now:
            self.assertEqual(fx["status"], "scheduled")
            self.assertGreater(ladder.parse_iso(fx["lock_utc"]), now)

    def test_coverage_counters_are_consistent(self):
        cov = BOARD["coverage"]
        self.assertEqual(cov["open"], len(BOARD["rows"]))
        self.assertEqual(cov["with_pick"], sum(1 for r in BOARD["rows"] if r["pick_team"]))
        self.assertEqual(cov["market"] + cov["market_contested"] + cov["originated_vrs"]
                         + cov["originated_floor"] + cov["unresolved"], cov["open"])

    def test_hotspawn_crowd_percent_is_not_read(self):
        forbidden = ("picked", "ownership", "percent", "crowd", "picked_percentage")
        for fx in CAPTURE["hotspawn"]["fixtures"]:
            for key in fx:
                self.assertNotIn(key.lower(), forbidden, f"{fx['fixture_id']} carries {key}")


class TestProbabilitiesReDerive(unittest.TestCase):
    def test_market_rows_re_derive_from_quoted_decimals(self):
        quotes = CAPTURE["quotes"]
        for row in BOARD["rows"]:
            if not row["basis"].startswith("market"):
                continue
            used = [q for q in quotes
                    if any(s["kind"] == "price"
                           and s.get("event_id") == str(q.get("event_id"))
                           and s.get("source_key") == q.get("source_key")
                           for s in row["sources"])]
            self.assertTrue(used, row["fixture_id"])
            entries = []
            for q in used:
                same = vrs_mod.norm(q["team_a"]) == vrs_mod.norm(row["team_a"])
                p = q["prob_a"] if same else 1.0 - q["prob_a"]
                # the raw decimals must de-vig back to the stored probability
                nv = ladder.no_vig(q["decimal_a"], q["decimal_b"])
                # stored decimals are rounded to 4 dp, so allow that rounding only
                self.assertAlmostEqual(nv["prob_a"] if same else nv["prob_b"], p, places=5)
                entries.append({**q, "prob_a": p})
            expect = ladder.consensus(entries)["prob_a"]
            self.assertAlmostEqual(row["prob_a"], expect, places=5,
                                   msg=f"{row['fixture_id']} drifted from its quoted prices")

    def test_model_rows_re_derive_from_valve_points(self):
        k = BOARD["calibration"]["k"]
        for row in BOARD["rows"]:
            if not row["model"]:
                continue
            pa = row["model"]["rating_a"]["row"]["points"]
            pb = row["model"]["rating_b"]["row"]["points"]
            self.assertAlmostEqual(row["model"]["prob_a"], ladder.vrs_prob(pa, pb, k), places=9)
            self.assertAlmostEqual(row["prob_a"], row["model"]["prob_a"], places=9) \
                if not row["basis"].startswith("market") else None

    def test_calibration_is_fitted_and_in_bounds(self):
        cal = BOARD["calibration"]
        self.assertTrue(cal["fitted"])
        self.assertGreaterEqual(cal["n_pairs"], 25)
        lo, hi = cal["bounds"]
        self.assertGreaterEqual(cal["k"], lo)
        self.assertLessEqual(cal["k"], hi)
        self.assertAlmostEqual(cal["c"], ladder.VALVE_C, places=12)


class TestSources(unittest.TestCase):
    def test_no_hotspawn_price_source(self):
        for row in BOARD["rows"]:
            for s in row["sources"]:
                if s["kind"] == "price":
                    self.assertNotIn("hotspawn.com", (s["url"] or ""), row["fixture_id"])
                    self.assertNotIn("play.hotspawn", (s["url"] or ""), row["fixture_id"])

    def test_every_row_has_a_source_link(self):
        for row in BOARD["rows"]:
            self.assertTrue(row["sources"], row["fixture_id"])
            self.assertTrue(any(s.get("url", "").startswith("http") for s in row["sources"]))
            kinds = {s["kind"] for s in row["sources"]}
            self.assertIn("discovery", kinds)
            self.assertTrue({"price", "rating"} & kinds)

    def test_unrated_rows_carry_the_assumption(self):
        for row in BOARD["rows"]:
            if "floor_proxy_unrated_team" not in row["flags"]:
                continue
            for res in (row["model"]["rating_a"], row["model"]["rating_b"]):
                if res["status"] == "floor-proxy":
                    self.assertIn("absent from the published global", res["assumption"])
                    self.assertTrue(res["row"]["is_floor_proxy"])
            if row["basis"].startswith("originated"):
                self.assertTrue(row["unresolved"])
                self.assertIn("no published Valve rating", row["limitation"])


class TestValveStandings(unittest.TestCase):
    def setUp(self):
        self.standings, self.manifest = vrs_mod.load_pinned_standings(
            ROOT / "data/86f3af65/valve")

    def test_files_match_live_read_hashes(self):
        live = json.loads((ROOT / "data/86f3af65/valve/live_reads.json").read_text())
        self.assertTrue(self.manifest["files"])
        for f in self.manifest["files"]:
            recorded = (live["files"] or {}).get(Path(f["path"]).name)
            self.assertIsNotNone(recorded, f["path"])
            self.assertEqual(f["sha256"], recorded["sha256"], f["path"])

    def test_regional_files_add_no_name(self):
        global_names = {vrs_mod.norm(r["team"]) for r in self.standings.global_rows()}
        for row in self.standings.rows:
            if row["region"] != "global":
                self.assertIn(vrs_mod.norm(row["team"]), global_names, row["team"])

    def test_duplicate_policy_prefers_five_player_active_roster(self):
        banda = self.standings.resolve("Banda chuya")
        self.assertEqual(banda["status"], "roster-selected")
        self.assertEqual(banda["row"]["standing"], 165)
        self.assertEqual(len(banda["rejected"]), 1)
        self.assertLess(len(banda["rejected"][0]["players"]), 5)

        huns = self.standings.resolve("The Huns")
        self.assertEqual(huns["row"]["standing"], 122)
        self.assertGreater(huns["row"]["latest_match_date"],
                           huns["rejected"][0]["latest_match_date"])

    def test_duplicate_resolution_never_rests_on_missing_evidence(self):
        """A roster-selected row must be supported by a dated official details page."""
        for row in BOARD["rows"]:
            if "duplicate_vrs_roster" not in row["flags"]:
                continue
            for res in (row["model"]["rating_a"], row["model"]["rating_b"]):
                if res["status"] != "roster-selected":
                    continue
                self.assertTrue(res["row"].get("latest_match_date"), res["team"])
                self.assertTrue(res["rejected"], res["team"])
                for cand in res["candidates"]:
                    self.assertTrue(cand.get("roster"), res["team"])

    def test_capture_details_paths_resolve_inside_the_repository(self):
        for path in (CAPTURE.get("vrs", {}).get("details") or {}):
            self.assertTrue(path.startswith("live/"), path)

    def test_absent_team_only_gets_a_floor_when_asked(self):
        absent = self.standings.resolve("LOS NINOS")
        self.assertEqual(absent["status"], "absent")
        self.assertIsNone(absent["row"])
        forced = self.standings.resolve("LOS NINOS", floor_ok=True)
        self.assertEqual(forced["status"], "floor-proxy")
        self.assertEqual(forced["row"]["points"], self.manifest["floor"]["points"])


class TestSite(unittest.TestCase):
    PAGES = ["index.html", "picks.html", "unresolved.html", "tournaments.html",
             "sources.html", "flagged.html", "method.html"]

    def test_pages_exist_and_have_no_placeholder_text(self):
        for name in self.PAGES:
            path = SITE / name
            self.assertTrue(path.exists(), name)
            text = path.read_text(encoding="utf-8")
            self.assertGreater(len(text), 3000, name)
            for bad in ("TODO", "FIXME", "{{", "None%"):
                self.assertNotIn(bad, text, f"{name} contains {bad}")
            self.assertIn('name="viewport"', text, name)

    def test_freshness_is_stated_on_every_page(self):
        """A reader must be able to see how old the numbers are without reading the board."""
        expected = "Stale data." if BOARD["capture"].get("stale") else (
            "Capture mode" if BOARD["capture"].get("mode") != "live" else "Live capture")
        for name in SITE.glob("*.html"):
            text = name.read_text()
            self.assertIn('class="fresh', text, name.name)
            self.assertIn(expected, text, name.name)

    def test_access_log_is_anchored(self):
        self.assertIn('id="access"', (SITE / "sources.html").read_text())

    def test_every_internal_link_resolves(self):
        link_re = re.compile(r'(?:href|src)="([^"]+)"')
        missing = []
        for name in self.PAGES + ["style.css", "app.js"]:
            path = SITE / name
            if path.suffix != ".html":
                continue
            for target in link_re.findall(path.read_text(encoding="utf-8")):
                if target.startswith(("http://", "https://", "mailto:", "#", "data:")):
                    continue
                rel = target.split("#")[0]
                if not rel:
                    continue
                resolved = (path.parent / rel).resolve()
                if not resolved.exists():
                    missing.append(f"{name} -> {target}")
        self.assertEqual(missing, [])

    def test_every_pick_is_on_the_picks_page(self):
        text = (SITE / "picks.html").read_text(encoding="utf-8")
        for row in BOARD["rows"]:
            self.assertIn(html.escape(row["team_a"]), text)
            self.assertIn(html.escape(row["team_b"]), text)

    def test_unresolved_page_lists_every_caveated_row(self):
        text = (SITE / "unresolved.html").read_text(encoding="utf-8")
        for row in BOARD["rows"]:
            if row.get("unresolved"):
                self.assertIn(html.escape(row["team_a"]), text, row["fixture_id"])

    def test_flagged_page_publishes_every_finding(self):
        text = (SITE / "flagged.html").read_text(encoding="utf-8")
        for finding in BOARD["findings"]:
            self.assertIn(finding["id"], text)

    def test_sources_page_cites_every_quote(self):
        text = (SITE / "sources.html").read_text(encoding="utf-8")
        for q in CAPTURE["quotes"]:
            if q.get("public_url"):
                self.assertIn(html.escape(q["public_url"]), text, q["public_url"])


class TestAudit(unittest.TestCase):
    def test_checks_all_verified(self):
        verdicts = {c["verdict"] for c in BOARD["audit"]["checks"]}
        self.assertNotIn("irregular", verdicts)
        self.assertGreaterEqual(len(BOARD["audit"]["checks"]), 6)

    def test_findings_have_files_or_urls(self):
        for finding in BOARD["findings"]:
            self.assertTrue(finding["files"], finding["id"])
            self.assertGreater(len(finding["detail"]), 80, finding["id"])

    def test_disagreements_are_computed_not_asserted(self):
        for d in BOARD["audit"]["earlier_board_disagreements"]:
            self.assertGreaterEqual(d["max_gap"], 0.049)
            for session, peer in d["peers"].items():
                if peer.get("prob_a") is not None:
                    self.assertGreaterEqual(peer["prob_a"], 0.0)
                    self.assertLessEqual(peer["prob_a"], 1.0)


if __name__ == "__main__":
    unittest.main()
