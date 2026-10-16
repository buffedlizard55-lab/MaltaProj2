"""Contract and verification tests for Session 98dcfc7e deliverables."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "audits" / "98dcfc7e"
DATA_FILE = ROOT / "data" / "98dcfc7e" / "audit.json"


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_98dcfc7e", ROOT / "scripts" / "98dcfc7e" / "build.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSession98dcfc7e(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = load_builder()
        cls.live_audit = cls.builder.build_audit()
        cls.saved_audit = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        cls.board = json.loads((ROOT / "data" / "c64a5e19" / "board.json").read_text(encoding="utf-8"))
        cls.pages = [
            "index.html",
            "twc.html",
            "unresolved.html",
            "flagged.html",
            "methodology.html",
        ]

    def test_zero_quote_vrs_and_crowd_mismatches(self):
        s = self.live_audit["summary"]
        self.assertEqual(s["quote_mismatches"], [])
        self.assertEqual(s["vrs_mismatches"], [])
        self.assertEqual(s["crowd_leak_mismatches"], [])
        self.assertEqual(s["open_fixtures"], len(self.board["open"]))
        self.assertEqual(
            s["directional_picks"] + s["priced_ties"] + s["blank_rows"],
            s["open_fixtures"],
        )

    def test_every_open_row_normalized_and_crowd_isolated(self):
        for r in self.live_audit["open_rows"]:
            fid = r["fixture_id"]
            if r["prob_a"] is None:
                self.assertIsNone(r["prob_b"], fid)
                self.assertIsNone(r["pick_team"], fid)
                self.assertEqual(r["tier_code"], "D", fid)
            else:
                self.assertAlmostEqual(r["prob_a"] + r["prob_b"], 1.0, places=6, msg=fid)
                self.assertAlmostEqual(r["prob_a"], r["rederived_prob_a"], places=3, msg=fid)
                if r["is_priced_tie"]:
                    self.assertIsNone(r["pick_team"], fid)
                    self.assertEqual(r["prob_a"], 0.5, fid)
                else:
                    expected = r["team_a"] if r["prob_a"] > r["prob_b"] else r["team_b"]
                    self.assertEqual(r["pick_team"], expected, fid)

    def test_twc_day1_day2_and_day3_deciders_verified(self):
        twc = self.live_audit["twc_2026"]
        self.assertEqual(len(twc["day1_results"]), 4)
        self.assertEqual(len(twc["day2_results"]), 4)
        self.assertEqual(len(twc["aurora_roster"]), 4)
        self.assertEqual(len(twc["day3_deciders"]), 2)
        d3_by_id = {d["fixture_id"]: d for d in twc["day3_deciders"]}
        self.assertIn("1080205", d3_by_id)
        self.assertIn("1081775", d3_by_id)
        self.assertEqual(d3_by_id["1080205"]["safe_pick"], "Aurora")
        self.assertEqual(d3_by_id["1080205"]["contrarian_candidate"], "9z")
        self.assertEqual(d3_by_id["1081775"]["safe_pick"], "Legacy")
        self.assertEqual(d3_by_id["1081775"]["contrarian_candidate"], "BetBoom")

    def test_pages_mobile_friendly_and_every_table_row_has_official_https_link(self):
        for page_name in self.pages:
            path = AUDIT_DIR / page_name
            self.assertTrue(path.is_file(), f"Missing {path}")
            soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
            vp = soup.select_one('meta[name="viewport"]')
            self.assertIsNotNone(vp, page_name)
            self.assertIn("width=device-width", vp.get("content", ""), page_name)
            skip = soup.select_one("a.skip-link")
            self.assertIsNotNone(skip, page_name)
            self.assertEqual(skip.get("href"), "#main-content", page_name)
            rows = soup.select("tbody tr")
            self.assertGreater(len(rows), 0, page_name)
            for idx, tr in enumerate(rows):
                https_links = [
                    a["href"]
                    for a in tr.select("a[href]")
                    if a["href"].startswith("https://")
                ]
                self.assertGreater(
                    len(https_links), 0, f"{page_name} row {idx} missing https:// link"
                )
                for td in tr.select("td"):
                    self.assertTrue(
                        bool(td.get("data-label")),
                        f"{page_name} row {idx} td missing data-label",
                    )

    def test_internal_links_resolve(self):
        for page_name in self.pages:
            path = AUDIT_DIR / page_name
            soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
            for a in soup.select("a[href]"):
                href = a["href"].strip()
                if not href or href.startswith(("https://", "http://", "mailto:", "#")):
                    continue
                rel = href.split("#", 1)[0]
                if not rel:
                    continue
                target = (AUDIT_DIR / rel).resolve()
                self.assertTrue(target.exists(), f"Broken link {href} in {page_name}")


if __name__ == "__main__":
    unittest.main()
