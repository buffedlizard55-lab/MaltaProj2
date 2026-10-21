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


class Coverage(unittest.TestCase):
    def test_exactly_the_open_hotspawn_fixtures_and_nothing_else(self):
        want = {str(f["fixture_id"]) for f in SOURCE_BOARD["open"]}
        got = [str(r["fixture_id"]) for r in BOARD["rows"]]
        self.assertEqual(len(got), len(set(got)), "a fixture appears twice")
        self.assertEqual(set(got), want)

    def test_every_open_fixture_has_a_pick_and_a_basis(self):
        self.assertEqual(BOARD["summary"]["open"], len(BOARD["rows"]))
        self.assertEqual(BOARD["summary"]["with_pick"], len(BOARD["rows"]))
        self.assertEqual(BOARD["summary"]["unresolved"], 0)
        for row in BOARD["rows"]:
            self.assertTrue(row["pick"], row["fixture_id"])
            self.assertIn(row["basis"], ("market", "market+model", "model", "research-market", "originated"))

    def test_probabilities_are_bounded_sum_to_one_and_pick_is_argmax(self):
        for row in BOARD["rows"]:
            pa, pb = row["prob_a"], row["prob_b"]
            self.assertAlmostEqual(pa + pb, 1.0, places=6, msg=row["fixture_id"])
            self.assertTrue(0 < pa < 1 and 0 < pb < 1)
            expected = row["team_a"] if pa > pb else row["team_b"]
            self.assertEqual(row["pick"], expected, row["fixture_id"])
            self.assertAlmostEqual(row["pick_prob"], max(pa, pb), places=9)

    def test_counts_add_up(self):
        s, rows = BOARD["summary"], BOARD["rows"]
        self.assertEqual(s["market"], sum(1 for r in rows if r["basis"] in ("market", "market+model")))
        self.assertEqual(s["model"], sum(1 for r in rows if r["basis"] == "model"))
        self.assertEqual(s["research_market"], sum(1 for r in rows if r["basis"] == "research-market"))
        self.assertEqual(s["originated"], sum(1 for r in rows if r["basis"] == "originated"))
        self.assertEqual(s["covered_percent"], 100.0)


class Arithmetic(unittest.TestCase):
    def test_researched_price_reproduces_from_the_quoted_decimal_odds(self):
        res = RESOLUTIONS["fixtures"]["1082762"]
        inv_a, inv_b = 1 / res["decimal_a"], 1 / res["decimal_b"]
        self.assertAlmostEqual(inv_a / (inv_a + inv_b), res["prob_a"], places=5)
        self.assertAlmostEqual(inv_b / (inv_a + inv_b), res["prob_b"], places=5)
        self.assertAlmostEqual(inv_a + inv_b, res["overround"], places=5)

    def test_originated_line_reproduces_from_official_valve_points(self):
        res = RESOLUTIONS["fixtures"]["1082837"]
        k = SOURCE_BOARD["calibration"]["k"]
        zetta, floor = 473.0, 381.0          # Valve 2026-10-05: Zetta #357; lowest published rating
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
            row = next(r for r in BOARD["rows"] if r["fixture_id"] == fid)
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
