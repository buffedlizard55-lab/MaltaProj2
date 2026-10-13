"""Finite, read-only hosted browser audit at desktop and narrow phone widths."""
import json
import os
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
server = subprocess.Popen(['python','-m','http.server','8793','--bind','0.0.0.0'],cwd=ROOT,stdout=subprocess.DEVNULL)
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('CHROME_BIN','/usr/bin/google-chrome'),headless=True,args=['--no-sandbox'])
        page = browser.new_page()
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        expected=json.loads((ROOT/'audits/eb454aaa/report.json').read_text())
        expected_rows=sum(r['snapshot_future_label'] or bool(r['quotes']) for r in expected['rows'])
        for width in (320,390,1280):
            page.set_viewport_size({'width':width,'height':844})
            for name in ('index','flagged','rows'):
                response=page.goto(f'http://127.0.0.1:8793/audits/eb454aaa/{name}.html',wait_until='networkidle')
                assert response.status==200,(name,width)
                assert page.locator('h1').count()==1
                assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth'),(name,width)
                if name=='rows':
                    assert page.locator('tbody tr').count()==expected_rows
                    assert page.locator('tbody tr a[href^="https://"]').count()>=expected_rows
                    assert page.locator('td[data-label="Probability / pick"]').all_text_contents()==['']*expected_rows
                    page.locator('#filter').fill('no-such-team-xyz')
                    assert page.locator('tbody tr:visible').count()==0
                    page.locator('#filter').fill('')
                    assert page.locator('tbody tr:visible').count()==expected_rows
        assert not errors,errors
        browser.close()
        print('PASS: audit pages at 320/390/1280px, no overflow, row sources, blank probabilities, working filters and no JS errors')
finally:
    server.terminate()
    server.wait(timeout=10)
