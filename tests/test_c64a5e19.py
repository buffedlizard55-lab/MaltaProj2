"""Session c64a5e19 every-match board tests. Offline: uses the committed snapshot."""
import json, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "c64a5e19"))
import core  # noqa: E402
import build as B  # noqa: E402

def board():
    snap = json.loads((ROOT / "data" / "f7279a54" / "snapshot.json").read_text())
    return B.build_board(snap, "test")

class TestEveryMatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.b = board()
    def test_every_open_fixture_has_a_pick(self):
        self.assertEqual(self.b["summary"]["open"], 28)
        self.assertEqual(self.b["summary"]["with_pick"], 28)
        self.assertEqual(self.b["summary"]["tier_d_none"], 0)
    def test_probabilities_sum_to_one_and_pick_is_higher(self):
        for r in self.b["open"]:
            ln = r["line"]; self.assertIsNotNone(ln)
            self.assertAlmostEqual(ln["prob_a"] + ln["prob_b"], 1.0, places=3)
            self.assertEqual(ln["pick_prob"], max(ln["prob_a"], ln["prob_b"]))
            self.assertIn(ln["pick_team"], (r["team_a"], r["team_b"]))
    def test_fallback_only_when_no_accepted_market(self):
        for r in self.b["open"]:
            if r["line"]["tier"] == "C": self.assertIsNone(r["market"])
            if r["market"]: self.assertIn(r["line"]["tier"], ("A", "B"))
    def test_fallback_fixtures_are_the_six_previously_unpicked(self):
        c = {r["fixture_id"] for r in self.b["open"] if r["line"]["tier"] == "C"}
        # WROTBERRY x3 slot + FORZE sibling; RoundsGG x2 resolve via documented ROUNDS alias (B, flagged)
        self.assertEqual(c, {"1079624", "1080279", "1080281", "1080283"})
        b_alias = {r["fixture_id"] for r in self.b["open"] if any(f.startswith("alias_used:RoundsGG") for f in r["flags"])}
        self.assertEqual(b_alias, {"1080286", "1080289", "1080288"})
    def test_expected_fallback_picks(self):
        picks = {r["fixture_id"]: r["line"]["pick_team"] for r in self.b["open"]}
        self.assertEqual(picks["1079624"], "FORZE Reload")
        self.assertEqual(picks["1080279"], "EAC")
        self.assertEqual(picks["1080281"], "WROTBERRY")
        self.assertEqual(picks["1080283"], "WROTBERRY")
        self.assertEqual(picks["1080286"], "HAVU")
        self.assertEqual(picks["1080289"], "Voca")
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
        self.assertIsNotNone(B.kalshi_start_from_ticker("KXCS2GAME-26OCT150400EACWBTACADEMY"))
    def test_rendered_pages_exist_and_link_board(self):
        for name in ("index.html", "picks.html", "flagged.html", "method.html"):
            txt = (ROOT / "picks-every-match" / name).read_text()
            self.assertIn("Every-match picks", txt)
            self.assertIn('name="viewport"', txt)
        idx = (ROOT / "picks-every-match" / "index.html").read_text()
        for href in ("picks.html", "flagged.html", "method.html", "../index.html", "../ourline/index.html"):
            self.assertIn(f'href="{href}"', idx)

if __name__ == "__main__": unittest.main()
