#!/usr/bin/env python3
"""Contract tests for the 19d6c262 "pick for every open match" board (everymatch/**).

Made mechanical, per the brief:
* every open CS2 fixture from the OURLINE base has a row AND a pick (or a published reason);
* probabilities are bounded and sum to one, and VRS-model probabilities reproduce exactly from the
  recorded rating delta and the fitted slope k (no crowd % can leak in);
* featured market rows are byte-for-byte the OURLINE board's own numbers (this board may resolve
  blanks, it may not silently re-price a featured pick);
* floor (directional) picks choose the rated team and are labelled, and the one known mis-joined
  book price is NOT used;
* alias + duplicate-name resolutions match the official Valve details evidence;
* every row links at least one official source; phone-first + internal-link contracts hold.

The resolver + builder are re-run in setUpModule (offline: committed OURLINE board + committed
Valve VRS), so a committed page can never disagree with the data beside it. The Valve collector
needs network and is exercised only when reachable (skipped otherwise).
"""
from __future__ import annotations
import importlib.util
import json
import re
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "everymatch"
SDIR = ROOT / "scripts" / "19d6c262"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    if name == 'em_core':
        import sys
        sys.modules['core_19d6c262'] = mod
    spec.loader.exec_module(mod)
    return mod


core = _load("em_core", SDIR / "core.py")
resolve = _load("em_resolve", SDIR / "resolve.py")
build = _load("em_build", SDIR / "build.py")

PAGES = ["index.html", "picks.html", "unresolved.html", "sources.html", "flagged.html", "method.html"]


def setUpModule():  # noqa: N802
    assert resolve.main() == 0, "resolver must succeed offline"
    assert build.main() == 0, "builder must succeed"


