"""Hosted browser acceptance tests; bounded server is torn down in finally."""
import os
import subprocess
import sys
from playwright.sync_api import sync_playwright
server=subprocess.Popen([sys.executable,'-m','http.server','8768','--bind','0.0.0.0'])
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.environ.get('CHROME_BIN','/usr/bin/google-chrome'),headless=True,args=['--no-sandbox'])
        page=browser.new_page(); page.clock.install(); errors=[]
        page.on('pageerror',lambda e: errors.append(str(e)))
        for width in (320,390,768,1280):
            page.set_viewport_size({'width':width,'height':844})
            for name in ('index','picks','flagged','method'):
                response=page.goto(f'http://127.0.0.1:8768/picks-every-match/{name}.html',wait_until='networkidle')
                assert response.status==200
                assert page.locator('h1').count()==1
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),(name,width)
                for link in page.locator('nav a').all(): assert link.bounding_box()['height']>=44
            page.goto('http://127.0.0.1:8768/picks-every-match/index.html',wait_until='networkidle')
            page.locator('#search').fill('no-such-team-8723')
            assert page.locator('[data-search]:visible').count()==0
            page.locator('#search').fill('')
            if page.locator('[data-current]').count():
                page.evaluate("document.querySelectorAll('[data-until]').forEach(e=>e.dataset.until='2000-01-01T00:00:00Z')")
                # Fire timer callback by advancing the browser clock, without wall-clock waiting.
                page.clock.fast_forward(31000)
                assert page.locator('[data-current]:visible').count()==0
                assert page.locator('.expiry:visible').count()>0
        assert not errors,errors
        browser.close()
        print('PASS: every-match mobile/desktop, source UI, search, tap targets and expiry')
finally:
    server.terminate();server.wait(timeout=10)
