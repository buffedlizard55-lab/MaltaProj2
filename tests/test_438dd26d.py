"""Tests for session 438dd26d (gap audit + TWC Day-5 re-read). Run: python3 -m unittest tests/test_438dd26d.py"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "438dd26d"))
import build as B  # noqa: E402

BOARD = json.loads((ROOT / "data/fe803b80/board.json").read_text())
INPUTS = json.loads((ROOT / "data/438dd26d/inputs.json").read_text())
AUDIT = json.loads((ROOT / "data/438dd26d/audit.json").read_text())
HTML = (ROOT / "audits/438dd26d/index.html").read_text()


class Formulas(unittest.TestCase):
    def test_no_vig_matches_board_day5_market(self):
        for fid in ("1080209", "1080210"):
            row = next(r for r in BOARD["open"] if r["fixture_id"] == fid)
            rc = B.recompute_market(row)
            self.assertIsNotNone(rc)
            self.assertLessEqual(abs(rc["prob_a"] - row["market"]["prob_a"]), 1e-4, fid)

    def test_vrs_formula_reproduces_every_board_vrs_row(self):
        k = BOARD["calibration"]["k"]
        n = 0
        for r in BOARD["open"]:
            m = r.get("model") or {}
            if m.get("vrs") and m.get("basis") == "valve_vrs":
                n += 1
                self.assertAlmostEqual(B.vrs_prob(m["vrs"]["points_a"], m["vrs"]["points_b"], k), m["prob_a"], places=9)
        self.assertGreater(n, 0)

    def test_thunderpick_orientation_falcons_and_furia_are_favourites(self):
        self.assertLess(INPUTS["bo3gg_thunderpick_day5"]["1080209"]["Falcons"], INPUTS["bo3gg_thunderpick_day5"]["1080209"]["Aurora"])
        self.assertLess(INPUTS["bo3gg_thunderpick_day5"]["1080210"]["FURIA"], INPUTS["bo3gg_thunderpick_day5"]["1080210"]["BetBoom"])

    def test_betclic_bbl_model_lean_is_bbl(self):
        g = AUDIT["gap_resolutions"]["1081546"]
        self.assertEqual(g["pick"], "BBL")
        self.assertAlmostEqual(g["p_bbl"], 0.5189, places=4)
        self.assertEqual(INPUTS["valve_vrs_2026_10_05"]["rows"]["BBL"]["points"], 1386)
        self.assertEqual(INPUTS["valve_vrs_2026_10_05"]["rows"]["Betclic"]["points"], 1333)


class AuditRows(unittest.TestCase):
    def test_every_open_row_has_pick_or_documented_limitation(self):
        for r in AUDIT["rows"]:
            if r["pick"] is None:
                self.assertIn(r["fixture_id"], AUDIT["gap_resolutions"], r["fixture_id"])
                self.assertTrue(AUDIT["gap_resolutions"][r["fixture_id"]]["attempts"])

    def test_unresolved_chinggis_wxm_has_no_invented_pick(self):
        r = next(x for x in AUDIT["rows"] if x["fixture_id"] == "1081863")
        self.assertIsNone(r["pick"])
        self.assertIsNone(r["prob_team_a"])

    def test_all_rechecks_pass(self):
        for r in AUDIT["rows"]:
            for key, val in r["checks"].items():
                self.assertNotEqual(val, False, (r["fixture_id"], key))

    def test_every_source_url_is_https(self):
        urls = re.findall(r'"(https?://[^"]+)"', json.dumps(INPUTS))
        self.assertTrue(urls)
        for u in urls:
            self.assertTrue(u.startswith("https://"), u)


class Page(unittest.TestCase):
    def test_phone_viewport_and_structure(self):
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1"', HTML)
        for section in ("1. TWC final-day picks", "2. Gap resolution", "3. Flagged for review", "4. Every open fixture"):
            self.assertIn(section, HTML)

    def test_page_never_uses_hotspawn_crowd_percentages(self):
        self.assertNotIn("picked</", HTML)
        self.assertNotIn("% picked", HTML)

    def test_every_pick_card_has_a_source_link(self):
        cards = re.split(r'<div class="card', HTML)[1:]
        for c in cards:
            if "PICK:" in c:
                self.assertIn('href="https://', c)

    def test_every_local_href_resolves_on_disk(self):
        base = ROOT / "audits" / "438dd26d"
        hrefs = re.findall(r'href="([^"]+)"', HTML)
        local = [h for h in hrefs if not h.startswith(("https://", "#", "mailto:"))]
        self.assertTrue(local)
        for h in local:
            self.assertTrue((base / h).resolve().exists(), h)

    def test_nav_targets_exist_on_disk(self):
        for rel in ("../../start/index.html", "../../start/unresolved.html", "../../start/flagged.html"):
            self.assertTrue((ROOT / "audits/438dd26d" / rel).resolve().exists(), rel)


if __name__ == "__main__":
    unittest.main()
