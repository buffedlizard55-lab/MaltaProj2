"""Tests for the OURLINE board (session f7279a54).

Unit tests of the pure maths/joins plus invariants over the published artifacts
(data/f7279a54/board.json and ourline/*.html) when they exist.
"""
import json
import math
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_HERE = str(ROOT / "scripts" / "f7279a54")


def _load(name, filename):
    # Load under a unique module name: other suites import scripts/build.py as plain `build`
    # and scripts/collect.py as `collect`, so this test must not leave those names cached.
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, str(Path(_HERE) / filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, _HERE)
try:
    core = _load("ourline_core", "core.py")
    sys.modules["core"] = core          # build.py does `import core`
    build = _load("ourline_build", "build.py")
finally:
    while _HERE in sys.path:
        sys.path.remove(_HERE)
    sys.modules.pop("core", None)

BOARD = ROOT / "data" / "f7279a54" / "board.json"
SITE = ROOT / "ourline"


class Names(unittest.TestCase):
    def test_generic_words_stripped(self):
        self.assertEqual(core.norm("Team Falcons"), core.norm("Falcons"))
        self.assertEqual(core.norm("The Falcons"), "falcons")
        self.assertEqual(core.norm("9z Team"), "9z")
        self.assertEqual(core.norm("FURIA Esports"), "furia")
        self.assertEqual(core.norm("Aurora Gaming"), "aurora")
        self.assertEqual(core.norm("BC.Game"), "bcgame")
        self.assertEqual(core.norm("Honvéd"), "honved")

    def test_academy_never_matches_main_team(self):
        self.assertFalse(core.same_team("B8", "B8 Academy")[0])
        self.assertFalse(core.same_team("MIBR", "MIBR Academy")[0])
        self.assertFalse(core.same_team("Sashi", "Sashi Academy")[0])

    def test_aliases_are_reported(self):
        ok, notes = core.same_team("BB Team", "BetBoom")
        self.assertTrue(ok)
        self.assertTrue(notes)
        self.assertTrue(core.same_team("NIP", "Ninjas in Pyjamas")[0])
        self.assertEqual(core.same_team("Falcons", "Team Falcons"), (True, []))


class OddsMaths(unittest.TestCase):
    def test_american(self):
        self.assertAlmostEqual(core.american_to_decimal(-455), 1 + 100 / 455)
        self.assertAlmostEqual(core.american_to_decimal(280), 3.8)
        self.assertIsNone(core.american_to_decimal(50))
        self.assertEqual(core.decimal_to_american(3.8), 280)
        self.assertEqual(core.decimal_to_american(1.25), -400)

    def test_no_vig(self):
        nv = core.no_vig(1.25, 4.0)
        self.assertAlmostEqual(nv["prob_a"] + nv["prob_b"], 1.0)
        self.assertAlmostEqual(nv["prob_a"], 0.8 / 1.05)
        self.assertIsNone(core.no_vig(1.0, 2.0))
        self.assertIsNone(core.no_vig(3.0, 3.0))  # book < 0.95 is not a plausible two-way market

    def test_consensus_weights(self):
        c = core.consensus([{"source_key": "pinnacle", "prob_a": 0.6}, {"source_key": "bovada", "prob_a": 0.3}])
        self.assertAlmostEqual(c["prob_a"], (2 * 0.6 + 0.3) / 3)
        self.assertAlmostEqual(c["spread_a"], 0.3)
        self.assertIsNone(core.consensus([]))


class ValveModel(unittest.TestCase):
    def test_valve_constants(self):
        # model/glicko.js: Q = ln(10)/400, g = 1/sqrt(1+3 Q^2 RD^2 / pi^2), RD = 75 (model/fit.js)
        q = math.log(10) / 400
        g = 1 / math.sqrt(1 + 3 * q * q * 75 * 75 / math.pi ** 2)
        self.assertAlmostEqual(core.VALVE_G, g)
        self.assertAlmostEqual(core.VALVE_G, 0.97283, places=4)
        expected = 1 / (1 + 10 ** (g * 400 / -400))
        self.assertAlmostEqual(core.vrs_prob(1400, 1000), expected)
        self.assertAlmostEqual(core.vrs_prob(1000, 1000), 0.5)

    def test_calibration_recovers_slope(self):
        pairs = [{"delta": d, "market_prob_a": core.vrs_prob(d, 0, 0.5)} for d in (-500, -300, -100, 100, 250, 400, 600)]
        cal = core.fit_calibration(pairs)
        self.assertTrue(cal["fitted"])
        self.assertAlmostEqual(cal["k"], 0.5, places=6)

    def test_calibration_needs_minimum_pairs(self):
        cal = core.fit_calibration([{"delta": 100, "market_prob_a": 0.6}] * 3)
        self.assertFalse(cal["fitted"])
        self.assertEqual(cal["k"], 1.0)

    def test_blend(self):
        self.assertIsNone(core.blend(None, 0, None))
        self.assertEqual(core.blend(0.7, 1, None)["basis"], "market")
        self.assertEqual(core.blend(None, 0, 0.6)["prob_a"], 0.6)
        b = core.blend(0.7, 3, 0.5)
        self.assertEqual(b["prob_a"], 0.7)
        self.assertEqual(b["basis"], "market")


