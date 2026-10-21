#!/usr/bin/env python3
"""Read-only coverage/evidence audit. Never generates a probability or rewrites a foreign board."""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/741a34ac'
SITE = ROOT / 'audits/741a34ac'
LOBBY = 'https://play.hotspawn.com/lobby'
BOARD = 'data/5f903db4/board.json'
SNAPSHOT = 'data/f7279a54/snapshot.json'
BOOK_HOSTS = {'www.pinnacle.com', 'guest.api.arcadia.pinnacle.com', 'www.bovada.lv',
              'melbet.com', 'thunderpick.io', 'www.thunderpick.io', 'kalshi.com',
              'api.elections.kalshi.com', 'polymarket.com', 'gamma-api.polymarket.com'}


def parse(value):
    try:
        t = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (TypeError, ValueError):
        return None


def iso(t):
    return t.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def read(path):
    return json.loads((ROOT / path).read_text())


def official_url(url):
    p = urlsplit(str(url or ''))
    return p.scheme == 'https' and not p.username and not p.password and p.hostname in (
        BOOK_HOSTS | {'play.hotspawn.com', 'www.hotspawn.com', 'www.hltv.org', 'github.com'})


def observation(meta):
    """A re-fetch or a report build must not reset the upstream cache's age."""
    t = parse(meta.get('at_utc'))
    try:
        age = float(meta.get('age_header') or 0)
        if not math.isfinite(age) or age < 0:
            return None
    except (ValueError, TypeError):
        return None
    return t - timedelta(seconds=age) if t else None


def rating_index(text):
    out = set()
    for line in text.splitlines():
        cols = [c.strip() for c in line.strip('|').split('|')]
        if len(cols) >= 5 and cols[0].isdigit() and cols[1].isdigit():
            out.add((int(cols[0]), float(cols[1]), cols[2],
                     tuple(sorted(x.strip().casefold() for x in cols[3].split(',')))))
    return out


def rating_matches(r, index):
    try:
        return (int(r['standing']), float(r['points']), r['vrs_name'],
                tuple(sorted(x.strip().casefold() for x in r['roster'].split(',')))) in index
    except (KeyError, TypeError, ValueError):
        return False


def rows_from_snapshot(snap):
    meta = snap.get('access_log', {}).get('hotspawn_lobby_page', {})
    # A failure with old retained data is not a successful new observation.
    if meta.get('status') != 200 or meta.get('error'):
        raise ValueError('No successful retained HotSpawn lobby response; completeness unverified')
    rows = [r for r in snap['hotspawn']['fixtures'] if 'lobby_page' in r.get('seen_in', [])]
    ids = [str(r.get('fixture_id') or '') for r in rows]
    if not rows or '' in ids or len(ids) != len(set(ids)):
        raise ValueError('Empty, missing-ID or duplicate lobby inventory; refuse a false 100% coverage')
    count = meta.get('fixtures_in_transfer_state')
    if count is not None and len(rows) != count:
        raise ValueError(f'Parsed lobby count {len(rows)} disagrees with source count {count}')
    return rows, meta


