/* npm packages supplied by the verification environment, never vendored. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright-core');
(async () => {
  const module = require('@sparticuz/chromium');
  const binary = module.default || module;
  // Chromium's npm bundle includes its runtime libraries; no external browser download.
  if (module.inflate) {
    const runtime = await module.inflate(path.join(path.dirname(require.resolve('@sparticuz/chromium')), '../bin/al2023.tar.br'));
    process.env.LD_LIBRARY_PATH = path.join(runtime,'lib') + ':' + (process.env.LD_LIBRARY_PATH || '');
  }
  const browser = await chromium.launch({executablePath: await binary.executablePath(), args:binary.args,headless:true});
  const root = path.resolve(__dirname,'../..');
  const report = JSON.parse(fs.readFileSync(path.join(root,'data/741a34ac/report.json')));
  const base = process.env.AUDIT_BASE_URL || 'http://127.0.0.1:8000/';
  try {
    const page = await browser.newPage();
    await page.clock.install({time:new Date('2099-01-01T00:00:00Z')});
    for (const width of [320,390,768,1280]) {
      await page.setViewportSize({width,height:844});
      const errors=[];
      page.on('pageerror',e=>errors.push(String(e)));
      page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
      page.on('response',r=>{if(r.status()>=400)errors.push(`${r.status()} ${r.url()}`);});
      for (const file of ['index.html','flagged.html']) {
        const response=await page.goto(base+'audits/741a34ac/'+file);
        assert.equal(response.status(),200);
        assert.equal(await page.locator('h1').count(),1);
        assert(await page.locator('meta[name=viewport]').count());
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`${width}/${file}: horizontal overflow`);
        await page.keyboard.press('Tab');
        assert.equal(await page.evaluate(()=>document.activeElement.textContent),'Skip to content');
        if (file==='index.html') {
          assert.equal(await page.locator('tbody tr[id]').count(),report.summary.listed);
          for (const row of report.rows) assert(await page.locator(`#m${row.fixture_id} a`).count());
        }
      }
      await page.reload();
      assert((await page.locator('#freshness').textContent()).includes('STALE / UNVERIFIED'));
      assert.deepEqual(errors,[]);
      console.log(`PASS: ${width}px, source rows, keyboard skip, no overflow/errors, expired clock`);
    }
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
