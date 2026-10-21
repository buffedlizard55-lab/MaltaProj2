#!/usr/bin/env python3
"""Comprehensive end-to-end contract & mathematical audit tests for session 7adc7718."""
from __future__ import annotations

import json
import math
import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "7adc7718"
LOBBY_DIR = ROOT / "lobby"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "lobby-7adc7718.yml"

EXPECTED_PAGES = (
    "index.html",
    "picks.html",
    "featured.html",
    "low-tier.html",
    "unresolved.html",
    "flagged.html",
    "inventory.html",
    "methodology.html",
)
WEIGHTS = {"pinnacle": 2.0, "bovada": 1.0, "melbet": 1.0, "thunderpick": 1.0, "kalshi": 1.0}


class Test7adc7718Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads((DATA_DIR / "raw_snapshot.json").read_text(encoding="utf-8"))
        cls.ledger = json.loads((DATA_DIR / "research_ledger.json").read_text(encoding="utf-8"))
        cls.board = json.loads((DATA_DIR / "board.json").read_text(encoding="utf-8"))
        cls.audit = json.loads((DATA_DIR / "repo_audit.json").read_text(encoding="utf-8"))
        cls.pages = {name: (LOBBY_DIR / name).read_text(encoding="utf-8") for name in EXPECTED_PAGES}

    def test_scheduled_workflow_updates_every_four_to_eight_hours(self):
        wf = WORKFLOW_PATH.read_text(encoding="utf-8")
        m = re.search(r"cron:\s*['\"]([^'\"]+)['\"]", wf)
        self.assertIsNotNone(m, "Scheduled cron trigger must exist")
        fields = m.group(1).split()
        self.assertEqual(len(fields), 5)
        self.assertTrue(fields[1].startswith("*/"))
        interval_hours = int(fields[1].split("/")[1])
        self.assertGreaterEqual(interval_hours, 4)
        self.assertLessEqual(interval_hours, 8)
        self.assertIn("workflow_dispatch:", wf)

    def test_zero_hotspawn_crowd_percentage_contamination(self):
        for script_name in ("collect.py", "resolve.py"):
            src = (ROOT / "scripts" / "7adc7718" / script_name).read_text(encoding="utf-8")
            self.assertNotIn("pickedPercent", src)
            self.assertNotIn("crowd_prob", src)
        for row in self.board["matches"]:
            cd = row.get("crowd_display_only")
            if cd is not None:
                self.assertFalse(cd["used_in_probability"])
                if row["prob_a"] is not None:
                    self.assertNotAlmostEqual(
                        row["prob_a"], cd["crowd_a_pct"] / 100.0, places=3,
                        msg=f"{row['fixture_id']} matches crowd share too closely without independent math",
                    )

    def test_every_open_match_is_accounted_for_and_sums_to_one_or_is_blank(self):
        s = self.board["summary"]
        self.assertEqual(s["open_matches"], len(self.board["matches"]))
        self.assertEqual(
            s["featured_market"] + s["rescue_exchange"] + s["rescue_vrs_model"] + s["unresolved_blank"],
            s["open_matches"],
        )
        for row in self.board["matches"]:
            with self.subTest(fixture=row["fixture_id"]):
                if row["resolution_tier"] == "unresolved_blank":
                    self.assertIsNone(row["prob_a"])
                    self.assertIsNone(row["prob_b"])
                    self.assertIsNone(row["pick"])
                    self.assertTrue(row["flag_ids"], "Unverified blank row must be flagged")
                else:
                    self.assertGreater(row["prob_a"], 0.0)
                    self.assertLess(row["prob_a"], 1.0)
                    self.assertAlmostEqual(row["prob_a"] + row["prob_b"], 1.0, places=6)
                    expected_pick = row["team_a"] if row["prob_a"] > row["prob_b"] else row["team_b"]
                    self.assertEqual(row["pick"], expected_pick)

    def test_independent_re_derivation_of_book_quotes_and_vrs_slope(self):
        cal = self.board["calibration"]
        pairs = cal["pairs"]
        sxx = sum(p["delta_points"] ** 2 for p in pairs)
        sxy = sum(p["delta_points"] * p["logit"] for p in pairs)
        expected_beta = min(0.0040, max(0.0008, sxy / sxx))
        self.assertAlmostEqual(cal["beta"], expected_beta, places=7)

        for row in self.board["matches"]:
            tier = row["resolution_tier"]
            if tier in ("featured_market", "rescue_exchange"):
                quotes = row["quotes"]
                self.assertTrue(quotes)
                for q in quotes:
                    da, db = q["decimal_a"], q["decimal_b"]
                    p_q = (1.0 / da) / ((1.0 / da) + (1.0 / db))
                    self.assertAlmostEqual(p_q, q["no_vig_prob_a"], places=5)
                wsum = sum(WEIGHTS.get(q["source_key"], 1.0) for q in quotes)
                expected_pa = sum(WEIGHTS.get(q["source_key"], 1.0) * q["no_vig_prob_a"] for q in quotes) / wsum
                self.assertAlmostEqual(row["prob_a"], expected_pa, places=5)
            elif tier == "rescue_vrs_model":
                delta = row["vrs_a"]["points"] - row["vrs_b"]["points"]
                expected_pa = 1.0 / (1.0 + math.exp(-cal["beta"] * delta))
                self.assertAlmostEqual(row["prob_a"], expected_pa, places=5)

    def test_zetta_vs_los_ninos_blank_and_ghost_1080200_quarantined(self):
        by_id = {r["fixture_id"]: r for r in self.board["matches"]}
        if "1082837" in by_id:
            z = by_id["1082837"]
            self.assertIsNone(z["prob_a"])
            self.assertIsNone(z["pick"])
            self.assertIn("F-01", z["flag_ids"])
        self.assertNotIn("1080200", by_id, "Concluded API ghost 1080200 must never appear as open")
        inv_by_id = {r["fixture_id"]: r for r in self.board["inventory"]}
        if "1080200" in inv_by_id:
            self.assertEqual(inv_by_id["1080200"]["state"], "flagged_api_ghost")

    def test_mobile_ui_executive_summary_and_every_row_source_links(self):
        exec_html = self.pages["index.html"]
        for subpage in ("picks.html", "featured.html", "low-tier.html", "unresolved.html", "flagged.html", "inventory.html"):
            self.assertIn(f'href="{subpage}"', exec_html)
        self.assertIn('id="exec-unresolved"', exec_html)
        self.assertIn("Unresolved Picks &amp; Limitations", exec_html)

        for name, html_text in self.pages.items():
            with self.subTest(page=name):
                self.assertIn('name="viewport" content="width=device-width, initial-scale=1"', html_text)
                self.assertEqual(len(re.findall(r"<h1\b", html_text)), 1)
                for row_match in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", html_text, re.S):
                    body = row_match.group(1)
                    if "<th" in body:
                        continue
                    self.assertRegex(body, r'href="(https://[^"]+|picks\.html#m-\d+)"')
                for href in re.findall(r'href="([^"#]+)"', html_text):
                    parsed = urlsplit(href)
                    if parsed.scheme or parsed.netloc or not parsed.path:
                        continue
                    target = (LOBBY_DIR / unquote(parsed.path)).resolve()
                    self.assertTrue(target.exists(), f"Broken local link {href} on lobby/{name}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
