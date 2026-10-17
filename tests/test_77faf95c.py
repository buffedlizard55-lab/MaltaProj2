"""Contract tests for session 77faf95c (HQ board).

These run against whatever is committed under ``data/77faf95c/``, so they pass before a first
capture and tighten once one exists. Nothing here reaches the network.
"""
import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "77faf95c"
RAW = DATA / "raw"
SCRIPTS = ROOT / "scripts" / "77faf95c"
HQ = ROOT / "hq"


def _load(rel, default=None):
    p = DATA / rel
    if not p.exists():
        return default
    if p.suffix == ".md":
        return p.read_text(encoding="utf-8")
    return json.loads(p.read_text(encoding="utf-8"))


class TestScripts(unittest.TestCase):
    def test_collect_and_build_exist(self):
        self.assertTrue((SCRIPTS / "collect.py").exists())
        self.assertTrue((SCRIPTS / "build.py").exists())

    def test_workflow_runs_often_enough(self):
        wf = (ROOT / ".github" / "workflows" / "hq-77faf95c.yml").read_text(encoding="utf-8")
        self.assertIn("cron", wf)
        # the brief asks for a refresh every 4-8 hours
        self.assertTrue(any(h in wf for h in ("*/4", "*/5", "*/6", "*/7", "*/8")))


class TestCapture(unittest.TestCase):
    def test_access_log_records_every_source(self):
        acc = _load("access.json")
        if acc is None:
            self.skipTest("no capture yet")
        for key in ("hotspawn_lobby_page", "pinnacle", "bovada", "melbet", "kalshi"):
            self.assertIn(key, acc["sources"])

    def test_lobby_transfer_state_was_read(self):
        acc = _load("access.json")
        if acc is None:
            self.skipTest("no capture yet")
        self.assertTrue(acc["sources"]["hotspawn_lobby_page"].get("ng_state_found"))

    def test_vrs_snapshot_is_the_official_file(self):
        text = _load("raw/vrs_standings.md")
        if text is None:
            self.skipTest("no VRS snapshot yet")
        self.assertIn("Standings as of ", text)
        self.assertIn("| Standing | Points | Team Name", text)
        rows = [ln for ln in text.splitlines() if ln.startswith("| ") and "Team Name" not in ln
                and ":-" not in ln]
        self.assertGreater(len(rows), 300, "official standings file should carry 300+ teams")

    def test_no_quote_has_an_absurd_price(self):
        doc = _load("quotes.json")
        if doc is None:
            self.skipTest("no capture yet")
        for q in doc["quotes"]:
            for k in ("decimal_a", "decimal_b"):
                v = q.get(k)
                self.assertIsInstance(v, (int, float))
                self.assertGreater(float(v), 1.0)

    def test_kalshi_rejections_carry_a_reason(self):
        rej = _load("raw/kalshi_rejections.json")
        if rej is None:
            self.skipTest("no capture yet")
        for r in rej:
            self.assertIn("reason", r)


class TestBoard(unittest.TestCase):
    def setUp(self):
        self.board = _load("board.json")
        if self.board is None:
            self.skipTest("no board yet")

    def test_every_row_has_a_source_link(self):
        for r in self.board["rows"]:
            self.assertTrue(r["sources"], "row %s has no source" % r["fixture_id"])
            for s in r["sources"]:
                self.assertTrue(str(s["url"]).startswith("http"),
                                "row %s has a non-URL source" % r["fixture_id"])

    def test_hotspawn_is_never_used_as_a_probability(self):
        """A market row must rest on a bookmaker quote; a model row must rest on the Valve file."""
        for r in self.board["rows"]:
            if r["basis"] == "market":
                self.assertTrue(r["quotes"])
                self.assertTrue(all(q["source_key"] in ("pinnacle", "bovada", "melbet")
                                    for q in r["quotes"]))
            elif r["basis"] == "model":
                self.assertIn("model", r)
                self.assertTrue(any("ValveSoftware" in s["url"] for s in r["sources"]))

    def test_no_row_is_a_defaulted_fifty_fifty(self):
        for r in self.board["rows"]:
            if r["prob_a"] is None:
                self.assertIn("no_supported_line", r["flags"])
                self.assertIsNone(r["pick"])
            else:
                self.assertIn(r["basis"], ("market", "market-flagged", "model"))

    def test_probabilities_are_in_range(self):
        for r in self.board["rows"]:
            if r["prob_a"] is not None:
                self.assertGreater(r["prob_a"], 0.0)
                self.assertLess(r["prob_a"], 1.0)

    def test_pick_matches_the_higher_side(self):
        for r in self.board["rows"]:
            if r["prob_a"] is None:
                continue
            expected = r["team_a"] if r["prob_a"] >= 0.5 else r["team_b"]
            self.assertEqual(r["pick"], expected)

    def test_calibration_is_reported_not_asserted(self):
        cal = self.board["calibration"]
        self.assertTrue(cal["bounds"][0] <= cal["k"] <= cal["bounds"][1])
        self.assertEqual(cal["n_pairs"], len(cal["pairs"]))
        self.assertIn("formula", cal)

    def test_counts_match_the_rows(self):
        c = self.board["counts"]
        rows = self.board["rows"]
        self.assertEqual(c["listed_open"] + c["extra_not_listed"], len(rows))
        self.assertEqual(c["market"] + c["market_flagged"] + c["model"] + c["blank"], len(rows))
        self.assertEqual(c["with_probability"], len(rows) - c["blank"])

    def test_unresolved_rows_carry_an_attempt_ledger_or_a_flag(self):
        for r in self.board["rows"]:
            if r["basis"] in ("blank", "market-flagged"):
                self.assertTrue(r["research_ledger"] or r["flags"],
                                "row %s is unresolved with no documented reason" % r["fixture_id"])


class TestPages(unittest.TestCase):
    def setUp(self):
        if not (HQ / "index.html").exists():
            self.skipTest("no pages built yet")

    def _pages(self):
        return sorted(HQ.glob("*.html"))

    def test_all_pages_present(self):
        names = {p.name for p in self._pages()}
        self.assertEqual(names, {"index.html", "picks.html", "twc.html",
                                 "unresolved.html", "flagged.html", "method.html"})

    def test_pages_are_phone_viewport_ready(self):
        for p in self._pages():
            t = p.read_text(encoding="utf-8")
            self.assertIn('name="viewport"', t)
            self.assertIn("max-width:700px", t.replace(" ", "") or t)

    def test_internal_links_resolve(self):
        for p in self._pages():
            t = p.read_text(encoding="utf-8")
            for href in _hrefs(t):
                if href.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                target = (HQ / href.split("#")[0].split("?")[0])
                self.assertTrue(target.exists(), "%s links to missing %s" % (p.name, href))

    def test_no_unescaped_placeholder_probability(self):
        for p in self._pages():
            t = p.read_text(encoding="utf-8")
            self.assertNotIn("50.0%</span><span>50.0%", t)

    def test_every_page_says_hotspawn_is_not_a_probability_source(self):
        for p in self._pages():
            t = p.read_text(encoding="utf-8")
            self.assertIn("crowd pick", t.lower())


def _hrefs(text):
    import re
    return re.findall(r'href="([^"]+)"', text)


if __name__ == "__main__":
    unittest.main()
