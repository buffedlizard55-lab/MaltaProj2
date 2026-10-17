"""Tests for the session 7191a16e desk (today/ + data/7191a16e).

Run:  python3 -m unittest tests.test_7191a16e -v

No network. The builder is executed once into the real output paths, then every
assertion is made against the files it produced. The canonical collector board
(data/c64a5e19/board.json) is hashed before and after to prove it is read-only.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANON = ROOT / "data" / "c64a5e19" / "board.json"
RESEARCH = ROOT / "data" / "7191a16e" / "research.json"
OUT_BOARD = ROOT / "data" / "7191a16e" / "board.json"
TODAY = ROOT / "today"
PAGES = [
    "index.html",
    "picks.html",
    "twc.html",
    "unresolved.html",
    "flagged.html",
    "method.html",
]


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DeskTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canon_before = sha(CANON)
        cls.proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "7191a16e" / "build.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        cls.canon_after = sha(CANON)
        cls.canon = json.loads(CANON.read_text())
        cls.research = json.loads(RESEARCH.read_text())
        cls.board = json.loads(OUT_BOARD.read_text())
        cls.rows = cls.board["rows"]
        cls.html = {p: (TODAY / p).read_text() for p in PAGES}

    # ---------- build integrity ----------

    def test_build_succeeds(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)

    def test_canonical_board_not_modified(self):
        self.assertEqual(self.canon_before, self.canon_after)

    def test_pages_exist(self):
        for page in PAGES:
            self.assertTrue((TODAY / page).is_file(), page)

    # ---------- coverage: every open fixture gets a row ----------

    def test_every_open_fixture_is_rendered_once(self):
        canon_ids = [str(r["fixture_id"]) for r in self.canon["open"]]
        self.assertEqual(len(canon_ids), len(self.rows))
        for fid in canon_ids:
            self.assertEqual(
                self.html["picks.html"].count('id="m-%s"' % fid), 1, fid
            )

    def test_row_count_matches_summary(self):
        s = self.board["summary"]
        self.assertEqual(s["open"], len(self.rows))
        self.assertEqual(s["priced"], s["open"] - s["direction_only"])
        self.assertEqual(
            s["named_pick"], s["priced"] - s["exact_tie"] + s["direction_only"]
        )

    def test_summary_counts_are_shown_in_html(self):
        s = self.board["summary"]
        self.assertIn("Priced matches (%d)" % s["priced"], self.html["picks.html"])
        self.assertIn(
            "Direction only — no percentage (%d)" % s["direction_only"],
            self.html["picks.html"],
        )
        self.assertIn("%d open matches" % s["open"], self.html["index.html"])

    # ---------- the actual requirement: no blank picks ----------

    def test_no_fixture_is_left_without_a_pick_or_an_edge_verdict(self):
        for r in self.rows:
            if r["kind"] in ("priced", "tie"):
                if r["kind"] == "tie":
                    self.assertIsNone(r["pick"])
                else:
                    self.assertTrue(r["pick"], r["fid"])
            else:
                self.assertEqual(r["kind"], "direction")
                self.assertTrue(r["pick"], r["fid"])
                self.assertTrue(r["note"], "direction row needs a reason: %s" % r["fid"])
                self.assertIsNone(r["pa"])
                self.assertIsNone(r["pb"])

    def test_direction_rows_are_listed_on_unresolved_page(self):
        for r in self.rows:
            if r["kind"] in ("direction", "tie"):
                self.assertIn("#%s" % r["fid"], self.html["unresolved.html"])

    def test_every_unpriced_fixture_is_ledgered(self):
        unpriced = {
            str(r["fixture_id"]) for r in self.canon["open"] if not r.get("line")
        }
        covered = (
            set(self.research.get("overrides", {}))
            | set(self.research.get("pick_only", {}))
            | set(self.research.get("tie", {}))
        )
        self.assertEqual(unpriced - covered, set(), "unhandled fixtures")
        # The ledger also carries the three fixtures that DO have a line, because
        # this session re-priced them (two TWC semis) or ruled them a coin flip.
        self.assertEqual(
            covered - unpriced, {"1080207", "1080208", "1082020"},
            "unexpected ledger entries with no fixture",
        )

    # ---------- no fake numbers ----------

    def test_probabilities_are_valid(self):
        for r in self.rows:
            if r["pa"] is None:
                self.assertIsNone(r["pb"])
                continue
            self.assertGreaterEqual(r["pa"], 0.0)
            self.assertLessEqual(r["pa"], 1.0)
            self.assertAlmostEqual(r["pa"] + r["pb"], 1.0, places=6)
            self.assertNotEqual(r["basis"], "no verified line")

    def test_only_one_exact_coin_flip_and_it_is_documented(self):
        ties = [r for r in self.rows if r["pa"] == 0.5]
        self.assertEqual([r["fid"] for r in ties], ["1082020"])
        self.assertIsNone(ties[0]["pick"])
        self.assertIn("coin flip", ties[0]["note"].lower())

    def test_placeholder_1_80_never_becomes_a_probability(self):
        """The 1.80/1.80 default would de-vig to exactly 50.0%. No row may carry it."""
        for r in self.rows:
            if r["fid"] == "1082020":
                continue
            if r["pa"] is not None:
                self.assertNotAlmostEqual(r["pa"], 0.5, places=4, msg=r["fid"])
        self.assertIn("1.80 / 1.80", self.html["unresolved.html"])

    def test_verified_values_survive_the_build(self):
        expected = {
            "1080207": 0.5140,
            "1080208": 0.7473,
            "1079634": 0.6276,
            "1081515": 0.3456,
            "1081126": 0.4577,
            "1079638": 0.6212,
            "1081521": 0.6822,
            "1081529": 0.4704,
        }
        got = {r["fid"]: r["pa"] for r in self.rows}
        for fid, want in expected.items():
            self.assertAlmostEqual(got[fid], want, places=6, msg=fid)

    def test_every_row_is_source_linked(self):
        for r in self.rows:
            self.assertTrue(r["sources"], r["fid"])
            for s in r["sources"]:
                self.assertTrue(s["url"].startswith("http"), (r["fid"], s))
                self.assertTrue(s.get("label"), (r["fid"], s))
            self.assertIn(r["hs"], r["hs"] and self.html["picks.html"])

    # ---------- TWC day-4 content ----------

    def test_twc_page_covers_days_1_to_3(self):
        page = self.html["twc.html"]
        for day in ("Day 1", "Day 2", "Day 3"):
            self.assertIn(day, page)
        for team in ("9z", "Aurora", "FURIA", "BETBOOM", "Falcons", "Legacy"):
            self.assertIn(team, page)

    def test_twc_page_states_the_verified_kickoff(self):
        page = self.html["twc.html"]
        self.assertIn("14:00 UTC", page)
        self.assertIn("13:54", page)
        self.assertNotIn("Kickoff ≈ <b>10:00", page)

    def test_roster_premise_is_corrected(self):
        page = self.html["twc.html"]
        self.assertIn("recent aurora roster change", page.lower())
        self.assertIn("July 2026", page)

    def test_upcoming_cards_are_sorted_by_start(self):
        starts = [r["start"] for r in self.rows]
        self.assertEqual(starts, sorted(starts))

    # ---------- HTML hygiene / phone layout ----------

    def test_mobile_scaffolding(self):
        for page in PAGES:
            h = self.html[page]
            self.assertIn('name="viewport"', h)
            self.assertIn('class="tabs"', h)
            self.assertIn("min-height:56px", h)  # 56px tap targets
            self.assertNotIn("width:980", h)

    def test_no_template_leaks(self):
        for page in PAGES:
            h = self.html[page]
            for bad in ("{esc(", "{LOBBY}", "None</div>", "nan%", "NaN"):
                self.assertNotIn(bad, h, page)
            self.assertIsNone(re.search(r">\s*None\s*<", h), page)

    def test_every_page_links_to_the_picks_list(self):
        for page in PAGES:
            self.assertIn('href="picks.html"', self.html[page], page)

    def test_executive_summary_links_every_in_site_list(self):
        page = self.html["index.html"]
        for target in ("picks.html", "twc.html", "unresolved.html", "flagged.html", "method.html"):
            self.assertIn('href="%s"' % target, page, target)


if __name__ == "__main__":
    unittest.main()
