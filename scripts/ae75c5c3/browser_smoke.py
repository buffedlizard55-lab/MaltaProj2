"""Hosted Chromium: source links, mobile readability, filters and fail-closed expiration."""
import json
import os
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
board = json.loads((ROOT / 'data/f7279a54/board.json').read_text())
server = subprocess.Popen(['python', '-m', 'http.server', '8767', '--bind', '0.0.0.0'], cwd=ROOT)
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('CHROME_BIN', '/usr/bin/google-chrome'), headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        # Stable test clock anchored to the captured source time, not a scheduled run's delay.
        page.clock.install(time=board['generated_utc'])
        for width in (1280, 390, 320):
            page.set_viewport_size({'width': width, 'height': 844})
            for name in ('index', 'flagged', 'sources', 'method', 'results'):
                response = page.goto(f'http://127.0.0.1:8767/ourline/{name}.html', wait_until='networkidle')
                assert response.status == 200
                assert page.locator('h1').count() == 1
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), (name, width)
                if name == 'index':
                    assert page.get_by_role('heading', name='Executive summary').count() == 1
                    assert page.locator('tr[data-row]').count() == board['summary']['open']
                    page.get_by_role('searchbox').fill('no-such-team-xyz')
                    assert page.locator('tr[data-row]:visible').count() == 0
                    page.get_by_role('searchbox').fill('')
                    page.locator('[data-m="model"]').click()
                    assert page.locator('tr[data-row]:visible').count() == board['summary']['model_only']
                    page.locator('[data-m="market"]').click()
                    assert page.locator('tr[data-row]:visible').count() == board['summary']['market_based']
                    page.locator('[data-m="all"]').click()
                    for row in page.locator('tr[data-row]').all():
                        assert row.locator('a[href^="https://"]').count() > 0
        page.goto('http://127.0.0.1:8767/ourline/index.html', wait_until='networkidle')
        first = page.locator('tr[data-row]').first
        first.evaluate("r => {r.dataset.validUntil='2000-01-01T00:00:00Z';}")
        page.clock.fast_forward(60001)
        assert first.locator('.pickcell').inner_text() == 'Expired — awaiting source refresh'
        assert first.locator('.b-pick').count() == 0
        assert set(first.locator('.pct').all_inner_texts()) == {'—'}
        assert page.locator('#freshness-alert').is_visible()
        assert not errors, errors
        browser.close()
        print('PASS: fallback board desktop/390px/320px, source links, filters, expiry and no overflow')
finally:
    server.terminate()
    server.wait(timeout=10)
