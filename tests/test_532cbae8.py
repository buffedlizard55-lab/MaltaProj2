"""Integration contract for the mobile TWC 2026 pick entry points."""
from pathlib import Path
import unittest

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]


class MobileTWCEntryPointTests(unittest.TestCase):
    def test_landing_summary_links_to_current_picks_and_limitations(self):
        soup = BeautifulSoup((ROOT / "index.html").read_text(encoding="utf-8"), "html.parser")
        self.assertIsNotNone(soup.select_one('meta[name="viewport"][content*="width=device-width"]'))
        summary = soup.select_one("#executive-summary")
        self.assertIsNotNone(summary, "the landing page must have a clearly named executive summary")

        hrefs = {anchor.get("href") for anchor in summary.select("a[href]")}
        required = {
            "day5/picks.html",
            "day5/twc.html",
            "day5/unresolved.html",
            "finals/picks.html",
            "finals/twc.html",
            "finals/unresolved.html",
            "picks-every-match/index.html",
            "picks-every-match/unresolved.html",
        }
        self.assertTrue(required <= hrefs, f"missing landing links: {sorted(required - hrefs)}")
        for href in required:
            self.assertTrue((ROOT / href).is_file(), f"landing link target does not exist: {href}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
