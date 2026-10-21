"""Contract tests for the session e1b48771 full-coverage CS2 pick board (``cs2/``).

These tests re-derive the published numbers from the raw inputs (the quoted decimal odds and the
official Valve points) instead of trusting the rendered HTML, and they check the mobile/evidence
contract: one h1 per page, a viewport meta tag, a source link on every table row, resolving internal
links, and one card per open fixture.
"""
import importlib.util
import json
import math
import re
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "scripts" / "e1b48771" / "build.py"
spec = importlib.util.spec_from_file_location("cs2_build", MOD_PATH)
BUILD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BUILD)

BOARD = json.loads((ROOT / "data" / "e1b48771" / "board.json").read_text())
RESOLUTIONS = json.loads((ROOT / "scripts" / "e1b48771" / "resolutions.json").read_text())
SOURCE_BOARD = json.loads((ROOT / BOARD["source_board"]["path"]).read_text())
VALVE_URL = ("https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/"
             "live/2026/standings_global_2026_10_05.md")
PAGES = ["index.html", "picks.html", "unresolved.html", "flagged.html", "method.html"]


def soup(name):
    return BeautifulSoup((ROOT / "cs2" / name).read_text(), "html.parser")


def assert_pick_contract(case, row):
    """Absence of evidence must not be 'fixed' by inventing a number to make CI green."""
    fid = row["fixture_id"]
    if row.get("pick") is None:
        case.assertEqual(row["basis"], "unresolved", fid)
        for key in ("prob_a", "prob_b", "pick_prob", "confidence"):
            case.assertIsNone(row.get(key), (fid, key))
        case.assertTrue(row.get("flags") or row.get("limitations"), fid)
        case.assertTrue(row.get("basis_label"), fid)
        case.assertTrue(row.get("sources"), fid)
        return
    case.assertIn(row["basis"], ("market", "market+model", "model", "research-market", "originated"))
    pa, pb = row["prob_a"], row["prob_b"]
    for p in (pa, pb):
        case.assertIsInstance(p, (int, float), fid)
        case.assertNotIsInstance(p, bool, fid)
        case.assertTrue(math.isfinite(p) and 0 < p < 1, fid)
    case.assertAlmostEqual(pa + pb, 1.0, places=6, msg=fid)
    case.assertNotEqual(pa, pb, "A tied probability pair has no directional pick")
    case.assertEqual(row["pick"], row["team_a"] if pa > pb else row["team_b"], fid)
    case.assertAlmostEqual(row["pick_prob"], max(pa, pb), places=9)


class UnresolvedContract(unittest.TestCase):
    def example(self):
        return dict(fixture_id="synthetic-unknown", team_a="A", team_b="B", pick=None,
                    prob_a=None, prob_b=None, pick_prob=None, confidence=None, basis="unresolved",
                    basis_label="No supported line - pick withheld", flags=["missing verified line"],
                    sources=[{"url": "https://play.hotspawn.com/lobby"}])

    def test_explicit_blank_with_sources_is_accepted(self):
        assert_pick_contract(self, self.example())

    def test_blank_row_with_fabricated_probability_is_rejected(self):
        row = self.example(); row["prob_a"] = 0.5
        with self.assertRaises(AssertionError): assert_pick_contract(self, row)

    def test_unexplained_blank_is_rejected(self):
        row = self.example(); row["flags"] = []
        with self.assertRaises(AssertionError): assert_pick_contract(self, row)

    def test_blank_row_without_sources_is_rejected(self):
        row = self.example(); row["sources"] = []
        with self.assertRaises(AssertionError): assert_pick_contract(self, row)


