"""Tests for session c0e223d3 (the `summary/` pick hub).

Scope: `scripts/c0e223d3/**`, `data/c0e223d3/**`, `summary/**`, `tests/test_c0e223d3.py`.
Nothing in another session's directory is required to pass except the published OURLINE board,
which this section reads as an input artifact and always attributes.
"""
import json
import math
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "c0e223d3"
SUMMARY = ROOT / "summary"
DATA = ROOT / "data" / "c0e223d3"

import sys

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import core_c0e223d3 as core  # noqa: E402
import aliases_c0e223d3 as aliases  # noqa: E402


def _board():
    path = DATA / "board.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _valve():
    by_name, meta = core.load_valve_teams(ROOT)
    return by_name, meta


# --------------------------------------------------------------------------- model arithmetic
class TestValveModel(unittest.TestCase):
    def test_valve_constants_match_published_formula(self):
        q = math.log(10) / 400.0
        g = 1.0 / math.sqrt(1.0 + 3.0 * q ** 2 * 75.0 ** 2 / math.pi ** 2)
        self.assertAlmostEqual(core.VALVE_Q, q, places=15)
        self.assertAlmostEqual(core.VALVE_G, g, places=12)
        self.assertAlmostEqual(core.VALVE_C, g * math.log(10) / 400.0, places=15)
        # The curve is documented as "400 point delta = 90%", so with RD applied it must be near it.
        self.assertGreater(core.vrs_prob(400, 0, 1.0), 0.85)

    def test_vrs_prob_is_symmetric(self):
        p = core.vrs_prob(1200, 1000, 0.36)
        q = core.vrs_prob(1000, 1200, 0.36)
        self.assertAlmostEqual(p, 1.0 - q, places=12)

    def test_vrs_prob_returns_none_without_both_ratings(self):
        self.assertIsNone(core.vrs_prob(None, 1000, 0.36))
        self.assertIsNone(core.vrs_prob(1000, None, 0.36))

    def test_equal_ratings_are_a_coin_flip(self):
        self.assertAlmostEqual(core.vrs_prob(1000, 1000, 0.36), 0.5, places=12)


class TestValveParsing(unittest.TestCase):
    def test_committed_valve_file_parses(self):
        by_name, meta = _valve()
        self.assertTrue(meta["n_teams"] > 100, "official standings file produced no rows")
        self.assertIn("spirit", by_name)
        self.assertEqual(by_name["spirit"]["points"], 2046)

    def test_teams_used_by_the_resolutions_are_real_rows(self):
        by_name, _ = _valve()
        for name in ("WBT", "ROUNDS", "BOJONG", "EAC", "ENCE", "HAVU", "Voca", "Phantom",
                     "FORZE Reload", "WBT Academy"):
            self.assertIn(name.casefold(), by_name, f"{name} missing from Valve's file")

    def test_lfo_ten_really_is_absent(self):
        """The one row we leave blank must be blank for a real reason."""
        by_name, _ = _valve()
        self.assertNotIn("lfo 10", by_name)
        for n in ("lfo 7", "lfo 8", "lfo 9"):
            self.assertIn(n, by_name)

    def test_parser_ignores_header_and_rule_rows(self):
        rows = core.parse_valve_markdown(
            "### Standings as of 2026_10_05\n"
            "| Standing | Points | Team Name | Roster | |\n"
            "| :- | -: | :- | :- | :- |\n"
            "| 1 | 2046 | Spirit | donk, magixx | [x](y) |\n"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["team"], "Spirit")
        self.assertEqual(rows[0]["standing"], 1)


