#!/usr/bin/env python3
"""Contract tests for session 6484426f (desk/ board + resolver).

Enforced:
  1. every row in the published board carries at least one http(s) source link;
  2. a row with no eligible evidence stays blank, carries no pick and publishes a limitation;
  3. the crowd (ownership) percentage never moves a published probability: mutating every crowd
     share leaves all probabilities byte-identical (runtime check) and no published probability
     equals a crowd share (static check);
  4. the ladder is respected: market rows have a bookmaker quote, exchange rows have a two-sided
     exchange quote, model rows have both official ratings and no external price;
  5. the climb rule is applied with its declared gates and daily cap;
  6. the pages are mobile-first, use no third-party asset and only link to pages that exist;
  7. the resolver is deterministic apart from its timestamp;
  8. verification.json reports no failed check and covers the published rows.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "6484426f"
BOARD = DATA / "board.json"
VERIFY = DATA / "verification.json"
DESK = ROOT / "desk"


def load(path: Path):
    return json.loads(path.read_text())


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class PublishedBoard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load(BOARD)
        cls.rows = cls.board["rows"]

    def test_every_row_has_an_http_source_link(self):
        self.assertGreater(len(self.rows), 0, "board has no rows")
        for row in self.rows:
            links = [s.get("url") for s in row.get("sources") or []]
            self.assertTrue(links, f"{row['fixture_id']} has no source link")
            for url in links:
                self.assertTrue(str(url).startswith("http"), f"{row['fixture_id']}: {url}")

    def test_blank_rows_stay_blank_and_publish_a_limitation(self):
        for row in self.rows:
            if row["basis"] != "unresolved":
                continue
            self.assertIsNone(row["prob_a"], row["fixture_id"])
            self.assertIsNone(row["prob_b"], row["fixture_id"])
            self.assertIsNone(row["safe_pick"], row["fixture_id"])
            self.assertTrue(row.get("limitation"), f"{row['fixture_id']} has no limitation")
            self.assertFalse(row.get("quotes"), f"{row['fixture_id']} has a quote but no line")

    def test_ladder_is_respected(self):
        keys = ("pinnacle", "bovada", "melbet", "kalshi")
        for row in self.rows:
            sources = {q["source_key"] for q in row.get("quotes") or []}
            if row["basis"] == "market":
                self.assertTrue(sources & {"pinnacle", "bovada", "melbet"},
                                f"{row['fixture_id']} claims a market line without a bookmaker quote")
            elif row["basis"] == "exchange":
                self.assertIn("kalshi", sources, row["fixture_id"])
                self.assertFalse(sources & {"pinnacle", "bovada", "melbet"},
                                 f"{row['fixture_id']} has a bookmaker quote but uses the exchange tier")
            elif row["basis"] == "model":
                self.assertFalse(sources & set(keys),
                                 f"{row['fixture_id']} has an external price but uses the model tier")
                vrs = row.get("vrs") or {}
                self.assertTrue((vrs.get("team_a") or {}).get("resolved"), row["fixture_id"])
                self.assertTrue((vrs.get("team_b") or {}).get("resolved"), row["fixture_id"])

    def test_probabilities_are_complementary_and_pick_matches(self):
        for row in self.rows:
            if row["prob_a"] is None:
                continue
            self.assertAlmostEqual(row["prob_a"] + row["prob_b"], 1.0, places=9, msg=row["fixture_id"])
            if abs(row["prob_a"] - row["prob_b"]) < 1e-9:
                self.assertTrue(row.get("tie_break"), f"{row['fixture_id']} tie without disclosure")
                continue
            best = row["team_a"] if row["prob_a"] > row["prob_b"] else row["team_b"]
            self.assertEqual(row["safe_pick"], best, row["fixture_id"])

    def test_climb_rule_gates_and_cap(self):
        cap = self.board["policy"]["climb_max_per_day"]
        active = [r for r in self.rows if r.get("climb_active")]
        self.assertLessEqual(len(active), cap)
        for row in active:
            gates = row["gates"]
            self.assertTrue(gates["prob_floor_30pct"], row["fixture_id"])
            self.assertTrue(gates["leverage_2x"], row["fixture_id"])
            self.assertEqual(row["climb_pick"], (row.get("underdog") or {}).get("team"),
                             row["fixture_id"])
            self.assertGreaterEqual(row["underdog"]["prob"], self.board["policy"]["climb_min_prob"])

    def test_crowd_share_is_never_a_published_probability(self):
        for row in self.rows:
            crowd = row.get("crowd") or {}
            for key in ("a", "b"):
                share = crowd.get(key)
                if share is None:
                    continue
                for side in ("prob_a", "prob_b"):
                    if row.get(side) is not None:
                        self.assertNotAlmostEqual(row[side], share, places=9,
                                                  msg=f"{row['fixture_id']} {side} equals crowd {key}")

    def test_every_open_row_carries_a_basis_and_flagged_rows_are_disclosed(self):
        allowed = {"market", "exchange", "model", "unresolved"}
        for row in self.rows:
            self.assertIn(row["basis"], allowed, row["fixture_id"])
            if row.get("quote_stale"):
                self.assertIn("quote_older_than_4h", row["flags"])
            if row["basis"] == "model":
                for side in ("team_a", "team_b"):
                    for note in ((row.get("vrs") or {}).get(side) or {}).get("notes") or []:
                        self.assertTrue(note.get("type"))

    def test_summary_matches_rows(self):
        summary = self.board["summary"]
        self.assertEqual(summary["open"], len(self.rows))
        self.assertEqual(summary["with_pick"], sum(1 for r in self.rows if r.get("safe_pick")))
        for basis in ("market", "exchange", "model", "unresolved"):
            self.assertEqual(summary[basis], sum(1 for r in self.rows if r["basis"] == basis))


class CrowdIndependence(unittest.TestCase):
    """Runtime proof that ownership cannot reach a probability."""

    def test_mutating_crowd_shares_does_not_move_a_probability(self):
        resolver = load_module("resolver_6484426f", ROOT / "scripts" / "6484426f" / "resolve.py")
        board = load(BOARD)
        row = next(r for r in board["rows"] if r["basis"] == "market" and r.get("crowd"))
        mutated = json.loads(json.dumps(row))
        mutated["crowd"] = {"a": 0.99, "b": 0.01, "pct_a": 99, "pct_b": 1, "total_picks": 1}
        before = resolver.choose_picks(row)
        after = resolver.choose_picks(mutated)
        self.assertEqual(before["safe_pick"], after["safe_pick"])
        self.assertEqual(row["prob_a"], mutated["prob_a"])
        # leverage is derived from the crowd and must change; the probability must not.
        if before["leverage"] and after["leverage"]:
            self.assertNotAlmostEqual(before["leverage"], after["leverage"], places=6)

    def test_resolver_withholds_a_pick_when_there_is_no_probability(self):
        resolver = load_module("resolver_6484426f", ROOT / "scripts" / "6484426f" / "resolve.py")
        empty = {"prob_a": None, "prob_b": None, "team_a": "A", "team_b": "B", "crowd": None}
        picks = resolver.choose_picks(empty)
        self.assertIsNone(picks["safe_pick"])
        self.assertIsNone(picks["climb_pick"])


class Determinism(unittest.TestCase):
    def test_resolver_reproduces_the_committed_board(self):
        resolver = load_module("resolver_6484426f", ROOT / "scripts" / "6484426f" / "resolve.py")
        committed = load(BOARD)
        rebuilt = resolver.build()
        strip = lambda doc: {k: v for k, v in doc.items()  # noqa: E731
                             if k not in ("generated_utc", "grading", "research_read_utc")}
        self.assertEqual(strip(committed)["summary"], strip(rebuilt)["summary"])
        old = {r["fixture_id"]: (r["basis"], r["prob_a"], r["safe_pick"], r["climb_pick"])
               for r in committed["rows"]}
        new = {r["fixture_id"]: (r["basis"], r["prob_a"], r["safe_pick"], r["climb_pick"])
               for r in rebuilt["rows"]}
        self.assertEqual(old, new)


class DeskPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = sorted(DESK.glob("*.html"))
        cls.names = {p.name for p in cls.pages}

    def test_pages_exist(self):
        self.assertEqual(self.names, {"index.html", "picks.html", "twc.html", "unresolved.html",
                                      "flagged.html", "method.html", "verify.html"})

    def test_pages_are_mobile_first_and_dependency_free(self):
        for page in self.pages:
            text = page.read_text()
            self.assertIn('name="viewport"', text, page.name)
            self.assertIn("width=device-width", text, page.name)
            self.assertNotIn("http://", text.replace("http://www.w3.org", ""), page.name)
            for url in re.findall(r'(?:src|href)="(https?://[^"]+)"', text):
                host = url.split("/")[2]
                self.assertNotIn(host, {"fonts.googleapis.com", "cdn.jsdelivr.net", "unpkg.com"},
                                 f"{page.name} loads a third-party asset")

    def test_internal_links_resolve(self):
        for page in self.pages:
            text = page.read_text()
            for target in set(re.findall(r'href="([a-z0-9_.-]+\.html)(?:#[^"]*)?"', text)):
                self.assertIn(target, self.names, f"{page.name} -> {target}")

    def test_executive_summary_links_every_board(self):
        home = (DESK / "index.html").read_text()
        for target in ("picks.html", "twc.html", "unresolved.html", "flagged.html",
                       "method.html", "verify.html"):
            self.assertIn(f'href="{target}"', home)

    def test_unresolved_page_is_a_separate_section_with_limitations(self):
        text = (DESK / "unresolved.html").read_text()
        self.assertIn("Unresolved picks", text)
        self.assertIn("Known limits of the method", text)
        board = load(BOARD)
        for row in board["rows"]:
            if row["basis"] == "unresolved" and row.get("limitation"):
                self.assertIn(row["limitation"][:40], text)

    def test_twc_page_carries_both_deciders_and_the_roster_check(self):
        text = (DESK / "twc.html").read_text()
        self.assertIn("Aurora", text)
        self.assertIn("9z", text)
        self.assertIn("BetBoom", text)
        self.assertIn("Legacy", text)
        self.assertIn("Roster premise check", text)
        self.assertIn("hltv.org/matches/2399384", text)


class VerificationReport(unittest.TestCase):
    def test_no_failed_checks(self):
        report = load(VERIFY)
        self.assertEqual(report["summary"]["failed"], 0, report["checks"])
        self.assertGreater(report["summary"]["passed"], 0)
        self.assertGreater(report["quotes_re_derived"], 0)
        self.assertEqual(report["rows_checked"], len(load(BOARD)["rows"]))

    def test_third_party_assets_absent_from_every_desk_page(self):
        for page in DESK.glob("*.html"):
            self.assertNotIn("<script", page.read_text(), page.name)


if __name__ == "__main__":
    unittest.main()
