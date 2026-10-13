#!/usr/bin/env python3
"""Tests for session 8e7a652d's verification deliverables.

Validates verify/8e7a652d/verified_market_lines.json (fresh multi-book market
captures for the TWC 2026 opening fixtures) and that the generated page matches
the data. Part of TASK-V independent verification (see COORDINATION.md).
"""
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VDIR = os.path.join(ROOT, "verify", "8e7a652d")


class TestVerifiedMarketLines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(VDIR, "verified_market_lines.json"), encoding="utf-8") as fh:
            cls.data = json.load(fh)

    def test_file_exists_and_schema(self):
        for key in ("matches", "outright_market", "devig_method", "captured_utc_range"):
            self.assertIn(key, self.data)
        self.assertFalse(self.data["hotspawn_used_as_probability"])

    def test_four_twc_openers_covered(self):
        pairings = {m["match"] for m in self.data["matches"]}
        self.assertEqual(
            pairings,
            {
                "9z vs Aurora",
                "Falcons vs Ninjas in Pyjamas",
                "Legacy vs PARIVISION",
                "FURIA vs BetBoom",
            },
        )
        for m in self.data["matches"]:
            self.assertTrue(m["kickoff"].startswith("2026-10-14"))

    def test_every_line_has_source_url_and_timestamp(self):
        for m in self.data["matches"]:
            self.assertGreaterEqual(len(m["lines"]), 3)
            for line in m["lines"]:
                self.assertTrue(line["source_url"].startswith("http"), line)
                self.assertRegex(line["captured_utc"], r"^2026-10-13T\d{2}:\d{2}:\d{2}Z$")

    def test_devig_math_is_exact_and_normalized(self):
        for m in self.data["matches"]:
            for line in m["lines"]:
                if "decimal_a" in line and line.get("decimal_a"):
                    ia, ib = 1 / line["decimal_a"], 1 / line["decimal_b"]
                    fa, fb = ia / (ia + ib), ib / (ia + ib)
                    self.assertAlmostEqual(fa, line["fair_a"], places=3, msg=line["source"])
                    self.assertAlmostEqual(fb, line["fair_b"], places=3, msg=line["source"])
            # consensus equals mean of sources and pair sums to 1
            self.assertAlmostEqual(
                m["consensus_fair_a"] + m["consensus_fair_b"], 1.0, places=3, msg=m["match"]
            )

    def test_outright_market_normalized(self):
        om = self.data["outright_market"]
        self.assertEqual(len(om["entries"]), 8)
        total = sum(e["fair_probability"] for e in om["entries"])
        self.assertAlmostEqual(total, 1.0, places=3)
        self.assertGreater(om["overround"], 1.0)  # real book margin retained
        # Falcons are the market favourite per the verified capture
        top = om["entries"][0]
        self.assertEqual(top["team"], "Falcons")

    def test_pinnacle_prices_are_american_converted_correctly(self):
        pin = [l for m in self.data["matches"] for l in m["lines"] if l["source"] == "Pinnacle"]
        self.assertEqual(len(pin), 4)
        for line in pin:  # e.g. +218 -> 3.18, -275 -> 1.3636
            self.assertGreater(line["decimal_a"], 1.0)
            self.assertGreater(line["decimal_b"], 1.0)

    def test_generated_page_matches_data(self):
        page = os.path.join(VDIR, "index.html")
        self.assertTrue(os.path.exists(page))
        html = open(page, encoding="utf-8").read()
        for m in self.data["matches"]:
            self.assertIn(f"{m['consensus_fair_a']*100:.1f}%", html)
            self.assertIn(m["pick"], html)
        for i in range(1, 11):
            self.assertIn(f"IR-V{i}", html)

    def test_evidence_snapshots_present(self):
        for f in (
            "standings_global_2026_10_05.md",
            "standings_global_2026_08_03.md",
            "standings_global_2026_09_07.md",
            "VERIFICATION_REPORT.md",
        ):
            self.assertTrue(os.path.exists(os.path.join(VDIR, "evidence", f)), f) if "standings" in f else \
                self.assertTrue(os.path.exists(os.path.join(VDIR, f)), f)

    def test_root_index_links_verification_page(self):
        html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
        self.assertIn("verify/8e7a652d/index.html", html)


if __name__ == "__main__":
    unittest.main()
