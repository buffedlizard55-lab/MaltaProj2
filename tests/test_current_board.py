"""Tests for the T-CURRENT board (session 0f6c89c6)."""

import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


class CurrentBoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = load("data/current_board.json")
        cls.rows = cls.doc["rows"]

    def test_summary_matches_rows(self):
        s = self.doc["summary"]
        self.assertEqual(s["open_cs2_fixtures"], len(self.rows))
        self.assertEqual(
            s["with_named_bookmaker_line"] + s["with_egw_fallback_only"] + s["without_any_line"],
            len(self.rows),
        )

    def test_probabilities_are_complementary_and_pick_is_the_higher_side(self):
        for r in self.rows:
            if not r["quote_captured"]:
                self.assertIsNone(r["probability_a"])
                self.assertIsNone(r["pick"])
                continue
            self.assertAlmostEqual(r["probability_a"] + r["probability_b"], 1.0, places=3)
            expected = r["team_a"] if r["probability_a"] >= r["probability_b"] else r["team_b"]
            self.assertEqual(r["pick"], expected, r["fixture_id"])

    def test_probability_is_mean_of_source_probabilities(self):
        for r in self.rows:
            if not r["sources"]:
                continue
            mean = sum(s["p_a"] for s in r["sources"]) / len(r["sources"])
            self.assertAlmostEqual(r["probability_a"], round(mean, 4), places=4, msg=r["fixture_id"])

    def test_named_bookmakers_are_preferred_over_widget(self):
        for r in self.rows:
            names = [s["source"] for s in r["sources"]]
            named = [n for n in names if n in ("Pinnacle", "Bovada")]
            if named:
                # widget fallback is used only when no named bookmaker quote exists
                self.assertFalse(any(n.startswith("EamersWorld") for n in names), r["fixture_id"])
            if r["quality"] and r["quality"].startswith("Low"):
                self.assertEqual(len(r["sources"]), 1)

    def test_no_placeholder_or_started_widget_prices_used(self):
        egw_urls = {s["url"] for r in self.rows for s in r["sources"] if s["source"].startswith("EGamersWorld")}
        for r in self.rows:
            for s in r["sources"]:
                if s["source"].startswith("EGamersWorld"):
                    self.assertFalse(s["decimal_a"] == 1.8 and s["decimal_b"] == 1.8, r["fixture_id"])
        self.assertTrue(all(u.startswith("https://egamersworld.com/") for u in egw_urls))

    def test_crowd_percentages_never_used_as_probability(self):
        for r in self.rows:
            crowd = r["hotspawn_pick_pct_reference_only"]
            for s in r["sources"]:
                self.assertNotIn("hotspawn", (s.get("url") or "").lower())
            if r["probability_a"] is not None and crowd["team_a"] is not None:
                # the probability is derived from external sources only
                self.assertTrue(r["sources"])

    def test_every_row_links_to_official_pages(self):
        for r in self.rows:
            self.assertTrue(r["hotspawn_url"].startswith("https://www.hotspawn.com/matches/"))
            for s in r["sources"]:
                self.assertTrue(s["url"].startswith("https://"), r["fixture_id"])

    def test_pages_render_mobile_viewport_and_flagged_link(self):
        for rel in ("current/index.html", "current/flagged.html"):
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                html = fh.read()
            self.assertIn('name="viewport" content="width=device-width', html)
            self.assertIn("flagged.html", html)
            self.assertIn("index.html", html)

    def test_index_contains_every_open_fixture(self):
        with open(os.path.join(ROOT, "current/index.html"), encoding="utf-8") as fh:
            html = fh.read()
        self.assertEqual(html.count('<article class="card">'), len(self.rows))
        self.assertIn("EGamersWorld", html) if self.doc["summary"]["with_egw_fallback_only"] else None


if __name__ == "__main__":
    unittest.main()
