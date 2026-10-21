#!/usr/bin/env python3
"""Evidence-only report and mobile site. Missing evidence is never a 50/50 guess."""
import copy
import hashlib
import html
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from common import ROOT, DATA, SITE, CORE, now, read, write, strict_join, RULES, PAYLOAD_VERIFIER

LOBBY = 'https://play.hotspawn.com/lobby'
VRS_REPO = 'https://github.com/ValveSoftware/counter-strike_regional_standings'
HOURS = 8


def esc(x):
    return html.escape(str(x if x is not None else ''), quote=True)


def stamp(x):
    return str(x or 'unverified').replace('T', ' ').replace('Z', ' UTC')


def parse(x):
    return CORE.parse_any(x)


def select_input():
    candidates = []
    for folder in (DATA / 'upstream', ROOT / 'data/f7279a54'):
        b = read(folder / 'board.json', {})
        s = read(folder / 'snapshot.json', {})
        if b.get('generated_utc') and s.get('collected_to_utc'):
            # A board and its raw capture must belong to exactly the same collection.
            if b['generated_utc'] != s['collected_to_utc']:
                continue
            candidates.append((s['collected_to_utc'], folder, b, s))
    if not candidates:
        raise ValueError('No internally consistent board/raw snapshot pair')
    _, folder, b, s = max(candidates, key=lambda x: x[0])
    return folder, b, s


def ratings(md):
    groups = {}
    for m in re.finditer(r'^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]+)\|([^|]*)\|\s*\[details\]\(([^)]+)\)', md, re.M):
        r = dict(standing=int(m[1]), points=int(m[2]), team=m[3].strip(), roster=m[4].strip(), details=m[5])
        groups.setdefault(CORE.canon(r['team'])[0], []).append(r)
    return groups


def model_pair(row, index):
    pair = [index.get(CORE.canon(row['team_' + side])[0], []) for side in ('a', 'b')]
    return [rs[0] for rs in pair] if all(len(rs) == 1 for rs in pair) else None


def quoted_consensus(row):
    entries = []
    for q in row.get('quotes', []):
        source = {'team_a': q['names_at_source'][0], 'team_b': q['names_at_source'][1],
                  'start_utc': q.get('start_utc_at_source')}
        joined = strict_join(row, source)
        if not joined or joined['swapped'] != q['swapped']:
            raise ValueError('Stored quote no longer passes strict identity/time join')
        raw = CORE.rederive_quote(q)
        if not raw:
            raise ValueError('Invalid raw odds')
        p = 1 - raw['prob_a'] if q['swapped'] else raw['prob_a']
        if abs(p - q['no_vig_prob_team_a']) > .000051:
            raise ValueError('Stored no-vig probability does not reproduce')
        entries.append({'source_key': q['source_key'], 'prob_a': p})
    return CORE.consensus(entries)


