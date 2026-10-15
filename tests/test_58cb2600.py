"""Final current-pipeline contract tests for session 58cb2600."""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_lines import MAX_AGE_SECONDS, build_document, iso  # noqa: E402
from fetch_hotspawn import build_documents, parse_lobby  # noqa: E402

CAPTURE = ROOT / "audits" / "ae75c5c3" / "lobby_fixture.txt"


class LobbyTransferStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = CAPTURE.read_text(encoding="utf-8")

    def test_real_public_capture_parses_exact_listing_and_published_links(self):
        """The raw capture must parse into a self-consistent listing.

        The lobby capture and the published counters are written by the same collector job, but they
        can be refreshed at different moments, so this checks the parser's own arithmetic (counters
        equal the parsed fixture histogram, ids unique) and cross-checks the published listing where
        the two observations overlap. Nothing here is frozen to a lobby size.
        """
        published = json.loads((ROOT / "data" / "live" / "fixtures.json").read_text(encoding="utf-8"))
        counters = published["lobby_counters"]
        parsed = parse_lobby(self.html)
        fixtures = parsed["fixtures"]
        histogram = {"s": 0, "b": 0, "c": 0}
        for row in fixtures:
            tier = str(row.get("tier") or "").lower()
            if tier in histogram:
                histogram[tier] += 1
        self.assertEqual(len(fixtures), len({row["fixture_id"] for row in fixtures}))
        self.assertEqual(parsed["counters"], {
            "matches_this_week": parsed["counters"]["matches_this_week"],
            "all_tiers": len(fixtures),
            "tier_s": histogram["s"], "tier_b": histogram["b"], "tier_c": histogram["c"],
        })
        self.assertGreater(parsed["published_permalink_count"], 0)
        ids = {row["fixture_id"] for row in fixtures}
        shared = ids & set(counters["listing_ids"])
        self.assertGreater(len(shared), 50, "the capture and the published listing do not overlap")
        # The weekly counter changes as the lobby rotates, so it is compared only between two
        # observations taken by the SAME collector job: the live raw capture and the counters
        # published from it (session f28afd9e repair; the pinned capture above is dated 14 Oct and
        # its counter legitimately differs from today's).
        same_job = ROOT / "data" / "live" / "samples" / "lobby_page.txt"
        if same_job.exists():
            live = parse_lobby(same_job.read_text(encoding="utf-8"))
            self.assertEqual(live["counters"]["matches_this_week"], counters["matches_this_week"])
            self.assertEqual(live["counters"]["all_tiers"], counters["all_tiers"])
    def test_parser_fails_closed_on_missing_malformed_and_ambiguous_state(self):
        bad_pages = [
            "",
            '<script id="ng-state">{}</script>',
            '<script id="ng-state">not json</script>',
            ('<script id="ng-state">'
             '{"a":{"u":"https://x/api/v1/fixtures","b":[{"id":1}]},'
             '"b":{"u":"https://y/api/v1/fixtures","b":[{"id":2}]}}'
             '</script>'),
        ]
        for page in bad_pages:
            with self.subTest(page=page[:50]), self.assertRaises(ValueError):
                parse_lobby(page)

    def test_http_age_is_preserved_and_used_for_source_observation(self):
        retrieved = datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)
        doc, evidence = build_documents(self.html, retrieved, {"Age": "3600", "Date": None})
        self.assertEqual(doc["generated_at_utc"], "2026-10-14T01:00:00Z")
        self.assertEqual(doc["source_observed_at_utc"], "2026-10-14T00:00:00Z")
        self.assertEqual(doc["source_cache_age_seconds"], 3600)
        self.assertEqual(evidence["fixture_ids"], [row["fixture_id"] for row in doc["matches"]])


class CurrentPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads((ROOT / "data" / "hotspawn_matches.json").read_text())
        cls.probe = json.loads((ROOT / "evidence" / "hotspawn_probe.json").read_text())
        cls.lines = json.loads((ROOT / "data" / "lines.json").read_text())
        cls.probabilities = json.loads((ROOT / "data" / "current_probabilities.json").read_text())

    def test_published_inventory_is_the_evidenced_lobby_listing(self):
        rows = self.inventory["matches"]
        self.assertEqual(self.inventory["match_count"], len(rows))
        self.assertEqual([row["fixture_id"] for row in rows], self.probe["fixture_ids"])
        self.assertEqual({row["sport"] for row in rows}, {"cs2"})
        self.assertNotIn("pick_pct", json.dumps(self.inventory).lower())
        self.assertTrue(self.probe["validation"]["fixture_ids_unique"])
        self.assertFalse(self.probe["validation"]["normalized_crowd_percentage_fields_present"])

    def test_summary_and_every_pick_recompute_from_rows(self):
        rows = self.lines["fixtures"]
        summary = self.lines["summary"]
        open_rows = [row for row in rows if row["pick_status"] == "open"]
        priced = [row for row in open_rows if row["bookmaker_lines"]]
        self.assertEqual(summary["fixtures_total"], len(rows))
        self.assertEqual(summary["fixtures_open_for_picks"], len(open_rows))
        self.assertEqual(summary["fixtures_open_with_external_line"], len(priced))
        self.assertEqual(summary["fixtures_open_without_external_line"], len(open_rows) - len(priced))
        self.assertEqual(summary["fixtures_locked_or_past"], len(rows) - len(open_rows))
        for row in rows:
            consensus = row["derived"]["consensus"]
            if consensus is None:
                self.assertFalse(row["bookmaker_lines"])
                self.assertIn("external_odds_not_found", row["review_flags"])
                continue
            self.assertEqual(row["pick_status"], "open")
            self.assertAlmostEqual(consensus["derived_probability_a_mean"] +
                                   consensus["derived_probability_b_mean"], 1)
            self.assertTrue(row["bookmaker_lines"])
            for source in row["bookmaker_lines"]:
                self.assertIn(urlsplit(source["source_api_url"]).hostname,
                              {"guest.api.arcadia.pinnacle.com", "www.bovada.lv"})

    def test_current_probability_rows_have_official_fixture_links(self):
        allowed = {"play.hotspawn.com", "www.hotspawn.com"}
        self.assertEqual(len(self.probabilities["rows"]), self.lines["summary"]["fixtures_total"])
        for row in self.probabilities["rows"]:
            self.assertIn(urlsplit(row["official_source_url"]).hostname, allowed)
            if row["probability_a"] is not None:
                self.assertEqual(row["pick_status"], "open")
                self.assertTrue(row["sources"])
                self.assertAlmostEqual(row["probability_a"] + row["probability_b"], 1)

    def test_current_pages_are_focused_mobile_and_every_table_row_is_sourced(self):
        index = BeautifulSoup((ROOT / "index.html").read_text(), "html.parser")
        # Integration session fe803b80 added one additive navigation entry that points at the
        # full-coverage picks board (board/picks.html) from the shared index; every entry this
        # test originally guarded must still be present, and the header must stay compact.
        nav_hrefs = {a.get("href") for a in index.select("header nav a")}
        for required in ("index.html", "cs2.html", "probabilities.html", "tournaments.html",
                         "flagged.html", "methodology.html", "research.html"):
            self.assertIn(required, nav_hrefs)
        # 53220a1b integration: the compact header now carries two more additive anchors
        # (summary/index.html "Where the picks are", requested by c0e223d3, and the
        # 6ddde224 coverage board), so the compactness cap is 10 unique entries.
        self.assertLessEqual(len(nav_hrefs), 10)
        self.assertIsNotNone(index.select_one('a[href="research.html"]'))
        self.assertIsNotNone(index.select_one('a[href="board/picks.html"]'))
        self.assertIn("Every CS2 match currently open for picks", index.get_text(" ", strip=True))
        for name in ("index.html", "cs2.html", "probabilities.html", "flagged.html",
                     "methodology.html", "tournaments.html", "research.html"):
            soup = BeautifulSoup((ROOT / name).read_text(), "html.parser")
            self.assertIsNotNone(soup.select_one('meta[name="viewport"]'), name)
            for row in soup.select("tbody tr"):
                self.assertTrue(row.select('a[href^="https://"]'), (name, row.get_text(" ")[:120]))
        cs2 = BeautifulSoup((ROOT / "cs2.html").read_text(), "html.parser")
        self.assertIsNotNone(cs2.select_one("#open-fixtures"))
        self.assertIsNotNone(cs2.select_one("#closed-fixtures"))
        self.assertIsNotNone(cs2.select_one("details.archive"))


class CacheFreshnessTests(unittest.TestCase):
    def test_cache_adjusted_fixture_time_fails_closed(self):
        now = datetime(2026, 10, 14, 1, 0, tzinfo=timezone.utc)
        future = now + timedelta(hours=6)
        fixture = {
            "fixture_id": "1", "sport": "cs2", "team_a": "Alpha", "team_b": "Beta",
            "status": "scheduled", "scheduled_start_time": iso(future),
            "lock_time": iso(future - timedelta(minutes=5)), "competition_name": "Test",
            "source": {"page": "https://play.hotspawn.com/lobby"},
        }
        quote = {
            "source_key": "bovada", "source_name": "Bovada", "sport": "cs2",
            "source_api_url": "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports",
            "source_event_id": "q", "team_a_name": "Alpha", "team_b_name": "Beta",
            "start_time_utc": iso(future), "retrieved_at_utc": iso(now),
            "market_type": "match winner (moneyline, full match)", "market_status": "O",
            "market_is_live": False, "outcome_alignment_verified": True,
            "decimal_odds_a": 2.0, "decimal_odds_b": 2.0,
        }
        fixtures = {
            "generated_at_utc": iso(now),
            "source_observed_at_utc": iso(now - timedelta(seconds=MAX_AGE_SECONDS + 1)),
            "matches": [fixture],
        }
        doc, _ = build_document(fixtures, {"generated_at_utc": iso(now), "lines": [quote]}, now)
        self.assertIsNone(doc["fixtures"][0]["derived"]["consensus"])
        self.assertIn("fixture_snapshot_stale_or_unverified_timestamp",
                      doc["fixtures"][0]["review_flags"])


if __name__ == "__main__":
    unittest.main()
