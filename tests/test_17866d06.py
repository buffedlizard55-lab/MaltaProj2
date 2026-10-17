#!/usr/bin/env python3
"""Contract tests for session 17866d06 (day-4 live desk).

Two layers:

1. Engine invariants on synthetic inputs - deterministic, network-free, and they
   encode the project's hard rules (no-vig maths, strict join, flat payout with no
   ownership term, unresolved rows never get a guessed pick, HotSpawn never a
   probability input).
2. Rendered-artifact checks - the six pages exist, every internal link resolves,
   every pick row carries a source link, and unconfirmed values render blank with an
   UNVERIFIED tag instead of a number.

Board-level assertions run against ``data/17866d06/board.json`` when a capture has
been committed and skip cleanly when it has not, so the suite passes both before and
after the scheduled refresh.
"""
from __future__ import annotations

import importlib.util
import json
import math
import re
import shutil
import tempfile
import unittest
from html import escape as html_escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "17866d06"
PAGES = ROOT / "picks-day4"
SCRIPTS = ROOT / "scripts" / "17866d06"


def load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_17866d06", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


research = load("research")
collect = load("collect")
model = load("model")
build = load("build")

BOARD = json.loads((DATA / "board.json").read_text(encoding="utf-8")) if (DATA / "board.json").exists() else None
HAS_CAPTURE = bool(BOARD and BOARD.get("open"))

# --------------------------------------------------------------------- fixtures
def synthetic_vrs():
    return {"snapshot": "2026_10_05",
            "standings": {"global": {
                "Falcons": {"standing": 6, "points": 1843, "roster": "a, b, c, d, e"},
                "BETBOOM": {"standing": 11, "points": 1596, "roster": "f, g, h, i, j"},
                "Ninjas in Pyjamas": {"standing": 14, "points": 1534, "roster": "adamb, Krimbo, sjuush"},
                "HEROIC": {"standing": 15, "points": 1550, "roster": "k, l, m, n, o"},
                "6666": {"standing": 127, "points": 923, "roster": "amster, dENZY, kL1o"},
            }}}


def synthetic_fixture(fixture_id="1", team_a="NIP", team_b="HEROIC", start_epoch=1792224000.0,
                      offered=3, crowd_a=22, crowd_b=78, tier="b"):
    return {"fixture_id": fixture_id, "competition": "Test Cup", "competition_id": "99999",
            "sport": "cs2", "status": "scheduled", "tier": tier, "stage": "group", "offered_points": offered,
            "base_points": 2, "points_breakdown": {"game_multiplier": 1.25, "tier_multiplier": 1.5},
            "best_of": 3, "start_utc": "2026-10-17T08:00:00Z", "start_epoch": start_epoch,
            "lock_utc": "2026-10-17T07:54:00Z", "lock_offset_sec": 360,
            "team_a": team_a, "team_b": team_b, "crowd_a": crowd_a, "crowd_b": crowd_b,
            "total_picks": 41, "hotspawn_public_url": "https://play.hotspawn.com/lobby",
            "hotspawn_api_url": "https://example.invalid/fixtures"}


def synthetic_quote(source_key="melbet", team_a="Ninjas in Pyjamas", team_b="HEROIC",
                    decimal_a=2.103, decimal_b=1.73, start_epoch=1792224000.0, volume=None):
    quote = {"source_key": source_key, "book": source_key, "team_a": team_a, "team_b": team_b,
             "start_epoch": start_epoch, "start_utc": "2026-10-17T08:00:00Z",
             "public_url": "https://example.invalid/line", "evidence_url": "https://example.invalid/feed",
             "retrieved_utc": "2026-10-16T23:00:00Z"}
    if source_key == "polymarket":
        quote.update({"price_a": decimal_a, "price_b": decimal_b, "volume_usd": volume,
                      "market_slug": "cs2-test"})
        quote.pop("decimal_a", None), quote.pop("decimal_b", None)
    else:
        quote.update({"decimal_a": decimal_a, "decimal_b": decimal_b})
    return quote


