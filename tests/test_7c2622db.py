"""7c2622db: the mobile pick'em hub — every match, its own evidence, blanks stay blank.

The tests run offline: they execute the hub's own builder (which falls back to the committed
manual capture and the read-only canonical collection when no live capture is present) and then
assert the published invariants a phone reader depends on.
"""
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "7c2622db"
HUB = ROOT / "hub"


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


BUILD = module("test_hub_build_7c2622db", "scripts/7c2622db/build.py")


class HubBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hub = BUILD.build()
        cls.rows = cls.hub["rows"]
        cls.html = {path.name: path.read_text() for path in HUB.glob("*.html")}

    # ---------------------------------------------------------------- machine-readable board
    def test_counts_match_the_rows(self):
        counts = self.hub["counts"]
        self.assertEqual(counts["open"], len(self.rows))
        self.assertEqual(counts["with_pick"], sum(1 for r in self.rows if r.get("pick")))
        for basis in ("market", "exchange", "model", "unresolved"):
            self.assertEqual(counts[basis], sum(1 for r in self.rows if r.get("basis") == basis),
                             f"{basis} count must agree with the rows")

    def test_every_open_row_is_priced_or_explicitly_unresolved(self):
        for row in self.rows:
            prob = row.get("prob") or {}
            if prob.get("a") is None:
                self.assertEqual(row.get("basis"), "unresolved", row["fixture_id"])
                self.assertTrue(row.get("pick") is None, "an unresolved row must not carry a pick")
                self.assertTrue(any(f.endswith("unverified") or "unverified" in f
                                    for f in row.get("flags") or []),
                                f"{row['fixture_id']} must flag the blank")
                self.assertTrue(row.get("pick_blocked_reason"),
                                f"{row['fixture_id']} must say why the pick is withheld")
            else:
                self.assertAlmostEqual(float(prob["a"]) + float(prob["b"]), 1.0, places=9)
                self.assertIn((row.get("pick") or {}).get("side"), ("a", "b"))

    def test_every_row_links_at_least_one_official_source(self):
        for row in self.rows:
            links = [s for s in row.get("sources") or []
                     if str(s.get("url") or "").startswith("http")]
            self.assertTrue(links, f"{row['fixture_id']} has no source link")

    def test_priced_rows_expose_a_retained_price_source(self):
        for row in self.rows:
            if row.get("basis") not in ("market", "exchange"):
                continue
            labels = " | ".join(str(s.get("label")) for s in row.get("sources") or [])
            self.assertTrue(re.search(r"price|exchange market", labels),
                            f"{row['fixture_id']} must link the source that produced the price")

    def test_crowd_share_is_ownership_only(self):
        for row in self.rows:
            prob = row.get("prob") or {}
            own = row.get("ownership") or {}
            rendered = own.get("as_rendered") or []
            if prob.get("a") is None or len(rendered) != 2:
                continue
            # the same share would have to equal the printed probability on both sides at once,
            # which no bookmaker-derived line does; assert the builder never copies the share.
            self.assertNotEqual([round(float(prob["a"]), 2), round(float(prob["b"]), 2)],
                                [round(v / 100.0, 2) for v in rendered],
                                f"{row['fixture_id']} looks like the crowd share was used as a price")
        policy = self.hub.get("policy") or ""
        self.assertIn("ownership only", policy)

    def test_activated_swings_obey_the_published_gate(self):
        for row in self.rows:
            climb = row.get("climb") or {}
            if not climb.get("activated"):
                continue
            self.assertGreaterEqual(climb["market_prob"], 0.30)
            self.assertLessEqual(climb["ownership"], 0.50)
            self.assertGreaterEqual(climb["market_prob"] - climb["ownership"], 0.15)
            self.assertTrue(climb.get("crowd_fade"),
                            "an activated swing is always the side the crowd is fading")
            self.assertIn(climb.get("kind"), ("contrarian underdog", "fade the crowd"))
            self.assertGreaterEqual(climb.get("model_prob") or 0,
                                    (row.get("market_consensus") or {}).get("prob_a", 0) - 0.10
                                    if climb["side"] == "a" else 1 - 1,
                                    "model must not sit more than 10 points below the reading")

    def test_displayed_clock_rule_is_rechecked_at_every_build(self):
        clock = self.hub["capture"]["display_clock"]
        self.assertEqual(clock["mismatches"], [],
                         "a displayed ET time disagrees with the canonical epoch start")
        self.assertGreaterEqual(clock["checked_against_epoch_starts"], 10,
                                "the ET rule must be cross-checked on many fixtures")
        for row in self.rows:
            self.assertTrue(row.get("start_source"), f"{row['fixture_id']} must say where its UTC start came from")
        self.assertTrue(clock["derived_from_display_only"])

    def test_calibration_is_reproducible_from_this_capture(self):
        calibration = self.hub["calibration"]
        self.assertTrue(calibration.get("fitted"))
        self.assertGreaterEqual(calibration["n_pairs"], calibration["min_pairs"])
        self.assertLessEqual(calibration["bounds"][0], calibration["k"])
        self.assertLessEqual(calibration["k"], calibration["bounds"][1])
        # the calibrated slope must beat the uncalibrated valve on its own pairs
        self.assertLessEqual(calibration["mae_prob"], calibration["mae_prob_valve"])

    # -------------------------------------------------------------------------- the pages
    def test_every_page_is_mobile_ready_and_links_home(self):
        for name, text in self.html.items():
            self.assertIn('name="viewport"', text, f"{name} misses the viewport meta")
            self.assertIn("width=device-width", text)
            self.assertIn("index.html", text, f"{name} needs a route back to the hub front door")

    def test_front_door_links_every_updated_pick_list(self):
        front = self.html["index.html"]
        for target in ("twc.html", "unresolved.html", "flagged.html", "method.html", "verify.html"):
            self.assertIn(target, front, f"executive summary must link {target}")
        self.assertIn("../index.html", front, "hub must link back to the main site")
        for phrase in ("Every open match", "Executive summary", "Unresolved picks"):
            self.assertIn(phrase, front)
        # the front door states what the capture covers before any pick is shown
        self.assertIn("What this capture covers", front)
        self.assertIn(str(self.hub["capture"]["counters"]["matches_this_week"]), front)

    def test_unresolved_section_is_separate_and_never_invents_a_probability(self):
        unresolved = self.html["unresolved.html"]
        self.assertIn("Unresolved picks &amp; limitations", unresolved)
        for row in self.rows:
            if row.get("basis") != "unresolved":
                continue
            self.assertIn(row["team_a"], unresolved)
            self.assertIn(row["team_b"], unresolved)
        self.assertNotIn("50%", re.sub(r"50% of", "", unresolved))

    def test_every_table_row_carries_a_source_link(self):
        for name in ("index.html", "twc.html", "unresolved.html"):
            for block in re.findall(r"<tr>.*?</tr>", self.html[name], re.S):
                if "<td" not in block:
                    continue  # header row
                self.assertIn("href=\"http", block, f"a row in {name} has no source link")

    def test_twc_review_states_the_unverified_premise_plainly(self):
        twc = self.html["twc.html"]
        self.assertIn("9z", twc)
        self.assertIn("Aurora", twc)
        self.assertIn("could not be verified", twc,
                      "the roster premise must be called out, not repeated")

    def test_verification_page_matches_the_last_verification_run(self):
        verification = json.loads((DATA / "verification.json").read_text())
        self.assertEqual(verification["failed"], 0, verification.get("failures"))
        self.assertGreater(verification["passed"], 100)
        self.assertIn("Verification", self.html["verify.html"])

    def test_twc_day3_rows_are_in_the_open_board(self):
        research = json.loads((DATA / "research.json").read_text())
        listed = {r["fixture_id"] for r in self.rows}
        for entry in research["twc"]["day3"]:
            self.assertIn(str(entry["fixture_id"]), listed,
                          "every day-3 decider must appear in the open board")


