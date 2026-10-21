"""Session fe803b80 — invariants for the full-coverage picks board, its evidence and its section.

These tests read committed files only (no network). They fail if a published probability stops being
reproducible from its stored quotes, if a row loses its source link, if the board silently starts
reading HotSpawn's crowd pick percentage, if an "originated" row loses its rating source, or if the
published section has a broken internal link.
"""
from __future__ import annotations

import importlib.util
import json
import re
import os
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_core_spec = importlib.util.spec_from_file_location(
    "core_fe803b80_test", os.path.join(ROOT, "scripts", "fe803b80", "core.py")
)
core = importlib.util.module_from_spec(_core_spec)
_core_spec.loader.exec_module(core)

DATA = os.path.join(ROOT, "data", "fe803b80")
SITE = os.path.join(ROOT, "board")
BOARD_PATH = os.path.join(DATA, "board.json")
BASES = {"market", "market+model", "model"}


def load_board():
    with open(BOARD_PATH, encoding="utf-8") as fh:
        return json.load(fh)


class CoreTests(unittest.TestCase):
    def test_norm_and_canon_strip_generic_org_words_without_over_matching(self):
        self.assertEqual(core.norm("FURIA Esports"), "furia")
        self.assertEqual(core.norm("Team Falcons"), "falcons")
        self.assertEqual(core.norm("9z Team"), "9z")
        self.assertNotEqual(core.norm("B8"), core.norm("B8 Academy"))
        self.assertNotEqual(core.norm("ENCE"), core.norm("ENCE Academy"))

    def test_alias_is_documented_with_evidence(self):
        key, evidence, note = core.canon("WROTBERRY")
        self.assertEqual(key, "wbt")
        self.assertTrue(evidence and all(u.startswith("http") for u in evidence))
        self.assertTrue(note)

    def test_no_vig_is_proportional_and_refuses_junk(self):
        nv = core.no_vig(2.0, 2.0)
        self.assertAlmostEqual(nv["prob_a"], 0.5)
        self.assertAlmostEqual(nv["prob_a"] + nv["prob_b"], 1.0)
        self.assertIsNone(core.no_vig(1.0, 3.0))      # invalid decimal price
        self.assertIsNone(core.no_vig(1.01, 1.01))    # impossible 98% overround

    def test_consensus_weights_and_spread(self):
        entries = [{"source_key": "pinnacle", "prob_a": 0.6}, {"source_key": "kalshi", "prob_a": 0.5}]
        con = core.consensus(entries)
        self.assertAlmostEqual(con["prob_a"], (2.0 * 0.6 + 1.0 * 0.5) / 3.0)
        self.assertEqual(con["n_sources"], 2)
        self.assertAlmostEqual(con["spread_a"], 0.1)

    def test_vrs_probability_matches_valve_curve_shape(self):
        self.assertAlmostEqual(core.vrs_prob(1000, 1000), 0.5)
        # Valve's own published relationship: 400 points is worth ~90% win probability
        self.assertGreater(core.vrs_prob(1400, 1000), 0.88)
        self.assertLess(core.vrs_prob(1400, 1000), 0.92)

    def test_match_quote_requires_both_names_and_time(self):
        fixture = {"team_a": "Gothic", "team_b": "Lavked", "start_utc": "2026-10-14T08:00:00Z"}
        good = {"team_a": "Gothic", "team_b": "Lavked", "start_utc": "2026-10-14T08:05:00Z"}
        swapped = {"team_a": "Lavked", "team_b": "Gothic", "start_utc": "2026-10-14T08:00:00Z"}
        same_day_far = {"team_a": "Gothic", "team_b": "Lavked", "start_utc": "2026-10-16T08:00:00Z"}
        wrong_team = {"team_a": "Gothic", "team_b": "Lavked Academy",
                      "start_utc": "2026-10-14T08:00:00Z"}
        self.assertFalse(core.match_quote(fixture, good)["swapped"])
        self.assertTrue(core.match_quote(fixture, swapped)["swapped"])
        self.assertIsNone(core.match_quote(fixture, same_day_far))
        self.assertIsNone(core.match_quote(fixture, wrong_team))

    def test_lobby_state_parses_public_transfer_state(self):
        page = ('<html><script id="ng-state" type="application/json">'
                '{"k":{"u":"https://play.hotspawn.com/lobby/api/v1/fixtures","b":[{"id":"1"}]},'
                '"p":{"u":"/api/v1/pickems/permalinks","b":{"permalinks":{"1":'
                '"https://www.hotspawn.com/matches/a-vs-b-cup-1"}}}}'
                '</script></html>')
        state = core.lobby_state(page)
        self.assertEqual(state["fixtures"], [{"id": "1"}])
        self.assertEqual(state["permalinks"]["1"], "https://www.hotspawn.com/matches/a-vs-b-cup-1")

    def test_crowd_pick_fields_cannot_reach_the_fixture_parser(self):
        raw = {"id": "9", "sport_alias": "cs2", "scheduled_start_time": "1792173600000",
               "lock_time": "1792170000000", "participants0_name": "A", "participants1_name": "B",
               "participants0_picked_percent": 90, "pick_score": 1}
        fx = core.fixture_from_hotspawn(raw)
        self.assertNotIn("participants0_picked_percent", json.dumps(fx))
        self.assertNotIn("pick_score", json.dumps(fx))


