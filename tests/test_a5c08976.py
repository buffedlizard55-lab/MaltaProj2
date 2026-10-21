"""Session a5c08976 — resolving the last blank lobby rows without guessing.

Covers three additions to the fe803b80 full-coverage board:

* an evidence-backed alias (bo3.gg "Alianza Lima Esports" == Zetta) so the Elo rung can rate the
  CCT South America fixture;
* the guarded "ex-" roster join (HLTV/HotSpawn "ex-CYBERSHOKE" vs a bookmaker's "CYBERSHOKE"):
  market quotes only, identical opponent, same kick-off to the minute, never a rating borrow;
* the unlisted-team Elo floor, the "directional" label and the Unresolved picks & limitations page.

Offline: reads committed files only.
"""
from __future__ import annotations

import html
import json
import os
import sys
import unittest
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_DIR = os.path.join(ROOT, "scripts", "fe803b80")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)
import importlib  # noqa: E402

core = importlib.import_module("core")
if not hasattr(core, "match_quote_ex_prefix"):      # another session's `core` module got there first
    import importlib.util
    spec = importlib.util.spec_from_file_location("fe803b80_core", os.path.join(CORE_DIR, "core.py"))
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)

BOARD_PATH = os.path.join(ROOT, "data", "fe803b80", "board.json")
NOTES_PATH = os.path.join(ROOT, "data", "a5c08976", "research_notes.json")
SITE = os.path.join(ROOT, "board")
PAGES = ("index.html", "picks.html", "lines.html", "tournaments.html", "results.html",
         "flagged.html", "unresolved.html", "method.html")


class AliasTests(unittest.TestCase):
    def test_alianza_lima_resolves_to_zetta_with_roster_evidence(self):
        for name in ("Alianza Lima Esports", "alianza-lima-esports", "Alianza Lima"):
            key, evidence, note = core.canon(name)
            self.assertEqual(key, "zetta", name)
            self.assertTrue(note and "roster" in note.lower())
            self.assertTrue(any("bo3.gg/teams/alianza-lima-esports" in u for u in evidence))
            self.assertTrue(any("hltv.org/team/13833" in u for u in evidence))
            self.assertTrue(any("counter-strike_regional_standings" in u for u in evidence))
        self.assertEqual(core.canon("Zetta")[0], "zetta")
        self.assertEqual(core.canon("LOS NINOS")[0], core.canon("Los Niños")[0])

    def test_ex_prefix_is_never_folded_by_canon(self):
        self.assertNotEqual(core.canon("ex-CYBERSHOKE")[0], core.canon("CYBERSHOKE")[0])
        self.assertEqual(core.strip_ex_prefix("ex-CYBERSHOKE"), "CYBERSHOKE")
        self.assertEqual(core.strip_ex_prefix("Ex Tricked"), "Tricked")
        self.assertIsNone(core.strip_ex_prefix("CYBERSHOKE"))
        self.assertIsNone(core.strip_ex_prefix("Exploit"))      # no hyphen/space: not a prefix
        self.assertIsNone(core.strip_ex_prefix("ex-"))