def board_from(fixtures, quotes, vrs=None):
    joined, rejected = collect.join_quotes(fixtures, quotes, "2026-10-16T23:00:00Z")
    fixtures_doc = {"captured_utc": "2026-10-16T23:00:00Z", "open": fixtures, "dropped_stale": [],
                    "twc_settlement": [], "twc_competition_id": "35859"}
    quotes_doc = {"captured_utc": "2026-10-16T23:00:00Z", "joined": joined, "rejected": rejected,
                  "unjoined_for_calibration": [], "counts": {}}
    vrs_doc = vrs if vrs is not None else synthetic_vrs()
    return model.build_board(research, fixtures_doc, quotes_doc, vrs_doc)


# ------------------------------------------------------------------ maths + join
class TestMarketMaths(unittest.TestCase):
    def test_no_vig_removes_overround(self):
        fair = model.no_vig_from_decimal(1.5, 2.563)
        self.assertAlmostEqual(fair[0], (1 / 1.5) / (1 / 1.5 + 1 / 2.563), places=9)
        self.assertAlmostEqual(fair[0] + fair[1], 1.0, places=9)
        self.assertGreater(model.overround(1.5, 2.563), 1.0)

    def test_no_vig_rejects_bad_input(self):
        for pair in ((None, 2.0), (0, 2.0), ("x", 2.0), (1.9, None)):
            self.assertIsNone(model.no_vig_from_decimal(*pair))

    def test_polymarket_prices_renormalise_and_volume_weights_are_bounded(self):
        quote = synthetic_quote("polymarket", decimal_a=0.525, decimal_b=0.475, volume=12271.77)
        prob_a, prob_b, weight, kind = model.quote_implied(quote)
        self.assertAlmostEqual(prob_a + prob_b, 1.0, places=9)
        self.assertEqual(kind, "exchange")
        self.assertGreaterEqual(weight, 0.5)
        self.assertLessEqual(weight, 1.25)
        self.assertLess(model.poly_weight(10), model.poly_weight(100000))
        self.assertEqual(model.poly_weight(0), 0.5)

    def test_consensus_is_weighted_and_flags_disagreement(self):
        quotes = [synthetic_quote("melbet", decimal_a=1.40, decimal_b=2.90),
                  synthetic_quote("thunderpick", decimal_a=2.60, decimal_b=1.50)]
        cons, rows = model.consensus(quotes)
        self.assertEqual(cons["n_sources"], 2)
        self.assertTrue(cons["disagreement"])
        self.assertAlmostEqual(cons["prob_a"] + cons["prob_b"], 1.0, places=9)
        self.assertEqual(len(rows), 2)

    def test_logistic_is_monotonic_and_symmetric(self):
        self.assertAlmostEqual(model.logistic(0, 700), 0.5, places=9)
        self.assertGreater(model.logistic(200, 700), model.logistic(100, 700))
        self.assertAlmostEqual(model.logistic(100, 700) + model.logistic(-100, 700), 1.0, places=9)


class TestCalibration(unittest.TestCase):
    def test_fit_recovers_a_known_scale(self):
        truth = 520.0
        samples = []
        for delta in range(-600, 601, 50):
            if delta == 0:
                continue
            samples.append({"delta_points": delta, "market_prob_a": model.logistic(delta, truth)})
        fit = model.fit_scale(samples)
        self.assertTrue(fit["calibrated"])
        self.assertAlmostEqual(fit["scale"], truth, delta=1.0)
        self.assertGreater(fit["r_squared"], 0.99)

    def test_fit_falls_back_and_labels_itself_when_thin(self):
        fit = model.fit_scale([{"delta_points": 100, "market_prob_a": 0.6}])
        self.assertFalse(fit["calibrated"])
        self.assertEqual(fit["scale"], model.SCALE_FALLBACK)
        self.assertIn("fallback", fit["note"])

    def test_fit_clamps_to_bounds(self):
        samples = [{"delta_points": 1, "market_prob_a": 0.999} for _ in range(20)]
        self.assertLessEqual(model.fit_scale(samples)["scale"], model.SCALE_BOUNDS[1])
        samples = [{"delta_points": 5000, "market_prob_a": 0.51} for _ in range(20)]
        self.assertGreaterEqual(model.fit_scale(samples)["scale"], model.SCALE_BOUNDS[0])

    def test_extreme_market_prices_are_excluded_from_the_fit(self):
        samples = [{"delta_points": 100, "market_prob_a": 0.999}] * 20
        self.assertEqual(model.fit_scale(samples)["samples"], 0)


