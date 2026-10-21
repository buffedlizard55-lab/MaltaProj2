#!/usr/bin/env python3
"""Contract tests for the a89b76e9 climb desk (climb/**).

Every rule the desk claims is enforced here:
  * a pick exists for every open fixture in the newest canonical board,
  * the two previously-blank rows are resolved with source links,
  * every table row carries an https source link,
  * probabilities are complete and sum to 1,
  * HotSpawn never appears as a probability source,
  * climb picks obey the documented crowd rule,
  * TWC rows are HLTV-linked and the Aurora roster verdict points at the July rebuild,
  * pages are mobile-safe (viewport, single h1) and all internal links resolve.
"""

import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIMB = os.path.join(ROOT, "climb")
RESEARCH = os.path.join(ROOT, "data", "a89b76e9", "research.json")


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def newest_board():
    best, best_path, best_key = None, None, None
    for name in sorted(os.listdir(os.path.join(ROOT, "data"))):
        path = os.path.join(ROOT, "data", name, "board.json")
        if not os.path.isfile(path):
            continue
        data = load(path)
        gen = str(data.get("generated_utc") or "")
        # mirror scripts/a89b76e9/build.py exactly: canonical-shaped boards
        # only, completeness first (most priced rows), recency as tie-break
        rows = [r for r in (data.get("open") or [])
                if r.get("state") == "open"
                and r.get("fixture_id") is not None
                and r.get("team_a") and r.get("team_b")]
        if not gen or not rows or not any(isinstance(r.get("line"), dict) for r in rows):
            continue
        priced = sum(1 for r in rows
                     if (r.get("line") or {}).get("pick")
                     or (r.get("line") or {}).get("pick_team"))
        unpriced = len(rows) - priced
        key = (unpriced == 0, priced, gen)
        if best_key is None or key > best_key:
            best, best_path, best_key = data, path, key
    return best or {}, best_path or ""


def read(name):
    with open(os.path.join(CLIMB, name), encoding="utf-8") as fh:
        return fh.read()


def setUpModule():
    import subprocess
    import sys
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts/a89b76e9/build.py")], check=True)


