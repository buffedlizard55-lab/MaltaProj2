"""Run unchanged legacy and new browser assertions; publish actionable failure annotations."""
import subprocess
import sys

SCRIPTS = [
    'scripts/browser_smoke.py',
    'scripts/build_site.py',
    'scripts/browser_current_smoke.py',
    'scripts/cbf92764/browser_smoke.py',
    'scripts/browser_479ef53e.py',
    'scripts/ae75c5c3/browser_smoke.py',
    'scripts/c64a5e19/browser_smoke.py',
    'scripts/browser_778756a1.py',
    'scripts/69e4c06a/browser_smoke.py',
]
for script in SCRIPTS:
    print('Browser verification:', script, flush=True)
    result = subprocess.run([sys.executable, script], capture_output=True, text=True)
    print(result.stdout, end='', flush=True)
    print(result.stderr, end='', file=sys.stderr, flush=True)
    if result.returncode:
        detail = (result.stderr or result.stdout)[-7000:]
        detail = detail.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print(f'::error title=Browser verification {script}::{detail}', flush=True)
        raise SystemExit(result.returncode)
print('PASS: all legacy and new browser checks')