class TestStandingsResolution(unittest.TestCase):
    def setUp(self):
        self.index = model.vrs_index(synthetic_vrs()["standings"])

    def test_exact_and_verified_alias_resolve(self):
        self.assertTrue(model.resolve_vrs("Falcons", self.index)["resolved"])
        record = model.resolve_vrs("NIP", self.index)
        self.assertTrue(record["resolved"])
        self.assertEqual(record["name"], "Ninjas in Pyjamas")
        self.assertEqual(record["method"], "verified alias")
        self.assertIn("official standings", record["alias_evidence"])

    def test_case_and_spacing_are_normalised(self):
        self.assertTrue(model.resolve_vrs("  betboom ", self.index)["resolved"])
        self.assertTrue(model.resolve_vrs("Ninjas in Pyjamas", self.index)["resolved"])

    def test_two_rosters_sharing_one_name_are_never_collapsed(self):
        standings = {"global": {"6666": {"standing": 127, "points": 923, "roster": "amster, dENZY"},
                                "Team X": {"standing": 5, "points": 1500, "roster": "a"}}}
        # a second roster under the same name, as Valve's real snapshot has
        standings["global"]["6666 "] = None
        standings["global"].pop("6666 ")
        index = model.vrs_index({"global": {"6666": {"standing": 127, "points": 923, "roster": "amster"}}})
        index[model.norm("6666")] = {"standing": 368, "points": 425, "roster": "auth0ri", "name": "6666",
                                     "region": "global", "ambiguous_rosters": ["amster", "auth0ri"]}
        record = model.resolve_vrs("6666", index)
        self.assertFalse(record["resolved"])
        self.assertIn("more than one roster", record["reason"])

    def test_ambiguous_and_unknown_names_stay_unresolved(self):
        record = model.resolve_vrs("ex-6666", self.index)
        self.assertFalse(record["resolved"])
        self.assertIn("two different rosters", record["reason"])
        self.assertFalse(model.resolve_vrs("WROTBERRY", self.index)["resolved"])
        self.assertFalse(model.resolve_vrs("", self.index)["resolved"])
        self.assertFalse(model.resolve_vrs(None, self.index)["resolved"])

    def test_global_standing_wins_over_regional(self):
        standings = {"global": {"Team X": {"standing": 5, "points": 1500, "roster": "a"}},
                     "europe": {"Team X": {"standing": 2, "points": 1400, "roster": "a"}}}
        index = model.vrs_index(standings)
        self.assertEqual(index[model.norm("Team X")]["points"], 1500)
        self.assertEqual(index[model.norm("Team X")]["region"], "global")


class TestJoinRule(unittest.TestCase):
    def test_exact_epoch_and_names_join(self):
        fixtures = [synthetic_fixture(team_a="Ninjas in Pyjamas")]
        joined, rejected = collect.join_quotes(fixtures, [synthetic_quote()], "2026-10-16T23:00:00Z")
        self.assertEqual(len(joined), 1)
        self.assertEqual(joined[0]["fixture_id"], "1")
        self.assertEqual(joined[0]["join"]["confidence"], "exact")
        self.assertEqual(rejected, [])

    def test_the_melbet_2h30m_offset_row_is_rejected_not_priced(self):
        """Regression for flag F7: same two names, start 2.5 h later -> must not join."""
        fixtures = [synthetic_fixture()]
        late = synthetic_quote(start_epoch=1792233000.0)          # 10:30Z vs 08:00Z
        joined, rejected = collect.join_quotes(fixtures, [late], "2026-10-16T23:00:00Z")
        self.assertEqual(joined, [])
        self.assertEqual(len(rejected), 1)
        self.assertIn("no HotSpawn fixture", rejected[0]["reason"])

    def test_one_side_match_is_enough_but_a_contradiction_is_not(self):
        fixtures = [synthetic_fixture(team_a="BET-M", team_b="Just Players")]
        alias_quote = synthetic_quote(team_a="33 Team", team_b="Just Players")
        joined, _ = collect.join_quotes(fixtures, [alias_quote], "2026-10-16T23:00:00Z")
        self.assertEqual(len(joined), 1)
        self.assertEqual(joined[0]["join"]["confidence"], "alias")
        wrong = synthetic_quote(team_a="Falcons", team_b="Aurora")
        joined2, rejected2 = collect.join_quotes(fixtures, [wrong], "2026-10-16T23:00:00Z")
        self.assertEqual(joined2, [])
        self.assertEqual(len(rejected2), 1)

    def test_swapped_sides_are_detected(self):
        fixtures = [synthetic_fixture(team_a="HEROIC", team_b="NIP")]
        joined, _ = collect.join_quotes(fixtures, [synthetic_quote()], "2026-10-16T23:00:00Z")
        self.assertEqual(len(joined), 1)
        self.assertTrue(joined[0]["join"]["swapped"])

    def test_quote_without_a_start_time_is_rejected_and_kept(self):
        quote = synthetic_quote()
        quote["start_epoch"] = None
        joined, rejected = collect.join_quotes([synthetic_fixture()], [quote], "2026-10-16T23:00:00Z")
        self.assertEqual(joined, [])
        self.assertIn("no usable start time", rejected[0]["reason"])

    def test_stale_scheduled_rows_are_dropped_not_priced(self):
        captured = 1792300000.0
        row = {"id": 5, "competition_id": 1, "competition_name": "Old Cup", "sport_alias": "cs2",
               "status": "scheduled", "scheduled_start_time": int((captured - 7200) * 1000),
               "tier": "b", "offered_points": 3, "base_points": 2, "points_breakdown": {},
               "participants0_name": "A", "participants1_name": "B",
               "participants0_picked_percent": 50, "participants1_picked_percent": 50, "total_picks": 3}
        kept, dropped = collect.open_fixtures([row], captured)
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0]["reason"], "past_start_still_marked_scheduled")

    def test_iso_parsing_handles_zulu_space_and_naive_stamps(self):
        self.assertEqual(collect.iso_to_epoch("2026-10-17T08:00:00Z"),
                         collect.iso_to_epoch("2026-10-17 08:00:00"))
        self.assertIsNone(collect.iso_to_epoch("not a date"))
        self.assertIsNone(collect.iso_to_epoch(""))


