"""Browser assertions: 320/390/768/1280px, filtering, sources, expiry and no-JS content."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
URL=os.environ.get('DASHBOARD_TEST_URL','http://127.0.0.1:8767/dashboard/')
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=os.environ.get('CHROME_BIN','/usr/bin/google-chrome'),headless=True,
                              args=['--no-sandbox','--disable-dev-shm-usage','--no-zygote','--single-process'])
    page=browser.new_page()
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    for width in (320,390,768,1280):
        page.set_viewport_size({'width':width,'height':844})
        for name in ('index','picks','unresolved','sources','flagged','inventory'):
            res=page.goto(URL+name+'.html',wait_until='networkidle')
            assert res.status==200,(name,res.status)
            assert page.locator('h1').count()==1,name
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(width,name,'horizontal overflow')
            assert page.locator('nav a').count()==5
            if name in ('picks','inventory'):
                original=page.locator('tbody tr:visible').count()
                page.locator('#search').fill('xyz-no-such-team')
                assert page.locator('tbody tr:visible').count()==0
                page.locator('#search').fill('')
                assert page.locator('tbody tr:visible').count()==original
            if name=='picks':
                for row in page.locator('tbody tr').all():
                    assert row.locator('a[href^="https://"]').count()>0
        if width==390 and os.environ.get('DASHBOARD_SCREENSHOT'):
            page.goto(URL+'index.html',wait_until='networkidle')
            page.screenshot(path=os.environ['DASHBOARD_SCREENSHOT'],full_page=True)
    page.goto(URL+'picks.html')
    if page.locator('tr[data-state="open"]').count():
        page.evaluate('''() => {
          document.querySelectorAll('tr[data-state="open"]').forEach(r=>r.dataset.expiry='2000-01-01T00:00:00Z');
          window.dispatchEvent(new Event('visibilitychange'));
        }''')
        # Reload the display script once with already-expired row attributes.
        page.add_script_tag(url=URL+'app.js')
        assert page.locator('tr.expired .expiry-note').count()>0
        assert 'not a current recommendation' in page.locator('tr.expired .expiry-note').first.inner_text()
    assert not errors,errors
    context=browser.new_context(java_script_enabled=False,viewport={'width':320,'height':844})
    plain=context.new_page();plain.goto(URL+'picks.html')
    assert plain.locator('table').count()>0
    assert plain.locator('tbody tr a[href^="https://"]').count()>0
    browser.close()
print('PASS: all dashboard pages at 320/390/768/1280px; no overflow, filtering, source links, expiry and no-JS fallback')
