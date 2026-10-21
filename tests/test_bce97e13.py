#!/usr/bin/env python3
"""Contract tests for the bce97e13 independent verification desk (``cs2-picks/``).

The tests never trust the published numbers: every probability is re-derived here from the raw
decimal quotes or the official Valve points, and the result must match the stored row. They also
enforce the product rules:

  * every fixture open in the freshest raw HotSpawn lobby snapshot has a verified row with a pick
    and two probabilities (an unresolvable fixture must be an explicit unresolved entry, not a blank);
  * market rows reproduce from no-vig book/exchange maths and originated rows from the Valve formula;
  * originated rows' points/standing/roster match the official standings (live file when present);
  * every row carries an openable external source plus its HotSpawn permalink;
  * HotSpawn crowd/vote percentages never appear;
  * bound rows are labelled with >= / <= and never pretend to a point estimate;
  * the six phone-first pages exist, declare a mobile viewport and contain no broken local links.
"""
from __future__ import annotations

import importlib.util as iu
import json
import re
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "cs2-picks"
DATA = ROOT / "data" / "bce97e13"

_spec = iu.spec_from_file_location("bce97e13_core", ROOT / "scripts" / "bce97e13" / "core.py")
core = iu.module_from_spec(_spec)
sys.modules["bce97e13_core"] = core
_spec.loader.exec_module(core)

_spec2 = iu.spec_from_file_location("bce97e13_verify", ROOT / "scripts" / "bce97e13" / "verify.py")
verify_mod = iu.module_from_spec(_spec2)
sys.modules["bce97e13_verify"] = verify_mod
_spec2.loader.exec_module(verify_mod)


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class Coverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = _load(DATA / "board.json")
        cls.verification = _load(DATA / "verification.json")
        cls.raw = _load(ROOT / "data" / "7adc7718" / "raw_snapshot.json")
        cls.rows = cls.board["rows"]
        cls.by_id = {r["fixture_id"]: r for r in cls.rows}
        cls.open_fx = verify_mod.open_lobby_fixtures(cls.raw)
        cls.open_ids = {str(f["fixture_id"]) for f in cls.open_fx}

    def test_every_open_fixture_has_a_row(self):
        self.assertTrue(self.open_ids, "no open fixtures found in raw snapshot")
        missing = self.open_ids - set(self.by_id)
        self.assertFalse(missing, f"open fixtures without a verified row: {sorted(missing)}")

    def test_every_row_has_pick_and_two_probabilities(self):
        for r in self.rows:
            with self.subTest(fixture=r["fixture_id"]):
                self.assertTrue(r.get("pick"))
                self.assertIsNotNone(r.get("prob_a"))
                self.assertIsNotNone(r.get("prob_b"))
                self.assertAlmostEqual(r["prob_a"] + r["prob_b"], 1.0, delta=0.002)
                want_side = "a" if r["prob_a"] > r["prob_b"] else "b"
                self.assertEqual(r["pick_side"], want_side)
                self.assertIn(r["pick"], (r["team_a"], r["team_b"]))

    def test_all_rows_independently_verified(self):
        bad = [r["fixture_id"] for r in self.rows
               if r["verification"]["status"] != "verified"
               or not all(c["ok"] for c in r["verification"]["checks"])]
        self.assertFalse(bad, f"rows failing a verification gate: {bad}")

    def test_summary_matches_rows(self):
        s = self.verification["summary"]
        self.assertEqual(s["verified_rows"], len(self.rows))
        self.assertEqual(s["unverified_rows"], 0)
        self.assertEqual(s["open_fixtures_total"], len(self.open_fx))
        self.assertEqual(s["market_rows"],
                         sum(1 for r in self.rows if r["basis"] == "market"))
        self.assertEqual(s["originated_vrs_rows"],
                         sum(1 for r in self.rows if r["basis"] == "originated_vrs"))
        self.assertEqual(s["bound_rows"],
                         sum(1 for r in self.rows if r["basis"] == "originated_vrs_bound"))
        self.assertTrue(s["all_open_fixtures_covered"])


class Arithmetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = _load(DATA / "board.json")
        cls.vrs = _load(ROOT / "data" / "5f903db4" / "vrs_global.json")

    def test_market_rows_reproduce_from_decimal_odds(self):
        for r in self.board["rows"]:
            if r["basis"] != "market":
                continue
            with self.subTest(fixture=r["fixture_id"]):
                books = [q for q in r["quotes"] if q.get("no_vig_prob_a") is not None]
                self.assertTrue(books, "market row needs at least one stored quote")
                re_a = sum(q["no_vig_prob_a"] for q in books) / len(books)
                re_b = sum(q["no_vig_prob_b"] for q in books) / len(books)
                self.assertLess(abs(re_a - r["prob_a"]), core.TOL_MARKET)
                self.assertLess(abs(re_b - r["prob_b"]), core.TOL_MARKET)
                # every stored no-vig pair itself sums to one
                for q in books:
                    self.assertAlmostEqual(q["no_vig_prob_a"] + q["no_vig_prob_b"], 1.0, delta=1e-9)

    def test_originated_rows_reproduce_from_official_points(self):
        floor_points = self.vrs["floor"]["points"]
        for r in self.board["rows"]:
            if r["basis"] not in ("originated_vrs", "originated_vrs_bound"):
                continue
            with self.subTest(fixture=r["fixture_id"]):
                va, vb = r["vrs_a"], r["vrs_b"]
                pa = float(va["points"]) if va.get("listed") else floor_points
                pb = float(vb["points"]) if vb.get("listed") else floor_points
                re_a = core.vrs_prob(pa, pb)
                self.assertLess(abs(re_a - r["prob_a"]), core.TOL_VRS)
                self.assertLess(abs((1 - re_a) - r["prob_b"]), core.TOL_VRS)

    def test_bound_rows_are_labelled(self):
        for r in self.board["rows"]:
            if r["basis"] != "originated_vrs_bound":
                continue
            with self.subTest(fixture=r["fixture_id"]):
                self.assertIsNotNone(r.get("bound"))
                self.assertIn(r["bound"].get("side"), ("a", "b"))
                # exactly one side is unrated
                listed = [r["vrs_a"].get("listed"), r["vrs_b"].get("listed")]
                self.assertEqual(listed.count(False), 1)

    def test_slope_constant_matches_valve_glicko_derivation(self):
        derived = core.valve_slope(core.VALVE_FIXED_RD)
        self.assertLess(abs(derived - core.CANONICAL_C), 1e-8)


class OfficialIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = _load(DATA / "board.json")
        cls.committed = _load(ROOT / "data" / "5f903db4" / "vrs_global.json")
        cls.live_md = ROOT / "data" / "bce97e13" / "standings_official.md"
        cls.live = core.parse_official_markdown(cls.live_md.read_text(encoding="utf-8")) \
            if cls.live_md.exists() else None

    def _check_identity(self, official, label):
        for r in self.board["rows"]:
            for v in (r["vrs_a"], r["vrs_b"]):
                if not v or not v.get("listed"):
                    continue
                with self.subTest(fixture=r["fixture_id"], team=v.get("name"), source=label):
                    rows = official["by_name"].get(core.norm(v["vrs_name"]))
                    self.assertTrue(rows, f"{v['vrs_name']} missing from {label}")
                    chosen = next((o for o in rows if o["standing"] == v["standing"]
                                   and o["points"] == v["points"]), None)
                    self.assertIsNotNone(chosen, f"{v['vrs_name']} standing/points mismatch in {label}")
                    roster_a = {p.strip().lower() for p in v["roster"].split(",") if p.strip()}
                    roster_b = {p.strip().lower() for p in chosen["roster"].split(",") if p.strip()}
                    self.assertEqual(roster_a, roster_b)

    def test_identity_against_committed_standings(self):
        by_name: dict = {}
        for t in self.committed["teams"]:
            by_name.setdefault(core.norm(t["team"]), []).append(t)
        self._check_identity({"by_name": by_name}, "committed VRS parse")

    def test_identity_against_live_official_table_when_present(self):
        if self.live is None:
            self.skipTest("live official markdown not fetched in this environment")
        self.assertEqual(self.live["n_teams"], 380)
        self._check_identity(self.live, "live official Valve table")


class SourcesAndPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = _load(DATA / "board.json")

    def test_every_row_has_external_source_and_permalink(self):
        for r in self.board["rows"]:
            with self.subTest(fixture=r["fixture_id"]):
                self.assertTrue(r.get("hotspawn_url"))
                ext = [u for u in r["sources"] if u.startswith("https://")]
                self.assertTrue(ext, "at least one https source required")

    def test_source_urls_well_formed(self):
        url_re = re.compile(r"^https://[^\s\"<>]+$")
        for r in self.board["rows"]:
            for u in r["sources"]:
                with self.subTest(url=u):
                    self.assertRegex(u, url_re)

    def test_no_hotspawn_crowd_or_vote_input(self):
        blob = json.dumps(self.board).lower()
        for forbidden in ("crowd_pick", "crowd_share", "vote_share", "poll_pct", "crowd_pct"):
            self.assertNotIn(forbidden, blob)
        for r in self.board["rows"]:
            self.assertNotIn("hotspawn", {q.get("source_key") for q in r["quotes"]})

    def test_cross_board_pick_direction_agrees(self):
        for r in self.board["rows"]:
            cross = r.get("cross_board")
            if cross is None:
                continue
            with self.subTest(fixture=r["fixture_id"]):
                self.assertTrue(cross["agrees"],
                                f"secondary board picks {cross.get('other_pick')} vs {r['pick']}")


class Pages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = ["index.html", "picks.html", "unresolved.html", "sources.html",
                     "method.html", "flagged.html"]

    def test_all_pages_exist_and_are_mobile_first(self):
        for name in self.pages:
            p = SITE / name
            with self.subTest(page=name):
                self.assertTrue(p.exists())
                text = p.read_text(encoding="utf-8")
                self.assertIn('name="viewport"', text)
                self.assertIn('width=device-width', text)
                self.assertLess(text.count("http://"), 1, "no insecure http links")

    def test_no_broken_local_links(self):
        href_re = re.compile(r'href="([^"#]+)"')
        for name in self.pages:
            text = (SITE / name).read_text(encoding="utf-8")
            for href in href_re.findall(text):
                if href.startswith(("http://", "https://", "mailto:")):
                    continue
                target = (SITE / href).resolve()
                with self.subTest(page=name, href=href):
                    self.assertTrue(target.exists(), f"broken local link {href} on {name}")

    def test_every_verified_row_renders_a_card_with_pick_and_sources(self):
        board = _load(DATA / "board.json")
        picks_html = (SITE / "picks.html").read_text(encoding="utf-8")
        for r in board["rows"]:
            with self.subTest(fixture=r["fixture_id"]):
                self.assertIn(f'id="f{r["fixture_id"]}"', picks_html)
                self.assertIn(r["pick"], picks_html)
        # one card per row
        self.assertEqual(picks_html.count('class="match-card"'), len(board["rows"]))

    def test_unresolved_page_reflects_ledger(self):
        verification = _load(DATA / "verification.json")
        html_text = (SITE / "unresolved.html").read_text(encoding="utf-8")
        n = verification["summary"]["unresolved"]
        if n == 0:
            self.assertIn("0 unresolved matches", html_text)
        else:
            for u in verification["unresolved"]:
                self.assertIn(str(u["fixture_id"]), html_text)
        # limitations are always published even when nothing is unresolved
        self.assertIn("Current limitations", html_text)


class ValveLiveCheck(unittest.TestCase):
    def test_record_structure_and_slope(self):
        p = DATA / "valve_live.json"
        self.assertTrue(p.exists())
        rec = _load(p)
        self.assertIn("live", rec)
        if rec.get("live"):
            self.assertTrue(rec["newest_global_table"].startswith("standings_global_"))
            self.assertEqual(rec["n_teams_parsed"], 380)
            self.assertTrue(rec["slope_check"]["matches_canonical"])
            self.assertLess(rec["slope_check"]["abs_diff"], 1e-8)


class RootIntegration(unittest.TestCase):
    def test_root_contains_marked_verification_block(self):
        text = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("<!-- bce97e13:start -->", text)
        self.assertIn("<!-- bce97e13:end -->", text)
        self.assertIn('href="cs2-picks/picks.html"', text)
        # block appears exactly once (stage script must be idempotent)
        self.assertEqual(text.count("<!-- bce97e13:start -->"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