@unittest.skipUnless(os.path.exists(BOARD_PATH), "board.json not generated in this checkout")
class BoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load_board()
        cls.open_rows = cls.board["open"]
        cls.quotes = {q["event_id"]: q for q in cls.board["quotes"]}

    def test_every_open_row_has_a_pick_or_an_explicit_flag(self):
        for row in self.open_rows:
            line = row.get("line")
            if line:
                self.assertIn(line["basis"], BASES, row["fixture_id"])
                self.assertAlmostEqual(line["prob_a"] + line["prob_b"], 1.0, places=6)
                self.assertIn(line["pick"], (row["team_a"], row["team_b"]))
                self.assertAlmostEqual(
                    line["pick_probability"],
                    line["prob_a"] if line["pick"] == row["team_a"] else line["prob_b"],
                    places=6)
                self.assertIn(line["confidence"], ("Strong", "Solid", "Lean", "Toss-up"))
            else:
                self.assertIn("no_source_input_available_row_left_blank", row["flags"])

    def test_every_open_row_carries_a_source_link(self):
        for row in self.open_rows:
            self.assertTrue(row["sources"], row["fixture_id"])
            for s in row["sources"]:
                self.assertTrue(str(s.get("url") or "").startswith("http"),
                                (row["fixture_id"], s))
                self.assertTrue(s.get("read_utc"), (row["fixture_id"], s))
            # a published probability must be backed by a price or rating source;
            # the HotSpawn listing alone is discovery evidence, never a probability.
            if row.get("line"):
                kinds = {s.get("kind") for s in row["sources"]}
                self.assertTrue(kinds & {"price", "rating"},
                                (row["fixture_id"], row["sources"]))

    def test_hotspawn_is_labelled_discovery_only(self):
        for row in self.open_rows:
            discovery = [s for s in row["sources"] if s.get("kind") == "discovery"]
            self.assertEqual(len(discovery), 1, row["fixture_id"])
            self.assertIn("hotspawn.com", discovery[0]["url"])
            self.assertIn("not used as a probability", discovery[0]["note"])
            self.assertEqual(discovery[0]["label"],
                             "HotSpawn Pick'ems lobby (fixture discovery only)")

    def test_market_probability_is_reproducible_from_the_stored_quotes(self):
        for row in self.open_rows:
            market = row.get("market")
            if not market:
                continue
            usable = [q for q in row["quotes"] if q.get("prob_a") is not None]
            self.assertEqual(len(usable), market["n_sources"])
            weights = sum(core.SOURCE_WEIGHTS.get(q["source_key"], 1.0) for q in usable)
            expected = sum(core.SOURCE_WEIGHTS.get(q["source_key"], 1.0) * q["prob_a"]
                           for q in usable) / weights
            self.assertAlmostEqual(market["prob_a"], expected, places=6)

    def test_joined_quotes_reproduce_their_own_no_vig(self):
        for row in self.open_rows:
            for q in row["quotes"]:
                nv = core.no_vig(q["decimal_a"], q["decimal_b"])
                self.assertIsNotNone(nv, (row["fixture_id"], q["public_url"]))
                # 2e-4 tolerance: a source feed may publish an already-rounded probability,
                # the board stores the derived value from the published decimal odds.
                self.assertAlmostEqual(q["prob_a"], nv["prob_a"], delta=2e-4)

    def test_originated_rows_name_their_rating_source(self):
        for row in self.open_rows:
            if (row.get("line") or {}).get("basis") != "model":
                continue
            basis = row["model"].get("basis")
            self.assertIn(basis, ("valve_vrs", "originated_elo", "originated_rank"),
                          row["fixture_id"])
            urls = " ".join(s.get("url") or "" for s in row["sources"])
            if basis == "valve_vrs":
                self.assertTrue(row["model"].get("prob_a") is not None)
                self.assertIn("counter-strike_regional_standings", urls, row["fixture_id"])
            else:
                self.assertIn("bo3.gg", urls, row["fixture_id"])
                self.assertTrue(row["model"].get("elo"), row["fixture_id"])
            if basis == "originated_rank":
                self.assertIn("originated_rank_line_bo3gg_ranking", row["flags"],
                              row["fixture_id"])

    def test_hotspawn_crowd_percentages_are_absent_everywhere(self):
        """The only permitted mention of crowd-picks is the note that they are never used."""
        blob = json.dumps(self.board)
        for needle in ("picked_percent", "picked%", "hotspawn_pick_pct", "crowd_pick",
                       "participants0_picked"):
            self.assertNotIn(needle, blob)
        for match in re.finditer(r"[^\"]*crowd[^\"]*", blob):
            self.assertIn("never", match.group(0))

    def test_coverage_is_published_honestly(self):
        """The board states its own coverage: a blank row is only allowed if it is counted as one."""
        s = self.board["summary"]
        self.assertIn("open_blank", s)
        self.assertEqual(s["open_blank"], s["open"] - s["open_with_pick"], self.board["summary"])
        for row in self.open_rows:
            if not row.get("line"):
                self.assertIn("no_source_input_available_row_left_blank", row["flags"])

    def test_summary_counts_match_the_rows(self):
        s = self.board["summary"]
        self.assertEqual(s["open"], len(self.open_rows))
        self.assertEqual(s["open_with_pick"], sum(1 for r in self.open_rows if r.get("line")))
        self.assertEqual(s["open_blank"], sum(1 for r in self.open_rows if not r.get("line")))
        self.assertEqual(s["open_with_market"], sum(1 for r in self.open_rows if r.get("market")))

    def test_alias_rows_publish_their_evidence(self):
        for row in self.open_rows:
            if "alias_applied_see_evidence" not in row["flags"]:
                continue
            self.assertTrue(row["alias_note"])
            self.assertTrue(row["alias_evidence"])
            for url in row["alias_evidence"]:
                self.assertTrue(url.startswith("http"), url)


