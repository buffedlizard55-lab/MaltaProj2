#!/usr/bin/env python3
"""Contract and unit tests for the pick centre (session 2cadfaf2).

Two jobs:

1. **Unit checks** for the decisions that turn sources into a line — the state machine, the quote
   join, the Kalshi ticker conversion and the bound rule — so a regression is caught without
   needing the published board.
2. **Board and site contracts**: every fixture the lobby lists has a row, every published line is
   internally reproducible, every row links an official HotSpawn page, nothing is invented, no
   crowd percentage is present, and every page in ``pickcenter/`` is mobile-shaped with working
   in-site links.
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "pickcenter"
sys.path.insert(0, str(ROOT / "scripts" / "2cadfaf2"))

import pc_core as core  # noqa: E402  (unique name, no cross-session `core` collision)


def load_board() -> dict:
    return json.loads((ROOT / "data" / "2cadfaf2" / "board.json").read_text(encoding="utf-8"))


class StateMachine(unittest.TestCase):
    NOW = datetime(2026, 10, 21, 20, 0, tzinfo=timezone.utc)

    def fx(self, **kw):
        base = {"fixture_id": "1", "status": "scheduled", "winner": None,
                "start_utc": "2026-10-21T22:00:00Z", "lock_utc": "2026-10-21T21:54:00Z"}
        base.update(kw)
        return base

    def test_open_before_lock(self):
        self.assertEqual(core.state_of(self.fx(), self.NOW)[0], "open")

    def test_locked_between_lock_and_start(self):
        self.assertEqual(core.state_of(self.fx(lock_utc="2026-10-21T19:00:00Z"), self.NOW)[0], "locked")

    def test_stale_is_reported_not_hidden(self):
        state, why = core.state_of(self.fx(start_utc="2026-06-26T10:30:00Z",
                                           lock_utc="2026-06-26T10:24:00Z"), self.NOW)
        self.assertEqual(state, "stale")
        self.assertIn("scheduled", why)

    def test_final_wins_over_time(self):
        self.assertEqual(core.state_of(self.fx(winner="b"), self.NOW)[0], "final")

    def test_missing_start_is_awaiting(self):
        self.assertEqual(core.state_of(self.fx(start_utc=None, lock_utc=None), self.NOW)[0], "awaiting")


class QuoteJoin(unittest.TestCase):
    FIXTURE = {"team_a": "Zetta", "team_b": "LOS NINOS", "start_utc": "2026-10-21T22:00:00Z"}

    def quote(self, **kw):
        base = {"source_key": "melbet", "team_a": "Zetta", "team_b": "Los Ninos",
                "start_utc": "2026-10-21T22:00:05Z", "event_id": "1"}
        base.update(kw)
        return base

    def test_exact_pairing_joins(self):
        join = core.join_quote(self.FIXTURE, self.quote())
        self.assertIsNotNone(join)
        self.assertFalse(join["swapped"])

    def test_reversed_pairing_is_swapped(self):
        join = core.join_quote(self.FIXTURE, self.quote(team_a="Los Ninos", team_b="Zetta"))
        self.assertTrue(join["swapped"])

    def test_time_mismatch_is_rejected_not_joined(self):
        join = core.join_quote(self.FIXTURE, self.quote(start_utc="2026-10-22T02:00:00Z"))
        self.assertTrue(join["rejected"])
        self.assertEqual(join["reason"], "start_time_mismatch")

    def test_alias_needs_the_other_side_to_match_exactly(self):
        quote = {"source_key": "kalshi", "team_a": "Alianza Lima Esports", "team_b": "Someone Else",
                 "event_id": "KXCS2GAME-26OCT211800LNALE"}
        self.assertIsNone(core.join_quote(self.FIXTURE, quote))

    def test_alias_join_is_recorded_with_evidence(self):
        quote = {"source_key": "kalshi", "team_a": "Alianza Lima Esports", "team_b": "Los Ninos",
                 "event_id": "KXCS2GAME-26OCT211800LNALE"}
        join = core.join_quote(self.FIXTURE, quote)
        self.assertIsNotNone(join)
        self.assertIsNotNone(join["alias"])
        self.assertTrue(all(u.startswith("https://") for u in join["alias"]["evidence"]))
        self.assertEqual(join["start_diff_h"], 0.0)


class KalshiTicker(unittest.TestCase):
    def test_october_ticker_is_eastern_daylight_time(self):
        iso, method = core.kalshi_start_utc("KXCS2GAME-26OCT211800LNALE")
        self.assertEqual(iso, "2026-10-21T22:00:00Z")
        self.assertIn("new_york", method)

    def test_november_ticker_follows_the_dst_change(self):
        # 1 Nov 2026 is the DST change; 19:00 Eastern is 00:00Z on 2 Nov (EST, UTC-5).
        iso, _ = core.kalshi_start_utc("KXCS2GAME-26NOV011900ABCD")
        self.assertEqual(iso, "2026-11-02T00:00:00Z")

    def test_garbage_returns_no_time(self):
        self.assertIsNone(core.kalshi_start_utc("NOPE")[0])


class LadderUnits(unittest.TestCase):
    def row(self, **kw):
        base = {"team_a": "A", "team_b": "B", "market": None, "vrs": {"team_a": None, "team_b": None},
                "quotes": []}
        base.update(kw)
        return base

    CAL = {"k": 0.4308}

    def test_market_wins_over_the_model(self):
        row = self.row(market={"prob_a": 0.62, "n_sources": 2, "spread_a": 0.01},
                       vrs={"team_a": {"points": 1500, "team": "A", "page_url": "https://x"},
                            "team_b": {"points": 1000, "team": "B", "page_url": "https://x"}})
        line = core.ladder(row, self.CAL, 400)
        self.assertEqual(line["basis"], "market")
        self.assertAlmostEqual(line["prob_a"], 0.62, places=4)

    def test_model_line_recomputes_from_points(self):
        row = self.row(vrs={"team_a": {"points": 1500, "team": "A", "page_url": "https://x"},
                            "team_b": {"points": 1200, "team": "B", "page_url": "https://x"}})
        line = core.ladder(row, self.CAL, 400)
        self.assertEqual(line["basis"], "model")
        expected = core.vrs_prob(300, 0, 0.4308)
        self.assertAlmostEqual(line["prob_a"], round(expected, 4), places=4)

    def test_bound_side_favours_the_rated_team_and_states_the_assumption(self):
        row = self.row(vrs={"team_a": {"points": 1500, "team": "A", "page_url": "https://x"},
                            "team_b": None})
        line = core.ladder(row, self.CAL, 400)
        self.assertEqual(line["basis"], "bound_lo")
        self.assertEqual(line["pick_team"], "A")
        self.assertGreater(line["prob_a"], 0.5)
        self.assertIn("assumed", line["assumption"])
        # Same fixture with the rated side second: the bound must flip to the other team.
        flipped = self.row(vrs={"team_a": None,
                                "team_b": {"points": 1500, "team": "B", "page_url": "https://x"}})
        line_b = core.ladder(flipped, self.CAL, 400)
        self.assertEqual(line_b["pick_team"], "B")
        self.assertAlmostEqual(line_b["prob_a"], 1 - line["prob_a"], places=4)

    def test_no_basis_means_no_line(self):
        self.assertIsNone(core.ladder(self.row(), self.CAL, 400))

    def test_pick_is_always_the_higher_probability(self):
        for prob in (0.02, 0.31, 0.5, 0.69, 0.98):
            row = self.row(market={"prob_a": prob, "n_sources": 1, "spread_a": None})
            line = core.ladder(row, self.CAL, 400)
            self.assertEqual(line["pick_side"], "a" if prob >= 0.5 else "b")


class BoardContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = load_board()
        cls.rows = cls.b["rows"]

    def test_board_metadata(self):
        self.assertEqual(self.b["session"], "2cadfaf2")
        self.assertIn(self.b["mode"], ("live", "committed_snapshot_fallback"))
        self.assertTrue(self.b["generated_utc"].endswith("Z"))
        self.assertIsInstance(self.b["week"].get("weekId"), int)

    def test_every_listed_fixture_has_a_row(self):
        listed = [r for r in self.rows if r.get("listed_in_lobby")]
        self.assertEqual(len(listed), self.b["summary"]["listed_in_lobby"])
        ids = [r["fixture_id"] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)), "duplicate fixture ids")

    def test_states_partition_the_inventory(self):
        states = {}
        for row in self.rows:
            states[row["state"]] = states.get(row["state"], 0) + 1
        self.assertEqual(states, self.b["summary"]["by_state"])

    def test_every_row_links_an_official_hotspawn_page(self):
        for row in self.rows:
            url = row.get("hotspawn_url") or ""
            self.assertTrue(url.startswith("https://"), row["fixture_id"])
            self.assertIn("hotspawn.com", url, row["fixture_id"])
            self.assertNotRegex(url, r"/matches/\d+$", "bare numeric route is not a real permalink")

    def test_resolved_rows_publish_both_probabilities_that_sum_to_one(self):
        for row in self.rows:
            line = row.get("line")
            if not line:
                continue
            self.assertIsInstance(line["prob_a"], float, row["fixture_id"])
            self.assertIsInstance(line["prob_b"], float, row["fixture_id"])
            self.assertAlmostEqual(line["prob_a"] + line["prob_b"], 1.0, places=3, msg=row["fixture_id"])

    def test_pick_is_the_higher_probability_on_every_row(self):
        for row in self.rows:
            line = row.get("line")
            if not line:
                continue
            expected = row["team_a"] if line["prob_a"] >= line["prob_b"] else row["team_b"]
            self.assertEqual(line["pick_team"], expected, row["fixture_id"])
            self.assertAlmostEqual(line["pick_prob"], max(line["prob_a"], line["prob_b"]), places=4)

    def test_market_lines_reproduce_their_consensus(self):
        for row in self.rows:
            line = row.get("line") or {}
            if line.get("basis") != "market":
                continue
            self.assertAlmostEqual(line["prob_a"], row["market"]["prob_a"], places=4, msg=row["fixture_id"])
            self.assertTrue(row["quotes"], "a market line must carry its quotes")
            for q in row["quotes"]:
                self.assertTrue(str(q["public_url"]).startswith("https://"), row["fixture_id"])

    def test_model_lines_recompute_from_published_delta_and_k(self):
        for row in self.rows:
            line = row.get("line") or {}
            if line.get("basis") != "model":
                continue
            detail = line["detail"]
            expected = core.vrs_prob(detail["delta_points"], 0, detail["k"])
            self.assertAlmostEqual(expected, line["prob_a"], places=3, msg=row["fixture_id"])

    def test_bound_rows_carry_their_assumption(self):
        for row in self.rows:
            line = row.get("line") or {}
            if line.get("basis") != "bound_lo":
                continue
            self.assertIn("assumed", line.get("assumption", ""), row["fixture_id"])
            self.assertIn("lower_bound_not_a_point_estimate", row["flags"], row["fixture_id"])

    def test_every_originated_line_links_an_official_source(self):
        for row in self.rows:
            line = row.get("line") or {}
            if not line or line.get("basis") == "market":
                continue
            self.assertTrue(line.get("sources"), row["fixture_id"])
            for url in line["sources"]:
                self.assertTrue(url.startswith("https://"), row["fixture_id"])

    def test_unresolved_rows_are_blank_flagged_and_explained(self):
        unresolved = self.b["unresolved"]
        self.assertEqual(len(unresolved), self.b["summary"]["unresolved"])
        for item in unresolved:
            row = next(r for r in self.rows if r["fixture_id"] == item["fixture_id"])
            self.assertIsNone(row["line"], item["fixture_id"])
            self.assertIn("unresolved_no_verified_basis", row["flags"], item["fixture_id"])
            self.assertTrue(item["reason"].strip(), item["fixture_id"])
        self.assertEqual(sum(1 for r in self.rows if not r["line"]), len(unresolved))

    def test_summary_counts_match_the_rows(self):
        s = self.b["summary"]
        self.assertEqual(s["total_rows"], len(self.rows))
        self.assertEqual(s["with_pick"], sum(1 for r in self.rows if r["line"]))
        self.assertEqual(s["open"], sum(1 for r in self.rows if r["state"] == "open"))
        self.assertEqual(s["open_with_pick"], sum(1 for r in self.rows
                                                   if r["state"] == "open" and r["line"]))
        for basis, key in (("market", "market_rows"), ("model", "model_rows"),
                           ("bound_lo", "bound_rows")):
            self.assertEqual(s[key], sum(1 for r in self.rows
                                         if (r.get("line") or {}).get("basis") == basis))

    def test_no_crowd_percentage_anywhere_in_the_board(self):
        """The prose may *say* crowd data is ignored; no row may *carry* it."""
        blob = json.dumps(self.b).lower()
        for forbidden in ('"crowd"', '"crowd_pct"', '"picked_pct"', '"pick_percentage"',
                          '"popularity"', '"hotspawn_pick"', '"picked_percentage"'):
            self.assertNotIn(forbidden, blob)
        for row in self.rows:
            for key in row:
                self.assertNotIn("crowd", key.lower(), row["fixture_id"])
                self.assertNotIn("picked", key.lower(), row["fixture_id"])

    def test_verification_checks_all_pass(self):
        self.assertTrue(self.b["verification"])
        for check in self.b["verification"]:
            self.assertTrue(check["passed"], f'{check["check"]}: {check["detail"]}')


class SiteContract(unittest.TestCase):
    PAGES = ("index.html", "picks.html", "unresolved.html", "sources.html", "results.html",
             "flagged.html", "method.html")

    def test_every_page_exists_and_is_self_contained_html(self):
        for name in self.PAGES:
            path = SITE / name
            self.assertTrue(path.exists(), name)
            text = path.read_text(encoding="utf-8")
            self.assertIn('<!doctype html>', text, name)
            self.assertIn('name="viewport"', text, name)
            self.assertIn('nav class="bottom"', text, msg=f"{name}: mobile tab bar missing")

    def test_no_page_links_to_a_missing_local_file(self):
        for name in self.PAGES:
            text = (SITE / name).read_text(encoding="utf-8")
            for href in re.findall(r'href="([^"]+)"', text):
                if href.startswith(("http", "#", "mailto")):
                    continue
                target = (SITE / href.split("#")[0]).resolve()
                self.assertTrue(target.exists(), f"{name} -> {href}")

    def test_no_page_uses_a_root_absolute_link(self):
        for name in self.PAGES:
            text = (SITE / name).read_text(encoding="utf-8")
            for href in re.findall(r'href="([^"]+)"', text):
                self.assertFalse(href.startswith("/"), f"{name} -> {href} (breaks under /MaltaProj2/)")

    def test_executive_summary_links_the_picks_lists_and_unresolved_section(self):
        text = (SITE / "index.html").read_text(encoding="utf-8")
        for target in ("picks.html", "unresolved.html", "sources.html", "method.html"):
            self.assertIn(f'href="{target}"', text, target)
        self.assertIn("Unresolved picks &amp; limitations", text)
        self.assertIn("Where everything is", text)

    def test_every_resolved_row_appears_as_a_card_on_the_picks_page(self):
        board = load_board()
        text = (SITE / "picks.html").read_text(encoding="utf-8")
        self.assertEqual(text.count('<article class="card'), len(board["rows"]))
        self.assertEqual(text.count('<div class="pickline">Pick <b>'),
                         sum(1 for r in board["rows"] if r["line"]))

    def test_unresolved_page_names_every_unresolved_fixture(self):
        board = load_board()
        text = (SITE / "unresolved.html").read_text(encoding="utf-8")
        for item in board["unresolved"]:
            self.assertIn(html.escape(item["team_a"]), text, item["fixture_id"])
            self.assertIn(item["fixture_id"], text, item["fixture_id"])

    def test_sources_page_lists_every_feed_read(self):
        board = load_board()
        text = (SITE / "sources.html").read_text(encoding="utf-8")
        for key, meta in board["access"].items():
            self.assertIn(key, text)
            self.assertIn(html.escape(str(meta.get("url")) or ""), text, key)

    def test_flagged_page_publishes_every_flag_with_a_source(self):
        board = load_board()
        text = (SITE / "flagged.html").read_text(encoding="utf-8")
        for flag in board["flags"]:
            self.assertIn(flag["id"], text)
            self.assertIn(html.escape(flag["title"]), text)

    def test_build_is_deterministic(self):
        before = {name: (SITE / name).read_bytes() for name in self.PAGES}
        subprocess.run([sys.executable, str(ROOT / "scripts" / "2cadfaf2" / "build.py")],
                       check=True, cwd=ROOT, capture_output=True)
        after = {name: (SITE / name).read_bytes() for name in self.PAGES}
        self.assertEqual(before, after)


class CollectorContract(unittest.TestCase):
    def test_snapshot_is_labelled_with_its_capture_and_mode(self):
        snap = json.loads((ROOT / "data" / "2cadfaf2" / "snapshot.json").read_text(encoding="utf-8"))
        self.assertEqual(snap["session"], "2cadfaf2")
        self.assertIn(snap["mode"], ("live", "committed_snapshot_fallback"))
        self.assertTrue(snap["collected_to_utc"])
        if snap["mode"] != "live":
            self.assertTrue(snap.get("fallback"), "a fallback capture must say why")

    def test_snapshot_keeps_no_crowd_field(self):
        snap = (ROOT / "data" / "2cadfaf2" / "snapshot.json").read_text(encoding="utf-8").lower()
        self.assertNotIn("pick_percentage", snap)
        self.assertNotIn("crowd", snap)

    def test_hltv_probe_result_is_recorded_honestly(self):
        snap = json.loads((ROOT / "data" / "2cadfaf2" / "snapshot.json").read_text(encoding="utf-8"))
        probe = (snap.get("access_log") or {}).get("hltv_probe")
        self.assertIsNotNone(probe, "the collector must probe HLTV and record the result")
        self.assertIn("status", probe)


class RootExecutiveSummary(unittest.TestCase):
    """The root landing page must lead with this desk and link to the live pick list.

    The published site is built from the committed files, so a stale hero is a real defect: the
    counts on the front page have to be the counts in the board it links to.
    """

    def setUp(self):
        self.html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.board = json.loads((ROOT / "data" / "2cadfaf2" / "board.json").read_text(encoding="utf-8"))

    def test_hero_block_is_present_and_first(self):
        self.assertIn("<!-- pickcenter:start -->", self.html)
        self.assertIn("<!-- pickcenter:end -->", self.html)
        start = self.html.index("<!-- pickcenter:start -->")
        end = self.html.index("<!-- pickcenter:end -->")
        # no other start-here desk may sit above it
        self.assertNotIn("START HERE", self.html[:start])
        self.assertGreater(end, start)

    def test_hero_links_the_pick_list_and_the_unresolved_section(self):
        block = self.html[self.html.index("<!-- pickcenter:start -->"):self.html.index("<!-- pickcenter:end -->")]
        for target in ("pickcenter/picks.html", "pickcenter/unresolved.html",
                       "pickcenter/index.html", "pickcenter/sources.html"):
            self.assertIn('href="%s"' % target, block, "the executive summary must link %s" % target)

    def test_hero_counts_match_the_board(self):
        block = self.html[self.html.index("<!-- pickcenter:start -->"):self.html.index("<!-- pickcenter:end -->")]
        s = self.board["summary"]
        for key, label in (("total_rows", "matches listed"), ("with_pick", "with a pick"),
                           ("unresolved", "unresolved"), ("open", "still open")):
            self.assertIn("<strong>%s</strong>" % s[key], block,
                          "hero must show the board's %s count (%s)" % (label, key))

    def test_hero_is_not_a_second_h1(self):
        self.assertEqual(self.html.count("<h1"), 1, "exactly one h1 per page")



if __name__ == "__main__":
    unittest.main(verbosity=2)
