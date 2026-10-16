"""Contract tests for the day3/ section (session 4cf64ea3).

Principle (established in this repo by session 6c5bb3d6): the tests enforce STRUCTURE
and provenance; they report state and never assert that an upstream bot-refreshed board
keeps a specific value. Every table row must carry an official source link; anything
that cannot be confirmed stays blank and flagged; HotSpawn crowd % is never a probability.
"""
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build4cf", ROOT / "scripts" / "4cf64ea3" / "build.py")
build4cf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build4cf)

HTTPS = re.compile(r'href="(https?://[^"]+)"')
LOCAL = re.compile(r'href="([^"]+)"')


def build_twice():
    a = build4cf.build(write=False)
    b = build4cf.build(write=False)
    return a, b


class TestDeterminism(unittest.TestCase):
    def test_rebuild_is_identical(self):
        a, b = build_twice()
        self.assertEqual(a["board"], b["board"])
        self.assertEqual(a["pages"], b["pages"])


class TestBoardRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board, _ = build_twice()

    def test_every_row_normalizes_and_pick_is_argmax(self):
        for r in self.board["board"]["rows"]:
            if r["prob_a"] is None:
                self.assertIsNone(r["climb_pick"], f"{r['fixture_id']}: blank row must publish no pick")
                continue
            self.assertAlmostEqual(r["prob_a"] + r["prob_b"], 1.0, places=6,
                                   msg=f"{r['fixture_id']} probabilities do not normalize")
            fav = r["team_a"] if r["prob_a"] >= r["prob_b"] else r["team_b"]
            self.assertEqual(r["safe_pick"], fav, f"{r['fixture_id']}: safe pick must be argmax")

    def test_market_rows_rederive_from_raw_quotes(self):
        for r in self.board["board"]["rows"]:
            if r["basis"] != "market":
                continue
            quotes = [s for s in r["sources"] if s.get("prob_a") is not None and s.get("read_utc")]
            self.assertGreaterEqual(len(quotes), 1, f"{r['fixture_id']}: market row without retained quotes")
            mean = sum(q["prob_a"] for q in quotes) / len(quotes)
            self.assertAlmostEqual(mean, r["prob_a"], places=6,
                                   msg=f"{r['fixture_id']}: published probability is not the re-derived quote mean")

    def test_originated_row_matches_valve_formula(self):
        rows = [r for r in self.board["board"]["rows"] if r["basis"].startswith("originated")]
        self.assertTrue(rows, "expected the pre-emptive BETBOOM-Legacy originated row")
        k = self.board["board"]["inputs"]["calibration_k"]
        for r in rows:
            ev = json.loads((ROOT / "data" / "4cf64ea3" / "evidence.json").read_text())
            fx = next(f for f in ev["day3_fixtures"] if f["fixture_id"] == r["fixture_id"])
            vrs = fx["valve_vrs"]
            expect = build4cf.vrs_prob(vrs["points_a"], vrs["points_b"], k)
            self.assertAlmostEqual(expect, r["prob_a"], places=6)
            self.assertIn("originated", r["basis"].lower())

    def test_every_row_has_official_source_link(self):
        for r in self.board["board"]["rows"]:
            urls = [s.get("url") for s in r.get("sources") or []]
            self.assertTrue(any(u and u.startswith("https://") for u in urls),
                            f"{r['fixture_id']}: no https source on the row")
            for u in urls:
                self.assertTrue(u.startswith("https://"), f"{r['fixture_id']}: non-https source {u!r}")

    def test_crowd_never_used_as_probability(self):
        # The only probability-producing helpers must not read crowd fields.
        src = (ROOT / "scripts" / "4cf64ea3" / "build.py").read_text()
        for fn in ("def vrs_prob", "def rederive_fe_row", "def devig_prob"):
            i = src.index(fn)
            j = src.find("\ndef ", i + 1)
            block = src[i:j if j != -1 else i + 1600]
            block = "\n".join(line.split("#", 1)[0] for line in block.splitlines())  # drop comments
            self.assertNotIn("crowd", block, f"{fn} must not read crowd data")
            self.assertNotIn("pct_a", block, f"{fn} must not read crowd data")
        # Runtime: no published probability equals the raw crowd split.
        for r in self.board["board"]["rows"]:
            if r["prob_a"] is not None and r.get("crowd_pct_a") is not None:
                self.assertNotAlmostEqual(r["prob_a"], r["crowd_pct_a"] / 100.0, places=3,
                                          msg=f"{r['fixture_id']}: probability suspiciously equals crowd %")


class TestLadder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board, _ = build_twice()

    def test_not_stupid_floor(self):
        for r in self.board["board"]["rows"]:
            st = r["strategy"]
            if st.get("rule") in ("C1_coinflip_fade", "C2_upset_shot"):
                self.assertGreaterEqual(r["climb_prob"], 0.30 - 1e-9,
                                        f"{r['fixture_id']}: swing below the 30% floor")

    def test_c2_requires_two_flags_and_differential(self):
        for r in self.board["board"]["rows"]:
            st = r["strategy"]
            if st.get("rule") == "C2_upset_shot":
                self.assertGreaterEqual(len(st.get("flags") or []), 2)
                self.assertIsNotNone(st.get("differential"))
                self.assertGreaterEqual(st["differential"], 0.7)

    def test_no_crowd_defaults_to_safe(self):
        for r in self.board["board"]["rows"]:
            st = r["strategy"]
            if r["prob_a"] is not None and (r.get("crowd_pct_a") is None or r.get("crowd_pct_b") is None):
                self.assertEqual(r["climb_pick"], r["safe_pick"],
                                 f"{r['fixture_id']}: without a crowd split the climb pick must default to safe")
                self.assertTrue(any("no crowd split" in n for n in st.get("notes") or []),
                                f"{r['fixture_id']}: missing the no-crowd disclosure")

    def test_swings_are_labelled_not_hidden(self):
        for r in self.board["board"]["rows"]:
            st = r["strategy"]
            if r["climb_pick"] != r["safe_pick"]:
                self.assertIn(st.get("rule"), ("C1_coinflip_fade", "C2_upset_shot"),
                              f"{r['fixture_id']}: a different climb pick must carry a swing rule")
                self.assertTrue(st.get("notes"), f"{r['fixture_id']}: swing without an explanation note")


class TestPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result, _ = build_twice()
        cls.pages = cls.result["pages"]

    def test_all_pages_have_mobile_viewport_and_responsive_tables(self):
        for name, html in self.pages.items():
            self.assertIn('name="viewport"', html, f"{name}: missing mobile viewport")
            self.assertIn("max-width:640px", html, f"{name}: missing mobile media query")
            if "<table" in html:
                self.assertIn('class="responsive"', html, f"{name}: table without responsive stacking")

    def test_every_table_row_has_a_source_link(self):
        row_re = re.compile(r"<tr>(.*?)</tr>", re.S)
        for name, html in self.pages.items():
            for row in row_re.findall(html):
                if "<td" not in row:
                    continue
                # Every row must link somewhere (data rows: to their official source).
                self.assertTrue(LOCAL.search(row),
                                f"{name}: table row without any link: {row[:120]!r}")
                if re.search(r'data-label="(Sources|Source|URL)"', row):
                    self.assertTrue(HTTPS.search(row),
                                    f"{name}: data row without an https source link: {row[:120]!r}")

    def test_internal_links_resolve(self):
        for name, html in self.pages.items():
            for href in LOCAL.findall(html):
                if href.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                target, _, frag = href.partition("#")
                if not target:
                    continue
                resolved = (ROOT / "day3" / name).parent / target
                self.assertTrue(resolved.exists(),
                                f"{name}: broken internal link {href} -> {resolved}")

    def test_exec_summary_links_every_picks_list(self):
        html = self.pages["index.html"]
        for needle in ("picks.html", "unresolved.html", "day1-day2.html",
                       "../picks-all/index.html", "../board/picks.html", "../strategy/index.html",
                       "../picks-every-match/index.html", "../unresolved/index.html",
                       "../audits/6c5bb3d6/index.html", "../flagged.html"):
            self.assertIn(needle, html, f"executive summary missing link {needle}")

    def test_unresolved_page_discloses_limitations(self):
        html = self.pages["unresolved.html"]
        self.assertIn("limitations", html.lower())
        self.assertIn("bo3.gg", html)  # the researched-and-missing line must be disclosed
        self.assertIn("Valve VRS", html)

    def test_flagged_page_flags_values_left_blank(self):
        html = self.pages["flagged.html"]
        self.assertIn("left blank", html.lower())
        self.assertIn("https://", html)

    def test_day2_results_present_with_hltv_sources(self):
        html = self.pages["day1-day2.html"]
        for needle in ("2–0", "1–2", "hltv.org/matches/2399408", "hltv.org/matches/2399410",
                       "hltv.org/news/45728", "hltv.org/news/45730", "1080176", "UPSET"):
            self.assertIn(needle, html, f"day-1/2 review missing {needle}")


class TestEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev = json.loads((ROOT / "data" / "4cf64ea3" / "evidence.json").read_text())

    def test_all_evidence_urls_are_https(self):
        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if isinstance(v, str) and v.startswith(("https://", "http://")):
                        yield v
                    else:
                        yield from walk(v)
            elif isinstance(o, list):
                for v in o:
                    yield from walk(v)
        urls = [u for u in walk(self.ev) if u]
        self.assertGreater(len(urls), 30)
        for u in urls:
            self.assertTrue(str(u).startswith("https://"), f"non-https evidence url {u!r}")

    def test_results_have_scores_and_winners(self):
        for r in self.ev["day1_results"] + self.ev["day2_results"]:
            self.assertIn(r["winner"], (r["team_a"], r["team_b"]))
            self.assertIsInstance(r["score_a"], int)
            self.assertIsInstance(r["score_b"], int)
            self.assertTrue(r["sources"], f"{r['fixture_id']}: result row without sources")

    def test_day3_quotes_are_dated_and_sourced(self):
        for f in self.ev["day3_fixtures"]:
            if f["listed_on_hotspawn"]:
                for q in f["quotes"]:
                    self.assertTrue(q["url"].startswith("https://"))
                    self.assertRegex(q["retrieved_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
            else:
                self.assertTrue(f.get("searched"), "unpriced fixture must list where lines were searched")
                note = f["quotes_search_note"].lower()
                self.assertTrue("no bookmaker or exchange price" in note or "no market line" in note)
                self.assertIn("originated", note)


class TestWrittenOutput(unittest.TestCase):
    def test_written_files_match_build(self):
        saved = {
            p: p.read_bytes()
            for p in [ROOT / "data" / "4cf64ea3" / "board.json", *(ROOT / "day3").glob("*.html")]
            if p.exists()
        }
        try:
            written = build4cf.build(write=True)
            board = json.loads((ROOT / "data" / "4cf64ea3" / "board.json").read_text())
            self.assertEqual(board["summary"], written["board"]["summary"])
            for name, html in written["pages"].items():
                self.assertEqual((ROOT / "day3" / name).read_text(), html, f"{name} differs from build()")
        finally:
            for p, raw in saved.items():
                p.write_bytes(raw)


if __name__ == "__main__":
    unittest.main()
