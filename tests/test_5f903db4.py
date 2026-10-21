#!/usr/bin/env python3
"""Contract tests for the `5f903db4` every-match pick section.

Every published number is re-derived here from the raw inputs (decimal odds, Valve VRS points,
no-vig arithmetic) instead of being trusted.  The tests also enforce the product rules:
  * every retained fixture is visible; resolved fixtures have a pick and two probabilities;
  * a value that cannot be sourced stays blank on an explicit unresolved row;
  * every row carries at least one https source link;
  * HotSpawn's crowd-pick percentages never appear in the pages;
  * the phone-first pages exist and their internal links resolve.
"""
from __future__ import annotations

import html
import importlib.util as iu
import json
import math
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "data" / "5f903db4" / "board.json"
EVERYPICK = ROOT / "everypick"

_spec = iu.spec_from_file_location("everpick_core", ROOT / "scripts" / "5f903db4" / "core.py")
core = iu.module_from_spec(_spec)
sys.modules["everpick_core"] = core
_spec.loader.exec_module(core)


def load_board():
    with open(BOARD, encoding="utf-8") as fh:
        return json.load(fh)


class BoardCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load_board()
        cls.rows = cls.board["rows"]
        cls.vrs = core.load(ROOT / "data" / "19d6c262" / "vrs_global.json", {})
        cls.primary = core.load(ROOT / "data" / "f7279a54" / "board.json", {})
        cls.extra = core.load(ROOT / "data" / "fe803b80" / "board.json", {})

    # ---------------------------------------------------------------- coverage
    def test_every_open_lobby_fixture_is_present(self):
        ids = {str(m["fixture_id"]) for m in self.primary.get("open") or []}
        ids |= {str(m["fixture_id"]) for m in self.extra.get("open") or []}
        self.assertTrue(ids, "no open fixtures in the input boards")
        self.assertEqual(ids, {r["fixture_id"] for r in self.rows},
                         "every open fixture from either collector must appear exactly once")

    def test_every_row_has_a_pick_and_two_probabilities(self):
        for r in self.rows:
            with self.subTest(fixture=r["fixture_id"]):
                if r["resolution"]["basis"] == "unresolved":
                    self.assertIsNone(r.get("pick"))
                    self.assertIsNone(r["resolution"].get("prob_a"))
                    self.assertIsNone(r["resolution"].get("prob_b"))
                    self.assertTrue(r["resolution"].get("reason"))
                    continue
                self.assertTrue(r.get("pick"), "a resolved fixture requires a pick")
                self.assertIsNotNone(r["resolution"].get("prob_a"))
                self.assertIsNotNone(r["resolution"].get("prob_b"))
                self.assertAlmostEqual(r["resolution"]["prob_a"] + r["resolution"]["prob_b"],
                                       1.0, places=9)
                self.assertIn(r["pick"], (r["team_a"], r["team_b"]))

    def test_pick_is_the_higher_probability(self):
        for r in self.rows:
            res = r["resolution"]
            if res["basis"] == "unresolved":
                self.assertIsNone(r["pick"])
                continue
            expected = r["team_a"] if res["prob_a"] >= res["prob_b"] else r["team_b"]
            self.assertEqual(expected, r["pick"], r["fixture_id"])
            self.assertEqual(res["prob_a"] >= res["prob_b"], r["pick_side"] == "a", r["fixture_id"])

    def test_unresolved_rows_are_counted_not_hidden(self):
        s = self.board["summary"]
        unresolved = [r for r in self.rows if r["resolution"]["basis"] == "unresolved"]
        self.assertEqual(s["unresolved"], len(unresolved))
        self.assertEqual(s["with_pick"], len([r for r in self.rows if r.get("pick")]))
        self.assertEqual(s["with_pick"] + s["unresolved"], len(self.rows))

    # ---------------------------------------------------------------- market maths
    def test_market_probabilities_reproduce_from_decimal_odds(self):
        checked = 0
        for r in self.rows:
            for q in r["quotes"]:
                ia, ib = 1.0 / q["decimal_a"], 1.0 / q["decimal_b"]
                self.assertAlmostEqual(ia / (ia + ib), q["prob_a"], places=6, msg=r["fixture_id"])
                self.assertAlmostEqual(ib / (ia + ib), q["prob_b"], places=6, msg=r["fixture_id"])
                self.assertAlmostEqual(ia + ib - 1.0, q["overround"], places=6, msg=r["fixture_id"])
                self.assertGreater(q["decimal_a"], 1.0)
                self.assertGreater(q["decimal_b"], 1.0)
                checked += 1
        self.assertGreater(checked, 0, "at least one market quote must be present")

    def test_market_consensus_is_the_mean_of_the_books(self):
        for r in self.rows:
            if r["resolution"]["basis"] != "market":
                continue
            mean = sum(q["prob_a"] for q in r["quotes"]) / len(r["quotes"])
            self.assertAlmostEqual(mean, r["resolution"]["prob_a"], places=9, msg=r["fixture_id"])
            self.assertEqual(r["resolution"]["n_books"], len(r["quotes"]))

    def test_quote_kickoff_agrees_with_fixture(self):
        for r in self.rows:
            for q in r["quotes"]:
                if q.get("start_diff_minutes") is None:
                    continue
                self.assertLessEqual(q["start_diff_minutes"], 90.0,
                                     f"{r['fixture_id']} quote {q['event_id']} is off-schedule")

    # ---------------------------------------------------------------- origination
    def test_originated_lines_reproduce_from_official_valve_points(self):
        index = core.vrs_index(self.vrs)
        floor = core.vrs_floor(self.vrs)
        for r in self.rows:
            basis = r["resolution"]["basis"]
            if not basis.startswith("originated"):
                continue
            with self.subTest(fixture=r["fixture_id"]):
                a = core.vrs_lookup(index, r["team_a"])
                b = core.vrs_lookup(index, r["team_b"])
                pa = float(a["chosen"]["points"]) if a else None
                pb = float(b["chosen"]["points"]) if b else None
                if basis == "originated_vrs":
                    self.assertIsNotNone(pa, "both sides must be rated for a point estimate")
                    self.assertIsNotNone(pb)
                    self.assertAlmostEqual(core.vrs_prob(pa, pb), r["resolution"]["prob_a"], places=9)
                else:
                    self.assertIsNotNone(floor, "a floor row is required for a bound")
                    listed = pa if pa is not None else pb
                    self.assertIsNotNone(listed, "a bound needs one rated side")
                    self.assertEqual((pa is None) or (pb is None), True,
                                     "a bound row must have exactly one unrated side")
                    p_listed = core.vrs_prob(listed, float(floor["points"]))
                    p_a = p_listed if pa is not None else 1.0 - p_listed
                    self.assertAlmostEqual(p_a, r["resolution"]["prob_a"], places=9)
                    self.assertEqual(r["confidence"], "Bound")

    def test_originated_basis_is_labelled_in_flags(self):
        for r in self.rows:
            basis = r["resolution"]["basis"]
            if basis == "originated_vrs":
                self.assertIn("originated_from_official_valve_vrs", r["flags"], r["fixture_id"])
                self.assertIn("no_external_price_any_book", r["flags"], r["fixture_id"])
            if basis == "originated_vrs_bound":
                self.assertIn("originated_bound_unlisted_opponent", r["flags"], r["fixture_id"])
                self.assertIsNotNone(r["resolution"]["bound"])

    def test_bounds_are_not_presented_as_point_estimates(self):
        page = (EVERYPICK / "picks.html").read_text(encoding="utf-8")
        for r in self.rows:
            if r["resolution"]["basis"] != "originated_vrs_bound":
                continue
            frag = re.search(rf'id="f{r["fixture_id"]}".*?</tr>', page, re.S)
            self.assertIsNotNone(frag, f"row {r['fixture_id']} missing from picks.html")
            self.assertIn("≥", frag.group(0), "the rated side must be marked as a lower bound")
            self.assertIn("≤", frag.group(0), "the unrated side must be marked as an upper bound")

    def test_calibration_constant_is_the_best_fit_on_the_published_pairs(self):
        cal = self.board["calibration_check"]
        self.assertTrue(cal["available"])
        self.assertLess(abs(cal["k_best_grid"] - core.CAL_K), 0.05,
                        "the k in use must be within 0.05 of the best grid fit")
        self.assertLess(cal["mae_at_k_used"], 0.10,
                        "the fitted model's own MAE must be under 10 percentage points")
        self.assertGreaterEqual(cal["pairs"], 30)

    # ---------------------------------------------------------------- sourcing
    def test_every_row_has_at_least_one_https_source(self):
        for r in self.rows:
            urls = [s.get("url") for s in r["sources"] if s.get("url")]
            self.assertTrue(urls, f"{r['fixture_id']} has no source")
            self.assertTrue(any(u.startswith("https://") for u in urls),
                            f"{r['fixture_id']} has no https source")

    def test_market_rows_cite_the_book_that_set_the_price(self):
        for r in self.rows:
            cited = json.dumps(r["sources"]).lower()
            for q in r["quotes"]:
                self.assertIn(str(q["event_id"]).lower(), cited,
                              f"{r['fixture_id']} row does not cite quote {q['event_id']}")

    def test_no_crowd_percentage_is_used(self):
        """The crowd vote on the lobby must never become an input or a published column."""
        board_blob = json.dumps(self.board).lower()
        for needle in ("picked_pct", "picked_percentage", "crowd_pct", "hotspawn_pick_pct",
                       '"picked"'):
            self.assertNotIn(needle, board_blob, f"crowd field {needle!r} leaked into the board")
        for page in EVERYPICK.glob("*.html"):
            text = html.unescape(page.read_text(encoding="utf-8")).lower()
            self.assertNotIn("% picked", text, f"{page.name} shows a crowd percentage")
            self.assertIsNone(re.search(r"\d+\s*%\s*picked", text), page.name)

    # ---------------------------------------------------------------- site
    def test_all_pages_exist_and_are_mobile_first(self):
        expected = {"index.html", "picks.html", "unresolved.html", "sources.html", "method.html",
                    "flagged.html"}
        present = {p.name for p in EVERYPICK.glob("*.html")}
        self.assertEqual(expected, present)
        for name in expected:
            text = (EVERYPICK / name).read_text(encoding="utf-8")
            self.assertIn('name="viewport"', text, f"{name} is not mobile-ready")
            self.assertIn('width=device-width', text, f"{name} is not mobile-ready")
            self.assertIn('@media(max-width:639px)', text, f"{name} does not collapse tables for phones")

    def test_internal_links_resolve(self):
        for page in EVERYPICK.glob("*.html"):
            text = page.read_text(encoding="utf-8")
            for href in re.findall(r'href="([^"#:]+)"', text):
                if href.startswith(("http", "mailto", "#")):
                    continue
                target = (EVERYPICK / href).resolve()
                self.assertTrue(target.exists(),
                                f"{page.name} links to missing file {href}")

    def test_every_match_appears_on_the_picks_page(self):
        text = (EVERYPICK / "picks.html").read_text(encoding="utf-8")
        for r in self.rows:
            self.assertIn(f'id="f{r["fixture_id"]}"', text, r["fixture_id"])
            if r.get("pick"):
                self.assertIn(html.escape(r["pick"]), text, r["fixture_id"])

    def test_executive_summary_links_every_pick_page(self):
        text = (EVERYPICK / "index.html").read_text(encoding="utf-8")
        for target in ("picks.html", "unresolved.html", "sources.html", "method.html",
                       "flagged.html", "../index.html"):
            self.assertIn(f'href="{target}"', text, f"executive summary does not link {target}")

    def test_unresolved_page_lists_limits_and_attempts(self):
        text = (EVERYPICK / "unresolved.html").read_text(encoding="utf-8")
        self.assertIn("Attempt ledger", text)
        for item in self.board["limitations"]:
            self.assertIn(item["id"], text)
        for src in self.board["attempted_sources"]:
            self.assertIn(html.escape(src["source"]), text)

    def test_flagged_page_publishes_every_irregularity(self):
        text = (EVERYPICK / "flagged.html").read_text(encoding="utf-8")
        for item in self.board["irregularities"]:
            self.assertIn(item["id"], text)
            self.assertIn(html.escape(item["title"]), text)


