from __future__ import annotations

from decimal import Decimal
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "94ab4483" / "review.json"
AUDIT_DIR = ROOT / "audits" / "94ab4483"


class AuditHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.viewport = False
        self.main_id = False
        self.h1_count = 0
        self.in_tbody = False
        self.in_row = False
        self.row_has_external_source = False
        self.table_rows: list[bool] = []
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "meta" and attrs_dict.get("name", "").lower() == "viewport":
            self.viewport = True
        if tag == "main" and attrs_dict.get("id") == "main":
            self.main_id = True
        if tag == "h1":
            self.h1_count += 1
        if attrs_dict.get("id"):
            self.ids.add(attrs_dict["id"])
        if tag == "tbody":
            self.in_tbody = True
        if tag == "tr" and self.in_tbody:
            self.in_row = True
            self.row_has_external_source = False
        if tag == "a" and attrs_dict.get("href"):
            href = attrs_dict["href"]
            self.links.append(href)
            if self.in_row and href.startswith("https://"):
                self.row_has_external_source = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self.in_row:
            self.table_rows.append(self.row_has_external_source)
            self.in_row = False
        if tag == "tbody":
            self.in_tbody = False


def read_data() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


class TestDayFourAudit(unittest.TestCase):
    def test_market_prices_rederive_to_a_tie_without_hotspawn_input(self) -> None:
        data = read_data()
        market = data["market_evidence"]
        self.assertIsNone(market["crowd_ownership"])
        self.assertEqual(market["directional_summary"], {"FURIA": 0.5, "Aurora": 0.5})
        self.assertIsNone(data["strategy"]["published_pick"])
        for quote in market["observations"]:
            raw_a = Decimal(1) / Decimal(str(quote["decimal_a"]))
            raw_b = Decimal(1) / Decimal(str(quote["decimal_b"]))
            fair_a = raw_a / (raw_a + raw_b)
            fair_b = raw_b / (raw_a + raw_b)
            overround = raw_a + raw_b - Decimal(1)
            self.assertAlmostEqual(float(fair_a), quote["no_vig_a"], places=6)
            self.assertAlmostEqual(float(fair_b), quote["no_vig_b"], places=6)
            self.assertAlmostEqual(float(overround), quote["overround"], places=6)
            source = data["sources"][quote["source_url_key"]]
            self.assertTrue(source["url"].startswith("https://"))
            self.assertNotIn("hotspawn", source["url"].lower())
            snapshot = data["sources"][quote["source_snapshot_key"]]
            self.assertIn("/data/fe803b80/board.json", snapshot["url"])
            self.assertTrue(snapshot["url"].startswith("https://github.com/"))

    def test_all_result_rows_have_sources_and_expected_day_counts(self) -> None:
        data = read_data()
        self.assertEqual(len(data["results"]), 9)
        self.assertEqual(sum(item["day"] == 1 for item in data["results"]), 4)
        self.assertEqual(sum(item["day"] == 2 for item in data["results"]), 4)
        self.assertEqual(sum(item["day"] == 3 for item in data["results"]), 1)
        self.assertEqual(data["results"][0]["map_scores"], ["Inferno 13-11", "Nuke 13-1"])
        for item in data["results"]:
            self.assertTrue(item["sources"], item)
            for key in item["sources"]:
                self.assertTrue(data["sources"][key]["url"].startswith("https://"))

    def test_placeholder_and_live_decider_values_stay_blank(self) -> None:
        data = read_data()
        second = next(item for item in data["day4_fixtures"] if item["fixture_id"] == "1080208")
        self.assertIsNone(second["resolved_pairing"])
        self.assertIsNone(second["probability"])
        self.assertIsNone(second["pick"])
        self.assertEqual(data["live_match"]["series_score_observed"], "1-1")
        self.assertIsNone(data["live_match"]["result"])
        self.assertEqual(data["strategy"]["published_probability"], None)

    def test_pickem_lobby_state_change_keeps_semifinal_membership_unverified(self) -> None:
        data = read_data()
        lobby = data["coverage_observations"]["pickem_lobby"]
        previous = lobby["previous_same_day_observation"]
        self.assertFalse(lobby["main_twc_filter_visible"])
        self.assertFalse(lobby["twc_match_rows_visible"])
        self.assertTrue(previous["main_twc_filter_visible"])
        self.assertFalse(previous["twc_match_rows_visible"])
        self.assertFalse(lobby["ownership_visible"])
        self.assertTrue(all(fixture["pickem_membership"] == "unverified" for fixture in data["day4_fixtures"]))

    def test_snapshot_gap_is_rederived_and_capture_policies_are_distinct(self) -> None:
        data = read_data()["board_freshness"]
        canonical = data["canonical"]["capture_utc"].replace("Z", "+00:00")
        independent = data["independent"]["capture_utc"].replace("Z", "+00:00")
        from datetime import datetime
        delta = int((datetime.fromisoformat(independent) - datetime.fromisoformat(canonical)).total_seconds())
        self.assertEqual(delta, data["capture_gap_seconds"])
        self.assertNotEqual(data["canonical"]["policy"], data["independent"]["policy"])
        self.assertEqual(delta, -(9 * 60 + 51))

    def test_generated_pages_are_mobile_accessible_source_linked_and_resolve_local_links(self) -> None:
        pages = ["index.html", "unresolved.html", "flagged.html", "method.html"]
        for name in pages:
            path = AUDIT_DIR / name
            self.assertTrue(path.exists(), name)
            parser = AuditHTMLParser()
            parser.feed(path.read_text(encoding="utf-8"))
            self.assertTrue(parser.viewport, name)
            self.assertTrue(parser.main_id, name)
            self.assertEqual(parser.h1_count, 1, name)
            self.assertTrue(parser.table_rows, name)
            self.assertTrue(all(parser.table_rows), f"table row without external source in {name}")
            for href in parser.links:
                if href.startswith(("https://", "http://", "mailto:", "#")):
                    continue
                target = href.split("#", 1)[0]
                if not target:
                    continue
                local = (path.parent / target).resolve()
                self.assertTrue(local.exists(), f"{name}: missing local target {href}")
        unresolved = AuditHTMLParser()
        unresolved.feed((AUDIT_DIR / "unresolved.html").read_text(encoding="utf-8"))
        self.assertIn("second-semi", unresolved.ids)

    def test_css_supports_small_screens_and_reduced_motion(self) -> None:
        css = (AUDIT_DIR / "style.css").read_text(encoding="utf-8")
        self.assertIn("@media(max-width:700px)", css)
        self.assertIn("@media(prefers-reduced-motion:reduce)", css)
        self.assertIn("scroll-behavior:auto", css)
        self.assertIn("td::before", css)

    def test_report_records_source_boundaries(self) -> None:
        report = json.loads((AUDIT_DIR / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["result_rows"], 9)
        self.assertEqual(report["day4_semifinal_slots"], 2)
        self.assertEqual(report["unresolved_fixture_ids"], ["1080208"])
        self.assertFalse(report["hotspawn_ownership_used_as_probability"])
        self.assertEqual(len(report["market_quotes_rederived"]), 2)

    def test_builder_is_reproducible(self) -> None:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "94ab4483" / "build.py")], check=True, cwd=ROOT, capture_output=True, text=True)
        report = json.loads((AUDIT_DIR / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "published with explicit unresolved/flagged values")


if __name__ == "__main__":
    unittest.main()