# ----------------------------------------------------------------------------- name resolution
class TestResolutions(unittest.TestCase):
    def test_each_resolution_cites_at_least_two_sources(self):
        for entry in aliases.RESOLUTIONS:
            self.assertGreaterEqual(
                len(entry.get("evidence", [])), 2,
                f"{entry['hotspawn_name']} resolution has too little evidence",
            )

    def test_each_evidence_item_has_a_source_and_a_quote(self):
        for entry in aliases.RESOLUTIONS:
            for ev in entry["evidence"]:
                self.assertTrue(ev.get("url", "").startswith("https://"), ev)
                self.assertTrue(ev.get("quote"), ev)
                self.assertTrue(ev.get("source"), ev)

    def test_confirmed_resolutions_point_at_a_real_valve_row(self):
        by_name, _ = _valve()
        for entry in aliases.RESOLUTIONS:
            if entry["status"] != "confirmed":
                continue
            self.assertIn(entry["valve_name"].casefold(), by_name, entry["hotspawn_name"])

    def test_unresolved_entry_has_no_valve_name(self):
        for entry in aliases.RESOLUTIONS:
            if entry["status"] == "unresolved":
                self.assertIsNone(entry["valve_name"])
                self.assertTrue(entry.get("conflict"))

    def test_lookup_is_case_insensitive(self):
        self.assertIsNotNone(aliases.by_hotspawn_name("wrotberry"))
        self.assertIsNotNone(aliases.by_hotspawn_name("ROUNDSGG"))
        self.assertIsNone(aliases.by_hotspawn_name("Not A Team"))

    def test_every_resolution_names_the_fixtures_it_affects(self):
        for entry in aliases.RESOLUTIONS:
            self.assertTrue(entry.get("affects_fixtures"), entry["hotspawn_name"])


# ------------------------------------------------------------------------------- published data
class TestPublishedBoard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = _board()

    def setUp(self):
        if self.board is None:
            self.skipTest("data/c0e223d3/board.json not built yet")

    def test_every_row_has_an_official_source_link(self):
        for row in self.board["rows"]:
            self.assertTrue(row["source_links"], f"{row['fixture_id']} has no source link")
            for link in row["source_links"]:
                self.assertTrue(link["url"].startswith("https://"), link)

    def test_no_row_links_a_constructed_hotspawn_match_path(self):
        """Regression for the defect session 7cd2e67a found: /matches/<numeric id> is not a match page."""
        bad = re.compile(r"hotspawn\.com/matches/\d+$")
        for row in self.board["rows"]:
            for link in row["source_links"]:
                self.assertIsNone(bad.search(link["url"]), link["url"])

    def test_probabilities_sum_to_one_when_present(self):
        for row in self.board["rows"]:
            if row["prob_a"] is None:
                self.assertIsNone(row["prob_b"])
                self.assertIsNone(row["pick_team"])
                continue
            self.assertAlmostEqual(row["prob_a"] + row["prob_b"], 1.0, places=9)

    def test_pick_is_the_higher_probability(self):
        for row in self.board["rows"]:
            if row["prob_a"] is None:
                continue
            higher = row["team_a"] if row["prob_a"] >= row["prob_b"] else row["team_b"]
            self.assertEqual(row["pick_team"], higher)
            self.assertAlmostEqual(row["pick_prob"], max(row["prob_a"], row["prob_b"]), places=9)

    def test_blank_rows_state_a_reason(self):
        blanks = [r for r in self.board["rows"] if r["prob_a"] is None]
        for row in blanks:
            self.assertTrue(row["flags"], f"blank row {row['fixture_id']} has no reason")
            self.assertEqual(row["basis"], "none")

    def test_only_the_unresolvable_row_is_blank(self):
        blanks = [r["fixture_id"] for r in self.board["rows"] if r["prob_a"] is None]
        self.assertEqual(blanks, ["1079624"], "LFO 10 is the only team with no official rating")

    def test_summary_counters_match_the_rows(self):
        rows = self.board["rows"]
        s = self.board["summary"]
        self.assertEqual(s["open"], len(rows))
        self.assertEqual(s["with_pick"], sum(1 for r in rows if r["prob_a"] is not None))
        self.assertEqual(s["no_pick_flagged"], sum(1 for r in rows if r["prob_a"] is None))
        self.assertEqual(s["with_pick"] + s["no_pick_flagged"], s["open"])

    def test_resolved_flag_replaces_the_stale_not_in_vrs_flag(self):
        for row in self.board["rows"]:
            for flag in row["flags"]:
                self.assertFalse(
                    flag.startswith("not_in_vrs:") and flag.split(":", 1)[1] in
                    {e["hotspawn_name"] for e in aliases.RESOLUTIONS if e["status"] == "confirmed"},
                    f"stale flag survived a successful resolution: {flag}",
                )

    def test_vrs_resolved_rows_are_labelled_as_estimates(self):
        for row in self.board["rows"]:
            if row["basis"] == "vrs-resolved":
                self.assertIn("originated_estimate_not_a_market_price", row["flags"])
                self.assertTrue(row["resolved"])

    def test_rows_are_sorted_by_start_time(self):
        starts = [r["start_utc"] or "" for r in self.board["rows"]]
        self.assertEqual(starts, sorted(starts))

    def test_calibration_is_copied_not_invented(self):
        cal = self.board["calibration_used"]
        self.assertTrue(cal.get("fitted"))
        self.assertGreaterEqual(cal["n_pairs"], 6)
        self.assertGreater(0.25 <= cal["k"] <= 1.5, 0)

    def test_board_records_where_it_came_from(self):
        self.assertEqual(self.board["session"], "c0e223d3")
        self.assertEqual(self.board["source_board"], "data/f7279a54/board.json")
        self.assertTrue(self.board["valve_snapshot"]["snapshot"])


