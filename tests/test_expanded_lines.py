#!/usr/bin/env python3
"""Tests for the T-EXPAND collection pipeline (session a0586093).

Two kinds of checks:
  1. Arithmetic and join rules — no network, exact expectations.
  2. Parser checks against the raw payloads committed under data/expanded/samples/, so the
     parser is verified against what the sources actually returned, not against a mock.

Run: python3 -m unittest tests.test_expanded_lines -v
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "expanded"))

from collect_lines import guess_game, hotspawn_link, parse_linefeed_event  # noqa: E402
from verify_repo_claims import window_rows  # noqa: E402
from lines_core import (  # noqa: E402
    consensus, implied, join_quote, norm, parse_iso, same_team, to_utc_iso,
)

SAMPLES = ROOT / "data" / "expanded" / "samples"


class TestNormalisation(unittest.TestCase):
    def test_norm_strips_accents_and_punctuation(self):
        self.assertEqual(norm("Grêmio"), "gremio")
        self.assertEqual(norm("LOS NINOS"), "losninos")
        self.assertEqual(norm("BC.Game"), "bcgame")

    def test_alias_table_matches_known_source_spellings(self):
        self.assertTrue(same_team("Ninjas in Pyjamas", "NiP"))
        self.assertTrue(same_team("Aurora", "Team AURORA"))
        self.assertTrue(same_team("9z", "9Z Globant"))
        self.assertTrue(same_team("BC.Game", "BC.Game Esports"))
        self.assertTrue(same_team("WROTBERRY", "WBT"))

    def test_academy_and_gender_variants_are_not_collapsed(self):
        self.assertFalse(same_team("B8", "B8 Academy"))
        self.assertFalse(same_team("MIBR", "MIBR fe"))
        self.assertFalse(same_team("Inner Circle", "Inner Circle Academy"))


class TestParsing(unittest.TestCase):
    def test_parse_iso_always_returns_utc_aware(self):
        for value in ("2026-10-13T19:00:00Z", "2026-10-13T19:00:00", "2026-10-13T19:00:00.000Z"):
            dt = parse_iso(value)
            self.assertIsNotNone(dt, value)
            self.assertIsNotNone(dt.tzinfo, value)
            self.assertEqual(dt.utcoffset().total_seconds(), 0)
        self.assertEqual(parse_iso("1791939600"),
                         datetime.fromtimestamp(1791939600, tz=timezone.utc))
        self.assertEqual(parse_iso(1791939600), parse_iso("1791939600"))
        self.assertEqual(to_utc_iso(parse_iso("2026-10-13T19:00:00")), "2026-10-13T19:00:00Z")

    def test_guess_game_reads_the_league_label(self):
        self.assertEqual(guess_game("Esports", "CS 2. Elisa Esports BreakOut"), "cs2")
        self.assertEqual(guess_game("Esports", "CS 2. CCT Europe Series"), "cs2")
        self.assertEqual(guess_game("Esports", "Counter-Strike. ESL Pro League"), "cs2")
        self.assertEqual(guess_game("Esports", "League of Legends. Worlds"), "lol")
        self.assertEqual(guess_game("Esports", "Dota 2. DreamLeague"), None)

    def test_linefeed_event_parser_on_a_committed_sample(self):
        path = SAMPLES / "linefeed_melbet_sport40_1x2.json"
        if not path.exists():
            self.skipTest("no committed LineFeed sample")
        events = json.loads(path.read_text(encoding="utf-8"))["Value"]
        rows = [e for e in events if isinstance(e, dict)]
        self.assertGreater(len(rows), 10)
        parsed = [(e, parse_linefeed_event(e)) for e in rows]
        ok = [(e, p) for e, p in parsed if p]
        self.assertGreater(len(ok), 10, "most sampled events should carry a 2-way moneyline")
        for e, p in ok:
            self.assertGreater(p["dec_a"], 1.0)
            self.assertGreater(p["dec_b"], 1.0)
            self.assertTrue(p["team_a"] and p["team_b"])
            self.assertNotEqual(p["team_a"], p["team_b"])
        leagues = {str(e.get("LE") or "") for e, _ in ok}
        self.assertTrue(any("CS 2." in lg for lg in leagues), leagues)

    def test_bovada_sample_carries_moneyline_payload_shape(self):
        path = SAMPLES / "bovada_cs2.json"
        if not path.exists():
            self.skipTest("no committed Bovada sample")
        groups = json.loads(path.read_text(encoding="utf-8"))
        events = [e for g in groups for e in (g.get("events") or [])]
        self.assertTrue(events, "Bovada CS2 coupon should list events")
        moneylines = 0
        for ev in events:
            for dg in ev.get("displayGroups") or []:
                for mk in dg.get("markets") or []:
                    if str(mk.get("description", "")).lower() != "moneyline":
                        continue
                    if not (mk.get("period") or {}).get("main"):
                        continue
                    outs = mk.get("outcomes") or []
                    if len(outs) == 2 and all((o.get("price") or {}).get("decimal") for o in outs):
                        moneylines += 1
        self.assertGreater(moneylines, 0, "sample should contain at least one main moneyline")

    def test_pinnacle_sample_carries_matchup_and_price_shape(self):
        path = SAMPLES / "pinnacle_esports_matchups.json"
        if not path.exists():
            self.skipTest("no committed Pinnacle sample")
        rows = json.loads(path.read_text(encoding="utf-8"))
        # Collector bounds large evidence with an explicit envelope. Verify the
        # retained real rows, not the envelope's string keys.
        if isinstance(rows, dict):
            self.assertTrue(rows.get("_trimmed_list"))
            self.assertGreaterEqual(rows["_original_length"], len(rows["_items"]))
            rows = rows["_items"]
        self.assertIsInstance(rows, list)
        matchups = [m for m in rows if m.get("type") == "matchup"]
        self.assertTrue(matchups)
        for m in matchups:
            self.assertEqual(len(m.get("participants") or []), 2)
            self.assertIn((m.get("league") or {}).get("name", "")[:4],
                          ("CS2 ", "Dota", "Leag", "Rain", "Valo"))


class TestProbabilityMath(unittest.TestCase):
    def test_proportional_no_vig(self):
        pa, pb, over = implied(2.0, 2.0)
        self.assertEqual((pa, pb), (0.5, 0.5))
        self.assertAlmostEqual(over, 0.0, places=6)
        pa, pb, over = implied(1.5, 2.5)
        self.assertAlmostEqual(pa + pb, 1.0, places=6)
        self.assertAlmostEqual(pa, 0.625, places=4)
        self.assertAlmostEqual(over, 0.066667, places=5)
        self.assertEqual(implied(1.0, 2.0), (None, None, None))

    def test_consensus_is_the_mean_over_sources(self):
        quotes = [
            {"source_key": "a", "implied_prob_a": 0.60, "implied_prob_b": 0.40},
            {"source_key": "b", "implied_prob_a": 0.50, "implied_prob_b": 0.50},
        ]
        c = consensus(quotes)
        self.assertEqual(c["n_sources"], 2)
        self.assertAlmostEqual(c["prob_a"], 0.55)
        self.assertAlmostEqual(c["spread_a"], 0.10)
        self.assertEqual(c["sources"], ["a", "b"])
        self.assertIsNone(consensus([{"source_key": "a", "implied_prob_a": None}]))


class TestJoinRules(unittest.TestCase):
    fixture = {
        "team_a": "Zomblers", "team_b": "Overtake Sector",
        "competition_name": "ESL Challenger League Season 52: North America - Cup #3",
        "scheduled_start_time": "2026-10-14T01:00:00Z",
    }

    def test_join_accepts_tolerated_time_and_records_side_swap(self):
        quote = {"team_a_name": "Overtake Sector", "team_b_name": "Zomblers",
                 "start_time_utc": "2026-10-14T01:05:00Z"}
        join = join_quote(self.fixture, quote)
        self.assertIsNotNone(join)
        self.assertEqual(join["side_order"], "reversed")
        self.assertLessEqual(join["start_time_delta_min"], 90)

    def test_join_rejects_wrong_teams(self):
        quote = {"team_a_name": "Zomblers", "team_b_name": "Some Other Team",
                 "start_time_utc": "2026-10-14T01:00:00Z"}
        self.assertIsNone(join_quote(self.fixture, quote))

    def test_join_rejects_time_outside_tolerance(self):
        quote = {"team_a_name": "Zomblers", "team_b_name": "Overtake Sector",
                 "start_time_utc": "2026-10-15T01:00:00Z"}
        self.assertIsNone(join_quote(self.fixture, quote))

    def test_join_accepts_clock_skew_when_the_competition_agrees(self):
        fixture = {"team_a": "Cloud9", "team_b": "Karmine Corp",
                   "competition_name": "World Championship Play-In",
                   "scheduled_start_time": "2026-10-15T18:00:00Z"}
        quote = {"team_a_name": "Karmine Corp", "team_b_name": "Cloud9",
                 "source_league": "League of Legends - World Championship Play-In",
                 "start_time_utc": "2026-10-15T13:00:00Z"}
        join = join_quote(fixture, quote)
        self.assertIsNotNone(join)
        self.assertFalse(join["within_strict_tolerance"])
        self.assertEqual(join["side_order"], "reversed")
        self.assertIn("clock-skew", join["rule"])

    def test_join_rejects_clock_skew_without_competition_agreement(self):
        fixture = {"team_a": "Cloud9", "team_b": "Karmine Corp",
                   "competition_name": "Some Local Cup",
                   "scheduled_start_time": "2026-10-15T18:00:00Z"}
        quote = {"team_a_name": "Cloud9", "team_b_name": "Karmine Corp",
                 "source_league": "League of Legends - World Championship Play-In",
                 "start_time_utc": "2026-10-15T13:00:00Z"}
        self.assertIsNone(join_quote(fixture, quote))

    def test_join_without_time_requires_competition_agreement(self):
        quote = {"team_a_name": "Zomblers", "team_b_name": "Overtake Sector",
                 "start_time_utc": None,
                 "source_league": "ESL Challenger League North America"}
        self.assertIsNotNone(join_quote(self.fixture, quote))
        quote_bad = {"team_a_name": "Zomblers", "team_b_name": "Overtake Sector",
                     "start_time_utc": None, "source_league": "Some Unrelated Cup"}
        self.assertIsNone(join_quote(self.fixture, quote_bad))


class TestPublishedData(unittest.TestCase):
    """Checks that only run once data/expanded/lines.json exists (i.e. after a collector run)."""

    lines_path = ROOT / "data" / "expanded" / "lines.json"

    def setUp(self):
        if not self.lines_path.exists():
            self.skipTest("no data/expanded/lines.json yet")
        self.doc = json.loads(self.lines_path.read_text(encoding="utf-8"))

    def test_every_priced_fixture_has_a_source_link_and_timestamp(self):
        for row in self.doc["fixtures"]:
            for q in row.get("quotes") or []:
                self.assertTrue(q.get("source_api_url") or q.get("source_public_url"),
                                f"fixture {row['fixture_id']} quote without a source link")
                self.assertTrue(q.get("retrieved_at_utc"), row["fixture_id"])
                self.assertIsNotNone(q.get("decimal_odds_a"))
                self.assertIsNotNone(q.get("decimal_odds_b"))

    def test_unpriced_fixtures_carry_no_probability(self):
        for row in self.doc["fixtures"]:
            if not row.get("quotes"):
                self.assertIsNone(row.get("consensus"))
                self.assertIsNone(row.get("pick"))
                self.assertIn("no_external_line_found", row["verification"]["flags"])

    def test_probabilities_are_normalised_and_pick_matches_consensus(self):
        for row in self.doc["fixtures"]:
            c = row.get("consensus")
            if not c:
                continue
            self.assertAlmostEqual(c["prob_a"] + c["prob_b"], 1.0, places=3)
            self.assertEqual(row["pick"]["team"],
                             row["team_a"] if c["prob_a"] >= c["prob_b"] else row["team_b"])
            self.assertGreaterEqual(row["pick"]["probability"], 0.5)

    def test_hotspawn_crowd_percentage_is_flagged_as_reference_only(self):
        for row in self.doc["fixtures"]:
            ref = row["hotspawn_pick_pct_reference_only"]
            self.assertIn("never used as a probability input", ref["note"])

    def test_originated_estimates_never_overwrite_market_values(self):
        for row in self.doc["fixtures"]:
            est = row.get("originated_estimate")
            if not est or not est.get("available"):
                continue
            self.assertIsNone(row.get("consensus"), row["fixture_id"])
            self.assertIn("ORIGINATED MODEL", est["label"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestRepoReviewWindow(unittest.TestCase):
    """The R1 comparison set is the live pick'em window, not every fixture the API ever served."""

    NOW = datetime(2026, 10, 13, 22, 0, tzinfo=timezone.utc)
    LIVE = [
        {"id": "a", "sport_alias": "cs2", "status": "scheduled", "scheduled_start_time": "2026-10-15T08:00:00Z"},
        {"id": "b", "sport_alias": "cs2", "status": "ended", "scheduled_start_time": "2026-10-15T08:00:00Z"},
        {"id": "c", "sport_alias": "lol", "status": "cancelled", "scheduled_start_time": "2026-10-15T08:00:00Z"},
        {"id": "d", "sport_alias": "lol", "status": "scheduled", "scheduled_start_time": 1792065600000},
        {"id": "e", "sport_alias": "dota2", "status": "scheduled", "scheduled_start_time": 1792065600000},
        {"id": "f", "sport_alias": "cs2", "status": "scheduled", "scheduled_start_time": None},
        {"id": "g", "sport_alias": "cs2", "status": "scheduled", "scheduled_start_time": "2026-08-01T08:00:00Z"},
        {"id": "h", "sport_alias": "cs2", "status": "scheduled", "scheduled_start_time": "2027-06-01T08:00:00Z"},
    ]

    def test_window_keeps_only_upcoming_cs2_and_lol(self):
        ids = [f["id"] for f in window_rows(self.LIVE, self.NOW)]
        self.assertEqual(ids, ["a", "d"])

    def test_window_tolerates_naive_and_epoch_timestamps(self):
        naive = [{"id": "n", "sport_alias": "cs2", "status": "scheduled",
                  "scheduled_start_time": "2026-10-14T10:00:00"}]
        self.assertEqual([f["id"] for f in window_rows(naive, self.NOW)], ["n"])

    def test_window_is_empty_for_an_empty_response(self):
        self.assertEqual(window_rows([], self.NOW), [])