def resolve(board, snap, research, md, clock):
    index = ratings(md)
    official = research.get('valve', {})
    # Only use the exact latest verified official file. A fresh HTTP read does not
    # make dated standings current; we explicitly disclose the rating date/age.
    date_match = re.search(r'(\d{4}_\d{2}_\d{2})', official.get('latest_file', ''))
    rating_date = parse(date_match[1].replace('_', '-') + 'T00:00:00Z') if date_match else None
    fresh_check = parse(official.get('checked_utc'))
    blob_hash = hashlib.sha1(f'blob {len(md.encode())}\0'.encode() + md.encode()).hexdigest()
    vrs_ok = bool(rating_date and fresh_check and -300 <= (clock-fresh_check).total_seconds() <= HOURS*3600
                  and 0 <= (clock-rating_date).days <= 35 and blob_hash == official.get('sha'))
    # Independently calibrate ONLY from raw current market prices + two unique
    # official ratings. No historical derived line/HotSpawn crowd is a training target.
    pairs = []
    for r in board.get('open', []):
        if (r.get('line') or {}).get('basis') != 'market':
            continue
        pair = model_pair(r, index)
        con = quoted_consensus(r)
        if pair and con:
            pairs.append({'delta': pair[0]['points']-pair[1]['points'], 'market_prob_a': con['prob_a'],
                          'fixture_id': r['fixture_id']})
    calibration = CORE.fit_calibration(pairs)
    # No uncalibrated model masquerading as a usable pick.
    model_ok = vrs_ok and calibration['fitted']
    inventory = [copy.deepcopy(r) for r in snap['hotspawn']['fixtures'] if 'lobby_page' in r.get('seen_in', [])]
    lookup = {r['fixture_id']: r for r in board.get('open', [])}
    page_meta = board['access'].get('hotspawn_lobby_page', {})
    observed = parse(page_meta.get('at_utc'))
    observed = observed - timedelta(seconds=float(page_meta.get('age_header') or 0)) if observed else None
    source_expiry = observed + timedelta(hours=4) if observed else clock
    collected = parse(snap['collected_to_utc'])
    end = min(source_expiry, collected + timedelta(hours=4))
    rows = []
    for fx in inventory:
        fid = fx['fixture_id']
        r = lookup.get(fid, fx)
        lock = parse(fx.get('lock_utc')) or parse(fx.get('start_utc'))
        row = {k: fx.get(k) for k in ('fixture_id','team_a','team_b','competition','status','start_utc','lock_utc')}
        row.update({'hotspawn_url': snap['hotspawn'].get('permalinks', {}).get(fid) or LOBBY,
                    'pick': None, 'prob_a': None, 'prob_b': None, 'basis': None, 'quotes': [],
                    'flags': [], 'attempts': [], 'sources': [{'label': 'HotSpawn fixture inventory', 'url': LOBBY}],
                    'valid_until_utc': CORE.to_iso(min(end, lock)) if lock else CORE.to_iso(end)})
        if row['hotspawn_url'] != LOBBY:
            row['sources'].append({'label': 'Official match permalink', 'url': row['hotspawn_url']})
        row['state'] = ('open' if lock and lock > clock and fx.get('status') == 'scheduled'
                        else 'status conflict' if lock and lock > clock else 'locked / past')
        if not lock:
            row['state'] = 'unverified schedule'
        if row['state'] != 'open':
            row['flags'] = ['Not an actionable pick: deadline passed, missing schedule, or conflicting status.']
            rows.append(row)
            continue
        row['attempts'] = [{'source': k, 'status': v.get('status'), 'url': v.get('url'), 'error': v.get('error')}
                           for k, v in board['access'].items() if k in ('pinnacle','bovada','melbet','kalshi','hltv_probe')]
        if end <= clock:
            row['flags'].append('Fixture/quote capture expired; probabilities suppressed until successful refresh.')
        elif fid in lookup and (r.get('line') or {}).get('basis') == 'market':
            con = quoted_consensus(r)
            if not con or abs(round(con['prob_a'], 4)-r['line']['prob_a']) > .000001:
                raise ValueError(f'{fid}: featured market does not reproduce')
            row.update(basis='featured market', prob_a=r['line']['prob_a'], prob_b=r['line']['prob_b'],
                       quotes=copy.deepcopy(r['quotes']))
        else:
            # Research must be fresh, and joins independently require both names,
            # pre-match state and a verified source kickoff within the strict window.
            extras = []
            exchange_quotes = RULES.enrich_quotes(research.get('exchange_quotes', []), research.get('exchange_payload', {}))
            eligible_exchange = [q for q in exchange_quotes if q.get('kickoff_evidence')
                                 and all(float(o.get('volume_contracts_reported') or 0) >= 20 for o in q['kickoff_evidence']['outcomes'])]
            for q in research.get('quotes', []) + eligible_exchange:
                age = (clock-parse(q['retrieved_utc'])).total_seconds() if parse(q.get('retrieved_utc')) else 1e9
                join = strict_join(fx, q)
                nv = CORE.rederive_quote(q)
                if join and nv and not q.get('live') and -300 <= age <= 4*3600:
                    extras.append({**q, 'swapped': join['swapped'], 'prob_a': 1-nv['prob_a'] if join['swapped'] else nv['prob_a']})
            # Deduplicate provider/event, not one vote per duplicate response/page.
            extras = list({(q['source_key'], q['event_id']): q for q in extras}.values())
            if extras and end > clock:
                pa = sum(q['prob_a'] for q in extras)/len(extras)
                exchange = all(q['source_key']=='kalshi' for q in extras)
                row.update(basis='rule-backed exchange' if exchange else 'secondary published odds', prob_a=round(pa,4), prob_b=round(1-pa,4), quotes=extras)
                row['flags'].append('Normalized exchange midpoints, not executable bookmaker odds; contract rules verify kickoff; liquidity/accuracy not guaranteed.' if exchange else 'Secondary odds publisher; not independently confirmed on bookmaker site.')
            elif model_ok and end > clock and (pair := model_pair(fx,index)):
                pa = CORE.vrs_prob(pair[0]['points'], pair[1]['points'], calibration['k'])
                row.update(basis='originated rating model', prob_a=round(pa,4), prob_b=round(1-pa,4), ratings=pair)
                row['flags'].append('Experimental computed estimate, not a bookmaker line or verified win chance. '
                                    f"Standings dated {rating_date.date()} ({(clock-rating_date).days} days old); current roster not confirmed.")
                row['sources'].append({'label': 'Valve official standings (retained hash)', 'url': official['source_url']})
            else:
                for side in ('a','b'):
                    candidates = index.get(CORE.canon(fx['team_'+side])[0], [])
                    if len(candidates) != 1:
                        row['flags'].append(f"{fx['team_'+side]}: " + ('ambiguous Valve rosters' if candidates else 'no exact unique Valve rating'))
                if not model_ok:
                    row['flags'].append('Model unavailable: fresh latest-file verification and ≥6 current market calibration pairs required.')
                row['flags'].append('No verified eligible two-sided match-winner price; pick and probabilities left blank / unverified.')
        if row['prob_a'] is not None:
            row['pick'] = row['team_a'] if row['prob_a'] > row['prob_b'] else row['team_b'] if row['prob_b'] > row['prob_a'] else None
            if not row['pick']:
                row['flags'].append('Priced tie: no evidence-backed directional edge.')
            for q in row['quotes']:
                row['sources'].append({'label': q.get('source_name', q['source_key']), 'url': q['public_url']})
        for rd in research.get('reads', []):
            if rd.get('kind') in ('hltv','bo3gg'):
                row['attempts'].append({k:rd.get(k) for k in ('url','status','error','at_utc','kind')})
        rows.append(row)
    counts = Counter(r['state'] for r in rows)
    opened = [r for r in rows if r['state']=='open']
    return {'generated_utc': CORE.to_iso(clock), 'capture_utc': snap['collected_to_utc'],
            'inventory_observed_utc': CORE.to_iso(observed), 'valid_until_utc': CORE.to_iso(end),
            'week': snap['hotspawn'].get('week'), 'calibration': {**calibration,'pairs':pairs}, 'valve': official,
            'summary': {'listed':len(rows),'open':len(opened),'with_pick':sum(bool(r['pick']) for r in opened),
                        'unresolved':sum(not r['pick'] for r in opened), 'featured':sum(r['basis']=='featured market' for r in opened),
                        'secondary':sum(r['basis']=='secondary published odds' for r in opened),
                        'exchange':sum(r['basis']=='rule-backed exchange' for r in opened),
                        'model':sum(r['basis']=='originated rating model' for r in opened),
                        'locked_or_conflicting':len(rows)-len(opened)},
            'source_access': board['access'], 'rows':rows}


