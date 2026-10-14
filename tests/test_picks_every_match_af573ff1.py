"""Tests for the EVERY-MATCH board (session af573ff1).

Unit tests of the fallback maths/joins plus invariants over the published
artifacts (data/af573ff1/board.json and picks-every-match/*.html) when present:
every open fixture has a pick, featured lines are copied verbatim, fallback
levels are only used where the featured board publishes no line, and every row
carries at least one external source link.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_HERE = str(ROOT / "scripts" / "af573ff1")


def _load(name, filename):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, str(Path(_HERE) / filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, _HERE)
try:
    core = _load("everymatch_core", "core.py")
    sys.modules["core"] = core  # build.py does `import core`
    build = _load("everymatch_build", "build.py")
finally:
    while _HERE in sys.path:
        sys.path.remove(_HERE)
    sys.modules.pop("core", None)

BOARD = ROOT / "data" / "af573ff1" / "board.json"
FEATURED = ROOT / "data" / "f7279a54" / "board.json"
SITE = ROOT / "picks-every-match"


class MathsAndJoins(unittest.TestCase):
    def test_placeholder_rejected(self):
        self.assertIsNone(core.no_vig(1.8, 1.8))
        self.assertIsNotNone(core.no_vig(1.62, 2.107))

    def test_no_vig_sums_to_one(self):
        nv = core.no_vig(2.0, 1.727)
        self.assertAlmostEqual(nv["prob_a"] + nv["prob_b"], 1.0)

    def test_alias_identity(self):
        self.assertTrue(core.same_team("WhiteBIT Team", "WROTBERRY")[0])
        self.assertTrue(core.same_team("WBT", "WROTBERRY")[0])
        self.assertTrue(core.same_team("Rounds", "RoundsGG")[0])
        self.assertTrue(core.same_team("EA Copenhagen", "EAC")[0])
        # Different rosters of the same numbered stack are never aliased.
        self.assertFalse(core.same_team("LFO 9", "LFO 10")[0])
        self.assertFalse(core.same_team("B8", "B8 Academy")[0])

    def test_alias_join_requires_opponent_and_time(self):
        fx = {"team_a": "WROTBERRY", "team_b": "ENCE", "start_utc": "2026-10-15T12:00:00Z"}
        q = {"team_a": "WhiteBIT Team", "team_b": "ENCE", "start_utc": "2026-10-15T12:00:00Z",
             "prob_a": 0.5653}
        j = core.match_quote(fx, q)
        self.assertIsNotNone(j)
        self.assertFalse(j["swapped"])
        self.assertTrue(j["alias_notes"])
        far = dict(q, start_utc="2026-10-16T12:00:00Z")
        self.assertIsNone(core.match_quote(fx, far))
        one_side = dict(q, team_b="HAVU")
        self.assertIsNone(core.match_quote(fx, one_side))

    def test_vrs_curve(self):
        self.assertAlmostEqual(core.vrs_prob(1000, 1000, 0.3646), 0.5)
        self.assertGreater(core.vrs_prob(1201, 548, 0.3646), 0.5)

    def test_single_rating_is_shrunk_and_clamped(self):
        p = core.single_rating_prob(2046, 381, 0.3646, True)
        self.assertLessEqual(p, core.SINGLE_RATING_CLAMP[1])
        self.assertGreaterEqual(p, 0.5)
        p2 = core.single_rating_prob(2046, 381, 0.3646, False)
        self.assertAlmostEqual(p + p2, 1.0)


@unittest.skipUnless(BOARD.exists() and FEATURED.exists(), "board artifacts not present")
class PublishedBoard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = json.loads(BOARD.read_text())
        featured_doc = json.loads(FEATURED.read_text())
        # This board is an archived independent cross-check (see audits/af573ff1/).
        # Once the featured board refreshes past the snapshot this board was built
        # from, verbatim/current-inventory assertions no longer apply to it.
        if featured_doc.get("generated_utc") != cls.board["inputs"].get("featured_board_generated_utc"):
            raise unittest.SkipTest("archived cross-check board: featured board has refreshed since")
        cls.featured = {r["fixture_id"]: r for r in featured_doc["open"]}

    def test_every_open_match_has_a_pick(self):
        s = self.board["summary"]
        self.assertEqual(s["with_pick"] + s["no_information"], s["open"])
        for r in self.board["rows"]:
            z = r["resolution"]
            self.assertTrue(z["pick_team"], r["fixture_id"])
            self.assertAlmostEqual(z["prob_a"] + z["prob_b"], 1.0, places=3)

    def test_featured_lines_verbatim_and_fallback_only_where_blank(self):
        for r in self.board["rows"]:
            f = self.featured.get(r["fixture_id"])
            if f is None:
                continue
            z = r["resolution"]
            if f["line"]:
                self.assertEqual(z["level"], "featured", r["fixture_id"])
                self.assertEqual(z["prob_a"], f["line"]["prob_a"])
                self.assertEqual(z["pick_team"], f["line"]["pick_team"])
            else:
                self.assertNotEqual(z["level"], "featured", r["fixture_id"])

    def test_every_row_has_external_source_link(self):
        for r in self.board["rows"]:
            urls = [s["url"] for s in r["resolution"]["sources"]]
            self.assertTrue(any(u.startswith("http") for u in urls), r["fixture_id"])
            self.assertNotIn("picked_percent", json.dumps(r))

    def test_site_pages_exist_and_are_mobile_first(self):
        for name in ("index.html", "method.html", "flagged.html"):
            text = (SITE / name).read_text()
            self.assertIn('name="viewport"', text)
            self.assertIn('href="../', text)  # in-site navigation links exist
        index = (SITE / "index.html").read_text()
        self.assertIn("Executive summary", index)
        self.assertIn('href="#picks"', index)
        self.assertIn("../ourline/index.html", index)
        for r in self.board["rows"]:
            self.assertIn(f'id="m-{r["fixture_id"]}"', index)


if __name__ == "__main__":
    unittest.main()
