"""Contract tests for session f28afd9e (every-match safe + leaderboard picks, day-1 review)."""
import json
import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "f28afd9e"))
import strategy  # noqa: E402

BOARD = ROOT / "data" / "f28afd9e" / "board.json"
DAY1 = ROOT / "data" / "f28afd9e" / "day1_review.json"
CONTEXT = ROOT / "data" / "f28afd9e" / "context.json"
SITE = ROOT / "strategy"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self.viewport = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
        if tag == "meta" and a.get("name") == "viewport":
            self.viewport = True


class StrategyRules(unittest.TestCase):
    def test_no_probability_gives_no_pick(self):
        r = strategy.evaluate("A", "B", None, (0.5, 0.5), 2)
        self.assertIsNone(r["safe_pick"])
        self.assertIsNone(r["leaderboard_pick"])

    def test_safe_pick_is_the_higher_probability(self):
        for p in (0.51, 0.7, 0.3, 0.49):
            r = strategy.evaluate("A", "B", p, None, 2)
            self.assertEqual(r["safe_pick"], "A" if p >= 0.5 else "B")
            self.assertEqual(r["leaderboard_pick"], r["safe_pick"])  # no ownership -> no fade

    def test_coinflip_fade(self):
        r = strategy.evaluate("A", "B", 0.53, (0.9, 0.1), 3)
        self.assertEqual((r["leaderboard_pick"], r["rule"]), ("B", "R1_coinflip_fade"))

    def test_never_fades_a_dead_underdog(self):
        r = strategy.evaluate("A", "B", 0.85, (0.97, 0.03), 7, {"A": [{"type": "roster_change", "date": "2026-10-01"}]},
                              "2026-10-15")
        self.assertEqual(r["leaderboard_pick"], "A")

    def test_upset_swing_needs_low_ownership(self):
        self.assertEqual(strategy.evaluate("A", "B", 0.62, (0.9, 0.1), 3)["rule"], "R2_upset_swing")
        self.assertEqual(strategy.evaluate("A", "B", 0.62, (0.6, 0.4), 3)["leaderboard_pick"], "A")

    def test_context_swing_requires_verified_recent_context(self):
        ctx = {"A": [{"type": "roster_change", "date": "2026-07-08"}]}
        self.assertEqual(strategy.evaluate("A", "B", 0.70, (0.96, 0.04), 7, ctx, "2026-10-14")["rule"],
                         "R3_context_swing")
        old = {"A": [{"type": "roster_change", "date": "2026-01-01"}]}
        self.assertEqual(strategy.evaluate("A", "B", 0.70, (0.96, 0.04), 7, old, "2026-10-14")["rule"], "chalk")
        secondary = {"A": [{"type": "roster_change", "date": "2026-10-01", "secondary": True}]}
        self.assertEqual(strategy.evaluate("A", "B", 0.70, (0.96, 0.04), 7, secondary, "2026-10-14")["rule"], "chalk")

    def test_daily_cap(self):
        rows = [{"start_utc": "2026-10-15T1%d:00:00Z" % i, "points": 2,
                 "strategy": strategy.evaluate("A", "B", 0.6, (0.92, 0.08), 2)} for i in range(5)]
        strategy.apply_daily_cap(rows)
        swings = [r for r in rows if r["strategy"]["rule"] == "R2_upset_swing"]
        self.assertEqual(len(swings), strategy.MAX_SWINGS_PER_DAY)

    def test_ownership_normalises(self):
        a, b = strategy.ownership(13, 88)
        self.assertAlmostEqual(a + b, 1.0)
        self.assertIsNone(strategy.ownership(None, 50))


