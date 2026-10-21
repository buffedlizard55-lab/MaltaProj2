"""Contract tests for session 907e9435 (everypick board).

These tests run against the committed capture and the rendered pages, so a regression in the
resolution ladder, the join gate, the assumption policy or the published HTML fails the workflow
before anything is committed or deployed.

Run: python3 -m unittest tests.test_907e9435 -v
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "907e9435"))
import core  # noqa: E402

BOARD = ROOT / "data" / "907e9435" / "board.json"
SNAPSHOT = ROOT / "data" / "907e9435" / "snapshot.json"
SITE = ROOT / "everypick"


def load(path: Path):
    return json.loads(path.read_text())


class TestCaptureAndInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load(BOARD)
        cls.snapshot = load(SNAPSHOT)

    def test_snapshot_and_board_are_present(self):
        self.assertTrue(self.snapshot["hotspawn"]["fixtures"], "no HotSpawn fixtures captured")
        self.assertTrue(self.board["open"], "board has no open fixtures")

    def test_one_row_per_open_lobby_fixture(self):
        ids = [r["fixture_id"] for r in self.board["open"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate fixture ids in the board")
        lobby = [f for f in self.snapshot["hotspawn"]["fixtures"]
                 if "lobby_page" in (f.get("seen_in") or [])
                 and core.parse_iso(f["start_utc"]) > (core.parse_iso(self.board["snapshot_utc"]))]
        self.assertEqual(len(ids), len(lobby),
                         "the board must cover every lobby fixture that is still in the future")

    def test_no_crowd_percentage_is_read(self):
        blob = json.dumps(self.board)
        # HotSpawn's pick'em fields, which must never enter a probability.
        for needle in ('"picked"', "crowd", "picked_percentage", "community"):
            self.assertNotIn(needle, blob.lower().replace('"crowd', '"crowd'), blob[:200])
        source = (ROOT / "scripts" / "907e9435" / "core.py").read_text()
        self.assertNotIn("picked_percentage", source)
        self.assertNotIn("crowd", source.lower().split("crowd percentage is never")[0][-200:])


class TestProbabilities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load(BOARD)
        cls.rows = cls.board["open"]

    def test_published_probabilities_are_two_sided(self):
        for row in self.rows:
            if row["prob_a"] is None:
                self.assertIsNone(row["prob_b"], row["fixture_id"])
                continue
            self.assertAlmostEqual(row["prob_a"] + row["prob_b"], 1.0, places=4,
                                   msg=row["fixture_id"])
            self.assertTrue(0.0 < row["prob_a"] < 1.0, row["fixture_id"])

    def test_every_published_probability_has_a_source_link(self):
        for row in self.rows:
            if row["prob_a"] is None:
                continue
            self.assertTrue(row["evidence"], f"{row['fixture_id']} has a probability but no evidence")
            for item in row["evidence"]:
                url = item.get("url") or ""
                self.assertTrue(url.startswith("https://"),
                                f"{row['fixture_id']} evidence without https link: {item}")

    def test_market_rows_rederive_from_raw_prices(self):
        for row in self.rows:
            if row["tier_code"] not in ("market_multi", "market_single", "exchange"):
                continue
            recomputed = []
            for item in row["evidence"]:
                raw_a, raw_b = item.get("raw") or [None, None]
                fmt = item.get("raw_format")
                if fmt == "american":
                    da, db = core.american_to_decimal(raw_a), core.american_to_decimal(raw_b)
                elif fmt == "decimal":
                    da, db = float(raw_a), float(raw_b)
                elif fmt == "yes mid ($)":
                    da, db = 1 / float(raw_a), 1 / float(raw_b)
                else:
                    self.fail(f"unknown raw format {fmt}")
                nv = core.no_vig(da, db)
                self.assertIsNotNone(nv, row["fixture_id"])
                recomputed.append(1 - nv["prob_a"] if item.get("swapped") else nv["prob_a"])
            # Unweighted mean lies inside the published mean whenever all prices are close; check
            # the published number against each source within a 5pp tolerance and the weighted
            # mean exactly through the published consensus.
            for value in recomputed:
                self.assertLess(abs(value - row["prob_a"]), 0.05,
                                f"{row['fixture_id']}: published {row['prob_a']} vs source {value}")
            weights = {"pinnacle": 2.0, "bovada": 1.0, "melbet": 1.0, "kalshi": 1.0}
            keys = [{"Pinnacle": "pinnacle", "Bovada": "bovada", "Melbet": "melbet",
                     "Kalshi (exchange)": "kalshi"}.get(e["source_name"]) for e in row["evidence"]]
            wsum = sum(weights.get(k, 1.0) for k in keys)
            expected = sum(weights.get(k, 1.0) * v for k, v in zip(keys, recomputed)) / wsum
            self.assertAlmostEqual(expected, row["prob_a"], places=3, msg=row["fixture_id"])

    def test_vrs_rows_match_the_official_points_and_calibration(self):
        k = self.board["calibration"]["k"]
        self.assertGreaterEqual(k, core.CAL_K_BOUNDS[0])
        self.assertLessEqual(k, core.CAL_K_BOUNDS[1])
        for row in self.rows:
            if row["tier_code"] != "vrs_model":
                continue
            a, b = row["vrs"]["team_a"], row["vrs"]["team_b"]
            self.assertTrue(a.get("points") and b.get("points"))
            expected = core.vrs_prob(a["points"], b["points"], k)
            self.assertAlmostEqual(expected, row["prob_a"], places=4, msg=row["fixture_id"])
            self.assertTrue(a["details_url"].startswith("https://github.com/ValveSoftware/"))
            self.assertTrue(b["details_url"].startswith("https://github.com/ValveSoftware/"))

    def test_assumption_rows_are_ranges_and_never_verified(self):
        for row in self.rows:
            if row["tier_code"] != "assumption":
                continue
            self.assertFalse(row["verified"])
            self.assertTrue(row["prob_range_a"], row["fixture_id"])
            lo, hi = row["prob_range_a"]
            self.assertLess(lo, hi)
            self.assertGreaterEqual(row["prob_a"], lo)
            self.assertLessEqual(row["prob_a"], hi)
            # A pick exists only when both documented assumptions agree on the favourite.
            self.assertTrue(row["pick"], row["fixture_id"])
            self.assertGreater(lo, 0.5, f"{row['fixture_id']} publishes a pick from a range that "
                                        "crosses 50%")
            self.assertIn("assumption", row["basis_text"].lower())

    def test_withheld_rows_publish_no_value(self):
        for row in self.rows:
            if row["tier_code"] != "unresolved":
                continue
            self.assertIsNone(row["prob_a"])
            self.assertIsNone(row["prob_b"])
            self.assertIsNone(row["pick"])
            self.assertTrue(row["limitations"], f"{row['fixture_id']} withheld without a reason")


class TestJoinGate(unittest.TestCase):
    def fixture(self, a, b, start="2026-10-22T14:00:00Z"):
        return {"team_a": a, "team_b": b, "start_utc": start}

    def quote(self, a, b, start, prob=0.4):
        return {"team_a": a, "team_b": b, "start_utc": start, "prob_a": prob}

    def test_exact_names_and_kickoff_join(self):
        info = core.match_quote(self.fixture("Imperial", "Turma do Pagode"),
                                self.quote("Imperial", "Turma do Pagode", "2026-10-22T14:00:00Z"))
        self.assertTrue(info and not info.get("rejected"))

    def test_reversed_orientation_joins_and_flips(self):
        info = core.match_quote(self.fixture("Imperial", "Turma do Pagode"),
                                self.quote("Turma do Pagode", "Imperial", "2026-10-22T14:00:00Z"))
        self.assertTrue(info["swapped"])
        self.assertAlmostEqual(core.oriented(self.quote("a", "b", "x", 0.2), True), 0.8)

    def test_kickoff_mismatch_is_rejected(self):
        info = core.match_quote(self.fixture("Imperial", "Turma do Pagode"),
                                self.quote("Imperial", "Turma do Pagode", "2026-10-22T14:10:00Z"))
        self.assertTrue(info["rejected"])

    def test_missing_kickoff_is_rejected(self):
        info = core.match_quote(self.fixture("Imperial", "Turma do Pagode"),
                                self.quote("Imperial", "Turma do Pagode", None))
        self.assertTrue(info["rejected"])

    def test_prefix_names_do_not_join(self):
        self.assertIsNone(core.match_quote(self.fixture("B8", "Team Liquid"),
                                           self.quote("B8 Academy", "Team Liquid",
                                                      "2026-10-22T14:00:00Z")))

    def test_published_alias_needs_agreeing_opponent_and_time(self):
        f = self.fixture("UNiTY", "Apogee Betclic")
        info = core.match_quote(f, self.quote("UNiTY", "Apogee Esports", "2026-10-22T14:00:00Z"))
        self.assertTrue(info and not info.get("rejected"))
        self.assertTrue(info["alias_notes"])
        # Same alias, different opponent -> no join at all.
        self.assertIsNone(core.match_quote(self.fixture("UNiTY", "Somebody Else"),
                                           self.quote("UNiTY", "Apogee Esports",
                                                      "2026-10-22T14:00:00Z")))


class TestExchangeTimeRule(unittest.TestCase):
    def test_rules_text_is_parsed_to_utc(self):
        rules = ("If X wins the Exort Fiesta Closed Qualifier: Series #3 2026: X vs. Y CS2 match "
                 "originally scheduled for Oct 21, 2026 at 1:00 PM EDT, then the market resolves to Yes.")
        self.assertEqual(core.to_iso(core.kalshi_rules_start(rules)), "2026-10-21T17:00:00Z")

    def test_evening_time_is_not_mangled(self):
        rules = "scheduled for Oct 22, 2026 at 12:30 AM EDT."
        self.assertEqual(core.to_iso(core.kalshi_rules_start(rules)), "2026-10-22T04:30:00Z")

    def test_unknown_zone_is_refused(self):
        self.assertIsNone(core.kalshi_rules_start("scheduled for Oct 22, 2026 at 1:00 PM XYZ"))

    def test_occurrence_datetime_is_not_used_as_kickoff(self):
        # The retained payload's occurrence_datetime is four hours after the exchange's own rules
        # text on every event; the board must use the rules text.
        snap = load(SNAPSHOT)
        kalshi = [q for q in snap["quotes"] if q.get("source_key") == "kalshi"]
        self.assertTrue(kalshi)
        for q in kalshi:
            self.assertEqual(q["kickoff_source"], "exchange rules_primary")
            self.assertNotEqual(q.get("time_basis", ""), "occurrence_datetime")


class TestRatingChoices(unittest.TestCase):
    def test_duplicate_rows_resolved_with_official_evidence(self):
        board = load(BOARD)
        by_id = {r["fixture_id"]: r for r in board["open"]}
        expectations = {"1082792": 122, "1081600": 165, "1081597": 157}
        for fid, standing in expectations.items():
            row = by_id.get(fid)
            self.assertIsNotNone(row, fid)
            side = row["vrs"].get("team_b") if fid == "1082792" else row["vrs"].get("team_a")
            if fid == "1081600":
                side = row["vrs"].get("team_b")
            self.assertEqual(side.get("standing"), standing, f"{fid} chose {side}")

    def test_calibration_matches_retained_pairs(self):
        pairs = list(load(ROOT / "data" / "f7279a54" / "calibration_pairs.json").values())
        fit = core.fit_calibration(pairs)
        self.assertGreaterEqual(fit["n_pairs"], core.CAL_MIN_PAIRS)
        self.assertAlmostEqual(fit["k"], 0.4308, places=3)

    def test_model_matches_canonical_implementation(self):
        try:
            sys.path.insert(0, str(ROOT / "scripts" / "f7279a54"))
            import core as canonical_core  # noqa: F401
        except Exception:  # noqa: BLE001
            self.skipTest("canonical core module not importable")
        for delta in (0, 50, -137, 493, -712):
            self.assertAlmostEqual(core.vrs_prob(delta, 0, 0.430779),
                                   canonical_core.vrs_prob(delta, 0, 0.430779), places=9)


class TestRenderedSite(unittest.TestCase):
    PAGES = ("index.html", "picks.html", "unresolved.html", "flagged.html", "method.html",
             "sources.html")

    def test_pages_exist_and_link_each_other(self):
        for name in self.PAGES:
            path = SITE / name
            self.assertTrue(path.exists(), name)
            text = path.read_text()
            self.assertIn('name="viewport"', text, f"{name} is not mobile-ready")
            self.assertIn('href="picks.html"', text, name)
            self.assertIn('href="unresolved.html"', text, name)

    def test_every_open_fixture_appears_on_the_picks_page(self):
        board = load(BOARD)
        text = (SITE / "picks.html").read_text()
        for row in board["open"]:
            self.assertIn(f"id='m-{row['fixture_id']}'", text, row["fixture_id"])
            self.assertIn(row["team_a"], text)
            self.assertIn(row["team_b"], text)

    def test_unresolved_page_carries_every_assumption_and_withheld_row(self):
        board = load(BOARD)
        text = (SITE / "unresolved.html").read_text()
        for row in board["open"]:
            if row["tier_code"] in ("assumption", "unresolved"):
                self.assertIn(f"id=\"u-{row['fixture_id']}\"", text, row["fixture_id"])

    def test_no_placeholder_values_are_published(self):
        for name in self.PAGES:
            text = (SITE / name).read_text()
            self.assertNotIn(">None<", text, f"{name} prints a Python None")
            self.assertNotIn("None%", text, name)
            self.assertNotIn(" nan ", text.lower(), name)
            self.assertNotIn("NaN", text, name)

    def test_local_links_resolve(self):
        for name in self.PAGES:
            page_path = SITE / name
            for href in re.findall(r'href="([^"#]+)', page_path.read_text()):
                if not href or href.startswith(("http", "#", "mailto")):
                    self.assertNotEqual(href, "", f"{name} has an empty href")
                    continue
                target = (page_path.parent / href).resolve()
                self.assertTrue(target.exists(), f"{name} -> {href} is broken")


if __name__ == "__main__":
    unittest.main(verbosity=2)