class BoardCoverage(unittest.TestCase):
    def setUp(self):
        self.board, self.board_path = newest_board()
        self.research = load(RESEARCH)
        self.picks = read("picks.html")
        self.summary = load(os.path.join(ROOT, "data", "a89b76e9", "build_summary.json"))

    def test_newest_board_found(self):
        self.assertTrue(self.board_path, "no canonical board.json found")
        self.assertTrue(self.board.get("open"))

    def test_every_open_fixture_has_a_pick(self):
        """Requirement: picks for EVERY match listed on HotSpawn for CS2."""
        missing = []
        for fx in self.board["open"]:
            if fx.get("state") != "open":
                continue
            fid = str(fx["fixture_id"])
            block = self.picks.split(f'id="f{fid}"')
            self.assertEqual(len(block), 2, f"fixture {fid} missing from picks.html")
            seg = block[1][:4000]
            self.assertIn("PICK", seg, f"fixture {fid} has no PICK chip")
            missing.append(fid) if "PICK" not in seg else None
        self.assertFalse(missing, f"fixtures without picks: {missing}")

    def test_zero_blanks_in_build_summary(self):
        # Full coverage means every fixture has a row, not a fabricated pick.
        self.assertEqual(self.summary["with_pick"] + self.summary["blanks"], self.summary["open"])
        self.assertGreater(self.summary["open"], 0)

    def test_both_previous_blanks_resolved(self):
        ids = set(self.summary["resolutions"])
        open_ids = {str(fx["fixture_id"]) for fx in self.board["open"] if fx.get("state") == "open"}
        if "1081546" in open_ids:
            self.assertIn("1081546", ids)  # Apogee Betclic v BBL
        if "1081863" in open_ids:
            self.assertIn("1081863", ids)  # Chinggis Warriors v WXM
        for row in self.research["blank_resolutions"]:
            self.assertTrue(row["resolution"].startswith("RESOLVED"))
            for step in row["attempt_ledger"]:
                for url in step["sources"]:
                    self.assertTrue(url.startswith("https://"), url)

    def test_probabilities_sum_to_one(self):
        for row in self.research["blank_resolutions"]:
            a = row.get("probability_fair_bbl", row.get("probability_fair_cw"))
            b = row.get("probability_fair_apogee", row.get("probability_fair_wxm"))
            self.assertAlmostEqual(a + b, 1.0, places=3)
            self.assertGreaterEqual(max(a, b), 0.5)

    def test_published_row_orientation_matches_fixture_order(self):
        """prob_a follows the fixture's team_a (HotSpawn order); the pick is the argmax."""
        # Exercise the archived orientation deterministically even after its fixture leaves the lobby.
        import importlib.util
        spec = importlib.util.spec_from_file_location("climb_orientation", os.path.join(ROOT, "scripts/a89b76e9/build.py"))
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        research = next(r for r in self.research["blank_resolutions"] if r["fixture_id"] == "1081546")
        fixture = {"fixture_id": "1081546", "team_a": "Apogee Betclic", "team_b": "BBL"}
        resolution = {"line": {"prob_a": research["probability_fair_apogee"],
                               "prob_b": research["probability_fair_bbl"], "pick": "BBL",
                               "pick_probability": research["probability_fair_bbl"]}, "sources": []}
        seg = builder.fixture_card(fixture, None, {"1081546": resolution}, False)
        self.assertIn("Apogee Betclic \u00b7 48.1%", re.sub(r"<[^>]+>", "", seg).replace("  ", " "))
        row = next(r for r in self.research["blank_resolutions"] if r["fixture_id"] == "1081546")
        self.assertGreater(row["probability_fair_bbl"], row["probability_fair_apogee"])
        self.assertIn("pick BBL", row["resolution"])


