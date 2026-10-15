#!/usr/bin/env python3
"""Tests for the /picks/ live-lines board (session ac475c09, task T-LIVE).

These tests run offline against the committed data so that they validate the published artefact
rather than live sources. Every assertion maps to a rule from the task brief:

  * every table row must carry a source link to an official site,
  * a value that could not be confirmed must be blank and flagged, never inferred,
  * HotSpawn's crowd "picked %" must never enter a probability,
  * probabilities must be arithmetic derived from quoted prices (no odds -> no probability),
  * the dashboard must build and have no broken local links.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

BOARD = os.path.join(ROOT, "data", "picks_board.json")
QUOTES = os.path.join(ROOT, "data", "picks_quotes.json")
FIXTURES = os.path.join(ROOT, "data", "picks_fixtures.json")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class TestPicksBoard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load(BOARD)
        cls.quotes = load(QUOTES)
        cls.fixtures = load(FIXTURES)

    def test_board_covers_open_fixtures(self):
        rows = self.board["rows"]
        self.assertGreater(len(rows), 0, "board must contain the fixtures in scope")
        open_rows = [r for r in rows if r.get("open_for_picks")]
        self.assertGreater(len(open_rows), 0, "the lobby must have open fixtures")
        self.assertEqual(len(open_rows), self.board["stats"]["open"])

    def test_every_row_links_to_the_official_fixture_page(self):
        """A published row link must open something real on the official site.

        `/matches/<id>` on its own was measured to redirect to the matches index, so it is never
        published: a row either carries a slug permalink the source itself publishes, or the lobby
        listing, and the kind of link is stated on the row.
        """
        allowed = {"lobby_published_permalink", "constructed_slug_verified_200", "lobby_listing_fallback"}
        for row in self.board["rows"]:
            url = row.get("hotspawn_match_url") or ""
            kind = row.get("hotspawn_match_url_kind")
            self.assertTrue(url.startswith("https://"), f"row {row.get('fixture_id')} has no link")
            self.assertIn(kind, allowed, f"row {row.get('fixture_id')} has unknown link kind {kind!r}")
            self.assertIsNone(re.fullmatch(r"https://www\.hotspawn\.com/matches/\d+", url),
                              f"row {row.get('fixture_id')} publishes the redirecting bare-id URL")
            if kind == "lobby_published_permalink":
                self.assertTrue(url.startswith("https://www.hotspawn.com/matches/"), url)
                self.assertTrue(url.endswith("-" + str(row["fixture_id"])), url)
            elif kind == "lobby_listing_fallback":
                self.assertEqual(url, "https://play.hotspawn.com/lobby")

    def test_lobby_listing_fallback_rows_are_flagged(self):
        for row in self.board["rows"]:
            if row.get("hotspawn_match_url_kind") == "lobby_listing_fallback":
                self.assertIn("match_link_lobby_listing_fallback", row["flags"],
                              f"row {row.get('fixture_id')} uses the fallback link without saying so")

    def test_link_checks_cover_the_published_quote_urls(self):
        path = os.path.join(ROOT, "evidence", "picks", "link_checks.json")
        if not os.path.exists(path):
            self.skipTest("collector has not run a link check for this revision")
        results = (load(path).get("results") or {})
        capture_sources = {"egamersworld_manual"}
        for row in self.board["rows"]:
            for quote in row["quotes"]:
                if quote["source_key"] in capture_sources:
                    continue
                url = quote.get("source_url")
                self.assertIn(url, results, f"published quote URL was never opened: {url}")
                state = quote.get("link_state")
                status = results[url]["status"]
                if state == "ok":
                    self.assertEqual(status, 200, url)
                elif state and state.startswith(("http_", "blocked_")):
                    self.assertEqual(int(state.split("_", 1)[1]), status, url)
                elif state in ("not_found", "unreachable"):
                    self.assertTrue(status in (404, 405, 410, 0), f"{url} -> {status}")

    def test_dated_capture_rows_publish_no_derived_clock_and_are_link_checked(self):
        path = os.path.join(ROOT, "data", "picks_supplementary.json")
        if not os.path.exists(path):
            self.skipTest("no dated capture in this revision")
        capture = load(path)
        for row in capture.get("rows", []):
            self.assertIn("link_check", row, f"capture row {row.get('fixture_id')} has no link check")
            self.assertIsNone(row.get("start_time_utc"),
                              f"capture row {row.get('fixture_id')} publishes a derived UTC time")

    def test_probability_exists_only_with_a_quoted_price(self):
        for row in self.board["rows"]:
            used = [q for q in row["quotes"] if not q["is_live"]]
            if used:
                self.assertIsNotNone(row["prob_a"], f"{row['fixture_id']} has quotes but no probability")
                self.assertIsNotNone(row["pick"])
                self.assertAlmostEqual(row["prob_a"] + row["prob_b"], 1.0, places=9)
                self.assertEqual(row["n_sources"], len(used))
            else:
                self.assertIsNone(row["prob_a"], f"{row['fixture_id']} has no quote but a probability")
                self.assertIsNone(row["pick"])
                # Either there was no external price at all, or only a live one (which is never
                # presented as a pre-match line) — both cases stay blank and flagged.
                self.assertTrue({"no_external_line", "live_market_only_no_prematch_line"}
                                & set(row["flags"]), row["flags"])

    def test_every_probability_is_reproducible_from_its_quotes(self):
        """Re-derive the consensus from the stored quotes; it must match the published number."""
        for row in self.board["rows"]:
            used = [q for q in row["quotes"] if not q["is_live"]]
            if not used:
                continue
            for q in used:
                qa, qb = 1 / q["decimal_a"], 1 / q["decimal_b"]
                self.assertAlmostEqual(q["prob_a"], qa / (qa + qb), places=9)
                self.assertAlmostEqual(q["overround"], (qa + qb) - 1, places=9)
            expected = sum(q["prob_a"] for q in used) / len(used)
            self.assertAlmostEqual(row["prob_a"], expected, places=9)

    def test_every_quote_has_a_source_url_and_timestamp(self):
        for q in self.quotes["quotes"]:
            self.assertTrue(str(q.get("source_public_url") or q.get("source_api_url") or "").startswith("http"),
                            "a quote without a source URL is not publishable")
            self.assertTrue(q.get("retrieved_at_utc"), "a quote without a retrieval time is not publishable")
            self.assertNotIn(q.get("source_key"), (None, ""))

    def test_no_crowd_percentage_is_ever_used_as_a_probability(self):
        for row in self.board["rows"]:
            self.assertNotIn("team_a_pick_pct", row)
            self.assertFalse(row.get("crowd_pct_used", False))
        source = open(os.path.join(ROOT, "scripts", "picks_build.py"), encoding="utf-8").read()
        self.assertNotIn("pick_pct", source.replace("pick_pct_used", ""),
                         "the builder must never read a crowd pick percentage")

    def test_quotes_outside_the_lobby_are_rejected_not_used(self):
        for rej in self.board["rejections"]:
            self.assertIn(rej["reason"], {"no_fixture_match", "ambiguous_multiple_fixtures"})
            self.assertTrue(rej.get("source_url", "").startswith("http") or rej.get("source_key"))

    def test_locked_fixtures_are_marked_not_pickable(self):
        for row in self.board["rows"]:
            if row.get("open_for_picks"):
                continue
            if row.get("lock_time_utc"):
                self.assertIn("past_lock_not_pickable", row["flags"])
            else:
                self.assertIn("lock_time_unknown_in_source_api", row["flags"])


class TestPicksSite(unittest.TestCase):
    def test_pages_exist(self):
        for name in ("index.html", "cs2.html", "lol.html", "events.html",
                     "flagged.html", "methodology.html", "style.css"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "picks", name)), f"picks/{name} missing")

    def test_no_broken_local_links(self):
        import picks_build
        self.assertEqual(picks_build.check_links(), [])

    def test_mobile_viewport_and_card_labels(self):
        html = open(os.path.join(ROOT, "picks", "index.html"), encoding="utf-8").read()
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1"', html)
        self.assertIn('href="style.css"', html)
        with open(os.path.join(ROOT, "picks", "cs2.html"), encoding="utf-8") as fh:
            cs2 = fh.read()
        self.assertIn('data-label="Pick"', cs2, "mobile card layout needs per-cell labels")

    def test_every_probability_row_renders_its_source_link(self):
        """A row that shows a number must show the source it came from on the same page."""
        with open(os.path.join(ROOT, "picks", "cs2.html"), encoding="utf-8") as fh:
            cs2 = fh.read()
        board = load(BOARD)
        for row in board["rows"]:
            if row["prob_a"] is None or row.get("sport") != "cs2" or not row.get("open_for_picks"):
                continue
            for q in row["quotes"]:
                self.assertIn(q["source_url"], cs2,
                              f"source link for fixture {row['fixture_id']} is missing from the page")

    def test_builder_is_deterministic(self):
        """Re-running the builder twice must produce byte-identical pages (excluding the timestamp
        of the *source* data, which is not rewritten)."""
        # A committed artifact is not a first build at the same wall clock.
        # Rebuild twice from identical inputs and an explicit evaluation time in
        # an isolated output tree; never mutate another section during tests.
        import importlib.util
        import tempfile
        from unittest.mock import patch
        from datetime import datetime, timezone
        spec = importlib.util.spec_from_file_location("isolated_picks_build", os.path.join(ROOT, "scripts", "picks_build.py"))
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        real_load = builder.load
        fixed = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "data"))
            with patch.object(builder, "ROOT", tmp), patch.object(builder, "OUT", os.path.join(tmp, "picks")), \
                 patch.object(builder, "load", real_load), patch.object(builder, "datetime", Clock), \
                 patch.object(builder, "check_links", return_value=[]):
                # Real source inputs resolve against the repository, not tmp.
                def source_load(rel, default=None):
                    path = os.path.join(ROOT, rel)
                    return load(path) if os.path.exists(path) else default
                with patch.object(builder, "load", source_load):
                    self.assertEqual(builder.main(), 0)
                    before = open(os.path.join(tmp, "picks", "cs2.html"), encoding="utf-8").read()
                    self.assertEqual(builder.main(), 0)
                    after = open(os.path.join(tmp, "picks", "cs2.html"), encoding="utf-8").read()
                    self.assertEqual(before, after)



if __name__ == "__main__":
    unittest.main(verbosity=2)
