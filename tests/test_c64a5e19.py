"""Session c64a5e19 every-match board tests. Offline: uses the committed snapshot."""
import json, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
# Load with unique module names and restore sys.path/sys.modules afterwards, so this file
# never shadows the shared scripts/build.py ("build") or any other session's "core".
import importlib.util  # noqa: E402
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
_here = str(ROOT / "scripts" / "c64a5e19")
sys.path.insert(0, _here)
try:
    core = _load("c64a5e19_core", Path(_here) / "core.py")
    B = _load("c64a5e19_build", Path(_here) / "build.py")
finally:
    sys.path.remove(_here)
    sys.modules.pop("build", None); sys.modules.pop("core", None)

def board():
    snap = json.loads((ROOT / "data" / "f7279a54" / "snapshot.json").read_text())
    return B.build_board(snap, "test")

class TestEveryMatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.b = board()
    def test_every_open_fixture_has_a_row_or_explicit_gap(self):
        s = self.b["summary"]
        self.assertEqual(s["open"], len(self.b["open"]))
        self.assertEqual(s["with_pick"] + s["tier_d_none"], s["open"])
        self.assertEqual(s["tier_c_fallback"], 0)
        self.assertEqual(len({r["fixture_id"] for r in self.b["open"]}), s["open"])
    def test_probabilities_sum_to_one_and_pick_is_higher(self):
        for r in self.b["open"]:
            ln = r["line"]
            if ln is None:
                self.assertIn("no_line_unverified", r["flags"]); continue
            self.assertAlmostEqual(ln["prob_a"] + ln["prob_b"], 1.0, places=3)
            self.assertEqual(ln["pick_prob"], max(ln["prob_a"], ln["prob_b"]))
            self.assertIn(ln["pick_team"], (r["team_a"], r["team_b"]))
    def test_fallback_only_when_no_accepted_market(self):
        for r in self.b["open"]:
            if r["market"]:
                self.assertIsNone(r["model"])
                self.assertAlmostEqual(r["line"]["prob_a"], r["market"]["prob_a"], places=3)
            if r["model"]: self.assertIsNone(r["market"])
    def test_missing_roster_is_never_replaced_by_siblings(self):
        for r in self.b["open"]:
            if "LFO 10" in (r["team_a"], r["team_b"]) and not r["market"]:
                self.assertIsNone(r["line"])
    def test_ambiguous_slot_prices_not_joined(self):
        for r in self.b["open"]:
            if "WROTBERRY" in (r["team_a"], r["team_b"]):
                self.assertIsNone(r["line"])
    def test_every_row_has_source_link(self):
        for r in self.b["open"]:
            self.assertTrue(r["sources"])
            for s in r["sources"]: self.assertTrue(str(s["url"]).startswith("https://"))
    def test_no_hotspawn_crowd_in_board(self):
        self.assertNotIn("picked", json.dumps(self.b).lower().replace("pick'ems", "").replace("picks at a glance", ""))
    def test_alias_evidence(self):
        self.assertNotEqual(core.canon("RoundsGG")[0], core.canon("ROUNDS")[0])
        self.assertNotEqual(core.canon("EA Copenhagen")[0], core.canon("EAC")[0])
        self.assertEqual(core.canon("B8")[0], "b8")  # never collapses to B8 Academy etc.
        self.assertNotEqual(core.canon("B8")[0], core.canon("B8 Academy")[0])
    def test_ticker_is_not_a_verified_kickoff(self):
        self.assertIsNone(B.kalshi_start_from_ticker("KXCS2GAME-26OCT150400EACWBTACADEMY"))
    def test_rendered_pages_exist_and_link_board(self):
        for name in ("index.html", "picks.html", "flagged.html", "method.html"):
            txt = (ROOT / "picks-every-match" / name).read_text()
            self.assertIn("Every-match picks", txt)
            self.assertIn('name="viewport"', txt)
        idx = (ROOT / "picks-every-match" / "index.html").read_text()
        for href in ("picks.html", "flagged.html", "method.html", "../index.html", "../ourline/index.html"):
            self.assertIn(f'href="{href}"', idx)

if __name__ == "__main__": unittest.main()
