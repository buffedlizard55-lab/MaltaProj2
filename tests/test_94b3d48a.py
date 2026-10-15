"""Contract and verification tests for Session 94b3d48a:
- Every-match CS2 Pick'em resolution
- Strict source hierarchy (primary bookmakers first; fallback sources invoked ONLY for unresolved primary matches)
- Unresolved Picks & Limitations section
- Line-by-line official source links on every table row and blank cells for unverified strict values
- Mobile-first Executive Summary and 4-hour automated refresh workflow
"""

from __future__ import annotations

import json
import math
import unittest
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = ROOT / "data" / "94b3d48a" / "board.json"
AUDIT_PATH = ROOT / "data" / "94b3d48a" / "audit.json"
AUDIT_DIR = ROOT / "audits" / "94b3d48a"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "refresh-94b3d48a.yml"


class TestSession94b3d48a(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.board = json.loads(BOARD_PATH.read_text(encoding="utf-8"))
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def test_every_open_lobby_match_has_pick_and_normalized_probability(self) -> None:
        open_matches = self.board["open_matches"]
        self.assertGreaterEqual(len(open_matches), 15)
        self.assertEqual(self.board["summary"]["open_lobby_matches"], len(open_matches))
        self.assertEqual(self.board["summary"]["resolved_open_matches"], len(open_matches))
        self.assertFalse(self.board["hotspawn_probability_used"])
        self.assertTrue(self.board["fallback_only_for_unpriced_featured"])

        for row in open_matches:
            res = row["resolution"]
            self.assertIn(res["pick"], (row["team_a"], row["team_b"]))
            self.assertTrue(math.isfinite(res["prob_a"]))
            self.assertTrue(math.isfinite(res["prob_b"]))
            self.assertGreater(res["prob_a"], 0.0)
            self.assertLess(res["prob_a"], 1.0)
            self.assertAlmostEqual(res["prob_a"] + res["prob_b"], 1.0, places=5)
            self.assertAlmostEqual(res["pick_prob"], max(res["prob_a"], res["prob_b"]), places=5)
            expected_pick = row["team_a"] if res["prob_a"] >= res["prob_b"] else row["team_b"]
            self.assertEqual(res["pick"], expected_pick)
            self.assertGreater(res["fair_odds_a"], 1.0)
            self.assertGreater(res["fair_odds_b"], 1.0)

    def test_fallback_sources_used_only_when_featured_primary_unavailable(self) -> None:
        for row in self.board["open_matches"]:
            sp = row["strict_primary"]
            res = row["resolution"]
            if sp["verified"]:
                self.assertEqual(res["tier_code"], "TIER_1_PRIMARY_BOOKMAKER")
                self.assertFalse(res["fallback_invoked"])
                self.assertAlmostEqual(res["prob_a"], sp["prob_a"], places=5)
                self.assertAlmostEqual(res["prob_b"], sp["prob_b"], places=5)
                self.assertEqual(res["pick"], sp["pick"])
            else:
                self.assertIn(
                    res["tier_code"],
                    ("TIER_2_FALLBACK_ESPORTSBOOK", "TIER_3_ORIGINATED_VRS_HLTV"),
                )
                self.assertTrue(res["fallback_invoked"])
                self.assertIsNone(sp["prob_a"])
                self.assertIsNone(sp["prob_b"])
                self.assertIsNone(sp["pick"])
                self.assertTrue(res["limitation"])
                self.assertTrue(res["method"])

    def test_all_open_teams_have_5of5_verified_official_vrs_and_hltv_links(self) -> None:
        self.assertTrue(self.board["summary"]["all_36_lobby_teams_vrs_verified_5of5"])
        for row in self.board["open_matches"]:
            self.assertIsNotNone(row["vrs_a"], f"Missing vrs_a on {row['fixture_id']}")
            self.assertIsNotNone(row["vrs_b"], f"Missing vrs_b on {row['fixture_id']}")
            self.assertTrue(str(row["vrs_a"]["details_url"]).startswith("https://github.com/ValveSoftware/"))
            self.assertTrue(str(row["vrs_b"]["details_url"]).startswith("https://github.com/ValveSoftware/"))
            self.assertTrue(str(row["hltv"]["match_url"]).startswith("https://www.hltv.org/matches/"))

    def test_every_table_row_has_official_https_source_link_and_mobile_viewport(self) -> None:
        for page_name in ("index.html", "unresolved.html", "flagged.html", "methodology.html"):
            page_path = AUDIT_DIR / page_name
            self.assertTrue(page_path.is_file(), f"Missing {page_path}")
            soup = BeautifulSoup(page_path.read_text(encoding="utf-8"), "html.parser")
            self.assertIsNotNone(soup.select_one('meta[name="viewport"]'))
            rows = soup.select("tbody tr")
            self.assertGreater(len(rows), 0, f"No table rows in {page_name}")
            for tr in rows:
                https_links = [
                    a["href"]
                    for a in tr.select("a[href]")
                    if str(a.get("href", "")).startswith("https://")
                ]
                self.assertTrue(
                    len(https_links) > 0,
                    f"Row in {page_name} missing official https:// link: {tr.get_text()}",
                )

    def test_unresolved_page_keeps_strict_column_blank_and_documents_limitations(self) -> None:
        soup = BeautifulSoup((AUDIT_DIR / "unresolved.html").read_text(encoding="utf-8"), "html.parser")
        expected_fallback_ids = {
            r["fixture_id"]
            for r in self.board["open_matches"]
            if r["resolution"]["fallback_invoked"]
        }
        for fid in expected_fallback_ids:
            tr = soup.select_one(f"#u-{fid}")
            self.assertIsNotNone(tr, f"Missing unresolved row #u-{fid}")
            strict_td = tr.find_all("td")[1]
            self.assertIn("—", strict_td.get_text())
        # Completed anomaly 1080200 is also documented with a blank strict cell
        tr_anom = soup.select_one("#u-1080200")
        self.assertIsNotNone(tr_anom)
        self.assertIn("—", tr_anom.find_all("td")[1].get_text())
        self.assertIn("Wildcard 3 : 2 DENDELE", tr_anom.get_text())

    def test_four_hour_refresh_workflow_configured(self) -> None:
        self.assertTrue(WORKFLOW_PATH.is_file())
        wf_text = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("*/4 * * *", wf_text)
        self.assertIn("scripts/94b3d48a/build.py", wf_text)
        self.assertIn("tests/test_94b3d48a.py", wf_text)

    def test_root_executive_summary_and_flagged_link_to_94b3d48a(self) -> None:
        idx_soup = BeautifulSoup((ROOT / "index.html").read_text(encoding="utf-8"), "html.parser")
        self.assertIsNotNone(idx_soup.select_one('#executive-summary a[href="audits/94b3d48a/index.html"]'))
        self.assertIsNotNone(idx_soup.select_one('#executive-summary a[href="audits/94b3d48a/unresolved.html"]'))
        self.assertIsNotNone(idx_soup.select_one('a[href="audits/94b3d48a/flagged.html"]'))
        flg_soup = BeautifulSoup((ROOT / "flagged.html").read_text(encoding="utf-8"), "html.parser")
        self.assertIsNotNone(flg_soup.select_one('a[href="audits/94b3d48a/flagged.html"]'))


if __name__ == "__main__":
    unittest.main()
