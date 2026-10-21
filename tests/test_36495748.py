"""Session 36495748 desk contracts.

Everything here is checked against stored inputs (upstream boards, the pinned official Valve
file, this session's overrides) - nothing is taken on trust from the rendered pages alone.
Tests stay green as the HotSpawn lobby rotates: claims about specific fixtures are asserted
only while that fixture is still on the desk.
"""
import json
import math
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Unique-name loading: several sessions ship their own core.py/build.py, and under
# `unittest discover` a bare `import core`/`import build` binds whichever loaded first.
import importlib.util  # noqa: E402


def _load(modname, filename):
    spec = importlib.util.spec_from_file_location(modname, ROOT / "scripts" / "36495748" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


core = _load("exec36495748_core_for_tests", "core.py")
desk_build = _load("exec36495748_build_for_tests", "build.py")

DATA = ROOT / "data" / "36495748"
SITE = ROOT / "audits" / "36495748"
BOARD = json.loads((DATA / "board.json").read_text(encoding="utf-8"))
ROWS = {r["fixture_id"]: r for r in BOARD["rows"]}


def vrs_rows():
    f = sorted(DATA.glob("vrs_standings_global_*.md"))[-1]
    return desk_build.parse_vrs(f.read_text(encoding="utf-8"))


class TestCoverageAndArithmetic(unittest.TestCase):
    def test_summary_adds_up(self):
        s = BOARD["summary"]
        self.assertEqual(s["open"], len(BOARD["rows"]))
        self.assertEqual(s["with_pick"] + s["unresolved"], s["open"])
        self.assertEqual(s["market"] + s["exchange"] + s["vrs_model"] + s["directional_floor"], s["with_pick"])

    def test_every_row_pick_or_blank_never_guessed(self):
        for r in BOARD["rows"]:
            self.assertEqual(len(r["ladder"]), 5, r["fixture_id"])
            if r["basis"] == "unresolved":
                self.assertIsNone(r["prob_a"]); self.assertIsNone(r["pick"])
            else:
                self.assertTrue(0 < r["prob_a"] < 1)
                self.assertAlmostEqual(r["prob_a"] + r["prob_b"], 1.0, places=9)
                self.assertIn(r["pick"], (r["team_a"], r["team_b"]))
                if not r.get("pick_note"):
                    expect = r["team_a"] if r["prob_a"] >= 0.5 else r["team_b"]
                    self.assertEqual(r["pick"], expect, r["fixture_id"])

    def test_verify_board_clean(self):
        self.assertEqual(desk_build.verify_board(BOARD), [])

    def test_market_rows_rederive_from_stored_decimals(self):
        checked = 0
        for r in BOARD["rows"]:
            if r["basis"] != "market":
                continue
            usable = [q for q in r["detail"]["market"]["quotes"] if q.get("usable")]
            self.assertTrue(usable, r["fixture_id"])
            for q in usable:
                self.assertTrue(q["public_url"].startswith("https://"))
                self.assertNotIn("hotspawn", q["public_url"])
                p_first = (1 / q["decimal_a"]) / (1 / q["decimal_a"] + 1 / q["decimal_b"])
                pa = p_first if core.same_name(q["names_at_source"][0], r["team_a"]) else 1 - p_first
                self.assertAlmostEqual(pa, q["prob_a"], places=9)
                checked += 1
            cons = core.consensus_prob_a(usable)
            self.assertAlmostEqual(cons["prob_a"], r["prob_a"], places=9)
        self.assertGreater(checked, 0)

    def test_model_rows_match_official_file_and_recompute(self):
        rows = vrs_rows()
        by_standing = {x["standing"]: x for x in rows}
        k = BOARD["model"]["k"]
        for r in BOARD["rows"]:
            if r["basis"] not in ("vrs_model", "directional_floor"):
                continue
            v = r["detail"]["vrs"]
            for side in ("a", "b"):
                row = v.get(side)
                if row:
                    official = by_standing[row["standing"]]
                    self.assertEqual(official["points"], row["points"], (r["fixture_id"], side))
                    self.assertEqual(core.norm(official["team"]), core.norm(row["team"]))
            if r["basis"] == "vrs_model":
                self.assertAlmostEqual(core.vrs_prob_a(v["a"]["points"], v["b"]["points"], k), r["prob_a"], places=9)
            else:
                self.assertEqual(v["floor"]["standing"], rows[-1]["standing"])
                rated = v["a"] if v["rated_side"] == "a" else v["b"]
                p = core.vrs_prob_a(rated["points"], rows[-1]["points"], k)
                self.assertAlmostEqual(p if v["rated_side"] == "a" else 1 - p, r["prob_a"], places=9)

    def test_duplicate_names_never_joined_silently(self):
        """The two fixtures upstream mis-joined (2026-10-21) must carry roster evidence."""
        if "1082792" in ROWS:
            v = ROWS["1082792"]["detail"]["vrs"]
            self.assertEqual(v["b"]["standing"], 122)          # current Huns core, not #213
            self.assertIn("disambiguated", v["state_b"]["state"])
        if "1081600" in ROWS:
            v = ROWS["1081600"]["detail"]["vrs"]
            self.assertEqual(v["b"]["standing"], 165)          # playing five = #165 roster, not #373
            self.assertEqual(ROWS["1081600"]["pick"], ROWS["1081600"]["team_b"])

    def test_researched_fixtures(self):
        """Today's fallback resolutions, while those fixtures are still open."""
        if "1082762" in ROWS:  # ex-CYBERSHOKE v BlinkDagger
            r = ROWS["1082762"]
            self.assertEqual(r["basis"], "directional_floor")
            self.assertEqual(r["detail"]["vrs"]["a"]["standing"], 61)
            self.assertEqual(r["pick"], "ex-CYBERSHOKE")
        if "1082837" in ROWS:  # Zetta v LOS NINOS
            r = ROWS["1082837"]
            self.assertEqual(r["basis"], "directional_floor")
            self.assertEqual(r["detail"]["vrs"]["a"]["standing"], 357)
            self.assertEqual(r["pick"], "Zetta")
        if "1082763" in ROWS:  # Kalshi UPGRADE
            r = ROWS["1082763"]
            self.assertEqual(r["basis"], "exchange")
            self.assertGreater(r["prob_a"], 0.9)
        if "1079648" in ROWS:  # Kalshi coin flip + tiebreak
            r = ROWS["1079648"]
            self.assertEqual(r["basis"], "exchange")
            self.assertTrue(r.get("pick_note"))
            self.assertAlmostEqual(r["prob_a"], 0.5, delta=0.02)


class TestSiteContract(unittest.TestCase):
    PAGES = ["index.html", "picks.html", "unresolved.html", "flagged.html", "method.html"]

    def test_pages_exist_mobile_meta_and_links(self):
        for name in self.PAGES:
            text = (SITE / name).read_text(encoding="utf-8")
            self.assertIn('name="viewport"', text, name)
            self.assertIn("36495748", text, name)
            for href in re.findall(r'href="([^"#]+)"', text):
                if href.startswith(("https://", "mailto:")):
                    continue
                target = (SITE / href).resolve() if not href.startswith("../") else (SITE / href).resolve()
                self.assertTrue(target.exists(), f"{name} -> {href}")

    def test_exec_summary_links_every_section(self):
        idx = (SITE / "index.html").read_text(encoding="utf-8")
        for target in ("picks.html", "unresolved.html", "flagged.html", "method.html",
                       "../../index.html", "../../probabilities.html"):
            self.assertIn(f'href="{target}"', idx)
        self.assertIn("Unresolved", idx)

    def test_unresolved_page_has_limitations_and_ledgers(self):
        text = (SITE / "unresolved.html").read_text(encoding="utf-8")
        for tag in ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8"):
            self.assertIn(tag, text)
        self.assertIn("Resolved only by fallback research", text)
        flagged = (SITE / "flagged.html").read_text(encoding="utf-8")
        for tag in ("F1", "F2", "F8"):
            self.assertIn(tag, flagged)

    def test_no_hotspawn_price_links_anywhere(self):
        for name in self.PAGES:
            text = (SITE / name).read_text(encoding="utf-8")
            for m in re.finditer(r'href="https://[^"]*hotspawn[^"]*"', text):
                self.fail(f"{name}: external link to HotSpawn used as a source: {m.group(0)}")

    def test_reads_ledger_complete_and_https(self):
        reads = json.loads((DATA / "overrides.json").read_text(encoding="utf-8"))["reads"]
        self.assertGreaterEqual(len(reads), 10)
        for r in reads:
            self.assertTrue(r["url"].startswith("https://"), r["id"])
            self.assertTrue(r["what"], r["id"])

    def test_workflow_scoped(self):
        wf = (ROOT / ".github" / "workflows" / "36495748-refresh.yml").read_text(encoding="utf-8")
        self.assertIn("cron: '23 */4 * * *'", wf)
        self.assertIn("git add audits/36495748 data/36495748", wf)
        self.assertIn("tests.test_36495748", wf)
        self.assertIn("scripts/36495748/collect.py", wf)


class TestOfficialFile(unittest.TestCase):
    def test_pinned_file_is_structurally_the_official_table(self):
        rows = vrs_rows()
        self.assertGreaterEqual(len(rows), 300)
        standings = [r["standing"] for r in rows]
        self.assertEqual(standings, sorted(standings))
        points = [r["points"] for r in rows]
        self.assertEqual(points, sorted(points, reverse=True))
        recorded = BOARD["inputs"]["official_vrs"]
        self.assertEqual(recorded["rows"], len(rows))
        self.assertTrue(math.isfinite(core.VALVE_C) and 0 < core.VALVE_C < 0.01)


if __name__ == "__main__":
    unittest.main()
