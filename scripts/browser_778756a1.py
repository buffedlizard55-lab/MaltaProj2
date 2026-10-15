"""Mobile acceptance for the canonical root handoff and dated day-one review."""
import os
import subprocess
import sys
from playwright.sync_api import sync_playwright

server = subprocess.Popen([sys.executable, '-m', 'http.server', '8773', '--bind', '0.0.0.0'])
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('CHROME_BIN', '/usr/bin/google-chrome'),
                                   headless=True, args=['--no-sandbox'])
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        for width in (320, 390, 768, 1280):
            page.set_viewport_size({'width': width, 'height': 844})
            for name in ('index', 'day-one', 'flagged'):
                response = page.goto(f'http://127.0.0.1:8773/{name}.html', wait_until='networkidle')
                assert response.status == 200
                assert page.locator('h1').count() == 1
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, name)
                for row in page.locator('tbody tr').all():
                    assert row.locator('a[href^="https://"]').count(), name
            page.goto('http://127.0.0.1:8773/index.html', wait_until='networkidle')
            cta = page.locator('#executive-summary a.btn-primary')
            assert cta.get_attribute('href') == 'picks-every-match/index.html'
            assert cta.bounding_box()['height'] >= 44
            cta.click()
            assert page.url.endswith('/picks-every-match/index.html')
        assert not errors, errors
        browser.close()
        print('PASS: canonical mobile CTA, day-one and review at 320/390/768/1280px')
finally:
    server.terminate()
    server.wait(timeout=10)
