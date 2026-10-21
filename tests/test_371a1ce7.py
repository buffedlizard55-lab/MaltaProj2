"""Tests for the start/ front door (session 371a1ce7).

They check properties that stay true as the line board refreshes (arithmetic, one row per open fixture,
a source link on every row, blank-not-guessed probabilities, the climb rule) and never pin a snapshot of
the live fixture set, so a board refresh cannot break them.
"""
import copy
import importlib.util
import json
import pathlib
import re
import unittest
from datetime import datetime, timezone
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = load("start_build_371a1ce7", "scripts/371a1ce7/build.py")
C = load("start_collect_371a1ce7", "scripts/371a1ce7/collect.py")
START = ROOT / "start"
PAGES = ("index.html", "picks.html", "twc.html", "unresolved.html", "flagged.html", "method.html", "archive.html")
BOARD = json.loads((ROOT / "data/fe803b80/board.json").read_text(encoding="utf-8"))
CROWD = json.loads((ROOT / "data/371a1ce7/crowd.json").read_text(encoding="utf-8"))
TWC = json.loads((ROOT / "data/371a1ce7/twc.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 10, 18, 0, 30, tzinfo=timezone.utc)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs, self.stack, self.errors = [], [], []
        self.rows = []          # (id, [hrefs])
        self._row = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
            if self._row is not None:
                self._row[1].append(a["href"])
        if tag == "tr" and a.get("id"):
            self._row = (a["id"], [])
            self.rows.append(self._row)
        if tag not in ("meta", "br", "img", "hr", "input", "link", "i"):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "tr":
            self._row = None
        if tag in ("meta", "br", "img", "hr", "input", "link", "i"):
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(tag)
        else:
            self.stack.pop()


def parse(name):
    p = Links()
    p.feed((START / name).read_text(encoding="utf-8"))
    return p


class Pages(unittest.TestCase):
    def test_present_mobile_first_and_balanced(self):
        for n in PAGES:
            t = (START / n).read_text(encoding="utf-8")
            self.assertGreater(len(t), 2000, n)
            self.assertIn("width=device-width, initial-scale=1", t, n)
            p = parse(n)
            self.assertEqual(p.errors, [], n)
            self.assertEqual(p.stack, [], n)

    def test_tab_navigation_on_every_page_and_small(self):
        for n in PAGES:
            t = (START / n).read_text(encoding="utf-8")
            nav = re.search(r'<nav class="tabs".*?</nav>', t, re.S).group(0)
            targets = re.findall(r'href="([^"]+)"', nav)
            self.assertEqual(targets, [h for h, _ in B.TABS], n)
            self.assertLessEqual(len(targets), 7)

    def test_internal_links_resolve_and_external_are_https(self):
        for n in PAGES:
            for h in parse(n).hrefs:
                if h.startswith("http"):
                    self.assertTrue(h.startswith("https://"), (n, h))
                elif h.startswith("#"):
                    pass
                else:
                    target = (START / h.split("#")[0]).resolve()
                    self.assertTrue(target.exists(), (n, h))

    def test_anchor_links_land_on_an_id(self):
        for n in PAGES:
            t = (START / n).read_text(encoding="utf-8")
            for h in parse(n).hrefs:
                if "#" in h and not h.startswith("http"):
                    page, frag = h.split("#")
                    tt = t if not page else (START / page).read_text(encoding="utf-8")
                    self.assertIn(f'id="{frag}"', tt, (n, h))

    def test_every_table_row_has_an_external_source_link(self):
        for n in ("picks.html", "unresolved.html", "twc.html"):
            for rid, hrefs in parse(n).rows:
                self.assertTrue(any(h.startswith("https://") for h in hrefs), (n, rid))
        for tr in re.findall(r"<tr>.*?</tr>", (START / "twc.html").read_text(encoding="utf-8"), re.S):
            if "<td" in tr:
                self.assertIn('href="https://', tr)

    def test_landing_has_the_executive_summary_parts(self):
        t = (START / "index.html").read_text(encoding="utf-8")
        for needle in ("TWC 2026 final day", "Unresolved picks &amp; limitations", 'href="picks.html"',
                       'href="twc.html"', 'href="unresolved.html"', 'href="flagged.html"', "Best climb plays"):
            self.assertIn(needle, t)


class BoardRows(unittest.TestCase):
    def setUp(self):
        self.open, self.locked, self.anom = B.build_rows(BOARD, CROWD, NOW)

    def test_each_scheduled_lobby_fixture_exactly_once(self):
        ids = [r["fixture_id"] for r in self.open + self.locked]
        self.assertEqual(len(ids), len(set(ids)))
        for o in BOARD["open"]:
            if o["status"] == "scheduled" and str(o["fixture_id"]) not in {str(a["fixture_id"]) for a in self.anom}:
                self.assertIn(str(o["fixture_id"]), ids)
        for a in self.anom:
            self.assertNotIn(str(a["fixture_id"]), ids)

    def test_probability_is_copied_from_the_line_never_from_the_crowd(self):
        by = {str(o["fixture_id"]): o for o in BOARD["open"]}
        for r in self.open:
            line = by[r["fixture_id"]].get("line") or {}
            self.assertEqual(r["prob_a"], line.get("prob_a"))
            self.assertEqual(r["prob_b"], line.get("prob_b"))

    def test_pick_is_the_higher_probability_side(self):
        for r in self.open:
            if r["prob_a"] is not None and not r.get("tie"):
                self.assertEqual(r["pick"], r["team_a"] if r["prob_a"] >= r["prob_b"] else r["team_b"])
                self.assertAlmostEqual(r["prob_a"] + r["prob_b"], 1.0, places=6)
                self.assertEqual(r["pick_prob"], max(r["prob_a"], r["prob_b"]))

    def test_blank_probability_is_never_filled(self):
        for r in self.open:
            if r["prob_a"] is None or r.get("tie"):
                self.assertIsNone(r["pick_prob"])
                self.assertIsNone(r["leverage"])
                self.assertNotEqual(r["basis_kind"], "lines")

    def test_climb_rule_only_fires_when_every_condition_holds(self):
        for r in self.open:
            c = r["climb"]
            if c["kind"] == "switch":
                opp_p = c["prob"]
                self.assertGreaterEqual(opp_p, B.CLIMB_MIN_P)
                crowd_opp = r["crowd_b"] if r["pick_side"] == "a" else r["crowd_a"]
                self.assertLessEqual(crowd_opp, B.CLIMB_MAX_CROWD)
                self.assertGreaterEqual(opp_p - crowd_opp, B.CLIMB_MIN_EDGE)
                self.assertGreaterEqual(r["n_book_sources"], 1)

    def _synthetic(self, pa, ca, sources=("melbet",)):
        board = copy.deepcopy(BOARD)
        o = copy.deepcopy(next(x for x in BOARD["open"] if x["status"] == "scheduled" and (x.get("line") or {}).get("prob_a")))
        o["line"].update(prob_a=pa, prob_b=1 - pa)
        o["market"] = {"sources": list(sources)}
        o["lock_utc"] = "2026-10-18T09:00:00Z"
        board["open"] = [o]
        crowd = {"rows": [{"fixture_id": str(o["fixture_id"]), "crowd_a": ca, "crowd_b": 100 - ca}]}
        return B.build_rows(board, crowd, NOW)[0][0]

    def test_synthetic_switch_and_no_switch(self):
        r = self._synthetic(0.58, 85)          # B is 42% on the line, 15% of the crowd: switch
        self.assertEqual(r["climb"]["kind"], "switch")
        self.assertEqual(r["climb"]["pick"], r["team_b"])
        r = self._synthetic(0.70, 85)          # B only 30%: stay
        self.assertEqual(r["climb"]["kind"], "same")
        r = self._synthetic(0.58, 70)          # crowd on B is 30%: stay
        self.assertEqual(r["climb"]["kind"], "same")
        r = self._synthetic(0.58, 85, sources=())  # model-only: no switch
        self.assertEqual(r["climb"]["kind"], "same")

    def test_dead_even_line_is_a_tie_not_a_pick(self):
        r = self._synthetic(0.5, 85)
        self.assertTrue(r.get("tie"))
        self.assertIsNone(r["pick"])
        self.assertIsNone(r["pick_prob"])

    def test_tiny_crowd_sample_gives_no_climb_advice(self):
        board = copy.deepcopy(BOARD)
        o = copy.deepcopy(next(x for x in BOARD["open"] if x["status"] == "scheduled" and (x.get("line") or {}).get("prob_a")))
        o["line"].update(prob_a=0.58, prob_b=0.42)
        o["market"] = {"sources": ["melbet"]}
        o["lock_utc"] = "2026-10-18T09:00:00Z"
        board["open"] = [o]
        crowd = {"rows": [{"fixture_id": str(o["fixture_id"]), "crowd_a": 100, "crowd_b": 0, "total_picks": 2}]}
        r = B.build_rows(board, crowd, NOW)[0][0]
        self.assertEqual(r["climb"]["kind"], "none")
        self.assertIsNone(r["leverage"])

    def test_locked_rows_move_to_the_locked_table(self):
        # Cross an actual retained deadline, rather than permanently testing Oct 18.
        from datetime import timedelta
        deadlines = [B.parse_iso(o["lock_utc"]) for o in BOARD["open"] if o.get("lock_utc") and o.get("status") == "scheduled"]
        self.assertTrue(deadlines)
        late = max(deadlines) + timedelta(minutes=1)
        op, lk, _ = B.build_rows(BOARD, CROWD, late)
        self.assertTrue(lk)
        for r in lk:
            self.assertLessEqual(B.parse_iso(r["lock_utc"]), late)
        for r in op:
            self.assertGreater(B.parse_iso(r["lock_utc"]), late)

    def test_one_sided_rating_gives_a_direction_and_no_number(self):
        board = copy.deepcopy(BOARD)
        o = copy.deepcopy(next(x for x in BOARD["open"] if x["status"] == "scheduled"))
        o["line"] = None
        o["vrs_a"], o["vrs_b"] = {"points": 700.0}, None
        o["lock_utc"] = "2026-10-18T09:00:00Z"
        board["open"] = [o]
        r = B.build_rows(board, {"rows": []}, NOW)[0][0]
        self.assertEqual(r["pick"], r["team_a"])
        self.assertIsNone(r["pick_prob"])
        self.assertTrue(r["direction_only"])

    def test_both_unrated_gives_no_pick(self):
        board = copy.deepcopy(BOARD)
        o = copy.deepcopy(next(x for x in BOARD["open"] if x["status"] == "scheduled"))
        o["line"] = None
        o["vrs_a"] = o["vrs_b"] = None
        o["lock_utc"] = "2026-10-18T09:00:00Z"
        board["open"] = [o]
        r = B.build_rows(board, {"rows": []}, NOW)[0][0]
        self.assertIsNone(r["pick"])
        self.assertIsNone(r["pick_prob"])


class Twc(unittest.TestCase):
    def test_twelve_results_each_with_an_hltv_match_link(self):
        self.assertEqual(len(TWC["results"]), 12)
        seen = set()
        for r in TWC["results"]:
            m = re.fullmatch(r"https://www\.hltv\.org/matches/(\d+)/[a-z0-9-]+-thunderpick-world-championship-2026", r["hltv_url"])
            self.assertTrue(m, r["hltv_url"])
            self.assertEqual(int(m.group(1)), r["hltv_id"])
            self.assertNotEqual(r["score_a"], r["score_b"])
            self.assertIn(max(r["score_a"], r["score_b"]), (2,))
            self.assertNotIn(r["hltv_id"], seen)
            seen.add(r["hltv_id"])
            for t in (r["team_a"], r["team_b"]):
                self.assertIn(t, TWC["valve_rank"])

    def test_day5_arithmetic(self):
        for board_open in (BOARD["open"], []):          # with and without a HotSpawn board row
            for m in B.twc_day5(TWC, board_open):
                self.assertAlmostEqual(m["market_a"] + m["market_b"], 1.0, places=9)
                self.assertAlmostEqual(m["blend_a"] + m["blend_b"], 1.0, places=9)
                self.assertGreater(m["fav_prob"], 0.5)
                ln = m["line"]
                self.assertAlmostEqual(m["tp_a"], (1 / ln["dec_a"]) / (1 / ln["dec_a"] + 1 / ln["dec_b"]), places=9)
                self.assertGreater(m["overround"], 0)
                if m["basis"] == "single":
                    lo, hi = sorted((m["market_a"], m["model_a"]))
                    self.assertTrue(lo - 1e-9 <= m["blend_a"] <= hi + 1e-9)
                    self.assertAlmostEqual(m["market_a"], m["tp_a"], places=9)

    def test_board_row_is_the_published_number_when_hotspawn_lists_the_match(self):
        board = copy.deepcopy(BOARD)
        o = copy.deepcopy(next(x for x in BOARD["open"] if x["status"] == "scheduled" and (x.get("line") or {}).get("prob_a")))
        o.update(team_a="FURIA", team_b="BetBoom")
        o["line"].update(prob_a=0.7, prob_b=0.3)
        o["market"] = {"prob_a": 0.72, "prob_b": 0.28, "n_sources": 3, "sources": ["pinnacle", "melbet", "kalshi"]}
        furia = next(m for m in B.twc_day5(TWC, [o]) if m["key"] == "final")
        self.assertEqual(furia["basis"], "board")
        self.assertAlmostEqual(furia["blend_a"], 0.7, places=9)       # team_a of the TWC card is FURIA
        self.assertAlmostEqual(furia["market_a"], 0.72, places=9)
        self.assertEqual(furia["n_sources"], 3)
        # swapped order on the board row is aligned, not copied
        o2 = copy.deepcopy(o)
        o2.update(team_a="BetBoom", team_b="FURIA")
        o2["line"].update(prob_a=0.3, prob_b=0.7)
        o2["market"].update(prob_a=0.28, prob_b=0.72)
        furia2 = next(m for m in B.twc_day5(TWC, [o2]) if m["key"] == "final")
        self.assertAlmostEqual(furia2["blend_a"], 0.7, places=9)

    def test_series_math_roundtrip(self):
        for bo in (3, 5):
            self.assertAlmostEqual(B.series_prob(0.5, bo), 0.5, places=9)
            for p in (0.4, 0.55, 0.7):
                self.assertAlmostEqual(B.implied_map_prob(B.series_prob(p, bo), bo), p, places=6)
            self.assertGreater(B.series_prob(0.6, bo), 0.6)
        self.assertGreater(B.series_prob(0.6, 5), B.series_prob(0.6, 3))

    def test_day5_matches_are_the_two_hltv_matches(self):
        keys = {m["key"]: m for m in TWC["day5"]}
        self.assertEqual(keys["final"]["hltv_id"], 2399417)
        self.assertEqual(keys["third"]["hltv_id"], 2399416)
        for m in TWC["day5"]:
            for f in m["facts"]:
                self.assertTrue(f["s"], f["t"])
                for _, u in f["s"]:
                    self.assertTrue(u.startswith("https://"))


class Collector(unittest.TestCase):
    OPEN = [{"fixture_id": "1", "team_a": "Alpha", "team_b": "Beta"}]

    def test_sides_follow_names_not_position(self):
        api = [{"id": "1", "participants0_name": "Beta", "participants1_name": "Alpha",
                "participants0_picked_percent": 30, "participants1_picked_percent": 70, "total_picks": 9}]
        rows = C.rows_from_api(api, self.OPEN)
        self.assertEqual(rows[0]["crowd_a"], 70)
        self.assertEqual(rows[0]["crowd_b"], 30)

    def test_zero_pick_fixture_is_dropped(self):
        api = [{"id": "1", "participants0_name": "Alpha", "participants1_name": "Beta",
                "participants0_picked_percent": 0, "participants1_picked_percent": 0, "total_picks": 0}]
        self.assertEqual(C.rows_from_api(api, self.OPEN), [])

    def test_name_mismatch_and_missing_percent_are_dropped(self):
        api = [{"id": "1", "participants0_name": "Gamma", "participants1_name": "Beta",
                "participants0_picked_percent": 30, "participants1_picked_percent": 70}]
        self.assertEqual(C.rows_from_api(api, self.OPEN), [])
        api = [{"id": "1", "participants0_name": "Alpha", "participants1_name": "Beta"}]
        self.assertEqual(C.rows_from_api(api, self.OPEN), [])


class Freshness(unittest.TestCase):
    def test_stale_board_shows_a_banner(self):
        board = copy.deepcopy(BOARD)
        board["generated_utc"] = "2026-10-17T10:00:00Z"
        pages, _ = B.build_pages(board, CROWD, TWC, NOW)
        self.assertIn("Data is", pages["index.html"])

    def test_machine_summary_adds_up(self):
        _, m = B.build_pages(BOARD, CROWD, TWC, NOW)
        s = m["summary"]
        self.assertEqual(s["lines"] + s["model"] + s["direction_only"] + s["no_pick"], s["open"])


class Boundary(unittest.TestCase):
    def test_collector_never_reads_a_probability_from_the_crowd(self):
        src = (ROOT / "scripts/371a1ce7/build.py").read_text(encoding="utf-8")
        # crowd values may feed leverage and the climb rule, never prob_a / prob_b
        self.assertNotRegex(src, r"prob_[ab]\s*=\s*[^\n]*crowd")


if __name__ == "__main__":
    unittest.main()
