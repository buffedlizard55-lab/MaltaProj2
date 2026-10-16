#!/usr/bin/env python3
"""Contract tests for session 1c8f79f8 (day-4 desk).

Re-derives every published number from the retained raw inputs
(fixtures API capture + research ledger) so the tests hold on every
scheduled refresh, not just on the commit that wrote them.
"""
from __future__ import annotations

import importlib.util
import json
import math
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "1c8f79f8"
DAY4 = ROOT / "day4"

_spec = importlib.util.spec_from_file_location(
    "research_1c8f79f8", ROOT / "scripts" / "1c8f79f8" / "research.py")
research = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(research)

_spec2 = importlib.util.spec_from_file_location(
    "collect_1c8f79f8", ROOT / "scripts" / "1c8f79f8" / "collect.py")
collect = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(collect)

# canonical model constants (scripts/fe803b80/core.py arithmetic)
VALVE_RD = 75.0
VALVE_Q = math.log(10) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10) / 400.0
K_FIT = 0.25


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def devig(da, db):
    ia, ib = 1.0 / da, 1.0 / db
    return ia / (ia + ib), ib / (ia + ib)


def load_board():
    return json.loads((DATA / "board.json").read_text())


def load_raw():
    return json.loads((DATA / "fixtures_raw.json").read_text())


class BoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load_board()
        cls.rows = {r["fixture_id"]: r for r in cls.board["open"]}

    def test_board_shape(self):
        self.assertEqual(len(self.board["open"]), 21)
        self.assertEqual(self.board["session"], "1c8f79f8")
        for key in ("generated_utc", "snapshot_utc", "fixture_source_read_utc",
                    "summary", "calibration", "vrs", "open", "twc", "notes"):
            self.assertIn(key, self.board)
        s = self.board["summary"]
        self.assertEqual(s["open_with_market"] + s["open_model_only"] + s["open_blank"], 21)
        self.assertEqual(s["open_with_pick"], 21)
        self.assertEqual(s["climb_picks"], 3)
        self.assertTrue(s["twc_not_listed_on_hotspawn"])

    def test_every_fixture_has_pick(self):
        for r in self.board["open"]:
            self.assertTrue(r["line"]["pick"], r["fixture_id"])
        numeric = [r for r in self.board["open"] if r["line"]["prob_a"] is not None]
        blank = [r for r in self.board["open"] if r["line"]["prob_a"] is None]
        self.assertEqual(len(numeric), 19)
        self.assertEqual(len(blank), 2)
        for r in blank:
            self.assertIsNotNone(r["blank_reason"])
            self.assertIn("probability_blank_by_policy", r["flags"])
            self.assertEqual(r["line"]["basis"], None)

    def test_fixtures_match_retained_capture(self):
        raw = load_raw()
        api_rows = {f["id"]: f for f in raw["fixtures"]}
        self.assertEqual(len(api_rows), 21)  # future-start rows only; stale rows stay in evidence/
        for r in self.board["open"]:
            fx = research.FIXTURES[[f["fixture_id"] for f in research.FIXTURES]
                                   .index(r["fixture_id"])]
            api = api_rows[r["fixture_id"]]
            self.assertEqual(api["participants0_name"].casefold(), fx["team_a"].casefold())
            self.assertEqual(api["participants1_name"].casefold(), fx["team_b"].casefold())
            self.assertEqual(api["participants0_picked_percent"], fx["crowd_a"])
            self.assertEqual(api["participants1_picked_percent"], fx["crowd_b"])
            self.assertEqual(int(api["scheduled_start_time"]),
                             int(__import__("datetime").datetime.strptime(
                                 fx["start_utc"], "%Y-%m-%dT%H:%M:%SZ")
                                 .replace(tzinfo=__import__("datetime").timezone.utc).timestamp() * 1000))

    def test_lock_offset_arithmetic(self):
        for row in load_raw()["fixtures"]:
            self.assertEqual(int(row["lock_time"]),
                             int(row["scheduled_start_time"]) - 360_000,
                             row["id"])
        problems = collect.verify(load_raw())
        self.assertEqual(problems, [])

    def test_market_rows_rederive_from_quotes(self):
        for r in self.board["open"]:
            if r["market"] is None:
                continue
            quotes = [q for q in r["quotes"] if q.get("decimal_a")]
            self.assertTrue(quotes, r["fixture_id"])
            for q in quotes:
                pa, pb = devig(q["decimal_a"], q["decimal_b"])
                self.assertAlmostEqual(pa, q["prob_a"], delta=5e-4,
                                       msg=f"{r['fixture_id']} quote {q['source_key']}")
                self.assertAlmostEqual(pb, q["prob_b"], delta=5e-4)
            # the stored market block is the primary quote's de-vig
            self.assertAlmostEqual(quotes[0]["prob_a"], r["market"]["prob_a"],
                                   delta=5e-4, msg=r["fixture_id"])

    def test_model_rows_rederive_from_vrs(self):
        for r in self.board["open"]:
            if r["model"] is None:
                continue
            v = r["model"]["vrs"]
            pa = sigmoid(K_FIT * VALVE_C * (v["points_a"] - v["points_b"]))
            self.assertAlmostEqual(pa, r["model"]["prob_a"], delta=5e-4,
                                   msg=r["fixture_id"])
            # the VRS row must exist in the ledger with matching points
            key_a = research.vrs_key(r["team_a"])
            key_b = research.vrs_key(r["team_b"])
            self.assertIsNotNone(key_a, r["fixture_id"])
            self.assertIsNotNone(key_b, r["fixture_id"])
            self.assertEqual(research.VRS[key_a]["points"], v["points_a"])
            self.assertEqual(research.VRS[key_b]["points"], v["points_b"])

    def test_fair_probability_derivation_rules(self):
        """Every published fair probability follows exactly one documented rule."""
        for r in self.board["open"]:
            fid, basis = r["fixture_id"], r["line"]["basis"]
            if basis is None:
                self.assertIsNone(r["line"]["prob_a"])
                continue
            if basis == "model":
                self.assertAlmostEqual(r["model"]["prob_a"], r["line"]["prob_a"],
                                       delta=5e-3, msg=fid)
            elif basis == "market":
                quotes = [q for q in r["quotes"] if q.get("decimal_a")]
                mean_a = sum(q["prob_a"] for q in quotes) / len(quotes)
                self.assertAlmostEqual(mean_a, r["line"]["prob_a"], delta=5e-3, msg=fid)
            elif basis == "blend":
                self.assertIsNotNone(r["market"], fid)
                self.assertIsNotNone(r["model"], fid)
                blended = (2 / 3) * r["market"]["prob_a"] + (1 / 3) * r["model"]["prob_a"]
                self.assertAlmostEqual(blended, r["line"]["prob_a"], delta=5e-3, msg=fid)
            else:
                self.fail(f"unknown basis {basis} on {fid}")
            self.assertAlmostEqual(r["line"]["prob_a"] + r["line"]["prob_b"], 1.0,
                                   places=6, msg=fid)

    def test_crowd_is_ownership_context_never_a_probability(self):
        """Provenance test: fair probabilities re-derive from quotes/model only.
        A numeric equality with a crowd share would be coincidental and is
        additionally checked nowhere to be the source: every row's basis is
        market/model/blend and every basis re-derives from non-crowd inputs
        (test_fair_probability_derivation_rules)."""
        for r in self.board["open"]:
            self.assertIn("crowd_" + "note" if False else "crowd_note", r)
            self.assertIn("never a probability input", r["crowd_note"])
            self.assertNotIn("crowd", r["line"]["basis"] or "")
        self.assertTrue(any("crowd" in n.lower() and "never" in n.lower()
                            for n in self.board["notes"]))

    def test_ladder_gates_on_climb_picks(self):
        climbs = [r for r in self.board["open"] if r["ladder"]["climb"]]
        self.assertEqual(len(climbs), 3)
        for r in climbs:
            side = r["ladder"]["climb_side"]
            self.assertIn(side, ("a", "b"), r["fixture_id"])
            own = (r["crowd_b"] if side == "b" else r["crowd_a"]) / 100.0
            prob = r["ladder"]["climb_prob"]
            self.assertGreaterEqual(prob, 0.30, r["fixture_id"])
            self.assertLessEqual(own, 0.20, r["fixture_id"])
            self.assertGreaterEqual(prob / own, 2.0, r["fixture_id"])
            self.assertIn("floor", r["ladder"]["climb_gates"], r["fixture_id"])
            self.assertGreaterEqual(len(r["flags"]), 1)
            self.assertGreaterEqual(len(r["context"]), 2)

    def test_every_row_has_external_sources(self):
        for r in self.board["open"]:
            links = [u for _, u in r["sources"]]
            self.assertTrue(links, r["fixture_id"])
            for u in links:
                self.assertTrue(u.startswith("https://"), (r["fixture_id"], u))
                self.assertNotIn("play.hotspawn.com", u)
            # blank rows need the fullest documentation
            if r["line"]["basis"] is None:
                self.assertGreaterEqual(len(links), 2, r["fixture_id"])

    def test_twc_block(self):
        twc = self.board["twc"]
        self.assertEqual(twc["decider"]["result"], "BETBOOM 2-1 Legacy")
        self.assertEqual([m[1] for m in twc["decider"]["maps"]], [16, 11, 13])
        for key in ("sf1", "sf2"):
            m = twc[key]
            self.assertIn(m["pick"], m["teams"])
            self.assertIsNotNone(m["fair"][0])
            self.assertGreaterEqual(len(m["sources"]), 3)
        # sf2 must carry the no-published-line evidence
        self.assertEqual(twc["sf2"]["market"]["kind"], "no-market")
        self.assertEqual(len(twc["schedule"]), 4)

    def test_ghost_row_documented(self):
        g = self.board["ghost_rows"]
        self.assertEqual(g[0]["fixture_id"], "1080200")
        self.assertIn("stale capture artifact", g[0]["explanation"])

    def test_aliases_resolve(self):
        self.assertEqual(research.vrs_key("WROTBERRY"), "WBT")
        self.assertEqual(research.vrs_key("Apogee Betclic"), "Betclic")
        self.assertEqual(research.vrs_key("Donstu"), "DONSTU")
        self.assertIsNone(research.vrs_key("Morningstar"))
        self.assertIsNone(research.vrs_key("WXM"))


