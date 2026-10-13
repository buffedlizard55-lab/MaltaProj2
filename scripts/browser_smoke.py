"""Exercise static navigation and filtering in real desktop/mobile Chromium on CI."""
import subprocess
from playwright.sync_api import sync_playwright

server=subprocess.Popen(['python','-m','http.server','8765','--bind','0.0.0.0','--directory','docs'])
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox'])
        page=browser.new_page()
        errors=[]
        page.on('pageerror', lambda error: errors.append(str(error)))
        for name in ('index','matches','odds','methodology','sources','flags'):
            response=page.goto('http://127.0.0.1:8765/'+name+'.html',wait_until='networkidle')
            assert response.status==200, name
            assert page.locator('h1').count()==1, name
            assert page.locator('nav a[aria-current="page"]').count()==1, name
        page.goto('http://127.0.0.1:8765/matches.html')
        total=page.locator('#matches tbody tr').count()
        assert total>0
        page.locator('#search').fill('astralis')
        assert page.locator('#matches tbody tr:visible').count()==1
        page.locator('#search').fill('no-such-team-xyz')
        assert page.locator('#matches tbody tr:visible').count()==0
        assert page.locator('#row-count').inner_text().startswith('0 of ')
        page.locator('#search').fill('')
        page.locator('#visibility').select_option('Visible card')
        assert 0<page.locator('#matches tbody tr:visible').count()<=total
        page.set_viewport_size({'width':390,'height':844})
        for name in ('index','matches','flags'):
            page.goto('http://127.0.0.1:8765/'+name+'.html')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), name
        assert not errors, errors
        browser.close()
        print('PASS: desktop/mobile navigation, filters, no page errors, no viewport overflow')
finally:
    server.terminate()
    server.wait(timeout=10)
