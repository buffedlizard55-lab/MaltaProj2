import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "data/4b915077/day2-review.json").read_text())
PAGE = (ROOT / "strategy/day2.html").read_text()


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.extend(v for k, v in attrs if k == "href" and v)


class DayTwoReviewTests(unittest.TestCase):
    def test_all_four_day_two_series_have_direct_hltv_match_sources(self):
        rows = DATA["day2_results"]
        self.assertEqual(len(rows), 4)
        self.assertEqual({r["team_a"] for r in rows}, {"Aurora", "9z", "PARIVISION", "Legacy"})
        for row in rows:
            self.assertTrue(row["match_source"].startswith("https://www.hltv.org/matches/"))
            self.assertEqual(row["official_results_source"], "https://www.hltv.org/results?event=8932")
            self.assertTrue(row["score"] in ("2-0", "1-2"))

    def test_aurora_9z_market_probability_and_contrarian_thresholds_are_consistent(self):
        row = DATA["day3_fixtures"][0]
        self.assertEqual(row["hotspawn_fixture_id"], "1080205")
        self.assertEqual(row["safe_pick"], "Aurora")
        self.assertEqual(row["leaderboard_pick"], "Aurora")
        self.assertEqual(row["hotspawn_crowd_ownership_pct"], {"Aurora": 80, "9z": 20})
        self.assertAlmostEqual(35 / 20, row["contrarian_rules"]["underdog_leverage"])
        self.assertLess(row["contrarian_rules"]["underdog_leverage"], 2.0)
        self.assertEqual(row["market_consensus_probability_pct"], 66)
        for url in row["market_source_urls"]:
            self.assertTrue(url.startswith("https://"))

    def test_betboom_legacy_is_explicitly_separate_model_only_and_flagged(self):
        row = DATA["day3_fixtures"][1]
        self.assertFalse(row["hotspawn_listed_in_snapshot"])
        self.assertEqual(row["model_pick"], "Legacy")
        self.assertEqual(row["model_probability_pct"], 63)
        self.assertIn("model estimate", row["method"])
        self.assertIn("live market line", row["review_flag"])
        self.assertIn("day-two form is contrary context", row["limitation"])
        self.assertTrue(row["rating_source"].startswith("https://github.com/ValveSoftware/"))

    def test_page_has_phone_viewport_executive_result_and_unresolved_sections(self):
        self.assertIn('name="viewport"', PAGE)
        self.assertIn("Day 2 → day 3", PAGE)
        self.assertIn("Executive take", PAGE)
        self.assertIn("unresolved item and limitations", PAGE.lower())
        self.assertIn("aria-current", PAGE)
        self.assertIn("not betting odds", PAGE)
        self.assertIn("day1.html", PAGE)

    def test_page_local_links_resolve(self):
        parser = AnchorParser()
        parser.feed(PAGE)
        for href in parser.hrefs:
            if href.startswith(("http://", "https://", "mailto:")):
                continue
            target = (ROOT / "strategy" / href.split("#", 1)[0]).resolve()
            self.assertTrue(target.exists(), f"Missing target for {href}")

    def test_landing_exec_summary_exposes_day_two_review(self):
        template = (ROOT / "scripts/build_site.py").read_text()
        self.assertIn('href="strategy/day2.html"', template)
        home = (ROOT / "index.html").read_text()
        self.assertIn('href="strategy/day2.html"', home)

    def test_data_sources_include_official_schedule_and_results(self):
        self.assertEqual(DATA["results_source"], "https://www.hltv.org/results?event=8932")
        self.assertEqual(DATA["schedule_source"], "https://www.hltv.org/events/8932/matches")
        for row in DATA["day3_fixtures"]:
            self.assertTrue(row["match_source"].startswith("https://www.hltv.org/matches/"))
            self.assertTrue(row["schedule_source"].startswith("https://www.hltv.org/events/8932/"))


if __name__ == "__main__":
    unittest.main()