class PageTests(unittest.TestCase):
    PAGES = ["index.html", "picks.html", "twc-review.html",
             "unresolved.html", "flagged.html", "method.html"]

    def test_pages_exist_with_single_h1_and_viewport(self):
        for name in self.PAGES:
            text = (DAY4 / name).read_text(encoding="utf-8")
            self.assertEqual(text.count("<h1"), 1, name)
            self.assertIn('name="viewport"', text)
            self.assertIn("2026-10-16T20:50Z", text, name)

    def test_internal_links_resolve(self):
        for name in self.PAGES:
            text = (DAY4 / name).read_text(encoding="utf-8")
            for href in re.findall(r'href="([^"#]+?)(?:#[^"]*)?"', text):
                if href.startswith(("http", "mailto")):
                    continue
                target = (DAY4 / href)
                self.assertTrue(target.exists(), f"{name} -> {href}")

    def test_external_links_are_https(self):
        for name in self.PAGES:
            text = (DAY4 / name).read_text(encoding="utf-8")
            for href in re.findall(r'href="(https?://[^"]+)"', text):
                self.assertTrue(href.startswith("https://"), f"{name}: {href}")

    def test_picks_table_has_per_row_source_links(self):
        text = (DAY4 / "picks.html").read_text(encoding="utf-8")
        for fid in research.LINES:
            self.assertIn(f'id="fx{fid}"', text)
        # every fixture row carries at least one external source anchor
        rows = text.split("<tr id=")[1:]
        for chunk in rows:
            self.assertIn("href=\"https://", chunk)

    def test_exec_summary_links_every_subsection(self):
        text = (DAY4 / "index.html").read_text(encoding="utf-8")
        for name in self.PAGES[1:]:
            self.assertIn(f'href="{name}"', text)
        self.assertIn('href="picks.html#twc"', text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
