"""Independent current-snapshot audit for the canonical every-match board.

This suite intentionally reads committed source data rather than trusting generated summary counts.
It is safe across later inventories: fixture-specific identity checks run only while those fixtures
remain open, while collector/source-quality invariants apply to every refresh.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "data" / "c64a5e19" / "snapshot.json"
BOARD = ROOT / "data" / "c64a5e19" / "board.json"
MAX_EXCHANGE_SPREAD = 0.10


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class CurrentInventoryAndRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = load(SNAP)
        cls.board = load(BOARD)
        cls.rows = {r["fixture_id"]: r for r in cls.board["open"]}

    def test_generated_board_is_same_committed_snapshot(self):
        self.assertEqual(self.board["generated_utc"], self.snapshot["collected_to_utc"])
        self.assertEqual(self.board["snapshot_session"], self.snapshot["session"])

    def test_open_inventory_is_derived_without_using_board_summary(self):
        now = dt(self.snapshot["collected_to_utc"])
        expected = {
            str(raw["fixture_id"])
            for raw in self.snapshot["hotspawn"]["fixtures"]
            if raw.get("status") == "scheduled"
            and dt(raw.get("lock_utc") or raw["start_utc"]) > now
        }
        self.assertEqual(set(self.rows), expected)

    def test_every_row_has_pick_pair_or_explicit_blank_and_flag(self):
        for row in self.rows.values():
            line = row.get("line")
            if line is None:
                self.assertTrue(row.get("flags"), row["fixture_id"])
                self.assertIn("no_line_unverified", row["flags"])
                continue
            self.assertIn(line["pick_team"], (row["team_a"], row["team_b"]))
            self.assertAlmostEqual(line["prob_a"] + line["prob_b"], 1.0, places=3)
            self.assertEqual(line["pick_prob"], max(line["prob_a"], line["prob_b"]))

    def test_every_row_has_non_hotspawn_evidence_source(self):
        for row in self.rows.values():
            sources = row.get("sources") or []
            self.assertTrue(sources, row["fixture_id"])
            for source in sources:
                self.assertTrue(str(source.get("url", "")).startswith("https://"), source)
            self.assertTrue(any(not str(s.get("label", "")).startswith("HotSpawn") for s in sources),
                            f"{row['fixture_id']} has discovery link only")

    def test_fallback_lines_are_inside_their_published_evidence_range(self):
        for row in self.rows.values():
            if (row.get("line") or {}).get("tier") != "C":
                continue
            fallback = row.get("fallback") or {}
            self.assertTrue(fallback.get("evidence"), row["fixture_id"])
            lo, hi = fallback["prob_a_range"]
            self.assertLessEqual(lo, row["line"]["prob_a"] + 1e-4)
            self.assertGreaterEqual(hi, row["line"]["prob_a"] - 1e-4)
            self.assertTrue(row["flags"], row["fixture_id"])

    def test_forze_lfo_uses_direct_market_and_exact_roster_not_siblings(self):
        row = self.rows.get("1079624")
        if not row:
            self.skipTest("fixture 1079624 is no longer open")
        evidence = (row.get("fallback") or {}).get("evidence") or []
        kinds = {e.get("kind") for e in evidence}
        self.assertTrue(kinds & {"exact_roster_market_price", "wide_exchange_exact_roster_price"})
        self.assertIn("exact_roster_identity", kinds)
        self.assertNotIn("originated_sibling_vrs_range", kinds)
        market = [e for e in evidence if e.get("kind") in {"exact_roster_market_price", "wide_exchange_exact_roster_price"}]
        self.assertTrue(any("Polymarket" in e.get("source", "") for e in market))
        self.assertIn("fallback_exact_roster_identity_name_unconfirmed", row["flags"])
        source_blob = json.dumps(row["sources"], ensure_ascii=False)
        for required in ("HLTV", "Liquipedia", "Polymarket"):
            self.assertIn(required, source_blob)

    def test_wrotberry_rows_keep_wbt_and_academy_conflicts_visible(self):
        target_rows = [r for r in self.rows.values() if "WROTBERRY" in (r["team_a"], r["team_b"])]
        if not target_rows:
            self.skipTest("WROTBERRY fixtures are no longer open")
        for row in target_rows:
            evidence = (row.get("fallback") or {}).get("evidence") or []
            source_names = [name for e in evidence for name in (e.get("names_at_source") or [])]
            self.assertTrue(any(name in {"WBT", "WhiteBIT Team"} for name in source_names), row["fixture_id"])
            self.assertTrue(any("Polymarket" in e.get("source", "") for e in evidence), row["fixture_id"])
            academy = [e for e in evidence if "WBT Academy" in (e.get("names_at_source") or [])]
            for conflict in academy:
                self.assertEqual(conflict.get("kind"), "identity_conflict_price_not_used")
                self.assertNotIn("prob_team_a", conflict)
                self.assertNotIn("prob_team_a_normalised_mid", conflict)
            self.assertIn("fallback_slot_price_source_calls_team_wbt_not_wrotberry", row["flags"])


class PolymarketDiscoveryAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = load(SNAP)

    def test_numeric_match_tag_collection_succeeded(self):
        access = self.snapshot.get("access_log", {}).get("polymarket") or {}
        self.assertEqual(access.get("tag_id"), 100780)
        self.assertEqual(access.get("status"), 200)
        self.assertIsInstance(access.get("market_rows"), int)
        self.assertIsInstance(access.get("match_winner_candidates"), int)
        self.assertFalse(access.get("truncated"))
        self.assertIn("tag_id=100780", access.get("url", ""))
        self.assertNotIn("tag_slug=counter-strike", access.get("url", ""))

    def test_tight_quotes_and_wide_books_are_separated(self):
        accepted = [q for q in self.snapshot.get("quotes", []) if q.get("source_key") == "polymarket"]
        rejected = [r for r in self.snapshot.get("rejected_quotes", []) if r.get("source_key") == "polymarket"]
        access = self.snapshot.get("access_log", {}).get("polymarket") or {}
        self.assertEqual(len(accepted) + len(rejected), access.get("match_winner_candidates"))
        for quote in accepted:
            self.assertLessEqual(quote["bid_ask_spread"], MAX_EXCHANGE_SPREAD)
            self.assertRegex(quote["public_url"], r"^https://polymarket\.com/event/cs2-")
            self.assertEqual(len({quote["team_a"], quote["team_b"]}), 2)
        for item in rejected:
            quote = item.get("quote") or {}
            spread = quote.get("bid_ask_spread")
            self.assertTrue(spread is None or spread > MAX_EXCHANGE_SPREAD)
            self.assertIn("fallback-only", item.get("reason", ""))

    def test_polymarket_probability_rederives_from_raw_contract_prices(self):
        records = [q for q in self.snapshot.get("quotes", []) if q.get("source_key") == "polymarket"]
        records += [r["quote"] for r in self.snapshot.get("rejected_quotes", [])
                    if r.get("source_key") == "polymarket" and isinstance(r.get("quote"), dict)]
        for quote in records:
            a, b = float(quote["raw_a"]), float(quote["raw_b"])
            self.assertGreater(a, 0); self.assertGreater(b, 0)
            self.assertAlmostEqual(quote["prob_a"], a / (a + b), places=6)
            self.assertAlmostEqual(float(quote["decimal_a"]), 1 / a, places=3)


class PublishedMethodAndAutomation(unittest.TestCase):
    def test_generated_method_corrects_old_false_no_coverage_claim(self):
        method = (ROOT / "picks-every-match" / "method.html").read_text(encoding="utf-8")
        self.assertIn("numeric Counter-Strike match tag", method)
        self.assertIn("100780", method)
        self.assertIn("LFO 10 / Sökerorg exact-roster line", method)
        self.assertNotIn("no open CS2 match markets have been observed", method)

    def test_mobile_summary_surfaces_unresolved_limitations(self):
        page = (ROOT / "picks-every-match" / "index.html").read_text(encoding="utf-8")
        self.assertIn('name="viewport"', page)
        self.assertIn("Unresolved / provisional identity limitations", page)
        self.assertIn('href="flagged.html"', page)
        source = (ROOT / "scripts" / "build_site.py").read_text(encoding="utf-8")
        self.assertIn("Unresolved / provisional limitations", source)
        self.assertIn("Polymarket", source)

    def test_half_hour_workflow_has_no_sleeping_self_dispatch_job(self):
        workflow = (ROOT / ".github" / "workflows" / "every-match-c64a5e19.yml").read_text(encoding="utf-8")
        self.assertRegex(workflow, r"cron:\s*['\"]12,42 \* \* \* \*['\"]")
        self.assertNotIn("sleep 1500", workflow)
        self.assertNotRegex(workflow, r"(?m)^\s+next:\s*$")
        self.assertIn("tests.test_57e26db7", workflow)


if __name__ == "__main__":
    unittest.main()