def links(row):
    return '<br>'.join(f'<a href="{esc(s["url"])}" rel="noreferrer">{esc(s["label"])}</a>' for s in row['sources'])


def table(rows, evidence=False):
    out = []
    for r in rows:
        p = lambda x: f'{x*100:.1f}%' if x is not None else '—'
        odds = ''
        if evidence:
            odds = '<details><summary>Raw odds &amp; attempts</summary>'
            for q in r['quotes']:
                odds += f'<p>{esc(q.get("source_name", q["source_key"]))}: {esc(q.get("names_at_source") or [q.get("team_a"),q.get("team_b")])} · {esc(q["raw_a"])} / {esc(q["raw_b"])} ({esc(q["raw_format"])}) · read {esc(q["retrieved_utc"])} · <a href="{esc(q["api_url"])}">raw source API</a></p>'
            for a in r['attempts']:
                odds += f'<p><a href="{esc(a["url"])}">{esc(a.get("source") or a.get("kind") or "source")}</a> · HTTP {esc(a.get("status"))} {esc(a.get("error"))}</p>'
            odds += '</details>'
        out.append(f'''<tr id="m{esc(r['fixture_id'])}" data-state="{esc(r['state'])}" data-expiry="{esc(r['valid_until_utc'])}">
<td data-label="Match"><strong>{esc(r['team_a'])} <span class="muted">vs</span> {esc(r['team_b'])}</strong><small>{esc(r['competition'])} · #{esc(r['fixture_id'])}</small><small>{esc(stamp(r['start_utc']))}</small><small>Locks {esc(stamp(r['lock_utc']))}</small></td>
<td data-label="Our pick"><strong class="pick">{esc(r['pick']) if r['pick'] else '— Unresolved / no edge'}</strong><small>{esc(r['basis'] or r['state'])}</small><span class="expiry-note" role="status"></span></td>
<td data-label="Win probabilities"><div class="prob">{esc(r['team_a'])} <b>{p(r['prob_a'])}</b></div><div class="prob">{esc(r['team_b'])} <b>{p(r['prob_b'])}</b></div></td>
<td data-label="Evidence & limitations">{links(r)}<small>{esc(' '.join(r['flags']))}</small>{odds}</td></tr>''')
    return '<table><caption>Every row retains its official fixture inventory source. Computed estimates are explicitly labelled.</caption><thead><tr><th scope="col">Match / UTC</th><th scope="col">Our pick</th><th scope="col">Win probabilities</th><th scope="col">Sources / limitations</th></tr></thead><tbody>'+''.join(out)+'</tbody></table>' if out else '<p>No matches in this category in the retained capture.</p>'


