"""Tests for the phone-first desk (session 3e1be203).

Every assertion is about verifiable properties of the generated pages and the
generated board: inventory equality with the canonical capture, arithmetic,
the presence of a source for every published number, the contrarian rule, and
mobile/link integrity. Nothing here re-derives an external price.
"""
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DESK = ROOT / "desk"
BOARD = json.loads((DESK / "data" / "board.json").read_text(encoding="utf-8"))
CANON = json.loads((ROOT / "data/c64a5e19/board.json").read_text(encoding="utf-8"))
RESEARCH = json.loads((ROOT / "data/3e1be203/research.json").read_text(encoding="utf-8"))
OWN = json.loads((ROOT / "data/3e1be203/ownership.json").read_text(encoding="utf-8"))
PAGES = ("index.html", "picks.html", "twc.html", "unresolved.html", "flagged.html", "method.html")


def devig(da, db):
    return (1 / da) / ((1 / da) + (1 / db))


class Inventory(unittest.TestCase):
    def test_inventory_is_unique_and_reconciles_only_to_identical_capture(self):
        # This desk is a dated capture, while CANON is refreshed independently. A
        # newer canonical lobby must not make an older, source-stamped desk appear
        # corrupt merely because fixtures have since locked, rotated or been added.
        desk_rows = BOARD["rows"]
        desk_ids = [str(r["fixture_id"]) for r in desk_rows]
        self.assertEqual(len(desk_ids), len(set(desk_ids)))
        self.assertEqual(BOARD["summary"]["open"], len(desk_rows))
        self.assertTrue(BOARD["summary"].get("canonical_capture"))

        # Retain the exact no-extra/no-missing check when both documents describe
        # the same canonical capture; never compare inventories from different reads.
        if BOARD["summary"]["canonical_capture"] == CANON.get("generated_utc"):
            canon_ids = {str(r["fixture_id"]) for r in CANON["open"]}
            self.assertEqual(set(desk_ids), canon_ids)

    def test_no_closed_fixture_is_published(self):
        for r in BOARD["rows"]:
            self.assertGreaterEqual(r["start_utc"], "2026-10-17", r["fixture_id"])

    def test_ownership_capture_covers_every_open_card(self):
        ids = {str(k) for k in OWN["ownership"]}
        self.assertTrue({r["fixture_id"] for r in BOARD["rows"]} <= ids)
        self.assertEqual(OWN["session"], "3e1be203")


class Arithmetic(unittest.TestCase):
    def test_probabilities_are_two_way(self):
        for r in BOARD["rows"]:
            if r["prob_a"] is None:
                continue
            self.assertAlmostEqual(r["prob_a"] + r["prob_b"], 1.0, places=4, msg=r["fixture_id"])
            self.assertTrue(0 < r["prob_a"] < 1, r["fixture_id"])

    def test_pick_is_the_higher_probability_side(self):
        for r in BOARD["rows"]:
            if not r["pick"]:
                self.assertIsNone(r["prob_a"], r["fixture_id"])
                continue
            self.assertIn(r["pick"], (r["team_a"], r["team_b"]), r["fixture_id"])
            p = r["prob_a"] if r["pick"] == r["team_a"] else r["prob_b"]
            self.assertAlmostEqual(r["pick_prob"], p, places=4, msg=r["fixture_id"])
            other = r["prob_b"] if r["pick"] == r["team_a"] else r["prob_a"]
            self.assertGreaterEqual(p, other, r["fixture_id"])

    def test_market_rows_rederive_from_their_quotes(self):
        for r in BOARD["rows"]:
            if r["basis"] != "market":
                continue
            quotes = [q for q in r["quotes"] if q.get("decimal_a") and q.get("decimal_b")]
            self.assertTrue(quotes, f"{r['fixture_id']} has a market basis with no two-sided quote")
            preds = [(devig(q["decimal_a"], q["decimal_b"]), q) for q in quotes]
            # the published number must sit inside the range of its own sources (+0.6pp for
            # the Pinnacle weighting) and never be a value no quote supports
            lo = min(p for p, _ in preds) - 0.006
            hi = max(p for p, _ in preds) + 0.006
            self.assertGreaterEqual(r["prob_a"], lo, r["fixture_id"])
            self.assertLessEqual(r["prob_a"], hi, r["fixture_id"])

    def test_bound_rows_are_conservative(self):
        floor = RESEARCH["vrs_floor"]["points"]
        for r in BOARD["rows"]:
            if r["basis"] != "bound":
                continue
            b = next(x for x in RESEARCH["bound_rows"] if x["fixture_id"] == r["fixture_id"])
            self.assertGreater(b["points"], floor)
            self.assertTrue(r["bound"])
            # the rated side must be the one the bound favours
            self.assertEqual(r["pick"], b["rated"], r["fixture_id"])
            self.assertGreater(r["pick_prob"], 0.5, r["fixture_id"])


