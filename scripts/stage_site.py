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
for name in ('assets','data','docs','pickem','evidence'):
    source=ROOT/name
    if source.exists():
        shutil.copytree(source,OUT/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.git'))
(OUT/'.nojekyll').touch()
assert (OUT/'docs/index.html').is_file()
print('Staged root contributions, LineWatch at /docs/, and separate /pickem/ board')
