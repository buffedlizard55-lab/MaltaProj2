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

_spec3 = importlib.util.spec_from_file_location(
    "build_1c8f79f8", ROOT / "scripts" / "1c8f79f8" / "build.py")
builder = importlib.util.module_from_spec(_spec3)
_spec3.loader.exec_module(builder)

import tempfile
from datetime import datetime, timezone

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
        """Counts are derived from the board itself, so a lobby rotation cannot
        break the contract (the previous literal 21 pinned one capture)."""
        rows = self.board["open"]
        self.assertEqual(len(rows), len({r["fixture_id"] for r in rows}))
        self.assertEqual(self.board["session"], "1c8f79f8")
        for key in ("generated_utc", "snapshot_utc", "fixture_source_read_utc",
                    "summary", "calibration", "vrs", "open", "twc", "notes", "inventory"):
            self.assertIn(key, self.board)
        s = self.board["summary"]
        self.assertEqual(s["open"], len(rows))
        self.assertEqual(s["fixtures_total"], len(rows))
        self.assertEqual(s["open_with_market"] + s["open_model_only"] + s["open_blank"], len(rows))
        self.assertEqual(s["open_with_pick"] + s["open_without_direction"], len(rows))
        self.assertEqual(s["climb_picks"],
                         sum(1 for r in rows if r["ladder"]["climb"]))
        self.assertTrue(s["twc_not_listed_on_hotspawn"])
        inv = self.board["inventory"]
        self.assertIn(inv["mode"], ("fresh_capture", "retained_inventory"))
        self.assertEqual(inv["open_rows"], len(rows))
        self.assertEqual(inv["auto_rows"],
                         sum(1 for r in rows if r.get("row_origin") == "auto_from_capture"))
        self.assertTrue(inv["policy"])

    def test_capture_stamps_are_published_not_frozen(self):
        """The board must stamp the capture it actually used."""
        raw = load_raw()
        self.assertEqual(self.board["snapshot_utc"], raw["meta"]["captured_utc"])
        self.assertEqual(self.board["inventory"]["capture_utc"], raw["meta"]["captured_utc"])
        datetime.strptime(self.board["inventory"]["evaluated_utc"], "%Y-%m-%dT%H:%M:%SZ")

    def test_every_fixture_has_pick_or_documented_blank(self):
        """Requirement: a pick for every match — or an explicit blank with a
        reason, never a silent omission and never an invented number."""
        for r in self.board["open"]:
            if r["line"]["prob_a"] is None:
                self.assertIsNotNone(r["blank_reason"], r["fixture_id"])
                self.assertEqual(r["line"]["basis"], None, r["fixture_id"])
                self.assertIn("probability_blank", " ".join(r["flags"]), r["fixture_id"])
                self.assertTrue(r["context"], r["fixture_id"])
                self.assertGreaterEqual(len(r["sources"]), 2, r["fixture_id"])
            else:
                self.assertIsNotNone(r["line"]["pick"], r["fixture_id"])
                self.assertAlmostEqual(r["line"]["prob_a"] + r["line"]["prob_b"], 1.0, places=6)
                side_prob = (r["line"]["prob_a"]
                             if r["line"]["pick"].casefold() == r["team_a"].casefold()
                             else r["line"]["prob_b"])
                self.assertAlmostEqual(side_prob, r["line"]["pick_probability"], places=4,
                                       msg=r["fixture_id"])
                self.assertGreaterEqual(r["line"]["pick_probability"], 0.5, r["fixture_id"])
        numeric = [r for r in self.board["open"] if r["line"]["prob_a"] is not None]
        self.assertEqual(len(numeric),
                         self.board["summary"]["open"] - self.board["summary"]["open_blank"])

    def test_rows_reconcile_with_the_live_capture(self):
        """The capture is authoritative for inventory, ownership and kickoff.

        A live lobby moves ownership and sometimes moves kickoffs. Neither may
        abort a refresh: the row must carry the live value, and any difference
        from the research ledger must be recorded in inventory.drift.
        """
        raw = load_raw()
        api_rows = {str(f["id"]): f for f in raw["fixtures"]}
        inv = self.board["inventory"]
        if inv["mode"] != "fresh_capture":
            self.assertTrue(inv["degraded_reasons"])
            for r in self.board["open"]:
                self.assertIn("retained_inventory_capture_degraded", r["flags"], r["fixture_id"])
            return
        # every open captured fixture is on the board (no silent omission)
        for fid, api in api_rows.items():
            lock = builder._iso(builder._ms(api.get("lock_time")))
            if not builder.open_for_picks(builder._iso(builder._ms(api.get("scheduled_start_time"))),
                                          lock, datetime.now(timezone.utc)):
                continue
            self.assertIn(fid, {r["fixture_id"] for r in self.board["open"]},
                          f"{fid} is listed by the capture but missing from the board")
        for r in self.board["open"]:
            api = api_rows.get(r["fixture_id"])
            if api is None:
                continue
            self.assertEqual(r["crowd_a"], api["participants0_picked_percent"], r["fixture_id"])
            self.assertEqual(r["crowd_b"], api["participants1_picked_percent"], r["fixture_id"])
            self.assertEqual(r["start_utc"], builder._iso(builder._ms(api["scheduled_start_time"])))
            self.assertEqual(r["lock_utc"], builder._iso(builder._ms(api["lock_time"])))
            for name, key in ((r["team_a"], "participants0_name"), (r["team_b"], "participants1_name")):
                if name.casefold() == "wbt (whitebit team)":
                    continue  # documented alias row (see flagged)
                self.assertEqual(name.casefold(), api[key].casefold(), r["fixture_id"])
        for d in inv["drift"]:
            self.assertIn(d["issue"], ("crowd ownership moved", "kickoff rescheduled",
                                       "capture name variant (team A)",
                                       "capture name variant (team B)",
                                       "capture row without parsable start/lock time"), d)

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
        self.assertEqual(len(climbs), self.board["summary"]["climb_picks"])
        self.assertTrue(climbs, "the curated ladder activates swings on every capture with the gate rows")
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
                self.assertNotIn("www.hotspawn.com", u)
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
    board_stamp = json.loads((DATA / "board.json").read_text())["snapshot_utc"]

    def test_pages_exist_with_single_h1_and_viewport(self):
        for name in self.PAGES:
            text = (DAY4 / name).read_text(encoding="utf-8")
            self.assertEqual(text.count("<h1"), 1, name)
            self.assertIn('name="viewport"', text)
            # the published stamp is the retained capture's own time
            self.assertIn(self.board_stamp[:16], text, name)

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




