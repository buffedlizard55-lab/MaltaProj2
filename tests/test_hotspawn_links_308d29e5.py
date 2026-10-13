"""Regression tests for the independent HotSpawn market-link audit."""
from __future__ import annotations

import importlib.util
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "verify" / "308d29e5" / "audit_market_links.py"
spec = importlib.util.spec_from_file_location("audit_market_links_308d29e5", AUDIT_PATH)
assert spec and spec.loader
AUDIT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AUDIT)


class BodyRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_body = False
        self.rows = 0
        self.row_links = 0
        self._in_row = False
        self._links_in_row = 0

    def handle_starttag(self, tag, attrs):
        if tag == "tbody":
            self.in_body = True
        elif tag == "tr" and self.in_body:
            self.rows += 1
            self._in_row = True
            self._links_in_row = 0
        elif tag == "a" and self._in_row:
            self._links_in_row += 1

    def handle_endtag(self, tag):
        if tag == "tr" and self._in_row:
            if self._links_in_row:
                self.row_links += 1
            self._in_row = False
        elif tag == "tbody":
            self.in_body = False


class HotSpawnMarketLinkAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = AUDIT.build_report()

    def test_counts_are_derived_from_the_captured_fixture_rows(self):
        rows = self.report["rows"]
        summary = self.report["summary"]
        self.assertEqual(summary["future_cs2_fixtures_reviewed"], len(rows))
        self.assertEqual(
            summary["numeric_id_routes_in_market_board"],
            sum(bool(AUDIT.NUMERIC_MATCH_ROUTE.fullmatch(r["market_board_url"])) for r in rows),
        )

    def test_flagged_condition_is_specific_to_numeric_id_routes(self):
        for row in self.report["rows"]:
            numeric = bool(AUDIT.NUMERIC_MATCH_ROUTE.fullmatch(row["market_board_url"]))
            self.assertEqual(row["numeric_id_route"], numeric, row["fixture_id"])
            self.assertEqual(
                row["issue"],
                "numeric_id_route_not_a_match_permalink" if numeric else None,
                row["fixture_id"],
            )

    def test_official_reference_is_a_captured_permalink_or_lobby_fallback(self):
        for row in self.report["rows"]:
            if row["official_reference_kind"] == "lobby_published_permalink":
                self.assertRegex(row["official_reference_url"], r"^https://www\.hotspawn\.com/matches/[^/]+-\d+$")
                self.assertTrue(row["official_reference_url"].endswith("-" + row["fixture_id"]))
                self.assertIn("Separate picks capture", row["link_capture_note"])
            else:
                self.assertEqual(row["official_reference_kind"], "lobby_listing_fallback")
                self.assertEqual(row["official_reference_url"], AUDIT.LOBBY_URL)

    def test_manual_read_is_fixture_specific_and_scoped(self):
        checks = self.report["manual_live_checks"]
        self.assertEqual(len(checks), 1)
        check = checks[0]
        self.assertEqual(check["fixture_id"], "1079546")
        self.assertEqual(check["observed_final_url"], "https://www.hotspawn.com/matches")
        self.assertIn("Zomblers vs Overtake Sector", check["observation"])
        self.assertIn("One live fixture", check["scope_note"])
        self.assertRegex(check["source_published_permalink"], r"-north-america-cup-3-1079546$")

    def test_each_rendered_match_row_has_an_official_reference_link(self):
        parser = BodyRows()
        parser.feed(AUDIT.render(self.report))
        self.assertEqual(parser.rows, len(self.report["rows"]))
        self.assertEqual(parser.row_links, len(self.report["rows"]))

    def test_live_check_attributes_permalink_to_separate_capture_and_one_read(self):
        page = AUDIT.render(self.report)
        self.assertIn("The separate HotSpawn lobby capture recorded", page)
        self.assertIn("when opened in this one manual check", page)


if __name__ == "__main__":
    unittest.main()
