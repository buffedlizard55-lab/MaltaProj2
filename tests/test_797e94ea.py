"""Regression tests for the session-797e94ea read-only source-integrity audit."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "audits" / "797e94ea"
BUILD = AUDIT_DIR / "build_audit.py"


spec = importlib.util.spec_from_file_location("audit_797e94ea", BUILD)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SourceIntegrityAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        exit_code = module.main()
        assert exit_code == 0
        cls.report = json.loads((AUDIT_DIR / "report.json").read_text(encoding="utf-8"))
        cls.ledger = json.loads((AUDIT_DIR / "source_check_ledger.json").read_text(encoding="utf-8"))
        cls.page = (AUDIT_DIR / "index.html").read_text(encoding="utf-8")

    def test_snapshot_summary_is_complete_and_passing(self) -> None:
        summary = self.report["summary"]
        self.assertEqual(summary["status"], "pass")
        self.assertEqual(summary["quoted_fixtures_checked"], 8)
        self.assertEqual(summary["quote_rows_checked"], 12)
        self.assertEqual(summary["root_rows_with_blank_probability"], 82)
        self.assertEqual(summary["errors"], [])

    def test_every_quoted_fixture_has_hotspawn_and_external_https_sources(self) -> None:
        for row in self.report["rows"]:
            self.assertEqual(row["hotspawn_fixture_source"], module.FIXTURES_URL)
            self.assertTrue(row["per_source"], row["fixture_id"])
            for quote in row["per_source"]:
                self.assertTrue(quote["links"], (row["fixture_id"], quote["source_name"]))
                self.assertTrue(all(item["url"].startswith("https://") for item in quote["links"]))

    def test_probability_math_and_consensus_are_reproducible(self) -> None:
        for row in self.report["rows"]:
            self.assertEqual(row["status"], "pass", row)
            self.assertTrue(all(row["checks"].values()), row)
            for quote in row["per_source"]:
                self.assertTrue(all(quote["checks"].values()), (row["fixture_id"], quote))
                self.assertAlmostEqual(sum(quote["stored_probability"]), 1.0, places=4)
                self.assertEqual(quote["stored_probability"], quote["recomputed_probability"])
            consensus = row["consensus"]
            self.assertEqual(consensus["stored_probability_a"], consensus["recomputed_probability_a"])
            self.assertEqual(consensus["stored_probability_b"], consensus["recomputed_probability_b"])

    def test_root_analysis_inputs_have_no_crowd_pick_key(self) -> None:
        lines = json.loads((ROOT / "data" / "lines.json").read_text(encoding="utf-8"))
        current = json.loads((ROOT / "data" / "current_probabilities.json").read_text(encoding="utf-8"))
        text = json.dumps({"lines": lines, "current": current}, sort_keys=True).lower()
        self.assertNotRegex(text, r'"[^" ]*picked[^" ]*"')

    def test_source_ledger_is_explicitly_dated_and_does_not_act_as_a_feed(self) -> None:
        self.assertEqual(self.ledger["audit_observed_at_utc"], module.AUDIT_OBSERVED_AT)
        self.assertEqual(len(self.ledger["checks"]), 7)
        moved = next(item for item in self.ledger["checks"] if item["id"] == "SRC-797-01")
        self.assertEqual(moved["status"], "observed_price_moved")
        self.assertEqual(moved["snapshot_at_011557z"]["american_prices"], [255, -326])
        self.assertEqual(moved["observed"]["american_prices"], [241, -307])
        self.assertIn("not a replacement price feed", self.ledger["collection_method"])

    def test_rendered_page_is_mobile_ready_and_rows_are_source_linked(self) -> None:
        self.assertIn('name="viewport"', self.page)
        self.assertIn('class="cards"', self.page)
        self.assertIn("@media", (AUDIT_DIR / "style.css").read_text(encoding="utf-8"))
        for row in self.report["rows"]:
            match = re.search(
                rf'<tr data-fixture="{re.escape(row["fixture_id"])}">(.*?)</tr>',
                self.page,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(match, row["fixture_id"])
            fragment = match.group(1)
            self.assertIn(module.FIXTURES_URL, fragment)
            self.assertRegex(fragment, r'href="https://')

    def test_findings_are_flagged_and_each_has_manual_review_links(self) -> None:
        expected = {"F-797-01", "F-797-02", "F-797-03", "F-797-04"}
        self.assertEqual({item["id"] for item in self.report["findings"]}, expected)
        for finding in self.report["findings"]:
            self.assertTrue(finding["sources"], finding)
            self.assertTrue(all(url.startswith("https://") for url in finding["sources"]))
        self.assertIn('class="finding needs-review"', self.page)
        self.assertIn('class="finding scope-boundary"', self.page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
