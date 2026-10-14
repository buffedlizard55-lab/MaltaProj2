"""CI browser checks the canonical landing at phone and desktop sizes."""
import json
import os
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[2]
board = json.loads((ROOT/'data/f7279a54/board.json').read_text())
server = subprocess.Popen(['python','-m','http.server','8768','--bind','0.0.0.0'], cwd=ROOT)
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('CHROME_BIN','/usr/bin/google-chrome'), headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.clock.install(time=board['generated_utc'])
        for width in (1280,390,320):
            page.set_viewport_size({'width':width,'height':844})
            assert page.goto('http://127.0.0.1:8768/index.html',wait_until='networkidle').status == 200
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), width
            assert page.locator('[data-pick-row]').count() == len(board['open'])
            page.locator('#dashboard-search').fill('no-such-team-xyz')
            assert page.locator('[data-pick-row]:visible').count() == 0
            assert page.locator('#dashboard-empty').is_visible()
            page.locator('#dashboard-search').fill('')
            page.locator('#dashboard-basis').select_option('model')
            assert page.locator('[data-pick-row]:visible').count() == board['summary']['model_only']
            page.locator('#dashboard-basis').select_option('all')
            for row in page.locator('[data-pick-row]').all():
                assert row.locator('a[href^="https://"]').count() > 0
        first = page.locator('[data-pick-row]').first
        first.evaluate("r => r.dataset.expiry = '2000-01-01T00:00:00Z'")
        page.clock.fast_forward(60001)
        assert first.locator('[data-pick]').inner_text() == 'Expired — awaiting refresh'
        assert set(first.locator('[data-prob]').all_inner_texts()) == {'—'}
        assert page.locator('#dashboard-freshness').is_visible()
        assert not errors, errors
        browser.close()
        print('PASS canonical dashboard: desktop/390/320px, filters, sources and expiry')
finally:
    server.terminate()
    server.wait(timeout=10)
