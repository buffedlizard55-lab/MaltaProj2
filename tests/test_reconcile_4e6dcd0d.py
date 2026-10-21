"""Tests for the RECONCILE-4E6 cross-board section (session 4e6dcd0d)."""
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import reconcile_4e6dcd0d as R  # noqa: E402


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
        self.viewport = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("name") == "viewport":
            self.viewport = True
        for k in ("href", "src"):
            if a.get(k):
                self.urls.append(a[k])


class ReconcileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "reconcile"
        cls.model = R.build(cls.out, write_json=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_probabilities_sum_and_pick_is_argmax(self):
        n = 0
        for f in self.model["fixtures"]:
            if f["consensus_p_a"] is None:
                self.assertIsNone(f["pick"])
                self.assertIsNone(f["consensus_p_b"])
                continue
            n += 1
            self.assertAlmostEqual(f["consensus_p_a"] + f["consensus_p_b"], 1.0, places=3)
            if f["pick"]:
                best = f["team_a"] if f["consensus_p_a"] > 0.5 else f["team_b"]
                self.assertEqual(f["pick"], best)
                self.assertAlmostEqual(f["pick_p"], max(f["consensus_p_a"], f["consensus_p_b"]), places=3)
            else:
                self.assertAlmostEqual(f["consensus_p_a"], 0.5, places=6)
        # Zero priced rows is valid during a source outage or after expiry.
        self.assertTrue(self.model['fixtures'], 'inventory must remain available')
        self.assertEqual(n, sum(bool(f['n_book_sources']) for f in self.model['fixtures']))

    def test_every_priced_fixture_has_eligible_sourced_quotes(self):
        for f in self.model["fixtures"]:
            if f["consensus_p_a"] is None:
                continue
            elig = [q for q in f["quotes"] if q["eligible"] and q["source"] in R.BOOKMAKER_KEYS]
            self.assertEqual(len(elig), f["n_book_sources"])
            for q in elig:
                self.assertTrue(urlsplit(q["url"] or "").scheme in ("http", "https"), f["fixture_id"])
                self.assertIsNotNone(q["retrieved_at_utc"])
                self.assertLessEqual(q["age_min"], R.MAX_QUOTE_AGE_MIN)
                if q["p_a_recomputed"] is not None:
                    self.assertAlmostEqual(q["p_a"], q["p_a_recomputed"], delta=0.002)
            mean = sum(q["p_a"] for q in elig) / len(elig)
            self.assertAlmostEqual(f["consensus_p_a"], mean, delta=0.0006)

    def test_kalshi_never_enters_consensus(self):
        self.assertNotIn("kalshi", R.BOOKMAKER_KEYS)
        for f in self.model["fixtures"]:
            if f["consensus_p_a"] is not None:
                self.assertTrue(all(q["source"] != "kalshi" for q in f["quotes"] if q["eligible"] and q["source"] in R.BOOKMAKER_KEYS))

    def test_hotspawn_crowd_percent_never_read(self):
        code = (ROOT / "scripts" / "reconcile_4e6dcd0d.py").read_text()
        self.assertNotIn("pick_pct", code)
        self.assertNotIn("total_picks", code)
        blob = repr(self.model)
        self.assertNotIn("pick_pct", blob)

    def test_open_means_future_lock_and_scheduled(self):
        for f in self.model["fixtures"]:
            if f["open"]:
                self.assertEqual(f["status"], "scheduled")
                self.assertGreater(f["lock_utc"], self.model["generated_at_utc"])

    def test_normalisation_and_devig(self):
        self.assertEqual(R.norm("Grêmio"), R.norm("Gremio"))
        self.assertAlmostEqual(R.no_vig_a(1.5, 3.0), (1 / 1.5) / (1 / 1.5 + 1 / 3.0))
        self.assertAlmostEqual(R.no_vig_a(2.0, 2.0), 0.5)

    def test_pages_mobile_and_links(self):
        pages = sorted(self.out.glob("*.html"))
        self.assertEqual({p.name for p in pages}, {n for n, _ in R.NAV})
        for p in pages:
            parser = Links()
            parser.feed(p.read_text(encoding="utf-8"))
            self.assertTrue(parser.viewport, p.name)
            for u in parser.urls:
                sp = urlsplit(u)
                if sp.scheme or u.startswith("#"):
                    continue
                if u.startswith("../"):
                    continue  # cross-section links are validated by scripts/stage_site.py on the staged artifact
                self.assertTrue((self.out / sp.path).exists(), f"{p.name} -> {u}")

    def test_unpriced_rows_are_blank_with_official_link(self):
        txt = (self.out / "unpriced.html").read_text(encoding="utf-8")
        # Zero unpriced rows is valid. Check source + blanks on each actual data row.
        import re
        for row in re.findall(r"<tr>.*?</tr>", txt.split("<tbody>")[1], re.S):
            self.assertRegex(row, r'href="https://(?:www\.hotspawn\.com/matches/|play\.hotspawn\.com/lobby)')
            self.assertNotIn("%</td>", row)

    def test_identical_two_sided_price_is_never_a_line(self):
        for f in self.model["fixtures"]:
            for q in f["quotes"]:
                if q["decimal_a"] is not None and q["decimal_a"] == q["decimal_b"]:
                    self.assertFalse(q["eligible"])
            if f["consensus_p_a"] is not None:
                self.assertNotEqual(f["consensus_p_a"], 0.5)

    def test_cancelled_rows_have_no_pick(self):
        for f in self.model["fixtures"]:
            if f["cancelled"]:
                self.assertIsNone(f["pick"])


if __name__ == "__main__":
    unittest.main()
