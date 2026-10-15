import json, re, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
D = json.loads((ROOT / "data/869a5375/twc.json").read_text())

class TestTwcData(unittest.TestCase):
    def test_day1_day2_complete(self):
        self.assertEqual(len(D["day1"]["rows"]), 4)
        self.assertEqual(len(D["day2"]["rows"]), 4)
        for day in ("day1", "day2"):
            for r in D[day]["rows"]:
                self.assertTrue(any("hltv.org" in s["url"] for s in r["sources"]), r["match"])
                self.assertRegex(r["score"], r"2–[01]|1–2")
    def test_standings_arithmetic(self):
        wins = {}
        for day in ("day1", "day2"):
            for r in D[day]["rows"]:
                m = re.match(r"(.+?) (\d)–(\d) (.+)", r["score"])
                a, sa, sb, b = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
                for t, s, o in ((a, sa, sb), (b, sb, sa)):
                    w, l = wins.get(t, (0, 0))
                    wins[t] = (w + (s > o), l + (s < o))
        for s in D["day2"]["standings_derived"]:
            self.assertEqual(f'{wins[s["team"]][0]}–{wins[s["team"]][1]}', s["record"], s["team"])
    def test_day3_every_match_has_pick_or_limitation(self):
        self.assertEqual(len(D["day3"]["rows"]), 2)
        for r in D["day3"]["rows"]:
            self.assertTrue(r["safe_pick"] and r["leaderboard_pick"])
            self.assertTrue(r["sources"])
            if r["prob_a"] is None:
                self.assertIsNone(r["prob_b"]); self.assertIsNone(r["safe_prob"])
                self.assertTrue(any(u["id"] == "U-TWC1" for u in D["unresolved"]))
            else:
                self.assertAlmostEqual(r["prob_a"] + r["prob_b"], 100.0, places=5)
                self.assertEqual(r["safe_pick"], "Aurora" if r["prob_a"] > r["prob_b"] else "9z")
    def test_crowd_never_probability(self):
        r = D["day3"]["rows"][0]
        self.assertNotEqual(r["prob_a"], r["crowd_a"])  # 65 market != 80 crowd
        self.assertIn("never a win probability", " ".join(D["policy"]))
    def test_contrarian_gates(self):
        r = D["day3"]["rows"][0]
        self.assertGreaterEqual(min(r["prob_a"], r["prob_b"]), 25)  # live underdog floor
        self.assertNotEqual(r["leaderboard_pick"], r["safe_pick"])
        r2 = D["day3"]["rows"][1]
        self.assertEqual(r2["leaderboard_pick"], r2["safe_pick"])  # no data -> no swing
    def test_unresolved_register(self):
        ids = [u["id"] for u in D["unresolved"]]
        self.assertEqual(len(ids), len(set(ids)))
        for u in D["unresolved"]:
            self.assertEqual(u["value"], "")
            self.assertTrue(u["sources"] and u["limitation"])

class TestTwcPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import subprocess, sys
        subprocess.run([sys.executable, str(ROOT / "scripts/869a5375/build.py")], check=True, cwd=ROOT, capture_output=True)
        cls.pages = {p.name: p.read_text() for p in (ROOT / "twc").glob("*.html")}
    def test_pages_exist_mobile_and_links(self):
        self.assertEqual(set(self.pages), {"index.html", "unresolved.html", "method.html"})
        for name, txt in self.pages.items():
            self.assertIn('name="viewport"', txt, name)
            for href in re.findall(r'href="([^"#]+)', txt):
                if href.startswith(("http://", "https://", "mailto:")):
                    continue
                target = (ROOT / "twc" / href).resolve() if not href.startswith("../") else (ROOT / href[3:]).resolve()
                self.assertTrue(target.exists(), f"{name} -> {href}")
    def test_index_shows_picks_and_blank(self):
        t = self.pages["index.html"]
        for needle in ("Aurora", "9z", "Legacy", "BetBoom", "65%", "35%", "blank", "Unresolved"):
            self.assertIn(needle, t)
        self.assertIn("crowd = ownership only", t)

if __name__ == "__main__":
    unittest.main()