class HotSpawnParsing(unittest.TestCase):
    PAGE = ('<html><script id="ng-state" type="application/json">' + json.dumps({
        "1": {"b": [{"id": "1", "sport_alias": "cs2", "scheduled_start_time": "1792173600000",
                     "lock_time": "1792173240000", "participants0_name": "A", "participants1_name": "B",
                     "participants0_picked_percent": 90, "participants1_picked_percent": 10,
                     "competition_name": "X", "tier": "c", "offered_points": 2},
                    {"id": "2", "sport_alias": "lol", "scheduled_start_time": "1792173600000",
                     "participants0_name": "C", "participants1_name": "D"}],
              "u": "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures", "s": 200},
        "2": {"b": {"permalinks": {"1": "https://www.hotspawn.com/matches/a-vs-b-x-1",
                                   "9": "https://www.hotspawn.com/matches/9"}},
              "u": "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/admin/gamification/fixtures/permalinks"},
    }) + '</script></html>')

    def test_state_and_crowd_percent_dropped(self):
        st = core.lobby_state(self.PAGE)
        self.assertEqual(len(st["fixtures"]), 2)
        self.assertEqual(st["permalinks"], {"1": "https://www.hotspawn.com/matches/a-vs-b-x-1"})
        fx = [core.fixture_from_hotspawn(f) for f in st["fixtures"]]
        self.assertIsNone(fx[1])  # LoL excluded
        self.assertEqual(fx[0]["start_utc"], "2026-10-16T18:00:00Z")
        self.assertEqual(fx[0]["lock_utc"], "2026-10-16T17:54:00Z")
        self.assertNotIn("picked", json.dumps(fx[0]))

    def test_real_captured_lobby_page_if_present(self):
        page = ROOT / "data" / "live" / "samples" / "lobby_page.txt"
        if not page.exists():
            self.skipTest("captured lobby page not present")
        st = core.lobby_state(page.read_text())
        self.assertGreater(len(st["fixtures"]), 10)
        self.assertTrue(all(core.fixture_from_hotspawn(f) for f in st["fixtures"]
                            if f.get("sport_alias") == "cs2"))


class Joining(unittest.TestCase):
    FX = {"team_a": "FURIA", "team_b": "BetBoom", "start_utc": "2026-10-14T16:00:00Z"}

    def test_swapped_alias_join(self):
        j = core.match_quote(self.FX, {"team_a": "BB Team", "team_b": "FURIA Esports",
                                       "start_utc": "2026-10-14T16:00:00Z", "prob_a": 0.3})
        self.assertTrue(j["swapped"])
        self.assertAlmostEqual(core.oriented_prob({"prob_a": 0.3}, True), 0.7)

    def test_time_window(self):
        self.assertIsNone(core.match_quote(self.FX, {"team_a": "FURIA", "team_b": "BetBoom",
                                                     "start_utc": "2026-10-20T16:00:00Z"}))

    def test_one_team_only_is_not_a_match(self):
        self.assertIsNone(core.match_quote(self.FX, {"team_a": "FURIA", "team_b": "BetBoom Academy",
                                                     "start_utc": "2026-10-14T16:00:00Z"}))


class JoinWindowAndResults(unittest.TestCase):
    FX = {"team_a": "mellren", "team_b": "Privateer", "start_utc": "2026-10-16T14:00:00Z"}

    def test_five_minute_tolerance_and_rejected_join(self):
        q = {"team_a": "Mellren", "team_b": "Privateer Gaming", "start_utc": "2026-10-15T14:00:00Z"}
        j = core.match_quote(self.FX, q)          # same pairing, 24 h earlier -> not joined
        self.assertTrue(j["rejected"])
        self.assertAlmostEqual(j["start_diff_h"], 24.0)
        q["start_utc"] = "2026-10-16T04:00:00Z"   # 10 h -> joined (flagged downstream)
        self.assertTrue(core.match_quote(self.FX, q)["rejected"])

    def test_result_winner(self):
        self.assertEqual(core.result_winner({"status": "ended", "participants0_score": 2,
                                             "participants1_score": 1}), "a")
        self.assertEqual(core.result_winner({"status": "ended", "participants0_score": "0",
                                             "participants1_score": "2"}), "b")
        self.assertIsNone(core.result_winner({"status": "scheduled", "participants0_score": 2,
                                              "participants1_score": 0}))
        self.assertIsNone(core.result_winner({"status": "ended", "participants0_score": 1,
                                              "participants1_score": 1}))
        self.assertIsNone(core.result_winner({"status": "forfeited"}))

    def test_grade_uses_last_published_line_only(self):
        hist = {"1": {"observed_utc": "2026-10-14T07:00:00Z",
                      "line": {"prob_a": 0.7, "pick_team": "A", "pick_side": "a",
                               "pick_prob": 0.7, "basis": "market"}},
                "2": {"observed_utc": "2026-10-14T07:00:00Z",
                      "line": {"prob_a": 0.4, "pick_team": "D", "pick_side": "b",
                               "pick_prob": 0.6, "basis": "model"}}}
        fx = [{"fixture_id": "1", "team_a": "A", "team_b": "B", "start_utc": "x", "winner": "b"},
              {"fixture_id": "2", "team_a": "C", "team_b": "D", "start_utc": "x", "winner": "b"},
              {"fixture_id": "3", "team_a": "E", "team_b": "F", "start_utc": "x", "winner": "a"}]
        track = {}
        s = build.grade(fx, hist, track)
        self.assertEqual(set(track), {"1", "2"})   # no published line -> not graded
        self.assertEqual((s["all"]["n"], s["all"]["correct"]), (2, 1))
        self.assertAlmostEqual(track["1"]["brier"], 0.49)
        self.assertAlmostEqual(track["2"]["brier"], 0.16)
        self.assertEqual(s["by_basis"]["model"]["correct"], 1)