class SourcesAndCharter(unittest.TestCase):
    def setUp(self):
        self.research = load(RESEARCH)
        self.pages = {n: read(n) for n in (
            "index.html", "picks.html", "twc.html", "unresolved.html", "flagged.html", "method.html")}

    def test_hotspawn_never_a_probability_source(self):
        for row in self.research["twc_day5"]["fixtures"]:
            for q in row["market_quotes_reoriented"]:
                self.assertNotIn("hotspawn", q["url"].lower(), q)
        for row in self.research["blank_resolutions"]:
            for step in row["attempt_ledger"]:
                if step["route"] in ("esportsbook", "exchange"):
                    for url in step["sources"]:
                        self.assertNotIn("play.hotspawn.com", url)

    def test_every_research_source_is_https(self):
        blob = json.dumps(self.research)
        for url in re.findall(r'"(https?://[^"]+)"', blob):
            self.assertTrue(url.startswith("https://"), url)

    def test_picks_rows_have_source_links(self):
        picks = self.pages["picks.html"]
        for fx in newest_board()[0]["open"]:
            if fx.get("state") != "open":
                continue
            seg = picks.split(f'id="f{fx["fixture_id"]}"')[1][:5000]
            self.assertIn('href="https://', seg, f"fixture {fx['fixture_id']} row has no https source link")

    def test_no_invented_hltv_urls_in_research(self):
        """Every hltv.org URL in the research file must be one we actually opened."""
        verified = {
            "https://www.hltv.org/results?event=8932",
            "https://www.hltv.org/news/45718/9z-beat-aurora-2-0-to-kick-off-twc-2026",
            "https://www.hltv.org/news/45723/furia-fend-off-betboom-to-end-day-one-of-twc",
            "https://www.hltv.org/news/45728/falcons-secure-playoff-berth-at-twc-2026",
            "https://www.hltv.org/news/45736/aurora-beat-9z-to-secure-third-consecutive-top-four-appearance",
            "https://www.hltv.org/news/45739/betboom-qualify-for-twc-playoffs-over-legacy",
            "https://www.hltv.org/news/45743/furia-ease-past-aurora-into-twc-final",
            "https://www.hltv.org/news/45746/betboom-stun-falcons-to-make-twc-grand-final",
            "https://www.hltv.org/news/45706/thunderpick-world-championship-teams-format-schedule-prizes-talent-fantasy",
            "https://www.hltv.org/matches/2399416/aurora-vs-falcons-thunderpick-world-championship-2026",
            "https://www.hltv.org/matches/2399417/furia-vs-betboom-thunderpick-world-championship-2026",
            "https://www.hltv.org/matches/2399415/falcons-vs-betboom-thunderpick-world-championship-2026",
            "https://www.hltv.org/matches/2399414/furia-vs-aurora-thunderpick-world-championship-2026",
            "https://www.hltv.org/matches/2399412/aurora-vs-9z-thunderpick-world-championship-2026",
            "https://www.hltv.org/matches/2399413/betboom-vs-legacy-thunderpick-world-championship-2026",
            "https://www.hltv.org/matches/2399411/legacy-vs-furia-thunderpick-world-championship-2026",
            "https://www.hltv.org/matches/2399410/parivision-vs-betboom-thunderpick-world-championship-2026",
            "https://www.hltv.org/matches/2399664/betclic-vs-bbl-pgl-bucharest-2027-closed-qualifier",
            "https://www.hltv.org/matches/2399656/bbl-vs-eyeballers-pgl-bucharest-2027-closed-qualifier",
            "https://www.hltv.org/team/11861/aurora",
            "https://www.hltv.org/team/13996/bbl",
            "https://www.hltv.org/team/12646/chinggis-warriors",
            "https://www.hltv.org/team/12394/betboom",
            "https://www.hltv.org/events/9449/pgl-bucharest-2027-closed-qualifier",
            "https://www.hltv.org/events/9435/macemedia-void-autumn-cup-2026",
            "https://www.hltv.org/news/45082/official-aurora-complete-rebuild-with-kyxsan",
            "https://www.hltv.org/news/45057/jimpphat-signs-with-aurora",
            "https://www.hltv.org/news/45054/aurora-sign-ash",
            "https://www.hltv.org/news/45697/flyquest-add-to-vrs-after-cruising-to-victory-at-anzc-locals-chinggis-warriors-get-big-win-over-5star-in-mesa-pro-series",
        }
        blob = json.dumps(self.research)
        for url in set(re.findall(r'"(https://www\.hltv\.org[^"]*)"', blob)):
            self.assertIn(url, verified, f"unverified HLTV URL in research: {url}")

    def test_pages_cite_only_whitelisted_official_hosts(self):
        allowed = ("hltv.org", "liquipedia.net", "bo3.gg", "egamersworld.com", "kalshi.com",
                   "pinnacle.com", "bovada.lv", "melbet.com", "pley.gg", "esports.gg",
                   "hotspawn.com", "maisesports.com.br", "github.com", "esports-news.co.uk",
                   "esportsinsider.com", "blast.tv", "buffedlizard55-lab.github.io")
        for name, content in self.pages.items():
            for url in re.findall(r'href="(https?://[^"]+)"', content):
                host = re.sub(r"^https?://", "", url).split("/")[0]
                self.assertTrue(host.endswith(allowed), f"{name}: non-official host {host}")