class PublishedBoard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = json.loads(BOARD.read_text(encoding="utf-8"))
        cls.rows = cls.board["rows"]

    def test_every_open_row_has_pick_or_documented_blank(self):
        for r in self.rows:
            if r["state"] != "open":
                continue
            s = r["strategy"]
            if r["prob_a"] is None:
                self.assertEqual(r["basis"], "unresolved")
                self.assertIn("no_line_from_any_board", r["flags"])
                self.assertIsNone(s["safe_pick"])
            else:
                self.assertAlmostEqual(r["prob_a"] + r["prob_b"], 1.0, places=9)
                self.assertEqual(s["safe_pick"], r["team_a"] if r["prob_a"] >= 0.5 else r["team_b"])
                self.assertIn(s["leaderboard_pick"], (r["team_a"], r["team_b"]))

    def test_every_priced_row_cites_an_external_source(self):
        for r in self.rows:
            self.assertTrue(r["hotspawn_url"].startswith("https://"))
            if r["prob_a"] is not None:
                urls = [s["url"] for s in (r["line"] or {}).get("sources") or []]
                self.assertTrue(any(u.startswith("https://") and "hotspawn" not in u for u in urls), r["fixture_id"])

    def test_probability_never_comes_from_crowd(self):
        for r in self.rows:
            line = r.get("line") or {}
            self.assertIn(line.get("board"), (None, "fe803b80", "c64a5e19", "b1fb1465", "7177d07f"))
            if r["prob_a"] is not None:
                self.assertAlmostEqual(r["prob_a"], line["prob_a"], places=12)

    def test_contrarian_pick_only_on_live_underdogs(self):
        for r in self.rows:
            s = r["strategy"]
            if s["leaderboard_pick"] and s["leaderboard_pick"] != s["safe_pick"]:
                self.assertGreaterEqual(s["leaderboard_prob"], strategy.CONTEXT_MIN_P)
                self.assertIn(s["rule"], ("R1_coinflip_fade", "R2_upset_swing", "R3_context_swing"))

    def test_summary_counts(self):
        open_rows = [r for r in self.rows if r["state"] == "open"]
        sm = self.board["summary"]
        self.assertEqual(sm["listed_open"], len(open_rows))
        self.assertEqual(sm["with_pick"] + sm["unresolved"], len(open_rows))


class Day1Review(unittest.TestCase):
    def test_review_rows_reproduce(self):
        doc = json.loads(DAY1.read_text(encoding="utf-8"))
        settled = [r for r in doc["rows"] if r["winner"]]
        self.assertEqual(doc["summary"]["settled"], len(settled))
        self.assertEqual(doc["summary"]["safe_correct"], sum(1 for r in settled if r["safe_correct"]))
        nine_z = next(r for r in doc["rows"] if r["fixture_id"] == "1080176")
        self.assertEqual(nine_z["winner"], "9z")
        self.assertEqual(nine_z["strategy"]["safe_pick"], "Aurora")
        self.assertTrue(re.fullmatch(r"[0-9a-f]{40}", nine_z["crowd"]["commit"]))

    def test_context_entries_are_sourced(self):
        ctx = json.loads(CONTEXT.read_text(encoding="utf-8"))
        for team, entries in ctx["teams"].items():
            for e in entries:
                self.assertTrue(e["sources"], team)
                self.assertTrue(all(u.startswith("https://") for u in e["sources"]))


class Pages(unittest.TestCase):
    def test_pages_are_mobile_and_links_resolve(self):
        for name in ("index.html", "unresolved.html", "day1.html", "method.html"):
            text = (SITE / name).read_text(encoding="utf-8")
            p = Links()
            p.feed(text)
            self.assertTrue(p.viewport, name)
            for href in p.hrefs:
                if href.startswith(("http://", "https://", "#")):
                    continue
                target = (SITE / href.split("#")[0]).resolve()
                if href.startswith("../"):
                    if not target.exists():
                        # generated root sections are present in the staged artifact
                        self.assertTrue((ROOT / href[3:].split("#")[0]).exists(), (name, href))
                else:
                    self.assertTrue(target.exists(), (name, href))

    def test_every_open_match_has_a_card(self):
        board = json.loads(BOARD.read_text(encoding="utf-8"))
        text = (SITE / "index.html").read_text(encoding="utf-8")
        for r in board["rows"]:
            self.assertIn(f'id="m-{r["fixture_id"]}"', text)

    def test_workflow_cadence_within_four_to_eight_hours(self):
        wf = (ROOT / ".github" / "workflows" / "strategy-f28afd9e.yml").read_text(encoding="utf-8")
        self.assertRegex(wf, r"cron: '\d+ \*/4 \* \* \*'")


if __name__ == "__main__":
    unittest.main()