def audit(snap, board, rating_text, rating_meta, clock, research):
    fixtures, meta = rows_from_snapshot(snap)
    observed = observation(meta)
    freshness_ok = observed is not None and 0 <= (clock - observed).total_seconds() <= 4*3600
    expires = observed + timedelta(hours=4) if observed else None
    published = board.get('rows')
    if not isinstance(published, list):
        raise ValueError('Unsupported published board schema')
    grouped = {}
    for row in published:
        grouped.setdefault(str(row.get('fixture_id')), []).append(row)
    index = rating_index(rating_text)
    blob_sha = hashlib.sha1(f'blob {len(rating_text.encode())}\0'.encode() + rating_text.encode()).hexdigest()
    vrs_ok = bool(index and blob_sha == rating_meta.get('sha'))
    findings = []
    output = []

    def flag(code, message, fid=None, url=LOBBY):
        item = dict(code=code, fixture_id=fid, message=message, source_url=url)
        findings.append(item)
        return code

    if not freshness_ok:
        flag('inventory_stale_or_unverified', 'Lobby observation exceeds four hours, is future-dated, or lacks an auditable cache age.')
    for fx in fixtures:
        fid = str(fx['fixture_id'])
        lock = parse(fx.get('lock_utc'))
        start = parse(fx.get('start_utc'))
        due = min(lock, start) if lock and start else None
        status = str(fx.get('status', '')).lower()
        state = ('open' if due and due > clock and status in ('scheduled', 'not_started', 'not started')
                 else 'locked / past' if due and due <= clock else 'status / schedule unverified')
        url = snap['hotspawn'].get('permalinks', {}).get(fid) or LOBBY
        if not official_url(url) or urlsplit(url).hostname not in {'play.hotspawn.com', 'www.hotspawn.com'}:
            url = LOBBY
        out = dict(fixture_id=fid, team_a=fx.get('team_a'), team_b=fx.get('team_b'),
                   start_utc=fx.get('start_utc'), lock_utc=fx.get('lock_utc'), state=state,
                   hotspawn_url=url, evidence_links=[url], published_pick=None, basis=None,
                   review_status='not actionable', flags=[])
        output.append(out)
        if state != 'open':
            if state == 'status / schedule unverified':
                out['flags'].append(flag('schedule_unverified', 'Missing timezone-aware start/lock or unrecognized status.', fid, url))
            continue
        candidates = grouped.get(fid, [])
        if len(candidates) != 1:
            out['flags'].append(flag('missing_or_duplicate_pick_row', f'Expected one row, found {len(candidates)}; never silently omit this match.', fid, url))
            out['review_status'] = 'unresolved'
            continue
        r = candidates[0]
        out['published_pick'] = r.get('pick')
        res = r.get('resolution') or {}
        basis = out['basis'] = res.get('basis')
        def issue(code, message, source=url):
            out['flags'].append(flag(code, message, fid, source))
        if any(fx.get(k) != r.get(k) for k in ('team_a','team_b','start_utc','lock_utc')):
            issue('fixture_identity_conflict', 'Published names/start/lock differ from the retained lobby row.')
        if not freshness_ok:
            issue('expired_inventory', 'Current lobby membership is unverified; do not present this row as current.')
        if not r.get('pick'):
            if any(res.get(k) is not None for k in ('prob_a','prob_b')):
                issue('unresolved_with_probability', 'Unresolved row still carries probability values.')
            out['review_status'] = 'unresolved'
            issue('no_supported_pick', 'No supported directional pick published. See source research and unresolved page.')
            continue
        pa, pb = res.get('prob_a'), res.get('prob_b')
        valid = all(isinstance(x, (int,float)) and not isinstance(x,bool) and math.isfinite(x) and 0 <= x <= 1 for x in (pa,pb))
        if not valid or abs(pa + pb - 1) > .0001:
            issue('invalid_probability_pair', 'Probabilities must be finite, in [0,1] and total one.')
        elif r['pick'] != (fx['team_a'] if pa > pb else fx['team_b'] if pb > pa else None):
            issue('pick_side_conflict', 'Published pick disagrees with its win probabilities (ties have no edge).')
        links = [s.get('url') for s in r.get('sources', []) if official_url(s.get('url'))]
        out['evidence_links'] = list(dict.fromkeys([url] + links))
        if not links:
            issue('no_official_evidence_link', 'No recognized primary/HLTV evidence link accompanies this pick.')
        if basis == 'market':
            quotes = r.get('quotes') or []
            if not quotes:
                issue('missing_quote', 'Market-labelled pick has no retained two-sided quote.')
            for q in quotes:
                qurl = q.get('public_url') or q.get('api_url')
                if urlsplit(str(qurl or '')).hostname not in BOOK_HOSTS or not official_url(qurl):
                    issue('non_book_probability_source', 'A market quote lacks a recognized direct bookmaker/exchange URL.')
                t = parse(q.get('retrieved_utc'))
                if not t or not 0 <= (clock-t).total_seconds() <= 8*3600:
                    issue('quote_expired_or_unverified', 'Quote observation exceeds eight hours or is missing/future-dated.', qurl if official_url(qurl) else url)
                try:
                    a,b = float(q['decimal_a']),float(q['decimal_b'])
                    if not all(math.isfinite(x) and x > 1 for x in (a,b)):
                        raise ValueError('invalid odds')
                    expected = (1/a) / (1/a+1/b)
                    if abs(expected-float(q['prob_a'])) > .0001:
                        issue('quote_arithmetic_conflict', 'Stored no-vig probability does not reproduce from its displayed two-way odds.', qurl if official_url(qurl) else url)
                except (KeyError, ValueError, TypeError, ZeroDivisionError):
                    issue('quote_not_reproducible', 'Missing or invalid decimal odds/probability in retained quote.')
                raw = q.get('raw') or {}
                if raw.get('volume_dollars') == 0:
                    issue('zero_volume_exchange', 'Quote has zero traded volume; it is not a traded consensus.', qurl if official_url(qurl) else url)
        elif basis == 'originated_vrs':
            if not vrs_ok or not all(rating_matches(r.get('vrs_'+s) or {}, index) for s in ('a','b')):
                issue('rating_input_unverified', 'Both exact rating/standing/team/roster tuples must match the pinned official file.', rating_meta.get('html_url') or url)
            # Even matching published inputs do not validate a live roster or predicted probability.
            issue('model_not_book_odds', 'Model estimate, not an official win probability. Current lineup equivalence and predictive accuracy require separate evidence.', rating_meta.get('html_url') or url)
        else:
            issue('unsupported_probability_basis', 'Unknown or one-unranked-team floor basis: absence from a ranking does not bound a team’s strength.')
        out['review_status'] = 'flagged' if out['flags'] else 'retained arithmetic checked'
    known = {r['fixture_id'] for r in output}
    extra = []
    for fid, rows in grouped.items():
        if fid not in known:
            extra.append({'fixture_id': fid, 'team_a': rows[0].get('team_a'), 'team_b': rows[0].get('team_b'),
                          'source_url': LOBBY, 'reason': 'Published by picks board but absent from the retained lobby; API-only is not confirmed lobby coverage.'})
    opened = [r for r in output if r['state'] == 'open']
    summary = dict(listed=len(output), open=len(opened), represented=sum(r['fixture_id'] in grouped for r in opened),
                   unresolved=sum(r['review_status'] == 'unresolved' for r in opened),
                   flagged=sum(bool(r['flags']) for r in opened),
                   unsupported=sum('unsupported_probability_basis' in r['flags'] for r in opened), api_or_board_only=len(extra))
    return dict(generated_utc=iso(clock), inventory_observed_utc=iso(observed) if observed else None,
                inventory_expires_utc=iso(expires) if expires else None, inventory_fresh=freshness_ok,
                source_capture_utc=snap.get('collected_to_utc'), board_generated_utc=board.get('generated_utc'),
                source_url=LOBBY, board_path=BOARD, summary=summary, rows=output, extra_rows=extra,
                findings=findings, research=research, official_rating_file={**rating_meta, 'blob_hash_matches':vrs_ok},
                scope='All rows in the retained successful HotSpawn lobby capture, not an assertion of real-time completeness. Arithmetic checks do not verify a forecast or a current lineup.')