# --------------------------------------------------------------- engine invariants
class TestPickEngine(unittest.TestCase):
    def test_flat_payout_no_ownership_term(self):
        """Flag F1: expected points = offered_points x P(win), never ownership-scaled."""
        board = board_from([synthetic_fixture(offered=3)], [synthetic_quote()])
        row = board["open"][0]
        self.assertAlmostEqual(row["pick"]["expected_points"],
                               row["offered_points"] * row["pick"]["prob"], places=2)
        text = json.dumps(row["final"]) + json.dumps(row["pick"]["reason"])
        self.assertNotIn("ownership", text.replace("crowd ownership", ""))

    def test_hotspawn_crowd_never_moves_the_probability(self):
        """The crowd can be 99/1 and the line must stay exactly the market line."""
        quotes = [synthetic_quote(decimal_a=1.80, decimal_b=1.95)]
        plain = board_from([synthetic_fixture(crowd_a=50, crowd_b=50)], quotes)["open"][0]
        skewed = board_from([synthetic_fixture(crowd_a=99, crowd_b=1)], quotes)["open"][0]
        self.assertEqual(plain["final"]["prob_a"], skewed["final"]["prob_a"])
        self.assertEqual(plain["consensus"]["prob_a"], skewed["consensus"]["prob_a"])

    def test_market_beats_model_and_single_quote_is_shrunk(self):
        fixtures = [synthetic_fixture(team_a="Falcons", team_b="BETBOOM")]
        two = board_from(fixtures, [synthetic_quote(team_a="Falcons", team_b="BETBOOM",
                                                    decimal_a=1.30, decimal_b=3.60),
                                    synthetic_quote("thunderpick", team_a="Falcons", team_b="BETBOOM",
                                                    decimal_a=1.34, decimal_b=3.40)])
        row = two["open"][0]
        self.assertIn("market consensus", row["final"]["basis"])
        self.assertEqual(row["consensus"]["n_sources"], 2)
        self.assertNotIn("shrunk", row["final"]["basis"])

        one = board_from(fixtures, [synthetic_quote(team_a="Falcons", team_b="BETBOOM",
                                                    decimal_a=1.30, decimal_b=3.60)])["open"][0]
        self.assertIn("shrunk 25%", one["final"]["basis"])
        market = model.no_vig_from_decimal(1.30, 3.60)[0]
        modelled = model.logistic(1843 - 1596, one["vrs"]["scale_used"])
        self.assertAlmostEqual(one["final"]["prob_a"], 0.75 * market + 0.25 * modelled, places=4)

    def test_model_only_row_is_labelled_and_listed_as_a_limitation(self):
        row = board_from([synthetic_fixture(team_a="Falcons", team_b="BETBOOM")], [])["open"][0]
        self.assertTrue(row["final"]["no_market"])
        self.assertIn("originated from Valve", " ".join(row["limitations"]))
        self.assertIsNotNone(row["pick"]["team"])

    def test_unresolved_rows_never_carry_a_guessed_pick(self):
        row = board_from([synthetic_fixture(team_a="WROTBERRY", team_b="antidaun")], [])["open"][0]
        self.assertTrue(row["unresolved"])
        self.assertIsNone(row["pick"]["team"])
        self.assertIsNone(row["final"]["prob_a"])
        self.assertIn("no book or exchange quote", row["unresolved_reason"])
        self.assertTrue(row["limitations"])

    def test_r2_free_contrarian_fires_only_with_a_real_edge(self):
        fixtures = [synthetic_fixture(team_a="NIP", team_b="HEROIC", crowd_a=22, crowd_b=78)]
        quotes = [synthetic_quote(decimal_a=1.60, decimal_b=2.35)]       # NIP ~57% but crowd is on HEROIC
        row = board_from(fixtures, quotes)["open"][0]
        self.assertEqual(row["pick"]["team"], "NIP")
        self.assertTrue(row["pick"]["rule"].startswith("R2"))
        self.assertIn("flat points", row["pick"]["reason"])

        aligned = board_from([synthetic_fixture(crowd_a=78, crowd_b=22)], quotes)["open"][0]
        self.assertTrue(aligned["pick"]["rule"].startswith("R1"))

        thin = board_from([synthetic_fixture(crowd_a=45, crowd_b=55)],
                          [synthetic_quote(decimal_a=1.95, decimal_b=1.85)])["open"][0]
        self.assertFalse(thin["pick"]["rule"].startswith("R2"))

    def test_r5_tie_break_prefers_the_crowd_favourite_only_in_a_coin_flip(self):
        coin = board_from([synthetic_fixture(team_a="NIP", team_b="HEROIC", crowd_a=70, crowd_b=30)],
                          [synthetic_quote(decimal_a=1.90, decimal_b=1.90)])["open"][0]
        self.assertTrue(coin["pick"]["rule"].startswith("R5"))
        self.assertEqual(coin["pick"]["team"], "NIP")
        clear = board_from([synthetic_fixture(team_a="NIP", team_b="HEROIC", crowd_a=70, crowd_b=30)],
                           [synthetic_quote(decimal_a=1.50, decimal_b=2.60)])["open"][0]
        self.assertFalse(clear["pick"]["rule"].startswith("R5"))

    def test_r3_needs_two_verified_flags_points_and_value_and_is_capped(self):
        fixtures = [synthetic_fixture(fixture_id=str(i), team_a="Aurora", team_b="FURIA",
                                      crowd_a=80, crowd_b=20, offered=3) for i in range(1, 4)]
        # our model rates Aurora above 30% but below 50%, the market rates them lower still,
        # and research.CONTEXT_FLAGS carries four verified Aurora facts.
        quotes = [synthetic_quote(team_a="Aurora", team_b="FURIA", decimal_a=2.90, decimal_b=1.40)]
        board = board_from(fixtures, quotes * 3)
        r3 = [r for r in board["open"] if r["pick"]["rule"].startswith("R3")]
        self.assertLessEqual(len(r3), 2)
        for row in r3:
            self.assertGreaterEqual(len(row["context_flags"]), 2)
            self.assertGreaterEqual(row["offered_points"], 3)
            self.assertGreaterEqual(row["pick"]["prob"], 0.30)
            for flag in row["context_flags"]:
                self.assertTrue(flag["sources"], "every context flag must carry a source")
        self.assertEqual(board["r3_uses"]["remaining"], 2 - len(r3))

    def test_context_flags_only_come_from_verified_research_entries(self):
        row = board_from([synthetic_fixture(team_a="Falcons", team_b="BETBOOM")], [])["open"][0]
        self.assertEqual(row["context_flags"], [])
        aurora = board_from([synthetic_fixture(team_a="Aurora", team_b="FURIA")], [])["open"][0]
        self.assertTrue(aurora["context_flags"])
        for flag in aurora["context_flags"]:
            self.assertTrue(all(s.get("url", "").startswith("http") for s in flag["sources"]))

    def test_r4_is_published_but_never_applied(self):
        board = board_from([synthetic_fixture()], [synthetic_quote()])
        self.assertTrue(any(rule["id"] == "R4" for rule in board["rules"]))
        self.assertFalse(any(str(row["pick"]["rule"]).startswith("R4") for row in board["open"]))


