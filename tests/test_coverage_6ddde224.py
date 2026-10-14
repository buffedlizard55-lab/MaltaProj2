#!/usr/bin/env python3
"""Tests for the T-COVERAGE-FULL pipeline (session 6ddde224).

These tests are deliberately offline: every input below is a small hand-written fixture whose
expected output is derived from the published rule on the method page, not from a live service.
Run with:  python -m unittest tests.test_coverage_6ddde224 -v
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/coverage"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


cov_core = _load("cov_core", ROOT / "scripts/coverage/cov_core.py")
build = _load("build_coverage", ROOT / "scripts/coverage/build_coverage.py")


def fixture(fid="1", a="Gothic", b="Lavked", start="2026-10-14T08:00:00Z",
            lock="2026-10-14T07:54:00Z", status="scheduled", listed=True, crowd=(17, 83)):
    return {
        "fixture_id": fid, "game": "CS2", "competition": "CCT Europe 2026 Series #11",
        "tier": "b", "stage": None, "status": status, "start_time_utc": start,
        "lock_time_utc": lock, "team_a": a, "team_b": b,
        "listed_in_lobby": listed,
        "hotspawn_crowd_pct_reference_only": {"team_a": crowd[0], "team_b": crowd[1],
                                              "note": "reference only"},
        "source": {"api": "https://example.invalid/fixtures", "page": "https://play.hotspawn.com/lobby",
                   "match": f"https://www.hotspawn.com/matches/{fid}"},
    }


def quote(a="Gothic", b="Lavked", odds_a=1.881, odds_b=1.782, start="2026-10-14T08:00:00Z",
          read=None, live=False, source="melbet"):
    read = read or build.now_iso()
    return {
        "source_key": source, "source_name": source.title(), "source_kind": "bookmaker",
        "market_type": "match winner (moneyline, full match)", "market_is_live": live,
        "market_status": "open", "source_event_id": "1",
        "source_public_url": f"https://example.invalid/{source}", "source_api_url": "https://example.invalid/api",
        "retrieved_at_utc": read, "start_time_utc": start, "team_a_name": a, "team_b_name": b,
        "decimal_odds_a": odds_a, "decimal_odds_b": odds_b, "confidence": "market",
        "raw_price_format": "decimal",
    }


def inputs(fixtures=None, quotes=None, events=None, ratings=None, corpus=None):
    return {
        "fixtures": {"fixtures": fixtures if fixtures is not None else [fixture()],
                     "lobby": {"listed_ids": ["1"], "counters": {"all_tiers": 1}}},
        "quotes": {"quotes": quotes if quotes is not None else [quote()]},
        "events": {"events": events or []},
        "ratings": {"snapshots": {"global": "2026_10_05"},
                    "ratings": ratings if ratings is not None else {}},
        "corpus": corpus or {"matches": [], "team_names": {}},
    }


class CoreMathTest(unittest.TestCase):
    def test_devig_proportional_exact(self):
        p_a, p_b, over = cov_core.devig_proportional(2.0, 2.0)
        self.assertAlmostEqual(p_a, 0.5, places=12)
        self.assertAlmostEqual(p_b, 0.5, places=12)
        self.assertAlmostEqual(over, 1.0, places=12)

        p_a, p_b, over = cov_core.devig_proportional(1.881, 1.782)
        self.assertAlmostEqual(over, 1 / 1.881 + 1 / 1.782, places=12)
        self.assertAlmostEqual(p_a + p_b, 1.0, places=12)
        self.assertGreater(p_b, p_a)  # shorter price -> higher probability

    def test_devig_rejects_nonsense_prices(self):
        for bad in ((1.0, 2.0), (0.5, 2.0), (None, 2.0), (2.0, None)):
            with self.assertRaises(ValueError):
                cov_core.devig_proportional(*bad)

    def test_canon_team_normalisation(self):
        self.assertEqual(cov_core.canon_team("Team Liquid"), "liquid")
        self.assertEqual(cov_core.canon_team("NINJAS IN PYJAMAS"), "ninjas in pyjamas")
        self.assertEqual(cov_core.canon_team("Aurora Gaming"), "aurora")
        self.assertEqual(cov_core.canon_team("9z Team"), "9z")
        self.assertEqual(cov_core.canon_team("QUINTESSÊNCIA"), "quintessencia")
        # significant words are never stripped
        self.assertEqual(cov_core.canon_team("MIBR Academy"), "mibr academy")
        self.assertEqual(cov_core.canon_team("G2 Ares"), "g2 ares")
        self.assertNotEqual(cov_core.canon_team("MIBR"), cov_core.canon_team("MIBR Academy"))

    def test_same_teams_is_orientation_insensitive_but_not_fuzzy(self):
        self.assertTrue(cov_core.same_teams(("Gothic", "Lavked"), ("Lavked", "Gothic")))
        self.assertFalse(cov_core.same_teams(("Gothic", "Lavked"), ("Gothic", "Lavked B")))

    def test_kalshi_rules_time_is_parsed_in_utc(self):
        rules = ("If Phantom wins the Elisa BreakOut Series #2 2026: HAVU vs. Phantom CS2 match "
                 "originally scheduled for Oct 16, 2026 at 2:00 PM EDT, then the market resolves to Yes.")
        start, raw = build.kalshi_stated_start(rules)
        self.assertEqual(build.to_iso(start), "2026-10-16T18:00:00Z")
        self.assertIn("Oct 16, 2026 at 2:00 PM EDT", raw)
        self.assertEqual(build.kalshi_stated_start("no time here"), (None, None))


class JoinTest(unittest.TestCase):
    def test_prematch_quote_joins_with_expected_probabilities(self):
        board = build.build_board(inputs())
        row = board["rows"][0]
        self.assertEqual(row["published"]["basis"], "market")
        expected_a, _, _ = cov_core.devig_proportional(1.881, 1.782)
        self.assertAlmostEqual(row["published"]["prob_a"], expected_a, places=12)
        self.assertEqual(row["published"]["pick_team"], "Lavked")

    def test_reversed_source_orientation_is_corrected(self):
        board = build.build_board(inputs(quotes=[quote(a="Lavked", b="Gothic")]))
        row = board["rows"][0]
        expected_a, _, _ = cov_core.devig_proportional(1.782, 1.881)
        self.assertAlmostEqual(row["published"]["prob_a"], expected_a, places=12)

    def test_start_time_disagreement_beyond_tolerance_is_refused(self):
        board = build.build_board(inputs(quotes=[quote(start="2026-10-14T14:00:00Z")]))
        self.assertIsNone(board["rows"][0]["published"])
        self.assertTrue(any("start-time disagreement" in q["reason"] for q in board["rejected_quotes"]))
        self.assertIn("blank_no_published_probability", board["rows"][0]["flags"])
        # the refused candidate is published for review, with its source link
        refused = [q for q in board["rejected_quotes"] if q["reason"].startswith("start-time disagreement")]
        self.assertTrue(refused and refused[0]["source_public_url"])

    def test_in_play_quote_is_refused(self):
        board = build.build_board(inputs(quotes=[quote(live=True)]))
        self.assertIsNone(board["rows"][0]["published"])
        self.assertTrue(any("in-play" in q["reason"] for q in board["rejected_quotes"]))

    def test_stale_quote_is_refused(self):
        old = (build.now_utc() - timedelta(hours=build.FRESHNESS_HOURS + 1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        board = build.build_board(inputs(quotes=[quote(read=old)]))
        self.assertIsNone(board["rows"][0]["published"])
        self.assertTrue(any("old" in q["reason"] for q in board["rejected_quotes"]))

    def test_consensus_averages_distinct_sources_only(self):
        quotes = [quote(source="melbet", odds_a=1.881, odds_b=1.782),
                  quote(source="pinnacle", odds_a=1.60, odds_b=2.30),
                  # second melbet quote must not be double counted
                  quote(source="melbet", odds_a=9.99, odds_b=1.01,
                        read=(build.now_utc() - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"))]
        board = build.build_board(inputs(quotes=quotes))
        pub = board["rows"][0]["published"]
        p1 = cov_core.devig_proportional(1.881, 1.782)[0]
        p2 = cov_core.devig_proportional(1.60, 2.30)[0]
        self.assertAlmostEqual(pub["prob_a"], (p1 + p2) / 2, places=12)
        self.assertEqual(len(pub["sources"]), 2)
        self.assertEqual(board["summary"]["market"], 1)


class ModelTest(unittest.TestCase):
    def corpus(self, dominance=0.9, n=60):
        matches, names = [], {}
        for i in range(n):
            a, b = i % 4, (i % 4) + 4
            winner = a if (i / n) < dominance else b
            matches.append({"id": i, "d": "2026-09-01T00:00:00Z", "a": str(a), "b": str(b),
                            "w": str(winner), "bo": 3, "t": "b"})
        for i, name in enumerate(["Alpha", "Bravo", "Charlie", "Delta",
                                  "Echo", "Foxtrot", "Golf", "Hotel"]):
            names[str(i)] = name
        return {"matches": matches, "team_names": names, "generated_at_utc": build.now_iso(),
                "source": "https://bo3.gg/api/v1/matches", "source_public": "https://bo3.gg/matches/finished"}

    def test_bt_fit_orders_dominant_teams_and_meets_name_lookup(self):
        bt = build.fit_bradley_terry(self.corpus())
        self.assertEqual(bt["matches_used"], 60)
        self.assertGreater(bt["ratings"]["0"], bt["ratings"]["4"])
        p, why = build.bt_prob(bt, "Alpha", "Echo")
        self.assertEqual(why, "ok")
        self.assertGreater(p, 0.5)
        self.assertAlmostEqual(p + build.bt_prob(bt, "Echo", "Alpha")[0], 1.0, places=12)

    def test_bt_requires_minimum_corpus_matches(self):
        corpus = self.corpus(n=8)
        bt = build.fit_bradley_terry(corpus)
        # every team appears once per pair-cycle; a very short corpus must not publish a rating
        p, why = build.bt_prob(bt, "Alpha", "Echo")
        if bt["appearances"].get("0", 0) < build.BT_MIN_MATCHES:
            self.assertIsNone(p)
            self.assertIn("fewer than", why)

    def test_bt_unknown_team_returns_no_probability(self):
        bt = build.fit_bradley_terry(self.corpus())
        p, why = build.bt_prob(bt, "Alpha", "Team Not In Corpus")
        self.assertIsNone(p)
        self.assertIn("not present", why)

    def test_vrs_estimate_uses_published_scale_and_source(self):
        ratings = {"gothic": {"points": 705, "standings": 211, "snapshot": "2026_10_05",
                              "source_url": "https://api.github.com/repos/ValveSoftware/x"},
                   "lavked": {"points": 862, "standings": 143, "snapshot": "2026_10_05",
                              "source_url": "https://api.github.com/repos/ValveSoftware/x"}}
        p, why, info = build.vrs_prob(ratings, "Gothic", "Lavked")
        self.assertEqual(why, "ok")
        self.assertLess(p, 0.5)
        self.assertAlmostEqual(p, 1 / (1 + 10 ** (-(705 - 862) / build.ELO_SCALE)), places=12)
        self.assertEqual(info["source_url"], "https://api.github.com/repos/ValveSoftware/x")

    def test_vrs_missing_team_produces_blank_row_naming_the_team(self):
        board = build.build_board(inputs(quotes=[], ratings={}))
        row = board["rows"][0]
        self.assertIsNone(row["published"])
        self.assertTrue(any("no official Valve CS2 Regional Standings entry" in f for f in row["flags"]))

    def test_estimate_row_is_labelled_and_cites_its_input(self):
        ratings = {"gothic": {"points": 705, "standings": 211, "snapshot": "2026_10_05",
                              "source_url": "https://api.github.com/repos/ValveSoftware/x"},
                   "lavked": {"points": 862, "standings": 143, "snapshot": "2026_10_05",
                              "source_url": "https://api.github.com/repos/ValveSoftware/x"}}
        board = build.build_board(inputs(quotes=[], ratings=ratings))
        pub = board["rows"][0]["published"]
        self.assertEqual(pub["basis"], "vrs")
        self.assertEqual(pub["label"], build.ESTIMATE_LABEL)
        self.assertIn("not a market price", pub["label"])
        self.assertTrue(pub["source_url"])


class GuardTest(unittest.TestCase):
    def test_pick_is_the_higher_probability_or_coin_flip(self):
        board = build.build_board(inputs())
        pub = board["rows"][0]["published"]
        self.assertEqual(pub["pick_side"], "a" if pub["prob_a"] > 0.5 else "b")
        # an effective 50/50 produces no pick
        even = build.build_board(inputs(quotes=[quote(odds_a=1.98, odds_b=1.98)]))
        self.assertEqual(even["rows"][0]["published"]["pick_side"], "coin_flip")
        self.assertIsNone(even["rows"][0]["published"]["pick_team"])

    def test_hotspawn_crowd_percentage_can_never_change_a_published_number(self):
        """The lobby's crowd percentages are replaced by impossible values: nothing may move."""
        baseline = build.build_board(inputs())
        poisoned = inputs()
        poisoned["fixtures"]["fixtures"][0]["hotspawn_crowd_pct_reference_only"] = {
            "team_a": "IMPOSSIBLE", "team_b": "IMPOSSIBLE", "note": "poisoned"}
        after = build.build_board(poisoned)
        self.assertEqual(baseline["rows"][0]["published"]["prob_a"],
                         after["rows"][0]["published"]["prob_a"])
        self.assertEqual(baseline["rows"][0]["published"]["pick_team"],
                         after["rows"][0]["published"]["pick_team"])
        self.assertEqual(json.dumps(baseline["summary"], sort_keys=True),
                         json.dumps(after["summary"], sort_keys=True))

    def test_exchange_book_outside_spread_limit_is_not_published(self):
        event = {"event_ticker": "KXCS2GAME-26OCT140800GOTLAV", "title": "Gothic vs Lavked",
                 "sub_title": "Gothic vs. Lavked (Oct 14)",
                 "source_public_url": "https://kalshi.com/markets/kxcs2game",
                 "source_api_url": "https://api.elections.kalshi.com/trade-api/v2/events",
                 "retrieved_at_utc": build.now_iso(), "start_time_utc": "2026-10-14T12:00:00Z",
                 "rules_primary": ("If Lavked wins the CCT Europe 2026 Series #11: Gothic vs. Lavked CS2 "
                                   "match originally scheduled for Oct 14, 2026 at 4:00 AM EDT, then the "
                                   "market resolves to Yes."),
                 "sides": [{"ticker": "x-GOT", "team": "Gothic", "yes_bid": 0.10, "yes_ask": 0.90,
                            "last_price": 0.5, "bid_size": 1, "ask_size": 1, "volume": 0.0,
                            "open_interest": 10.0, "status": "active", "mid": 0.5, "spread": 0.8},
                           {"ticker": "x-LAV", "team": "Lavked", "yes_bid": 0.10, "yes_ask": 0.90,
                            "last_price": 0.5, "bid_size": 1, "ask_size": 1, "volume": 0.0,
                            "open_interest": 10.0, "status": "active", "mid": 0.5, "spread": 0.8}]}
        board = build.build_board(inputs(quotes=[], events=[event]))
        row = board["rows"][0]
        self.assertTrue(row["exchange"])
        self.assertFalse(row["exchange_usable"])
        self.assertIsNone(row["published"])
        self.assertTrue(any("spread" in r for r in row["exchange_reasons"]))

    def test_tight_exchange_book_is_published_with_its_spread(self):
        def side(team, bid, ask):
            return {"ticker": team, "team": team, "yes_bid": bid, "yes_ask": ask, "last_price": bid,
                    "bid_size": 5, "ask_size": 5, "volume": 3.0, "open_interest": 20.0,
                    "status": "active", "mid": (bid + ask) / 2, "spread": ask - bid}
        event = {"event_ticker": "KXCS2GAME-26OCT140800GOTLAV", "title": "Gothic vs Lavked",
                 "sub_title": "Gothic vs. Lavked (Oct 14)",
                 "source_public_url": "https://kalshi.com/markets/kxcs2game",
                 "source_api_url": "https://api.elections.kalshi.com/trade-api/v2/events",
                 "retrieved_at_utc": build.now_iso(), "start_time_utc": "2026-10-14T12:00:00Z",
                 "rules_primary": ("... originally scheduled for Oct 14, 2026 at 4:00 AM EDT, then the "
                                   "market resolves to Yes."),
                 "sides": [side("Gothic", 0.40, 0.50), side("Lavked", 0.50, 0.60)]}
        board = build.build_board(inputs(quotes=[], events=[event]))
        pub = board["rows"][0]["published"]
        self.assertEqual(pub["basis"], "exchange")
        self.assertAlmostEqual(pub["prob_a"], 0.45, places=9)
        # the mid price of the second side (0.55) is the higher probability, so it is the pick
        self.assertEqual(pub["pick_team"], "Lavked")
        self.assertAlmostEqual(pub["pick_probability"], 0.55, places=9)

    def test_bookmaker_consensus_never_includes_the_exchange(self):
        board = build.build_board(inputs(quotes=[quote()]))
        self.assertTrue(all(s["source_key"] != "kalshi"
                            for s in board["rows"][0]["published"]["sources"]))