def _temp_capture(fixtures, captured_utc=None, base=None):
    """Write a fixtures capture to a temp file for refresh-robustness tests."""
    doc = base if base is not None else load_raw()
    doc = json.loads(json.dumps(doc))
    doc["meta"]["captured_utc"] = captured_utc or doc["meta"]["captured_utc"]
    if fixtures is not None:
        doc["fixtures"] = fixtures
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(doc, handle)
    handle.close()
    return handle.name


_OPEN_NOW = datetime(2026, 10, 17, 6, 0, tzinfo=timezone.utc)


class RefreshRobustnessTests(unittest.TestCase):
    """The refresh path must survive a live lobby: ownership moves, fixtures are
    added and removed, and a provider can return an empty capture.

    These tests encode the project requirement directly: a pick (or an explicit,
    reason-carrying blank) for every match the lobby lists, at every refresh.
    """

    def test_ownership_drift_is_recorded_and_never_fatal(self):
        raw = load_raw()
        drifted = json.loads(json.dumps(raw))
        target = drifted["fixtures"][0]
        target["participants0_picked_percent"] = 5
        target["participants1_picked_percent"] = 95
        path = _temp_capture(drifted["fixtures"])
        rows, inv = builder.build_rows(capture_path=path, now=_OPEN_NOW)
        row = {r["fixture_id"]: r for r in rows}[str(target["id"])]
        self.assertEqual((row["crowd_a"], row["crowd_b"]), (5, 95))
        self.assertIn("crowd ownership moved",
                      [d["issue"] for d in inv["drift"]])
        ledger = {fx["fixture_id"]: fx for fx in research.FIXTURES}[str(target["id"])]
        self.assertNotEqual(ledger["crowd_a"], 5)
        # the probability is untouched by ownership
        pick = research.PICKS[str(target["id"])]
        self.assertEqual(row["line"]["prob_a"], pick["fair_a"])

    def test_new_rated_listing_gets_a_pick_and_a_probability(self):
        raw = json.loads(json.dumps(load_raw()))
        raw["fixtures"].append({
            "id": "9900001", "competition_id": 36197, "competition_name": "Stake Pulse Beat III",
            "sport_alias": "cs2", "status": "scheduled",
            "scheduled_start_time": "1792459200000", "lock_time": "1792458840000",
            "lock_offset_sec": 360, "offered_points": 3, "tier": "b", "stage": "Semi-final",
            "best_of": 3, "total_picks": 0, "points_breakdown": {},
            "participants0_id": "367", "participants0_name": "HEROIC",
            "participants0_picked_percent": 50, "participants0_score": 0,
            "participants1_id": "347", "participants1_name": "Ninjas in Pyjamas",
            "participants1_picked_percent": 50, "participants1_score": 0,
        })
        path = _temp_capture(raw["fixtures"])
        rows, inv = builder.build_rows(capture_path=path, now=_OPEN_NOW)
        by_id = {r["fixture_id"]: r for r in rows}
        self.assertIn("9900001", by_id, "a new lobby listing must appear on the board")
        row = by_id["9900001"]
        self.assertEqual(row["row_origin"], "auto_from_capture")
        self.assertIsNotNone(row["line"]["pick"], "a listed match must carry a pick direction")
        self.assertIsNotNone(row["line"]["prob_a"], "an eligible rating pair must be priced")
        self.assertAlmostEqual(row["line"]["prob_a"] + row["line"]["prob_b"], 1.0, places=6)
        self.assertIn(row["line"]["basis"], ("market", "model"))
        self.assertTrue(any(u.startswith("https://") for _, u in row["sources"]))
        self.assertEqual(inv["auto_added"][0]["fixture_id"], "9900001")

    def test_new_unrated_listing_is_blank_with_a_published_reason(self):
        raw = json.loads(json.dumps(load_raw()))
        raw["fixtures"].append({
            "id": "9900002", "competition_id": 36412,
            "competition_name": "MaceMedia VOID Autumn Cup 2026", "sport_alias": "cs2",
            "status": "scheduled", "scheduled_start_time": "1792459200000",
            "lock_time": "1792458840000", "lock_offset_sec": 360, "offered_points": 2,
            "tier": "c", "stage": "Round 1", "best_of": 1, "total_picks": 0,
            "points_breakdown": {},
            "participants0_id": "1", "participants0_name": "Morningstar",
            "participants0_picked_percent": 40, "participants0_score": 0,
            "participants1_id": "2", "participants1_name": "WXM",
            "participants1_picked_percent": 60, "participants1_score": 0,
        })
        path = _temp_capture(raw["fixtures"])
        rows, _ = builder.build_rows(capture_path=path, now=_OPEN_NOW)
        row = {r["fixture_id"]: r for r in rows}["9900002"]
        self.assertIsNone(row["line"]["prob_a"], "no evidence means no number")
        self.assertIsNone(row["line"]["pick"])
        self.assertTrue(row["blank_reason"])
        self.assertGreaterEqual(len(row["sources"]), 2)
        for _, url in row["sources"]:
            self.assertTrue(url.startswith("https://"))
            self.assertNotIn("hotspawn.com", url)

    def test_removed_fixture_is_reported_not_silently_kept(self):
        raw = json.loads(json.dumps(load_raw()))
        dropped = raw["fixtures"][0]["id"]
        raw["fixtures"] = raw["fixtures"][1:]
        path = _temp_capture(raw["fixtures"])
        rows, inv = builder.build_rows(capture_path=path, now=_OPEN_NOW)
        self.assertNotIn(str(dropped), {r["fixture_id"] for r in rows})
        self.assertIn(str(dropped), [d["fixture_id"] for d in inv["dropped"]])

    def test_empty_capture_keeps_the_retained_inventory(self):
        path = _temp_capture([])
        rows, inv = builder.build_rows(capture_path=path, now=_OPEN_NOW)
        self.assertEqual(inv["mode"], "retained_inventory")
        self.assertTrue(inv["degraded_reasons"])
        self.assertEqual(len(rows), len(research.FIXTURES))
        for row in rows:
            self.assertIn("retained_inventory_capture_degraded", row["flags"])

    def test_every_captured_fixture_is_on_the_board(self):
        rows, inv = builder.build_rows(now=_OPEN_NOW)
        ids = {r["fixture_id"] for r in rows}
        for api in load_raw()["fixtures"]:
            if builder.open_for_picks(builder._iso(builder._ms(api["scheduled_start_time"])),
                                      builder._iso(builder._ms(api["lock_time"])), _OPEN_NOW):
                self.assertIn(str(api["id"]), ids)

    def test_sibling_quote_reuse_is_exact_id_only(self):
        # 371a1ce7 (robustness): pick a fixture id that is open on a published sibling board right now
        # instead of pinning one id that closes out of every board as its match locks.
        live_id = None
        for _s, rel, _l in builder.SIBLING_BOARDS:
            path = builder.ROOT / rel
            if not path.exists():
                continue
            for row in (json.loads(path.read_text()).get("open") or []):
                m = row.get("market") or {}
                if m.get("prob_a") and m.get("prob_b") and any(q.get("public_url") for q in (row.get("quotes") or [])):
                    live_id = str(row["fixture_id"])
                    break
            if live_id:
                break
        if live_id is None:
            self.skipTest("no sibling board currently lists a priced open fixture")
        quote = builder.sibling_market(live_id)
        self.assertIsNotNone(quote, "a live fixture id must be found in a published board")
        self.assertTrue(quote["url"].startswith("https://"))
        self.assertRegex(quote["retrieved_utc"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertIsNone(builder.sibling_market("999999999"),
                          "an unknown fixture id must never resolve to another match")


if __name__ == "__main__":
    unittest.main(verbosity=2)