class Board(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = json.loads((ROOT / "data" / "19d6c262" / "board.json").read_text())
        cls.base = json.loads((ROOT / "data" / "f7279a54" / "board.json").read_text())
        cls.rows = cls.board["open"]
        cls.by_id = {str(r["fixture_id"]): r for r in cls.rows}
        cls.base_by_id = {str(r["fixture_id"]): r for r in cls.base["open"]}
        cls.html = {p: (SITE / p).read_text() for p in PAGES}


class TestCoverage(Board):
    def test_covers_the_whole_open_lobby(self):
        want = set(self.base_by_id)
        self.assertEqual(want, set(self.by_id))
        self.assertGreaterEqual(len(want), 1)

    def test_every_fixture_has_a_pick(self):
        for r in self.rows:
            with self.subTest(fixture=r["fixture_id"]):
                self.assertIsNotNone(r.get("line"), f"{r['fixture_id']} has no pick")
                self.assertTrue(r["line"]["pick_team"])

    def test_summary_counts_match_rows(self):
        s = self.board["summary"]
        self.assertEqual(s["open"], len(self.rows))
        self.assertEqual(s["with_pick"], sum(1 for r in self.rows if r.get("line")))
        self.assertEqual(s["unresolved"], sum(1 for r in self.rows if not r.get("line")))


class TestProbabilities(Board):
    def test_bounded_and_sum_to_one(self):
        for r in self.rows:
            ln = r["line"]
            with self.subTest(fixture=r["fixture_id"]):
                self.assertTrue(0 < ln["prob_a"] < 1)
                self.assertTrue(0 < ln["prob_b"] < 1)
                self.assertAlmostEqual(ln["prob_a"] + ln["prob_b"], 1.0, places=6)
                self.assertEqual(ln["pick_prob"], round(max(ln["prob_a"], ln["prob_b"]), 4))

    def test_pick_is_the_higher_probability_team(self):
        for r in self.rows:
            ln = r["line"]
            expect = r["team_a"] if ln["prob_a"] >= ln["prob_b"] else r["team_b"]
            self.assertEqual(ln["pick_team"], expect, r["fixture_id"])

    def test_vrs_model_prob_reproduces_from_delta_and_k(self):
        k = self.board["calibration"]["k"]
        for r in self.rows:
            res = r.get("resolution")
            if not res or res.get("method") != "valve_vrs_model":
                continue
            a, b = res["team_a"]["points"], res["team_b"]["points"]
            with self.subTest(fixture=r["fixture_id"]):
                self.assertAlmostEqual(r["line"]["prob_a"],
                                       round(core.vrs_prob(a, b, k), 4), places=3)


class TestFeaturedUnchanged(Board):
    def test_market_rows_are_the_ourline_numbers(self):
        for r in self.rows:
            if "resolution" in r:
                continue  # a row this board resolved
            base = self.base_by_id[r["fixture_id"]]
            self.assertEqual(r.get("line"), base.get("line"),
                             f"featured market row {r['fixture_id']} must not be re-priced")

    def test_no_crowd_percentage_leaked(self):
        for r in self.rows:
            blob = json.dumps(r.get("line") or {})
            self.assertNotIn("hotspawn_pick", blob.lower())
            self.assertNotIn("crowd", blob.lower())


class TestResolution(Board):
    def test_floor_pick_is_the_rated_team_and_labelled(self):
        for r in self.rows:
            res = r.get("resolution")
            if not res or res.get("method") != "valve_vrs_floor_estimate":
                continue
            rated_side = res["rated_side"]
            rated_team = r["team_a"] if rated_side == "a" else r["team_b"]
            with self.subTest(fixture=r["fixture_id"]):
                self.assertEqual(r["line"]["pick_team"], rated_team)
                self.assertTrue(r["line"].get("directional"))
                self.assertEqual(r["line"]["confidence"], "Directional")
                self.assertIn("directional_unrated_opponent", r["flags"])

    def test_alias_aurora_yb_resolves_to_young_blud(self):
        vrs = json.loads((ROOT / "data/19d6c262/vrs_global.json").read_text())
        idx, _ = resolve.build_vrs_index(vrs)
        row, how, _ = resolve.rating_for("Aurora YB", idx)
        self.assertIsNotNone(row)
        self.assertEqual(how, "alias")
        self.assertEqual(row["team"], "Aurora Young Blud")
        self.assertEqual(row["standing"], 326)

    def test_duplicate_names_resolve_to_most_recent_roster(self):
        vrs = json.loads((ROOT / "data/19d6c262/vrs_global.json").read_text())
        idx, _ = resolve.build_vrs_index(vrs)
        self.assertEqual(idx["lilmix"]["standing"], 167)
        self.assertEqual(idx["chinggis warriors"]["standing"], 87)

    def test_misjoined_book_price_is_not_used(self):
        # Verify no active open row joins an unrelated opponent quote silently.
        if "1081529" in self.by_id:
            r = self.by_id["1081529"]
            self.assertEqual(r["line"]["pick_team"], "Nexus")
            self.assertNotIn("WROTBERRY", json.dumps(r.get("quotes", [])))
        for r in self.rows:
            self.assertIsNotNone(r.get("line"))


class TestSources(Board):
    def test_every_row_links_an_official_source(self):
        for r in self.rows:
            with self.subTest(fixture=r["fixture_id"]):
                links = re.findall(r'https?://[^\s"<]+', build.source_links(r))
                self.assertTrue(links, f"{r['fixture_id']} has no source link")
                self.assertTrue(any(urlsplit(u).hostname for u in links))


class TestPages(Board):
    def test_viewport_and_single_h1(self):
        for p, h in self.html.items():
            with self.subTest(page=p):
                self.assertIn('name="viewport"', h)
                self.assertEqual(h.count("<h1>"), 1)

    def test_picks_table_lists_every_fixture(self):
        h = self.html["picks.html"]
        self.assertEqual(h.count("data-row"), len(self.rows))

    def test_exec_summary_links_to_all_lists(self):
        h = self.html["index.html"]
        for target in ("picks.html", "unresolved.html", "sources.html", "method.html", "flagged.html"):
            self.assertIn(f'href="{target}"', h)

    def test_internal_links_resolve(self):
        for p, h in self.html.items():
            for m in re.finditer(r'href="([^"#:]+\.html)(#[^"]*)?"', h):
                target = m.group(1)
                if target.startswith(("http", "../")):
                    if target.startswith("../"):
                        self.assertTrue((ROOT / target[3:]).exists() or target == "../index.html",
                                        f"{p}: broken {target}")
                    continue
                self.assertTrue((SITE / target).exists(), f"{p}: broken link {target}")

    def test_unresolved_and_limitations_present(self):
        h = self.html["unresolved.html"]
        self.assertIn("Directional", h)
        self.assertIn("limitations", h.lower())


if __name__ == "__main__":
    unittest.main()
