#!/usr/bin/env python3
"""Unit contracts for session 34af18bf (pick desk).

The tests that touch the published board skip themselves when the board has not
been generated in this checkout yet (the collector only runs on GitHub-hosted
runners), so the suite stays green on a fresh clone.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "34af18bf"))

import core  # noqa: E402
import research  # noqa: E402

DATA = ROOT / "data" / "34af18bf"
PAGES = ROOT / "pickdesk"


class TestArithmetic(unittest.TestCase):
    def test_american_to_decimal(self):
        self.assertEqual(core.american_to_decimal(150), 2.5)
        self.assertEqual(core.american_to_decimal(-200), 1.5)
        self.assertEqual(core.american_to_decimal(100), 2.0)
        self.assertIsNone(core.american_to_decimal(0))
        self.assertIsNone(core.american_to_decimal(50))

    def test_no_vig_is_two_way_and_removes_the_overround(self):
        nv = core.no_vig(1.85, 1.85)
        self.assertAlmostEqual(nv["prob_a"], 0.5, places=9)
        self.assertAlmostEqual(nv["prob_b"], 0.5, places=9)
        self.assertAlmostEqual(nv["overround"], 2 / 1.85, places=9)
        nv2 = core.no_vig(1.20, 4.00)
        self.assertAlmostEqual(nv2["prob_a"] + nv2["prob_b"], 1.0, places=9)
        self.assertGreater(nv2["prob_a"], 0.7)
        self.assertIsNone(core.no_vig(None, 2.0))

    def test_blend_weights_pinnacle_double(self):
        readings = [{"prob_a": 0.60, "prob_b": 0.40, "weight": 2.0},
                    {"prob_a": 0.40, "prob_b": 0.60, "weight": 1.0}]
        merged = core.blend(readings)
        self.assertAlmostEqual(merged["prob_a"], (0.60 * 2 + 0.40) / 3, places=6)
        self.assertEqual(merged["sources"], 2)

    def test_canon_is_alias_aware(self):
        self.assertEqual(core.canon("BETBOOM Team"), core.canon("BetBoom"))
        self.assertEqual(core.canon("NIP"), core.canon("Ninjas in Pyjamas"))
        self.assertEqual(core.canon("Aurora Gaming"), core.canon("aurora"))
        self.assertNotEqual(core.canon("Falcons"), core.canon("FURIA"))


class TestResearchLedger(unittest.TestCase):
    def test_every_source_has_a_url_and_a_label(self):
        for key, (label, url) in research.SOURCES.items():
            self.assertTrue(url.startswith("https://"), key)
            self.assertTrue(label.strip(), key)

    def test_results_reference_real_sources_and_never_guess_maps(self):
        for row in research.TWC_RESULTS:
            self.assertIn(row["source"], research.SOURCES)
            self.assertIn(row["score"], {"2-0", "2-1"})
            if row["maps"] is not None:
                # convention: (map, row-winner's score, row-loser's score). Regulation ends at 13,
                # overtime maps end 16-13/19-16, so a map never needs more than 30 rounds for one side.
                won = 0
                for name, a, b, note in row["maps"]:
                    self.assertIsInstance(name, str)
                    self.assertIsInstance(note, str)
                    self.assertGreaterEqual(a, 0)
                    self.assertGreaterEqual(b, 0)
                    self.assertLessEqual(max(a, b), 30, f"map {name} score {a}-{b} out of range")
                    self.assertGreaterEqual(max(a, b), 13, f"map {name} score {a}-{b} has no winner")
                    if a > b:
                        won += 1
                self.assertEqual(f"{won}-{len(row['maps']) - won}", row["score"],
                                 f"map results do not add up to the series score for {row['winner']}")

    def test_day4_rows_carry_hotspawn_ids_ownership_and_kickoff(self):
        ids = {r["fixture_id"] for r in research.TWC_DAY4}
        self.assertEqual(ids, {"1080207", "1080208"})
        for row in research.TWC_DAY4:
            self.assertIn(row["source"], research.SOURCES)
            self.assertTrue(row["start_utc"].endswith("Z"))
            self.assertEqual(sum(row["crowd_ownership"].values()), 100)
            self.assertTrue(row["hotspawn_url"].startswith("https://www.hotspawn.com/matches/"))

    def test_roster_audit_claims_are_sourced(self):
        for team, entry in research.ROSTER_AUDIT.items():
            self.assertTrue(entry["sources"], team)
            for key in entry["sources"]:
                self.assertIn(key, research.SOURCES, f"{team} -> {key}")
            self.assertTrue(entry["last_active_lineup_change"] or entry.get("last_active_lineup_change") is None)

    def test_no_crowd_percentage_is_stored_as_a_probability(self):
        for row in research.TWC_DAY4:
            for value in row["crowd_ownership"].values():
                self.assertNotIn("probability", str(row).lower().replace("crowd_ownership", ""))


class TestPublishedBoard(unittest.TestCase):
    """Only runs once the board exists in this checkout."""

    @classmethod
    def setUpClass(cls):
        cls.board_path = DATA / "board.json"
        if not cls.board_path.exists():
            raise unittest.SkipTest("board.json not generated in this checkout")
        cls.board = json.loads(cls.board_path.read_text(encoding="utf-8"))

    def rows(self):
        return self.board["fixtures"] + self.board["twc"]

    def test_every_row_has_a_pick_and_a_basis(self):
        for row in self.rows():
            self.assertIn(row["basis"], {"market", "originated", "blank"})
            if row["basis"] == "blank":
                self.assertIsNone(row["pick"])
            else:
                self.assertIn(row["pick"], (row["team_a"], row["team_b"]))
                self.assertGreater(row["probability"], 0.0)
                self.assertLess(row["probability"], 1.0)

    def test_every_resolved_row_has_a_source_link(self):
        for row in self.rows():
            if row["basis"] != "blank":
                self.assertTrue(row["source_links"], row["fixture_id"])
                for link in row["source_links"]:
                    self.assertTrue(link["url"].startswith("https://"), row["fixture_id"])

    def test_market_rows_rederive_from_their_readings(self):
        for row in self.rows():
            if row["basis"] != "market":
                continue
            merged = core.blend([{"prob_a": r["prob_a"], "prob_b": r["prob_b"], "weight": r["weight"]}
                                 for r in row["readings"]])
            self.assertAlmostEqual(merged["prob_a"], row["prob_a"], places=4)

    def test_climb_picks_respect_the_published_gates(self):
        activated = 0
        for row in self.rows():
            if not row.get("climb"):
                continue
            activated += 1
            gates = row["climb_gates"]
            self.assertTrue(all(g["pass"] for g in gates.values()), row["fixture_id"])
            self.assertGreaterEqual(row["climb_probability"], 0.20)
            self.assertGreater(row["climb_differential"], 0)
            self.assertGreaterEqual(len(row["climb_flags"]), 2)
        self.assertLessEqual(activated, 3)

    def test_unresolved_rows_are_reported_and_explained(self):
        blanks = [r["fixture_id"] for r in self.rows() if r["basis"] == "blank"]
        self.assertEqual([r["fixture_id"] for r in self.board["unresolved"]], blanks)
        for entry in self.board["unresolved"]:
            self.assertTrue(entry["reason"].strip())


class TestPublishedPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PAGES.exists() or not any(PAGES.glob("*.html")):
            raise unittest.SkipTest("pick desk pages not generated in this checkout")

    def test_pages_are_mobile_first(self):
        for page in sorted(PAGES.glob("*.html")):
            text = page.read_text(encoding="utf-8")
            self.assertIn('name="viewport"', text, page.name)
            self.assertEqual(text.count("<h1"), 1, page.name)
            self.assertIn("width=device-width", text, page.name)

    def test_executive_summary_links_the_picks_and_unresolved_lists(self):
        text = (PAGES / "index.html").read_text(encoding="utf-8")
        for target in ("picks.html", "twc.html", "unresolved.html", "flagged.html", "method.html"):
            self.assertIn(f'href="{target}"', text)

    def test_internal_links_resolve(self):
        broken = []
        for page in sorted(PAGES.glob("*.html")):
            text = page.read_text(encoding="utf-8")
            for href in re.findall(r'href="([^"#][^"]*)"', text):
                if href.startswith(("http://", "https://", "mailto:")):
                    continue
                if href.split("#")[0] and not (page.parent / href.split("#")[0]).resolve().exists():
                    broken.append((page.name, href))
        self.assertFalse(broken, broken)

    def test_twc_page_states_the_roster_position_and_the_upset(self):
        text = (PAGES / "twc.html").read_text(encoding="utf-8")
        self.assertIn("9z", text)
        self.assertIn("13-1", text)
        self.assertIn("deko", text)


if __name__ == "__main__":
    unittest.main()
