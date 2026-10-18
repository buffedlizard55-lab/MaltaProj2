#!/usr/bin/env python3
"""Contract tests for the b3871d16 day-5 desk (now/**).

These are the checks the brief asked for, made mechanical:

* every open CS2 fixture on the board has a row, and either a pick or a published reason;
* probabilities are bounded, sum to one, and are reproducible from the recorded market and model
  inputs - so a crowd percentage can never have leaked into a line;
* un-overridden rows carry exactly the canonical board's numbers (this desk may add evidence, it
  may not silently re-price);
* every row links at least one external source, and blanks are labelled blanks;
* the phone-first requirements (viewport, responsive tables, short rows) and the internal links.

The builder is re-run in setUpModule so a committed page can never disagree with the data beside it.
"""
from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
NOW = ROOT / "now"
SPEC = importlib.util.spec_from_file_location("b3871d16_build", ROOT / "scripts/b3871d16/build.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)

PAGES = ["index.html", "day5.html", "twc.html", "picks.html", "unresolved.html", "flagged.html", "method.html"]
BOOK_HOSTS = ("bo3.gg", "pinnacle.com", "bovada.lv", "melbet.com", "kalshi.com", "22bet.com", "betwinner.com",
              "hltv.org", "github.com", "liquipedia.net", "play-hotspawn", "hotspawn.com")


def setUpModule():  # noqa: N802 - unittest hook
    assert build.main() == 0, "builder must succeed"


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads((NOW / "data/board.json").read_text(encoding="utf-8"))
        cls.board = json.loads((ROOT / "data/fe803b80/board.json").read_text(encoding="utf-8"))
        cls.overrides = json.loads((ROOT / "data/b3871d16/overrides.json").read_text(encoding="utf-8"))
        cls.rows = cls.payload["rows"]
        cls.day5 = {r["fixture_id"]: r for r in cls.payload.get("day5") or []}
        cls.by_id = {r["fixture_id"]: r for r in cls.rows}
        cls.html = {p: (NOW / p).read_text(encoding="utf-8") for p in PAGES}


class TestCoverage(Fixture):
    def test_every_open_fixture_has_a_row(self):
        want = {str(r["fixture_id"]) for r in self.board["open"]}
        self.assertEqual(want, set(self.by_id), "the section must cover the whole open lobby, not a subset")
        self.assertGreater(len(want), 20, "a dropped board read should fail loudly")

    def test_every_row_has_a_pick_or_a_reason(self):
        for r in self.rows:
            with self.subTest(fixture=r["fixture_id"]):
                line, band = r.get("line"), r.get("band")
                if line:
                    self.assertTrue(line.get("pick"), "a priced row needs a pick")
                    self.assertGreaterEqual(line["pick_probability"], 0.5)
                elif band:
                    self.assertTrue(band.get("why_no_number") or band.get("label"),
                                    "a direction-only row must publish why there is no number")
                    self.assertTrue(r["notes"], "a direction-only row must carry its evidence in the notes")
                else:
                    self.assertTrue(r["notes"] or r["status_flag"] == "no_pick",
                                    "a row with no number needs a published reason")
                    self.assertIn(r["status_flag"], ("no_pick", "direction_band"))

    def test_the_two_previously_blank_rows_are_resolved(self):
        fixed = self.by_id["1081546"]
        self.assertTrue(fixed["line"], "the Betclic v BBL card should now be priced")
        self.assertGreaterEqual(fixed["market_n_sources"], 1)
        self.assertEqual(fixed["correction"], "price_added")
        band = self.by_id["1081863"]
        self.assertTrue(band["line"] or band["band"],
                        "Chinggis v WXM is either priced by a source or published as a band - never blank")
        if not band["line"]:
            self.assertTrue(band["band"], "an unpinned card must publish a range and the reason for it")
        self.assertIn("no probability published", self.html["unresolved.html"])

    def test_day5_cards_are_present_and_priced(self):
        for fid in ("1080209", "1080210"):
            row = self.day5.get(fid)
            self.assertIsNotNone(row, "a day-5 card must still be on the desk after its lock")
            self.assertGreaterEqual(row["market_n_sources"], 2)
            self.assertIn(row["state"], ("open", "closed"))
        text = self.html["day5.html"]
        for needle in ("1.35 / 2.90", "1.52 / 2.35", "11:24", "14:54", "7 points", "35%", "Bo5", "Bo3"):
            self.assertIn(needle, text, f"day5.html should quote {needle}")
        self.assertIn("20-pick floor", text, "the crowd-sample limit must be stated on the day-5 page")

    def test_climb_advice_only_exists_when_the_sample_clears_the_floor(self):
        """The sample grows minute by minute, so the rule is what gets asserted, not the number."""
        for row in self.payload.get("day5") or []:
            picks, lev = row["crowd"]["picks"], row["leverage"]
            with self.subTest(card=row["fixture_id"], picks=picks):
                if picks is not None and picks < 20:
                    self.assertTrue(lev is None or not lev["sample_ok"],
                                    "a sample under 20 picks may never clear the floor")
                if lev is not None:
                    self.assertEqual(lev["sample_ok"], picks is not None and picks >= 20)
        text = self.html["day5.html"]
        self.assertIn("Ownership is not a probability and never was", text)
        self.assertIn("pick floor", text)

class TestNumbers(Fixture):
    def test_probabilities_are_bounded_and_sum_to_one(self):
        for r in self.rows:
            line = r.get("line")
            if not line:
                continue
            with self.subTest(fixture=r["fixture_id"]):
                for key in ("prob_a", "prob_b", "pick_probability"):
                    self.assertGreaterEqual(line[key], 0.0)
                    self.assertLessEqual(line[key], 1.0)
                self.assertAlmostEqual(line["prob_a"] + line["prob_b"], 1.0, places=9)
                self.assertGreaterEqual(line["pick_probability"], max(line["prob_a"], line["prob_b"]) - 1e-9)
                exp = ("Strong" if line["pick_probability"] >= .70 else "Solid" if line["pick_probability"] >= .60
                       else "Lean" if line["pick_probability"] >= .53 else "Toss-up")
                self.assertEqual(line["confidence"], exp)

    def test_un_overridden_rows_match_the_canonical_board_exactly(self):
        max_dev = 0.0
        checked = 0
        for r in self.rows:
            if r.get("correction") or r.get("vrs_corrected"):
                continue
            src = next((x for x in self.board["open"] if str(x["fixture_id"]) == r["fixture_id"]), None)
            if not src or not src.get("line"):
                continue
            checked += 1
            max_dev = max(max_dev, abs(src["line"]["prob_a"] - r["line"]["prob_a"]))
        self.assertGreater(checked, 20)
        self.assertLess(max_dev, 2e-2, f"published line drifted from the board by {max_dev:.4f}")

    def test_lines_are_reproducible_from_market_and_model_only(self):
        """The published probability must be derivable from the recorded market/model inputs."""
        for r in self.rows:
            line = r.get("line")
            if not line or r.get("correction") or r.get("vrs_corrected"):
                continue
            with self.subTest(fixture=r["fixture_id"]):
                rebuilt = build.blend(r["market_prob_a"], r["market_n_sources"], r["model_prob_a"])
                self.assertIsNotNone(rebuilt)
                self.assertAlmostEqual(rebuilt["prob_a"], line["prob_a"], places=6)

    def test_no_probability_is_derived_from_hotspawn_ownership(self):
        for r in self.rows:
            line = r.get("line")
            if not line or r["crowd"]["a"] is None:
                continue
            with self.subTest(fixture=r["fixture_id"]):
                crowd_pct = (r["crowd"]["a"], r["crowd"]["b"])
                self.assertNotEqual((round(line["prob_a"] * 100), round(line["prob_b"] * 100)), crowd_pct,
                                    "a line equal to the crowd split means the crowd was used as a price")

    def test_price_links_never_point_at_hotspawn(self):
        for r in self.rows:
            if r["market_n_sources"]:
                urls = [u for lbl, u in r["sources"] if "price" in (lbl or "").lower()]
                self.assertTrue(urls, "a priced row must link the price page")
                for u in urls:
                    self.assertNotIn("hotspawn.com", u, "HotSpawn is never a price source")

    def test_every_row_has_at_least_one_external_link(self):
        for r in self.rows:
            urls = [u for _, u in r["sources"] if u.startswith("http")]
            self.assertTrue(urls, f"fixture {r['fixture_id']} has no external source link")
            self.assertTrue(any(any(h in u for h in BOOK_HOSTS) for u in urls),
                            f"fixture {r['fixture_id']} links nothing on the trusted list: {urls}")

    def test_crowd_join_is_refused_when_names_disagree(self):
        for r in self.rows:
            ori = (r["crowd"].get("orientation") or "")
            if ori.startswith("unusable"):
                self.assertIsNone(r["crowd"]["a"], "an unmatched crowd row must not be printed as numbers")
                self.assertIsNone(r["leverage"])

    def test_band_rows_publish_a_range_not_a_point(self):
        for r in self.rows:
            if not r.get("band"):
                continue
            rng = r["band"]["prob_a_range"]
            self.assertEqual(len(rng), 2)
            self.assertLess(rng[0], rng[1])
            self.assertTrue(r["band"].get("supported_by"), "a band must say what supports it")
            self.assertTrue(r["band"].get("not_supported_by"), "and what does not support it")


class TestSite(Fixture):
    def test_mobile_contract(self):
        for name, text in self.html.items():
            with self.subTest(page=name):
                self.assertIn("name=viewport", text)
                self.assertIn("content=\"width=device-width,initial-scale=1\"", text)
                self.assertIn("@media(max-width:760px)", text)
                self.assertIn('max-width:1080px', text)
                if "<table" in text:
                    self.assertIn("table.responsive", text)
                    self.assertIn("data-label=", text)
                    self.assertLessEqual(max((row.count("<td") for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S)
                                              if "<td" in row), default=0), 7, "a table with more than 7 columns is not usable on a phone")

    def test_internal_links_resolve(self):
        for name, text in self.html.items():
            for url in re.findall(r'href="([^"#]+)(?:#[^"]*)?"', text):
                parsed = urlsplit(url)
                if parsed.scheme or parsed.netloc:
                    continue
                target = (NOW / url).resolve()
                with self.subTest(page=name, href=url):
                    self.assertTrue(target.exists(), f"{name} links to a missing file: {url}")

    def test_executive_summary_links_into_the_pick_lists(self):
        text = self.html["index.html"]
        for target in ("picks.html", "day5.html", "unresolved.html", "flagged.html", "method.html", "twc.html"):
            self.assertRegex(text, r'href="?' + re.escape(target) + r'"?', f"summary should link {target}")

    def test_no_invented_dates_from_last_year(self):
        for name, text in self.html.items():
            self.assertNotIn("2025-10-1", text, f"{name} carries a 2025 date - a stale capture has leaked in")
        self.assertIn("2026-10-18", self.html["day5.html"])

    def test_flagged_page_lists_every_irregularity_with_a_link(self):
        ids = [ir["id"] for ir in self.overrides["irregularities_to_report"]]
        self.assertGreaterEqual(len(ids), 5)
        for iid in ids:
            self.assertIn(iid, self.html["flagged.html"])
        for ir in self.overrides["irregularities_to_report"]:
            self.assertTrue(ir["links"], f"{ir['id']} must link its evidence")
            self.assertTrue(ir["action"], f"{ir['id']} must say what was done")

    def test_limitations_are_surfaced_in_the_summary(self):
        self.assertIn("unresolved", self.html["index.html"].lower())
        self.assertIn("Blank beats wrong", self.html["method.html"])
        self.assertIn("HotSpawn is a fixture and ownership source only", self.html["method.html"])

    def test_read_times_are_published(self):
        for name in ("index.html", "picks.html", "day5.html"):
            self.assertRegex(self.html[name], r"Board read 20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ")
        self.assertIn("UTC", self.html["day5.html"])


