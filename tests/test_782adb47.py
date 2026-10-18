"""Session 782adb47 finals desk: arithmetic, coverage and honesty gates.

Every published probability must re-derive from its retained decimals or Valve
points; every canonical open fixture must appear exactly once; crowd ownership
must never enter a probability; unresolved/blank semantics must hold.
"""
import json
import math
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


Q = math.log(10) / 400.0
G = 1.0 / math.sqrt(1.0 + 3.0 * Q ** 2 * 75.0 ** 2 / math.pi ** 2)
C = G * math.log(10) / 400.0


def vrs(pa, pb, k=0.4213):
    return 1.0 / (1.0 + math.exp(-(k * C * (pa - pb))))


def devig(decimal_a, decimal_b):
    ia, ib = 1.0 / float(decimal_a), 1.0 / float(decimal_b)
    return ia / (ia + ib)


def recalibrated_from_raw_vrs(p_raw, k=0.4213):
    """Apply the calibrated slope to a retained k=1 VRS probability."""
    p_raw = float(p_raw)
    if not 0.0 < p_raw < 1.0:
        raise ValueError("raw VRS probability must be strictly between zero and one")
    logit_raw = math.log(p_raw / (1.0 - p_raw))
    return 1.0 / (1.0 + math.exp(-(k * logit_raw)))


