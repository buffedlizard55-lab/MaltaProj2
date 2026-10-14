#!/usr/bin/env python3
"""Regression tests for session b1fb1465 (executive summary, unresolved-pick resolution).

They run without any network: the collector's parsing rules are exercised on synthetic payloads, the
join/classify logic on synthetic quotes, and the whole build → render → verify chain on a synthetic
snapshot written to a temporary directory. A failure here means the published section is wrong.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "b1fb1465"))

import build  # noqa: E402
import core  # noqa: E402
import render  # noqa: E402
import verify  # noqa: E402


class CoreMath(unittest.TestCase):
    def test_no_vig_removes_the_margin(self):
        rec = core.no_vig(1.9091, 1.8333)
        self.assertAlmostEqual(rec["prob_a"] + rec["prob_b"], 1.0, places=9)
        self.assertGreater(rec["overround"], 0)
        self.assertAlmostEqual(rec["prob_a"], (1 / 1.9091) / (1 / 1.9091 + 1 / 1.8333), places=9)

    def test_no_vig_refuses_impossible_prices(self):
        self.assertIsNone(core.no_vig(1.0, 2.0))
        self.assertIsNone(core.no_vig("abc", 2.0))

    def test_american_conversion(self):
        self.assertAlmostEqual(core.american_to_decimal(100), 2.0, places=9)
        self.assertAlmostEqual(core.american_to_decimal(-200), 1.5, places=9)
        self.assertIsNone(core.american_to_decimal(50))

    def test_vrs_probability_is_monotone_and_symmetric(self):
        p = core.vrs_probability(1000, 800, 400)
        self.assertGreater(p, 0.5)
        self.assertAlmostEqual(core.vrs_probability(800, 1000, 400), 1 - p, places=9)
        self.assertAlmostEqual(core.vrs_probability(500, 500, 400), 0.5, places=9)

    def test_confidence_caps_thin_exchange_books(self):
        self.assertTrue(core.confidence(0.9, "exchange").startswith("Moderate"))
        self.assertEqual(core.confidence(0.9, "market"), "Strong")


class NamesAndAliases(unittest.TestCase):
    def test_norm_does_not_merge_distinct_rosters(self):
        self.assertEqual(core.norm("B8 Academy"), core.norm("b8 academy"))
        self.assertNotEqual(core.norm("B8 Academy"), core.norm("B8"))
        self.assertNotEqual(core.norm("MIBR Academy"), core.norm("MIBR"))

    def test_rounds_alias_resolves_to_roundsgg(self):
        key, evidence, note = core.canon("ROUNDS")
        self.assertEqual(key, "roundsgg")
        self.assertTrue(evidence and note)

    def test_wraith_pcific_alias(self):
        self.assertEqual(core.canon("WRAITH PCIFIC")[0], "pcific")
        self.assertEqual(core.canon("PCIFIC")[0], "pcific")

    def test_privateer_gaming_alias(self):
        self.assertEqual(core.canon("Privateer Gaming")[0], core.canon("Privateer")[0])

    def test_unknown_names_are_not_merged(self):
        self.assertNotEqual(core.canon("Ryvex")[0], core.canon("PCIFIC")[0])


class HotspawnParsing(unittest.TestCase):
    def _raw(self, **over):
        raw = {"id": 1081113, "sport_alias": "cs2", "competition_name": "CCT",
               "scheduled_start_time": 1791993600000, "lock_time": 1791993240000,
               "participants0_name": "Ryvex", "participants1_name": "PCIFIC", "status": "scheduled"}
        raw.update(over)
        return raw

    def test_parses_epoch_milliseconds_to_utc(self):
        fx = core.fixture_from_hotspawn(self._raw())
        self.assertEqual(fx["fixture_id"], "1081113")
        self.assertTrue(fx["start_utc"].endswith("Z"))
        self.assertEqual(core.parse_iso(fx["start_utc"]).year, 2026)

    def test_refuses_non_cs2(self):
        self.assertIsNone(core.fixture_from_hotspawn(self._raw(sport_alias="lol")))

    def test_refuses_crowd_pick_fields(self):
        with self.assertRaises(AssertionError):
            core.fixture_from_hotspawn(self._raw(pick_percent_a=14))

    def test_refuses_missing_participants(self):
        self.assertIsNone(core.fixture_from_hotspawn(self._raw(participants1_name=None)))

    def test_is_open_requires_a_future_lock(self):
        now = core.parse_iso("2026-10-14T12:00:00Z")
        fx = core.fixture_from_hotspawn(self._raw())
        self.assertTrue(core.is_open(fx, now))
        locked = dict(fx, lock_utc=core.iso(now - timedelta(minutes=1)))
        self.assertFalse(core.is_open(locked, now))
        finished = dict(fx, winner="Ryvex")
        self.assertFalse(core.is_open(finished, now))


class JoinRules(unittest.TestCase):
    @staticmethod
    def _fixture(team_a="Ryvex", team_b="PCIFIC", start="2026-10-14T14:00:00Z"):
        return {"fixture_id": "1", "team_a": team_a, "team_b": team_b, "start_utc": start}

    def _index(self, *quotes):
        idx: dict = {}
        for q in quotes:
            ka, _, _ = core.canon(q["team_a"])
            kb, _, _ = core.canon(q["team_b"])
            idx.setdefault(frozenset((ka, kb)), []).append(q)
        return idx

    def test_alias_join_aligns_sides(self):
        quote = {"source_key": "bovada", "team_a": "Wraith Pcific", "team_b": "Ryvex",
                 "prob_a": 0.6, "start_utc": "2026-10-14T14:00:00Z", "decimal_a": 1.6,
                 "decimal_b": 2.5, "event_id": "x", "public_url": "https://example.invalid"}
        joined = build.join_quotes(self._fixture(), self._index(quote), [])
        self.assertEqual(len(joined), 1)
        self.assertTrue(joined[0]["swapped"])
        self.assertAlmostEqual(joined[0]["prob_a"], 0.4, places=6)
        self.assertAlmostEqual(joined[0]["source_prob_a"], 0.6, places=6)

    def test_time_mismatch_is_refused_and_recorded(self):
        quote = {"source_key": "bovada", "team_a": "mellren", "team_b": "Privateer Gaming",
                 "prob_a": 0.5, "start_utc": "2026-10-15T14:00:00Z", "decimal_a": 2.0,
                 "decimal_b": 2.0, "event_id": "y", "public_url": "https://example.invalid"}
        rejected: list = []
        fx = self._fixture("mellren", "Privateer", "2026-10-16T14:00:00Z")
        joined = build.join_quotes(fx, self._index(quote), rejected)
        self.assertEqual(joined, [])
        self.assertEqual(rejected[0]["reason"], "same team pair but the kick-off times disagree")
        self.assertEqual(rejected[0]["start_diff_h"], 24.0)   # HotSpawn kick-off minus source

    def test_market_consensus_is_the_median(self):
        quotes = [{"source_key": "bovada", "prob_a": 0.40}, {"source_key": "melbet", "prob_a": 0.50},
                  {"source_key": "pinnacle", "prob_a": 0.60}]
        rec = build.market_consensus(quotes)
        self.assertAlmostEqual(rec["prob_a"], 0.50, places=9)
        self.assertEqual(rec["n_sources"], 3)
        self.assertAlmostEqual(rec["spread_a"], 0.20, places=6)

    def test_thin_exchange_book_is_kept_and_flagged(self):
        quotes = [{"source_key": "kalshi", "prob_a": 0.7, "thin_book": True, "spread": 0.14}]
        rec = build.exchange_consensus(quotes)
        self.assertTrue(rec["thin_book"])
        self.assertAlmostEqual(rec["max_spread"], 0.14, places=6)

    def test_calibration_is_bounded(self):
        pairs = [{"delta": 200.0, "market_prob_a": 0.7}] * 8
        cal = build.fit_calibration(pairs)
        self.assertLessEqual(cal["k"], build.CAL_K_BOUNDS[1])
        self.assertGreaterEqual(cal["k"], build.CAL_K_BOUNDS[0])


class EndToEnd(unittest.TestCase):
    """build → render → verify on a synthetic snapshot, in a temporary tree."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "data" / "b1fb1465").mkdir(parents=True)
        (root / ".github" / "workflows").mkdir(parents=True)
        self.root = root
        fixture_open = {
            "fixture_id": "1", "competition": "CCT Europe 2026 Series #12 Play-In", "tier": "C",
            "stage": "group b", "status": "scheduled",
            "start_utc": core.iso(core.now_utc() + timedelta(hours=6)),
            "lock_utc": core.iso(core.now_utc() + timedelta(hours=5, minutes=54)),
            "team_a": "Ryvex", "team_b": "PCIFIC",
            "hotspawn_url": "https://www.hotspawn.com/matches/ryvex-vs-pacific-x-1",
            "hotspawn_url_kind": "match page",
        }
        fixture_model = {
            "fixture_id": "2", "competition": "Elisa BreakOut Series #2", "tier": "C",
            "stage": "group", "status": "scheduled",
            "start_utc": core.iso(core.now_utc() + timedelta(hours=30)),
            "lock_utc": core.iso(core.now_utc() + timedelta(hours=29, minutes=54)),
            "team_a": "HAVU", "team_b": "RoundsGG",
            "hotspawn_url": "https://play.hotspawn.com/lobby",
            "hotspawn_url_kind": "official lobby page (no permalink)",
        }
        snapshot = {
            "session": "b1fb1465", "generated_utc": core.iso(core.now_utc()),
            "hotspawn": {"fixtures": [fixture_open, fixture_model], "week": {}, "permalinks": {}},
            "quotes": [
                {"source_key": "bovada", "source_name": "Bovada", "public_url": "https://bovada.lv/x",
                 "api_url": "https://bovada.lv/api", "event_id": "42", "team_a": "Wraith Pcific",
                 "team_b": "Ryvex", "decimal_a": 1.6, "decimal_b": 2.4, "prob_a": 0.6,
                 "raw_format": "decimal", "raw_a": "1.6", "raw_b": "2.4",
                 "start_utc": fixture_open["start_utc"], "league": "Series 12", "live": False,
                 "retrieved_utc": core.iso(core.now_utc())},
            ],
            "kalshi_not_usable": [],
            "vrs": {"snapshot": "live/2026/standings_global_2026_10_05.md",
                    "source_url": "https://github.com/ValveSoftware/counter-strike_regional_standings"},
            "vrs_teams": {"havu": {"name": "HAVU", "standing": 124, "points": 937, "roster": ""},
                          "roundsgg": {"name": "RoundsGG", "standing": 200, "points": 600,
                                       "roster": ""}},
            "bo3gg_teams": {}, "access": {
                "hltv_matches": {"url": "https://www.hltv.org/matches", "status": 403,
                                 "bytes": 4096, "error": "HTTPError 403",
                                 "at_utc": core.iso(core.now_utc())}},
            "notes": [],
        }
        (root / "data" / "b1fb1465" / "snapshot.json").write_text(json.dumps(snapshot),
                                                                  encoding="utf-8")
        (root / ".github" / "workflows" / "exec-b1fb1465.yml").write_text(
            "on:\n  schedule:\n    - cron: '23 */4 * * *'\n", encoding="utf-8")
        self._patch()

    def _patch(self):
        for module in (build, render, verify):
            module.ROOT = self.root
        build.DATA = self.root / "data" / "b1fb1465"
        render.DATA = self.root / "data" / "b1fb1465"
        render.OUT = self.root / "exec"
        verify.DATA = self.root / "data" / "b1fb1465"
        verify.EXEC = self.root / "exec"

    def tearDown(self):
        self.tmp.cleanup()
        # restore the real repository paths
        for module in (build, render, verify):
            module.ROOT = ROOT
        build.DATA = ROOT / "data" / "b1fb1465"
        render.DATA = ROOT / "data" / "b1fb1465"
        render.OUT = ROOT / "exec"
        verify.DATA = ROOT / "data" / "b1fb1465"
        verify.EXEC = ROOT / "exec"

    def test_pipeline_publishes_and_verifies(self):
        self.assertEqual(build.main(), 0)
        board = json.loads((self.root / "data" / "b1fb1465" / "board.json").read_text())
        self.assertEqual(board["summary"]["open_for_picks"], 2)
        rows = {r["fixture_id"]: r for r in board["open"]}
        self.assertEqual(rows["1"]["basis"], "market")
        # The Bovada quote names "Wraith Pcific" first with p=0.60; after side alignment the
        # fixture's first team (Ryvex) is the 0.40 side, so the pick must be PCIFIC at 60%.
        self.assertAlmostEqual(rows["1"]["prob_a"], 0.4, places=6)
        self.assertEqual(rows["1"]["pick"], "PCIFIC")
        self.assertAlmostEqual(rows["1"]["pick_probability"], 0.6, places=6)
        self.assertEqual(rows["2"]["basis"], "model")         # no price, official ratings exist
        self.assertEqual(rows["2"]["unresolved_category"], "resolved_by_originated_line")
        self.assertEqual(board["summary"]["unresolved"], 0)
        self.assertEqual(board["summary"]["resolved_by_originated_line"], 1)
        self.assertEqual(render.main(), 0)
        for name in ("index.html", "picks.html", "unresolved.html", "sources.html", "flagged.html",
                     "method.html"):
            self.assertTrue((self.root / "exec" / name).is_file(), name)
        index = (self.root / "exec" / "index.html").read_text()
        self.assertIn("Unresolved picks", index)
        self.assertIn("picks.html", index)
        self.assertIn("HLTV", index)
        self.assertEqual(verify.main(), 0)

    def test_verify_catches_a_tampered_probability(self):
        build.main()
        render.main()
        path = self.root / "data" / "b1fb1465" / "board.json"
        board = json.loads(path.read_text())
        board["open"][0]["market"]["quotes"][0]["prob_a"] += 0.2
        path.write_text(json.dumps(board), encoding="utf-8")
        self.assertEqual(verify.main(), 1)

    def test_verify_catches_a_missing_source_link(self):
        build.main()
        render.main()
        path = self.root / "data" / "b1fb1465" / "board.json"
        board = json.loads(path.read_text())
        board["open"][0]["sources"] = []
        path.write_text(json.dumps(board), encoding="utf-8")
        self.assertEqual(verify.main(), 1)

    def test_verify_catches_a_wrong_pick(self):
        build.main()
        render.main()
        path = self.root / "data" / "b1fb1465" / "board.json"
        board = json.loads(path.read_text())
        for row in board["open"]:
            if row["pick"]:
                row["pick"] = row["team_b"] if row["pick"] == row["team_a"] else row["team_a"]
        path.write_text(json.dumps(board), encoding="utf-8")
        self.assertEqual(verify.main(), 1)

    def test_unresolved_rows_stay_blank(self):
        snapshot_path = self.root / "data" / "b1fb1465" / "snapshot.json"
        snap = json.loads(snapshot_path.read_text())
        snap["quotes"] = []
        snap["vrs_teams"] = {}
        snapshot_path.write_text(json.dumps(snap), encoding="utf-8")
        self.assertEqual(build.main(), 0)
        board = json.loads((self.root / "data" / "b1fb1465" / "board.json").read_text())
        self.assertEqual(board["summary"]["unresolved"], 2)
        for row in board["open"]:
            self.assertIsNone(row["prob_a"])
            self.assertIsNone(row["pick"])
            self.assertTrue(row["limitations"])
        render.main()
        self.assertEqual(verify.main(), 0)
        page = (self.root / "exec" / "unresolved.html").read_text()
        self.assertIn("Not resolved", page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
