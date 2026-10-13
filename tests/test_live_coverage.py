#!/usr/bin/env python3
"""Tests for the T-COVER current-lobby board (session 3cd9787c).

Three groups:
  1. Arithmetic and parsing — exact expectations, no network.
  2. Join rules and the board builder on synthetic inputs (including a corruption case that must
     be rejected).
  3. If this session has already published a board (`data/live/board.json`), every published
     number is re-derived from the committed raw quotes and the invariants are re-checked, so the
     published artifact can never drift away from its evidence.

Run: python3 -m unittest tests.test_live_coverage -v
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "live"))

from build_live import (  # noqa: E402
    build_board, check_page_links, join_quote_to_fixture, verify_board, window_analysis,
)
from live_core import (  # noqa: E402
    american_to_decimal, canon_team, consensus, extract_lobby_listing, html_to_text,
    no_vig_two_way, parse_lobby_counters, parse_ms, pct, same_team, vrs_estimate,
    vrs_markdown_rows, week_window,
)

DATA = ROOT / "data" / "live"
NOW = datetime(2026, 10, 13, 22, 0, tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------------------------- 1. math
class TestOddsArithmetic(unittest.TestCase):
    def test_american_conversion(self):
        self.assertAlmostEqual(american_to_decimal(100), 2.0, places=9)
        self.assertAlmostEqual(american_to_decimal(-200), 1.5, places=9)
        self.assertAlmostEqual(american_to_decimal(280), 3.8, places=9)
        # the conversion is published rounded to 6 decimals, which is where it is stored
        self.assertAlmostEqual(american_to_decimal(-455), 1.2197802197802199, places=5)
        self.assertEqual(american_to_decimal(-455), round(1 + 100 / 455, 6))
        self.assertIsNone(american_to_decimal(0))
        self.assertIsNone(american_to_decimal("n/a"))

    def test_no_vig_is_normalised_and_reports_overround(self):
        nv = no_vig_two_way(1.909, 1.909)
        self.assertAlmostEqual(nv["prob_a"] + nv["prob_b"], 1.0, places=12)
        self.assertAlmostEqual(nv["prob_a"], 0.5, places=12)
        self.assertAlmostEqual(nv["overround"], 2 / 1.909 - 1, places=12)
        # a quoted pair that is not a market (one side <= 1.0) is refused, not guessed
        self.assertIsNone(no_vig_two_way(1.0, 2.0))
        self.assertIsNone(no_vig_two_way(None, 2.0))

    def test_no_vig_matches_hand_calculation(self):
        # Bovada Astralis vs Sashi 1.10 / 6.50 — published in the market board as 85.5% / 14.5%
        nv = no_vig_two_way(1.10, 6.5)
        self.assertAlmostEqual(nv["prob_a"], (1 / 1.10) / ((1 / 1.10) + (1 / 6.5)), places=12)
        self.assertAlmostEqual(nv["prob_a"], 0.8552631578947369, places=9)

    def test_consensus_is_the_mean_of_sources(self):
        c = consensus([{"source_key": "a", "prob_a": 0.60, "prob_b": 0.40},
                       {"source_key": "b", "prob_a": 0.50, "prob_b": 0.50}])
        self.assertAlmostEqual(c["prob_a"], 0.55, places=12)
        self.assertAlmostEqual(c["prob_b"], 0.45, places=12)
        self.assertEqual(c["n_sources"], 2)
        self.assertEqual(c["sources"], ["a", "b"])
        self.assertAlmostEqual(c["spread_a"], 0.10, places=12)
        self.assertIsNone(consensus([]))

    def test_consensus_single_source_has_no_spread(self):
        c = consensus([{"source_key": "a", "prob_a": 0.7, "prob_b": 0.3}])
        self.assertIsNone(c["spread_a"])
        self.assertAlmostEqual(c["prob_a"], 0.7, places=12)


class TestRatingModel(unittest.TestCase):
    def test_vrs_logistic_known_values(self):
        e = vrs_estimate(2046, 2046)
        self.assertAlmostEqual(e["prob_a"], 0.5, places=12)
        e = vrs_estimate(2246, 2046)
        self.assertAlmostEqual(e["prob_a"], 1 / (1 + 10 ** -0.5), places=12)
        self.assertAlmostEqual(e["prob_a"] + e["prob_b"], 1.0, places=12)
        self.assertIsNone(vrs_estimate(None, 2000))

    def test_markdown_rows_parse_valve_table(self):
        text = """
### Standings as of 2026_10_05<br />