class ResearchEvidence(unittest.TestCase):
    def setUp(self):
        self.research = core.load(ROOT / "scripts" / "5f903db4" / "research.json", {})
        self.board = load_board()

    def test_every_research_quote_has_a_join_note_and_evidence(self):
        for q in self.research.get("quotes") or []:
            with self.subTest(quote=q.get("event_id")):
                self.assertTrue(q.get("join_note"), "a non-exact join needs a written reason")
                self.assertTrue(q.get("evidence_urls"), "a non-exact join needs evidence URLs")
                self.assertTrue(q.get("retrieved_utc"), "a quote needs a read timestamp")

    def test_research_quotes_land_on_a_row(self):
        by_id = {r["fixture_id"]: r for r in self.board["rows"]}
        for q in self.research.get("quotes") or []:
            row = by_id.get(str(q["fixture_id"]))
            self.assertIsNotNone(row, q["fixture_id"])
            events = {str(x["event_id"]) for x in row["quotes"]}
            self.assertIn(str(q["event_id"]), events,
                          f"{q['event_id']} was researched but did not join the row")

    def test_vrs_snapshot_claim_matches_the_committed_file(self):
        vrs = core.load(ROOT / "data" / "19d6c262" / "vrs_global.json", {})
        self.assertEqual(vrs.get("snapshot"), "2026_10_05")
        self.assertEqual(self.board["sources"]["valve_vrs_snapshot"], vrs.get("snapshot"))
        self.assertIn("standings_global_2026_10_05.md", self.board["sources"]["valve_vrs_page"])

    def test_duplicate_valve_rows_are_documented(self):
        index = core.vrs_index(core.load(ROOT / "data" / "19d6c262" / "vrs_global.json", {}))
        dupes = [k for k, v in index.items() if v["ambiguous"]]
        self.assertTrue(dupes, "expected Valve to publish duplicate organisation rows")
        flagged = [r for r in self.board["rows"]
                   if "vrs_duplicate_rows_resolved_by_published_rule" in r["flags"]]
        for r in flagged:
            alternatives = (r["vrs_a"].get("alternatives") or []) + (r["vrs_b"].get("alternatives") or [])
            self.assertTrue(alternatives, f"{r['fixture_id']} resolved a duplicate without keeping it")


if __name__ == "__main__":
    unittest.main()
