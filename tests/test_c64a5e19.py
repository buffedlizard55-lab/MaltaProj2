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
    def test_every_open_fixture_is_accounted_for(self):
        snap = json.loads((ROOT / "data/f7279a54/snapshot.json").read_text())
        now = core.parse_iso(snap["collected_to_utc"])
        expected = {r["fixture_id"] for r in snap["hotspawn"]["fixtures"]
                    if "lobby_page" in r.get("seen_in", []) and r["status"] == "scheduled"
                    and core.parse_iso(r["start_utc"]) > now
                    and core.parse_iso(r.get("lock_utc") or r["start_utc"]) > now}
        self.assertEqual({r["fixture_id"] for r in self.b["open"]}, expected)
        self.assertEqual(self.b["summary"]["open"], len(expected))
        self.assertEqual(self.b["summary"]["with_pick"] + self.b["summary"]["tier_d_none"], len(expected))
    def test_probabilities_sum_to_one_and_pick_is_higher(self):
        for r in self.b["open"]:
            ln = r["line"]
            if not ln:
                self.assertIn("no_line_unverified", r["flags"])
                continue
            self.assertAlmostEqual(ln["prob_a"] + ln["prob_b"], 1.0, places=3)
            self.assertEqual(ln["pick_prob"], max(ln["prob_a"], ln["prob_b"]))
            self.assertIn(ln["pick_team"], (r["team_a"], r["team_b"]))
    def test_fallback_only_when_no_accepted_market(self):
        for r in self.b["open"]:
            if r["market"]:
                self.assertEqual(r["line"]["tier"], "A")
                self.assertEqual(r["line"]["prob_a"], r["market"]["prob_a"])
                self.assertIsNone(r["model"])
            elif r["line"]:
                self.assertEqual(r["line"]["tier"], "B")
                self.assertTrue(r["vrs"]["team_a"] and r["vrs"]["team_b"])
    def test_no_unsupported_slot_or_sibling_estimate(self):
        self.assertEqual(self.b["summary"]["tier_c_fallback"], 0)
        for r in self.b["open"]:
            if r["line"] and r["line"]["basis"] == "model":
                self.assertNotIn("WROTBERRY", (r["team_a"], r["team_b"]))
                self.assertNotIn("LFO 10", (r["team_a"], r["team_b"]))
    def test_every_row_has_source_link(self):
        for r in self.b["open"]:
            self.assertTrue(r["sources"])
            for s in r["sources"]: self.assertTrue(str(s["url"]).startswith("https://"))
    def test_no_hotspawn_crowd_in_board(self):
        self.assertNotIn("picked", json.dumps(self.b).lower().replace("pick'ems", "").replace("picks at a glance", ""))
    def test_alias_evidence(self):
        self.assertEqual(core.canon("RoundsGG")[0], "rounds")
        self.assertEqual(core.canon("EA Copenhagen")[0], "eac")
        self.assertEqual(core.canon("B8")[0], "b8")  # never collapses to B8 Academy etc.
        self.assertNotEqual(core.canon("B8")[0], core.canon("B8 Academy")[0])
    def test_thin_mid_and_ticker_time(self):
        self.assertAlmostEqual(B.thin_mid({"yes_bid_dollars": "0.40", "yes_ask_dollars": "0.60"}), 0.5)
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