def page(title, body, report):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} · CS2 match desk</title><link rel="stylesheet" href="style.css"><script defer src="app.js"></script></head><body><a class="skip" href="#main">Skip to content</a><header><a class="brand" href="index.html">CS2 / MATCH DESK</a><nav aria-label="Main"><a href="index.html">Summary</a><a href="picks.html">All picks</a><a href="unresolved.html">Unresolved</a><a href="sources.html">Sources</a><a href="flagged.html">Flagged for Review</a></nav></header><main id="main"><p class="eyebrow">HOTSPAWN FIXTURES · INDEPENDENT EXTERNAL LINES</p><h1>{esc(title)}</h1><div class="freshness" data-capture-expiry="{esc(report['valid_until_utc'])}">Source capture: {esc(stamp(report['capture_utc']))}. Inventory cache observed: {esc(stamp(report['inventory_observed_utc']))}. <span class="capture-status"></span></div>{body}</main><footer>Probabilities are estimates, not guarantees or advice to wager. HotSpawn supplies fixtures only; crowd selections never price a match. <a href="../research.html">Research archive</a> · <a href="../index.html">Site home</a> · <a href="../data/cbf92764/report.json">Download evidence report</a></footer></body></html>'''


def build():
    folder,b,s = select_input()
    research = read(DATA/'research.json', {})
    md = (DATA/'valve-standings.md').read_text() if (DATA/'valve-standings.md').exists() else ''
    # Replay the official bookmaker response JSON, not just normalized quote fields.
    provider_replay = PAYLOAD_VERIFIER.verify(folder)
    if provider_replay['failures']:
        raise ValueError('Official provider payload replay failed: ' + '; '.join(provider_replay['failures']))
    report = resolve(b,s,research,md,now())
    report['provider_replay'] = provider_replay
    report['input'] = {'folder':str(folder.relative_to(ROOT)), 'board_sha256':hashlib.sha256((folder/'board.json').read_bytes()).hexdigest(),
                       'snapshot_sha256':hashlib.sha256((folder/'snapshot.json').read_bytes()).hexdigest()}
    write(DATA/'report.json',report)
    SITE.mkdir(parents=True,exist_ok=True)
    c=report['summary']; opened=[r for r in report['rows'] if r['state']=='open']; unresolved=[r for r in opened if not r['pick']]
    actions='<div class="actions"><a class="primary" href="picks.html">See every updated pick →</a><a href="unresolved.html">Unresolved &amp; limitations</a></div>'
    summary=f'''<p class="intro">One match list. A clear pick, both win probabilities, and the evidence behind them.</p>{actions}
