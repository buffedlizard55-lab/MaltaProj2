"""Session c9c97561 — final-integration contracts for the landing front door and the
"Unresolved picks & limitations" page.

The brief asks for one phone-first dashboard where every HotSpawn CS2 match carries a pick, each
row links to the external source the number came from, and anything that could not be priced is
published as a documented limitation instead of being guessed. These tests read the committed
files only (no network) and fail when the landing stops publishing the full board, when a row
loses its source link, when a crowd percentage reappears as a probability, or when the limitations
page disappears from the executive summary.
"""
from __future__ import annotations

import json
import os
import unittest

from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD_PATH = os.path.join(ROOT, "data", "fe803b80", "board.json")
LANDING = os.path.join(ROOT, "index.html")
SITE = os.path.join(ROOT, "board")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def soup(path):
    return BeautifulSoup(read(path), "html.parser")


class BoardContract(unittest.TestCase):
    """The canonical board itself: every open match priced, sourced and reproducible."""

    @classmethod
    def setUpClass(cls):
        cls.board = load(BOARD_PATH)
        cls.rows = cls.board.get("open") or []

    def test_every_open_fixture_has_a_pick_and_no_blank_row(self):
        self.assertGreater(len(self.rows), 0, "the board must publish the open lobby")
        for row in self.rows:
            with self.subTest(fixture=row["fixture_id"]):
                line = row.get("line") or {}
                self.assertTrue(line.get("pick"), "every open fixture must carry a pick")
                self.assertAlmostEqual(line["prob_a"] + line["prob_b"], 1.0, places=6)
                self.assertGreaterEqual(line["pick_probability"],
                                        max(line["prob_a"], line["prob_b"]) - 1e-9)
                expected = row["team_a"] if line["prob_a"] >= line["prob_b"] else row["team_b"]
                self.assertEqual(line["pick"], expected)
        summary = self.board.get("summary") or {}
        self.assertEqual(summary.get("open_blank"), 0,
                         "a blank row must be published on the unresolved page, not silently left out")

    def test_every_open_row_links_an_external_source(self):
        for row in self.rows:
            with self.subTest(fixture=row["fixture_id"]):
                links = [s for s in (row.get("sources") or [])
                         if s.get("kind") in ("price", "rating", "identity", "assumption")
                         and str(s.get("url") or "").startswith("https://")]
                self.assertTrue(links, "every number must be traceable to an external source")
                self.assertTrue(row.get("attempts"), "the attempt ledger must be published")

    def test_crowd_percentage_is_never_read(self):
        blob = json.dumps(self.board)
        self.assertNotIn("hotspawn_pick", blob.lower())
        self.assertNotIn("crowd_pick", blob.lower())


