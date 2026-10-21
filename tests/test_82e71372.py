"""Contract tests for the independent pick-audit desk (session 82e71372).

These tests never write outside data/82e71372 and never call the network: they verify the
committed audit artefact and the pure maths helpers. Run with:
    python3 -m unittest tests.test_82e71372 -v
"""
from __future__ import annotations

import json
import math
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "82e71372"))

import audit  # noqa: E402

AUDIT_PATH = ROOT / "data" / "82e71372" / "audit.json"
SITE = ROOT / "pickaudit"
PAGES = ["index.html", "coverage.html", "arithmetic.html", "reconciliation.html",
         "links.html", "mobile.html", "flagged.html", "method.html"]


class AuditArtefact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def test_artefact_has_every_section(self):
        for key in ("summary", "valve", "constant_provenance", "calibration", "desks",
                    "canonical_fixtures", "coverage", "arithmetic", "valve_checks",
                    "reconciliation", "link_audit", "mobile_audit", "unresolved_sections",
                    "policy_blanks", "ci", "findings"):
            self.assertIn(key, self.audit, key)

    def test_run_is_recent(self):
        gen = datetime.strptime(self.audit["generated_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - gen).total_seconds() / 3600
        self.assertLess(age_h, 26, f"audit is {age_h:.1f}h old; rerun scripts/82e71372/audit.py")

    def test_policy_rules_recorded(self):
        pol = self.audit["policy"]
        self.assertTrue(pol["no_hotspawn_crowd_as_probability"])
        self.assertTrue(pol["blank_stays_blank"])


class CoverageContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def test_every_open_fixture_has_a_complete_pick_somewhere(self):
        coverage = self.audit["coverage"]
        self.assertGreater(len(coverage), 0)
        gaps = [c for c in coverage if c["fully_unresolved"]]
        self.assertEqual(gaps, [], f"fixtures with no pick anywhere: {[g['fixture_id'] for g in gaps]}")
        for c in coverage:
            complete = [d for d, v in c["desks"].items() if v.get("complete")]
            self.assertGreaterEqual(len(complete), 1, c["fixture_id"])
            for d in complete:
                cell = c["desks"][d]
                self.assertIsNotNone(cell["pick"])
                self.assertAlmostEqual(cell["prob_a"] + cell["prob_b"], 1.0, delta=0.01)

    def test_full_coverage_desks_have_no_blanks_on_canonical_fixtures(self):
        full_desks = {d["id"] for d in self.audit["desks"] if d.get("present") and d["id"] in
                      ("everypick", "hotspawn-picks", "fullpicks")}
        for c in self.audit["coverage"]:
            for d in full_desks:
                cell = c["desks"].get(d, {})
                if cell.get("has_row"):
                    self.assertTrue(cell.get("complete"),
                                    f"{d} leaves {c['fixture_id']} blank despite full-coverage claim")

    def test_unresolved_is_zero_on_every_match_desks(self):
        for row in self.audit["board_unresolved"]:
            if row["desk"] in ("everypick", "hotspawn-picks", "fullpicks"):
                self.assertEqual(row["unresolved"], 0)


class ArithmeticContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def test_zero_arithmetic_failures(self):
        self.assertEqual(self.audit["summary"]["arithmetic_failures"], 0)
        for row in self.audit["arithmetic"]:
            self.assertEqual(row["n_fail"], 0,
                             f"{row['desk']} {row['fixture_id']}: "
                             f"{[f['check'] for f in row['failures']]}")

    def test_valve_points_all_match_official_table(self):
        self.assertGreater(len(self.audit["valve_checks"]), 10)
        self.assertEqual(self.audit["summary"]["valve_point_failures"], 0)
        for v in self.audit["valve_checks"]:
            self.assertTrue(v["ok"], v)
            self.assertEqual(v["published_points"], v["official_points"])

    def test_calibration_refit_matches_published_slope(self):
        cal = self.audit["calibration"]
        self.assertTrue(cal["matches"], cal)
        self.assertAlmostEqual(cal["refit_k"], cal["claimed_k"], delta=audit.TOL_FIT)
        self.assertAlmostEqual(cal["refit_mae"], cal["claimed_mae"], delta=audit.TOL_MAE)

    def test_constant_c_derivation_matches_to_numeric_precision(self):
        cp = self.audit["constant_provenance"]
        self.assertIsNotNone(cp["derived_c_q_times_g_rd"])
        self.assertLess(cp["abs_diff"], 1e-6)
        # fit.js genuinely does not contain the literal; this is the PA-CONST-01 finding
        self.assertFalse(cp["fit_js_contains_project_c"])

    def test_pure_maths_helpers(self):
        na, nb, over = audit.novig(1.25, 3.75)
        self.assertAlmostEqual(na + nb, 1.0)
        self.assertAlmostEqual(na, 0.75, delta=0.001)
        self.assertGreater(over, 0)
        self.assertAlmostEqual(audit.vrs_prob(0.0, 0.0), 0.5)
        self.assertGreater(audit.vrs_prob(1297, 1051), 0.5)
        self.assertLess(audit.vrs_prob(1051, 1297), 0.5)

    def test_pick_flips_are_recorded_not_hidden(self):
        flips = [r for r in self.audit["reconciliation"] if r["pick_flip"]]
        flip_findings = {f["id"] for f in self.audit["findings"]}
        for r in flips:
            self.assertIn(f"PA-FLIP-{r['fixture_id']}", flip_findings)


class PublishedPagesContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def test_all_pages_exist(self):
        for name in PAGES:
            self.assertTrue((SITE / name).exists(), name)

    def test_mobile_chrome_on_every_page(self):
        for name in PAGES:
            txt = (SITE / name).read_text(encoding="utf-8")
            for needle in ('name="viewport"', 'lang="en"', "<title>",
                           'name="description"', "@media", "min-height:40px"):
                self.assertIn(needle, txt, f"{name} missing {needle}")

    def test_internal_links_resolve(self):
        import re
        for name in PAGES:
            txt = (SITE / name).read_text(encoding="utf-8")
            for href in re.findall(r'href="([^"#?]+)(?:[?#][^"]*)?"', txt):
                if href.startswith(("http", "mailto:", "tel:")):
                    continue
                target = (SITE / name).parent / href
                self.assertTrue(target.resolve().exists(), f"{name} -> {href}")

    def test_self_audit_pages_pass_mobile_and_link_checks(self):
        by_page = {m["page"]: m for m in self.audit["mobile_audit"]}
        link_by_page = {e["page"]: e for e in self.audit["link_audit"]}
        data_pages = {"coverage.html", "arithmetic.html", "reconciliation.html"}
        for name in PAGES:
            page = f"pickaudit/{name}"
            self.assertIn(page, by_page)
            self.assertEqual(by_page[page].get("failed", []), [], page)
            entry = link_by_page[page]
            self.assertEqual(entry["internal_broken"], [])
            self.assertEqual(entry["external_bad"], [])
            if name in data_pages:
                # data tables carry a source anchor in every fixture block
                self.assertEqual(entry["fixture_blocks_without_source"], [], page)

    def test_every_flagged_finding_has_a_source_link(self):
        txt = (SITE / "flagged.html").read_text(encoding="utf-8")
        for f in self.audit["findings"]:
            self.assertIn(f["id"], txt)
            if f.get("urls"):
                for url in f["urls"]:
                    if url.startswith("http"):
                        self.assertIn(url, txt, f"{f['id']} missing published url {url}")

    def test_executive_summary_links_to_live_pick_lists(self):
        txt = (SITE / "index.html").read_text(encoding="utf-8")
        for href in ("../everypick/picks.html", "../everypick/unresolved.html",
                     "../hotspawn-picks/picks.html", "coverage.html", "flagged.html"):
            self.assertIn(f'href="{href}"', txt)


class CiStateContract(unittest.TestCase):
    def test_known_red_tests_are_documented_not_masked(self):
        audit_doc = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        ci = audit_doc["ci"]
        self.assertIn("known_red_tests", ci)
        self.assertIsInstance(ci["known_red_tests"], list)
        self.assertLessEqual(len(ci["known_red_tests"]), 2)
        ids = {f["id"] for f in audit_doc["findings"]}
        self.assertIn("PA-CI-01", ids)  # green or red, the state must be published


if __name__ == "__main__":
    unittest.main(verbosity=2)