| Standing | Points | Team Name            | Roster                        |  |
| :- | -: | :- | :- | :- |
| 1        |   2046 | Spirit               | donk, magixx, sh1ro           | [details](x) |
| 8        |   1674 | Astralis             | HooXi, jabbi, phzy, ryu       | [details](x) |
| not-a-row | 1 | Ignored | | |
"""
        rows = vrs_markdown_rows(text)
        self.assertEqual(rows["spirit"]["points"], 2046)
        self.assertEqual(rows["astralis"]["standing"], 8)
        self.assertNotIn("ignored", rows)

    def test_team_normalisation_and_aliases(self):
        self.assertEqual(canon_team("Grêmio"), "gremio")
        self.assertEqual(canon_team("9z Globant"), "9z")
        self.assertTrue(same_team("NiP", "Ninjas in Pyjamas"))
        self.assertTrue(same_team("Team Falcons", "Falcons"))
        # different teams must never collapse into each other
        self.assertFalse(same_team("B8 Academy", "B8"))
        self.assertFalse(same_team("MIBR Academy", "MIBR"))


class TestHotSpawnParsing(unittest.TestCase):
    def test_parse_ms_epoch_milliseconds(self):
        dt = parse_ms("1767605400000")
        self.assertEqual(iso(dt), "2026-01-05T09:30:00Z")
        self.assertIsNone(parse_ms(None))
        self.assertIsNone(parse_ms("not-a-number"))

    def test_lobby_counters_read_what_the_page_prints(self):
        html = ("<html><body><div>This week</div><div>68 matches this week</div>"
                "<div>Resets in 5d 03h 09m 46s</div><div>Tier All tiers (90) B (26) C (60) S (4)</div>"
                "<div>All tournaments (90)</div></body></html>")
        c = parse_lobby_counters(html)
        self.assertEqual(c["matches_this_week"], 68)
        self.assertEqual(c["all_tiers"], 90)
        self.assertEqual(c["tier_counts"], {"b": 26, "c": 60, "s": 4})
        self.assertEqual(html_to_text("<p>a</p><script>x</script><p>b</p>").split(), ["a", "b"])

    def test_lobby_listing_ids_are_read_from_the_embedded_state(self):
        import json as _json
        state = {"fixtures": [
            {"id": "1079621", "participants0_name": "Gothic", "participants1_name": "Lavked",
             "scheduled_start_time": "1767custom",
             "nested": {"id": "1079622", "participants0_name": "A", "participants1_name": "B",
                        "scheduled_start_time": "1"}}]}
        html = ('<html><script id="ng-state" type="application/json">'
                + _json.dumps(state).replace("<", "\\u003c") + '</script>'
                + '<a href="https://www.hotspawn.com/matches/1079621">card</a></html>')
        listing = extract_lobby_listing(html)
        self.assertTrue(listing["found"])
        self.assertEqual(listing["listed_ids"], ["1079621", "1079622"])
        self.assertEqual(listing["match_links_rendered"], 1)
        self.assertFalse(extract_lobby_listing("<html><body>no state</body></html>")["found"])

    def test_week_window_is_monday_to_monday_utc(self):
        start, end = week_window(NOW)
        self.assertEqual(start.weekday(), 0)
        self.assertEqual(iso(start), "2026-10-12T00:00:00Z")
        self.assertEqual(iso(end), "2026-10-19T00:00:00Z")
        self.assertLess(start, NOW)
        self.assertGreater(end, NOW)


# ------------------------------------------------------------------------------- 2. joins
def fixture(**over):
    base = {
        "fixture_id": "1079621", "game": "CS2", "competition": "CCT Europe 2026 Series #11",
        "tier": "b", "status": "scheduled",
        "start_time_utc": iso(NOW + timedelta(hours=10)),
        "lock_time_utc": iso(NOW + timedelta(hours=9, minutes=55)),
        "team_a": "Gothic", "team_b": "Lavked",
        "source": {"api": "https://example.invalid/api", "page": "https://play.hotspawn.com/lobby",
                   "hotspawn_match_url": "https://www.hotspawn.com/matches/1079621"},
        "hotspawn_pick_pct_reference_only": {"team_a": 20, "team_b": 80},
    }
    base.update(over)
    return base


def quote(**over):
    base = {
        "source_key": "pinnacle", "source_name": "Pinnacle", "source_kind": "licensed bookmaker",
        "game": "cs2", "source_public_url": "https://www.pinnacle.com/en/esports/",
        "source_api_url": "https://guest.api.arcadia.pinnacle.com/0.1/matchups/1/markets/related/straight",
        "source_event_id": "1", "source_market_id": "2",
        "source_league": "CCT Europe", "market_type": "match winner (moneyline, full match)",
        "market_is_live": False, "market_status": "open",
        "retrieved_at_utc": iso(NOW - timedelta(minutes=30)),
        "start_time_utc": iso(NOW + timedelta(hours=10)),
        "team_a_name": "Gothic", "team_b_name": "Lavked",
        "raw_price_format": "decimal", "raw_price_a": 2.0, "raw_price_b": 1.8,
        "decimal_odds_a": 2.0, "decimal_odds_b": 1.8, "decimal_odds_derived": False,
        "confidence": "market",
    }
    base.update(over)
    return base


class TestJoinRules(unittest.TestCase):
    def test_join_requires_both_names(self):
        f = fixture()
        self.assertEqual(join_quote_to_fixture(f, quote())["orientation"], "ab")
        self.assertEqual(join_quote_to_fixture(
            f, quote(team_a_name="Lavked", team_b_name="Gothic"))["orientation"], "ba")
        self.assertIsNone(join_quote_to_fixture(f, quote(team_b_name="Someone Else")))

    def test_join_rejects_a_start_time_outside_tolerance(self):
        f = fixture()
        far = quote(start_time_utc=iso(NOW + timedelta(hours=40)))
        self.assertIsNone(join_quote_to_fixture(f, far))

    def test_join_without_source_start_time_is_accepted_but_noted(self):
        f = fixture()
        joined = join_quote_to_fixture(f, quote(start_time_utc=None))
        self.assertIsNotNone(joined)
        self.assertTrue(joined["notes"])

    def test_alias_join(self):
        f = fixture(team_a="BetBoom")
        joined = join_quote_to_fixture(f, quote(team_a_name="BB Team", team_b_name="Lavked"))
        self.assertEqual(joined["orientation"], "ab")


def docs(fixtures, quotes, ratings=None):
    return (
        {"generated_at_utc": iso(NOW), "lobby_counters": {"all_tiers": len(fixtures)},
         "fixtures": fixtures},
        {"generated_at_utc": iso(NOW), "quotes": quotes},
        {"generated_at_utc": iso(NOW), "source": "https://github.com/ValveSoftware/counter-strike_regional_standings",
         "ratings": ratings or {}},
        {"started_at_utc": iso(NOW)},
    )


RATINGS = {
    "gothic": {"team": "Gothic", "points": 1500, "standing": 100, "region": "europe",
               "snapshot": "2026_10_05", "source_url": "https://api.github.com/x1",
               "raw_url": "https://raw.githubusercontent.com/x1"},
    "lavked": {"team": "Lavked", "points": 1450, "standing": 130, "region": "europe",
               "snapshot": "2026_10_05", "source_url": "https://api.github.com/x2",
               "raw_url": "https://raw.githubusercontent.com/x2"},
}


class TestBoardBuilder(unittest.TestCase):
    def test_market_row_publishes_market_probability_and_pick(self):
        f_doc, q_doc, r_doc, log = docs([fixture()], [quote()], RATINGS)
        board = build_board(f_doc, q_doc, r_doc, NOW)
        row = board["rows"][0]
        self.assertEqual(row["published"]["basis"], "market")
        nv = no_vig_two_way(2.0, 1.8)
        self.assertAlmostEqual(row["published"]["prob_a"], nv["prob_a"], places=12)
        self.assertEqual(row["published"]["pick_team"], "Lavked")
        self.assertAlmostEqual(row["published"]["pick_probability"], nv["prob_b"], places=12)
        self.assertTrue(row["published"]["source_links"][0].startswith("https://"))

    def test_estimate_row_is_labelled_and_sourced(self):
        f_doc, q_doc, r_doc, log = docs([fixture()], [], RATINGS)
        board = build_board(f_doc, q_doc, r_doc, NOW)
        row = board["rows"][0]
        self.assertEqual(row["published"]["basis"], "estimate")
        self.assertIn("not a market price", row["published"]["label"])
        self.assertAlmostEqual(row["published"]["prob_a"], vrs_estimate(1500, 1450)["prob_a"],
                               places=12)
        self.assertTrue(all(str(l).startswith("http") for l in row["published"]["source_links"]))

    def test_blank_row_stays_blank_and_flagged(self):
        f_doc, q_doc, r_doc, log = docs([fixture(team_a="Unknown One", team_b="Unknown Two")], [])
        board = build_board(f_doc, q_doc, r_doc, NOW)
        row = board["rows"][0]
        self.assertEqual(row["published"]["basis"], "none")
        self.assertIsNone(row["published"]["prob_a"])
        self.assertIn("no_probability_available", row["flags"])
        self.assertIn("no_valve_vrs_rating:Unknown One|Unknown Two", row["flags"])

    def test_lol_never_gets_an_estimate(self):
        f = fixture(game="LoL", team_a="Cloud9", team_b="Karmine Corp")
        f_doc, q_doc, r_doc, log = docs([f], [], RATINGS)
        board = build_board(f_doc, q_doc, r_doc, NOW)
        self.assertEqual(board["rows"][0]["published"]["basis"], "none")
        self.assertIn("no_official_rating_source_for_lol", board["rows"][0]["flags"])

    def test_stale_and_in_play_quotes_are_excluded(self):
        stale = quote(retrieved_at_utc=iso(NOW - timedelta(hours=30)))
        live = quote(source_key="bovada", source_name="Bovada", market_is_live=True,
                     retrieved_at_utc=iso(NOW - timedelta(minutes=5)))
        f_doc, q_doc, r_doc, log = docs([fixture()], [stale, live], RATINGS)
        board = build_board(f_doc, q_doc, r_doc, NOW)
        row = board["rows"][0]
        self.assertIsNone(row["market"])
        self.assertIn("stale_quote_excluded:pinnacle", row["flags"])
        self.assertIn("live_market_excluded:bovada", row["flags"])
        self.assertEqual(row["published"]["basis"], "estimate")

    def test_orientation_is_respected_when_prices_are_reversed(self):
        q = quote(team_a_name="Lavked", team_b_name="Gothic", decimal_odds_a=1.8, decimal_odds_b=2.0,
                  raw_price_a=1.8, raw_price_b=2.0)
        f_doc, q_doc, r_doc, log = docs([fixture()], [q], RATINGS)
        board = build_board(f_doc, q_doc, r_doc, NOW)
        row = board["rows"][0]
        self.assertAlmostEqual(row["published"]["prob_a"], no_vig_two_way(2.0, 1.8)["prob_a"],
                               places=12)

    def test_ambiguous_pairing_without_source_time_is_refused(self):
        f1 = fixture(fixture_id="1")
        f2 = fixture(fixture_id="2", start_time_utc=iso(NOW + timedelta(hours=30)))
        q = quote(start_time_utc=None)
        f_doc, q_doc, r_doc, log = docs([f1, f2], [q], RATINGS)
        board = build_board(f_doc, q_doc, r_doc, NOW)
        self.assertEqual(len(board["rejected_joins"]), 2)
        self.assertIsNone(board["rows"][0]["market"])

    def test_reference_exchange_quotes_never_enter_the_consensus(self):
        ref = quote(source_key="kalshi", source_name="Kalshi (exchange)",
                    source_kind="prediction-market exchange (reference, never averaged)",
                    confidence="reference", raw_price_format="probability_mid", raw_price_a=0.9,
                    raw_price_b=None, decimal_odds_a=None, decimal_odds_b=None)
        trade = quote(source_key="bovada", source_name="Bovada", decimal_odds_a=1.5,
                      decimal_odds_b=2.5, raw_price_a=1.5, raw_price_b=2.5)
        f_doc, q_doc, r_doc, log = docs([fixture()], [ref, trade], RATINGS)
        board = build_board(f_doc, q_doc, r_doc, NOW)
        row = board["rows"][0]
        self.assertEqual(row["market"]["sources"], ["bovada"])
        self.assertEqual(len(row["reference"]), 1)

    def test_window_analysis_reports_unreproduced_counters(self):
        f = fixture()
        analysis = window_analysis([f], {"all_tiers": 999, "matches_this_week": 1}, NOW)
        self.assertIn("all_tiers", analysis["unexplained_counters"])
        self.assertTrue(analysis["counter_reproductions"])


class TestVerificationRejectsCorruption(unittest.TestCase):
    def _board(self):
        f_doc, q_doc, r_doc, log = docs([fixture(), fixture(fixture_id="2", game="LoL",
                                                           team_a="Cloud9", team_b="Karmine Corp")],
                                        [quote()], RATINGS)
        board = build_board(f_doc, q_doc, r_doc, NOW)
        return board, f_doc, q_doc, r_doc

    def test_clean_board_passes_every_check(self):
        board, f_doc, q_doc, r_doc = self._board()
        result = verify_board(board, q_doc, r_doc, f_doc)
        self.assertEqual(result["failed"], 0, [c for c in result["checks"] if not c["passed"]])

    def test_tampered_probability_is_rejected(self):
        board, f_doc, q_doc, r_doc = self._board()
        board["rows"][0]["published"]["prob_a"] = 0.99
        board["rows"][0]["published"]["prob_b"] = 0.01
        result = verify_board(board, q_doc, r_doc, f_doc)
        self.assertGreater(result["failed"], 0)
        failed = " ".join(c["check"] for c in result["checks"] if not c["passed"])
        self.assertIn("C3", failed)

    def test_tampered_pick_is_rejected(self):
        board, f_doc, q_doc, r_doc = self._board()
        board["rows"][0]["published"]["pick_team"] = "Gothic"
        result = verify_board(board, q_doc, r_doc, f_doc)
        self.assertGreater(result["failed"], 0)

    def test_missing_rating_for_an_estimate_is_rejected(self):
        board, f_doc, q_doc, r_doc = self._board()
        board["rows"][0].update({"published": {"basis": "estimate", "prob_a": 0.7, "prob_b": 0.3,
                                               "pick_side": "a", "pick_team": "Gothic",
                                               "pick_probability": 0.7, "edge": 0.4,
                                               "source_links": []},
                                 "market": None,
                                 "estimate": {"prob_a": 0.7, "prob_b": 0.3, "team_a_points": 1,
                                              "team_b_points": 2, "team_a_source_url": "",
                                              "team_b_source_url": ""}})
        result = verify_board(board, q_doc, r_doc, f_doc)
        self.assertGreater(result["failed"], 0)


# ------------------------------------------------------- 3. the published artifact itself
@unittest.skipUnless((DATA / "board.json").is_file(), "no published board yet in this checkout")
class TestPublishedBoard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = json.loads((DATA / "board.json").read_text())
        cls.quotes = json.loads((DATA / "quotes.json").read_text())
        cls.ratings = json.loads((DATA / "ratings.json").read_text())
        cls.fixtures = json.loads((DATA / "fixtures.json").read_text())

    def test_published_board_still_verifies(self):
        result = verify_board(self.board, self.quotes, self.ratings, self.fixtures)
        self.assertEqual(result["failed"], 0,
                         [c for c in result["checks"] if not c["passed"]])

    def test_every_row_has_a_source_link_or_is_flagged(self):
        for row in self.board["rows"]:
            pub = row["published"]
            if pub["basis"] == "none":
                self.assertIn("no_probability_available", row["flags"], row["fixture_id"])
                self.assertIsNone(pub["prob_a"])
            else:
                self.assertTrue(pub["source_links"], row["fixture_id"])
                self.assertTrue(pub["source_links"][0].startswith("http"), row["fixture_id"])
                self.assertIsNotNone(pub["pick_probability"])

    def test_no_hotspawn_url_is_used_as_a_probability_source(self):
        for row in self.board["rows"]:
            for link in row["published"]["source_links"]:
                self.assertNotIn("hotspawn", link.lower())

    def test_pages_exist_and_have_no_broken_local_links(self):
        site = ROOT / "live"
        if not site.is_dir():
            self.skipTest("pages not rendered in this checkout")
        self.assertTrue((site / "index.html").is_file())
        result = check_page_links(site)
        self.assertTrue(result["ok"], result["problems"])

    def test_pages_are_mobile_ready(self):
        site = ROOT / "live"
        if not site.is_dir():
            self.skipTest("pages not rendered in this checkout")
        css = (site / "assets" / "live.css").read_text()
        self.assertIn("@media (max-width:520px)", css.replace("@media (max-width: 520px)",
                                                              "@media (max-width:520px)"))
        for name in ("index.html", "cs2.html", "lol.html", "flagged.html", "methodology.html",
                     "sources.html"):
            text = (site / name).read_text()
            self.assertIn('name="viewport"', text, name)
            self.assertIn("width=device-width", text, name)
            # every page must be reachable from every other page (no dead ends on mobile)
            for target in ("index.html", "cs2.html", "lol.html", "flagged.html", "methodology.html",
                           "sources.html"):
                self.assertIn(f'href="{target}"', text, f"{name} -> {target}")

    def test_no_captured_page_is_stored_as_html(self):
        samples = DATA / "samples"
        if not samples.is_dir():
            self.skipTest("no samples in this checkout")
        stray = sorted(p.name for p in samples.glob("*.html"))
        self.assertEqual(stray, [], f"captured pages must be stored as .txt, found: {stray}")

    def test_probability_coverage_is_documented_not_assumed(self):
        summary = self.board["summary"]
        self.assertEqual(summary["with_market_probability"] + summary["with_originated_estimate"]
                         + summary["blank"], summary["rows"])


class TestFormatting(unittest.TestCase):
    def test_percent_formatting(self):
        self.assertEqual(pct(0.85526315789), "85.5%")
        self.assertEqual(pct(None), "")


if __name__ == "__main__":
    unittest.main()