class FrontDoorTests(unittest.TestCase):
    """The landing page must show the whole board, not a teaser."""

    @classmethod
    def setUpClass(cls):
        cls.board = load(BOARD_PATH)
        cls.rows = cls.board.get("open") or []
        cls.home = soup(LANDING)
        cls.door = cls.home.select_one("#front-door")
        cls.table = cls.door.select_one("table") if cls.door else None

    def test_landing_publishes_the_front_door(self):
        self.assertIsNotNone(self.door, "the landing page must publish the full-coverage front door")
        self.assertIsNotNone(self.table, "the front door must publish the picks as a table")
        self.assertEqual(len(self.home.find_all("h1")), 1, "one h1 keeps the phone header readable")

    def test_front_door_lists_every_open_fixture(self):
        body = self.door.get_text(" ", strip=True)
        for row in self.rows:
            with self.subTest(fixture=row["fixture_id"]):
                self.assertIn(row["team_a"], body)
                self.assertIn(row["team_b"], body)
        trs = self.table.find_all("tr")
        self.assertEqual(len(trs) - 1, len(self.rows),
                         "one table row per open fixture (the header row excluded)")

    def test_front_door_shows_both_win_probabilities_and_the_pick(self):
        for tr, row in zip(self.table.find_all("tr")[1:], self.rows):
            with self.subTest(fixture=row["fixture_id"]):
                labels = [td.get("data-label", "") for td in tr.find_all("td")]
                self.assertIn(f"{row['team_a']} win", labels)
                self.assertIn(f"{row['team_b']} win", labels)
                line = row.get("line") or {}
                cells = {td.get("data-label", ""): td.get_text(" ", strip=True)
                         for td in tr.find_all("td")}
                self.assertIn(f"{line['prob_a'] * 100:.1f}%", cells[f"{row['team_a']} win"])
                self.assertIn(f"{line['prob_b'] * 100:.1f}%", cells[f"{row['team_b']} win"])
                self.assertIn(line["pick"], cells["Pick"])

    def test_front_door_rows_link_their_source(self):
        for tr, row in zip(self.table.find_all("tr")[1:], self.rows):
            with self.subTest(fixture=row["fixture_id"]):
                cells = {td.get("data-label", ""): td for td in tr.find_all("td")}
                hrefs = [a.get("href", "") for a in cells["Sources"].find_all("a")]
                self.assertTrue(any(h.startswith("https://") for h in hrefs),
                                "every published row must link the source of its number")

    def test_front_door_never_shows_a_crowd_percentage(self):
        text = self.door.get_text(" ", strip=True).lower()
        self.assertNotIn("crowd", text, "HotSpawn's crowd split is never a probability")
        self.assertNotIn("hotspawn pick%", text)

    def test_front_door_reports_the_real_counts(self):
        summary = self.board.get("summary") or {}
        text = self.door.get_text(" ", strip=True)
        self.assertIn(str(summary.get("open")), text)
        self.assertIn(str(summary.get("open_with_pick")), text)
        self.assertIn(str(summary.get("open_blank")), text)

    def test_front_door_links_the_evidence_pages(self):
        hrefs = {a.get("href") for a in self.door.find_all("a")}
        for page in ("board/picks.html", "board/unresolved.html", "board/flagged.html",
                     "board/method.html"):
            self.assertIn(page, hrefs, f"the front door must link {page}")


class UnresolvedPageTests(unittest.TestCase):
    """A pick that could not be generated must be published with the reason, not hidden."""

    @classmethod
    def setUpClass(cls):
        cls.path = os.path.join(SITE, "unresolved.html")
        cls.page = soup(cls.path)
        cls.board = load(BOARD_PATH)
        cls.rows = cls.board.get("open") or []

    def test_page_exists_with_the_documented_sections(self):
        self.assertTrue(os.path.isfile(self.path), "the limitations page must be published")
        headings = [h.get_text(" ", strip=True) for h in self.page.find_all(["h1", "h2"])]
        self.assertTrue(any("Unresolved picks" in h for h in headings))
        for letter in ("A", "B", "C", "D"):
            self.assertTrue(any(h.startswith(letter + " ") for h in headings),
                            f"section {letter} must be published")

    def test_every_bounded_row_is_documented_with_a_source(self):
        bounded = [r for r in self.rows if (r.get("line") or {}).get("basis") in
                   ("vrs_floor_bound", "vrs_alias_candidate_bound", "vrs_alias_candidate")]
        text = self.page.get_text(" ", strip=True)
        for row in bounded:
            with self.subTest(fixture=row["fixture_id"]):
                self.assertIn(row["team_a"], text)
                self.assertIn(row["team_b"], text)
        self.assertIn(str(len(bounded)), text, "the count of assumption-bounded rows must be stated")

    def test_limitations_are_linked_from_the_executive_summary_and_the_board(self):
        pages = {
            "index.html": LANDING,
            "board/index.html": os.path.join(SITE, "index.html"),
            "board/picks.html": os.path.join(SITE, "picks.html"),
            "board/method.html": os.path.join(SITE, "method.html"),
        }
        for label, path in pages.items():
            with self.subTest(page=label):
                self.assertIn("unresolved.html", read(path),
                              f"{label} must link the unresolved & limitations page")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