class TestBacktest(unittest.TestCase):
    def test_backtest_counts_only_decided_rows_with_a_strong_favourite(self):
        settlement = [
            {"fixture_id": "a", "status": "ended", "team_a": "9z", "team_b": "Aurora",
             "score_a": 2, "score_b": 0, "crowd_a": 7, "crowd_b": 93, "total_picks": 29, "offered_points": 7},
            {"fixture_id": "b", "status": "ended", "team_a": "Falcons", "team_b": "NIP",
             "score_a": 2, "score_b": 0, "crowd_a": 90, "crowd_b": 10, "total_picks": 40, "offered_points": 7},
            {"fixture_id": "c", "status": "cancelled", "team_a": "Legacy", "team_b": "FURIA",
             "score_a": None, "score_b": None, "crowd_a": 30, "crowd_b": 70, "total_picks": 33,
             "offered_points": 7},
        ]
        backtest = model.crowd_backtest(settlement)
        self.assertEqual(backtest["strong_favourite_record"], "1-1")
        self.assertEqual(len(backtest["strong_favourites"]), 2)
        self.assertIn("flat offered_points", backtest["note"])


class TestResearchLedger(unittest.TestCase):
    def test_every_editorial_row_carries_a_source_url(self):
        for row in research.RESULTS:
            self.assertTrue(row["sources"], f"{row['a']} v {row['b']} has no source")
            for label, url in row["sources"]:
                self.assertTrue(url.startswith("http"), url)
                self.assertTrue(label.strip())
        for flag in research.FLAGS:
            self.assertTrue(flag["sources"], flag["id"])
            self.assertIn(flag["severity"], ("high", "medium", "low"))
        for label, url in research.SOURCES_INDEX:
            self.assertTrue(url.startswith("http"), url)

    def test_day1_upset_facts_are_the_verified_ones(self):
        upset = next(r for r in research.RESULTS if r["a"] == "9z" and r["b"] == "Aurora")
        self.assertEqual((upset["sa"], upset["sb"]), (2, 0))
        self.assertEqual((upset["crowd_a"], upset["crowd_b"]), (7, 93))
        self.assertIn("Inferno 13-11", upset["maps"])

    def test_rules_are_unique_and_gated(self):
        ids = [rule["id"] for rule in research.RULES]
        self.assertEqual(ids, ["R1", "R2", "R3", "R4", "R5"])
        for rule in research.RULES:
            self.assertTrue(rule["gate"] and rule["cost"] and rule["text"])
        r4 = next(rule for rule in research.RULES if rule["id"] == "R4")
        self.assertIn("never auto-applied", r4["text"])

    def test_aurora_roster_claim_is_evidenced_and_the_blank_stays_blank(self):
        self.assertEqual(len(research.AURORA["active_five"]), 5)
        self.assertGreaterEqual(len(research.AURORA["five_evidence"]), 2)
        self.assertFalse(research.AURORA["october_change_found"])
        self.assertIn("left blank rather than inferred", research.AURORA["october_change_note"])
        for date, text, url in research.AURORA["change_history"]:
            self.assertTrue(url.startswith("http"))
            self.assertRegex(date, r"^\d{4}-\d{2}-\d{2}$")

    def test_semifinals_are_recorded_as_not_pickable(self):
        for entry in research.DAY4:
            self.assertFalse(entry["hotspawn_pickem_listed"])
            self.assertTrue(entry["polymarket_url"].startswith("https://polymarket.com/event/"))
            self.assertTrue(entry["hltv_url"].startswith("https://www.hltv.org/matches/"))
            self.assertGreaterEqual(len(entry["start_evidence"]), 2)
        flag = next(f for f in research.FLAGS if f["id"] == "F2")
        self.assertIn("not pickable", flag["title"].lower())

    def test_scoring_records_the_official_rules_and_the_absent_ownership_term(self):
        self.assertTrue(any("streak" in rule for rule in research.SCORING["rules"]))
        self.assertTrue(research.SCORING["api_points_absent_fields"])
        for label, offered, base, multipliers in research.SCORING["observed_points"]:
            self.assertIsInstance(offered, int)
            self.assertGreater(offered, 0)
            self.assertIn("tier_multiplier", multipliers)


