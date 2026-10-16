#!/usr/bin/env python3
"""Regression tests for the independent e2d16060 publication audit.

The tests cover only this session's isolated audit artifacts.  They do not rewrite
another session's board, collectors, landing page, or workflow.
"""
from __future__ import annotations

import importlib.util
import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audits" / "e2d16060"
REPORT = AUDIT / "report.json"
BOARD = ROOT / "data" / "c64a5e19" / "board.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_audit_module():
    spec = importlib.util.spec_from_file_location("audit_e2d16060", ROOT / "scripts" / "e2d16060" / "audit.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AuditArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load_json(REPORT)
        cls.board = load_json(BOARD)
        cls.audit = load_audit_module()

    def test_report_declares_one_coherent_canonical_batch(self):
        scope = self.report["scope"]
        self.assertEqual(scope["canonical_board"], "data/c64a5e19/board.json")
        self.assertEqual(scope["canonical_page"], "picks-every-match/picks.html")
        self.assertIn("no external URL reachability", scope["policy"])
        self.assertEqual(self.report["source_capture"]["generated_utc"], self.board["generated_utc"])
        self.assertEqual(self.report["source_capture"]["collected_from_utc"], self.board["collected_from_utc"])

    def test_every_canonical_open_fixture_has_exactly_one_rendered_row(self):
        summary = self.report["summary"]
        self.assertEqual(summary["listed_open"], len(self.board["open"]))
        self.assertEqual(summary["page_rows"], len(self.board["open"]))
        self.assertEqual(summary["fixture_failures"], 0)
        ids = [row["fixture_id"] for row in self.report["fixture_checks"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {str(row["fixture_id"]) for row in self.board["open"]})

    def test_priced_rows_normalize_and_unresolved_rows_are_blank(self):
        priced = 0
        unresolved = 0
        for row in self.board["open"]:
            line = row.get("line")
            if line is None:
                unresolved += 1
                fixture = next(item for item in self.report["fixture_checks"] if item["fixture_id"] == row["fixture_id"])
                self.assertIsNone(fixture["prob_a"], row["fixture_id"])
                self.assertIsNone(fixture["prob_b"], row["fixture_id"])
                self.assertIsNone(fixture["pick_team"], row["fixture_id"])
                self.assertEqual(fixture["basis"], "unverified", row["fixture_id"])
                continue
            priced += 1
            self.assertIsInstance(line.get("prob_a"), (int, float), row["fixture_id"])
            self.assertIsInstance(line.get("prob_b"), (int, float), row["fixture_id"])
            self.assertTrue(math.isfinite(line["prob_a"]))
            self.assertTrue(math.isfinite(line["prob_b"]))
            self.assertAlmostEqual(line["prob_a"] + line["prob_b"], 1.0, places=4, msg=row["fixture_id"])
            expected = row["team_a"] if line["prob_a"] >= line["prob_b"] else row["team_b"]
            self.assertEqual(line["pick_team"].casefold(), expected.casefold(), row["fixture_id"])
        self.assertEqual(priced, self.report["summary"]["board_with_line"])
        self.assertEqual(unresolved, self.report["summary"]["board_unresolved"])
        self.assertGreater(unresolved, 0, "the audit must not conceal unresolved rows")
        self.assertEqual(self.report["summary"]["arithmetic_failures"], 0)

    def test_every_row_has_manual_review_source_urls(self):
        for row in self.report["fixture_checks"]:
            self.assertTrue(row["source_urls"], row["fixture_id"])
            self.assertTrue(all(url.startswith("https://") for url in row["source_urls"]), row["fixture_id"])
            self.assertTrue(row["page_source_urls"], row["fixture_id"])
            self.assertTrue(all(url.startswith("https://") for url in row["page_source_urls"]), row["fixture_id"])

    def test_findings_publish_known_limits_without_converting_them_to_picks(self):
        ids = {finding["id"] for finding in self.report["findings"]}
        self.assertIn("AUD-E2D-001", ids)  # shared filter markup needs integration review
        self.assertIn("AUD-E2D-002", ids)  # HLTV probe failure is disclosed
        self.assertIn("AUD-E2D-003", ids)  # unresolved rows remain explicit
        self.assertIn("AUD-E2D-004", ids)  # independent newer snapshot is not blended
        for finding in self.report["findings"]:
            self.assertTrue(finding["source_urls"], finding["id"])
            self.assertTrue(all(url.startswith("https://") for url in finding["source_urls"]), finding["id"])
        unresolved = [row for row in self.report["fixture_checks"] if row["basis"] == "unverified"]
        self.assertEqual(len(unresolved), self.report["summary"]["board_unresolved"])
        self.assertTrue(all(row["prob_a"] is None and row["prob_b"] is None and row["pick_team"] is None for row in unresolved))

    def test_surface_link_and_mobile_results_are_published(self):
        surfaces = self.report["surface_checks"]
        self.assertGreaterEqual(len(surfaces), 10)
        self.assertEqual(self.report["summary"]["surfaces_with_missing_links"], 0)
        self.assertTrue(all(not item["missing_local_links"] for item in surfaces))
        self.assertTrue(all(not item["broken_fragments"] for item in surfaces))
        self.assertTrue(all(item["has_viewport"] for item in surfaces))
        index = (AUDIT / "index.html").read_text(encoding="utf-8")
        flagged = (AUDIT / "flagged.html").read_text(encoding="utf-8")
        method = (AUDIT / "method.html").read_text(encoding="utf-8")
        for page in (index, flagged, method):
            self.assertIn('name="viewport"', page)
            self.assertIn('<main id="main"', page)
            self.assertIn('aria-label="Audit navigation"', page)
            self.assertIn('href="#main">Skip to content</a>', page)
        self.assertIn("Unresolved picks", index)
        self.assertIn("AUD-E2D-001", flagged)
        self.assertIn("HotSpawn is a fixture/lock source only", method)

    def test_malformed_shared_markup_is_flagged_not_silently_rewritten(self):
        canonical = (ROOT / "picks-every-match" / "picks.html").read_text(encoding="utf-8")
        self.assertRegex(canonical, r"</option\s+value=")
        finding = next(item for item in self.report["findings"] if item["id"] == "AUD-E2D-001")
        self.assertIn("Repair", finding["action"])


if __name__ == "__main__":
    unittest.main()