def esc(x):
    return html.escape(str(x if x is not None else ''), quote=True)


def render(report):
    SITE.mkdir(parents=True, exist_ok=True)
    def link(url, label):
        return f'<a href="{esc(url)}">{esc(label)}</a>'
    def page(title, body):
        return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} · CS2 coverage audit</title><link rel="icon" href="../../favicon.ico"><link rel="stylesheet" href="style.css"><script defer src="freshness.js"></script></head><body><a class="skip" href="#main">Skip to content</a><header><a href="../../index.html">CS2 MATCH DESK</a><nav aria-label="Audit navigation"><a href="../../everypick/picks.html">Picks</a><a href="index.html">Coverage audit</a><a href="flagged.html">Flagged for Review</a><a href="../../everypick/unresolved.html">Unresolved picks</a></nav></header><main id="main"><h1>{esc(title)}</h1><p class="notice" data-expires="{esc(report['inventory_expires_utc'])}">Inventory observed {esc(report['inventory_observed_utc'])}. Audit built {esc(report['generated_utc'])}. <strong id="freshness">{'Within four-hour audit window' if report['inventory_fresh'] else 'STALE / UNVERIFIED'} at build time; check timestamps before use.</strong></p>{body}</main><footer>{link('../../data/741a34ac/report.json','Download row-by-row audit')} · {link(LOBBY,'Official HotSpawn lobby')}<p>This is an evidence audit, not a second predictions dashboard. No crowd percentages, assumed ratings or new probabilities.</p></footer></body></html>'''
    s = report['summary']
    rows = []
    for r in report['rows']:
        evidence = ' · '.join(link(u, 'Official source' if i == 0 else 'Evidence '+str(i)) for i,u in enumerate(r['evidence_links']))
        rows.append(f'''<tr id="m{esc(r['fixture_id'])}"><th scope="row">{esc(r['team_a'])} vs {esc(r['team_b'])}<small>#{esc(r['fixture_id'])}</small></th><td data-label="Start / lock UTC">{esc(r['start_utc'])}<small>Lock: {esc(r['lock_utc'])}</small></td><td data-label="Listing">{esc(r['state'])}</td><td data-label="Pick audit">{esc(r['review_status'])}<small>{esc(r['published_pick'])} · {esc(r['basis'])}</small></td><td data-label="Sources">{evidence}</td></tr>''')
    extra = ''.join(f'<li>#{esc(r["fixture_id"])} {esc(r["team_a"])} vs {esc(r["team_b"])} — {esc(r["reason"])} {link(r["source_url"],"Official lobby")}</li>' for r in report['extra_rows']) or '<li>None in this capture.</li>'
    body = f'''<p class="intro">Is every listed CS2 match accounted for, and are the inputs still usable?</p><div class="metrics"><p><b>{s['listed']}</b>retained listings</p><p><b>{s['represented']} / {s['open']}</b>open matches represented</p><p><b>{s['unresolved']}</b>explicitly unresolved</p><p><b>{s['flagged']}</b>open rows to review</p></div><section><h2>Executive summary</h2><p><a class="button" href="../../everypick/picks.html">Open all picks →</a> <a class="button" href="flagged.html">Review limitations →</a></p><p>{esc(report['scope'])} A represented match may still be unresolved or have unsafe evidence; coverage is not accuracy.</p><p>Audit runs every four hours and after the existing collectors. A rebuild never resets a source timestamp. Expired inventory, unsupported probability bases, missing rows, and quote problems are published below. Schedules are best-effort, not guarantees.</p></section><section><h2>Unresolved picks &amp; limitations</h2><p>{s['unresolved']} open fixtures explicitly unresolved in the published board; <strong>{s['unsupported']} additional published picks have unsupported probability bases and must not be treated as resolved.</strong> {s['flagged']} open rows carry review findings. <a href="../../everypick/unresolved.html">Read each unresolved pick</a> and <a href="flagged.html">the independent evidence limitations</a>. A team absent from the dated official ranking does not have a known maximum strength.</p></section><section><h2>Complete retained lobby inventory</h2><p>Starts and locks are UTC. Past listings remain here for coverage auditing; they are not actionable picks.</p><table><caption>Every CS2 fixture in the retained lobby capture</caption><thead><tr><th scope="col">Match</th><th scope="col">Start / lock UTC</th><th scope="col">Listing</th><th scope="col">Pick audit</th><th scope="col">Sources</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section><section><h2>API / board-only listings</h2><ul>{extra}</ul></section>'''
    (SITE/'index.html').write_text(page('Match coverage & freshness',body))
    flags = ''.join(f'<tr><th scope="row">{esc(f["fixture_id"] or "Board")}</th><td data-label="Finding">{esc(f["code"])}<p>{esc(f["message"])}</p></td><td data-label="Source">{link(f["source_url"],"Official source")}</td></tr>' for f in report['findings']) or '<tr><td colspan="3">No automated findings in this retained capture.</td></tr>'
    research = ''.join(f'<article><h3>{esc(r["title"])}</h3><p>{esc(r["finding"])}</p><p>Read {esc(r["read_date_utc"])} via {esc(r["method"])}. {" · ".join(link(u,"Source "+str(i+1)) for i,u in enumerate(r["urls"]))}</p></article>' for r in report['research'])
    (SITE/'flagged.html').write_text(page('Flagged for Review',f'<p>Findings are non-blocking disclosures, not permission to fill unsupported cells. Exact live lineup and current prices require a new source observation.</p><h2>Source-reviewed irregularities</h2>{research}<h2>Automatic row-by-row findings</h2><table><caption>Coverage and evidence limitations</caption><thead><tr><th scope="col">Fixture</th><th scope="col">Finding</th><th scope="col">Source</th></tr></thead><tbody>{flags}</tbody></table>'))