class FinalsBoard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board = load("finals/data/board.json")
        cls.canon = load("data/c64a5e19/board.json")
        cls.research = load("data/782adb47/research.json")

    def test_inventory_is_unique_and_reconciles_only_to_identical_capture(self):
        rows = self.board["rows"]
        ids = [str(r["fixture_id"]) for r in rows]
        self.assertEqual(len(ids), len(set(ids)), "finals rows must not duplicate a fixture")

        locked_count = sum(bool(r["locked"]) for r in rows)
        self.assertEqual(self.board["summary"]["open"], len(rows) - locked_count)
        self.assertEqual(self.board["summary"]["locked_since_capture"], locked_count)

        # The canonical board refreshes independently of this retained desk. Compare
        # inventories only when both documents carry the exact same source capture;
        # fixture rotations and lock transitions must not rewrite historical rows.
        if self.board.get("canonical_capture") == self.canon.get("generated_utc"):
            want = {str(r["fixture_id"]) for r in self.canon["open"]}
            self.assertEqual(set(ids), want)

    def test_pick_is_argmax_and_probs_sum_to_one(self):
        for r in self.board["rows"]:
            if r["prob_a"] is None:
                self.assertIsNone(r["pick"], r["fixture_id"])
                continue
            self.assertAlmostEqual(r["prob_a"] + r["prob_b"], 1.0, places=9)
            want = r["team_a"] if r["prob_a"] >= r["prob_b"] else r["team_b"]
            self.assertEqual(r["pick"], want, r["fixture_id"])
            self.assertAlmostEqual(r["pick_prob"], max(r["prob_a"], r["prob_b"]), places=9)

    def test_market_rows_rederive_from_retained_decimals(self):
        for r in self.board["rows"]:
            if r["basis"] != "market":
                continue
            # The finals row retains fixture-oriented decimals from the exact
            # capture used to publish its probability. Do not borrow quotes from
            # the independently refreshed canonical board, where prices may move.
            probs = []
            for q in r.get("quotes", []):
                if q.get("no_vig_prob_team_a") is not None:
                    probs.append(float(q["no_vig_prob_team_a"]))
                    continue
                da, db = q.get("decimal_a"), q.get("decimal_b")
                self.assertIsNotNone(da, f"{r['fixture_id']} retained quote missing decimal_a")
                self.assertIsNotNone(db, f"{r['fixture_id']} retained quote missing decimal_b")
                self.assertGreater(float(da), 1.0, r["fixture_id"])
                self.assertGreater(float(db), 1.0, r["fixture_id"])
                probs.append(devig(float(da), float(db)))
            self.assertTrue(probs, f"{r['fixture_id']} market row has no retained two-sided quote")
            self.assertAlmostEqual(r["prob_a"], sum(probs) / len(probs), places=3,
                                   msg=r["fixture_id"])

    def test_alias_join_math_and_proof_present(self):
        r = next(x for x in self.board["rows"] if x["basis"] == "alias")
        # Melbet WhiteBIT 1.72 / Nexus 2.00, swapped onto Nexus (a) v WROTBERRY (b)
        ia, ib = 1 / 1.72, 1 / 2.0
        self.assertAlmostEqual(r["prob_b"], ia / (ia + ib), places=6)
        self.assertIn("5/5 roster", r["note"])
        self.assertTrue(any("hltv.org" in s["url"] for s in r["sources"]))

    def test_stale_quote_labelled_and_rederives(self):
        r = next(x for x in self.board["rows"] if x["basis"] == "stale")
        ia, ib = 1 / 2.279, 1 / 1.57
        self.assertAlmostEqual(r["prob_a"], ia / (ia + ib), places=6)
        self.assertIn("STALE", r["basis_label"])
        self.assertIn("12:09", r["basis_label"] + (r["note"] or ""))

    def test_model_and_bound_math(self):
        floor_pts = self.research["vrs_floor"]["points"]
        canon = {str(x["fixture_id"]): x for x in self.canon["open"]}
        same_capture = self.board.get("canonical_capture") == self.canon.get("generated_utc")
        models = {m["fixture_id"]: m for m in self.research["model_rows"]}
        bounds = {b["fixture_id"]: b for b in self.research["bound_rows"]}
        for r in self.board["rows"]:
            if r["basis"] == "model" and r["fixture_id"] in models:
                m = models[r["fixture_id"]]
                self.assertAlmostEqual(r["prob_a"], vrs(m["points_a"], m["points_b"]), places=6)
            elif r["basis"] == "model" and same_capture:
                # On a matching capture, re-derive directly from that capture's
                # retained Valve points. A different capture may have rotated this
                # fixture out, or refreshed its inputs, so never join across reads.
                self.assertIn(r["fixture_id"], canon, r["fixture_id"])
                v = canon[r["fixture_id"]]["vrs"]
                self.assertTrue(v.get("team_a") and v.get("team_b"), r["fixture_id"])
                self.assertAlmostEqual(
                    r["prob_a"], vrs(v["team_a"]["points"], v["team_b"]["points"]),
                    places=6, msg=r["fixture_id"])
            elif r["basis"] == "model":
                # The finals row retains the canonical k=1 probability alongside
                # its calibrated output. Reapply k=0.4213 on that retained input
                # when the matching source fixture is no longer in the current
                # canonical inventory; do not substitute a newer row or KeyError.
                raw = r.get("canonical_prob_a")
                self.assertIsNotNone(raw, f"{r['fixture_id']} missing retained canonical model input")
                # The canonical probability is stored to four decimals; allow the
                # corresponding rounding error after applying the logit slope.
                self.assertAlmostEqual(r["prob_a"], recalibrated_from_raw_vrs(raw),
                                       places=4, msg=r["fixture_id"])
            elif r["basis"] == "bound":
                b = bounds[r["fixture_id"]]
                p_rated = vrs(b["points"], floor_pts)
                want = p_rated if b["rated_side"] == "a" else 1 - p_rated
                self.assertAlmostEqual(r["prob_a"], want, places=6, msg=r["fixture_id"])

    def test_day5_originated_lines_and_verdicts(self):
        d5 = {d["id"]: d for d in self.board["day5"]}
        self.assertAlmostEqual(d5["final"]["prob_a_cal"], vrs(1829, 1596), places=6)
        self.assertAlmostEqual(d5["final"]["prob_a_raw"], vrs(1829, 1596, 1.0), places=6)
        self.assertEqual(d5["final"]["safe_pick"], "FURIA")
        self.assertIn("NO CLIMB", d5["final"]["verdict"])
        self.assertAlmostEqual(d5["third"]["prob_a_cal"], vrs(1716, 1843), places=6)
        self.assertEqual(d5["third"]["safe_pick"], "Falcons")
        self.assertIn("CONDITIONAL CLIMB", d5["third"]["verdict"])
        for d in d5.values():
            self.assertIsNone(d["market"])  # no invented market price

    def test_twc_results_all_hltv_linked(self):
        self.assertEqual(len(self.research["twc_results"]), 12)
        for t in self.research["twc_results"]:
            self.assertTrue(t["url"].startswith("https://www.hltv.org/matches/"), t["url"])
        days = [t["day"] for t in self.research["twc_results"]]
        self.assertEqual((days.count(1), days.count(2), days.count(3), days.count(4)), (4, 4, 2, 2))

    def test_no_row_without_https_source(self):
        for r in self.board["rows"]:
            self.assertTrue(any(s["url"].startswith("https://") for s in r["sources"]),
                            r["fixture_id"])

    def test_crowd_never_equals_probability_input(self):
        # ownership values are whole percents; a probability exactly equal to crowd/100
        # on a bound/model row would suggest leakage. Market coincidence tolerated once.
        suspicious = [r["fixture_id"] for r in self.board["rows"]
                      if r["basis"] in ("model", "bound") and r["crowd_a"] is not None
                      and r["prob_a"] is not None and abs(r["prob_a"] - r["crowd_a"] / 100) < 1e-9]
        self.assertEqual(suspicious, [])

    def test_watchlist_respects_floor_and_never_switches_pick(self):
        for r in self.board["rows"]:
            if r.get("watch"):
                self.assertGreaterEqual(r["watch"]["prob"], 0.35)
                self.assertGreaterEqual(r["watch"]["leverage"], 0.15 - 1e-9)
                self.assertNotEqual(r["watch"]["team"], r["pick"])
            self.assertIsNone(r.get("climb"))  # no lobby row may auto-switch without verified flags


class FinalsPages(unittest.TestCase):
    def html(self, name):
        with open(os.path.join(ROOT, "finals", name), encoding="utf-8") as fh:
            return fh.read()

    def test_pages_exist_mobile_and_linked(self):
        for name in ("index.html", "picks.html", "twc.html", "unresolved.html",
                     "flagged.html", "method.html"):
            body = self.html(name)
            self.assertIn("viewport", body, name)
            self.assertIn("unresolved.html", body, name)
            self.assertIn("never HotSpawn", body, name)

    def test_summary_surfaces_unresolved_and_day5(self):
        body = self.html("index.html")
        self.assertIn("Unresolved summary", body)
        self.assertIn("FURIA", body)
        self.assertIn("SAFE PICK", body)
        self.assertIn("picks.html", body)

    def test_picks_page_has_card_per_open_row(self):
        board = load("finals/data/board.json")
        body = self.html("picks.html")
        for r in board["rows"]:
            self.assertIn(f'id="{r["fixture_id"]}"', body)

    def test_no_placeholder_odds_published_as_prices(self):
        for name in ("picks.html", "twc.html", "index.html"):
            self.assertNotIn("1.8/1.8", self.html(name).replace("1.8/1.8 widgets", ""))


if __name__ == "__main__":
    unittest.main()
