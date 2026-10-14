"""Hosted Chromium verifies the primary root dashboard (mobile and desktop)."""
import subprocess
import os
from playwright.sync_api import sync_playwright

server = subprocess.Popen(['python', '-m', 'http.server', '8766', '--bind', '0.0.0.0'])
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('CHROME_BIN', '/usr/bin/google-chrome'), headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        for width in (1280, 390, 320):
            page.set_viewport_size({'width': width, 'height': 844})
            for name in ('index', 'cs2', 'probabilities', 'tournaments', 'flagged', 'methodology', 'research'):
                r = page.goto(f'http://127.0.0.1:8766/{name}.html', wait_until='networkidle')
                assert r.status == 200, name
                assert page.locator('h1').count() == 1, name
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), (name, width)
                if name in ('cs2', 'probabilities'):
                    assert page.locator('table tbody tr').count() > 0, name
                    page.locator('#filter').fill('no-such-team-xyz')
                    assert page.locator('table tbody tr:visible').count() == 0, name
                    page.locator('#filter').fill('')
                    assert page.locator('table tbody tr:visible').count() > 0, name
                    for row in page.locator('table tbody tr').all():
                        assert row.locator('a[href^="https://"]').count() > 0, name
        assert not errors, errors
        browser.close()
        print('PASS: current root UI desktop/390px/320px, filters, source links and no overflow/errors')
finally:
    server.terminate()
    server.wait(timeout=10)
