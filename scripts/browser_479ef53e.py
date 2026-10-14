"""Hosted Chromium checks the unified every-match board at phone and desktop widths."""
import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
board = json.loads((root / 'data/c64a5e19/board.json').read_text())
server = subprocess.Popen(['python', '-m', 'http.server', '8768', '--bind', '0.0.0.0'], cwd=root)
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('CHROME_BIN', '/usr/bin/google-chrome'), headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        for width in (1280, 390, 320):
            page.set_viewport_size({'width': width, 'height': 844})
            for name in ('index', 'picks', 'inventory', 'flagged', 'method'):
                response = page.goto(f'http://127.0.0.1:8768/picks-every-match/{name}.html', wait_until='networkidle')
                assert response.status == 200
                assert page.locator('h1').count() == 1
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (name, width)
                for row in page.locator('tbody tr').all():
                    assert row.locator('a[href^="https://"]').count() > 0, (name, 'row lacks source')
                if name in ('index', 'picks'):
                    assert page.locator('[data-match]').count() == board['summary']['open']
                    page.locator('#search').fill('no-such-team-479ef53e')
                    assert page.locator('[data-match]:visible').count() == 0
                    assert page.locator('#visible-count').inner_text() == '0 matches shown'
                    page.locator('#search').fill('')
                    page.locator('#basis').select_option('unverified')
                    assert page.locator('[data-match]:visible').count() == board['summary']['no_line']
                    page.locator('#basis').select_option('')
        # Test live-open browser tabs: expiry must run again without requiring a reload.
        now = datetime.fromisoformat(board['generated_utc'].replace('Z', '+00:00'))
        page.clock.install(time=now)
        page.goto('http://127.0.0.1:8768/picks-every-match/picks.html', wait_until='networkidle')
        page.clock.fast_forward(5 * 3600 * 1000)
        assert page.locator('[data-match] .estimate:visible').count() == 0
        if board['summary']['open']:
            assert page.locator('#expiry-note').is_visible()
        assert not errors, errors
        browser.close()
    print('PASS: unified board at desktop/390/320px; row sources, filters, expiry, no overflow or JS errors')
finally:
    server.terminate()
    server.wait(timeout=10)