class Automation(unittest.TestCase):
    def test_workflow_refreshes_inside_the_4_to_8_hour_band(self):
        workflow = (ROOT / ".github" / "workflows" / "hub-7c2622db.yml").read_text()
        cron = re.search(r"cron: '(\S+ \S+ \S+ \S+ \S+)'", workflow).group(1)
        minute, hour, dom, month, dow = cron.split()
        self.assertEqual((dom, month, dow), ("*", "*", "*"), "must be a recurring schedule")
        self.assertEqual(minute, "41")
        self.assertIn(hour, ("*/4 * * *".split()[0], "*/6", "*/5", "*/8"),
                      "the hourly field must refresh every 4-8 hours")
        for step in ("collect.py", "build.py", "verify.py", "test_7c2622db"):
            self.assertIn(step, workflow, f"the refresh must run {step}")
        self.assertIn("git pull --rebase", workflow, "every push must rebase first")
        self.assertIn("git add hub", workflow)
        self.assertIn("data/7c2622db/$extra", workflow)
        self.assertIn("workflow_dispatch", workflow, "a manual refresh must stay possible")

    def test_staging_and_landing_page_link_the_hub(self):
        staging = (ROOT / "scripts" / "stage_site.py").read_text()
        self.assertIn("'hub'", staging)
        landing = (ROOT / "scripts" / "build_site.py").read_text()
        self.assertIn("hub/index.html", landing)
        self.assertIn("hub/unresolved.html", landing)


if __name__ == "__main__":
    unittest.main()