class TestHotspawnLinks(unittest.TestCase):
    """The board must never construct a /matches/<id> path (audited by session 308d29e5)."""

    def test_published_permalink_is_used_verbatim(self):
        url = ("https://www.hotspawn.com/matches/zomblers-vs-overtake-sector-esl-challenger-"
               "league-season-52-north-america-cup-3-1079546")
        got, kind = hotspawn_link("1079546", {"1079546": url})
        self.assertEqual(got, url)
        self.assertIn("permalink", kind)

    def test_missing_permalink_falls_back_to_the_official_lobby(self):
        got, kind = hotspawn_link("1079546", {})
        self.assertEqual(got, "https://play.hotspawn.com/lobby")
        self.assertIn("lobby", kind)

    def test_numeric_only_permalink_is_rejected(self):
        got, kind = hotspawn_link("1079546", {"1079546": "https://www.hotspawn.com/matches/1079546"})
        self.assertEqual(got, "https://play.hotspawn.com/lobby")
        self.assertNotIn("/matches/1079546", got)

    def test_published_board_carries_no_constructed_match_path(self):
        board = ROOT / "data" / "expanded" / "lines.json"
        if not board.exists():
            self.skipTest("board not collected yet")
        doc = json.loads(board.read_text(encoding="utf-8"))
        bad = []
        for row in doc["fixtures"]:
            url = str(row.get("hotspawn_match_url") or "")
            if "/matches/" in url and url.rstrip("/").rsplit("/", 1)[-1].isdigit():
                bad.append({"fixture_id": row.get("fixture_id"), "url": url})
        self.assertEqual(bad, [])