# ------------------------------------------------------------- rendered artifacts
class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ("href", "src") and value:
                self.urls.append(value)


class TestRenderedPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="17866d06-render-"))
        cls.out = cls.tmp / "picks-day4"
        cls.data = cls.tmp / "data"
        cls.data.mkdir(parents=True)
        board = board_from(
            [synthetic_fixture(fixture_id="1", team_a="NIP", team_b="HEROIC", crowd_a=22, crowd_b=78),
             synthetic_fixture(fixture_id="2", team_a="WROTBERRY", team_b="antidaun", start_epoch=1792240000.0,
                               offered=2, tier="c")],
            [synthetic_quote()])
        board["captured_utc"] = "2026-10-16T23:00:00Z"
        (cls.data / "board.json").write_text(json.dumps(board), encoding="utf-8")
        (cls.tmp / "index.html").write_text("<!-- stub site home so ../index.html resolves -->",
                                            encoding="utf-8")
        (cls.tmp / "day4").mkdir(exist_ok=True)
        (cls.tmp / "day4" / "index.html").write_text("<!-- stub sibling board -->", encoding="utf-8")
        cls.original_data = build.DATA
        build.DATA = cls.data
        cls.pages = build.build(cls.out)

    @classmethod
    def tearDownClass(cls):
        build.DATA = cls.original_data
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def read(self, name):
        return (self.out / name).read_text(encoding="utf-8")

    def test_all_six_pages_render(self):
        self.assertEqual(sorted(self.pages),
                         ["flagged.html", "index.html", "method.html", "picks.html",
                          "twc.html", "unresolved.html"])
        for name in self.pages:
            content = self.read(name)
            self.assertIn("<!DOCTYPE html>", content)
            self.assertIn('name="viewport"', content)
            self.assertIn("Day-4 desk · 17866d06", content)

    def test_every_internal_link_resolves(self):
        for name in self.pages:
            page = self.out / name
            parser = _Links()
            parser.feed(self.read(name))
            for url in parser.urls:
                parsed = urlsplit(url)
                if parsed.scheme or parsed.netloc:
                    continue
                target = page.parent / unquote(parsed.path.split("#")[0])
                self.assertTrue(target.exists(), f"{name} -> {url}")

    def test_executive_summary_links_straight_to_the_picks(self):
        index = self.read("index.html")
        self.assertIn('href="picks.html"', index)
        self.assertIn('href="unresolved.html"', index)
        self.assertIn('href="flagged.html"', index)
        self.assertIn("Unresolved", index)
        self.assertLess(index.index('class="btn good" href="picks.html"'), index.index("Today's picks at a glance"))

    def test_hotspawn_is_never_presented_as_a_probability_source(self):
        for name in self.pages:
            content = self.read(name)
            self.assertNotIn("HotSpawn probability", content)
        self.assertIn("never as a probability input", self.read("index.html"))
        self.assertIn("never a probability input", self.read("method.html"))

    def test_unconfirmed_values_render_blank_and_tagged(self):
        picks = self.read("picks.html")
        self.assertIn("UNVERIFIED", picks)
        unresolved = self.read("unresolved.html")
        self.assertIn("WROTBERRY", unresolved)
        self.assertIn("no pick published", unresolved)
        self.assertIn("UNVERIFIED", unresolved)

    def test_no_python_leakage_into_the_markup(self):
        for name in self.pages:
            markup = re.sub(r"<style>.*?</style>", "", self.read(name), flags=re.S)
            for bad in ("None%", "&amp;amp;", "{'", "'}", "<unresolved>", "Traceback", "nan%", "{esc(", "None pts"):
                self.assertNotIn(bad, markup, f"{name} leaks {bad!r}")
            self.assertNotRegex(markup, r">\s*None\s*<")

    def test_pick_rows_carry_at_least_one_source_link(self):
        picks = self.read("picks.html")
        self.assertIn("example.invalid/line", picks)
        self.assertIn("HotSpawn lobby", picks)
        self.assertIn("fixtures API row", picks)

    def test_mobile_responsive_tables_and_touch_targets(self):
        for name in self.pages:
            content = self.read(name)
            self.assertIn('class="responsive"', content, name)
            self.assertIn("data-label=", content, name)
            self.assertIn("min-height:46px", content, name)
            self.assertIn("@media (max-width:680px)", content, name)

    def test_method_page_documents_maths_rules_and_verification(self):
        method = self.read("method.html")
        for needle in ("1/o_a", "90 minutes", "log10(volume)", "R1", "R5", "Verification protocol",
                       "Refresh cadence", "SHA-256"):
            self.assertIn(needle, method)

    def test_flagged_page_publishes_every_flag_with_sources(self):
        flagged = self.read("flagged.html")
        for flag in research.FLAGS:
            self.assertIn(f'id="{flag["id"]}"', flagged)
            self.assertIn(html_escape(flag["title"], quote=True), flagged)
            for label, url in flag["sources"]:
                self.assertIn(html_escape(url, quote=True), flagged)
        self.assertIn("blocks the build, the merge or the deploy", flagged)
        self.assertIn("Flagged for Review", flagged)


