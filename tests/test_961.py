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
    def test_builder_never_reads_the_crowd_pick_file(self):
        """The reference file must not be reachable from the builder's executable code."""
        with open(os.path.join(ROOT, "scripts", "961", "build_961.py"), encoding="utf-8") as fh:
            source = fh.read()
        reads = {os.path.basename(m) for m in
                 re.findall(r"(?:load_json|open)\([^\n]*?([\w./]+\.json)", source)}
        allowed = {"lobby.json", "quotes.json", "board.json", "odds.json",
                   "cs2_odds_egamersworld.json", "lol_odds_egamersworld.json"}
        self.assertNotIn("hotspawn_reference.json", reads)
        self.assertTrue(reads <= allowed, msg=sorted(reads - allowed))
        # the only mention of the reference file must be a warning string, not a read
        for line in source.splitlines():
            if "hotspawn_reference" in line:
                self.assertNotIn("load_json(", line)
                self.assertNotIn("open(", line)

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
        allowed = {"fixture_id", "crowd_pick_pct_a", "crowd_pick_pct_b", "total_picks", "note"}
        self.assertEqual(len(ref["rows"]), len(self.lobby["fixtures"]))
        for row in ref["rows"]:
            self.assertTrue(set(row) <= allowed, msg=row.get("fixture_id"))
            payload = {k: v for k, v in row.items() if k != "note"}
            self.assertNotIn("probab", json.dumps(payload).lower())


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


class CrossCheckTests(unittest.TestCase):
    """The published cross-checks must be real, sourced and internally consistent."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "data", "961", "cross_checks.json"), encoding="utf-8") as fh:
            cls.cross = json.load(fh)
        with open(os.path.join(ROOT, "data", "961", "irregularities.json"), encoding="utf-8") as fh:
            cls.irreg = json.load(fh)
        with open(os.path.join(ROOT, "data", "961", "board.json"), encoding="utf-8") as fh:
            cls.board = json.load(fh)

    def test_every_cross_check_has_a_source_link_and_wording(self):
        self.assertTrue(self.cross["rows"])
        for row in self.cross["rows"]:
            self.assertTrue(str(row["hltv_url"]).startswith("https://www.hltv.org/"), msg=row["match"])
            self.assertTrue(row["hltv_statement"], msg=row["match"])
            self.assertTrue(row["checker"] if "checker" in row else True)

    def test_cross_check_agreement_matches_the_board_pick(self):
        picks = {r["fixture_id"]: r["pick"] for r in self.board["rows"]}
        for row in self.cross["rows"]:
            self.assertIn(row["fixture_id"], picks, msg=row["match"])
            self.assertEqual(picks[row["fixture_id"]], row["board_pick"], msg=row["match"])
            self.assertEqual(row["hltv_favorite"] == row["board_pick"], row["agreement"],
                             msg=row["match"])

    def test_cross_checks_are_not_price_inputs(self):
        for r in self.board["rows"]:
            for s in r["sources"]:
                self.assertNotEqual("hltv", s["source_key"],
                                    msg="HLTV wording must never be published as a price")

    def test_cross_check_page_lists_every_row(self):
        with open(os.path.join(PAGES, "crosschecks.html"), encoding="utf-8") as fh:
            page = fh.read()
        for row in self.cross["rows"]:
            self.assertIn(row["hltv_url"], page, msg=row["match"])
            self.assertIn(row["hltv_favorite"], page, msg=row["match"])

    def test_every_irregularity_has_evidence(self):
        self.assertTrue(self.irreg["items"])
        for item in self.irreg["items"]:
            for key in ("id", "title", "detail", "evidence", "status"):
                self.assertTrue(item.get(key), msg=item.get("id"))
            self.assertTrue(any(str(e).startswith("http") or e.endswith(".json")
                                for e in item["evidence"]), msg=item["id"])

    def test_flagged_page_renders_every_irregularity(self):
        with open(os.path.join(PAGES, "flagged.html"), encoding="utf-8") as fh:
            page = fh.read()
        for item in self.irreg["items"]:
            self.assertIn(item["id"], page)
            import html as _html
            self.assertIn(_html.escape(item["title"]), page)

    def test_cancelled_fixtures_are_counted_but_not_open(self):
        summary = self.board["summary"]
        cancelled = [r for r in self.board["rows"] if r["cancelled"]]
        self.assertEqual(summary["cancelled_fixtures"], len(cancelled))
        for r in cancelled:
            self.assertIn("fixture_cancelled", r["flags"], msg=r["fixture_id"])
        self.assertLessEqual(summary["open_for_picks"],
                             summary["fixtures_total"] - len(cancelled))
