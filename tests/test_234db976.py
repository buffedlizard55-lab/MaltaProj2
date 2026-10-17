"""Checks for the source-linked TWC 2026 Day-5 research pages."""
from __future__ import annotations

import importlib.util
import math
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
BUILD_PATH = ROOT / "scripts" / "234db976" / "build.py"
SPEC = importlib.util.spec_from_file_location("twc_day5_234db976_build", BUILD_PATH)
assert SPEC and SPEC.loader
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class EvidenceRows(HTMLParser):
    """Collect rows deliberately marked as evidence-bearing in generated tables."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, object]] = []
        self.current: dict[str, object] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "tr" and attrs_dict.get("data-evidence-row"):
            self.current = {"kind": attrs_dict["data-evidence-row"], "links": []}
        elif tag == "a" and self.current is not None:
            href = attrs_dict.get("href") or ""
            if href.startswith("https://"):
                links = self.current["links"]
                assert isinstance(links, list)
                links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self.current is not None:
            self.rows.append(self.current)
            self.current = None


class Day5ResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = build.load_data()
        cls.pages = build.render_pages(cls.data)

    def test_two_way_market_math_and_quote_snapshot(self) -> None:
        aurora, final = self.data["matches"]
        a = build.market_probabilities(aurora)
        f = build.market_probabilities(final)
        self.assertAlmostEqual(a["no_vig"]["Aurora"], 0.34469, places=4)
        self.assertAlmostEqual(a["no_vig"]["Falcons"], 0.65531, places=4)
        self.assertAlmostEqual(a["overround_pct_points"], 7.4509, places=3)
        self.assertAlmostEqual(f["no_vig"]["FURIA"], 0.68241, places=4)
        self.assertAlmostEqual(f["no_vig"]["BETBOOM"], 0.31759, places=4)
        self.assertAlmostEqual(f["overround_pct_points"], 8.576, places=3)
        self.assertEqual(self.data["market_capture"]["checked_utc"], "2026-10-17T20:38Z")
        self.assertEqual(final["market_source_labels"]["BETBOOM"], "BB Team")
        self.assertIn("label discrepancy", final["market_label_note"])
        for match in self.data["matches"]:
            self.assertTrue(match["market_url"].startswith("https://thunderpick.io/"))

    def test_thunderpick_final_label_mismatch_is_explicit_and_sourced(self) -> None:
        day5 = next(content for path, content in self.pages.items() if path.name == "day-5.html")
        unresolved = next(content for path, content in self.pages.items() if path.name == "day-5-unresolved.html")
        self.assertIn("BETBOOM (Thunderpick: BB Team)", day5)
        self.assertIn("FURIA −286 / BB Team +190", unresolved)
        self.assertIn("Thunderpick final team label", unresolved)
        self.assertIn("hltv.org/matches/2399417", unresolved)
        self.assertIn("furia-vs-bb-team/2843592", unresolved)

    def test_decimal_returns_and_picks_are_consistent(self) -> None:
        self.assertAlmostEqual(build.american_to_decimal("+170"), 2.70)
        self.assertAlmostEqual(build.american_to_decimal("-238"), 1.4201680672)
        self.assertAlmostEqual(build.american_to_decimal("-286"), 1.3496503497)
        self.assertAlmostEqual(build.american_to_decimal("+190"), 2.90)
        for match in self.data["matches"]:
            p = build.market_probabilities(match)["no_vig"]
            self.assertEqual(match["primary_pick"], max(p, key=p.get))
            self.assertEqual(match["underdog_option"], min(p, key=p.get))
            self.assertAlmostEqual(sum(p.values()), 1.0)

    def test_vrs_secondary_crosscheck_matches_documented_model(self) -> None:
        vrs = self.data["vrs_crosscheck"]
        aurora = build.vrs_probability(1716, 1843, vrs["used_k"])
        furia = build.vrs_probability(1829, 1596, vrs["used_k"])
        self.assertAlmostEqual(aurora, 0.4556667, places=5)
        self.assertAlmostEqual(furia, 0.5808346, places=5)
        self.assertEqual(vrs["calibration_market_pairs"], 10)
        self.assertLess(vrs["raw_k"], vrs["used_k"])
        self.assertEqual(vrs["snapshot_date"], "2026-10-05")

    def test_all_12_historical_rows_include_official_blast_and_secondary_detail(self) -> None:
        history = self.data["history_days_1_to_4"]
        self.assertEqual(len(history), 12)
        self.assertEqual({day: sum(row["day"] == day for row in history) for day in range(1, 5)}, {1: 4, 2: 4, 3: 2, 4: 2})
        for row in history:
            self.assertIn("blast.tv/cs/tournaments/thunderpick-world-championship-2026/match/", row["blast_url"])
            self.assertIn("hotspawn.com/matches/", row["hotspawn_url"])
            self.assertIn("hltv.org/matches/", row["hltv_url"])
        page = next(content for path, content in self.pages.items() if path.name == "day-5.html")
        parser = EvidenceRows()
        parser.feed(page)
        rows = [row for row in parser.rows if row["kind"] == "history"]
        self.assertEqual(len(rows), 12)
        for row in rows:
            links = row["links"]
            self.assertTrue(any("blast.tv/" in url for url in links))
            self.assertTrue(any("hltv.org/matches/" in url for url in links))
            self.assertTrue(any("hotspawn.com/matches/" in url for url in links))

    def test_kickoffs_are_blank_and_conflicts_are_separate(self) -> None:
        self.assertTrue(all(match["kickoff_utc"] is None for match in self.data["matches"]))
        unresolved = next(content for path, content in self.pages.items() if path.name == "day-5-unresolved.html")
        for required in ("07:30", "11:00", "11:30", "15:00", "13:30", "17:00", "timezone", "BO3", "BO5"):
            self.assertIn(required, unresolved)
        parser = EvidenceRows()
        parser.feed(unresolved)
        schedules = [row for row in parser.rows if row["kind"] == "schedule"]
        self.assertGreaterEqual(len(schedules), 8)
        for row in schedules:
            self.assertTrue(row["links"], f"Schedule row has no source: {row}")

    def test_each_evidence_table_row_has_an_https_source(self) -> None:
        categories: set[str] = set()
        official_hosts = ("blast.tv", "thunderpick.io", "hotspawn.com", "github.com", "x.com")
        for content in self.pages.values():
            parser = EvidenceRows()
            parser.feed(content)
            for row in parser.rows:
                kind = str(row["kind"])
                categories.add(kind)
                links = row["links"]
                self.assertTrue(links, f"Evidence row has no direct HTTPS source: {row}")
                self.assertTrue(all(url.startswith("https://") for url in links))
                hosts = [urlsplit(url).hostname or "" for url in links]
                self.assertTrue(
                    any(any(host == official or host.endswith("." + official) for official in official_hosts) for host in hosts),
                    f"Evidence row has no official organizer/bookmaker/partner/VRS source: {row}",
                )
        self.assertTrue({"market", "vrs", "roster", "history", "schedule", "limitation"}.issubset(categories))

    def test_hotspawn_map_side_irregularity_is_flagged_on_unresolved_page(self) -> None:
        unresolved = next(content for path, content in self.pages.items() if path.name == "day-5-unresolved.html")
        self.assertIn("HotSpawn map-score rendering for FURIA series", unresolved)
        self.assertIn("appear reversed", unresolved)
        for match_id in ("1081614", "1080207"):
            self.assertIn(match_id, unresolved)
        self.assertIn("43d44ef6/legacy-furia", unresolved)
        self.assertIn("f1057d27/aurora-furia", unresolved)

    def test_hotspawn_full_coverage_is_read_only_and_not_a_probability_source(self) -> None:
        coverage = self.data["hotspawn_coverage"]
        self.assertEqual(coverage["canonical_full_coverage_board_path"], "../picks-every-match/index.html")
        self.assertEqual(coverage["canonical_unresolved_board_path"], "../picks-every-match/unresolved.html")
        self.assertIn("crowd", coverage["role"].lower())
        for match in self.data["matches"]:
            self.assertTrue(match["market_url"].startswith("https://thunderpick.io/"))
            self.assertNotIn("crowd", " ".join(match["sources"][0].keys()).lower())
        unresolved = next(content for path, content in self.pages.items() if path.name == "day-5-unresolved.html")
        self.assertIn("../picks-every-match/index.html", unresolved)
        self.assertIn("../picks-every-match/unresolved.html", unresolved)
        self.assertIn("crowd", unresolved.lower())
        self.assertNotIn("data-live", unresolved)

    def test_existing_twc_index_has_an_additive_day5_route(self) -> None:
        index = (ROOT / "twc-2026" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="day-5.html"', index)
        self.assertIn("Day-5 picks", index)

    def test_generated_pages_are_current_and_mobile_accessible(self) -> None:
        for path, content in self.pages.items():
            self.assertEqual(path.read_text(encoding="utf-8"), content, f"Run build.py; {path.name} is stale")
            self.assertIn('name="viewport"', content)
            self.assertIn('href="assets.css"', content)
            self.assertIn('class="skip"', content)
            self.assertIn('aria-label="Main navigation"', content)
        day5 = next(content for path, content in self.pages.items() if path.name == "day-5.html")
        self.assertIn("not a live feed", day5.lower())
        self.assertIn("approximate minute", day5.lower())


if __name__ == "__main__":
    unittest.main()
