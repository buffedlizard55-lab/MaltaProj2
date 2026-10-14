"""Verify the actual canonical Pages landing, not just the legacy docs section."""
import os
import time
from urllib.request import Request, urlopen
BASE = 'https://buffedlizard55-lab.github.io/MaltaProj2/'
checks = {'index.html': 'id="dashboard-search"', 'assets/dashboard-mobile.js': 'data-pick-row',
          'assets/dashboard-mobile.css': '.dashboard-summary', 'audits/9caec349/index.html': 'Integration audit',
          'ourline/index.html': 'Executive summary'}
for path, marker in checks.items():
    for attempt in range(12):
        try:
            with urlopen(Request(BASE+path+'?check='+os.environ.get('GITHUB_SHA','canonical'), headers={'Cache-Control':'no-cache'}), timeout=30) as response:
                assert response.status == 200
                assert marker in response.read().decode('utf-8'), f'missing marker: {path}'
            break
        except Exception:
            if attempt == 11: raise
            time.sleep(10)
    print('PASS public canonical page:', path)
