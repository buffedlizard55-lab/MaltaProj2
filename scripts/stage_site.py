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
for file in ROOT.glob('*.html'):
    shutil.copy2(file,OUT/file.name)
for name in ('assets','data','docs','pickem','evidence','audits','verify','current','verify961','picks','site'):
    source=ROOT/name
    if source.exists():
        shutil.copytree(source,OUT/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.git'))
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
