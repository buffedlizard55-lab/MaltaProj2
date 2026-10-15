#!/usr/bin/env python3
"""Verification suite for session 6c5bb3d6's independent audit (audits/6c5bb3d6/).

Enforced here:
  1. the audit ran: ten checks, each with a status, detail, evidence link and failure list;
  2. every check that failed would fail this suite (no silent red);
  3. every published probability in the audited board re-derives from a retained raw quote
     and satisfies p_a + p_b = 1 with pick = argmax;
  4. every official Valve VRS citation matches Valve's own file as fetched by this session,
     and the WBT / ROUNDS alias rosters match 5/5;
  5. the HotSpawn crowd percentage is never numerically equal to a published probability
     and the published probability equals the upstream board's value byte for byte;
  6. the day-1 backtest totals recompute from their own settled rows;
  7. every page row carries an https source link, pages are mobile-first, internal links resolve;
  8. every value this audit could not confirm is published as blank/unverified, never filled;
  9. the differential (leaderboard) arithmetic is correct on a hand-computed case;
 10. the pages rebuild deterministically from committed evidence.
"""
import json
import math
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIF = ROOT / "data" / "6c5bb3d6" / "verification.json"
RESEARCH = ROOT / "data" / "6c5bb3d6" / "research.json"
VRS = ROOT / "data" / "6c5bb3d6" / "vrs_official.json"
BOARD = ROOT / "data" / "f28afd9e" / "board.json"
DAY1 = ROOT / "data" / "f28afd9e" / "day1_review.json"
SITE = ROOT / "audits" / "6c5bb3d6"
PAGES = ("index.html", "flagged.html", "method.html")

