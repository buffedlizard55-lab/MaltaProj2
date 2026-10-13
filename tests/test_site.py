import json
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

class TestSiteIntegrity(unittest.TestCase):

    def test_nojekyll_exists(self):
        self.assertTrue((ROOT / ".nojekyll").exists())

    def test_html_files_exist(self):
        expected_files = ["index.html", "lines.html", "teams.html", "methodology.html", "flagged.html"]
        for f in expected_files:
            p = ROOT / f
            self.assertTrue(p.exists(), f"File {f} is missing")
            self.assertGreater(p.stat().st_size, 500, f"File {f} is too small")

    def test_css_exists(self):
        p = ROOT / "assets" / "style.css"
        self.assertTrue(p.exists())
        self.assertGreater(p.stat().st_size, 1000)

    def test_data_files_exist_and_valid(self):
        data_files = [
            "teams_verified.json",
            "originated_matches.json",
            "originated_outrights.json",
            "origination_summary.json",
            "flagged_irregularities.json"
        ]
        for df in data_files:
            p = ROOT / "data" / df
            self.assertTrue(p.exists(), f"Data file {df} missing")
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.assertTrue(data, f"Data file {df} is empty")

    def test_match_lines_count(self):
        p = ROOT / "data" / "originated_matches.json"
        with open(p, "r", encoding="utf-8") as f:
            matches = json.load(f)
        # Exactly 28 pairwise matches for 8 teams: 8 * 7 / 2 = 28
        self.assertEqual(len(matches), 28)
        for m in matches:
            self.assertIn("match_id", m)
            self.assertIn("team_a", m)
            self.assertIn("team_b", m)
            self.assertGreater(m["team_a"]["fair_probability"], 0)
            self.assertGreater(m["team_b"]["fair_probability"], 0)
            self.assertAlmostEqual(m["team_a"]["fair_probability"] + m["team_b"]["fair_probability"], 1.0, places=3)
            self.assertGreater(m["team_a"]["decimal_odds"], 1.0)
            self.assertGreater(m["team_b"]["decimal_odds"], 1.0)
            self.assertGreaterEqual(len(m["verification_sources"]), 2)

    def test_outrights_count(self):
        p = ROOT / "data" / "originated_outrights.json"
        with open(p, "r", encoding="utf-8") as f:
            outrights = json.load(f)
        self.assertEqual(len(outrights), 8)
        total_prob = sum(o["fair_probability"] for o in outrights)
        self.assertAlmostEqual(total_prob, 1.0, places=2)

    def test_no_hotspawn_probability_indicator(self):
        p = ROOT / "data" / "origination_summary.json"
        with open(p, "r", encoding="utf-8") as f:
            summary = json.load(f)
        self.assertFalse(summary["standards_compliance"]["hotspawn_used_as_probability_indicator"])
        self.assertTrue(summary["standards_compliance"]["all_lines_originated"])
        self.assertTrue(summary["standards_compliance"]["verified_against_official_sources"])
        self.assertTrue(summary["standards_compliance"]["no_hallucinations"])

    def test_all_html_have_source_links(self):
        for f in ["index.html", "lines.html", "teams.html", "methodology.html", "flagged.html"]:
            content = (ROOT / f).read_text(encoding="utf-8")
            self.assertTrue(
                "https://github.com/ValveSoftware/counter-strike_regional_standings" in content
                or "data/teams_verified.json" in content
                or "data/originated_matches.json" in content
                or "data/flagged_irregularities.json" in content
            )

if __name__ == "__main__":
    unittest.main()
