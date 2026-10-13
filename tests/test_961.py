#!/usr/bin/env python3
"""Session 961e163a — line-by-line verification of the published pick board.

These tests re-derive every published number from the stored raw quotes, so a hallucinated or
hand-edited probability cannot pass. They also enforce the project rules:

* every row with a probability must cite at least one external source URL + read time,
* a row without an external quote must be blank and flagged ``no_external_line``,
* Hotspawn crowd pick percentages must never appear as an input,
* every rendered table row must carry a source link or an explicit "unverified" marker.
"""

from __future__ import annotations

import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.path.join(ROOT, "data", "961", "board.json")
LOBBY = os.path.join(ROOT, "data", "961", "lobby.json")
REFERENCE = os.path.join(ROOT, "data", "961", "hotspawn_reference.json")
PAGES = os.path.join(ROOT, "verify961")
TOL = 1e-4


class BoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(BOARD, encoding="utf-8") as fh:
            cls.board = json.load(fh)
        with open(LOBBY, encoding="utf-8") as fh:
            cls.lobby = json.load(fh)
        cls.rows = cls.board["rows"]

    def test_every_lobby_fixture_is_on_the_board(self):
        lobby_ids = {f["fixture_id"] for f in self.lobby["fixtures"]}
        board_ids = {r["fixture_id"] for r in self.rows}
        self.assertEqual(lobby_ids, board_ids)

    def test_no_probability_without_a_source(self):
        for r in self.rows:
            if r["probability_a"] is None:
                self.assertIn("no_external_line", r["flags"], msg=r["fixture_id"])
                self.assertFalse(r["sources"], msg=r["fixture_id"])
            else:
                self.assertTrue(r["sources"], msg=r["fixture_id"])
                for s in r["sources"]:
                    self.assertTrue(str(s.get("source_url") or "").startswith("http"),
                                    msg=f'{r["fixture_id"]} {s.get("source_key")} missing source URL')
                    self.assertTrue(s.get("retrieved_at_utc"),
                                    msg=f'{r["fixture_id"]} {s.get("source_key")} missing read time')

    def test_no_vig_arithmetic_recomputes(self):
        for r in self.rows:
            for s in r["sources"]:
                oa, ob = s["decimal_odds_a"], s["decimal_odds_b"]
                self.assertGreater(oa, 1.0, msg=r["fixture_id"])
                self.assertGreater(ob, 1.0, msg=r["fixture_id"])
                qa, qb = 1 / oa, 1 / ob
                expected = qa / (qa + qb)
                self.assertAlmostEqual(expected, s["no_vig_probability_a"], delta=TOL,
                                       msg=f'{r["fixture_id"]} {s["source_key"]}')
                self.assertAlmostEqual(1 - expected, s["no_vig_probability_b"], delta=TOL,
                                       msg=f'{r["fixture_id"]} {s["source_key"]}')
                self.assertAlmostEqual(s["overround"], qa + qb - 1, delta=TOL,
                                       msg=f'{r["fixture_id"]} {s["source_key"]}')

    def test_consensus_is_the_mean_of_sources(self):
        for r in self.rows:
            if r["probability_a"] is None:
                continue
            probs = [s["no_vig_probability_a"] for s in r["sources"]]
            self.assertAlmostEqual(sum(probs) / len(probs), r["probability_a"], delta=TOL,
                                   msg=r["fixture_id"])
            self.assertAlmostEqual(1.0, r["probability_a"] + r["probability_b"], delta=TOL,
                                   msg=r["fixture_id"])

    def test_pick_is_the_more_probable_side(self):
        for r in self.rows:
            if r["probability_a"] is None:
                self.assertIsNone(r["pick"])
                self.assertIsNone(r["pick_probability"])
                continue
            expected_pick = r["team_a"] if r["probability_a"] >= 0.5 else r["team_b"]
            expected_prob = max(r["probability_a"], r["probability_b"])
            self.assertEqual(expected_pick, r["pick"], msg=r["fixture_id"])
            self.assertAlmostEqual(expected_prob, r["pick_probability"], delta=TOL,
                                   msg=r["fixture_id"])
            self.assertGreaterEqual(r["pick_probability"], 0.5, msg=r["fixture_id"])

    def test_hotspawn_crowd_pick_is_never_an_input(self):
        for r in self.rows:
            self.assertFalse(r["hotspawn_pick_pct_used"], msg=r["fixture_id"])
            for key in r:
                self.assertNotIn("crowd", key.lower(), msg=r["fixture_id"])
        # the builder must be structurally unable to read the reference file
        with open(os.path.join(ROOT, "scripts", "961", "build_961.py"), encoding="utf-8") as fh:
            builder = fh.read()
        self.assertNotIn("hotspawn_reference", builder)

    def test_every_row_links_an_official_hotspawn_source(self):
        for r in self.rows:
            self.assertTrue(str(r["official_source_url_hotspawn"]).startswith("https://"),
                            msg=r["fixture_id"])
            self.assertTrue(str(r["hotspawn_match_url"]).startswith("https://www.hotspawn.com/matches/"),
                            msg=r["fixture_id"])

    def test_summary_matches_the_rows(self):
        summary = self.board["summary"]
        self.assertEqual(summary["fixtures_total"], len(self.rows))
        self.assertEqual(summary["fixtures_with_external_line"],
                         sum(1 for r in self.rows if r["verified"]))
        self.assertEqual(summary["fixtures_without_external_line"],
                         sum(1 for r in self.rows if not r["verified"]))
        by_source = {}
        for r in self.rows:
            for s in r["sources"]:
                by_source[s["source_key"]] = by_source.get(s["source_key"], 0) + 1
        self.assertEqual(summary["by_source"], by_source)

    def test_reference_pick_percentages_are_present_but_separate(self):
        with open(REFERENCE, encoding="utf-8") as fh:
            ref = json.load(fh)
        self.assertIn("never a probability input", ref["warning"])
        for row in ref["rows"]:
            self.assertNotIn("probability", json.dumps(row).lower())


