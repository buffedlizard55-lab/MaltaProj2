"""Tests for the day-5 desk (session 7900154b).

Every assertion is about a verifiable property of the generated pages, the generated
board and the pure helpers: inventory equality with the live lobby read, arithmetic, the
presence of a source for every published number, the contrarian rule, and mobile/link
integrity. Nothing here re-derives an external price, and nothing here asserts a number
that is not in the board.
"""
import importlib.util
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Loaded as a private module so this test never changes the import path other sessions'
# tests rely on.
_core_spec = importlib.util.spec_from_file_location(
    "day5_core_7900154b", ROOT / "scripts" / "7900154b" / "core.py")
core = importlib.util.module_from_spec(_core_spec)
_core_spec.loader.exec_module(core)

DESK = ROOT / "day5"
BOARD = json.loads((DESK / "data" / "board.json").read_text(encoding="utf-8"))
LOBBY = json.loads((ROOT / "data/7900154b/lobby.json").read_text(encoding="utf-8"))
TWC = json.loads((ROOT / "data/7900154b/twc.json").read_text(encoding="utf-8"))
PAGES = ("index.html", "picks.html", "twc.html", "unresolved.html", "flagged.html",
         "method.html")
PRICE_SOURCES = {"pinnacle", "bovada", "melbet", "thunderpick_bo3"}


def text_of(name):
    return (DESK / name).read_text(encoding="utf-8")


class PagesExist(unittest.TestCase):
    def test_every_page_is_present_and_non_trivial(self):
        for name in PAGES:
            path = DESK / name
            self.assertTrue(path.exists(), name)
            self.assertGreater(len(path.read_text(encoding="utf-8")), 2000, name)

    def test_every_page_is_mobile_first(self):
        for name in PAGES:
            html = text_of(name)
            self.assertIn('name="viewport"', html, name)
            self.assertIn("width=device-width", html, name)
            self.assertIn("initial-scale=1", html, name)

    def test_every_page_carries_the_tab_navigation(self):
        for name in PAGES:
            html = text_of(name)
            for target in ("index.html", "picks.html", "twc.html", "unresolved.html",
                           "flagged.html", "method.html"):
                self.assertIn(f'href="{target}"', html, f"{name} -> {target}")

    def test_html_is_balanced(self):
        void = {"meta", "br", "img", "hr", "input", "link", "i"}
        for name in PAGES:
            html = text_of(name)
            stack = []
            for m in re.finditer(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)[^>]*?(/?)>", html):
                close, tag, selfclose = m.group(1), m.group(2).lower(), m.group(3)
                if tag in void or selfclose == "/":
                    continue
                if close:
                    self.assertTrue(stack, f"{name}: stray </{tag}>")
                    self.assertEqual(stack.pop(), tag, f"{name}: mismatched </{tag}>")
                else:
                    stack.append(tag)
            self.assertEqual(stack, [], f"{name}: unclosed {stack[:3]}")


class Inventory(unittest.TestCase):
    def test_one_row_per_lobby_card_that_is_still_open(self):
        lobby_ids = {str(c["fixture_id"]) for c in LOBBY["cards"]}
        desk_ids = {str(r["fixture_id"]) for r in BOARD["rows"]}
        self.assertTrue(desk_ids <= lobby_ids,
                        f"rows not on the lobby: {sorted(desk_ids - lobby_ids)}")

    def test_a_locked_fixture_is_never_published_as_pickable(self):
        for r in BOARD["rows"]:
            self.assertTrue(r.get("lock_utc"), r["fixture_id"])
            self.assertLess(r["lock_utc"], r["start_utc"])  # the lock is before the start
        desk_ids = {str(r["fixture_id"]) for r in BOARD["rows"]}
        self.assertNotIn("1082021", desk_ids,
                         "1082021 locked at 2026-10-17T18:54Z and must not be published")

    def test_every_row_has_a_source_link(self):
        for r in BOARD["rows"]:
            self.assertTrue(r.get("sources"), r["fixture_id"])
            for s in r["sources"]:
                self.assertTrue(s.get("url"), r["fixture_id"])
                self.assertTrue(str(s["url"]).startswith("http"), r["fixture_id"])

    def test_the_two_day5_matches_are_featured(self):
        ids = {r["fixture_id"] for r in BOARD["featured"]}
        self.assertEqual(ids, {"twc-third_place", "twc-grand_final"})
        final = next(r for r in BOARD["featured"] if r["fixture_id"] == "twc-grand_final")
        self.assertEqual(final["team_a"], "FURIA")
        self.assertEqual(final["team_b"], "BETBOOM")


