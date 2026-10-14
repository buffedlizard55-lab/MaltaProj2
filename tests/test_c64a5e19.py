"""Every-match board tests (session c64a5e19).

All tests are offline. They rebuild the committed c64 snapshot rather than an older session's
snapshot, independently derive the currently-open fixture IDs, and exercise the Polymarket parser
with captured-shape records so discovery/filter regressions cannot masquerade as "no coverage".
"""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "scripts" / "c64a5e19"
SNAPSHOT = ROOT / "data" / "c64a5e19" / "snapshot.json"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Keep this session's generic module names from shadowing shared scripts/build.py in discovery.
sys.path.insert(0, str(HERE))
try:
    core = _load("c64a5e19_core", HERE / "core.py")
    B = _load("c64a5e19_build", HERE / "build.py")
    C = _load("c64a5e19_collect", HERE / "collect.py")
finally:
    sys.path.remove(str(HERE))
    sys.modules.pop("build", None)
    sys.modules.pop("collect", None)
    sys.modules.pop("core", None)


def snapshot():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def board():
    return B.build_board(snapshot(), "test-current-c64-snapshot")


def _dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class TestEveryMatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap = snapshot()
        cls.b = board()

    def test_board_inventory_equals_independently_filtered_snapshot(self):
        now = _dt(self.snap["collected_to_utc"])
        expected = {
            str(f["fixture_id"])
            for f in self.snap["hotspawn"]["fixtures"]
            if f.get("status") == "scheduled"
            and _dt(f.get("lock_utc") or f["start_utc"]) > now
        }
        actual = {r["fixture_id"] for r in self.b["open"]}
        self.assertEqual(actual, expected)
        self.assertEqual(self.b["summary"]["open"], len(expected))

    def test_every_open_fixture_has_a_pick(self):
        self.assertEqual(self.b["summary"]["with_pick"], self.b["summary"]["open"])
        self.assertEqual(self.b["summary"]["tier_d_none"], 0)
        for row in self.b["open"]:
            self.assertIsNotNone(row["line"], row["fixture_id"])

    def test_probabilities_sum_to_one_and_pick_is_higher(self):
        for row in self.b["open"]:
            line = row["line"]
            self.assertAlmostEqual(line["prob_a"] + line["prob_b"], 1.0, places=3)
            self.assertEqual(line["pick_prob"], max(line["prob_a"], line["prob_b"]))
            self.assertIn(line["pick_team"], (row["team_a"], row["team_b"]))

    def test_fallback_only_when_no_accepted_market_or_model_pair(self):
        for row in self.b["open"]:
            if row["line"]["tier"] == "C":
                self.assertIsNone(row["market"], row["fixture_id"])
                self.assertIsNone(row["model"], row["fixture_id"])
                self.assertTrue((row.get("fallback") or {}).get("evidence"), row["fixture_id"])
            if row["market"]:
                self.assertEqual(row["line"]["tier"], "A")

    def test_fallback_evidence_is_linked_and_conflicts_are_not_numeric(self):
        for row in self.b["open"]:
            for evidence in (row.get("fallback") or {}).get("evidence") or []:
                self.assertTrue(str(evidence.get("public_url", "")).startswith("https://"),
                                (row["fixture_id"], evidence))
                if evidence.get("kind") == "identity_conflict_price_not_used":
                    self.assertNotIn("prob_team_a", evidence)
                    self.assertNotIn("prob_team_a_normalised_mid", evidence)

    def test_wbt_academy_is_never_averaged_into_wrotberry(self):
        for row in self.b["open"]:
            if "WROTBERRY" not in (row["team_a"], row["team_b"]):
                continue
            evidence = (row.get("fallback") or {}).get("evidence") or []
            academy = [e for e in evidence if "WBT Academy" in (e.get("names_at_source") or [])]
            self.assertTrue(academy, row["fixture_id"])
            for item in academy:
                self.assertEqual(item["kind"], "identity_conflict_price_not_used")
                self.assertNotIn("prob_team_a", item)

    def test_every_row_has_source_link(self):
        for row in self.b["open"]:
            self.assertTrue(row["sources"])
            for source in row["sources"]:
                self.assertTrue(str(source["url"]).startswith("https://"))

    def test_no_hotspawn_crowd_in_board(self):
        blob = json.dumps(self.b).lower()
        for forbidden in ("pick_pct", "picked_percent", "crowd_percent", "hotspawn_percent"):
            self.assertNotIn(forbidden, blob)

    def test_alias_evidence(self):
        self.assertEqual(core.canon("RoundsGG")[0], "rounds")
        self.assertEqual(core.canon("EA Copenhagen")[0], "eac")
        self.assertNotEqual(core.canon("B8")[0], core.canon("B8 Academy")[0])
        # LFO 10/Sökerorg is intentionally not a global alias.
        self.assertNotEqual(core.canon("LFO 10")[0], core.canon("Sökerorg")[0])

    def test_thin_mid_and_ticker_time(self):
        self.assertAlmostEqual(B.thin_mid({"yes_bid_dollars": "0.40", "yes_ask_dollars": "0.60"}), 0.5)
        self.assertIsNotNone(B.kalshi_start_from_ticker("KXCS2GAME-26OCT150400EACWBTACADEMY"))

    def test_rendered_pages_exist_and_link_board(self):
        for name in ("index.html", "picks.html", "flagged.html", "method.html"):
            text = (ROOT / "picks-every-match" / name).read_text(encoding="utf-8")
            self.assertIn("Every-match picks", text)
            self.assertIn('name="viewport"', text)
        index = (ROOT / "picks-every-match" / "index.html").read_text(encoding="utf-8")
        for href in ("picks.html", "flagged.html", "method.html", "../index.html", "../ourline/index.html"):
            self.assertIn(f'href="{href}"', index)