class TestCommittedBoard(unittest.TestCase):
    """Runs against the capture CI committed; skips when no capture exists yet."""

    @unittest.skipUnless(HAS_CAPTURE, "no committed capture yet")
    def test_summary_counts_match_the_rows(self):
        summary = BOARD["summary"]
        self.assertEqual(summary["open_fixtures"], len(BOARD["open"]))
        self.assertEqual(summary["resolved"], len([r for r in BOARD["open"] if not r["unresolved"]]))
        self.assertEqual(summary["unresolved"], len([r for r in BOARD["open"] if r["unresolved"]]))
        self.assertEqual(summary["points_available_on_resolved"],
                         sum(r["offered_points"] or 0 for r in BOARD["open"] if not r["unresolved"]))

    @unittest.skipUnless(HAS_CAPTURE, "no committed capture yet")
    def test_every_priced_row_is_reproducible_from_its_quotes(self):
        for row in BOARD["open"]:
            if row["unresolved"]:
                self.assertIsNone(row["pick"]["team"])
                continue
            final = row["final"]
            self.assertTrue(0.0 <= final["prob_a"] <= 1.0)
            self.assertAlmostEqual(final["prob_a"] + final["prob_b"], 1.0, places=3)
            self.assertTrue(final["basis"])
            if row.get("consensus"):
                weighted = sum(q["implied_a"] * q["weight"] for q in row["quotes"] if q.get("implied_a"))
                total = sum(q["weight"] for q in row["quotes"] if q.get("implied_a"))
                self.assertAlmostEqual(row["consensus"]["prob_a"], weighted / total, places=3)
            self.assertAlmostEqual(row["pick"]["expected_points"],
                                   (row["offered_points"] or 0) * row["pick"]["prob"], places=1)

    @unittest.skipUnless(HAS_CAPTURE, "no committed capture yet")
    def test_semifinals_are_not_claimed_as_pickable(self):
        self.assertFalse(BOARD["summary"]["twc_semifinals_pickable"])
        for row in BOARD["twc"]:
            self.assertIn("not pickable", row["not_pickable_evidence"])
            self.assertEqual(row["offered_points"], 0)

    @unittest.skipUnless(HAS_CAPTURE, "no committed capture yet")
    def test_calibration_is_reported_honestly(self):
        calibration = BOARD["calibration"]
        self.assertIn("scale", calibration)
        if calibration["calibrated"]:
            self.assertGreaterEqual(calibration["samples"], model.MIN_CALIBRATION_SAMPLES)
            self.assertLessEqual(calibration["mean_abs_error"], 0.25)
        else:
            self.assertEqual(calibration["scale"], model.SCALE_FALLBACK)

    @unittest.skipUnless(HAS_CAPTURE, "no committed capture yet")
    def test_committed_pages_are_in_sync_with_the_board(self):
        index = (PAGES / "index.html").read_text(encoding="utf-8")
        self.assertIn(str(BOARD["summary"]["open_fixtures"]), index)
        picks = (PAGES / "picks.html").read_text(encoding="utf-8")
        for row in BOARD["open"]:
            if not row["unresolved"] and row["pick"].get("team"):
                self.assertIn(row["pick"]["team"], picks)

    def test_pages_directory_is_committed(self):
        for name in ("index.html", "picks.html", "twc.html", "unresolved.html", "flagged.html", "method.html"):
            self.assertTrue((PAGES / name).is_file(), f"picks-day4/{name} missing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
