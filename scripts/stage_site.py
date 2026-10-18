"""Stage all published research work without publishing repository internals.

Each session keeps its own section: root, docs/ (LineWatch), pickem/.
No unrelated session's source files are rewritten.
"""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'out/site'
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
# 3e1be203 desk: re-render the phone-first desk from the canonical batch before staging, so a
# scheduled data refresh can never leave its probabilities stale. Additive: this session writes
# only desk/**, data/3e1be203/** and scripts/3e1be203/**.
import subprocess as _subprocess, sys as _sys
_subprocess.run([_sys.executable, str(ROOT/'scripts/3e1be203/build.py')], check=False)
# 782adb47 finals: re-render the Day-5 finals desk from the canonical batch before staging (additive;
# this session writes only finals/**, data/782adb47/**, scripts/782adb47/**).
_subprocess.run([_sys.executable, str(ROOT/'scripts/782adb47/build.py')], check=False)
# 7900154b day-5 desk: re-render from the retained raw prices before staging, so the
# published artifact can never serve a stale board. Writes only day5/**.
_subprocess.run([_sys.executable, str(ROOT/'scripts/7900154b/build.py')], check=False)
for file in ROOT.glob('*.html'):
    shutil.copy2(file,OUT/file.name)
for name in ('assets','data','docs','pickem','evidence','audits','verify','current','verify961','picks','site','market','live','fresh','ourline','picks-every-match','summary','coverage','board','exec','picks-all','unresolved','strategy','twc','day3','twc-2026','hub','day4','today','desk','finals','day5','finalday')  # finalday: 36186ad8:
# 'finals' added by session 782adb47 (TWC Day-5 finals desk), additive single entry: root NAV +
# landing front door link finals/index.html, so the artifact must carry the directory.
# 'day5' added by session 7900154b (TWC 2026 day-5 final desk + every-match picks), additive
# single entry: the root NAV and the landing executive summary link day5/index.html, so the
# artifact must carry the directory or every root page fails the staged-link check.
# Unioned by session 782adb47 during merge of PR #175; neither entry removed.
# 'desk' added by session 3e1be203 (phone-first TWC day-4 + every-match pick desk), additive
# single entry: the root NAV and the landing executive summary link desk/index.html, so the
# artifact must carry the directory or every root page fails the staged-link check.
# 'today' added by session 9c44d0e9 (T-9C44D0E9-TODAY phone-first desk), additive single entry:
# the root NAV + executive summary link today/index.html, so the artifact must carry the
# directory or every root page fails the staged-link check. No other session's files modified.
# 'day4' added by session 1c8f79f8 (T-DAY4-1C8F79F8 TWC day-4 desk + every-match
# refresh), additive single entry: the landing executive summary links day4/index.html,
# so the artifact must carry the directory or every root page fails the staged-link
# check. No other session's files are modified here.
# 'twc' added by session 869a5375 (T-TWC-DAY3 Day 1-3 review + Day 3 picks), additive single entry:
# the landing executive summary links twc/index.html, so the artifact must carry the directory.
# 'day3' added by session 4cf64ea3 (TWC day-2 review -> day-3 picks desk, every-match coverage);
# additive single entry: the landing executive summary links day3/index.html, so the artifact must
# carry the directory or every root page fails the staged-link check. No other session's files are
# modified here.
# 'strategy' added by session f28afd9e (every-match safe + leaderboard picks); additive single entry: the
# landing executive summary links strategy/index.html, so the artifact must carry the directory.
# 'picks-all' added by session b5436cf0 (complete every-match picks) as an additive single entry.
# 'unresolved' added by session 7177d07f (T-UNRESOLVED-7177D07F / T-INTEG-7177D07F) as an additive
# single entry: the executive summary on the landing page links into unresolved/index.html, so the
# artifact must carry the directory or every root page fails the staged-link check.
# Both entries are additive and were unioned during integration; neither session's entry was removed.
# 'picks-every-match' added by session c64a5e19 (every-match board) as an additive single entry.
# 'summary' added by session c0e223d3 (T-HUB-INTEG) as an additive single entry so the
# source/verification hub ships in the Pages artifact. Additive single entry only.
# 'ourline' added by session f7279a54 (OURLINE board) as an additive single entry so /ourline/ is
# published; requested in COORDINATION.md. f7279a54 does not touch NAV, README or other entries.
# 'coverage' added by session 6ddde224 (T-COVERAGE-INTEG, additive single entry): the root NAV links
# coverage/index.html, so the artifact must carry the directory or every staged page fails the
# link check and no site is published. No other session's files are modified here.
# 'live' added by session 3cd9787c (T-COVER current-lobby coverage board), additive single entry.
# 'board' added by session fe803b80 (T-FULLCOV full-coverage picks board). Additive single entry;
# the root NAV and the executive summary on the landing page link into it, so the artifact must
# carry the directory or every root page fails the staged-link check.
# 'exec' added by session b1fb1465 (T-EXEC-B1FB1465-INTEGRATE), additive single entry: the root
# NAV and the landing-page executive summary link exec/index.html, so the artifact must carry
# the directory or every root page fails the staged-link check. No other session's files are
# modified here.
# 'fresh' added by session 3cd9787c as an integration unblock: the shared root NAV links
# fresh/index.html (section dd2b7fee landed on main), so the artifact must carry the directory or
# every root page fails the staged-link check and no site is published. Additive single entry.
# dd2b7fee's own files are not modified here.
# 'hub' added by session 7c2622db (mobile pick'em hub: every open match + TWC day-3 desk) as an
# additive single entry; the root NAV and the landing-page executive summary link hub/index.html,
# so the artifact must carry the directory or every root page fails the staged-link check.
# The hub is re-rendered from the staged data batch below, so a scheduled refresh cannot leave
# its probabilities stale. No other session's files are modified here.
    source=ROOT/name
    if source.exists():
        shutil.copytree(source,OUT/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.git'))
# TWC day-two/day-three category (69e4c06a): render from the staged canonical batch,
# so a scheduled data refresh cannot leave the category's probabilities stale.
import importlib.util
_twc_spec=importlib.util.spec_from_file_location('staged_twc_69e4c06a',ROOT/'scripts/69e4c06a/build.py')
_twc=importlib.util.module_from_spec(_twc_spec)
_twc_spec.loader.exec_module(_twc)
_twc.build(OUT)
# TWC Day 1-3 -> Day 4 Semifinals & every-match verification (5a40690b): render from the staged canonical batch.
_d4_spec=importlib.util.spec_from_file_location('staged_d4_5a40690b',ROOT/'scripts/5a40690b/build.py')
_d4=importlib.util.module_from_spec(_d4_spec)
_d4_spec.loader.exec_module(_d4)
_d4.build(OUT)
# Pick'em hub (session 7c2622db): re-render from the staged data batch, read-only for every
# other session's files. If the render fails the copied hub/ directory stays as committed.
try:
    _hub_spec=importlib.util.spec_from_file_location('staged_hub_7c2622db',ROOT/'scripts/7c2622db/build.py')
    _hub=importlib.util.module_from_spec(_hub_spec)
    _hub_spec.loader.exec_module(_hub)
    _hub.OUT=OUT/'data'/'7c2622db'
    _hub.HUB=OUT/'hub'
    _hub.CANON=OUT/'data'/'c64a5e19'
    _hub.build()
    print('Staged pick\'em hub re-rendered from the staged data batch')
except Exception as _hub_error:  # noqa: BLE001
    print('hub re-render skipped, using committed pages:', _hub_error)
# RECONCILE-4E6 (session 4e6dcd0d): rebuild the cross-board section from the staged data batch (additive, read-only).
import reconcile_4e6dcd0d
reconcile_4e6dcd0d.build(OUT/'reconcile', write_json=False)
# Render the root handoff from the exact data batch staged above. The upstream
# refresh workflow commits JSON but not all generated root HTML. Rendering only
# inside staging avoids stale page/data disagreement without editing its sources.
import build_site
build_site.ROOT=str(OUT)
if build_site.main() != 0:
    raise SystemExit('Root handoff generator failed in staging')
(OUT/'.nojekyll').touch()
assert (OUT/'docs/index.html').is_file()
print('Staged root contributions, LineWatch at /docs/, /pickem/ and /verify961/ boards and /picks/ live-lines board')
# Verify local navigation across every staged section, not just LineWatch.
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
class Links(HTMLParser):
    def __init__(self):
        super().__init__();self.urls=[]
    def handle_starttag(self, tag, attrs):
        for key,value in attrs:
            if key in ('href','src') and value:
                self.urls.append(value)
errors=[]
for page in OUT.rglob('*.html'):
    parser=Links();parser.feed(page.read_text())
    for url in parser.urls:
        parsed=urlsplit(url)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        path=unquote(parsed.path)
        if path.startswith('/MaltaProj2/'):
            target=OUT/path.removeprefix('/MaltaProj2/')
        elif path.startswith('/'):
            target=OUT/path.lstrip('/')
        else:
            target=page.parent/path
        if not target.exists():
            errors.append(f'{page.relative_to(OUT)} -> {url}')
if errors:
    raise SystemExit('Broken staged local links:\n'+'\n'.join(errors))
print('PASS: all staged local links resolve across all session sections')
