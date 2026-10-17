import json, pathlib, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
B = json.loads((ROOT / "data/9c44d0e9/board.json").read_text())

def devig(da, db):
    return (1 / da) / ((1 / da) + (1 / db))

class TodayDesk(unittest.TestCase):
    def test_inventory_matches_canonical(self):
        canon = json.loads((ROOT / "data/c64a5e19/board.json").read_text())
        self.assertEqual(B["summary"]["inventory_total"], len(canon["inventory"]))
        self.assertEqual(B["summary"]["open"], len(canon["open"]))
        self.assertEqual({str(r["fixture_id"]) for r in B["open"]},
                         {str(r["fixture_id"]) for r in canon["open"]})

    def test_every_row_sourced_or_blank(self):
        for r in B["open"] + B["twc"]:
            urls = [s.get("url", "") for s in r["sources"] if isinstance(s, dict)]
            self.assertTrue(r["hotspawn_url"].startswith("https://"), r["fixture_id"])
            if r["prob_a"] is not None:
                self.assertTrue(urls and all(u.startswith("https://") for u in urls), r["fixture_id"])
                self.assertAlmostEqual(r["prob_a"] + r["prob_b"], 1.0, places=3)
                fav = r["team_a"] if r["prob_a"] >= r["prob_b"] else r["team_b"]
                self.assertEqual(r["pick"], fav, r["fixture_id"])
            else:
                self.assertIsNone(r["pick"], r["fixture_id"])

    def test_climb_rule(self):
        for r in B["open"] + B["twc"]:
            if r.get("climb_pick"):
                self.assertGreaterEqual(r["climb_prob"], 0.40, r["fixture_id"])
                self.assertNotEqual(r["climb_pick"], r["pick"], r["fixture_id"])
                self.assertIn(r["climb_pick"], (r["team_a"], r["team_b"]))

    def test_twc_probs_rederive_from_evidence(self):
        ev = B["inputs"]["twc_evidence"]
        sf1 = next(r for r in B["twc"] if r["fixture_id"] == "twc-sf1")
        expect = (devig(*ev["sf1"]["egw_decimals"]) + ev["sf1"]["poly_cents"][0] / sum(ev["sf1"]["poly_cents"])) / 2
        self.assertAlmostEqual(sf1["prob_a"], round(expect, 4), places=4)
        sf2 = next(r for r in B["twc"] if r["fixture_id"] == "twc-sf2")
        self.assertAlmostEqual(sf2["prob_a"], round(devig(*ev["sf2"]["egw_decimals"]), 4), places=4)
        self.assertIsNone(sf2["climb_pick"])  # BETBOOM ~25%: below the not-stupid threshold

    def test_results_all_hltv_linked(self):
        self.assertEqual(len(B["results"]), 10)
        for row in B["results"]:
            self.assertTrue(row[-1].startswith("https://www.hltv.org/"), row)
        self.assertIn("Nuke 13–1", B["results"][0][5])  # day-1 upset, corrected score

    def test_pages_mobile_and_linked(self):
        for f in ("index.html", "picks.html", "twc.html", "unresolved.html", "flagged.html", "method.html"):
            h = (ROOT / "today" / f).read_text()
            self.assertIn('name="viewport"', h, f)
            self.assertNotIn("localhost", h, f)
        idx = (ROOT / "today/index.html").read_text()
        for href in ("picks.html", "twc.html", "unresolved.html", "../picks-every-match/index.html"):
            self.assertIn(href, idx)
        self.assertIn("Aurora", (ROOT / "today/twc.html").read_text())

if __name__ == "__main__":
    unittest.main()
