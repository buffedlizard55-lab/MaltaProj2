#!/usr/bin/env python3
"""Dynamic contract tests for session f3e5123c (hotspawn-picks/).

No hardcoded fixture IDs/probabilities: every check derives from the current
committed upstream boards so 4-hourly lobby rotations cannot false-fail.
"""
from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "hotspawn-picks"
SDIR = ROOT / "scripts/f3e5123c"
PAGES = ("index.html", "picks.html", "unresolved.html", "tournaments.html",
         "sources.html", "flagged.html", "method.html")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


core = _load("f3e_core", SDIR / "core.py")
resolve = _load("f3e_resolve", SDIR / "resolve.py")
build = _load("f3e_build", SDIR / "build.py")


def setUpModule():  # noqa: N802
    assert resolve.main() == 0
    assert build.main() == 0


class EveryMatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = json.loads((ROOT / "data/f3e5123c/board.json").read_text(encoding="utf-8"))
        cls.base = json.loads((ROOT / "data/f7279a54/board.json").read_text(encoding="utf-8"))
        cls.rows = cls.board["open"]
        cls.by_id = {str(r["fixture_id"]): r for r in cls.rows}
        cls.base_by_id = {str(r["fixture_id"]): r for r in cls.base["open"]}
        cls.html = {p: (SITE / p).read_text(encoding="utf-8") for p in PAGES}

    def test_covers_exactly_the_open_lobby(self):
        self.assertEqual(set(self.by_id), set(self.base_by_id))
        s = self.board["summary"]
        self.assertEqual(s["open"], len(self.rows))
        self.assertEqual(s["with_pick"] + s["unresolved"], len(self.rows))
        self.assertEqual(
            s["featured_market"] + s["fallback_market"] + s["vrs_model"] + s["floor_directional"],
            s["with_pick"])

    def test_featured_lines_byte_for_byte_unchanged(self):
        for fid, base_row in self.base_by_id.items():
            if not base_row.get("line"):
                continue
            self.assertEqual(self.by_id[fid].get("line"), base_row.get("line"), fid)
            self.assertNotIn("resolution", self.by_id[fid], fid)

    def test_fallback_only_where_featured_missing(self):
        for r in self.rows:
            if r.get("resolution"):
                self.assertIsNone(self.base_by_id[str(r["fixture_id"])].get("line"), r["fixture_id"])

    def test_probabilities_valid_and_pick_is_argmax(self):
        for r in self.rows + self.board["status_conflicts"]:
            ln = r.get("line")
            if not ln:
                continue
            with self.subTest(fixture=r["fixture_id"]):
                self.assertTrue(0 < ln["prob_a"] < 1 and 0 < ln["prob_b"] < 1)
                self.assertAlmostEqual(ln["prob_a"] + ln["prob_b"], 1.0, places=3)
                expect = r["team_a"] if ln["prob_a"] >= ln["prob_b"] else r["team_b"]
                self.assertEqual(ln["pick_team"], expect)
                self.assertAlmostEqual(ln["pick_prob"], max(ln["prob_a"], ln["prob_b"]), places=4)
                self.assertAlmostEqual(ln["fair_decimal_a"], 1 / ln["prob_a"], delta=0.01)

    def test_market_fallback_reproduces_from_raw_quotes(self):
        for r in self.rows + self.board["status_conflicts"]:
            ln = r.get("line") or {}
            if ln.get("basis") not in ("esportsbook", "exchange"):
                continue
            with self.subTest(fixture=r["fixture_id"]):
                self.assertTrue(r.get("quotes"))
                entries = []
                for q in r["quotes"]:
                    # quote decimals are stored in FIXTURE orientation
                    nv = core.no_vig(q["decimal_a"], q["decimal_b"])
                    self.assertIsNotNone(nv)
                    self.assertAlmostEqual(nv["prob_a"], q["no_vig_prob_team_a"], places=3)
                    self.assertLessEqual(float(q["start_diff_h"]), 0.25)
                    self.assertTrue(str(q["public_url"]).startswith("http"))
                    entries.append({"source_key": q["source_key"], "prob_a": q["no_vig_prob_team_a"]})
                self.assertAlmostEqual(ln["prob_a"], core.consensus(entries)["prob_a"], places=3)

    def test_alias_joins_carry_roster_evidence(self):
        # Applies to THIS board's fallback joins (featured rows keep upstream quotes as-is).
        for r in self.rows + self.board["status_conflicts"]:
            if not r.get("resolution"):
                continue
            for q in r.get("quotes") or []:
                src_keys = {core.canon_team(n, allow_ex_strip=True)[0]
                            for n in (q.get("names_at_source") or [])}
                fix_keys = {core.canon_team(r["team_a"], allow_ex_strip=True)[0],
                            core.canon_team(r["team_b"], allow_ex_strip=True)[0]}
                if src_keys and src_keys != fix_keys:
                    self.assertTrue(q.get("alias_groups"), f'{r["fixture_id"]} alias join w/o evidence')
                    for g in q["alias_groups"]:
                        self.assertTrue(g.get("evidence"))

    def test_vrs_model_reproduces_from_official_points(self):
        k = float(self.board["calibration"]["k"])
        for r in self.rows + self.board["status_conflicts"]:
            ln = r.get("line") or {}
            if ln.get("basis") != "model":
                continue
            res = r["resolution"]
            expect = round(core.vrs_prob(res["team_a_vrs"]["points"], res["team_b_vrs"]["points"], k), 4)
            self.assertAlmostEqual(ln["prob_a"], expect, places=3, msg=r["fixture_id"])

    def test_floor_is_directional_and_picks_rated_side(self):
        k = float(self.board["calibration"]["k"])
        floor_pts = float(self.board["vrs"]["floor"]["points"])
        for r in self.rows:
            ln = r.get("line") or {}
            if ln.get("basis") != "floor_estimate":
                continue
            with self.subTest(fixture=r["fixture_id"]):
                self.assertEqual(ln["confidence"], "Directional")
                self.assertTrue(ln.get("directional"))
                res = r["resolution"]
                rated = res["team_a_vrs"] or res["team_b_vrs"]
                self.assertIsNotNone(rated)
                p_rated = core.vrs_prob(rated["points"], floor_pts, k)
                self.assertAlmostEqual(ln["pick_prob"], round(p_rated, 4), places=3)
                self.assertIn(r["fixture_id"], self.html["unresolved.html"])

    def test_every_row_has_sources_or_blank_ledger(self):
        for r in self.rows:
            with self.subTest(fixture=r["fixture_id"]):
                self.assertIn(str(r["fixture_id"]), self.html["picks.html"])
                self.assertIn(str(r["fixture_id"]), self.html["sources.html"])
                if not r.get("line"):
                    self.assertIn(str(r["fixture_id"]), self.board["unresolved_ids"])
                    self.assertTrue((r.get("resolution") or {}).get("attempts"))
                    self.assertTrue((r.get("resolution") or {}).get("Limitations"))
                if r.get("resolution"):
                    steps = r["resolution"]["attempts"]
                    self.assertGreaterEqual(len(steps), 3)
                    self.assertIn("HLTV", steps[0]["source"])

    def test_no_hotspawn_crowd_probability_fields(self):
        blob = json.dumps(self.board).lower()
        for banned in ('"crowd', '"pick_pct', '"ownership_pct', '"hotspawn_pct', '"community_pct'):
            self.assertNotIn(banned, blob)

    def test_site_pages_mobile_and_internal_links(self):
        for name, doc in self.html.items():
            with self.subTest(page=name):
                self.assertIn('name="viewport"', doc)
                self.assertIn("@media(max-width:760px)", doc)
                self.assertIn("nav class=\"bottom\"", doc)
                self.assertIn("executive", self.html["index.html"].lower())
                for href in re.findall(r'href="([^"#]+)(?:#[^"]*)?"', doc):
                    if href.startswith(("http://", "https://", "mailto:")):
                        continue
                    target = (SITE / href).resolve()
                    self.assertTrue(target.exists(), f"{name} -> {href} missing")

    def test_exec_summary_links_directory(self):
        idx = self.html["index.html"]
        for href in ("picks.html", "unresolved.html", "../board/picks.html",
                     "../fullpicks/picks.html", "../dashboard/picks.html", "../index.html"):
            self.assertIn(f'href="{href}"', idx)
        # every open fixture appears in the at-a-glance table
        for r in self.rows:
            self.assertIn(f'picks.html#row-{r["fixture_id"]}', idx)


if __name__ == "__main__":
    unittest.main()