class VrsDuplicates(unittest.TestCase):
    def test_duplicate_never_inferred_from_latest_match(self):
        vrs = {"teams": [
            {"team": "Zomblers", "points": 639, "standing": 254, "latest_match_date": "2026-09-14", "details_path": "a"},
            {"team": "Zomblers", "points": 631, "standing": 259, "latest_match_date": "2026-09-20", "details_path": "b"},
            {"team": "6666", "points": 923, "standing": 127, "latest_match_date": None, "details_path": "c"},
            {"team": "6666", "points": 425, "standing": 368, "latest_match_date": "2026-09-01", "details_path": "d"}]}
        idx, dup = build.rating_index(vrs)
        self.assertNotIn("zomblers", idx)
        self.assertIn("zomblers", dup)
        self.assertIn("6666", dup)
        self.assertEqual(build.rating_for("6666", idx, dup), (None, "ambiguous_vrs_name"))


@unittest.skipUnless(BOARD.exists(), "board not built yet")
class PublishedArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = json.loads(BOARD.read_text())

    def test_no_crowd_pick_percentages_anywhere(self):
        text = BOARD.read_text()
        self.assertNotIn("picked_percent", text)
        self.assertNotIn("pick_pct", text)

    def test_every_open_row_has_official_source_link(self):
        for r in self.board["open"]:
            self.assertRegex(r["hotspawn_url"], r"^https://(play\.hotspawn\.com/lobby|www\.hotspawn\.com/matches/[a-z0-9-]+-\d+)$")
            for q in r.get("quotes", []):
                self.assertTrue(q["public_url"].startswith("https://"))
                self.assertTrue(q["api_url"].startswith("https://"))

    def test_lines_recompute_from_inputs(self):
        for r in self.board["open"]:
            ln = r["line"]
            if not ln:
                self.assertIn("no_line_unverified", r["flags"])
                continue
            mk, md = r.get("market"), r.get("model")
            again = core.blend(mk["prob_a"] if mk else None, mk["n_sources"] if mk else 0,
                               md["prob_a"] if md else None)
            self.assertAlmostEqual(again["prob_a"], ln["prob_a"], places=3)
            self.assertEqual(ln["pick_team"], r["team_a"] if ln["prob_a"] >= 0.5 else r["team_b"])
            if mk:
                vals = [q["no_vig_prob_team_a"] for q in r["quotes"]]
                self.assertTrue(min(vals) - 1e-3 <= mk["prob_a"] <= max(vals) + 1e-3)
            for q in r.get("quotes", []):
                if q["raw_format"] in ("decimal", "american"):
                    nv = core.no_vig(q["decimal_a"], q["decimal_b"])
                    p = 1 - nv["prob_a"] if q["swapped"] else nv["prob_a"]
                    self.assertAlmostEqual(p, q["no_vig_prob_team_a"], places=3)

    def test_open_rows_are_actually_open(self):
        gen = core.parse_iso(self.board["generated_utc"])
        for r in self.board["open"]:
            self.assertGreater(core.parse_iso(r["lock_utc"]), gen)
            self.assertEqual(r["status"], "scheduled")

    def test_rejected_joins_never_feed_the_line(self):
        for r in self.board["open"]:
            rejected = {q["source_key"] for q in r.get("rejected_joins") or []}
            used = {q["source_key"] for q in r["quotes"]}
            self.assertFalse(rejected & used, r["fixture_id"])

    def test_pages_list_every_open_fixture(self):
        index = (SITE / "index.html").read_text()
        for r in self.board["open"]:
            self.assertIn(f'id="m-{r["fixture_id"]}"', index)
        for name in ("index.html", "results.html", "sources.html", "flagged.html", "method.html"):
            self.assertTrue((SITE / name).exists(), name)

    def test_local_links_resolve(self):
        for page in SITE.glob("*.html"):
            for href in re.findall(r'href="([^"#:]+)(?:#[^"]*)?"', page.read_text()):
                self.assertTrue((page.parent / href).resolve().exists(), f"{page.name} -> {href}")


if __name__ == "__main__":
    unittest.main()