class Arithmetic(unittest.TestCase):
    def test_probabilities_are_two_way(self):
        for r in BOARD["rows"] + BOARD["featured"]:
            if r.get("prob_a") is None:
                self.assertIsNone(r.get("prob_b"), r["fixture_id"])
                continue
            self.assertAlmostEqual(r["prob_a"] + r["prob_b"], 1.0, places=6,
                                   msg=r["fixture_id"])
            self.assertTrue(0 < r["prob_a"] < 1, r["fixture_id"])

    def test_a_row_without_a_probability_has_no_pick(self):
        for r in BOARD["rows"]:
            if r.get("prob_a") is None:
                self.assertIsNone(r.get("pick"), r["fixture_id"])
                self.assertTrue(r.get("unresolved_reason"), r["fixture_id"])

    def test_a_row_with_a_probability_has_a_pick(self):
        for r in BOARD["rows"]:
            if r.get("prob_a") is not None:
                self.assertIn(r.get("pick"), (r.get("team_a"), r.get("team_b")),
                              r["fixture_id"])

    def test_no_vig_removes_the_margin(self):
        nv = core.no_vig(1.5, 2.5)
        self.assertAlmostEqual(nv["prob_a"] + nv["prob_b"], 1.0, places=9)
        self.assertGreater(nv["overround"], 0)

    def test_a_one_sided_or_broken_price_is_rejected(self):
        self.assertIsNone(core.no_vig(1.5, None))
        self.assertIsNone(core.no_vig(1.0, 2.0))
        self.assertIsNone(core.no_vig("x", 2.0))


class BasisIsHonest(unittest.TestCase):
    def test_a_market_row_uses_only_real_book_prices(self):
        for r in BOARD["rows"]:
            if r.get("basis") != "market":
                continue
            for q in r.get("quotes") or []:
                self.assertIn(q.get("source_key"), PRICE_SOURCES | {"kalshi"},
                              r["fixture_id"])

    def test_an_unresolved_row_names_the_reason(self):
        unresolved = [r for r in BOARD["rows"] if r.get("basis") == "none"]
        for r in unresolved:
            self.assertIn("Valve", r["unresolved_reason"])
            self.assertIn("book", r["unresolved_reason"])

    def test_a_bound_row_says_which_side_is_unrated(self):
        for r in BOARD["rows"]:
            if r.get("basis") != "bound":
                continue
            self.assertIn("not in Valve's list", r["basis_detail"])
            self.assertIn("floor", r["basis_detail"])

    def test_a_model_row_is_labelled_as_a_model(self):
        for r in BOARD["rows"]:
            if r.get("basis") != "model":
                continue
            self.assertIn("not a bookmaker price", r["basis_detail"])

    def test_the_calibration_is_published_with_its_error(self):
        cal = BOARD.get("calibration") or {}
        self.assertGreaterEqual(cal.get("n_pairs", 0), 6)
        self.assertTrue(cal.get("fitted"))
        self.assertTrue(0 < cal.get("k", 0) < 1.5)
        self.assertLess(cal["mae_prob"], cal["mae_prob_valve"],
                        "the fitted slope must beat Valve's raw slope")


class PickRule(unittest.TestCase):
    def test_the_pick_is_the_more_likely_side(self):
        for r in BOARD["rows"]:
            if r.get("prob_a") is None:
                continue
            expected = r["team_a"] if r["prob_a"] >= r["prob_b"] else r["team_b"]
            self.assertEqual(r["pick"], expected, r["fixture_id"])

    def test_a_climb_clears_the_floor_the_crowd_cap_and_the_edge(self):
        for r in BOARD["rows"]:
            climb = r.get("climb")
            if not climb:
                continue
            self.assertGreaterEqual(climb["prob"], core.CONTRARIAN_FLOOR - 1e-9,
                                    r["fixture_id"])
            crowd = r["crowd_a"] if climb["team"] == r["team_a"] else r["crowd_b"]
            self.assertLessEqual(crowd, core.CROWD_ELSEWHERE * 100 + 1e-9, r["fixture_id"])
            self.assertGreaterEqual(climb["prob"] - crowd / 100.0,
                                    core.CONTRARIAN_MIN_EDGE - 1e-9, r["fixture_id"])

    def test_a_refused_climb_publishes_its_reason(self):
        for r in BOARD["rows"]:
            if r.get("climb") or r.get("prob_a") is None:
                continue
            self.assertTrue(r.get("climb_rejected"), r["fixture_id"])

    def test_the_crowd_is_never_used_as_a_probability(self):
        for r in BOARD["rows"]:
            if r.get("prob_a") is None:
                continue
            for q in r.get("quotes") or []:
                self.assertNotEqual(q.get("source_key"), "hotspawn", r["fixture_id"])
            self.assertNotEqual(r.get("basis"), "crowd", r["fixture_id"])


