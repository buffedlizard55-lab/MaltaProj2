#!/usr/bin/env python3
"""Contract tests for the additive 1b35a4a2 landing-page integration.

The imported audit remains a dated, secondary research view. These tests keep
its evidence basis and known source-link caveats visible without changing its
owned data or replacing the stricter canonical board.
"""
from __future__ import annotations

import json
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
FLAGGED = ROOT / "flagged.html"
README = ROOT / "README.md"
AUDIT_DATA = ROOT / "data" / "1b35a4a2" / "board.json"
DAY4_DATA = ROOT / "data" / "1c8f79f8" / "board.json"


def stamp(value: str | None) -> str:
    return (value or "unverified").replace("T", " ").replace("Z", " UTC")


class Hrefs(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.values.extend(value for key, value in attrs if key == "href" and value)


class LandingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = INDEX.read_text()
        cls.flagged = FLAGGED.read_text()
        cls.readme = README.read_text()
        cls.audit = json.loads(AUDIT_DATA.read_text())
        cls.day4 = json.loads(DAY4_DATA.read_text())

    def test_canonical_all_picks_remains_the_primary_action(self):
        self.assertIn('class="btn btn-primary" href="picks-every-match/index.html"', self.index)
        actions = self.index.split('<div class="actions primary-actions">', 1)[1].split("</div>", 1)[0]
        self.assertLess(
            actions.index('href="picks-every-match/index.html"'),
            actions.index('href="day4/index.html"'),
        )
        self.assertNotIn('class="btn btn-primary" href="audits/1b35a4a2/index.html"', self.index)

    def test_research_audit_is_secondary_and_basis_labeled(self):
        summary = self.audit["summary"]
        counts = (
            f"{summary['market_based']} market, {summary['research_resolved']} "
            f"research-resolved and {summary['model_only']} Valve-VRS model estimates"
        )
        self.assertIn('href="audits/1b35a4a2/index.html"', self.index)
        self.assertIn('href="audits/1b35a4a2/picks.html"', self.index)
        self.assertIn('href="audits/1b35a4a2/unresolved.html"', self.index)
        self.assertIn('href="audits/1b35a4a2/flagged.html"', self.index)
        self.assertIn('href="audits/1b35a4a2/method.html"', self.index)
        self.assertIn(counts, self.index)
        self.assertIn(
            f"{summary['with_line']} lines for {summary['open']} open fixtures",
            self.index,
        )
        self.assertIn(stamp(self.audit["canonical_snapshot_utc"]), self.index)
        self.assertIn(stamp(self.audit["generated_utc"]), self.index)
        self.assertIn("not bookmaker prices or verified win chances", self.index)
        self.assertIn("HotSpawn crowd shares are not probabilities", self.index)

    def test_day4_copy_counts_blank_probabilities_and_separates_timestamps(self):
        rows = self.day4.get("open") or []
        summary = self.day4.get("summary") or {}
        open_count = summary.get("open", len(rows))
        with_probability = sum(
            1 for row in rows
            if (row.get("line") or {}).get("prob_a") is not None
            and (row.get("line") or {}).get("prob_b") is not None
        )
        without_probability = max(0, open_count - with_probability)
        self.assertIn(
            f"{with_probability} of {open_count} open lobby fixtures with a market/model probability",
            self.index,
        )
        self.assertIn(f"{without_probability} remain blank and flagged", self.index)
        self.assertIn(stamp(self.day4["snapshot_utc"]), self.index)
        self.assertIn(stamp(self.day4["generated_utc"]), self.index)
        self.assertNotIn("a pick and probability for every open HotSpawn fixture", self.index)

    def test_source_link_mismatches_are_visible_with_fixture_and_citation_links(self):
        self.assertIn('id="audit-1b35-source-mismatch"', self.flagged)
        self.assertIn("#1079170", self.flagged)
        self.assertIn("#1081126", self.flagged)
        self.assertIn("Betclic vs Team Nemesis", self.flagged)
        self.assertIn("NODWIN Clutch Series 13", self.flagged)
        self.assertIn("CCT Europe 2026 Series #12 Play-In", self.flagged)
        self.assertIn("66% research estimate", self.flagged)
        self.assertIn("55% value is an unpriced research estimate", self.flagged)
        for url in (
            "https://www.hotspawn.com/matches/bet-m-vs-just-players-nodwin-clutch-series-13-1079170",
            "https://egamersworld.com/counterstrike/match/4JaFCnn5Ve/betclic-vs-team-nemesis-6LGr94GGb",
            "https://www.hotspawn.com/matches/banda-chuya-vs-enjoy-cct-europe-2026-series-12-play-in-1081126",
            "https://www.hltv.org/events/9440/nodwin-clutch-series-13",
        ):
            self.assertIn(url, self.flagged)
        self.assertIn('href="flagged.html#audit-1b35-source-mismatch"', self.index)
        self.assertIn("initial input snapshot <code>2026-10-16T22:48:43Z</code>", self.flagged)
        review_table = self.flagged.split('id="audit-1b35-source-review"', 1)[1].split("</table>", 1)[0]
        self.assertEqual(review_table.count('<td data-label='), 6, "two mismatch rows need three aligned cells each")
        self.assertIn(
            '<td data-label="Fixture and cited source links"><a href="https://www.hotspawn.com/matches/bet-m-vs-just-players-nodwin-clutch-series-13-1079170"',
            review_table,
        )

    def test_readme_audit_ledger_entry_discloses_snapshot_and_routes(self):
        for text in (
            "audits/1b35a4a2/index.html",
            "audits/1b35a4a2/picks.html",
            "audits/1b35a4a2/unresolved.html",
            "audits/1b35a4a2/flagged.html",
            "audits/1b35a4a2/method.html",
            "2026-10-16T22:48:43Z",
            "2026-10-16T23:57:03Z",
            ".github/workflows/audit-1b35a4a2.yml",
            "every 4 hours",
            "flagged.html#audit-1b35-source-mismatch",
        ):
            self.assertIn(text, self.readme)

    def test_new_landing_destinations_exist(self):
        parser = Hrefs()
        parser.feed(self.index)
        required = {
            "audits/1b35a4a2/index.html",
            "audits/1b35a4a2/picks.html",
            "audits/1b35a4a2/unresolved.html",
            "audits/1b35a4a2/flagged.html",
            "audits/1b35a4a2/method.html",
        }
        self.assertTrue(required.issubset(set(parser.values)))
        for href in required:
            self.assertTrue((ROOT / unquote(urlsplit(href).path)).is_file(), href)
        self.assertTrue((ROOT / "flagged.html").is_file())


if __name__ == "__main__":
    unittest.main()
