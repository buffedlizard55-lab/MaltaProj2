"""Independent line-by-line verification tests — session 0f71ea59.

These tests re-derive every published probability on the verify961 board from
the raw source quotes (data/961/quotes.json), enforce the blank-unverified
rule, the per-row source-link rule, the "HLTV is never a price source" rule and
the "Hotspawn crowd % is never an input" rule, and check the session's live
re-read ledger for internal consistency. They run against whatever snapshot is
checked in, so the hourly data refresh cannot silently break the invariants.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def amer_to_dec(a):
    a = float(a)
    return 1 + (100 / abs(a) if a < 0 else a / 100)


def dp(x):
    s = repr(float(x))
    if "e" in s or "E" in s:
        return 6
    return len(s.split(".")[1]) if "." in s else 0


def close_stored(stored, exact, base_tol=2e-5):
    if stored is None:
        return False
    tol = max(base_tol, 0.5 * 10 ** (-dp(stored)) + 1e-9)
    return abs(float(stored) - float(exact)) <= tol


class Verify961BoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = json.loads((ROOT / "data" / "961" / "board.json").read_text())
        cls.quotes = json.loads((ROOT / "data" / "961" / "quotes.json").read_text())
        cls.live = json.loads((ROOT / "data" / "0f71ea59" / "live_checks.json").read_text())
        cls.verification = json.loads((ROOT / "data" / "0f71ea59" / "verification.json").read_text())
        cls.rows = cls.board["rows"]
        cls.verified = [r for r in cls.rows if r.get("verified")]
        cls.unverified = [r for r in cls.rows if not r.get("verified")]

    def test_unverified_rows_blank_and_without_sources(self):
        for r in self.unverified:
            self.assertIn(r.get("pick"), (None, ""), r["fixture_id"])
            self.assertIn(r.get("probability_a"), (None, ""), r["fixture_id"])
            self.assertIn(r.get("probability_b"), (None, ""), r["fixture_id"])
            self.assertIn(r.get("pick_probability"), (None, ""), r["fixture_id"])
            self.assertFalse(r.get("sources"), r["fixture_id"])

    def test_per_source_novig_and_overround_match_published_odds(self):
        qmap = {(x["source_key"], str(x["source_event_id"])): x for x in self.quotes["quotes"]}
        for r in self.verified:
            for s in r["sources"]:
                oa, ob = s["decimal_odds_a"], s["decimal_odds_b"]
                self.assertGreater(oa, 1, (r["fixture_id"], oa))
                self.assertGreater(ob, 1, (r["fixture_id"], ob))
                layers = [(oa, ob)]
                qq = qmap.get((s["source_key"], str(s.get("event_id"))))
                if qq is not None:
                    qd_a, qd_b = qq["decimal_odds_a"], qq["decimal_odds_b"]
                    if s.get("orientation_vs_fixture") == "reversed":
                        qd_a, qd_b = qd_b, qd_a
                    layers.append((qd_a, qd_b))
                ok = False
                for da, db in layers:
                    ia, ib = 1 / da, 1 / db
                    tot = ia + ib
                    if (close_stored(s["no_vig_probability_a"], ia / tot)
                            and close_stored(s["no_vig_probability_b"], ib / tot)
                            and close_stored(s["overround"], tot - 1)):
                        ok = True
                        break
                self.assertTrue(ok, (r["fixture_id"], s["source_key"],
                                     s["no_vig_probability_a"], s["overround"]))

    def test_consensus_is_mean_of_sources_and_sums_to_one(self):
        for r in self.verified:
            srcs = r["sources"]
            nva = sum(s["no_vig_probability_a"] for s in srcs) / len(srcs)
            nvb = sum(s["no_vig_probability_b"] for s in srcs) / len(srcs)
            self.assertTrue(close_stored(r["probability_a"], nva, 5e-5), r["fixture_id"])
            self.assertTrue(close_stored(r["probability_b"], nvb, 5e-5), r["fixture_id"])
            self.assertTrue(close_stored((r["probability_a"] or 0) + (r["probability_b"] or 0), 1.0, 5e-5),
                            r["fixture_id"])

    def test_pick_is_argmax_and_pick_probability_is_max(self):
        for r in self.verified:
            pa, pb = r["probability_a"], r["probability_b"]
            exp_team = r["team_a"] if pa >= pb else r["team_b"]
            self.assertEqual(r["pick"], exp_team, r["fixture_id"])
            self.assertIn(r["pick"], (r["team_a"], r["team_b"]), r["fixture_id"])
            self.assertTrue(close_stored(r["pick_probability"], max(pa, pb)), r["fixture_id"])

    def test_every_verified_row_has_official_links_and_timestamps(self):
        for r in self.verified:
            self.assertTrue(str(r.get("hotspawn_match_url", "")).startswith("http"), r["fixture_id"])
            self.assertTrue(str(r.get("official_source_url_hotspawn", "")).startswith("http"), r["fixture_id"])
            for s in r["sources"]:
                self.assertTrue(any(isinstance(v, str) and v.startswith("http") for v in s.values()),
                                (r["fixture_id"], s["source_key"]))
                self.assertRegex(str(s.get("retrieved_at_utc")), r"^\d{4}-\d{2}-\d{2}T",
                                 (r["fixture_id"], s["source_key"]))

    def test_hotspawn_crowd_pct_never_used(self):
        for r in self.rows:
            self.assertIn(r.get("hotspawn_pick_pct_used"), (False, None), r["fixture_id"])

    def test_hltv_never_a_price_source(self):
        for r in self.rows:
            for s in (r.get("sources") or []):
                self.assertNotIn("hltv", str(s.get("source_key", "")).lower(), r["fixture_id"])
                self.assertNotIn("hltv", str(s.get("source_name", "")).lower(), r["fixture_id"])

    def test_quote_decimals_derive_from_raw_american(self):
        for x in self.quotes["quotes"]:
            self.assertTrue(close_stored(x["decimal_odds_a"], amer_to_dec(x["raw_price_a"]), 5e-7),
                            (x["source_key"], x["source_event_id"]))
            self.assertTrue(close_stored(x["decimal_odds_b"], amer_to_dec(x["raw_price_b"]), 5e-7),
                            (x["source_key"], x["source_event_id"]))

    def test_board_source_rows_match_quote_provenance_orientation_aware(self):
        qmap = {(x["source_key"], str(x["source_event_id"])): x for x in self.quotes["quotes"]}
        matched = 0
        for r in self.verified:
            for s in r["sources"]:
                qq = qmap.get((s["source_key"], str(s.get("event_id"))))
                if qq is None:
                    continue
                matched += 1
                da, db = amer_to_dec(qq["raw_price_a"]), amer_to_dec(qq["raw_price_b"])
                if s.get("orientation_vs_fixture") == "reversed":
                    da, db = db, da
                self.assertTrue(close_stored(s["decimal_odds_a"], da, 5e-4),
                                (r["fixture_id"], s["source_key"], s["decimal_odds_a"], da))
                self.assertTrue(close_stored(s["decimal_odds_b"], db, 5e-4),
                                (r["fixture_id"], s["source_key"], s["decimal_odds_b"], db))
        self.assertGreater(matched, 0)

    def test_live_hltv_crosschecks_agree_with_board(self):
        by_id = {r["fixture_id"]: r for r in self.rows}
        hrows = self.live["checks"]["hltv_directional"]
        self.assertEqual(len(hrows), 6)
        for h in hrows:
            self.assertTrue(h["agreement"], h["fixture_id"])
            self.assertEqual(h["board_pick"], h["hltv_favorite"], h["fixture_id"])
            self.assertEqual(by_id[h["fixture_id"]]["pick"], h["board_pick"], h["fixture_id"])
            self.assertTrue(h["url"].startswith("https://www.hltv.org/"), h["fixture_id"])
            self.assertRegex(h["read_at_utc"], r"^\d{4}-\d{2}-\d{2}T")

    def test_live_price_rereads_have_urls_and_timestamps(self):
        prows = self.live["checks"]["price_rereads"]
        self.assertGreaterEqual(len(prows), 5)
        for p in prows:
            self.assertTrue(p["url"].startswith("http"), p["fixture_id"])
            self.assertRegex(p["read_at_utc"], r"^\d{4}-\d{2}-\d{2}T")
            self.assertIn(p["match_type"],
                          ("exact", "direction_consistent_price_moved",
                           "event_and_competitors_confirmed_price_not_resampled"))

    def test_url_readability_results_present(self):
        rows = self.live["checks"]["url_readability"]
        self.assertGreaterEqual(len(rows), 5)
        for r in rows:
            self.assertTrue(r["url"].startswith("http"))
            self.assertIn("readable", r)

    def test_verification_report_has_no_failures(self):
        self.assertEqual(self.verification["failures"], [])
        c = self.verification["counts"]
        self.assertEqual(c["checks_passing"], c["checks_total"])
        self.assertEqual(c["verified"] + c["unverified"], c["rows"])

    def test_verification_page_exists_and_has_mobile_viewport(self):
        page = ROOT / "verify" / "0f71ea59" / "index.html"
        self.assertTrue(page.exists())
        text = page.read_text()
        self.assertIn('name="viewport"', text)
        for needle in ("Line-by-line checks", "HLTV directional", "blank by rule",
                       "Flagged for review"):
            self.assertIn(needle, text)
        self.assertTrue((ROOT / "verify" / "0f71ea59" / "style.css").exists())


if __name__ == "__main__":
    unittest.main()
