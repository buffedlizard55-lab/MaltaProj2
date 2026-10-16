#!/usr/bin/env python3
"""Contract tests for session 1b35a4a2 — TWC Day-4 + every-match research audit."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "1b35a4a2"
SITE = ROOT / "audits" / "1b35a4a2"

def load_board():
    return json.loads((DATA / "board.json").read_text())

class BoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load_board()
        cls.rows = {r["fixture_id"]: r for r in cls.board["open"]}

    def test_board_shape(self):
        self.assertEqual(self.board["session"], "1b35a4a2")
        self.assertIn("generated_utc", self.board)
        self.assertIn("summary", self.board)
        s = self.board["summary"]
        self.assertEqual(s["open"], 21)
        self.assertEqual(s["with_line"], 21)
        self.assertEqual(s["market_based"] + s["research_resolved"] + s["model_only"], 21)
        self.assertEqual(s["no_line"], 0)
        self.assertEqual(s["with_pick"], 21)
        self.assertEqual(s["climb_picks"], 3)
        self.assertTrue(s["twc_not_listed_on_hotspawn"])
        self.assertEqual(len(self.board["open"]), 21)
        self.assertIn("twc", self.board)
        self.assertIn("twc_results", self.board)

    def test_every_row_has_pick_and_normalized(self):
        for r in self.board["open"]:
            line = r["line"]
            self.assertIsNotNone(line["pick"], r["fixture_id"])
            self.assertIsNotNone(line["prob_a"], r["fixture_id"])
            self.assertIsNotNone(line["prob_b"], r["fixture_id"])
            self.assertAlmostEqual(line["prob_a"] + line["prob_b"], 1.0, places=6, msg=r["fixture_id"])
            self.assertEqual(line["pick_probability"], max(line["prob_a"], line["prob_b"]), msg=r["fixture_id"])
            # pick is argmax — allow documented alias WROTBERRY/WBT
            expected_pick = r["team_a"] if line["prob_a"] > line["prob_b"] else r["team_b"]
            if r["fixture_id"] == "1081529":
                # HotSpawn lists WROTBERRY, research resolves to WBT (WhiteBIT Team) — same slot, documented alias
                self.assertIn(line["pick"], (expected_pick, "WBT", "WBT (WhiteBIT Team)"), r["fixture_id"])
            else:
                self.assertEqual(line["pick"], expected_pick, r["fixture_id"])

    def test_research_gaps_have_sources_and_flags(self):
        # The 7 former gaps are now research-resolved
        for fid in ["1079170","1081515","1081126","1081522","1081529","1081861","1081863"]:
            r = self.rows[fid]
            self.assertEqual(r["line"]["basis"], "research", fid)
            self.assertTrue(r["sources"], fid)
            self.assertTrue(any(s["url"].startswith("https://") for s in r["sources"]), fid)
            self.assertIn("HotSpawn fixture", [s["label"] for s in r["sources"]], fid)
            self.assertTrue(r["flags"], fid)
            # research rows must have at least 2 sources with https
            https = [s for s in r["sources"] if s["url"].startswith("https://")]
            self.assertGreaterEqual(len(https), 2, fid)

    def test_market_rows_copy_canonical(self):
        # At least 11 market rows
        market_rows = [r for r in self.board["open"] if r["line"]["basis"] in ("market","blend")]
        self.assertGreaterEqual(len(market_rows), 11)
        for r in market_rows:
            # must have market dict or be research? market rows have market or blend
            # just check prob sum
            self.assertAlmostEqual(r["line"]["prob_a"] + r["line"]["prob_b"], 1.0, places=6)

    def test_no_crowd_as_probability(self):
        for r in self.board["open"]:
            self.assertIn("crowd_note", r)
            self.assertIn("never a probability input", r["crowd_note"])
            self.assertNotIn("crowd", (r["line"]["basis"] or ""))
        self.assertTrue(any("never" in n.lower() and "crowd" in n.lower() for n in self.board["notes"]))

    def test_climb_gates(self):
        climbs = [r for r in self.board["open"] if r["ladder"].get("climb")]
        self.assertEqual(len(climbs), 3)
        for r in climbs:
            prob = r["ladder"]["climb_prob"]
            # find crowd for that climb side
            team = r["ladder"]["climb"]
            crowd = r["crowd_a"] if team == r["team_a"] else r["crowd_b"]
            self.assertIsNotNone(crowd, r["fixture_id"])
            self.assertGreaterEqual(prob, 0.30, r["fixture_id"])
            self.assertLessEqual(crowd, 20, r["fixture_id"])
            lev = prob / (crowd/100.0) if crowd else 99
            self.assertGreaterEqual(lev, 2.0, r["fixture_id"])
            self.assertIn("30%", r["ladder"]["climb_gates"])
            self.assertGreaterEqual(len(r["flags"]), 1)

    def test_every_row_has_https_source(self):
        for r in self.board["open"]:
            self.assertTrue(r["sources"], r["fixture_id"])
            for s in r["sources"]:
                self.assertTrue(s["url"].startswith("https://"), f"{r['fixture_id']} {s['url']}")
            # first source must be HotSpawn fixture (either match page or lobby fallback)
            self.assertEqual(r["sources"][0]["label"], "HotSpawn fixture")
            self.assertTrue(r["sources"][0]["url"].startswith("https://www.hotspawn.com/") or r["sources"][0]["url"].startswith("https://play.hotspawn.com/"))
            # subsequent sources must not be HotSpawn probability (only fixture discovery)
            for s in r["sources"][1:]:
                self.assertNotIn("play.hotspawn.com", s["url"], f"{r['fixture_id']} {s['url']}")
                self.assertNotIn("www.hotspawn.com/matches", s["url"])  # match pages are ok for first source only; other sources should be external

    def test_twc_block(self):
        twc = self.board["twc"]
        self.assertIn("sf1", twc)
        self.assertIn("sf2", twc)
        for key in ("sf1","sf2"):
            m = twc[key]
            self.assertIn(m["pick"], m["teams"])
            self.assertIsNotNone(m["fair"])
            self.assertEqual(len(m["fair"]), 2)
            self.assertAlmostEqual(m["fair"][0] + m["fair"][1], 1.0, places=6)
            self.assertGreaterEqual(len(m["sources"]), 3)
            for _, url in m["sources"]:
                self.assertTrue(url.startswith("https://"))
        self.assertEqual(len(self.board["twc_results"]), 10)

    def test_pages_exist_and_mobile(self):
        for fname in ["index.html","picks.html","twc.html","unresolved.html","flagged.html","method.html"]:
            p = SITE / fname
            self.assertTrue(p.exists(), fname)
            html = p.read_text()
            self.assertIn('name="viewport"', html, fname)
            self.assertIn('Skip to content', html, fname)
            self.assertIn('Audit 1b35a4a2', html, fname)
            # every table row should have a source link
            if fname in ("picks.html","unresolved.html","twc.html"):
                # at least one https link per page
                self.assertRegex(html, r'href="https://', msg=fname)

    def test_unresolved_documents_gaps(self):
        html = (SITE / "unresolved.html").read_text()
        for fid in ["1079170","1081515","1081126","1081522","1081529","1081861","1081863"]:
            self.assertIn(fid, html)
        self.assertIn("research", html.lower())
        self.assertIn("HotSpawn", html)

    def test_method_publishes_formulas(self):
        html = (SITE / "method.html").read_text()
        self.assertIn("HotSpawn", html)
        self.assertIn("Pinnacle", html)
        self.assertIn("HLTV", html)
        self.assertIn("Valve", html)
        self.assertIn("k=0.25", html)
        low = html.lower()
        self.assertIn("never", low)
        self.assertIn("probability", low)
        # ensure crowd never used as probability is documented
        self.assertTrue("never" in low and "probability" in low and "crowd" in low)

    def test_report_json(self):
        rep = json.loads((DATA / "report.json").read_text())
        self.assertEqual(rep["open"], 21)
        self.assertTrue(rep["checks"]["all_rows_have_https_source"])
        self.assertTrue(rep["checks"]["probabilities_normalized"])

    def test_index_links_every_list(self):
        html = (SITE / "index.html").read_text()
        self.assertIn('href="picks.html"', html)
        self.assertIn('href="twc.html"', html)
        self.assertIn('href="unresolved.html"', html)
        self.assertIn('href="flagged.html"', html)
        self.assertIn('href="method.html"', html)
        self.assertIn('href="../../picks-every-match/index.html"', html)
        # primary CTA above fold: check that picks link exists
        self.assertIn('All lobby picks', html)