<div class="metrics"><div><b>{c['open']}</b>Open matches</div><div><b>{c['with_pick']}</b>With a pick</div><div><b>{c['unresolved']}</b>Unresolved / no edge</div></div>
<section><h2>Executive summary</h2><p>{c['listed']} CS2 fixtures retained from the lobby. {c['featured']} featured market lines are preserved; {c['secondary']} additional secondary price lines; {c['exchange']} official rule-backed exchange lines; {c['model']} explicitly labelled originated rating estimates. {c['locked_or_conflicting']} past, locked or status-conflicting listings remain visible in <a href="inventory.html">the complete inventory</a>, not presented as actionable picks.</p><p>Automatic checks target every four hours. The existing market collector also refreshes more often. GitHub schedules are best-effort, not a freshness guarantee. Expired rows are visibly disabled rather than silently kept as current.</p></section>
<section id="unresolved"><h2>Unresolved picks &amp; limitations</h2><p><strong>{c['unresolved']} open matches have no supported directional pick.</strong> We try HLTV, external esportsbooks/exchanges and published esports odds, then our documented rating model. Blocked access, absent two-way odds, ambiguous rosters or insufficient evidence leave values blank and flagged. An unlisted team is never assigned the lowest rating or an invented 50% line.</p><a href="unresolved.html">Review each unresolved fixture and source attempts →</a></section>
<section><h2>Find what you need</h2><div class="cards"><a href="picks.html"><h3>All current picks</h3><p>Team, win chance, deadline and source in a phone-friendly table.</p></a><a href="sources.html"><h3>Method &amp; evidence</h3><p>Raw odds, no-vig calculation, rating model and access logs.</p></a><a href="flagged.html"><h3>Flagged for Review</h3><p>Unverified values, source failures, stale inputs and inherited repository defects.</p></a></div></section>'''
    filter_ui='<label for="search">Find a team or tournament</label><input id="search" type="search" placeholder="Search matches…"><p id="filter-count" aria-live="polite"></p>'
    research_text=f'''<h2>Source hierarchy</h2><ol><li>Preserve eligible featured Pinnacle, Bovada and Melbet match-winner consensus, or independently timestamped exchange prices. No dependence on Polymarket coverage.</li><li>Only for missing featured prices: try HLTV first (never bypass its access controls), then esportsbook/exchange feeds and bo3.gg published coefficients. A secondary publisher is labelled, not claimed as direct bookmaker verification. Official Kalshi rules can verify an explicit full-match kickoff and both yes bid/ask midpoints; both sides need narrow spreads and ≥20 reported contracts. Normalized midpoints are not executable odds; zero-volume 50/50 quotes do not overrule a rating estimate.</li><li>If no eligible price exists: originate a separate experimental rating-model estimate only from two unique official Valve ratings, a fresh check of the latest official file (≤8 h), dated standings ≤35 days old, and at least six current matched market/rating calibration pairs. Duplicate-name rosters are refused.</li><li>If evidence is still inadequate, retain the row with blank probabilities/pick and the reason. No lowest-ranked proxy, no unsupported aliases or fabricated research.</li></ol>
