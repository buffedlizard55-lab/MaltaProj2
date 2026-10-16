#!/usr/bin/env python3
"""Run against a local/hosted static preview. Does not start a background server.
Example: CHROME_BIN=/path/to/chrome python scripts/6ffacd40/browser.py http://127.0.0.1:8080
"""
import os
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8080').rstrip('/')
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get('CHROME_BIN', '/usr/bin/google-chrome'), headless=True, args=['--no-sandbox'])
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    for width in (320, 390, 768, 1280):
        page.set_viewport_size({'width': width, 'height': 844})
        for path in ('index.html', 'audits/6ffacd40/index.html', 'picks-every-match/index.html', 'picks-every-match/unresolved.html', 'twc-2026/index.html'):
            response = page.goto(BASE + '/' + path, wait_until='networkidle')
            assert response.status == 200, path
            assert page.locator('h1').count() == 1, path
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (path, width)
        page.goto(BASE + '/index.html', wait_until='networkidle')
        cta = page.locator('#executive-summary a.btn-primary')
        box = cta.bounding_box()
        assert box['height'] >= 44 and box['y'] + box['height'] < 844, (width, box)
        assert page.locator('#pick-accounting').inner_text().find('priced ties') >= 0
        assert not page.locator('a.board-card[href="strategy/index.html"]').is_visible()
        page.keyboard.press('Tab')
        assert page.locator('a.skip-link').evaluate('(e)=>e===document.activeElement')
        page.keyboard.press('Enter')
        assert page.evaluate('document.activeElement.id') == 'main-content'
        if width == 390:
            Path('.cache').mkdir(exist_ok=True)
            page.screenshot(path='.cache/home-mobile-6ffacd40.png', full_page=True)
        cta.click()
        assert page.url.endswith('/picks-every-match/index.html')
    assert not errors, errors
    browser.close()
print('PASS: 320/390/768/1280px; no overflow, primary CTA above fold, 44px targets, skip link, archives collapsed, canonical navigation')
