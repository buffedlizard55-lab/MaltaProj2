import importlib.util
import json
import math
import re
import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "82a9a0cc"
SITE = ROOT / "hotspawn-live"
sys.path.insert(0, str(ROOT / "scripts" / "82a9a0cc"))
from core import SOURCE_WEIGHTS, market_consensus, quote_probability, vrs_probability  # noqa: E402


class AuditParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.h1 = 0
        self.viewport = None
        self.links = []
        self.cards = 0
        self.sources = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "h1":
            self.h1 += 1
        if tag == "meta" and attrs.get("name") == "viewport":
            self.viewport = attrs.get("content")
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
            if "source-chip" in attrs.get("class", "").split():
                self.sources += 1
        if tag == "article" and "match-card" in attrs.get("class", "").split():
            self.cards += 1


class HotSpawnLiveDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads((DATA / "input.json").read_text())
        cls.board = json.loads((DATA / "board.json").read_text())
        cls.base_rows = {row["fixture_id"]: row for row in cls.source["base"]["open"]}
        cls.rows = {row["fixture_id"]: row for row in cls.board["rows"]}

    def test_inventory_is_complete_and_one_to_one(self):
        self.assertEqual(set(self.base_rows), set(self.rows))
        self.assertEqual(len(self.rows), self.board["summary"]["open"])
        self.assertEqual(len(self.rows), len(set(self.rows)))
        locks = [row["lock_utc"] for row in self.board["rows"]]
        self.assertEqual(locks, sorted(locks))

    def test_summary_accounts_for_every_row(self):
        summary = self.board["summary"]
        with_pick = sum(row.get("line") is not None for row in self.board["rows"])
        self.assertEqual(summary["with_pick"], with_pick)
        self.assertEqual(summary["unresolved"], summary["open"] - with_pick)
        self.assertEqual(summary["featured_market"] + summary["researched_market"] +
                         summary["vrs_pair"] + summary["vrs_robust"] +
                         summary["vrs_floor_scenario"], with_pick)
        for row in self.board["rows"]:
            self.assertTrue(row.get("line") or row.get("resolution", {}).get("reason"))

    def test_authoritative_featured_lines_are_unchanged(self):
        for fixture_id, base in self.base_rows.items():
            if base.get("line"):
                self.assertEqual(self.rows[fixture_id]["line"], base["line"], fixture_id)

    def test_probabilities_are_complements_and_pick_is_argmax(self):
        for row in self.board["rows"]:
            line = row.get("line")
            if not line:
                continue
            self.assertGreater(line["prob_a"], 0, row["fixture_id"])
            self.assertLess(line["prob_a"], 1, row["fixture_id"])
            self.assertAlmostEqual(line["prob_a"] + line["prob_b"], 1, places=4)
            expected_side = "a" if line["prob_a"] >= line["prob_b"] else "b"
            self.assertEqual(line["pick_side"], expected_side)
            self.assertEqual(line["pick_team"], row[f"team_{expected_side}"])
            self.assertAlmostEqual(line["pick_prob"], max(line["prob_a"], line["prob_b"]), places=4)

    def test_alias_market_is_rederived_and_two_source(self):
        rescued = [row for row in self.board["rows"] if (row.get("line") or {}).get("basis") == "researched_market_alias"]
        for row in rescued:
            quotes = row["resolution"]["quotes"]
            self.assertGreaterEqual(len({q["source_key"] for q in quotes}), 2)
            self.assertEqual({q["start_utc"] for q in quotes}, {row["start_utc"]})
            oriented = []
            for quote in quotes:
                p = quote_probability(quote)
                self.assertIsNotNone(p)
                if quote["orientation"] == "reversed":
                    p = 1 - p
                self.assertAlmostEqual(p, quote["prob_fixture_a"], places=10)
                oriented.append(quote)
            self.assertAlmostEqual(row["line"]["prob_a"], market_consensus(oriented), places=4)

    def test_every_vrs_probability_rederives(self):
        k = self.board["method"]["calibration"]["k"]
        for row in self.board["rows"]:
            line, detail = row.get("line") or {}, row["resolution"]
            basis = line.get("basis")
            if basis in {"vrs_model", "vrs_model_roster_resolved"}:
                expected = vrs_probability(detail["team_a_vrs"]["points"], detail["team_b_vrs"]["points"], k)
                self.assertAlmostEqual(line["prob_a"], expected, places=4)
            elif basis == "vrs_ambiguity_robust":
                scenarios = detail["scenarios"]
                self.assertTrue(all(s["prob_a"] > .5 for s in scenarios) or all(s["prob_a"] < .5 for s in scenarios))
                nearest = min(scenarios, key=lambda s: abs(s["prob_a"] - .5))["prob_a"]
                self.assertAlmostEqual(line["prob_a"], nearest, places=4)
                self.assertTrue(line["directional"])
            elif basis == "vrs_floor_scenario":
                rated, floor = detail["rated_candidate"], detail["floor"]
                p_rated = vrs_probability(rated["points"], floor["points"], k)
                expected = p_rated if detail["rated_side"] == "a" else 1 - p_rated
                self.assertAlmostEqual(line["prob_a"], expected, places=4)
                self.assertTrue(line["directional"])

    def test_duplicate_selection_requires_rank_identity_or_robust_range(self):
        for row in self.board["rows"]:
            detail = row["resolution"]
            if detail.get("method") == "vrs_model_roster_resolved":
                self.assertTrue(detail["disambiguation"])
                for item in detail["disambiguation"]:
                    self.assertEqual(item["standing"], item["provider_rank"])
                    self.assertEqual(item["provider"], "bo3.gg")
            if detail.get("method") == "vrs_ambiguity_robust":
                self.assertGreater(len(detail["scenarios"]), 1)

    def test_each_row_has_fixture_and_probability_sources(self):
        allowed = {"play.hotspawn.com", "www.hotspawn.com", "www.pinnacle.com", "www.bovada.lv",
                   "melbet.com", "kalshi.com", "www.kalshi.com", "github.com", "bo3.gg"}
        for row in self.board["rows"]:
            evidence = row["evidence"]
            self.assertTrue(any(item["kind"] == "fixture" for item in evidence), row["fixture_id"])
            if row.get("line"):
                self.assertTrue(any(item["kind"] != "fixture" for item in evidence), row["fixture_id"])
            for item in evidence:
                parsed = urlparse(item["url"])
                self.assertEqual(parsed.scheme, "https")
                self.assertIn(parsed.netloc, allowed)
                self.assertTrue(item.get("observed_utc"))

    def test_latest_official_check_matches_model_snapshot(self):
        check = self.board["method"]["vrs_latest_check"]
        self.assertEqual(check["latest_global_snapshot"], self.board["method"]["vrs_snapshot"])
        self.assertRegex(check["blob_sha"], r"^[0-9a-f]{40}$")
        self.assertEqual(urlparse(check["page_url"]).netloc, "github.com")

    def test_crowd_ownership_fields_are_absent(self):
        forbidden = ("picked_percent", "pick_pct_reference", "crowd_pct", "total_picks")
        for path in (DATA / "input.json", DATA / "board.json", SITE / "data" / "board.json"):
            text = path.read_text().casefold()
            for key in forbidden:
                self.assertNotIn(key, text, f"{key} leaked into {path}")
        self.assertEqual(self.board["inventory"]["hotspawn_probability_policy"],
                         "never use crowd pick ownership as a probability, prior, feature, or tiebreak")


class HotSpawnLiveSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = json.loads((DATA / "board.json").read_text())
        cls.pages = {name: (SITE / name).read_text() for name in
                     ("index.html", "picks.html", "unresolved.html", "sources.html", "method.html", "flagged.html")}

    def test_all_pages_are_mobile_first_and_have_one_h1(self):
        required = {"./", "picks.html", "unresolved.html", "sources.html", "method.html", "flagged.html"}
        for name, text in self.pages.items():
            parser = AuditParser(); parser.feed(text)
            self.assertEqual(parser.h1, 1, name)
            self.assertIn("width=device-width", parser.viewport or "", name)
            self.assertTrue(required.issubset(set(parser.links)), name)
            self.assertNotIn("localhost", text.casefold())

    def test_overview_has_executive_links_and_current_counts(self):
        text = self.pages["index.html"]
        self.assertIn('id="executive-summary"', text)
        self.assertIn(f"{self.board['summary']['with_pick']}/{self.board['summary']['open']} picks resolved", text)
        for target in ("picks.html", "unresolved.html", "sources.html", "method.html", "flagged.html"):
            self.assertIn(f'href="{target}"', text)
        self.assertIn("No crowd signal", text)

    def test_full_picks_page_has_one_card_per_row_and_source_links(self):
        parser = AuditParser(); parser.feed(self.pages["picks.html"])
        self.assertEqual(parser.cards, self.board["summary"]["open"])
        self.assertGreaterEqual(parser.sources, self.board["summary"]["open"] * 2)
        for row in self.board["rows"]:
            self.assertIn(f'id="match-{row["fixture_id"]}"', self.pages["picks.html"])
            if row.get("line"):
                self.assertIn(html_escape(row["line"]["pick_team"]), self.pages["picks.html"])

    def test_unresolved_page_surfaces_blank_policy_and_each_featured_gap(self):
        text = self.pages["unresolved.html"]
        self.assertIn("Unresolved picks &amp; limitations", text)
        self.assertIn("Unsupported future rows stay blank", text)
        gaps = [row for row in self.board["rows"] if not row["base_featured_line"]]
        for row in gaps:
            self.assertIn(f'id="match-{row["fixture_id"]}"', text)

    def test_source_ledger_has_every_fixture_and_links(self):
        text = self.pages["sources.html"]
        for row in self.board["rows"]:
            self.assertIn(str(row["fixture_id"]), text)
        self.assertGreaterEqual(text.count("<tr>"), self.board["summary"]["open"] + 6)

    def test_machine_board_is_exact_copy(self):
        self.assertEqual((SITE / "data" / "board.json").read_bytes(), (DATA / "board.json").read_bytes())

    def test_builder_is_reproducible(self):
        before = {path.relative_to(SITE): path.read_bytes() for path in SITE.rglob("*") if path.is_file()}
        subprocess.run([sys.executable, "scripts/82a9a0cc/build.py"], cwd=ROOT, check=True, capture_output=True)
        after = {path.relative_to(SITE): path.read_bytes() for path in SITE.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_scheduled_workflow_targets_four_hours(self):
        workflow = (ROOT / ".github" / "workflows" / "hotspawn-live-82a9a0cc.yml").read_text()
        self.assertRegex(workflow, r"cron:\s*['\"]17 \*/4 \* \* \*['\"]")
        for script in ("check_valve.py", "capture.py", "resolve.py", "build.py"):
            self.assertIn(script, workflow)
        self.assertIn("tests/test_82a9a0cc.py", workflow)


def html_escape(value):
    import html
    return html.escape(str(value), quote=True)


if __name__ == "__main__":
    unittest.main()