<h2>Calculations, not source facts</h2><p>For decimal odds a,b: P(A)=(1/a)/((1/a)+(1/b)); P(B)=1−P(A). Consensus uses the existing source weights (Pinnacle 2; others 1) with one vote per source. Featured probabilities are replayed from raw odds and must match the upstream line to 0.0001.</p><p>Originated model: P(A)=1/(1+exp(−k·g·ln(10)/400·(ratingA−ratingB))), with g=1/sqrt(1+3·(ln(10)/400)²·75²/π²). k is a bounded through-origin least-squares fit of market logits against rating deltas using only this capture's prices. This is an unvalidated market-calibrated estimate, not a verified outcome probability or a backtested accuracy claim. It does not account for current veto, lineup or format changes.</p><p>Current calibration: {report['calibration']['n_pairs']} pairs; k={report['calibration']['k']:.4f}; fitted={report['calibration']['fitted']}. <a href="{VRS_REPO}/blob/main/model/glicko.js">Valve model</a> · <a href="{VRS_REPO}/blob/main/model/fit.js">Valve fitting code</a> · <a href="{VRS_REPO}">Official repository and caveats</a>.</p>
<h2>Coverage &amp; freshness</h2><p>The public lobby transfer state defines membership; the fixtures API is also checked, but its thousands of historical rows do not expand lobby membership. Missing page access preserves the last inventory with its original observation time. HTTP cache Age reduces the usable lifetime. Quotes and fixtures expire after four hours or the lock deadline, whichever is sooner. Started/ended/conflicting rows cannot become current picks. A refresh can legitimately find fewer matches; no count is hard-coded.</p><p><a href="../data/cbf92764/research.json">Raw fallback research</a> · <a href="../data/cbf92764/valve-standings.md">Exact retained Valve file</a> · <a href="../data/cbf92764/report.json">Per-row report, source hashes and calibration pairs</a>.</p>'''
    access='<table><caption>Latest upstream source access; HTTP success does not prove match coverage.</caption><thead><tr><th>Source</th><th>Read (UTC)</th><th>Result</th><th>Official endpoint</th></tr></thead><tbody>'+''.join(f'<tr><td data-label="Source">{esc(k)}</td><td data-label="Time">{esc(stamp(v.get("at_utc")))}</td><td data-label="Result">HTTP {esc(v.get("status"))} {esc(v.get("error"))}</td><td data-label="Source"><a href="{esc(v.get("url"))}">Source endpoint</a></td></tr>' for k,v in report['source_access'].items())+'</tbody></table>'
    flags='''<h2>Non-blocking findings — not claimed as verified</h2><ul><li>HLTV access may return HTTP 403. A blocked read is not "no match" or proof of team strength.</li><li>Valve standings are a dated roster-specific rating file. Duplicate organisation names are not resolved by choosing the most recently active roster. A team absent from the file is not assumed weaker than every rated team.</li><li>Some HotSpawn scheduled fixtures remain listed after their deadlines, or have conflicting statuses. See the complete inventory; no past fixture is promoted to a current pick.</li><li>The independent <a href="../cs2/index.html">cs2 research board</a> assigns an unrated opponent the lowest published Valve rating. Absence from a ranking does not establish that bound; this desk refuses that assumption. It also uses a CYBERSHOKE / ex-CYBERSHOKE name join and mixed best prices from an aggregator, not a directly replayed single-book two-way quote. Those outputs remain preserved for review, not imported into these probabilities. <a href="https://github.com/buffedlizard55-lab/MaltaProj2/blob/main/scripts/e1b48771/resolutions.json">Published assumptions</a> · <a href="https://github.com/ValveSoftware/counter-strike_regional_standings">Official ratings</a>.</li><li>Historical parallel desks and tournament-day summaries can be stale or use different source policies. They remain archived; this dashboard does not certify their claims.</li><li>The inherited repository-wide test suite had dynamic-date/fixture assumptions, generic Python import collisions and stale generated artifacts at the start of this session. Integration findings and repairs are recorded in <a href="https://github.com/buffedlizard55-lab/MaltaProj2/blob/main/COORDINATION.md">COORDINATION.md</a>. A passing new-section check is not a claim that all historical prose was independently verified.</li></ul><p><a href="unresolved.html">All currently unresolved rows</a> · <a href="inventory.html">Past / conflicting source rows</a> · <a href="sources.html">Source ledger &amp; reproducible calculations</a></p>'''
    bodies={'index.html':('Your CS2 picks, in one place',summary),
            'picks.html':('All current CS2 picks',filter_ui+table(opened)+actions),
            'unresolved.html':('Unresolved picks & limitations',f'<p>{c["unresolved"]} open fixtures. No unsupported pick is filled in. These are missing-evidence findings, not recommendations to guess.</p>'+table(unresolved,True)),
            'inventory.html':('Complete HotSpawn CS2 inventory',f'<p>All {c["listed"]} lobby-listed CS2 fixtures in the capture, including past and conflicting records. See <a href="picks.html">current picks</a> for actionable rows.</p>'+filter_ui+table(report['rows'])),
            'sources.html':('Method & sources',research_text+access+'<h2>Line-by-line evidence</h2>'+table(opened,True)),
            'flagged.html':('Flagged for Review',flags+table(unresolved,True))}
    for name,(title,body) in bodies.items():
        (SITE/name).write_text(page(title,body,report))
    print(report['summary'])
    return report

if __name__=='__main__':
    build()