class TwcResearch(unittest.TestCase):
    def test_every_day_one_to_four_result_has_a_source(self):
        for day in TWC["days"]:
            for r in day["results"]:
                self.assertTrue(r.get("hltv_url"), r)
                self.assertTrue(str(r["hltv_url"]).startswith("https://www.hltv.org/matches/"),
                                r)
                self.assertTrue(r.get("verified_by"), r)

    def test_the_scores_are_ordered(self):
        for day in TWC["days"]:
            for r in day["results"]:
                self.assertIn(r["score_a"], (0, 1, 2), r)
                self.assertIn(r["score_b"], (0, 1, 2), r)

    def test_the_two_day5_fixtures_are_verified(self):
        for m in TWC["day5"]["matches"]:
            self.assertTrue(m.get("hltv_url"), m)
            self.assertTrue(m.get("bo3_url"), m)
            self.assertTrue(m.get("verified_by"), m)
            self.assertIn(m["best_of"], (3, 5), m)

    def test_the_roster_premise_is_recorded_not_dropped(self):
        rp = TWC["roster_premise"]
        self.assertEqual(rp["verdict"], "not_supported")
        self.assertTrue(rp["checked"])
        for c in rp["checked"]:
            self.assertTrue(str(c["url"]).startswith("https://"), c)

    def test_every_flag_has_sources(self):
        self.assertTrue(TWC["flags"])
        for f in TWC["flags"]:
            self.assertTrue(f.get("id"))
            self.assertTrue(f.get("sources"), f["id"])
            for s in f["sources"]:
                self.assertTrue(str(s["url"]).startswith("https://"), f["id"])


class Coverage(unittest.TestCase):
    def test_the_summary_counts_add_up(self):
        s = BOARD["summary"]
        total = (s["market"] + s["exchange"] + s["model"] + s["bound"] + s["unresolved"])
        self.assertEqual(total, s["open"])
        self.assertEqual(s["open"], len(BOARD["rows"]))

    def test_unresolved_rows_are_listed_on_the_unresolved_page(self):
        unresolved = [r for r in BOARD["rows"] if r.get("basis") == "none"]
        html = text_of("unresolved.html")
        for r in unresolved:
            self.assertIn(r["team_a"], html)
            self.assertIn(r["team_b"], html)

    def test_every_row_appears_on_the_picks_page(self):
        html = text_of("picks.html")
        for r in BOARD["rows"]:
            self.assertIn(f'id="{r["fixture_id"]}"', html, r["fixture_id"])

    def test_the_summary_links_to_every_subpage(self):
        html = text_of("index.html")
        for target in ("picks.html", "twc.html", "unresolved.html", "flagged.html",
                       "method.html"):
            self.assertIn(f'href="{target}"', html, target)

    def test_the_exec_summary_surfaces_the_unresolved_section(self):
        html = text_of("index.html")
        self.assertIn("Unresolved", html)
        self.assertIn('href="unresolved.html"', html)

    def test_no_internal_link_is_broken(self):
        for name in PAGES:
            html = text_of(name)
            for href in re.findall(r'href="([^"]+)"', html):
                if href.startswith("http") or href.startswith("#"):
                    continue
                target = (DESK / href.split("#")[0])
                self.assertTrue(target.exists(), f"{name} -> {href}")

    def test_the_source_links_are_absolute(self):
        for name in PAGES:
            html = text_of(name)
            for href in re.findall(r'href="([^"]+)"', html):
                if href.startswith("#") or ".html" in href:
                    continue
                self.assertTrue(href.startswith("https://"), f"{name} -> {href}")


if __name__ == "__main__":
    unittest.main()