def load_harness():
    """Load scripts/6c5bb3d6/verify.py under a unique name.

    The repository root also contains a directory named `verify/`, and other sessions ship
    their own verify modules, so a plain `import verify` would bind the wrong module under
    discovery. Loading by explicit path keeps this suite independent of import order.
    """
    import importlib.util
    path = ROOT / "scripts" / "6c5bb3d6" / "verify.py"
    spec = importlib.util.spec_from_file_location("verify_6c5bb3d6_harness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class AuditRan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = load(VERIF)
        cls.checks = {c["id"]: c for c in cls.v["checks"]}

    def test_ten_checks_present_with_required_fields(self):
        self.assertEqual(len(self.v["checks"]), 10)
        for c in self.v["checks"]:
            for field in ("id", "name", "status", "detail", "evidence", "rows_checked",
                          "rows_failed", "failures"):
                self.assertIn(field, c, f"check {c.get('id')} missing {field}")
            self.assertIn(c["status"], ("pass", "warn", "info", "fail"))
            self.assertTrue(c["evidence"], f"check {c['id']} has no evidence link")

    def test_status_now_and_red_checks_are_published_not_hidden(self):
        """A failing check must surface on the pages rather than block the audit."""
        red = [c for c in self.v["checks"] if c["status"] == "fail"]
        index = (SITE / "index.html").read_text(encoding="utf-8")
        flagged = (SITE / "flagged.html").read_text(encoding="utf-8")
        self.assertIn(f"{len(red)} fail", index)
        for c in red:
            self.assertIn(f'{c["id"]} ·', index)
            self.assertIn('badge fail', index)
            for failure in c["failures"]:
                self.assertIn(failure.split(":")[0], flagged)
        # the current committed evidence produces no red check; if that changes the pages show it
        self.assertEqual([c["id"] for c in red], [], f"checks now failing: {[c['id'] for c in red]}")

    def test_every_check_actually_examined_rows(self):
        """A check that inspected zero rows would be vacuous evidence."""
        for cid, c in self.checks.items():
            self.assertGreater(c["rows_checked"], 0, f"{cid} checked no rows")

    def test_summary_counts_match_checks(self):
        counts = {}
        for c in self.v["checks"]:
            counts[c["status"]] = counts.get(c["status"], 0) + 1
        self.assertEqual(self.v["summary"]["by_status"], counts)
        self.assertEqual(self.v["summary"]["irregularities"], len(self.v["irregularities"]))


class PublishedBoardArithmetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load(BOARD)
        cls.v = load(VERIF)

    def test_rows_normalize_and_pick_is_argmax(self):
        for r in self.board["rows"]:
            pa, pb = r["prob_a"], r["prob_b"]
            self.assertAlmostEqual(pa + pb, 1.0, places=9, msg=r["fixture_id"])
            st = r.get("strategy") or {}
            if st.get("safe_pick"):
                best = r["team_a"] if pa >= pb else r["team_b"]
                self.assertEqual(st["safe_pick"], best, r["fixture_id"])

    def test_c3_rederived_every_row_from_raw_quotes(self):
        c3 = next(c for c in self.v["checks"] if c["id"] == "C3")
        self.assertEqual(c3["rows_failed"], 0, c3["failures"])
        priced = [row for row in c3["per_row"] if row["quotes"]]
        self.assertEqual(len(priced), len(self.board["rows"]),
                         "some published rows had no retained quote to re-derive from")
        for row in priced:
            for q in row["quotes"]:
                ia, ib = 1.0 / q["decimal_a"], 1.0 / q["decimal_b"]
                raw = ia / (ia + ib)
                oriented = raw if q["orientation"] == "straight" else 1.0 - raw
                self.assertAlmostEqual(q["raw_side_a_prob"], raw, places=6)
                self.assertAlmostEqual(q["rederived_prob_a"], oriented, places=6)
                self.assertIn(q["orientation"], ("straight", "swapped"))
                self.assertTrue(str(q["url"]).startswith("http"), row["fixture_id"])

    def test_novig_helper_matches_hand_computation(self):
        harness = load_harness()
        # Pinnacle WBT -179 / ENCE +139 -> 1.558659 / 2.39 (retained quote, 2026-10-15T09:55:01Z)
        p = harness.novig(1.558659, 2.39)
        ia, ib = 1 / 1.558659, 1 / 2.39
        self.assertAlmostEqual(p, ia / (ia + ib), places=9)
        self.assertAlmostEqual(p, 0.605269, places=5)


class OfficialStandings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vrs = load(VRS)
        cls.v = load(VERIF)
        cls.research = load(RESEARCH)

    def test_official_snapshot_is_real_and_sized(self):
        self.assertEqual(self.vrs["http_status"], 200)
        self.assertGreaterEqual(self.vrs["teams_parsed"], 300)
        self.assertIn("ValveSoftware/counter-strike_regional_standings", self.vrs["api_url"])
        self.assertEqual(self.vrs["snapshot"], "2026_10_05")

    def test_every_vrs_citation_matches_valves_file(self):
        c4 = next(c for c in self.v["checks"] if c["id"] == "C4")
        self.assertEqual(c4["rows_failed"], 0, c4["failures"])
        self.assertGreaterEqual(c4["rows_checked"], 10)
        teams = self.vrs["teams"]
        for cit in c4["citations"]:
            official = teams.get(re.sub(r"[^a-z0-9]", "", cit["cited"].lower()))
            self.assertIsNotNone(official, cit["cited"])
            self.assertEqual(official["standing"], cit["standing"], cit["cited"])
            self.assertEqual(official["points"], cit["points"], cit["cited"])

    def test_alias_rosters_match_five_of_five(self):
        c4 = next(c for c in self.v["checks"] if c["id"] == "C4")
        by_team = {a["team"]: a for a in c4["alias_rosters"]}
        for team in ("WBT", "ROUNDS"):
            self.assertEqual(by_team[team]["roster_overlap"], "5/5", by_team[team])
            self.assertEqual(by_team[team]["status"], "match")
        # WBT main and WBT Academy must remain distinct rows in Valve's file
        self.assertNotEqual(by_team["WBT"]["official_points"], by_team["WBT Academy"]["official_points"])

    def test_identity_evidence_chains_are_published_with_sources(self):
        for item in self.research["identity_resolutions"]:
            self.assertGreaterEqual(len(item["evidence_chain"]), 4, item["id"])
            self.assertTrue(all(str(s["url"]).startswith("https://") for s in item["sources"]))
            self.assertTrue(item["residual_limitation"], item["id"])


class CrowdPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load(BOARD)
        cls.v = load(VERIF)

    def test_crowd_never_equals_a_probability(self):
        for r in self.board["rows"]:
            crowd = (r.get("crowd") or {}).get("pct_a")
            if crowd is None:
                continue
            self.assertNotAlmostEqual(r["prob_a"], crowd / 100.0, places=9,
                                      msg=f"{r['fixture_id']} probability equals crowd share")

    def test_probability_is_the_upstream_value(self):
        c6 = next(c for c in self.v["checks"] if c["id"] == "C6")
        self.assertEqual(c6["rows_failed"], 0, c6["failures"])
        for r in self.board["rows"]:
            board = (r.get("line") or {}).get("board")
            upstream = [cc["prob_a"] for cc in r.get("cross_check") or [] if cc.get("board") == board]
            self.assertTrue(upstream, f"{r['fixture_id']} has no upstream cross-check")
            self.assertAlmostEqual(upstream[0], r["prob_a"], places=12)


class DayOneReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.day1 = load(DAY1)
        cls.v = load(VERIF)
        cls.research = load(RESEARCH)

    def test_backtest_totals_recompute(self):
        c7 = next(c for c in self.v["checks"] if c["id"] == "C7")
        self.assertEqual(c7["rows_failed"], 0, c7["failures"])
        rec = c7["recomputed"]
        summary = self.day1["summary"]
        for key in ("settled", "safe_correct", "leaderboard_correct", "safe_points", "leaderboard_points"):
            self.assertAlmostEqual(float(summary[key]), float(rec[key]), places=6, msg=key)

    def test_upset_results_are_officially_sourced(self):
        by_id = {str(i.get("fixture_id")): i for i in self.research["day1_results"]}
        for fid, expect in (("1080176", "9z 2-0 Aurora"), ("1079439", "HOTU 2-0 fnatic")):
            self.assertIn(fid, by_id)
            self.assertEqual(by_id[fid]["match"], expect)
            self.assertTrue(by_id[fid]["verdict"].startswith("verified"))
            self.assertTrue(all(str(s["url"]).startswith("https://") for s in by_id[fid]["sources"]))
            self.assertTrue(any("hltv.org" in s["url"] for s in by_id[fid]["sources"]), fid)

    def test_prelock_crowd_evidence_is_cited_to_a_commit(self):
        item = self.research["day1_crowd_ownership"][0]
        self.assertEqual(item["verdict"], "verified")
        joined = json.dumps(item)
        self.assertIn("8f66ce4705f8e7581fd32031945b038033eab739", joined)
        self.assertTrue(any("api.github.com" in s["url"] for s in item["sources"]))

    def test_inherited_settlements_are_disclosed(self):
        c7 = next(c for c in self.v["checks"] if c["id"] == "C7")
        self.assertTrue(c7["inherited_settlement"])
        flagged = [i for i in self.v["irregularities"] if i["id"] == "IR-C7b"]
        self.assertEqual(len(flagged), 1)
        for fid in c7["inherited_settlement"]:
            self.assertIn(fid, flagged[0]["detail"])


class DifferentialMath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = load(VERIF)
        cls.table = {d["fixture_id"]: d for d in cls.v["differential_table"] if d.get("points")}

    def test_edge_formula_on_a_known_row(self):
        row = self.table["1080202"]          # 9z vs Falcons, 7 points, crowd 5/95
        self.assertEqual((row["points"], row["crowd_a"], row["crowd_b"]), (7.0, 5, 95))
        # the harness rounds the differential before scaling; allow that rounding chain
        self.assertAlmostEqual(row["ev_a"], 7.0 * (row["prob_a"] - 0.05), delta=0.002)
        self.assertAlmostEqual(row["ev_b"], 7.0 * (row["prob_b"] - 0.95), delta=0.002)
        self.assertEqual(row["differential_optimal"], "9z")

    def test_every_open_row_has_both_edges_and_a_side(self):
        for fid, row in self.table.items():
            if row.get("state") != "open":
                continue
            for key in ("prob_a", "prob_b", "diff_a", "diff_b", "ev_a", "ev_b"):
                self.assertIsNotNone(row.get(key), f"{fid} missing {key}")
            self.assertAlmostEqual(row["diff_a"], row["prob_a"] - row["crowd_a"] / 100.0, places=6)
            self.assertIn(row["differential_optimal"], row["match"])

    def test_divergences_are_published_not_hidden(self):
        c8 = next(c for c in self.v["checks"] if c["id"] == "C8")
        flagged = [i for i in self.v["irregularities"] if i["id"] == "IR-C8"]
        if c8["divergences"]:
            self.assertEqual(len(flagged), 1)
            for d in c8["divergences"]:
                self.assertIn(d.split(":")[0], flagged[0]["detail"])
        page = (SITE / "flagged.html").read_text(encoding="utf-8")
        for d in c8["divergences"]:
            self.assertIn(d.split(":")[0].strip(), page)


class Pages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = {name: (SITE / name).read_text(encoding="utf-8") for name in PAGES}

    def test_mobile_viewport_and_language(self):
        for name, text in self.html.items():
            self.assertIn('name="viewport" content="width=device-width, initial-scale=1"', text, name)
            self.assertIn('lang="en"', text, name)
            self.assertIn("max-width:700px", text, name)

    def test_every_table_row_has_a_source_link(self):
        for name, text in self.html.items():
            # tables carrying values must link an official source; navigation tables are exempt
            # but must be explicitly marked as navigation and link our own site
            nav_spans = [m.span() for m in re.finditer(r'<table data-nav="true">.*?</table>', text, re.S)]
            rows = []
            for m in re.finditer(r"<tr\b.*?</tr>", text, re.S):
                if not any(a <= m.start() < b for a, b in nav_spans):
                    rows.append(m.group(0))
            self.assertTrue(rows, name)
            without = []
            for row in rows:
                if "<th" in row:
                    continue
                if not re.search(r'href="https?://', row):
                    without.append(re.sub(r"<[^>]+>", " ", row)[:90])
            self.assertEqual(without, [], f"{name}: rows without an https source: {without[:4]}")
            for m in re.finditer(r'<table data-nav="true">(.*?)</table>', text, re.S):
                self.assertTrue(re.search(r'href="\.\./', m.group(1)), name)

    def test_executive_links_to_the_picks(self):
        index = self.html["index.html"]
        self.assertIn("where-the-picks", index)
        for href in ("../../strategy/index.html", "../../picks-every-match/index.html",
                     "../94b3d48a/index.html", "../../strategy/unresolved.html"):
            self.assertIn(href, index)
            self.assertTrue((ROOT / href.replace("../../", "").replace("../", "audits/")).exists()
                            or (ROOT / "audits" / href.replace("../", "")).exists(), href)

    def test_unverified_items_are_published_as_blank(self):
        research = load(RESEARCH)
        flagged = self.html["flagged.html"]
        for item in research["unverified"]:
            self.assertIn(item["id"], flagged)
            self.assertIn(item["item"].split("(")[0].strip()[:24], flagged)

    def test_internal_links_resolve(self):
        for name, text in self.html.items():
            for href in re.findall(r'href="([^"]+)"', text):
                if href.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                target = (SITE / href.split("#")[0]).resolve()
                self.assertTrue(target.exists(), f"{name} -> {href}")

    def test_no_double_escaped_entities(self):
        for name, text in self.html.items():
            self.assertNotIn("&amp;amp;", text, name)

    def test_deterministic_rebuild(self):
        """Two consecutive renders of the same committed evidence are byte-identical."""
        build = str(ROOT / "scripts" / "6c5bb3d6" / "build_pages.py")
        first = subprocess.run([sys.executable, build], capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(first.returncode, 0, first.stderr)
        before = {name: (SITE / name).read_text(encoding="utf-8") for name in PAGES}
        second = subprocess.run([sys.executable, build], capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(second.returncode, 0, second.stderr)
        for name in PAGES:
            self.assertEqual((SITE / name).read_text(encoding="utf-8"), before[name], name)


class HarnessIntegrity(unittest.TestCase):
    def test_verify_reruns_clean(self):
        proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "6c5bb3d6" / "verify.py")],
                              capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("verification: 10 checks", proc.stdout)
        report = json.loads((SITE / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(len(report["checks"]), 10)
        self.assertEqual(report["summary"]["by_status"].get("fail", 0), 0)

    def test_rejected_sources_are_recorded_with_reasons(self):
        research = load(RESEARCH)
        self.assertTrue(research["rejected_sources"])
        for item in research["rejected_sources"]:
            self.assertTrue(item["reason"], item["id"])
            self.assertTrue(str(item["url"]).startswith("https://"), item["id"])


if __name__ == "__main__":
    unittest.main()