class VerificationTest(unittest.TestCase):
    def board(self):
        ratings = {"gothic": {"points": 705, "standings": 211, "snapshot": "2026_10_05",
                              "source_url": "https://api.github.com/repos/x"},
                   "lavked": {"points": 862, "standings": 143, "snapshot": "2026_10_05",
                              "source_url": "https://api.github.com/repos/x"}}
        return build.build_board(inputs(
            fixtures=[fixture(fid="1"), fixture(fid="2", a="Alpha", b="Bravo", listed=False),
                      fixture(fid="3", a="Gothic", b="Lavked", start="2026-11-01T08:00:00Z")],
            quotes=[quote()], ratings=ratings))

    def test_verification_checks_pass_on_a_mixed_board(self):
        board = self.board()
        verification = build.verify_board(board)
        self.assertEqual(verification["failed"], 0, [c for c in verification["checks"] if not c["passed"]])
        self.assertGreaterEqual(verification["passed"], 8)

    def test_every_published_row_has_a_source_link(self):
        board = self.board()
        for row in board["rows"]:
            if not row["published"]:
                continue
            links = [s.get("source_public_url") for s in row["published"].get("sources", [])]
            links.append(row["published"].get("source_url"))
            self.assertTrue(any(links), f"row {row['fixture_id']} has no source link")

    def test_blank_rows_are_flagged_and_carry_a_reason(self):
        board = self.board()
        blanks = [r for r in board["rows"] if not r["published"]]
        self.assertTrue(blanks)
        for row in blanks:
            self.assertIn("blank_no_published_probability", row["flags"])
            self.assertTrue(len(row["flags"]) > 1)

    def test_render_writes_pages_without_empty_links(self):
        board = self.board()
        verification = build.verify_board(board)
        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp) / "coverage"
            build.render(board, verification, outdir)
            for name in ("index.html", "flagged.html", "method.html", "assets/coverage.css",
                         "assets/coverage.js", "data/board.json", "data/board.csv"):
                self.assertTrue((outdir / name).is_file(), name)
            index = (outdir / "index.html").read_text()
            self.assertIn("PICK", index)
            self.assertIn("HotSpawn", index)
            self.assertNotIn('href=""', index)
            self.assertNotIn('src=""', index)
            payload = json.loads((outdir / "data/board.json").read_text())
            self.assertEqual(len(payload["rows"]), len(board["rows"]))

    def test_flagged_page_lists_blanks_and_refusals(self):
        board = build.build_board(inputs(quotes=[quote(start="2026-10-14T14:00:00Z")]))
        verification = build.verify_board(board)
        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp) / "coverage"
            build.render(board, verification, outdir)
            flagged = (outdir / "flagged.html").read_text()
            self.assertIn("start-time disagreement", flagged)
            self.assertIn("Gothic", flagged)

    def test_no_lol_or_other_game_rows_enter_the_board(self):
        lol = fixture(fid="9", a="A", b="B")
        lol["game"] = "LoL"
        board = build.build_board(inputs(fixtures=[fixture(), lol]))
        self.assertEqual([r["fixture_id"] for r in board["rows"]], ["1"])

    def test_collector_module_does_not_read_the_crowd_field_for_probabilities(self):
        source = (ROOT / "scripts/coverage/build_coverage.py").read_text()
        used = [line for line in source.splitlines()
                if "hotspawn_crowd_pct_reference_only" in line]
        # the field may only be copied through to the board payload, never read as a number
        for line in used:
            self.assertNotIn("prob", line, line)
            self.assertNotIn("/ 100", line, line)


