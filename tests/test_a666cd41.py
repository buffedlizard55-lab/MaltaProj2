"""Regression tests for the isolated a666cd41 provenance audit.

The checks intentionally use only the committed f7279a54 evidence and temporary output. They
never call a source website, so a source outage cannot turn a blank value into a test failure.
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "scripts/a666cd41/build_audit.py"
SPEC = importlib.util.spec_from_file_location("a666cd41_build_audit", BUILDER_PATH)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: list[str] = []

    def handle_starttag(self, tag, attrs):  # type: ignore[no-untyped-def]
        values = dict(attrs)
        if tag in {"a", "link", "script"} and values.get("href"):
            self.links.append(values["href"])
        if tag == "script" and values.get("src"):
            self.links.append(values["src"])
        if values.get("id"):
            self.ids.append(values["id"])


class AuditMathTests(unittest.TestCase):
    def test_no_vig_rederivation_is_normalized(self) -> None:
        quote = {"raw_format": "decimal", "raw_a": 2.0, "raw_b": 1.769230}
        result = AUDIT.rederive_two_way(quote)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertAlmostEqual(result["prob_a"], 0.46938765, places=7)
        self.assertAlmostEqual(result["prob_a"] + result["prob_b"], 1.0, places=12)
        self.assertGreater(result["overround"], 1.0)

    def test_exact_reordering_is_allowed_but_similar_names_are_not(self) -> None:
        fixture = {"team_a": "Apogee Betclic", "team_b": "Spirit Academy"}
        reordering = {"team_a": "Betclic Apogee", "team_b": "Spirit Academy"}
        self.assertIsNone(AUDIT.ordered_orientation(fixture, reordering))
        self.assertFalse(AUDIT.reordered_orientation(fixture, reordering))

        # This is intentionally the kind of apparent alias we must never infer.
        unrelated = {"team_a": "WBT", "team_b": "Nexus"}
        wrotberry = {"team_a": "Nexus", "team_b": "WROTBERRY"}
        self.assertIsNone(AUDIT.ordered_orientation(wrotberry, unrelated))
        self.assertIsNone(AUDIT.reordered_orientation(wrotberry, unrelated))

    def test_start_time_is_required(self) -> None:
        fixture = {"start_utc": "2026-10-19T09:00:00Z"}
        self.assertEqual(AUDIT.source_time_is_strict(fixture, {"start_utc": None}), (False, None))
        ok, hours = AUDIT.source_time_is_strict(fixture, {"start_utc": "2026-10-19T09:04:59Z"})
        self.assertTrue(ok)
        self.assertLess(hours or 1, 5 / 60)
        self.assertFalse(AUDIT.source_time_is_strict(fixture, {"start_utc": "2026-10-19T09:05:01Z"})[0])


class AuditCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.board = AUDIT.load_json(ROOT / "data/f7279a54/board.json")
        cls.snapshot = AUDIT.load_json(ROOT / "data/f7279a54/snapshot.json")
        cls.report = AUDIT.build_report(
            cls.board,
            cls.snapshot,
            ROOT / "data/f7279a54/board.json",
            ROOT / "data/f7279a54/snapshot.json",
        )

    def test_every_open_fixture_has_exactly_one_audit_row(self) -> None:
        source_ids = {str(row["fixture_id"]) for row in self.board["open"]}
        output_ids = [row["fixture_id"] for row in self.report["fixtures"]]
        self.assertEqual(source_ids, set(output_ids))
        self.assertEqual(len(output_ids), len(set(output_ids)))
        self.assertEqual(self.report["summary"]["open_fixtures"], len(source_ids))
        self.assertEqual(
            self.report["summary"]["published_external_market_picks"] + self.report["summary"]["unresolved_blank"],
            len(source_ids),
        )

    def test_source_board_market_rows_are_independently_rederived(self) -> None:
        source_markets = sum(
            1 for row in self.board["open"] if isinstance(row.get("line"), dict) and row["line"].get("basis") == "market"
        )
        direct = self.report["summary"]["published_direct_market_picks"]
        self.assertEqual(direct, source_markets)
        self.assertEqual(self.report["summary"]["source_board_market_picks"], source_markets)

    def test_published_and_unresolved_rows_obey_blank_policy(self) -> None:
        token_reorder_count = 0
        for fixture in self.report["fixtures"]:
            source = fixture["fixture_source"]
            self.assertTrue(source["url"].startswith("https://"), fixture["fixture_id"])
            if fixture["status"] == "published":
                self.assertIsInstance(fixture["prob_a"], float)
                self.assertIsInstance(fixture["prob_b"], float)
                self.assertAlmostEqual(fixture["prob_a"] + fixture["prob_b"], 1.0, places=12)
                self.assertIn(fixture["pick_team"], {fixture["team_a"], fixture["team_b"]})
                self.assertAlmostEqual(fixture["pick_probability"], max(fixture["prob_a"], fixture["prob_b"]), places=12)
                self.assertTrue(fixture["quotes"])
                for evidence in fixture["quotes"]:
                    self.assertTrue(evidence["source_url"].startswith("https://"))
                    self.assertLessEqual(evidence["start_diff_hours"], 5 / 60)
                    self.assertAlmostEqual(evidence["prob_a_at_source"] + evidence["prob_b_at_source"], 1.0, places=12)
                if "token_order_reordered_join_documented" in fixture["flags"]:
                    token_reorder_count += 1
                    self.assertIn("token-order reordering", fixture["basis"])
            else:
                self.assertIsNone(fixture["prob_a"])
                self.assertIsNone(fixture["prob_b"])
                self.assertIsNone(fixture["pick_team"])
                self.assertIn("no_external_market_line_verified", fixture["flags"])
        self.assertEqual(token_reorder_count, self.report["summary"]["published_exact_token_reorder_picks"])

    def test_fixture_payload_does_not_include_hotspawn_crowd_ownership(self) -> None:
        # Fixture links are expected, but ownership/pick-percentage fields must never reach the audit payload.
        fixture_payload = json.dumps(self.report["fixtures"]).casefold()
        for prohibited in ("picked_percentage", "picked percent", "crowd_ownership", "crowd_pick"):
            self.assertNotIn(prohibited, fixture_payload)

    def test_snapshot_access_failure_is_retained_as_a_limitation(self) -> None:
        hltv = self.report["source_access"].get("hltv_probe")
        self.assertIsNotNone(hltv)
        assert hltv is not None
        self.assertFalse(hltv["ok"])
        self.assertEqual(hltv["status"], 403)


class GeneratedSiteTests(unittest.TestCase):
    def test_generated_pages_have_resolving_local_navigation_and_unique_ids(self) -> None:
        board = AUDIT.load_json(ROOT / "data/f7279a54/board.json")
        snapshot = AUDIT.load_json(ROOT / "data/f7279a54/snapshot.json")
        report = AUDIT.build_report(board, snapshot, ROOT / "data/f7279a54/board.json", ROOT / "data/f7279a54/snapshot.json")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            site = root / "audits/a666cd41"
            AUDIT.render_site(report, site)
            (root / "index.html").write_text("<title>main</title>", encoding="utf-8")
            data_file = root / "data/a666cd41/report.json"
            data_file.parent.mkdir(parents=True)
            data_file.write_text(json.dumps(report), encoding="utf-8")
            pages = sorted(site.glob("*.html"))
            self.assertEqual({page.name for page in pages}, {
                "index.html", "picks.html", "unresolved.html", "evidence.html", "method.html"
            })
            for page in pages:
                parser = LinkCollector()
                parser.feed(page.read_text(encoding="utf-8"))
                self.assertEqual(len(parser.ids), len(set(parser.ids)), f"duplicate IDs in {page.name}")
                for link in parser.links:
                    parsed = urlsplit(link)
                    if parsed.scheme or parsed.netloc or not parsed.path:
                        continue
                    target = (page.parent / unquote(parsed.path)).resolve()
                    self.assertTrue(target.is_file(), f"{page.name} has broken local link {link}")

    def test_generated_pages_cover_the_report_and_expose_source_links(self) -> None:
        report = AUDIT.build_report(
            AUDIT.load_json(ROOT / "data/f7279a54/board.json"),
            AUDIT.load_json(ROOT / "data/f7279a54/snapshot.json"),
            ROOT / "data/f7279a54/board.json",
            ROOT / "data/f7279a54/snapshot.json",
        )
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp) / "audit"
            AUDIT.render_site(report, site)
            evidence = (site / "evidence.html").read_text(encoding="utf-8")
            picks = (site / "picks.html").read_text(encoding="utf-8")
            unresolved = (site / "unresolved.html").read_text(encoding="utf-8")
            for fixture in report["fixtures"]:
                self.assertIn(f'id="fixture-{fixture["fixture_id"]}"', evidence)
                self.assertIn(fixture["fixture_source"]["url"], evidence)
                target = picks if fixture["status"] == "published" else unresolved
                self.assertIn(f'evidence.html#fixture-{fixture["fixture_id"]}', target)
            self.assertIn("crowd-pick ownership is not read or used", (site / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
