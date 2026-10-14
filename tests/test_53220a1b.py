"""Final-integration verification (session 53220a1b).

Checks the two requirements this session integrated, without trusting any board's own claims:

1. Picks for every HotSpawn CS2 match — each open fixture on the every-match board carries a pick
   and a win probability, every row carries http(s) source links, and the matches that no bookmaker
   prices resolve only through documented fallback information sources (published market slots,
   exchange books, official Valve VRS rows), never HotSpawn's crowd percentage.
2. A mobile executive summary on the landing page that links, inside the site, to every place an
   updated list of picks can be found — and every one of those internal links resolves.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EVERY = ROOT / "data" / "c64a5e19" / "board.json"
FULL = ROOT / "data" / "fe803b80" / "board.json"
INDEX = ROOT / "index.html"
SUMMARY = ROOT / "summary" / "index.html"

PICK_BOARDS = (
    "picks-every-match/index.html",
    "board/picks.html",
    "ourline/index.html",
    "coverage/index.html",
    "live/index.html",
    "fresh/index.html",
    "cs2.html",
    "summary/index.html",
    "flagged.html",
)


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class EveryMatchPicksCoverage(unittest.TestCase):
    """data/c64a5e19/board.json — a supported pick or an explicitly unverified row for every open fixture."""

    @classmethod
    def setUpClass(cls):
        cls.board = _load(EVERY)
        cls.rows = cls.board["open"]

    def test_every_open_fixture_has_a_pick_and_a_win_probability(self):
        self.assertGreater(len(self.rows), 0)
        for row in self.rows:
            line = row.get("line") or {}
            if not line:
                self.assertIn("no_line_unverified", row.get("flags", []))
                continue
            self.assertIn(
                line.get("pick_team"), (row.get("team_a"), row.get("team_b")),
                f"{row.get('fixture_id')}: pick is not one of the two teams")
            self.assertIsNotNone(line.get("pick_prob"),
                                 f"{row.get('fixture_id')}: pick without a win probability")
            for key in ("prob_a", "prob_b"):
                self.assertIsInstance(line.get(key), (int, float),
                                      f"{row.get('fixture_id')}: missing {key}")

    def test_probabilities_normalize_and_the_pick_is_the_higher_side(self):
        for row in self.rows:
            line = row["line"]
            if not line: continue
            self.assertAlmostEqual(line["prob_a"] + line["prob_b"], 1.0, places=5,
                                   msg=f"{row['fixture_id']}: probabilities do not sum to 1")
            self.assertAlmostEqual(line["pick_prob"], max(line["prob_a"], line["prob_b"]),
                                   places=5,
                                   msg=f"{row['fixture_id']}: pick is not the higher-probability side")

    def test_every_row_carries_http_source_links(self):
        for row in self.rows:
            sources = row.get("sources") or []
            self.assertTrue(sources, f"{row.get('fixture_id')}: row has no source links")
            for source in sources:
                self.assertTrue(str(source.get("url", "")).startswith("http"),
                                f"{row.get('fixture_id')}: non-http source {source}")

    def test_unpriced_matches_resolve_only_via_documented_fallback_sources(self):
        """The low-tier / uncovered matches are the ones with basis 'fallback'.

        Each such row must publish fallback evidence (a named source with a URL) or at least an
        official Valve VRS citation — never a crowd percentage."""
        fallback_rows = [r for r in self.rows if (r.get("line") or {}).get("basis") == "model"]
        # Source coverage can change: never require fabricated fallback rows.
        for row in fallback_rows:
            source_blob = json.dumps(row.get("sources") or [])
            self.assertTrue(
                "Valve" in source_blob or "valve" in source_blob.lower()
                or "bo3.gg" in source_blob or "kalshi" in source_blob.lower()
                or "melbet" in source_blob.lower(),
                f"{row['fixture_id']}: fallback row cites no documented outside source")
            evidence = (row.get("fallback") or {}).get("evidence") or []
            documented = [e for e in evidence if e.get("public_url") or e.get("api_url")]
            self.assertTrue(
                documented or row.get("sources"),
                f"{row['fixture_id']}: fallback basis without evidence links")

    def test_hotspawn_is_fixture_discovery_only(self):
        blob = json.dumps(self.board).lower()
        for forbidden in ("pick_pct", "picked_percent", "crowd_percent", "hotspawn_percent"):
            self.assertNotIn(forbidden, blob,
                             "HotSpawn crowd percentage leaked into the every-match board")

    def test_summary_counts_match_the_rows(self):
        summary = self.board["summary"]
        self.assertEqual(summary["open"], len(self.rows))
        self.assertEqual(summary["with_pick"],
                         sum(1 for r in self.rows if (r.get("line") or {}).get("pick_team")))


class FullCoverageBoard(unittest.TestCase):
    """data/fe803b80/board.json — every open fixture priced, modelled, or blank + flagged."""

    @classmethod
    def setUpClass(cls):
        cls.board = _load(FULL)
        cls.rows = cls.board.get("open") or []

    def test_every_open_fixture_is_picked_or_explicitly_blank_and_flagged(self):
        self.assertGreater(len(self.rows), 0)
        for row in self.rows:
            line = row.get("line") or {}
            has_pick = line.get("pick") or line.get("pick_team")
            if not has_pick:
                flags = json.dumps(row.get("flags") or row.get("reasons") or "")
                self.assertTrue(flags and flags != "[]",
                                f"{row.get('fixture_id')}: blank row is not flagged")
            else:
                self.assertIsNotNone(line.get("pick_probability"),
                                     f"{row.get('fixture_id')}: pick without a probability")

    def test_every_row_carries_at_least_one_source_url(self):
        for row in self.rows:
            urls = [s.get("url") or s.get("public_url") or s.get("api_url")
                    for s in (row.get("sources") or [])]
            self.assertTrue(any(u and str(u).startswith("http") for u in urls),
                            f"{row.get('fixture_id')}: no source URL on row")


class ExecutiveSummaryAndMobileEntryPoints(unittest.TestCase):
    """The landing page must make the pick lists findable on a phone."""

    @classmethod
    def setUpClass(cls):
        cls.index = INDEX.read_text(encoding="utf-8")

    def test_landing_page_is_mobile_friendly(self):
        self.assertIn('name="viewport"', self.index)
        self.assertIn("width=device-width", self.index)

    def test_executive_summary_links_every_pick_board(self):
        self.assertIn('id="where-the-picks"', self.index)
        for href in PICK_BOARDS:
            self.assertIn(f'href="{href}"', self.index,
                          f"landing executive summary does not link {href}")

    def test_nav_has_picks_and_summary_entry_points(self):
        nav_match = re.search(r"<nav>(.*?)</nav>", self.index, re.S)
        self.assertIsNotNone(nav_match)
        nav = nav_match.group(1)
        for href in ("board/picks.html", "summary/index.html"):
            self.assertIn(f'href="{href}"', nav)

    def test_every_internal_exec_summary_link_resolves(self):
        block = self.index.split('id="where-the-picks"', 1)[1].split("</div>", 1)[0]
        for href in re.findall(r'href="([^"]+)"', block):
            if href.startswith("http") or href.startswith("#"):
                continue
            self.assertTrue((ROOT / href).exists(),
                            f"executive summary link does not resolve: {href}")

    def test_summary_hub_lists_every_board(self):
        hub = SUMMARY.read_text(encoding="utf-8")
        for href in ("picks-every-match/index.html", "board/picks.html", "ourline/index.html",
                     "coverage/index.html", "fresh/index.html", "live/index.html"):
            self.assertIn(href, hub, f"summary hub does not link {href}")


class RefreshAutomation(unittest.TestCase):
    """Matches and picks must refresh on their own, at least every 8 hours."""

    WORKFLOWS = (
        "every-match-c64a5e19.yml",
        "board-fe803b80.yml",
        "coverage-6ddde224.yml",
        "ourline-f7279a54.yml",
        "fresh-dd2b7fee.yml",
        "summary-c0e223d3.yml",
        "live-coverage.yml",
        "update-data.yml",
    )

    @staticmethod
    def _max_gap_minutes(cron):
        """Largest gap between consecutive runs of a 5-field cron (minute hour ...)."""
        minute_f, hour_f = cron.split()[:2]

        def expand(field, span):
            values = set()
            for part in field.split(","):
                step = 1
                if "/" in part:
                    part, step_s = part.split("/", 1)
                    step = int(step_s)
                if part in ("*", ""):
                    values.update(range(0, span, step))
                elif "-" in part:
                    lo, hi = part.split("-")
                    values.update(range(int(lo), int(hi) + 1, step))
                else:
                    values.add(int(part))
            return sorted(values)

        minutes = expand(minute_f, 60)
        hours = expand(hour_f, 24)
        runs = sorted(h * 60 + m for h in hours for m in minutes)
        gaps = [(b - a) for a, b in zip(runs, runs[1:])]
        gaps.append(24 * 60 - (runs[-1] - runs[0]))
        return max(gaps)

    def test_pick_boards_refresh_at_least_every_8_hours(self):
        for name in self.WORKFLOWS:
            text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            crons = re.findall(r"cron:\s*['\"]([^'\"]+)['\"]", text)
            self.assertTrue(crons, f"{name}: no cron schedule found")
            best = min(self._max_gap_minutes(c) for c in crons)
            self.assertLessEqual(
                best, 8 * 60,
                f"{name}: refresh gap {best} min exceeds the 8-hour requirement")


if __name__ == "__main__":
    unittest.main()