class CollectorShapeTest(unittest.TestCase):
    def test_bo3gg_quote_extraction_and_rejection(self):
        collect = _load("collect_coverage", ROOT / "scripts/coverage/collect_coverage.py")
        good = {"id": 1, "slug": "gothic-vs-lavked-14-10-2026", "status": "upcoming",
                "start_date": "2026-10-14T08:00:00.000+00:00", "bo_type": 3, "tier": "b",
                "bet_updates": {"path": "https://thunderpick.io/match/1", "provider": "thunderpick",
                                "team_1": {"name": "Gothic", "coeff": 1.9, "active": True, "team_id": 1},
                                "team_2": {"name": "Lavked", "coeff": 1.8, "active": True, "team_id": 2}}}
        q = collect.bo3g_quote_from_match(good, {})
        self.assertEqual(q["decimal_odds_a"], 1.9)
        self.assertEqual(q["start_time_utc"], "2026-10-14T08:00:00Z")
        self.assertEqual(q["source_public_url"], "https://bo3.gg/matches/gothic-vs-lavked-14-10-2026")
        self.assertEqual(q["provider_market_url"], "https://thunderpick.io/match/1")
        for mutate in ({"bet_updates": None},
                       {"bet_updates": {"team_1": {"name": "A", "coeff": 1.5, "active": False},
                                        "team_2": {"name": "B", "coeff": 2.5, "active": True}}},
                       {"bet_updates": {"team_1": {"name": "A", "coeff": 1.0},
                                        "team_2": {"name": "B", "coeff": 2.5}}},
                       {"bet_updates": {"team_1": {"name": None, "coeff": 1.5},
                                        "team_2": {"name": "B", "coeff": 2.5}}}):
            broken = copy.deepcopy(good)
            broken.update(mutate)
            self.assertIsNone(collect.bo3g_quote_from_match(broken, {}))

    def test_vrs_markdown_rows_are_parsed(self):
        collect = _load("collect_coverage", ROOT / "scripts/coverage/collect_coverage.py")
        markdown = ("### Regional Standings for Global as of 2026_10_05<br />\n\n"
                    "| Standing | Points | Team Name | Roster | |\n| :- | -: | :- | :- | :- |\n"
                    "| 84 | 1100 | FORZE Reload | a, b, c, d, e | [details](x) |\n"
                    "| 103 | 1035 | EAC | a, b, c, d, e | [details](x) |\n")
        rows = collect.vrs_rows(markdown)
        self.assertEqual(rows["forze reload"]["points"], 1100)
        self.assertEqual(rows["eac"]["standings"], 103)


if __name__ == "__main__":
    unittest.main(verbosity=2)