class ExPrefixJoinTests(unittest.TestCase):
    FIXTURE = {"team_a": "ex-CYBERSHOKE", "team_b": "BlinkDagger",
               "start_utc": "2026-10-21T15:00:00Z"}

    def test_bookmaker_org_name_quote_joins_when_opponent_and_kickoff_are_identical(self):
        quote = {"team_a": "CYBERSHOKE", "team_b": "blinkdagger", "start_utc": "2026-10-21T15:00:00Z"}
        info = core.match_quote(self.FIXTURE, quote)
        self.assertIsNotNone(info)
        self.assertFalse(info["swapped"])
        self.assertTrue(info["ex_prefix"])
        self.assertTrue(any("hltv.org/matches/2399839" in u for u in info["alias_evidence"]))
        self.assertTrue(any("ex-CYBERSHOKE" in n for n in info["alias_notes"]))

    def test_swapped_orientation_and_org_suffix_still_join(self):
        quote = {"team_a": "BlinkDagger", "team_b": "CYBERSHOKE Esports",
                 "start_utc": "2026-10-21T15:10:00Z"}
        info = core.match_quote(self.FIXTURE, quote)
        self.assertIsNotNone(info)
        self.assertTrue(info["swapped"])
        self.assertTrue(info["ex_prefix"])

    def test_wrong_opponent_fails_closed(self):
        quote = {"team_a": "CYBERSHOKE", "team_b": "Team Ace", "start_utc": "2026-10-21T15:00:00Z"}
        self.assertIsNone(core.match_quote(self.FIXTURE, quote))

    def test_kickoff_more_than_15_minutes_apart_fails_closed(self):
        quote = {"team_a": "CYBERSHOKE", "team_b": "BlinkDagger", "start_utc": "2026-10-21T15:30:00Z"}
        self.assertIsNone(core.match_quote(self.FIXTURE, quote))
        # the plain 14-hour window must NOT apply to the ex- route
        quote = {"team_a": "CYBERSHOKE", "team_b": "BlinkDagger", "start_utc": "2026-10-21T18:00:00Z"}
        self.assertIsNone(core.match_quote(self.FIXTURE, quote))

    def test_missing_start_time_fails_closed(self):
        quote = {"team_a": "CYBERSHOKE", "team_b": "BlinkDagger", "start_utc": None}
        self.assertIsNone(core.match_quote(self.FIXTURE, quote))

    def test_both_sides_prefixed_or_neither_is_not_an_ex_join(self):
        quote = {"team_a": "ex-CYBERSHOKE", "team_b": "BlinkDagger", "start_utc": "2026-10-21T15:00:00Z"}
        info = core.match_quote(self.FIXTURE, quote)
        self.assertIsNotNone(info)
        self.assertFalse(info["ex_prefix"])                      # exact join, not the ex- route
        fixture = {"team_a": "CYBERSHOKE", "team_b": "BlinkDagger", "start_utc": "2026-10-21T15:00:00Z"}
        quote = {"team_a": "CYBERSHOKE Prospects", "team_b": "BlinkDagger",
                 "start_utc": "2026-10-21T15:00:00Z"}
        self.assertIsNone(core.match_quote(fixture, quote))      # a different org team never joins

    def test_ex_route_requires_one_exact_side(self):
        quote = {"team_a": "CYBERSHOKE", "team_b": "ex-BlinkDagger", "start_utc": "2026-10-21T15:00:00Z"}
        self.assertIsNone(core.match_quote(self.FIXTURE, quote))


class EloFloorTests(unittest.TestCase):
    def test_unseeded_teams_start_at_the_caller_supplied_default(self):
        ratings = core.elo_run([], seed={"bo3:1": 1600.0}, default=900.0)
        self.assertEqual(ratings, {"bo3:1": 1600.0})
        matches = [{"key_a": "bo3:1", "key_b": "bo3:2", "winner": "a", "start_utc": "2026-10-01T00:00:00Z"}]
        ratings = core.elo_run(matches, seed={"bo3:1": 1600.0}, default=900.0, passes=1)
        self.assertEqual(ratings["bo3:1"], 1600.0 + core.ELO_K * (1 - core.elo_expected(1600.0, 900.0)))
        self.assertLess(ratings["bo3:2"], 900.0)
        # default keeps the historical behaviour when not supplied
        ratings = core.elo_run(matches, seed={"bo3:1": 1600.0}, passes=1)
        self.assertLess(ratings["bo3:2"], core.ELO_BASE)
        self.assertGreater(ratings["bo3:2"], core.ELO_BASE - core.ELO_K)


@unittest.skipUnless(os.path.exists(BOARD_PATH), "board.json not generated in this checkout")
class BoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(BOARD_PATH, encoding="utf-8") as fh:
            cls.board = json.load(fh)
        cls.rows = cls.board["open"]

    def test_ex_prefix_rows_are_flagged_with_hltv_evidence_and_minute_exact_kickoff(self):
        for row in self.rows:
            ex_quotes = [q for q in row["quotes"] if q.get("ex_prefix")]
            flagged = "alias_ex_prefix_opponent_and_kickoff_triangulated" in row["flags"]
            self.assertEqual(bool(ex_quotes), flagged, row["fixture_id"])
            if not ex_quotes:
                continue
            self.assertIn("alias_applied_see_evidence", row["flags"])
            self.assertTrue(row["alias_note"])
            self.assertTrue(any("hltv.org" in u for u in row["alias_evidence"]), row["fixture_id"])
            for q in ex_quotes:
                self.assertLessEqual(q["start_diff_h"] or 0.0, core.TIME_EXACT_H)
            # the "ex-" roster must not have borrowed the organisation's official rating
            self.assertIsNone(row.get("vrs_a") if row["team_a"].lower().startswith("ex") else None)

    def test_directional_rows_are_labelled_flagged_and_sourced_per_side(self):
        for row in self.rows:
            line = row.get("line") or {}
            if not line:
                continue
            directional = bool(line.get("directional"))
            origin = row["model"].get("basis")
            self.assertEqual(directional,
                             line["basis"] == "model" and origin in ("originated_elo", "originated_rank"),
                             row["fixture_id"])
            if not directional:
                continue
            self.assertIn("directional_estimate_only", row["flags"], row["fixture_id"])
            rating_sources = [s for s in row["sources"] if s.get("kind") == "rating"]
            self.assertGreaterEqual(len(rating_sources), 2, row["fixture_id"])
            for s in rating_sources:
                self.assertTrue(str(s.get("url") or "").startswith("http"), s)
            if origin == "originated_elo":
                elo = row["model"]["elo"]
                for side in ("side_a", "side_b"):
                    self.assertIn(elo[side]["seed"], ("valve_vrs", "floor_unlisted"), row["fixture_id"])
                if any(elo[s]["seed"] == "floor_unlisted" for s in ("side_a", "side_b")):
                    self.assertIn("originated_elo_unlisted_team_started_at_vrs_floor", row["flags"])
                    self.assertEqual(elo["unlisted_team_start"], self.board["elo"]["unlisted_team_start"])

    def test_elo_floor_is_the_lowest_official_points_value(self):
        elo = self.board["elo"]
        if not elo.get("matches"):
            self.skipTest("no Elo input in this build")
        self.assertIn("floor_vrs_points", elo)
        self.assertLessEqual(elo["floor_vrs_points"], elo["anchor_vrs_points"])
        self.assertAlmostEqual(elo["unlisted_team_start"],
                               round(core.ELO_BASE + elo["floor_vrs_points"] - elo["anchor_vrs_points"], 1))

    def test_alias_rows_keep_their_evidence_and_zetta_alias_is_documented(self):
        self.assertEqual(core.canon("Alianza Lima Esports")[0], "zetta")
        for row in self.rows:
            if "alias_applied_see_evidence" in row["flags"]:
                self.assertTrue(row["alias_evidence"], row["fixture_id"])

    def test_blank_rows_are_counted_and_flagged_never_filled(self):
        s = self.board["summary"]
        blank = [r for r in self.rows if not r.get("line")]
        self.assertEqual(len(blank), s["open_blank"])
        for row in blank:
            self.assertIn("no_source_input_available_row_left_blank", row["flags"])
            self.assertIsNone(row.get("market"))
            self.assertIsNone(row["model"].get("prob_a"))