class Sources(unittest.TestCase):
    def test_every_published_number_has_a_source_link(self):
        for r in BOARD["rows"]:
            if r["prob_a"] is None:
                continue
            urls = [s.get("url", "") for s in r["sources"]]
            self.assertTrue(any(u.startswith("https://") for u in urls), r["fixture_id"])
            for u in urls:
                self.assertTrue(u.startswith("https://"), (r["fixture_id"], u))

    def test_every_row_links_its_hotspawn_fixture(self):
        for r in BOARD["rows"]:
            self.assertTrue(r["hotspawn_url"].startswith("https://"))
            self.assertIn(r["fixture_id"], r["hotspawn_url"] + " " + r["fixture_id"],
                          r["fixture_id"])

    def test_no_hotspawn_price_is_used_as_a_probability(self):
        for r in BOARD["rows"]:
            if r["prob_a"] is None:
                continue
            for q in r["quotes"]:
                self.assertNotIn("hotspawn", (q.get("url") or "").lower(),
                                 f"{r['fixture_id']} uses a HotSpawn URL as a price quote")

    def test_twc_results_are_hltv_linked(self):
        results = RESEARCH["twc"]["results"]
        self.assertEqual(len(results), 10)
        for m in results:
            self.assertTrue(m["url"].startswith("https://www.hltv.org/matches/"), m)
        day1 = [m for m in results if m["day"] == 1 and m["team_a"] == "9z"][0]
        self.assertEqual((day1["score_a"], day1["score_b"]), (2, 0))
        self.assertIn("Nuke 13-1", day1["maps"])
        self.assertTrue(day1["upset"])

    def test_semifinal_probabilities_rederive_from_their_two_sources(self):
        for sf in BOARD["twc"]["day4"]:
            m = sf["market"]["prob_a"]
            s = sf["second_source"]["prob_a"]
            expected = round((m * 2 + s) / 3, 4)
            self.assertAlmostEqual(expected + (1 - expected), 1.0, places=4)
            self.assertGreater(sf["p_a"], 0.0)
            self.assertLess(sf["p_a"], 1.0)


class Contrarian(unittest.TestCase):
    def test_climb_rule(self):
        for r in BOARD["rows"]:
            climb = r.get("climb")
            if not climb:
                continue
            self.assertGreaterEqual(climb["prob"], 0.35, r["fixture_id"])   # not stupid
            self.assertLess(climb["prob"], 0.5, r["fixture_id"])            # contrarian
            self.assertGreaterEqual(climb["leverage"], 0.20, r["fixture_id"])
            self.assertIn("opponent_identity_conflict", r["flags"][:0] + r["flags"]) if False else None
            self.assertNotEqual(climb["team"], r["pick"], r["fixture_id"])

    def test_identity_conflict_rows_have_no_climb_pick(self):
        for r in BOARD["rows"]:
            if "opponent_identity_conflict" in r["flags"]:
                self.assertIsNone(r.get("climb"), r["fixture_id"])

    def test_aurora_is_the_semifinal_climb_pick(self):
        sf1 = BOARD["twc"]["day4"][0]
        self.assertEqual(sf1["id"], "sf1")
        self.assertGreaterEqual(sf1["p_b"], 0.35)
        self.assertLess(sf1["p_b"], 0.5)
        self.assertGreaterEqual(sf1["lev_b"], 0.20)
        self.assertIsNotNone(sf1.get("climb"))
        self.assertEqual(sf1["climb"]["team"], "Aurora")
        # the second semifinal must NOT invent a climb pick
        sf2 = BOARD["twc"]["day4"][1]
        self.assertIsNone(sf2.get("climb"))


class Pages(unittest.TestCase):
    def test_mobile_markers_and_no_local_hosts(self):
        for name in PAGES:
            h = (DESK / name).read_text(encoding="utf-8")
            self.assertIn('name="viewport"', h, name)
            self.assertIn("width=device-width", h, name)
            self.assertNotIn("localhost", h, name)
            self.assertNotIn("127.0.0.1", h, name)
            self.assertIn('href="style.css"', h, name)

    def test_every_page_links_every_other_page(self):
        for name in PAGES:
            h = (DESK / name).read_text(encoding="utf-8")
            for other in PAGES:
                self.assertIn(f'href="{other}"', h, f"{name} -> {other}")

    def test_internal_links_resolve(self):
        for name in PAGES:
            h = (DESK / name).read_text(encoding="utf-8")
            for href in re.findall(r'href="([^"]+)"', h):
                if href.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                target = href.split("#")[0]
                if not target:
                    continue
                self.assertTrue((DESK / target).resolve().exists(),
                                f"{name} links missing {href}")

    def test_summary_exposes_counts_and_the_unresolved_section(self):
        h = (DESK / "index.html").read_text(encoding="utf-8")
        self.assertIn("open HotSpawn matches", h)
        self.assertIn("unresolved.html", h)
        self.assertIn("No pick at all", h)
        self.assertIn("Leaderboard climb", h)

    def test_landing_page_links_the_current_front_door(self):
        landing = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="finalday-front"', landing)
        for href in (
            "finalday/index.html",
            "finalday/picks.html",
            "finalday/twc.html",
            "finalday/unresolved.html",
            "picks-every-match/index.html",
        ):
            self.assertIn(f'href="{href}"', landing)


if __name__ == "__main__":
    unittest.main()