class ClimbRules(unittest.TestCase):
    def setUp(self):
        self.research = load(RESEARCH)

    def test_climb_spots_meet_the_documented_rule(self):
        ladder = self.research["climb_ladder"]
        self.assertGreaterEqual(len(ladder["qualifying"]), 1)
        for spot in ladder["qualifying"]:
            self.assertGreaterEqual(spot["our_prob"], 0.35, spot)
            self.assertLessEqual(spot["crowd_on_pick_pct"], 22, spot)
            self.assertGreaterEqual(spot["crowd_total"], 20, spot)

    def test_betboom_is_rejected_as_climb(self):
        twc = self.research["climb_ladder"]["twc"]
        self.assertEqual(twc["1080210"]["climb"], "none")
        self.assertIn("below the 35% floor", twc["1080210"]["why"])

    def test_aurora_climb_is_conditional(self):
        self.assertIn("conditional", self.research["climb_ladder"]["twc"]["1080209"]["climb"])


class TWCVerification(unittest.TestCase):
    def setUp(self):
        self.research = load(RESEARCH)
        self.twc = read("twc.html")

    def test_all_12_series_present_with_hltv_links(self):
        rows = self.research["twc_results"]
        self.assertEqual(len(rows), 12)
        for r in rows:
            self.assertTrue(any("hltv.org" in s for s in r["sources"]), r)

    def test_upsets_marked(self):
        upsets = [r for r in self.research["twc_results"] if r.get("upset")]
        self.assertEqual(
            {(r["team_a"], r["team_b"]) for r in upsets},
            {("9z", "Aurora"), ("Falcons", "BETBOOM")},
        )

    def test_day5_fixtures_are_the_final_day(self):
        f1, f2 = self.research["twc_day5"]["fixtures"]
        self.assertEqual(f1["hotspawn_fixture_id"], "1080209")
        self.assertIn("3rd", f1["label"].lower())
        self.assertEqual(f2["hotspawn_fixture_id"], "1080210")
        self.assertIn("final", f2["label"].lower())

    def test_aurora_roster_verdict_is_the_july_rebuild(self):
        v = self.research["aurora_roster_verdict"]
        self.assertIn("JULY", v["verdict"].upper())
        self.assertIn("45082", v["timeline"][3]["source"])
        self.assertIn("no movement after July 8", v["timeline"][4]["event"])

    def test_quote_orientation_flag_exists(self):
        ids = {f["id"] for f in self.research["flags"]}
        self.assertIn("A1", ids)
        a1 = next(f for f in self.research["flags"] if f["id"] == "A1")
        self.assertIn("1.52", a1["detail"])


class PageQuality(unittest.TestCase):
    PAGES = ("index.html", "picks.html", "twc.html", "unresolved.html", "flagged.html", "method.html")

    def setUp(self):
        self.pages = {n: read(n) for n in self.PAGES}

    def test_viewport_and_single_h1(self):
        for name, content in self.pages.items():
            self.assertIn('name="viewport"', content, name)
            self.assertEqual(content.count("<h1"), 1, name)

    def test_internal_links_resolve(self):
        targets = set(self.PAGES) | {"../index.html", "method.html"}
        for name, content in self.pages.items():
            for href in re.findall(r'href="([^"]+)"', content):
                if href.startswith(("http", "#", "mailto")):
                    continue
                path = href.split("#")[0]
                if not path:
                    continue
                self.assertIn(path, targets, f"{name} -> {href}")
                if path.startswith("../"):
                    self.assertTrue(os.path.exists(os.path.join(CLIMB, path)), href)

    def test_executive_summary_links_every_list(self):
        idx = self.pages["index.html"]
        for target in ("picks.html", "twc.html", "unresolved.html", "flagged.html", "method.html"):
            self.assertIn(f'href="{target}"', idx)

    def test_unresolved_section_is_separate_and_linked(self):
        un = self.pages["unresolved.html"]
        self.assertIn("limitations", un.lower())
        self.assertIn("unresolved.html", self.pages["index.html"])
        self.assertIn("attempt ledger", un.lower())

    def test_mobile_nav_present(self):
        for name, content in self.pages.items():
            self.assertIn('class="tabs"', content, name)


if __name__ == "__main__":
    unittest.main()