class TestPolymarketParser(unittest.TestCase):
    @staticmethod
    def market(spread=0.04, market_type="moneyline", title="Match Winner"):
        return {
            "id": "5637276",
            "question": "Counter-Strike: FORZE Reload vs Sökerorg (BO3) - CCT Europe Series #11 Group Stage",
            "slug": "cs2-forzer-skr2-2026-10-14",
            "outcomes": '["FORZE Reload", "Sökerorg"]',
            "outcomePrices": '["0.855", "0.145"]',
            "active": True,
            "closed": False,
            "acceptingOrders": True,
            "groupItemTitle": title,
            "gameStartTime": "2026-10-14 17:00:00+00",
            "sportsMarketType": market_type,
            "spread": spread,
            "bestBid": 0.84,
            "bestAsk": 0.87,
            "volumeNum": 373.86314,
            "liquidityNum": 5169.6266,
            "updatedAt": "2026-10-14T04:31:29Z",
            "events": [{
                "slug": "cs2-forzer-skr2-2026-10-14",
                "title": "Counter-Strike: FORZE Reload vs Sökerorg (BO3) - CCT Europe Series #11 Group Stage",
                "live": False,
            }],
        }

    def test_tight_full_match_moneyline_is_accepted(self):
        quote, reason = C.polymarket_quote(self.market())
        self.assertIsNone(reason)
        self.assertEqual(quote["source_key"], "polymarket")
        self.assertEqual(quote["team_a"], "FORZE Reload")
        self.assertAlmostEqual(quote["prob_a"], 0.855)
        self.assertEqual(quote["bid_ask_spread"], 0.04)
        self.assertIn("/event/cs2-forzer-skr2-2026-10-14", quote["public_url"])

    def test_wide_book_is_retained_but_rejected_from_featured(self):
        quote, reason = C.polymarket_quote(self.market(spread=0.38))
        self.assertIsNotNone(quote)
        self.assertIn("fallback-only", reason)

    def test_map_or_non_winner_market_is_filtered(self):
        for changed in (
            self.market(market_type="child_moneyline", title="Map 1 Winner"),
            self.market(market_type="moneyline", title="Map 1 Winner"),
        ):
            quote, reason = C.polymarket_quote(changed)
            self.assertIsNone(quote)
            self.assertIsNone(reason)

    def test_discovery_uses_numeric_match_tag_not_counter_strike_slug(self):
        source = (HERE / "collect.py").read_text(encoding="utf-8")
        self.assertIn("POLY_MATCH_TAG_ID = 100780", source)
        self.assertNotIn('"tag_slug":', source)


if __name__ == "__main__":
    unittest.main()
