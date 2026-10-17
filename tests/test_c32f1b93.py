"""Session c32f1b93 — invariants for the independent re-derivation board.

These tests read committed files only (no network). They fail if:
  * a core primitive (no-vig, VRS probability, slope fit, Elo) misbehaves,
  * a published probability stops being re-derivable from its stored inputs,
  * a row loses its evidence link, if the crowd share leaks into a price,
  * the VRS duplicate-name rule or the live Oct-16 overrides regress,
  * the single BLANK fixture loses its attempt ledger, or
  * an audit page loses a fixture row or a working internal link.
"""
from __future__ import annotations

import json
import math
import os
import re
import statistics
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Load this session's core under a unique module name: several sessions'
# test files do a bare `import core` against their own scripts/<session>/
# directory, and a plain import would poison sys.modules['core'] for the
# tests that run after ours (unique-name loading is the repo convention,
# see tests/test_1c8f79f8.py).
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "core_c32f1b93", os.path.join(ROOT, "scripts", "c32f1b93", "core.py"))
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)

DATA = os.path.join(ROOT, "data", "c32f1b93")
AUDITS = os.path.join(ROOT, "audits", "c32f1b93")
BOARD_PATH = os.path.join(DATA, "board.json")


def load_board():
    with open(BOARD_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def load_research():
    with open(os.path.join(DATA, "research.json"), encoding="utf-8") as fh:
        return json.load(fh)


class CoreTests(unittest.TestCase):
    def test_norm_strips_org_words_and_is_accent_insensitive(self):
        self.assertEqual(core.norm("FURIA Esports"), "furia")
        self.assertEqual(core.norm("Ninjas in Pyjamas"), "ninjasinpyjamas")
        self.assertEqual(core.norm("Sökerorg"), "sokerorg")
        self.assertEqual(core.norm("The team"), "team")  # prefix 'the' stripped only when >1 token
        self.assertNotEqual(core.norm("B8"), core.norm("B8 Academy"))

    def test_canon_applies_documented_aliases(self):
        key, applied, note = core.canon("WROTBERRY")
        self.assertEqual(key, "wbt")
        self.assertTrue(applied and note)
        key, _, _ = core.canon("BB Team")
        self.assertEqual(key, "betboom")
        key, _, _ = core.canon("LFO 10")
        self.assertEqual(key, "sokerorg")

    def test_alias_evidence_is_real_urls(self):
        for entry in core.ALIASES.values():
            for url in entry["evidence"]:
                self.assertTrue(url.startswith("http"), url)

    def test_devig_is_proportional_and_symmetric(self):
        pa, pb = core.devig(2.0, 2.0)
        self.assertAlmostEqual(pa, 0.5)
        self.assertAlmostEqual(pa + pb, 1.0)
        pa2, pb2 = core.devig(1.5, 3.0)
        self.assertAlmostEqual(pa2 + pb2, 1.0)
        self.assertAlmostEqual(pa2, 1 - pb2)

    def test_sigmoid_logit_roundtrip(self):
        for p in (0.01, 0.25, 0.5, 0.77, 0.99):
            self.assertAlmostEqual(core.sigmoid(core.logit(p)), p, places=6)

    def test_vrs_prob_is_valves_glicko_curve(self):
        # delta 0 -> exactly 50%; monotone in the delta; symmetric.
        self.assertAlmostEqual(core.vrs_prob(1000, 1000, k=1.0), 0.5, places=9)
        self.assertGreater(core.vrs_prob(1100, 1000, k=1.0),
                           core.vrs_prob(1050, 1000, k=1.0))
        self.assertAlmostEqual(core.vrs_prob(1100, 1000, k=1.0),
                               1 - core.vrs_prob(1000, 1100, k=1.0), places=9)
        # Valve's documented anchor: 400 pt ~ 90% at k=1, default RD=75
        # (exact value 0.9090; the README rounds to "90%").
        self.assertAlmostEqual(core.vrs_prob(1400, 1000, k=1.0), 0.9038, places=3)

    def test_fit_slope_recovers_known_k(self):
        pairs = []
        for delta in (-300, -120, -40, 10, 65, 150, 260, 420, 700):
            p = core.vrs_prob(1000 + delta, 1000, k=0.275)
            pairs.append({"delta": delta, "market_prob_a": p})
        fit = core.fit_slope(pairs)
        self.assertAlmostEqual(fit["k"], 0.275, delta=0.02)
        self.assertFalse(fit["clamped"])
        self.assertLess(fit["mae_prob"], 1e-6)

    def test_fit_slope_clamps_out_of_band_and_flags(self):
        steep = [{"delta": d, "market_prob_a": core.vrs_prob(1000 + d, 1000, k=3.0)}
                 for d in (-400, -150, -50, 60, 200, 500, 900)]
        fit = core.fit_slope(steep)
        self.assertTrue(fit["clamped"])
        self.assertEqual(fit["k"], core.FIT_BOUNDS[1])

    def test_fit_slope_refuses_few_pairs(self):
        fit = core.fit_slope([{"delta": 100, "market_prob_a": 0.6}])
        self.assertIsNone(fit["k_raw"])
        self.assertEqual(fit["k"], 1.0)

    def test_elo_expected_and_run_are_deterministic(self):
        self.assertAlmostEqual(core.elo_expected(1500, 1500), 0.5)
        matches = [
            {"key_a": "a", "key_b": "b", "winner": "a", "start_utc": "2026-01-01", "match_id": 1},
            {"key_a": "b", "key_b": "c", "winner": "b", "start_utc": "2026-01-02", "match_id": 2},
            {"key_a": "a", "key_b": "c", "winner": "c", "start_utc": "2026-01-03", "match_id": 3},
        ]
        seed = {"a": 1200.0, "b": 1100.0, "c": 1000.0, "d": 999.0}
        r1 = core.elo_run(matches, seed=seed)
        r2 = core.elo_run(matches, seed=seed)
        self.assertEqual(r1, r2)
        # a seeded team with no recorded matches keeps its Valve anchor
        self.assertAlmostEqual(r1["d"], 999.0, places=6)
        self.assertIn("a", r1) and self.assertIn("b", r1) and self.assertIn("c", r1)

    def test_parse_vrs_file_reads_the_retained_ladder(self):
        table = core.parse_vrs_file(os.path.join(DATA, "vrs_global_2026_10_05.md"))
        teams = table["teams"]
        self.assertGreaterEqual(sum(len(v) for v in teams.values()), 380)
        # duplicate-name keys exist and the main roster is the lowest-standing row
        dupes = {k: v for k, v in teams.items() if len(v) > 1}
        self.assertGreaterEqual(len(dupes), 25)
        for key, rows in dupes.items():
            standings = [r["standing"] for r in rows]
            main = min(rows, key=lambda r: r["standing"])
            self.assertEqual(main["standing"], min(standings), key)


class BoardContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load_board()
        cls.rows = {r["fixture_id"]: r for r in cls.board["open"]}
        cls.research = load_research()

    def test_inventory_and_line_mix(self):
        s = self.board["summary"]
        self.assertEqual(s["open_fixtures"], 35)
        self.assertEqual(s["with_market_line"], 20)
        self.assertEqual(s["model_only_line"], 14)
        self.assertEqual(s["blank_unresolved"], 1)
        self.assertEqual(len(self.board["open"]), 35)

    def test_confidence_bands_match_published_probabilities(self):
        for r in self.board["open"]:
            if not r.get("line"):
                self.assertEqual(r["confidence"], "Unresolved")
                continue
            p = r["pick_probability"]
            conf = r["confidence"]
            if p >= 0.65:
                self.assertEqual(conf, "Strong", r["fixture_id"])
            elif p >= 0.60:
                self.assertEqual(conf, "Solid", r["fixture_id"])
            elif p >= 0.55:
                self.assertEqual(conf, "Lean", r["fixture_id"])
            else:
                self.assertEqual(conf, "Toss-up", r["fixture_id"])
            self.assertAlmostEqual(max(r["line"]["prob_a"], r["line"]["prob_b"]),
                                   p, places=6)

    def test_market_medians_rederive_from_stored_quotes(self):
        for r in self.board["open"]:
            if not r.get("market"):
                continue
            pas = [q["prob_a"] for q in r["quotes"]]
            self.assertGreaterEqual(len(pas), 1, r["fixture_id"])
            self.assertAlmostEqual(round(statistics.median(pas), 6),
                                   r["market"]["prob_a"], places=6,
                                   msg=r["fixture_id"])
            for q in r["quotes"]:
                self.assertIn("source_key", q)
                self.assertIn("public_url", q)

    def test_blend_arithmetic_rederives_every_published_line(self):
        for r in self.board["open"]:
            line = r.get("line")
            if not line:
                continue
            if r["market"] and r["model"]:
                expect = (0.85 * r["market"]["prob_a"] + 0.15 * r["model"]["prob_a"])
                self.assertAlmostEqual(expect, line["prob_a"], places=6, msg=r["fixture_id"])
                self.assertEqual(line["basis"], "market+model")
            elif r["market"]:
                self.assertEqual(line["basis"], "market")
                self.assertAlmostEqual(r["market"]["prob_a"], line["prob_a"], places=6)
            else:
                self.assertEqual(line["basis"], "model")
                self.assertAlmostEqual(r["model"]["prob_a"], line["prob_a"], places=6)

    def test_semifinal_one_uses_live_ladder_and_seven_sources(self):
        r = self.rows["1080207"]
        self.assertEqual(r["pick"], "FURIA")
        self.assertEqual(r["market"]["n_sources"], 7)
        self.assertEqual(r["model"]["vrs"]["points_a"], 1827.0)   # live AM #1
        self.assertEqual(r["model"]["vrs"]["points_b"], 1848.0)   # live EU #5
        self.assertEqual(r["model"]["vrs"]["delta"], -21.0)
        self.assertIn("twc_semifinal", r["flags"])
        self.assertIn("live_vrs_override", r["flags"])
        # the model leans Aurora while the market leans FURIA: both published
        self.assertLess(r["model"]["prob_a"], 0.5)
        self.assertGreater(r["market"]["prob_a"], 0.5)

    def test_semifinal_two_backs_falcons_strong(self):
        r = self.rows["1080208"]
        self.assertEqual(r["pick"], "Falcons")
        self.assertGreaterEqual(r["pick_probability"], 0.65)
        self.assertEqual(r["model"]["vrs"]["points_a"], 1880.0)
        self.assertEqual(r["model"]["vrs"]["points_b"], 1619.0)

    def test_calibration_is_our_own_fit_and_beats_the_prior_board(self):
        cal = self.board["calibration"]
        self.assertEqual(cal["n_pairs"], 19)
        self.assertGreaterEqual(cal["n_pairs"], cal["min_pairs"])
        self.assertFalse(cal["clamped"])
        self.assertTrue(cal["bounds"][0] <= cal["k"] <= cal["bounds"][1])
        self.assertLess(cal["mae_prob"], 0.1002)  # fe803b80's published MAE
        for p in cal["pairs"]:
            self.assertIn("delta", p)
            self.assertIn("market_prob_a", p)

    def test_duplicate_name_joins_use_verified_rows(self):
        # Betclic: the current five (Demho, ex1st, Prism, Qlocuu, ultimate),
        # not the stale hades-era row that poisoned the prior board.
        r = self.rows["1081515"]
        self.assertIn("stale_row_corrected", r["flags"])
        self.assertIn("row #45", r["model"]["vrs"]["join_a"])
        self.assertEqual(r["model"]["vrs"]["points_a"], 1232.0)  # live, not 765/1333
        # Just Players: wh1teout lineage, live 1002 pt
        r = self.rows["1079170"]
        self.assertEqual(r["model"]["vrs"]["points_b"], 1002.0)
        # ex-RUSTEC: active #92 lineage, live 1072 pt
        r = self.rows["1081517"]
        self.assertEqual(r["model"]["vrs"]["points_b"], 1072.0)
        self.assertIn("stale_row_corrected", r["flags"])

    def test_ex_rustec_pick_flips_and_sokerorg_is_ladder_fresh(self):
        self.assertEqual(self.rows["1079638"]["pick"], "ex-RUSTEC")
        self.assertEqual(self.rows["1079638"]["model"]["vrs"]["delta"], 172.0)
        r = self.rows["1079634"]
        self.assertEqual(r["pick"], "Lavked")  # live 855 vs LFO 10's 787
        self.assertIn("alias_applied", r["flags"])

    def test_blank_policy_holds_for_chinggis_wxm(self):
        r = self.rows["1081863"]
        self.assertIsNone(r["line"])
        self.assertIn("policy_blank", r["flags"])
        un = [u for u in self.board["unresolved"] if u["fixture_id"] == "1081863"][0]
        self.assertGreaterEqual(len(un["attempt_ledger"]), 8)
        self.assertIn("Chinggis Warriors", un["directional_pick"])
        self.assertIn("never presented as a percentage", un["policy"])

    def test_placeholder_scheduling_fixture_is_flagged_not_hidden(self):
        r = self.rows["1080200"]
        self.assertIn("placeholder_scheduling", r["flags"])
        self.assertIn("far_future_scheduling", r["flags"])
        self.assertEqual(r["model"]["vrs"]["points_a"], 1332.0)  # Wildcard live
        self.assertEqual(r["model"]["vrs"]["points_b"], 1355.0)  # DENDELE live

    def test_crowd_share_never_enters_a_probability(self):
        for r in self.board["open"]:
            crowd = r.get("crowd")
            if crowd:
                self.assertEqual(set(crowd) - {"matchup_mapped_from_ledger_fixture_id"},
                                 {"team_a", "team_b", "crowd_a", "crowd_b",
                                  "total_picks", "read_utc", "role"}, r["fixture_id"])
                self.assertEqual(crowd["role"], "context only - sentiment, never a price")
        # and the contrarian screen actually fired this session
        climbs = [r for r in self.board["open"]
                  if str(r.get("role", "")).startswith("climb")]
        self.assertGreaterEqual(len(climbs), 2)

    def test_every_row_carries_evidence_or_a_declared_basis(self):
        for r in self.board["open"]:
            self.assertTrue(r.get("sources") or r.get("model"), r["fixture_id"])
            if r.get("market"):
                self.assertGreaterEqual(len(r["quotes"]), 1)

    def test_corrections_ledger_covers_the_prior_board(self):
        titles = " ".join(c["title"] for c in self.board["corrections"])
        for needle in ("ex-RUSTEC", "Chinggis", "WROTBERRY", "slope", "Nuke"):
            self.assertIn(needle, titles)

    def test_rebuild_is_byte_reproducible(self):
        # build.py must re-emit the identical board (minus the build stamp).
        out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "c32f1b93", "build.py")],
                             capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        fresh = load_board()
        for section in ("open", "unresolved", "corrections", "calibration", "twc", "rules"):
            self.assertEqual(json.dumps(fresh[section], sort_keys=True),
                             json.dumps(self.board[section], sort_keys=True), section)