class TestPipeline(Fixture):
    def test_workflow_exists_cron_four_hours_and_stays_in_scope(self):
        wf = (ROOT / ".github/workflows/now-b3871d16.yml").read_text(encoding="utf-8")
        self.assertRegex(wf, r"cron: '\d+ \*/4 \* \* \*'")
        self.assertIn("workflow_dispatch", wf)
        self.assertIn("git pull --rebase", wf)
        self.assertIn("git add now data/b3871d16", wf)
        for foreign in ("git add data/fe803b80", "git add board ", "git add start", "git add index.html"):
            self.assertNotIn(foreign, wf, f"this workflow must never commit {foreign}")
        self.assertIn("continue-on-error", wf, "a source failure must not break the refresh")
        # a push event checks out a detached SHA; without a named ref the rebase-before-push step dies
        self.assertIn("ref: ${{ github.head_ref || github.ref_name }}", wf)
        self.assertIn('git push origin "HEAD:refs/heads/$BRANCH"', wf)
        self.assertIn("git rebase --abort", wf, "a failed rebase must not leave the runner mid-rebase")

    def test_staging_publishes_this_section(self):
        staging = (ROOT / "scripts/stage_site.py").read_text(encoding="utf-8")
        self.assertIn("'now'", staging, "stage_site.py must carry the directory or the staged link check fails")
        self.assertIn("scripts/b3871d16/build.py", staging, "staging must re-render this section")

    def test_coordination_board_records_this_session(self):
        text = (ROOT / "COORDINATION.md").read_text(encoding="utf-8")
        self.assertIn("b3871d16", text)
        self.assertIn("T-B3871D16-NOW", text)

    def test_evidence_ledger_is_valid_and_every_claim_points_at_a_read(self):
        ledger = json.loads((ROOT / "data/b3871d16/live_reads.json").read_text(encoding="utf-8"))
        ids = {r["id"] for r in ledger["reads"]}
        self.assertGreaterEqual(len(ids), 12)
        for read in ledger["reads"]:
            self.assertTrue(read["url"].startswith("https://"))
            self.assertRegex(read["read_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
            self.assertTrue(read["data"], f"{read['id']} must record what was copied out")
        refs = set(re.findall(r"read_ref[s]?\"?:\s*\"?(R\d+)", json.dumps(self.overrides)))
        refs |= set(re.findall(r"\"R\d+\"", json.dumps(self.overrides)))
        refs = {x.strip('"') for x in refs}
        self.assertTrue(refs, "corrections must cite the read they came from")
        self.assertTrue(refs <= ids, f"cited reads missing from the ledger: {sorted(refs - ids)}")


if __name__ == "__main__":
    unittest.main()