# --------------------------------------------------------------------------------- rendered site
class TestRenderedPages(unittest.TestCase):
    PAGES = ["index.html", "gaps.html", "sources.html", "method.html", "repo-review.html"]

    def test_pages_exist_and_are_html(self):
        for name in self.PAGES:
            path = SUMMARY / name
            self.assertTrue(path.is_file(), f"summary/{name} missing")
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.lstrip().startswith("<!DOCTYPE html>"))
            self.assertIn("</html>", text)

    def test_pages_are_mobile_first(self):
        for name in self.PAGES:
            text = (SUMMARY / name).read_text(encoding="utf-8")
            self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">',
                          text, f"{name} is not mobile-first")

    def test_stylesheet_exists_and_is_linked(self):
        self.assertTrue((SUMMARY / "assets" / "style.css").is_file())
        css = (SUMMARY / "assets" / "style.css").read_text(encoding="utf-8")
        self.assertIn("@media(max-width:699px)", css.replace(" ", ""))
        for name in self.PAGES:
            self.assertIn('href="assets/style.css"', (SUMMARY / name).read_text(encoding="utf-8"))

    def test_internal_links_resolve(self):
        link_re = re.compile(r'href="([^"#][^"]*)"')
        for name in self.PAGES:
            text = (SUMMARY / name).read_text(encoding="utf-8")
            for url in link_re.findall(text):
                if url.startswith(("http://", "https://", "mailto:")):
                    continue
                target = (SUMMARY / url.split("#")[0]).resolve()
                self.assertTrue(target.exists(), f"{name} -> {url} is broken")

    def test_index_links_every_other_page(self):
        text = (SUMMARY / "index.html").read_text(encoding="utf-8")
        for name in self.PAGES[1:]:
            self.assertIn(f'href="{name}"', text)

    def test_index_links_the_main_dashboard(self):
        text = (SUMMARY / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="../index.html"', text)

    def test_repo_review_publishes_the_checks(self):
        text = (SUMMARY / "repo-review.html").read_text(encoding="utf-8")
        self.assertIn("R-C0-1", text)
        self.assertIn("PASS", text)

    def test_no_unescaped_python_repr_leaks_into_the_pages(self):
        for name in self.PAGES:
            text = (SUMMARY / name).read_text(encoding="utf-8")
            self.assertNotIn("None", text.replace("&mdash;", ""), f"{name} leaked a None value")


if __name__ == "__main__":
    unittest.main()
