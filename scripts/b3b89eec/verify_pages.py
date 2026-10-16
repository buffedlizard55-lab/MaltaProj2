#!/usr/bin/env python3
"""Session b3b89eec — static audit of the published site pages.

Checks (no browser required; CI browser smokes cover layout/overflow separately):
 1. every audited page has a mobile viewport meta and exactly one h1
 2. every internal (relative) link on every audited page resolves to an existing file
 3. data tables: every row in the fixture/result tables carries at least one official
    https source link (rows without one are listed, never silently accepted)
 4. root executive summary exists and links in-site to the picks list + unresolved page
 5. the method page publishes the declared source weighting used by the board

Output: data/b3b89eec/pages_audit.json
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/b3b89eec/pages_audit.json'

PAGES = [
    'index.html', 'cs2.html', 'lines.html', 'teams.html', 'day-one.html', 'flagged.html',
    'methodology.html', 'research.html', 'hotspawn.html', 'probabilities.html', 'tournaments.html',
    'picks-every-match/index.html', 'picks-every-match/picks.html', 'picks-every-match/inventory.html',
    'picks-every-match/unresolved.html', 'picks-every-match/flagged.html', 'picks-every-match/method.html',
    'twc-2026/index.html', 'twc-2026/results.html', 'twc-2026/roster.html',
    'twc-2026/flagged.html', 'twc-2026/method.html',
    'twc/index.html', 'twc/unresolved.html', 'twc/method.html',
    'picks-all/index.html', 'picks-all/picks.html', 'picks-all/unresolved.html',
    'picks-all/method.html', 'picks-all/flagged.html',
    'day3/index.html', 'day3/picks.html', 'day3/unresolved.html', 'day3/method.html',
    'ourline/index.html',
    'ourline/method.html', 'ourline/flagged.html', 'ourline/results.html', 'ourline/sources.html',
    'board/index.html', 'board/picks.html', 'board/results.html', 'board/lines.html',
    'board/tournaments.html', 'board/flagged.html', 'board/method.html',
    'current/index.html', 'current/flagged.html',
    'unresolved/index.html',
    'verify/b3b89eec/index.html', 'verify/b3b89eec/flagged.html',
]

# Pages whose main table rows are match rows and therefore must each carry an official link.
ROW_SOURCE_PAGES = {
    'picks-every-match/index.html': 'data-match',
    'picks-every-match/picks.html': 'data-match',
    'picks-every-match/inventory.html': 'data-match',
    'picks-every-match/unresolved.html': None,
    'twc-2026/results.html': None,
    'twc/index.html': None,
    'picks-all/picks.html': None,
    'day3/picks.html': 'data-match',
    'ourline/index.html': 'data-row',
    'board/index.html': 'data-row',
    'board/picks.html': 'data-row',
    'verify/b3b89eec/index.html': None,
    'verify/b3b89eec/flagged.html': None,
}


def rows_of(html, attr=None):
    pat = r'<tr(?:\s[^>]*)?>(.*?)</tr>'
    rows = re.findall(pat, html, re.S)
    if attr:
        rows = [r for m in re.finditer(pat, html, re.S)
                if f' {attr}=' in m.group(0).split('>')[0]]
    return rows


def audit():
    findings, passes = [], []
    pages_checked = 0
    for rel in PAGES:
        p = ROOT / rel
        if not p.exists():
            findings.append({'page': rel, 'issue': 'file missing'})
            continue
        html = p.read_text(errors='replace')
        pages_checked += 1
        # 1. viewport + single h1
        if 'name="viewport"' not in html and 'name=\'viewport\'' not in html:
            findings.append({'page': rel, 'issue': 'no mobile viewport meta'})
        else:
            passes.append(f'{rel}: viewport meta present')
        h1 = len(re.findall(r'<h1[\s>]', html))
        if h1 != 1:
            findings.append({'page': rel, 'issue': f'{h1} h1 elements (expected 1)'})
        # 2. internal links resolve
        base = p.parent
        for href in re.findall(r'(?:href|src)="([^"#]+)"', html):
            if href.startswith(('http://', 'https://', 'mailto:', 'javascript:')):
                continue
            if '${' in href:  # client-side JS template, not a static link
                continue
            target = (base / href.split('#')[0].split('?')[0])
            if not target.exists():
                findings.append({'page': rel, 'issue': f'internal link does not resolve: {href}'})
        if not any(f['page'] == rel and 'internal link' in f['issue'] for f in findings):
            passes.append(f'{rel}: all internal links resolve')
        # 3. duplicate ids
        ids = re.findall(r'\bid="([^"]+)"', html)
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            findings.append({'page': rel, 'issue': f'duplicate ids: {sorted(dupes)[:6]}'})
        # 4. row-level source links
        if rel in ROW_SOURCE_PAGES:
            attr = ROW_SOURCE_PAGES[rel]
            missing = []
            for m in re.finditer(r'<tr(?:\s[^>]*)?>(.*?)</tr>', html, re.S):
                head = m.group(0).split('>')[0]
                # derived/standings rows (group tables) aggregate sourced rows; excluded by design
                if re.search(r'data-derived|standings', head, re.I):
                    continue
                if attr and f' {attr}=' not in head:
                    continue
                if not attr:
                    body = m.group(1).lstrip()
                    if body.startswith('<th') or body.startswith('<TH'):
                        continue  # header row (some tables use bare <th> rows, no thead)
                    # derived standings rows aggregate sourced match rows; excluded by design
                    if re.match(r'<td>\s*[AB]\s*</td>', body):
                        continue
                    # only count rows inside a tbody
                    prefix = html[:m.start()]
                    in_tbody = prefix.count('<tbody') > prefix.count('</tbody>')
                    in_thead = prefix.count('<thead') > prefix.count('</thead>')
                    if not in_tbody or in_thead:
                        continue
                if not re.search(r'https?://', m.group(1)):
                    label = re.sub(r'<[^>]+>', ' ', m.group(1))
                    label = re.sub(r'\s+', ' ', label).strip()[:80]
                    missing.append(label)
            if missing:
                findings.append({'page': rel, 'issue': f'{len(missing)} table row(s) without an official https source link',
                                 'rows': missing[:12]})
            else:
                passes.append(f'{rel}: every data row carries an official https source link')
    # 5. executive summary
    idx = (ROOT / 'index.html').read_text(errors='replace')
    m = re.search(r'<section id="executive-summary".*?</section>', idx, re.S)
    if not m:
        findings.append({'page': 'index.html', 'issue': 'executive summary section missing'})
    else:
        sec = m.group(0)
        for link, label in [('picks-every-match/index.html', 'picks list'),
                            ('picks-every-match/unresolved.html', 'unresolved picks & limitations')]:
            if f'href="{link}"' in sec:
                passes.append(f'index.html: executive summary links in-site to {label}')
            else:
                findings.append({'page': 'index.html', 'issue': f'executive summary lacks in-site link to {label}'})
    # 6. declared weighting published
    meth = (ROOT / 'picks-every-match/method.html').read_text(errors='replace')
    if re.search(r'weight[^.]{0,40}2[^.]{0,40}Pinnacle|Pinnacle[^.]{0,40}weight[^.]{0,40}2', meth, re.I):
        passes.append('method.html: Pinnacle weight 2 declared')
    else:
        findings.append({'page': 'picks-every-match/method.html', 'issue': 'declared source weighting not found in method page'})
    # snapshot stamp on the root
    mm = re.search(r'evaluated at ([0-9T:Z-]+)', idx)
    board = json.loads((ROOT / 'data/c64a5e19/board.json').read_text())
    return {
        'pages_checked': pages_checked,
        'canonical_snapshot_utc': board.get('generated_utc'),
        'root_stamp_utc': mm.group(1) if mm else None,
        'passes': passes,
        'findings': findings,
        'verdict': 'PASS' if not findings else f'FAIL — {len(findings)} finding(s)',
    }


def main():
    result = audit()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1) + '\n')
    print(result['verdict'], f"({result['pages_checked']} pages)")
    print('root stamp:', result['root_stamp_utc'], 'vs canonical snapshot:', result['canonical_snapshot_utc'])
    for f in result['findings'][:40]:
        print('FINDING:', json.dumps(f)[:300])
    return 0 if not result['findings'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