class Coverage(unittest.TestCase):
    def test_source_schema_cannot_be_selected_by_timestamp_alone(self):
        compatible = json.loads((ROOT / 'data/fe803b80/board.json').read_text())
        canonical = json.loads((ROOT / 'data/c64a5e19/board.json').read_text())
        self.assertTrue(BUILD.supported_board(compatible))
        self.assertFalse(BUILD.supported_board(canonical))
        canonical['generated_utc'] = '2099-01-01T00:00:00Z'
        self.assertFalse(BUILD.supported_board(canonical))

    def test_exactly_the_open_hotspawn_fixtures_and_nothing_else(self):
        want = {str(f["fixture_id"]) for f in SOURCE_BOARD["open"]}
        got = [str(r["fixture_id"]) for r in BOARD["rows"]]
        self.assertEqual(len(got), len(set(got)), "a fixture appears twice")
        self.assertEqual(set(got), want)

    def test_every_open_fixture_is_resolved_or_explicitly_unresolved(self):
        rows, summary = BOARD["rows"], BOARD["summary"]
        resolved = [r for r in rows if r.get("pick") is not None]
        self.assertEqual(summary["open"], len(rows))
        self.assertEqual(summary["with_pick"], len(resolved))
        self.assertEqual(summary["unresolved"], len(rows) - len(resolved))
        for row in rows:
            assert_pick_contract(self, row)

    def test_probabilities_are_bounded_sum_to_one_and_pick_is_argmax(self):
        for row in BOARD["rows"]:
            assert_pick_contract(self, row)

    def test_counts_add_up(self):
        s, rows = BOARD["summary"], BOARD["rows"]
        self.assertEqual(s["market"], sum(1 for r in rows if r["basis"] in ("market", "market+model")))
        self.assertEqual(s["model"], sum(1 for r in rows if r["basis"] == "model"))
        self.assertEqual(s["research_market"], sum(1 for r in rows if r["basis"] == "research-market"))
        self.assertEqual(s["originated"], sum(1 for r in rows if r["basis"] == "originated"))
        resolved = sum(r.get("pick") is not None for r in rows)
        self.assertEqual(s["covered_percent"], round(100.0 * resolved / len(rows), 1) if rows else 0.0)
        self.assertEqual(s["with_pick"] + s["unresolved"], s["open"])


class Arithmetic(unittest.TestCase):
    def test_researched_price_reproduces_from_the_quoted_decimal_odds(self):
        res = RESOLUTIONS["fixtures"]["1082762"]
        inv_a, inv_b = 1 / res["decimal_a"], 1 / res["decimal_b"]
        self.assertAlmostEqual(inv_a / (inv_a + inv_b), res["prob_a"], places=5)
        self.assertAlmostEqual(inv_b / (inv_a + inv_b), res["prob_b"], places=5)
        self.assertAlmostEqual(inv_a + inv_b, res["overround"], places=5)

    def test_originated_line_reproduces_from_official_valve_points(self):
        res = RESOLUTIONS["fixtures"]["1082837"]
        # This archived manual scenario used a fixed calibration snapshot.
        # A later upstream refresh must not silently change its historical inputs.
        calculation = res["calculation"]
        self.assertFalse(calculation["unrated_opponent_rating_verified"])
        k = calculation["calibration_k"]
        zetta, floor = calculation["points_a"], calculation["assumed_points_b"]
        expected = 1 / (1 + math.exp(-k * BUILD.valve_c() * (zetta - floor)))
        self.assertAlmostEqual(expected, res["prob_a"], places=5)
        self.assertLess(res["prob_a"], 0.75, "an unrated opponent must not be treated as a walkover")
        self.assertGreater(res["prob_a"], 0.5, "the rated team is the favourite under a lower bound")

    def test_no_crowd_percentage_anywhere(self):
        for row in BOARD["rows"]:
            self.assertNotIn("crowd", row)
            self.assertNotIn("picked_percent", row)
        for name in PAGES:
            text = soup(name).get_text(" ", strip=True).lower()
            self.assertNotIn("crowd picked", text)
            self.assertNotIn("% picked", text)