def main():
    p=argparse.ArgumentParser(); p.add_argument('--at',help='Explicit UTC replay clock (otherwise actual UTC)'); args=p.parse_args()
    clock=parse(args.at) if args.at else datetime.now(timezone.utc)
    if clock is None: p.error('--at must be timezone aware')
    source = 'data/741a34ac/lobby_snapshot.json'
    upstream=read(SNAPSHOT)
    own=read(source) if (ROOT/source).exists() else None
    # Prefer an independent observation only if it is newer than the retained upstream capture.
    snap=max([s for s in (upstream,own) if s],key=lambda s: parse(s.get('collected_to_utc')) or datetime.min.replace(tzinfo=timezone.utc))
    report=audit(snap,read(BOARD),(DATA/'valve-standings.md').read_text(),read('data/741a34ac/valve-file.json'),clock,read('data/741a34ac/research.json'))
    report['inventory_input']=source if snap is own else SNAPSHOT
    logpath=DATA/'collection.json'
    report['latest_collection_attempt']=json.loads(logpath.read_text()) if logpath.exists() else {}
    for key,attempt in report['latest_collection_attempt'].items():
        if attempt.get('error'):
            report['findings'].append(dict(code='source_collection_failed',fixture_id=None,
                message=key+': '+attempt['error']+'; prior observation retained without resetting its age.',source_url=attempt['url']))
    DATA.mkdir(parents=True,exist_ok=True); (DATA/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    render(report)
    print(json.dumps(report['summary']), 'inventory_fresh=',report['inventory_fresh'])

if __name__=='__main__': main()
