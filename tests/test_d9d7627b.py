"""Tests for the HotSpawn CS2 every-match picks pipeline (session d9d7627b).

Offline only: odds maths, strict name joining, the VRS model fit, the resolution chain,
and the live-collector parsers replayed against real recorded API payloads committed by
session f7279a54 (`data/f7279a54/source_payloads.json`).
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import importlib.util as _ilu, sys as _sys
from pathlib import Path as _Path
def _load_d9(name):
    key = f"d9d7627b_{name}"
    if key in _sys.modules:
        return _sys.modules[key]
    p = _Path(__file__).resolve().parent / f"{name}.py" if (_Path(__file__).resolve().parent / f"{name}.py").exists() else _Path(__file__).resolve().parents[1] / "scripts" / "d9d7627b" / f"{name}.py"
    spec = _ilu.spec_from_file_location(key, p)
    mod = _ilu.module_from_spec(spec)
    _sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod

core = _load_d9('core')
collect = _load_d9('collect')
resolve_mod = _load_d9('resolve')

PAYLOADS = ROOT / "data" / "f7279a54" / "source_payloads.json"
SEED_SNAPSHOT = ROOT / "data" / "f7279a54" / "snapshot.json"
BOARD = ROOT / "data" / "d9d7627b" / "board.json"


class TestOddsMath(unittest.TestCase):
    def test_no_vig_even(self):
        nv = core.no_vig(1.90, 1.90)
        self.assertAlmostEqual(nv["prob_a"], 0.5, places=9)
        self.assertAlmostEqual(nv["overround"], 2 / 1.9 - 1, places=9)

    def test_no_vig_rejects_bad(self):
        self.assertIsNone(core.no_vig(1.0, 2.0))
        self.assertIsNone(core.no_vig("x", 2.0))
        self.assertIsNone(core.no_vig(50.0, 50.0))  # book sum far below plausible

    def test_american_round_trip(self):
        for am, dec in [(-110, 1.9090909), (150, 2.5), (-812, 1.12315)]:
            self.assertAlmostEqual(core.american_to_decimal(am), dec, places=4)
        self.assertEqual(core.decimal_to_american(2.5), 150)
        self.assertEqual(core.decimal_to_american(1.9090909), -110)

    def test_median_consensus(self):
        entries = [{"source_key": "a", "prob_a": 0.40},
                   {"source_key": "b", "prob_a": 0.60},
                   {"source_key": "c", "prob_a": 0.55}]
        c = core.consensus(entries)
        self.assertEqual(c["prob_a"], 0.55)
        self.assertAlmostEqual(c["prob_a"] + c["prob_b"], 1.0)


class TestNames(unittest.TestCase):
    def test_strict_no_prefix(self):
        self.assertFalse(core.same_team("B8", "B8 Academy")[0])
        self.assertFalse(core.same_team("WBT", "WROTBERRY")[0])
        self.assertFalse(core.same_team("Spirit", "Spirit Academy")[0])

    def test_generic_words_and_case(self):
        self.assertTrue(core.same_team("Team Falcons", "Falcons")[0])
        self.assertTrue(core.same_team("FURIA Esports", "furia")[0])
        self.assertTrue(core.same_team("Aurora Gaming", "Aurora")[0])

    def test_alias(self):
        ok, notes = core.same_team("BB Team", "BetBoom")
        self.assertTrue(ok)
        self.assertTrue(notes)

    def test_word_order_variant(self):
        ok, notes = core.same_team("Apogee Betclic", "Betclic Apogee")
        self.assertTrue(ok)
        self.assertTrue(any("word-order" in n for n in notes))


def _fx(a="Alpha", b="Bravo", start="2026-10-21T14:00:00Z"):
    return {"fixture_id": "1", "team_a": a, "team_b": b, "start_utc": start,
            "competition": "Cup", "status": "scheduled", "lock_utc": start}


def _q(a="Alpha", b="Bravo", start="2026-10-21T14:00:00Z", da=1.8, db=2.0, **kw):
    nv = core.no_vig(da, db)
    return {"source_key": "pinnacle", "source_name": "Pinnacle", "public_url": "https://x",
            "api_url": "https://x", "event_id": "9", "team_a": a, "team_b": b,
            "decimal_a": da, "decimal_b": db, "raw_format": "decimal",
            "raw_a": da, "raw_b": db, "prob_a": nv["prob_a"],
            "overround": nv["overround"], "start_utc": start, "league": "CS2",
            "live": False, "retrieved_utc": "2026-10-21T12:00:00Z", **kw}


class TestJoining(unittest.TestCase):
    def test_join_within_30min(self):
        info = core.match_quote(_fx(), _q(start="2026-10-21T14:25:00Z"))
        self.assertIsNotNone(info)
        self.assertNotIn("rejected", info)
        self.assertTrue(info["loose_time"])

    def test_reject_over_30min(self):
        info = core.match_quote(_fx(), _q(start="2026-10-21T16:00:00Z"))
        self.assertTrue(info["rejected"])
        self.assertIn("differs", info["reason"])

    def test_reject_no_start(self):
        info = core.match_quote(_fx(), _q(start=None, start_is_approx=True))
        self.assertTrue(info["rejected"])

    def test_swap_orientation(self):
        info = core.match_quote(_fx(), _q(a="Bravo", b="Alpha"))
        self.assertTrue(info["swapped"])
        p = core.oriented_prob(_q(a="Bravo", b="Alpha"), True)
        self.assertAlmostEqual(p, 1 - core.no_vig(1.8, 2.0)["prob_a"])


class TestVrsModel(unittest.TestCase):
    def test_prob_monotone_and_capped(self):
        self.assertEqual(core.vrs_prob(1000, 1000, 0.45), 0.5)
        self.assertGreater(core.vrs_prob(1200, 1000, 0.45), 0.5)
        self.assertLessEqual(core.vrs_prob(3000, 100, 0.45), core.MODEL_PROB_MAX)
        self.assertGreaterEqual(core.vrs_prob(100, 3000, 0.45), core.MODEL_PROB_MIN)

    def test_fit_recovers_slope(self):
        pairs = [{"delta": d, "market_prob_a": core.sigmoid(0.5 * core.VALVE_C * d)}
                 for d in (-600, -300, -120, 120, 300, 600, 60, -60)]
        fit = core.fit_calibration(pairs)
        self.assertTrue(fit["fitted"])
        self.assertAlmostEqual(fit["k"], 0.5, places=2)
        self.assertLess(fit["mae_prob"], 0.01)

    def test_fit_requires_min_pairs(self):
        fit = core.fit_calibration([{"delta": 100, "market_prob_a": 0.6}])
        self.assertFalse(fit["fitted"])
        self.assertIsNone(fit["k"])


class TestHotspawnParsing(unittest.TestCase):
    def test_fixture_drops_crowd_fields(self):
        raw = {"id": 42, "sport_alias": "cs2", "participants0_name": "A",
               "participants1_name": "B", "competition_name": "Cup",
               "scheduled_start_time": "1792173600000", "lock_time": "1792173300000",
               "status": "scheduled", "participants0_pick_percentage": 83,
               "participants1_pick_percentage": 17}
        fx = core.fixture_from_hotspawn(raw)
        self.assertIsNotNone(fx)
        self.assertFalse(any("pick" in k and "percent" in k for k in fx))
        self.assertEqual(fx["start_utc"], "2026-10-16T18:00:00Z")

    def test_lobby_state(self):
        state = {"k1": {"u": "https://h/api/v1/fixtures", "b": [{"id": 1}]},
                 "k2": {"u": "https://h/x", "b": {"permalinks": {"1": "https://m/1"}}}}
        html_doc = f'<html><script id="ng-state" type="application/json">{json.dumps(state)}</script></html>'
        out = core.lobby_state(html_doc)
        self.assertEqual(len(out["fixtures"]), 1)
        self.assertEqual(out["permalinks"]["1"], "https://m/1")


def _vrs_index(rows):
    teams = [{"standing": i + 1, "points": p, "team": t, "roster": "r",
              "details_path": "x"} for i, (t, p) in enumerate(rows)]
    return resolve_mod.VrsIndex({"snapshot": "2099_01_01", "page_url": "https://v",
                                 "teams": teams})


FIT_OK = {"fitted": True, "k": 0.45, "n_pairs": 60, "mae_prob": 0.08}
NOW = core.parse_iso("2026-10-21T12:00:00Z")
ACCESS = {k: {"status": 200, "at_utc": "2026-10-21T12:00:00Z", "url": "https://x"}
          for k in ("pinnacle", "bovada", "melbet", "kalshi", "polymarket")}


class TestResolutionChain(unittest.TestCase):
    def _run(self, fx, quotes, vrs_rows):
        return resolve_mod.resolve_fixture(
            fx, quotes, _vrs_index(vrs_rows), FIT_OK, ACCESS,
            {"events": 3, "two_outcome": 1, "with_game_start": 0},
            {"status": 403, "at_utc": "2026-10-21T12:00:00Z"}, NOW)

    def test_market_tier(self):
        res, ev, _ = self._run(_fx(), [_q()], [("Alpha", 1000), ("Bravo", 900)])
        self.assertEqual(res["tier"], "market")
        self.assertAlmostEqual(res["prob_a"] + res["prob_b"], 1.0)
        self.assertEqual(res["pick_team"], "Alpha")

    def test_model_tier(self):
        res, _, _ = self._run(_fx(), [], [("Alpha", 1300), ("Bravo", 800)])
        self.assertEqual(res["tier"], "model")
        self.assertGreater(res["prob_a"], 0.6)
        self.assertTrue(res["limitations"])

    def test_direction_tier_blank_prob(self):
        res, _, _ = self._run(_fx(), [], [("Alpha", 900)])
        self.assertEqual(res["tier"], "direction")
        self.assertEqual(res["pick_team"], "Alpha")
        self.assertIsNone(res["prob_a"])
        self.assertIsNone(res["pick_prob"])

    def test_unresolved_tier(self):
        res, _, _ = self._run(_fx(), [], [])
        self.assertEqual(res["tier"], "unresolved")
        self.assertIsNone(res["pick_team"])
        self.assertGreaterEqual(len(res["limitations"]), 3)

    def test_ambiguous_straddle_unresolved(self):
        res, _, _ = self._run(_fx(), [], [("Alpha", 732), ("Bravo", 801), ("Bravo", 402)])
        self.assertEqual(res["tier"], "unresolved")

    def test_ambiguous_clear_direction(self):
        res, _, _ = self._run(_fx(), [], [("Alpha", 1400), ("Bravo", 801), ("Bravo", 402)])
        self.assertEqual(res["tier"], "direction")
        self.assertEqual(res["pick_team"], "Alpha")


class TestPolymarketParser(unittest.TestCase):
    def test_strict_parser(self):
        payload = [{"slug": "ev1", "title": "CS2 match", "markets": [
            {"id": "m1", "outcomes": '["Alpha", "Bravo"]',
             "outcomePrices": '["0.6", "0.4"]', "gameStartTime": "2026-10-21T14:00:00Z"},
            {"id": "m2", "outcomes": '["Yes", "No"]', "outcomePrices": '["0.5", "0.5"]'},
            {"id": "m3", "outcomes": '["Carol", "Delta"]',
             "outcomePrices": '["0.7", "0.3"]'}]}]
        quotes, stats = collect.parse_polymarket(payload)
        by_id = {q["event_id"]: q for q in quotes}
        self.assertEqual(stats["two_outcome"], 3)
        self.assertEqual(stats["with_game_start"], 1)
        self.assertIn("m1", by_id)
        self.assertFalse(by_id["m1"]["start_is_approx"])
        self.assertNotIn("m2", by_id)  # prop-style outcome names rejected
        self.assertTrue(by_id["m3"]["start_is_approx"])  # no start -> evidence only


@unittest.skipUnless(PAYLOADS.exists() and SEED_SNAPSHOT.exists(),
                     "recorded payloads not committed")
class TestParsersAgainstRecordedPayloads(unittest.TestCase):
    """Replay the live-collector parsers over real API payloads recorded 2026-10-21
    and check they reproduce the prices the previous collector stored."""

    @classmethod
    def setUpClass(cls):
        cls.payloads = json.loads(PAYLOADS.read_text())["sources"]
        cls.seed_quotes = json.loads(SEED_SNAPSHOT.read_text())["quotes"]

    def _seed_by_event(self, source):
        return {q["event_id"]: q for q in self.seed_quotes if q["source_key"] == source}

    def test_bovada(self):
        payload = next(v["payload"] for k, v in self.payloads.items() if "bovada" in k)
        mine = {q["event_id"]: q for q in collect.parse_bovada(payload)}
        seed = self._seed_by_event("bovada")
        self.assertGreater(len(mine), 5)
        for eid, q in seed.items():
            if eid in mine:
                self.assertAlmostEqual(mine[eid]["prob_a"], q["prob_a"], places=3, msg=eid)
        self.assertGreaterEqual(len(set(mine) & set(seed)), len(seed) - 2)

    def test_melbet(self):
        payload = next(v["payload"] for k, v in self.payloads.items() if "melbet" in k)
        mine = {q["event_id"]: q for q in collect.parse_melbet(payload)}
        seed = self._seed_by_event("melbet")
        self.assertGreater(len(mine), 5)
        for eid, q in seed.items():
            if eid in mine:
                self.assertAlmostEqual(mine[eid]["prob_a"], q["prob_a"], places=3, msg=eid)
        self.assertGreaterEqual(len(set(mine) & set(seed)), len(seed) - 2)

    def test_kalshi(self):
        payload = next(v["payload"] for k, v in self.payloads.items() if "kalshi" in k)
        quotes, rejected = collect.parse_kalshi(payload)
        self.assertGreater(len(quotes) + len(rejected), 5)
        for q in quotes:
            self.assertTrue(q["start_is_approx"])

    def test_pinnacle(self):
        matchups_payload = next(v["payload"] for k, v in self.payloads.items()
                                if k.endswith("/sports/12/matchups"))
        matchups = {m["id"]: m for m in collect.parse_pinnacle_matchups(matchups_payload)}
        self.assertGreater(len(matchups), 5)
        seed = self._seed_by_event("pinnacle")
        checked = 0
        for url, rec in self.payloads.items():
            if "/markets/related/straight" not in url:
                continue
            mid = int(url.split("/matchups/")[1].split("/")[0])
            if mid not in matchups:
                continue
            q = collect.parse_pinnacle_markets(matchups[mid], rec["payload"], url)
            if q and q["event_id"] in seed:
                self.assertAlmostEqual(q["prob_a"], seed[q["event_id"]]["prob_a"],
                                       places=3, msg=q["event_id"])
                checked += 1
        self.assertGreaterEqual(checked, 5)


@unittest.skipUnless(BOARD.exists(), "board.json not generated yet")
class TestBoardInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = json.loads(BOARD.read_text())

    def test_every_open_or_locked_row_resolved_into_a_tier(self):
        for r in self.board["rows"]:
            if r["state"] in ("open", "locked"):
                self.assertIsNotNone(r["resolution"], r["fixture_id"])
                self.assertIn(r["resolution"]["tier"],
                              ("market", "model", "direction", "unresolved"))

    def test_probabilities_consistent(self):
        for r in self.board["rows"]:
            res = r.get("resolution") or {}
            if res.get("prob_a") is not None:
                self.assertAlmostEqual(res["prob_a"] + res["prob_b"], 1.0, places=9)
                self.assertIn(res["pick_side"], ("a", "b"))
                expect = r["team_a"] if res["pick_side"] == "a" else r["team_b"]
                self.assertEqual(res["pick_team"], expect)
            if res.get("tier") == "unresolved":
                self.assertIsNone(res.get("pick_team"))
                self.assertTrue(res.get("limitations"))

    def test_no_crowd_data_anywhere(self):
        text = BOARD.read_text()
        self.assertNotIn("pick_percentage", text)
        self.assertNotIn("picked %", text)

    def test_market_rows_rederivable(self):
        for r in self.board["rows"]:
            res = r.get("resolution") or {}
            if res.get("tier") != "market":
                continue
            probs = []
            for q in r["evidence"]["quotes"]:
                rq = core.rederive_quote(q)
                self.assertIsNotNone(rq, q.get("event_id"))
                probs.append(core.oriented_prob(rq, q["swapped"]))
            self.assertAlmostEqual(core.median(probs), res["prob_a"], places=9,
                                   msg=r["fixture_id"])


class TestPublicationBoundary(unittest.TestCase):
    def test_isolated_render_never_overwrites_shared_root(self):
        import subprocess
        before = (ROOT / 'index.html').read_bytes()
        subprocess.run([sys.executable, str(ROOT / 'scripts/d9d7627b/build.py')],
                       check=True, capture_output=True)
        self.assertEqual((ROOT / 'index.html').read_bytes(), before)
        workflow = (ROOT / '.github/workflows/hotspawn-cs2-d9d7627b.yml').read_text()
        self.assertNotIn('git add data/d9d7627b hotspawn-cs2 index.html', workflow)


if __name__ == "__main__":
    unittest.main()
