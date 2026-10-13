"""Session 42580809 — invariants for the coverage board, its evidence and its published section.

These tests read committed files only (no network). They fail if a row loses its source link, if a
probability stops being reproducible from the per-source quotes, if a stale listing grows a
probability, if the CSV and JSON disagree, or if the published section has a broken internal link.
"""

import csv
import json
import os
import unittest
from html.parser import HTMLParser
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
EV = os.path.join(ROOT, "proof", "42580809", "evidence")
SITE = os.path.join(ROOT, "site", "42580809")
NAMED = {"pinnacle", "bovada", "kalshi"}


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class BoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load(os.path.join(DATA, "board_42580809.json"))
        cls.rows = cls.board["rows"]
        cls.orig = {r["fixture_id"]: r for r in load(os.path.join(DATA, "originated_42580809.json"))["rows"]}
        cls.coverage = load(os.path.join(EV, "coverage.json"))
        cls.matching = load(os.path.join(EV, "matching.json"))

    def test_fixture_window_is_complete(self):
        fixtures = [f for f in load(os.path.join(EV, "fixtures.json"))["fixtures"] if f["sport"] == "cs2"]
        self.assertEqual(len(fixtures), len(self.rows))
        self.assertEqual({f["fixture_id"] for f in fixtures}, {r["fixture_id"] for r in self.rows})

    def test_every_row_is_listable_and_source_linked(self):
        for r in self.rows:
            self.assertTrue(r["hotspawn_url"].startswith("https://www.hotspawn.com/matches/"))
            self.assertTrue(r["team_a"] and r["team_b"])
            self.assertRegex(r["scheduled_start_time_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
            for q in r["sources"]:
                self.assertTrue(q["source_url"] or q["api_url"], r["fixture_id"])
                self.assertRegex(str(q["retrieved_at_utc"]), r"^\d{4}-\d{2}-\d{2}T")

    def test_probabilities_are_consistent_and_bounded(self):
        for r in self.rows:
            if r["p_a"] is None:
                self.assertIsNone(r["p_b"])
                continue
            self.assertGreater(r["p_a"], 0.0)
            self.assertLess(r["p_a"], 1.0)
            self.assertAlmostEqual(r["p_a"] + r["p_b"], 1.0, places=3)
            expected = r["team_a"] if r["p_a"] >= r["p_b"] else r["team_b"]
            self.assertEqual(r["pick_team"], expected)
            self.assertAlmostEqual(r["pick_probability"], max(r["p_a"], r["p_b"]), places=3)

    def test_market_rows_average_their_named_sources(self):
        for r in self.rows:
            named = [q for q in r["sources"] if q["source_key"] in NAMED]
            if r["basis"] == "market-derived":
                self.assertTrue(named, r["fixture_id"])
                mean = sum(q["no_vig_probability_a"] for q in named) / len(named)
                self.assertAlmostEqual(r["p_a"], mean, places=3, msg=r["fixture_id"])
            if r["basis"] == "aggregator-fallback":
                self.assertFalse(named, r["fixture_id"])
                self.assertTrue(r["sources"], r["fixture_id"])

    def test_stale_listings_never_carry_a_probability(self):
        stale = [r for r in self.rows if r["stale"]]
        self.assertTrue(stale)
        for r in stale:
            self.assertIsNone(r["p_a"])
            self.assertIsNone(r["pick_team"])
            self.assertEqual(r["basis"], "stale-listing")

    def test_blank_rows_are_flagged_with_a_reason(self):
        for r in self.rows:
            if r["p_a"] is not None:
                continue
            if r["stale"]:
                continue
            o = self.orig.get(r["fixture_id"], {})
            if o.get("originated_p_a") is not None:
                continue          # published as an originated model line, not blank
            self.assertTrue(o.get("unoriginated_because") or r["rejected_quotes_flagged"],
                            f'{r["fixture_id"]} is blank without a recorded reason')

    def test_originated_rows_label_themselves(self):
        for r in self.rows:
            o = self.orig.get(r["fixture_id"])
            if o and o["originated_p_a"] is not None:
                self.assertTrue(o["method"])
                self.assertIn(o["method"], ("market-graph (Bradley-Terry on collected prices)",
                                            "Valve Regional Standings (official ranking, calibrated)"))
                self.assertGreater(o["originated_p_a"], 0.0)
                self.assertLess(o["originated_p_a"], 1.0)

    def test_hotspawn_is_discovery_only(self):
        self.assertIn("discovery only", self.board["hotspawn_used_for"])
        for r in self.rows:
            self.assertEqual(len(r["hotspawn_pick_pct_reference_only"]), 2)

    def test_coverage_counters_match_rows(self):
        c = self.coverage
        self.assertEqual(c["fixtures_total"], len(self.rows))
        self.assertEqual(c["stale_fixtures"], sum(1 for r in self.rows if r["stale"]))
        self.assertEqual(c["fixtures_with_named_line"], sum(1 for r in self.rows if r["basis"] == "market-derived"))
        self.assertEqual(c["quotes_accepted"], len(self.matching["accepted"]))

    def test_every_quote_decision_is_recorded(self):
        for rec in self.matching["accepted"]:
            self.assertTrue(rec["source_key"])
            self.assertIn(rec["orientation_vs_fixture"], ("direct", "reversed"))
        for rec in self.matching["rejected"]:
            self.assertTrue(rec["reason"])

    def test_csv_matches_json(self):
        with open(os.path.join(DATA, "board_42580809.csv"), encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), len(self.rows))
        self.assertEqual([r["fixture_id"] for r in rows], [r["fixture_id"] for r in self.rows])


class SiteTests(unittest.TestCase):
    def test_section_files_exist(self):
        for name in ("index.html", "tables.html", "methodology.html", "flagged.html",
                     "assets/style.css", "assets/app.js",
                     "data/board.json", "data/board.csv", "data/originated.json", "data/coverage.json"):
            self.assertTrue(os.path.isfile(os.path.join(SITE, name)), name)

    def test_internal_links_resolve(self):
        class Links(HTMLParser):
            def __init__(self):
                super().__init__()
                self.urls = []

            def handle_starttag(self, tag, attrs):
                for key, value in attrs:
                    if key in ("href", "src") and value:
                        self.urls.append(value)

        broken = []
        for dirpath, _dirs, files in os.walk(SITE):
            for name in files:
                if not name.endswith(".html"):
                    continue
                page = os.path.join(dirpath, name)
                parser = Links()
                parser.feed(open(page, encoding="utf-8").read())
                for url in parser.urls:
                    parts = urlsplit(url)
                    if parts.scheme or parts.netloc or not parts.path:
                        continue
                    target = os.path.normpath(os.path.join(dirpath, parts.path))
                    if not os.path.exists(target):
                        broken.append(f"{os.path.relpath(page, SITE)} -> {url}")
        self.assertEqual(broken, [])

    def test_every_published_probability_row_keeps_a_source_link(self):
        board = load(os.path.join(SITE, "data", "board.json"))
        page = open(os.path.join(SITE, "index.html"), encoding="utf-8").read()
        for r in board["rows"]:
            if r["sources"]:
                for q in r["sources"]:
                    url = q["source_url"] or q["api_url"]
                    self.assertIn(url, page, f'{r["fixture_id"]} source link missing from the board page')


if __name__ == "__main__":
    unittest.main()
