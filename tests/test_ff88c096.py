#!/usr/bin/env python3
"""Contract & mathematical verification suite for Session ff88c096 (`fullboard/**`).

Verifies mechanically:
1. All 19 live `play.hotspawn.com/lobby` CS2 matches + `1080200` API audit row are covered.
2. Anti-Crowd Firewall: AST check + live crowd-flip mutation test proving `prob_a`, `prob_b`,
   and `pick` change by exact 0.0 when HotSpawn crowd percentages are inverted.
3. Strict Featured vs Fallback Separation: every `featured_market` row has `fallback_invoked=False`
   and is 100% invariant to Valve VRS point mutations; fallback runs ONLY when multi-book lines are absent.
4. Exact arithmetic re-derivation of every quote's no-vig probability, every market consensus,
   and every October 21, 2026 Valve VRS logistic fallback probability (`p_A + p_B = 1`, `pick = argmax`).
5. Non-inference charter: `1082837 Zetta vs LOS NINOS` and `1080200 Wildcard vs DENDELE` stay
   explicitly `None` (blank) rather than inventing unverified org joins or VRS floor ratings.
6. Every HTML page in `fullboard/` is mobile-safe (`meta[name=viewport]`, single `<h1>`), every
   `<tbody><tr>` has an `https://` official source link, Executive Summary surfaces Unresolved &
   Limitations + direct links to `picks.html` and `unresolved.html`, and all internal links resolve.
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SDIR = ROOT / "scripts" / "ff88c096"
DDIR = ROOT / "data" / "ff88c096"
SITE = ROOT / "fullboard"


def _load_mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


collect_mod = _load_mod("ff88c096_collect", SDIR / "collect.py")
resolve_mod = _load_mod("ff88c096_resolve", SDIR / "resolve.py")
audit_mod = _load_mod("ff88c096_audit", SDIR / "audit_repo.py")
build_mod = _load_mod("ff88c096_build", SDIR / "build.py")

PAGES = [
    "index.html",
    "picks.html",
    "unresolved.html",
    "featured-vs-fallback.html",
    "hotspawn-lobby.html",
    "repo-audit.html",
    "flagged.html",
    "methodology.html",
]


class FullboardSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap = collect_mod.collect(live_refresh=False)
        cls.board = resolve_mod.resolve(cls.snap)
        cls.audit = audit_mod.audit_repository()
        build_mod.build_all()
        cls.by_id = {str(r["fixture_id"]): r for r in cls.board["fixtures"]}

    def test_covers_all_19_live_lobby_matches_and_phantom_audit_row(self):
        s = self.board["summary"]
        self.assertEqual(s["live_lobby_matches"], 19)
        self.assertEqual(s["backend_phantom_rows"], 1)
        self.assertEqual(s["total_tracked_rows"], 20)
        self.assertEqual(s["featured_market_count"], 14)
        self.assertEqual(s["lowtier_research_count"], 4)
        self.assertEqual(s["unresolved_live_count"], 1)
        self.assertEqual(s["live_with_verified_pick"], 18)

    def test_anti_crowd_firewall_zero_influence_under_extreme_mutation(self):
        # 1. Pure math functions never accept crowd arguments
        tree = ast.parse((SDIR / "resolve.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in (
                "devig_two_way", "fit_vrs_logistic_beta", "vrs_prob_a"
            ):
                arg_names = [a.arg for a in node.args.args]
                for forbidden in ("crowd", "crowd_a", "crowd_b", "picked"):
                    self.assertNotIn(forbidden, arg_names)

        # 2. Mutate every single crowd percentage to the opposite extreme and re-run resolver
        mutated = copy.deepcopy(self.snap)
        for fx in mutated["fixtures"]:
            fx["reference_only_crowd"] = {"crowd_a": 99, "crowd_b": 1, "total_picks": 99999}
        re_resolved = resolve_mod.resolve(copy.deepcopy(mutated))
        # Restore canonical files immediately after in-memory check
        resolve_mod.resolve(self.snap)

        for orig, mut in zip(self.board["fixtures"], re_resolved["fixtures"]):
            self.assertEqual(orig["prob_a"], mut["prob_a"], orig["fixture_id"])
            self.assertEqual(orig["prob_b"], mut["prob_b"], orig["fixture_id"])
            self.assertEqual(orig["pick"], mut["pick"], orig["fixture_id"])

    def test_strict_featured_vs_fallback_isolation(self):
        mutated = copy.deepcopy(self.snap)
        for fx in mutated["fixtures"]:
            if len(fx.get("quotes") or []) >= 2:
                fx["vrs_oct21_a"] = {"rank": 1, "points": 2500, "team": fx["team_a"]}
                fx["vrs_oct21_b"] = {"rank": 350, "points": 400, "team": fx["team_b"]}
        re_resolved = resolve_mod.resolve(copy.deepcopy(mutated))
        resolve_mod.resolve(self.snap)

        for orig, mut in zip(self.board["fixtures"], re_resolved["fixtures"]):
            if orig["resolution_tier"] == "featured_market":
                self.assertFalse(orig["fallback_invoked"], orig["fixture_id"])
                self.assertEqual(orig["prob_a"], mut["prob_a"], orig["fixture_id"])
                self.assertEqual(orig["pick"], mut["pick"], orig["fixture_id"])
            else:
                if orig["in_live_lobby"]:
                    self.assertTrue(orig["fallback_invoked"], orig["fixture_id"])

    def test_exact_arithmetic_rederivation_for_every_row(self):
        beta = self.board["calibration"]["beta_per_100pts"]
        for r in self.board["fixtures"]:
            fid = r["fixture_id"]
            if r["resolution_tier"] == "unresolved":
                self.assertIsNone(r["prob_a"], fid)
                self.assertIsNone(r["prob_b"], fid)
                self.assertIsNone(r["pick"], fid)
                continue

            self.assertGreater(r["prob_a"], 0.0)
            self.assertLess(r["prob_a"], 1.0)
            self.assertAlmostEqual(r["prob_a"] + r["prob_b"], 1.0, places=6, msg=fid)
            expected_pick = r["team_a"] if r["prob_a"] >= r["prob_b"] else r["team_b"]
            self.assertEqual(r["pick"], expected_pick, fid)

            if r["resolution_tier"] == "featured_market":
                tw = sum(resolve_mod.source_weight(q) for q in r["quotes"])
                pa = sum(
                    resolve_mod.source_weight(q) * round(resolve_mod.devig_two_way(q["decimal_a"], q["decimal_b"])[0], 6)
                    for q in r["quotes"]
                ) / tw
                self.assertAlmostEqual(r["prob_a"], round(pa, 6), places=6, msg=fid)
            elif r["resolution_method"] == "official_oct21_valve_vrs_logistic":
                pa = resolve_mod.vrs_prob_a(r["vrs_oct21_a"]["points"], r["vrs_oct21_b"]["points"], beta)
                self.assertAlmostEqual(r["prob_a"], round(pa, 6), places=6, msg=fid)

    def test_key_forensic_fixes_ex_prefix_kalshi_edt_and_vrs_flip(self):
        self.assertEqual(collect_mod.normalize_team_name("ex-CYBERSHOKE"), "cybershoke")
        self.assertNotEqual(collect_mod.normalize_team_name("Spirit Academy"), collect_mod.normalize_team_name("Team Spirit"))
        self.assertEqual(
            collect_mod.parse_kalshi_ticker_utc("kxcs2game-26oct210945pabebop"),
            "2026-10-21T13:45:00Z",
        )
        # 1082762 ex-CYBERSHOKE rescued across 4 markets
        self.assertEqual(self.by_id["1082762"]["pick"], "ex-CYBERSHOKE")
        self.assertGreater(self.by_id["1082762"]["prob_a"], 0.80)
        # 1081600 Oct 21 Valve VRS flip -> Banda chuya (#164, 785 pts > #187, 729 pts)
        self.assertEqual(self.by_id["1081600"]["pick"], "Banda chuya")
        # 1082835 anti-crowd alert -> JOGA DE TERNO despite 95% crowd on Martians
        self.assertEqual(self.by_id["1082835"]["pick"], "JOGA DE TERNO")
        # 1082837 & 1080200 left blank (unverified / already completed)
        self.assertIsNone(self.by_id["1082837"]["pick"])
        self.assertIsNone(self.by_id["1080200"]["pick"])

    def test_html_pages_mobile_source_links_and_internal_links(self):
        for page_name in PAGES:
            html_text = (SITE / page_name).read_text(encoding="utf-8")
            soup = BeautifulSoup(html_text, "html.parser")
            self.assertIsNotNone(soup.select_one('meta[name="viewport"]'), page_name)
            self.assertEqual(len(soup.select("h1")), 1, page_name)
            for tr in soup.select("tbody tr"):
                self.assertIsNotNone(tr.select_one('a[href^="https://"]'), f"{page_name} row missing https source")
            for tag in soup.select("[href], [src]"):
                raw = tag.get("href") or tag.get("src") or ""
                parsed = urlsplit(raw)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                target = (SITE / unquote(parsed.path)).resolve()
                self.assertTrue(target.exists(), f"{page_name} broken link -> {raw}")

        exec_soup = BeautifulSoup((SITE / "index.html").read_text(encoding="utf-8"), "html.parser")
        self.assertIsNotNone(exec_soup.select_one('a[href="picks.html"]'))
        self.assertIsNotNone(exec_soup.select_one('a[href="unresolved.html"]'))
        self.assertIsNotNone(exec_soup.select_one("#unresolved-summary"))


if __name__ == "__main__":
    unittest.main()
