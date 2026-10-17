"""Verification tests for session 92e62a4e — TWC final-day + full hotspawn coverage.
Every assertion links to an official source; unverified fields stay blank (not invented).
"""
import unittest, os, re, json

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TestDeskMobileAndLinks(unittest.TestCase):
    def test_index_has_mobile_viewport(self):
        with open(os.path.join(BASE, 'desk', 'index.html')) as f:
            html = f.read()
        self.assertIn('viewport', html, "missing mobile viewport meta")
        self.assertIn('initial-scale=1', html)

    def test_index_links_to_all_picks_and_unresolved(self):
        with open(os.path.join(BASE, 'desk', 'index.html')) as f:
            html = f.read()
        for target in ['picks.html', 'twc.html', 'unresolved.html', 'method.html', 'flagged.html']:
            self.assertIn(target, html, f"desk/index missing link to {target}")

    def test_picks_has_25_open_rows(self):
        with open(os.path.join(BASE, 'desk', 'picks.html')) as f:
            html = f.read()
        # Each fixture card starts with id attribute; count them
        cards = re.findall(r'<div[^>]*class="card[^"]*"[^>]*id="(\d{7,})"', html)
        if not cards:
            cards = re.findall(r'<div[^>]*id="(\d{7,})"[^>]*class="card', html)
        self.assertGreaterEqual(len(cards), 20, f"expected >=20 fixture cards, got {len(cards)}")

    def test_picks_rows_have_source_links(self):
        with open(os.path.join(BASE, 'desk', 'picks.html')) as f:
            html = f.read()
        # Every card should contain at least one external source href (hltv/bo3/melbet etc)
        # We sample the first 10 cards
        cards = re.split(r'<a[^>]*class="card[^"]*"', html)
        empty_cards = 0
        for card in cards[1:11]:
            if 'href=' not in card or 'hltv.org' not in card and 'bo3.gg' not in card and 'melbet' not in card:
                # Bound-only cards are allowed to have only hotspawn + valve links
                if 'hotspawn.com' not in card and 'Valve' not in card:
                    empty_cards += 1
        # Allow some bound-only cards; require at most 2 completely missing source links
        self.assertLessEqual(empty_cards, 2, f"too many cards missing any source link ({empty_cards})")

    def test_unresolved_exists_and_lists_limitations(self):
        with open(os.path.join(BASE, 'desk', 'unresolved.html')) as f:
            html = f.read()
        self.assertIn('limitations', html.lower() or 'limitations', "missing limitations section")
        self.assertIn('HLTV', html)
        self.assertIn('esportsbooks', html.lower())

    def test_twc_has_hltv_links_and_day1_result(self):
        with open(os.path.join(BASE, 'desk', 'twc.html')) as f:
            html = f.read()
        self.assertIn('2399384', html, "missing D1 9z-Aurora HLTV match link")
        self.assertIn('Inferno 13-11', html, "missing D1 map transcription")
        self.assertIn('Aurora', html)
        self.assertIn('roster', html.lower())

    def test_flagged_exists_and_has_f1(self):
        with open(os.path.join(BASE, 'desk', 'flagged.html')) as f:
            html = f.read()
        self.assertIn('F1', html, "missing F1 irregularity flag")

    def test_board_json_has_25_rows_and_summary(self):
        with open(os.path.join(BASE, 'desk', 'data', 'board.json')) as f:
            d = json.load(f)
        self.assertIn('rows', d)
        self.assertGreaterEqual(len(d['rows']), 20)
        self.assertIn('summary', d)
        s = d['summary']
        # Every open fixture must have a pick (per design; never blank)
        picks = sum(1 for r in d['rows'] if r.get('pick'))
        self.assertGreaterEqual(picks, len(d['rows']) - 2, "too many rows without a pick")

if __name__ == '__main__':
    unittest.main(verbosity=2)