class ResearchNotesTests(unittest.TestCase):
    def test_every_research_note_is_dated_and_linked(self):
        with open(NOTES_PATH, encoding="utf-8") as fh:
            notes = json.load(fh)
        self.assertEqual(notes["session"], "a5c08976")
        self.assertTrue(notes["entries"])
        for e in notes["entries"]:
            self.assertTrue(e.get("title") and e.get("finding") and e.get("status"), e.get("title"))
            self.assertRegex(e["read_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
            self.assertTrue(e["urls"] and all(u.startswith("http") for u in e["urls"]), e["title"])
        ids = {e["fixture_id"] for e in notes["entries"] if e.get("fixture_id")}
        self.assertIn("1082762", ids)
        self.assertIn("1082837", ids)


@unittest.skipUnless(os.path.exists(os.path.join(SITE, "unresolved.html")),
                     "board section not generated in this checkout")
class SiteTests(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(SITE, name), encoding="utf-8") as fh:
            return fh.read()

    def test_unresolved_page_exists_is_mobile_first_and_in_every_nav(self):
        text = self.read("unresolved.html")
        self.assertIn('name="viewport"', text)
        self.assertIn("Unresolved picks &amp; limitations", text)
        for name in PAGES:
            self.assertIn('href="unresolved.html"', self.read(name), name)

    def test_executive_summary_links_the_unresolved_section_and_the_pick_list(self):
        text = self.read("index.html")
        self.assertIn("Where the picks are", text)
        self.assertIn('href="picks.html"', text)
        self.assertIn('href="unresolved.html"', text)
        self.assertIn("Unresolved picks", text)

    def test_unresolved_page_carries_the_research_ledger_and_source_links(self):
        text = self.read("unresolved.html")
        with open(NOTES_PATH, encoding="utf-8") as fh:
            notes = json.load(fh)
        for e in notes["entries"]:
            self.assertIn(html.escape(e["urls"][0], quote=True), text, e["title"])
        self.assertIn("What was tried for this row", text)
        self.assertIn("hltv.org", text)

    def test_every_internal_link_resolves(self):
        class Links(HTMLParser):
            def __init__(self):
                super().__init__()
                self.urls = []

            def handle_starttag(self, tag, attrs):
                for key, value in attrs:
                    if key in ("href", "src") and value:
                        self.urls.append(value)

        for name in PAGES:
            parser = Links()
            parser.feed(self.read(name))
            for url in parser.urls:
                parsed = urlsplit(url)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                self.assertTrue(os.path.exists(os.path.join(SITE, unquote(parsed.path))), (name, url))

    def test_directional_rows_say_so_on_the_pick_list(self):
        with open(BOARD_PATH, encoding="utf-8") as fh:
            board = json.load(fh)
        picks = self.read("picks.html")
        for row in board["open"]:
            if (row.get("line") or {}).get("directional"):
                self.assertIn("directional estimate", picks)
                break


if __name__ == "__main__":
    unittest.main()