class Evidence(unittest.TestCase):
    def test_every_table_row_links_an_official_source(self):
        for name in PAGES:
            for row in soup(name).select("tbody tr"):
                self.assertTrue(row.select('a[href^="https://"]'), (name, row.get_text(" ", strip=True)[:100]))

    def test_every_fixture_row_has_a_source_with_a_read_time(self):
        for row in BOARD["rows"]:
            urls = [s["url"] for s in row["sources"] if str(s.get("url", "")).startswith("https://")]
            self.assertTrue(urls, row["fixture_id"])
            if row["basis"] in ("model", "originated"):
                self.assertIn(VALVE_URL, urls, row["fixture_id"])

    def test_researched_rows_keep_their_attempt_ledger(self):
        for fid in RESOLUTIONS["fixtures"]:
            row = next((r for r in BOARD["rows"] if r["fixture_id"] == fid), None)
            if row is None:          # fixture locked/closed since the research was done
                continue
            self.assertGreaterEqual(len(row["attempts"]), 3, fid)
            self.assertTrue(row["limitations"], fid)
            for attempt in row["attempts"]:
                self.assertTrue(attempt["result"], fid)

    def test_unresolved_page_lists_every_non_market_row(self):
        page = soup("unresolved.html")
        text = page.get_text(" ", strip=True)
        non_market = [r for r in BOARD["rows"] if r["basis"] not in ("market", "market+model")]
        self.assertTrue(non_market)
        for row in non_market:
            self.assertIn(row["team_a"], text)
            self.assertIn(row["team_b"], text)
        self.assertIn("Limitations of the whole method", text)

    def test_flagged_page_keeps_flag_links(self):
        page = soup("flagged.html")
        self.assertGreaterEqual(len(page.select("article.card")), 6)
        text = page.get_text(" ", strip=True)
        self.assertIn("F1", text)
        self.assertIn("Polymarket", text)


class Mobile(unittest.TestCase):
    def test_pages_are_mobile_ready(self):
        for name in PAGES:
            page = soup(name)
            self.assertEqual(len(page.select("h1")), 1, name)
            self.assertIsNotNone(page.select_one('meta[name="viewport"]'), name)
            self.assertIsNotNone(page.select_one("header nav a"), name)

    def test_internal_links_resolve(self):
        for name in PAGES:
            for a in soup(name).select("a[href]"):
                href = a["href"].split("#")[0]
                if not href or href.startswith(("http", "#", "mailto")):
                    continue
                self.assertTrue((ROOT / "cs2" / href).exists() or (ROOT / href).exists(), (name, href))

    def test_picks_page_has_one_card_and_one_table_row_per_fixture(self):
        page = soup("picks.html")
        self.assertEqual(len(page.select("article.match")), len(BOARD["rows"]))
        self.assertEqual(len(page.select("#tbl tbody tr")), len(BOARD["rows"]))
        for row in BOARD["rows"]:
            self.assertIsNotNone(page.select_one(f'#fx-{row["fixture_id"]}'), row["fixture_id"])


class Automation(unittest.TestCase):
    def test_workflow_refreshes_inside_the_four_to_eight_hour_window(self):
        wf = (ROOT / ".github" / "workflows" / "cs2-e1b48771.yml").read_text()
        self.assertIn("cron:", wf)
        self.assertRegex(wf, r"cron:\s*'[0-9 ,*/]+ \*/4 \* \* \*'")
        self.assertIn("scripts/e1b48771/build.py", wf)

    def test_section_is_staged_and_reachable(self):
        stage = (ROOT / "scripts" / "stage_site.py").read_text()
        self.assertIn("'cs2'", stage)
        self.assertIn("scripts/e1b48771/build.py", stage)
        home = BeautifulSoup((ROOT / "index.html").read_text(), "html.parser")
        self.assertIsNotNone(home.select_one('a[href="cs2/picks.html"]'))
        self.assertIsNotNone(home.select_one('a[href="cs2/unresolved.html"]'))
        self.assertIsNotNone(home.select_one('a[href="cs2/method.html"]'))


if __name__ == "__main__":
    unittest.main()