@unittest.skipUnless(os.path.exists(os.path.join(SITE, "picks.html")),
                     "board section not generated in this checkout")
class SiteTests(unittest.TestCase):
    PAGES = ("index.html", "picks.html", "lines.html", "tournaments.html", "results.html",
             "flagged.html", "method.html")
    REQUIRED_LINKS = {"index.html", "picks.html", "lines.html", "tournaments.html",
                      "results.html", "flagged.html", "method.html", "assets/board.css"}

    def test_all_pages_exist_mobile_first_and_self_linked(self):
        for name in self.PAGES:
            text = Path(SITE, name).read_text(encoding="utf-8")
            self.assertIn('name="viewport"', text, name)
            self.assertIn("width=device-width", text, name)
            for href in ("picks.html", "flagged.html", "method.html"):
                self.assertIn(f'href="{href}"', text, (name, href))

    def test_every_internal_link_resolves(self):
        class Links(HTMLParser):
            def __init__(self):
                super().__init__()
                self.urls = []

            def handle_starttag(self, tag, attrs):
                for key, value in attrs:
                    if key in ("href", "src") and value:
                        self.urls.append(value)

        for name in self.PAGES:
            parser = Links()
            parser.feed(Path(SITE, name).read_text(encoding="utf-8"))
            for url in parser.urls:
                parsed = urlsplit(url)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                target = os.path.join(SITE, unquote(parsed.path))
                self.assertTrue(os.path.exists(target), (name, url))

    def test_every_published_fixture_card_carries_a_source_link(self):
        text = Path(SITE, "picks.html").read_text(encoding="utf-8")
        cards = text.count('<article class="fixture">')
        self.assertGreater(cards, 0)
        self.assertGreaterEqual(text.count('rel="noopener"'), cards)

    def test_summary_page_links_to_the_pick_list(self):
        text = Path(SITE, "index.html").read_text(encoding="utf-8")
        self.assertIn('href="picks.html"', text)
        self.assertIn("Where the picks are", text)


if __name__ == "__main__":
    unittest.main()