class AuditPageTests(unittest.TestCase):
    PAGES = ("index.html", "twc-day4.html", "unresolved.html",
             "flagged.html", "method.html")

    @classmethod
    def setUpClass(cls):
        cls.board = load_board()

    def test_all_six_artifacts_exist(self):
        for name in self.PAGES + ("style.css",):
            self.assertTrue(os.path.exists(os.path.join(AUDITS, name)), name)
            self.assertGreater(os.path.getsize(os.path.join(AUDITS, name)), 500, name)

    def test_index_carries_every_fixture_and_the_headline_picks(self):
        text = open(os.path.join(AUDITS, "index.html"), encoding="utf-8").read()
        for r in self.board["open"]:
            self.assertIn(r["fixture_id"], text, r["fixture_id"])
        self.assertIn("FURIA", text)
        self.assertIn("Thunderpick World Championship", text)
        self.assertIn("k = 0.4970", text)

    def test_twc_page_carries_both_semis_and_the_verified_results(self):
        text = open(os.path.join(AUDITS, "twc-day4.html"), encoding="utf-8").read()
        for needle in ("FURIA", "Aurora", "Falcons", "BETBOOM", "THE DAY-1 UPSET",
                       "2399414", "2399415", "13-1"):
            self.assertIn(needle, text, needle)

    def test_method_page_publishes_the_full_fit(self):
        text = open(os.path.join(AUDITS, "method.html"), encoding="utf-8").read()
        flat = re.sub(r"\s+", " ", text)
        start = text.index('id="calibration-pairs"')
        stop = text.index("</table>", start)
        self.assertEqual(text.count("<tr>", start, stop) - 1, 19)  # header + 19 pairs
        for needle in ("least squares through the origin", "RD = 75",
                       "k = 0.4970", "0.85 market / 0.15 model"):
            self.assertIn(needle, flat, needle)

    def test_unresolved_page_ledger_the_blank(self):
        text = open(os.path.join(AUDITS, "unresolved.html"), encoding="utf-8").read()
        self.assertIn("1081863", text)
        self.assertIn("Attempt ledger", text)
        self.assertIn("placeholder_scheduling", text)

    def test_flagged_page_groups_every_flag(self):
        text = open(os.path.join(AUDITS, "flagged.html"), encoding="utf-8").read()
        raised = set()
        for r in self.board["open"]:
            raised.update(r["flags"])
        for flag in sorted(raised):
            self.assertIn(flag, text, flag)

    def test_internal_links_resolve(self):
        for name in self.PAGES:
            text = open(os.path.join(AUDITS, name), encoding="utf-8").read()
            for href in re.findall(r'href="([^"#]+?)"', text):
                if href.startswith("http"):
                    continue
                self.assertTrue(os.path.exists(os.path.join(AUDITS, href)),
                                (name, href))

    def test_no_template_artifacts_leak(self):
        for name in self.PAGES:
            text = open(os.path.join(AUDITS, name), encoding="utf-8").read()
            for artifact in ("{esc(", "{pct(", "{cal[", "{r[", "None</"):
                self.assertNotIn(artifact, text, (name, artifact))


if __name__ == "__main__":
    unittest.main()