class PageTests(unittest.TestCase):
    def test_rows_render_with_a_source_or_unverified_marker(self):
        for page in ("index.html", "cs2.html", "lol.html"):
            with open(os.path.join(PAGES, page), encoding="utf-8") as fh:
                text = fh.read()
            rows = re.findall(r'<tr class="row [^"]*">(.*?)</tr>', text, re.S)
            self.assertTrue(rows, msg=page)
            for row in rows:
                self.assertTrue('href="http' in row or "unverified" in row, msg=page)

    def test_pages_have_no_broken_local_links(self):
        for page in sorted(os.listdir(PAGES)):
            if not page.endswith(".html"):
                continue
            with open(os.path.join(PAGES, page), encoding="utf-8") as fh:
                text = fh.read()
            for href in re.findall(r'href="([^"#]+)"', text):
                if href.startswith(("http", "mailto:")):
                    continue
                self.assertTrue(os.path.exists(os.path.join(PAGES, href)),
                                msg=f"{page} -> {href}")

    def test_pages_declare_mobile_viewport_and_are_dark_on_small_screens(self):
        with open(os.path.join(PAGES, "index.html"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1"', text)
        with open(os.path.join(PAGES, "style.css"), encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn("@media (max-width:820px)", css)
        self.assertIn("data-label", text)

    def test_flagged_page_lists_every_unverified_fixture(self):
        with open(BOARD, encoding="utf-8") as fh:
            board = json.load(fh)
        with open(os.path.join(PAGES, "flagged.html"), encoding="utf-8") as fh:
            flagged = fh.read()
        for r in board["rows"]:
            if not r["verified"]:
                self.assertIn(str(r["fixture_id"]), flagged)


if __name__ == "__main__":
    unittest.main(verbosity=2)
