#!/usr/bin/env python3
"""Contract tests for session 1fac4be2 (final integration + verification).

The verification page is regenerated on every refresh, so these tests derive
their expectations from the published JSON instead of pinning today's counts:
they hold as the lobby rotates and as the collectors republish.

Run: python -m unittest tests.test_1fac4be2 -v
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "1fac4be2" / "verification.json"
VERIFY = ROOT / "verify" / "1fac4be2"
DAY4 = ROOT / "day4"
LANDING = ROOT / "index.html"


def report() -> dict:
    return json.loads(DATA.read_text())


class VerificationReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = report()

    def test_report_shape(self):
        for key in ("session", "generated_utc", "boards", "inventory", "twc", "pages",
                    "ci", "egress", "crowd", "flagged", "re_derivation_failures"):
            self.assertIn(key, self.report, key)
        self.assertEqual(self.report["session"], "1fac4be2")

    def test_every_published_probability_re_derives(self):
        """A failure here means a board publishes a number its own retained
        inputs cannot reproduce — the site must not ship that silently."""
        failures = []
        for board in self.report["boards"]:
            for row in board["re_derivation_failures"]:
                failures.append(f"{board['board']} {row['fixture_id']} {row['status']}")
        self.assertEqual(failures, [], f"unreproducible rows: {failures}")

    def test_probabilities_sum_to_one_and_have_a_declared_rule(self):
        checked = 0
        for board in self.report["boards"]:
            for row in board["rows"]:
                if row["published_prob_a"] is None:
                    continue
                checked += 1
                self.assertIsNotNone(row["rule"], f"{board['board']} {row['fixture_id']}")
                self.assertIn(row["status"], ("re-derived", "consistent with the retained quote range"),
                              f"{board['board']} {row['fixture_id']}: {row['status']}")
        self.assertGreater(checked, 0, "no probabilities were verified at all")

    def test_blank_rows_carry_a_reason_and_two_sources(self):
        board = next(b for b in self.report["boards"] if b["path"] == "data/1c8f79f8/board.json")
        blanks = [r for r in board["rows"] if r["published_prob_a"] is None]
        self.assertTrue(blanks)
        for row in blanks:
            self.assertTrue(row["blank_reason"], row["fixture_id"])

    def test_inventory_covers_every_captured_fixture(self):
        inv = self.report["inventory"]
        self.assertEqual(inv["captured_fixtures_with_a_published_row"], inv["captured_fixtures"])
        for row in inv["rows"]:
            self.assertNotIn("NO PUBLISHED BOARD ROW", row["resolved_by"], row["fixture_id"])

    def test_twc_ledger_records_the_correction(self):
        """The corrected desk row is 13-1, and any retained capture that says
        otherwise is named on the flagged page instead of being overwritten."""
        twc = self.report["twc"]
        self.assertIn("13-1", twc["verdict"])
        self.assertEqual(twc["desk_day1_9z_row"][5], "Inferno 13-11, Nuke 13-1")
        self.assertGreaterEqual(len(twc["sources_agreeing_on_13_1"]), 5)
        flagged = " ".join(item["title"] + item["detail"] for item in self.report["flagged"])
        for disagreement in twc["disagreeing_claims"]:
            self.assertIn(disagreement["source"], flagged)
            self.assertIn("Nuke", " ".join(disagreement["claims"]))

    def test_egress_limitation_is_published_not_hidden(self):
        self.assertTrue(self.report["egress"]["limitation"])
        self.assertTrue(self.report["flagged"])

    def test_every_flagged_item_has_sources(self):
        for item in self.report["flagged"]:
            self.assertTrue(item["sources"], item["title"])
            for name, url in item["sources"]:
                self.assertTrue(url.startswith("https://"), (item["title"], url))

    def test_no_failing_workflow_is_hidden(self):
        """If a scheduled collector is red, it must appear on the flagged page."""
        failing = [r["workflow"] for r in self.report["ci"].get("runs", [])
                   if r["conclusion"] == "failure"]
        flagged_titles = " ".join(i["title"] for i in self.report["flagged"])
        for workflow in failing:
            self.assertIn(workflow, flagged_titles, workflow)


class VerificationPages(unittest.TestCase):
    PAGES = ("index.html", "flagged.html")

    def test_pages_exist_mobile_and_single_h1(self):
        for name in self.PAGES:
            text = (VERIFY / name).read_text()
            self.assertIn('name="viewport"', text, name)
            self.assertEqual(text.count("<h1"), 1, name)
            self.assertIn("max-width:640px", text, name)

    def test_internal_links_resolve(self):
        for name in self.PAGES:
            text = (VERIFY / name).read_text()
            for href in re.findall(r'href="([^"#?]+)(?:[#?][^"]*)?"', text):
                if href.startswith(("http", "mailto")):
                    continue
                self.assertTrue((VERIFY / href).resolve().exists(), f"{name} -> {href}")

    def test_every_data_table_row_has_an_official_link(self):
        for name in self.PAGES:
            text = (VERIFY / name).read_text()
            for match in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", text, re.S):
                chunk = match.group(1)
                if "data-label=" not in chunk:
                    continue
                self.assertIn("https://", chunk, f"{name}: row without a source link")

    def test_flagged_page_lists_the_correction(self):
        text = (VERIFY / "flagged.html").read_text()
        self.assertIn("CORRECTED", text)
        self.assertIn("hltv.org", text)


class IntegrationInvariants(unittest.TestCase):
    """The user-facing requirements this session is responsible for."""

    def test_landing_has_one_primary_cta(self):
        """The shared smoke tests click `#executive-summary a.btn-primary`; a second
        primary button makes that locator ambiguous and the hosted run fails."""
        text = LANDING.read_text()
        summary = re.search(r'<section id="executive-summary".*?(?=<section id="canonical-picks|'
                            r'<footer)', text, re.S)
        self.assertIsNotNone(summary)
        self.assertEqual(summary.group(0).count('btn-primary'), 1)

    def test_landing_page_links_the_current_pick_lists_mobile_first(self):
        text = LANDING.read_text()
        # Exactly one primary CTA, as the shared browser smoke tests require
        # (they click a single .btn-primary inside #executive-summary).
        primary = re.findall(r'class="btn btn-primary" href="([^"]+)"', text)
        self.assertEqual(primary, ["picks-every-match/index.html"])
        self.assertIn('class="btn alt2" href="day4/index.html"', text)
        # the shared TWC smoke test clicks exactly one twc-2026 action from here
        self.assertEqual(text.count('class="btn ghost" href="twc-2026/index.html"'), 1)
        self.assertIn('href="#canonical-unresolved"', text)
        self.assertIn('name="viewport"', text)
        # the day-4 semifinal picks and their probabilities are on the landing page itself
        self.assertIn("Semifinal 1", text)
        self.assertIn("Semifinal 2", text)
        self.assertIn("day4/unresolved.html", text)

    def test_day4_desk_has_a_pick_or_a_reason_for_every_open_row(self):
        board = json.loads((ROOT / "data" / "1c8f79f8" / "board.json").read_text())
        for row in board["open"]:
            line = row["line"]
            if line["prob_a"] is None:
                self.assertTrue(row["blank_reason"], row["fixture_id"])
            else:
                self.assertTrue(line["pick"], row["fixture_id"])
                self.assertAlmostEqual(line["prob_a"] + line["prob_b"], 1.0, places=6)

    def test_day4_board_stamps_the_capture_it_used(self):
        board = json.loads((ROOT / "data" / "1c8f79f8" / "board.json").read_text())
        capture = json.loads((ROOT / "data" / "1c8f79f8" / "fixtures_raw.json").read_text())
        self.assertEqual(board["snapshot_utc"], capture["meta"]["captured_utc"])
        self.assertIn(board["inventory"]["mode"], ("fresh_capture", "retained_inventory"))

    def test_day4_refresh_survives_ownership_drift(self):
        """Regression test for the workflow that failed on every run: a moved
        crowd percentage must not abort the rebuild."""
        source = (ROOT / "scripts" / "1c8f79f8" / "build.py").read_text()
        self.assertNotIn('"crowd drift between capture and ledger"', source)
        self.assertIn("crowd ownership moved", source)

    def test_day1_nuke_score_is_the_corrected_value_everywhere(self):
        desk = (DAY4 / "twc-review.html").read_text()
        self.assertIn("Nuke 13-1", desk)
        self.assertNotIn("Nuke 13-4", desk)
        research = (ROOT / "scripts" / "1c8f79f8" / "research.py").read_text()
        self.assertIn("Nuke 13-1", research)

    def test_day4_results_table_has_per_row_sources(self):
        text = (DAY4 / "twc-review.html").read_text()
        rows = [chunk for chunk in re.findall(r"<tr\b[^>]*>(.*?)</tr>", text, re.S)
                if "data-label='Date'" in chunk]
        self.assertGreaterEqual(len(rows), 10, "all ten group-stage results must be listed")
        for chunk in rows:
            self.assertIn("https://", chunk, chunk[:120])


if __name__ == "__main__":
    unittest.main(verbosity=2)
