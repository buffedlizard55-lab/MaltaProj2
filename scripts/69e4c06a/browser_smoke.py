"""Bounded mobile/browser acceptance for the source-linked TWC category."""
import argparse
import functools
import json
import os
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    data = json.loads((args.root / 'data/69e4c06a/day3.json').read_text())
    handler = functools.partial(QuietHandler, directory=str(args.root))
    server = ThreadingHTTPServer(('0.0.0.0', 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=os.environ.get('CHROME_BIN', '/usr/bin/google-chrome'),
                headless=True, args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.clock.install(time=datetime.fromisoformat(data['evaluated_utc'].replace('Z', '+00:00')))
            base = f'http://127.0.0.1:{server.server_port}/'
            for width in (320, 390, 768, 1280):
                page.set_viewport_size({'width': width, 'height': 844})
                for name in ('index', 'results', 'roster', 'flagged', 'method'):
                    response = page.goto(base + 'twc-2026/' + name + '.html', wait_until='networkidle')
                    assert response.status == 200, (width, name)
                    assert page.locator('h1').count() == 1, (width, name)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, name)
                    assert page.locator('nav a[aria-current="page"]').count() == 1
                    for link in page.locator('nav a').all():
                        assert link.bounding_box()['height'] >= 44, (width, name, link.inner_text())
                    for row in page.locator('tbody tr').all():
                        assert row.locator('a[href^="https://"]').count(), (width, name)
                page.goto(base + 'index.html', wait_until='networkidle')
                cta = page.locator('#executive-summary .actions a[href="twc-2026/index.html"]')
                assert cta.count() == 1
                assert cta.bounding_box()['height'] >= 44
                cta.click()
                assert page.url.endswith('/twc-2026/index.html')
                for row in data['day_three']:
                    match = page.locator('#' + row['key'])
                    assert match.count() == 1
                    if row['line'] and 'expired' not in (match.get_attribute('class') or ''):
                        assert match.locator('.prob').all_text_contents() == [
                            f'{row["line"]["prob_a"] * 100:.2f}%', f'{row["line"]["prob_b"] * 100:.2f}%']
                    if not row['listed_on_hotspawn']:
                        assert 'not a HotSpawn pick' in match.inner_text()
            # Expiry is a browser behavior, not merely a timestamp in the JSON.
            page.clock.set_system_time(datetime(2100, 1, 1, tzinfo=timezone.utc))
            page.clock.run_for(30001)
            assert page.locator('[data-deadline].expired').count() == len(data['day_three'])
            assert page.locator('#expiry-note').is_visible()
            for forecast in page.locator('[data-live]').all():
                assert not forecast.is_visible(), 'Expired forecast remained visible'
            assert not errors, errors
            browser.close()
            print('PASS: TWC pages, primary links, canonical values, preview labels and expiry at 320/390/768/1280px')
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=10)


if __name__ == '__main__':
    main()
