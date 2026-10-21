#!/usr/bin/env python3
"""Contract & verification tests for session 51197e5b (`fullpicks/**`, `data/51197e5b/board.json`).

All checks are dynamic over the current board so scheduled 4-hourly refreshes never break when
the HotSpawn lobby rotates to new fixtures.
"""
from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "fullpicks"
SDIR = ROOT / "scripts" / "51197e5b"
PAGES = (
    "index.html",
    "picks.html",
    "unresolved.html",
    "tournaments.html",
    "sources.html",
    "flagged.html",
    "method.html",
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


core = _load("fp511_core", SDIR / "core.py")
resolve = _load("fp511_resolve", SDIR / "resolve.py")
build = _load("fp511_build", SDIR / "build.py")


def setUpModule():  # noqa: N802
    assert resolve.main() == 0, "resolve.py must succeed offline"
    assert build.main() == 0, "build.py must succeed offline"


class FullPicksContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = json.loads((ROOT / "data" / "51197e5b" / "board.json").read_text(encoding="utf-8"))
        cls.base = json.loads((ROOT / "data" / "f7279a54" / "board.json").read_text(encoding="utf-8"))
        cls.rows = cls.board["open"]
        cls.by_id = {str(r["fixture_id"]): r for r in cls.rows}
        cls.base_by_id = {str(r["fixture_id"]): r for r in cls.base["open"]}
        cls.html = {p: (SITE / p).read_text(encoding="utf-8") for p in PAGES}

    def test_covers_every_open_lobby_fixture(self):
        self.assertEqual(set(self.by_id), set(self.base_by_id))
        self.assertGreaterEqual(len(self.rows), 1)
        s = self.board["summary"]
        self.assertEqual(s["open"], len(self.rows))
        self.assertEqual(s["with_pick"] + s["unresolved"], len(self.rows))
        self.assertEqual(s["with_pick"], sum(1 for r in self.rows if r.get("line")))

    def test_every_open_fixture_has_a_pick_or_documented_unresolved_ledger(self):
        for r in self.rows:
            with self.subTest(fixture=r["fixture_id"]):
                if r.get("line"):
                    self.assertTrue(r["line"].get("pick_team"))
                else:
                    self.assertIn(r["fixture_id"], self.board["unresolved_ids"])
                    self.assertTrue((r.get("resolution") or {}).get("attempts"))
                    self.assertTrue((r.get("resolution") or {}).get("limitations"))

    def test_featured_market_rows_are_byte_for_byte_unchanged(self):
        for fid, base_row in self.base_by_id.items():
            if not base_row.get("line"):
                continue
            got_row = self.by_id[fid]
            self.assertEqual(got_row.get("line"), base_row.get("line"), f"Featured row {fid} was altered")
            self.assertNotIn("resolution", got_row, f"Featured row {fid} must not use fallback resolution")

    def test_probabilities_sum_to_one_and_pick_is_argmax(self):
        for r in self.rows:
            ln = r.get("line")
            if not ln:
                continue
            with self.subTest(fixture=r["fixture_id"]):
                pa, pb = ln["prob_a"], ln["prob_b"]
                self.assertTrue(0.0 < pa < 1.0)
                self.assertTrue(0.0 < pb < 1.0)
                self.assertAlmostEqual(pa + pb, 1.0, places=4)
                expected_team = r["team_a"] if pa >= pb else r["team_b"]
                self.assertEqual(ln["pick_team"], expected_team)
                self.assertAlmostEqual(ln["pick_prob"], max(pa, pb), places=4)

    def test_fallback_esportsbook_and_exchange_lines_reproduce_from_raw_quotes(self):
        for r in self.rows:
            ln = r.get("line") or {}
            if ln.get("basis") not in ("esportsbook", "exchange"):
                continue
            quotes = r.get("quotes") or []
            self.assertTrue(quotes, f"{r['fixture_id']} missing quotes")
            entries = [{"source_key": q["source_key"], "prob_a": q["no_vig_prob_team_a"]} for q in quotes]
            mkt = core.consensus(entries)
            self.assertAlmostEqual(ln["prob_a"], mkt["prob_a"], places=4)

    def test_vrs_model_lines_reproduce_from_official_points_and_k(self):
        k = float(self.board["calibration"]["k"])
        for r in self.rows:
            ln = r.get("line") or {}
            if ln.get("basis") != "model":
                continue
            res = r["resolution"]
            pa_pts = res["team_a_vrs"]["points"]
            pb_pts = res["team_b_vrs"]["points"]
            expected = round(core.vrs_prob(pa_pts, pb_pts, k), 4)
            self.assertAlmostEqual(ln["prob_a"], expected, places=3, msg=r["fixture_id"])

    def test_floor_estimate_picks_rated_team_and_is_labelled_directional(self):
        k = float(self.board["calibration"]["k"])
        for r in self.rows:
            ln = r.get("line") or {}
            if ln.get("basis") != "floor_estimate":
                continue
            res = r["resolution"]
            ta_v = res.get("team_a_vrs")
            tb_v = res.get("team_b_vrs")
            self.assertTrue(bool(ta_v) ^ bool(tb_v))
            rated = ta_v or tb_v
            rated_team = r["team_a"] if ta_v else r["team_b"]
            p_rated = round(core.vrs_prob(rated["points"], res["floor"]["points"], k), 4)
            self.assertEqual(ln["pick_team"], rated_team)
            self.assertEqual(ln["confidence"], "Directional")
            self.assertTrue(ln.get("directional"))
            self.assertAlmostEqual(ln["pick_prob"], p_rated, places=3)

    def test_specific_current_resolutions_when_present(self):
        # Conditional checks: verify exact resolutions when these fixtures are in the current open lobby
        if "1082762" in self.by_id:
            r = self.by_id["1082762"]
            self.assertEqual(r["line"]["pick_team"], "ex-CYBERSHOKE")
            self.assertEqual(r["line"]["basis"], "esportsbook")
            self.assertGreaterEqual(len(r.get("quotes") or []), 2)
        if "1081600" in self.by_id:
            r = self.by_id["1081600"]
            # Active 5-player Banda Chuya (#165, 801 pts) out-rates DONSTU (#197, 732 pts)
            self.assertEqual(r["resolution"]["team_b_vrs"]["standing"], 165)
            self.assertEqual(r["line"]["pick_team"], "Banda chuya")
        if "1082837" in self.by_id:
            r = self.by_id["1082837"]
            self.assertEqual(r["line"]["pick_team"], "Zetta")
            self.assertIn("bo3gg_schedule_opponent_conflict", r["flags"])

    def test_no_hotspawn_crowd_percentage_used(self):
        for r in self.rows:
            blob = json.dumps(r.get("line") or {}).lower()
            self.assertNotIn("crowd", blob)
            self.assertNotIn("hotspawn_pick", blob)

    def test_every_table_row_has_an_official_https_link(self):
        tr_re = re.compile(r"<tbody[^>]*>(.*?)</tbody>", re.S | re.I)
        row_re = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
        for name, html_text in self.html.items():
            for tbody in tr_re.findall(html_text):
                for tr in row_re.findall(tbody):
                    links = re.findall(r'href="(https://[^"]+)"', tr)
                    self.assertTrue(links, f"{name}: table row missing https:// source link: {tr[:140]}")
                    self.assertTrue(all(urlsplit(u).hostname for u in links))

    def test_mobile_viewport_single_h1_and_exec_summary_sections(self):
        for name, html_text in self.html.items():
            with self.subTest(page=name):
                self.assertIn('name="viewport"', html_text)
                self.assertEqual(len(re.findall(r"<h1\b", html_text)), 1)
        idx = self.html["index.html"]
        self.assertIn('id="executive-summary"', idx)
        self.assertIn('id="unresolved-and-limitations"', idx)
        for target in PAGES:
            if target != "index.html":
                self.assertIn(f'href="{target}"', idx)

    def test_internal_links_resolve(self):
        for name, html_text in self.html.items():
            for m in re.finditer(r'href="([^"#:]+\.html)(#[^"]*)?"', html_text):
                rel = m.group(1)
                if rel.startswith("http"):
                    continue
                target = (SITE / rel).resolve() if not rel.startswith("../") else (ROOT / rel[3:]).resolve()
                self.assertTrue(target.exists(), f"{name}: broken link {rel} -> {target}")

    def test_workflow_schedule_and_scope_guard(self):
        wf = (ROOT / ".github" / "workflows" / "fullpicks-51197e5b.yml").read_text(encoding="utf-8")
        self.assertRegex(wf, r"cron:\s*'[0-9 ,*/]+ \*/4 \* \* \*'")
        self.assertIn("scripts/51197e5b/resolve.py", wf)
        self.assertIn("scripts/51197e5b/build.py", wf)
        self.assertIn("git add data/51197e5b fullpicks", wf)

    def test_staging_and_landing_integration(self):
        stage = (ROOT / "scripts" / "stage_site.py").read_text(encoding="utf-8")
        self.assertIn("'fullpicks'", stage)
        self.assertIn("scripts/51197e5b/build.py", stage)
        landing = (ROOT / "index.html").read_text(encoding="utf-8")
        for href in (
            "fullpicks/index.html",
            "fullpicks/picks.html",
            "fullpicks/unresolved.html",
            "fullpicks/tournaments.html",
            "fullpicks/flagged.html",
        ):
            self.assertIn(f'href="{href}"', landing)


if __name__ == "__main__":
    unittest.main()
