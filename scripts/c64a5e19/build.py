#!/usr/bin/env python3
"""Every listed CS2 fixture; strict market-first estimates, never forced numeric coverage.

Reuses the maintained strict engine. Missing/ambiguous identities are not assigned another
roster's rating, floor rating, an unrelated slot price, or a guessed 50/50 probability.
"""
from __future__ import annotations
import copy
import html
import importlib.util
import json
from pathlib import Path
from verified_engine import load_engine
from research import fallback_review, limitations

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/c64a5e19'
SITE = ROOT / 'picks-every-match'
LOBBY = 'https://play.hotspawn.com/lobby'
ENGINE = load_engine('build.py')
core = ENGINE.core
rating_index = ENGINE.rating_index
POLICY = 'verified-every-match-v3'
# Canonical-only extension; shared-engine files and sibling boards are unchanged.
_rule_spec = importlib.util.spec_from_file_location('canonical_rule_kickoffs', ROOT / 'scripts/69e4c06a/kalshi.py')
RULES = importlib.util.module_from_spec(_rule_spec)
_rule_spec.loader.exec_module(RULES)
_clock_spec = importlib.util.spec_from_file_location('canonical_retained_clocks', ROOT / 'scripts/69e4c06a/refresh.py')
CLOCKS = importlib.util.module_from_spec(_clock_spec)
_clock_spec.loader.exec_module(CLOCKS)


def esc(value):
    return html.escape('' if value is None else str(value), quote=True)


def load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def pct(value):
    return f'{value * 100:.1f}%' if isinstance(value, (int, float)) else '—'


def build_board(snap, snap_source, now=None):
    # Explicit evaluation time makes replay deterministic. CLI renders at wall clock,
    # without changing a single source observation time in the stored snapshot.
    evaluated = core.to_iso(now) if now else snap['collected_to_utc']
    inputs = copy.deepcopy(snap)
    inputs['collected_to_utc'] = evaluated
    fixture_clock_review = CLOCKS.scope_fixture_clock(inputs, core)
    primary_inputs = copy.deepcopy(inputs)
    primary_inputs['quotes'] = [q for q in inputs.get('quotes', []) if not q.get('fallback_only')]
    primary = ENGINE.build_board(primary_inputs, {}, {}, {})
    inputs['quotes'], exclusions = RULES.select_for_gaps(inputs, primary, core)
    board = ENGINE.build_board(inputs, {}, {}, {})
    primary_rows = {r['fixture_id']: r for r in primary['open']}
    retained = {(q['source_key'], q['event_id']): q for q in inputs['quotes']}
    board['source_policy_exclusions'] = exclusions
    board['fixture_clock_review'] = fixture_clock_review
    board.update(policy=POLICY, snapshot_source=snap_source,
                 collected_to_utc=snap['collected_to_utc'], generated_utc=evaluated)
    # Use fallback research only for rows without accepted prices: strict engine.blend
    # returns the market alone when present; it does not alter featured picks with VRS.
    for row in board['open']:
        line = row['line']
        row['sources'] = [{'label': 'HotSpawn fixture', 'url': row['hotspawn_url']}]
        row['sources'] += [{'label': q['source_name'], 'url': q['api_url']} for q in row['quotes']]
        rule_quotes = []
        for quote in row['quotes']:
            proof = retained.get((quote['source_key'], quote['event_id']), {}).get('kickoff_evidence')
            if proof:
                quote['kickoff_evidence'] = copy.deepcopy(proof)
                rule_quotes.append(quote)
        if rule_quotes:
            row['gap_research'] = fallback_review(primary_rows[row['fixture_id']], snap, core)
            row['market_gap_resolution'] = 'Explicit full-match Kalshi rules verify kickoff; normalized exchange midpoints only.'
            row['flags'] += ['rule_backed_exchange_fallback', 'exchange_midpoints_not_executable_bookmaker_odds',
                             'exchange_volume_may_be_low_or_zero']
        if line:
            line['tier'] = 'B' if line['basis'] == 'model' else 'A'
            if line['tier'] == 'B':
                row['sources'].append({'label': 'Valve standings (model input)', 'url': board['vrs']['page_url']})
                row['flags'].append('model_estimate_not_verified_win_probability')
            if line['prob_a'] == line['prob_b']:
                line['pick_team'] = None
                line['pick_side'] = None
        row['fallback'] = None
        row['research'] = fallback_review(row, snap, core)
        row['flags'] = sorted(set(row['flags']))
    by_id = {r['fixture_id']: r for r in board['open']}
    inventory = []
    for fixture in snap['hotspawn']['fixtures']:
        if 'lobby_page' not in fixture.get('seen_in', []):
            continue  # API-only records are not evidence of current lobby membership
        fid = fixture['fixture_id']
        inventory.append({**fixture, 'state': 'open' if fid in by_id else 'locked / past / unverified',
                          'hotspawn_url': snap['hotspawn'].get('permalinks', {}).get(fid) or LOBBY})
    board['inventory'] = sorted(inventory, key=lambda r: (r['start_utc'], r['fixture_id']))
    s = board['summary']
    s.update(captured_quotes_total=len(snap.get('quotes', [])),
             rule_backed_quotes_excluded_by_gap_policy=len(exclusions),
             with_pick=sum(bool(r['line'] and r['line']['pick_team']) for r in board['open']),
             tier_a_market=s['market_based'], tier_b_model=s['model_only'], tier_c_fallback=0,
             tier_d_none=s['no_line'], listed=len(inventory))
    return board


CSS = '''
:root{color-scheme:dark;--bg:#0c131c;--panel:#141f2c;--line:#2d3c4d;--text:#edf3fa;--muted:#b2c0d0;--green:#69e4bd;--amber:#ffce80}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}a{color:#92caff;text-underline-offset:3px}a:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--amber);outline-offset:3px}header{border-bottom:1px solid var(--line);background:#101a26}.wrap{max-width:1120px;margin:auto;padding:20px}header .wrap{padding-top:12px;padding-bottom:12px}.brand{font-weight:750;letter-spacing:.02em}nav{display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:8px}nav a{padding:8px 0;min-height:44px;text-decoration:none}nav a[aria-current]{color:var(--green);font-weight:700}.skip{position:absolute;left:-9999px}.skip:focus{position:static}h1{font-size:clamp(1.9rem,5vw,2.7rem);line-height:1.15;margin:10px 0 16px}h2{font-size:1.3rem;margin-top:28px}.eyebrow{color:var(--green);font-size:.8rem;text-transform:uppercase;letter-spacing:.1em;font-weight:700}.muted,.small{color:var(--muted)}.small{font-size:.85rem}.hero{padding:14px 0 20px;max-width:780px}.actions{display:flex;flex-wrap:wrap;gap:12px}.button{padding:12px 18px;border-radius:8px;display:inline-block;border:1px solid var(--line);text-decoration:none;font-weight:700;min-height:48px}.primary{background:var(--green);color:#09241e}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0}.stat,.panel{border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:16px}.stat b{display:block;font-size:1.8rem}.stat span{font-size:.85rem;color:var(--muted)}.notice{border-left:3px solid var(--amber);padding:12px 16px;background:#282215;color:#ffe3b4;margin:16px 0}.filters{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0;align-items:end}.filters label{flex:1;min-width:150px}.filters input,.filters select{display:block;width:100%;font:inherit;padding:10px;background:var(--panel);color:var(--text);border:1px solid #607187;border-radius:8px;min-height:44px}table{width:100%;border-collapse:collapse;font-size:.9rem}caption{text-align:left;padding:8px 0;color:var(--muted)}th{text-align:left;color:var(--muted);font-size:.75rem;text-transform:uppercase;letter-spacing:.04em}td,th{padding:16px 10px;border-bottom:1px solid var(--line);vertical-align:top}td{overflow-wrap:anywhere}.teams{display:grid;grid-template-columns:1fr auto;gap:6px 18px;min-width:170px}.prob{font-variant-numeric:tabular-nums;font-weight:700}.pick{display:block;color:var(--green);font-weight:750;font-size:1rem}.badge{display:inline-block;border:1px solid var(--line);border-radius:5px;padding:2px 7px;font-size:.75rem;margin-top:6px}.model{color:var(--amber)}.sources a{display:inline-block;padding:5px 0;min-height:32px;margin-right:10px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.panel p{margin:8px 0}.expired .estimate{display:none}.expired .expired-label{display:block!important;color:var(--amber)}[hidden]{display:none!important}footer{border-top:1px solid var(--line);margin-top:32px;padding-top:20px}.nowrap{white-space:nowrap}
@media(max-width:700px){.wrap{padding:16px}.stats{grid-template-columns:repeat(2,1fr);gap:8px}table,tbody,tr,td{display:block;width:100%}thead{display:none}tr{border:1px solid var(--line);border-radius:12px;margin-bottom:14px;background:var(--panel);padding:8px}td{border:0;padding:8px}td:before{content:attr(data-label);display:block;text-transform:uppercase;font-size:.7rem;color:var(--muted);letter-spacing:.04em;margin-bottom:4px}.teams{min-width:0}.sources a{min-height:44px}nav{font-size:.88rem}.stat{padding:12px}}
'''
JS = '''
(() => {
 const rows = [...document.querySelectorAll('[data-match]')];
 function filter() {
  const query = (document.querySelector('#search')?.value || '').trim().toLowerCase();
  const basis = document.querySelector('#basis')?.value || '';
  rows.forEach(r => r.hidden = !r.dataset.search.includes(query) || !!(basis && r.dataset.basis !== basis));
  const count = document.querySelector('#visible-count');
  if (count) count.textContent = rows.filter(r => !r.hidden).length + ' matches shown';
 }
 function expire() {
  const now = Date.now(); let expired = 0;
  rows.forEach(r => {
   const end = Date.parse(r.dataset.until || r.dataset.expires), lock = Date.parse(r.dataset.lock);
   const stale = (!Number.isFinite(end) || now >= end || !Number.isFinite(lock) || now >= lock);
   r.classList.toggle('expired', stale);
   if (stale) expired++;
  });
  const note = document.querySelector('#expiry-note');
  if (note) { note.hidden = !expired; note.textContent = expired + ' rows are past their evidence deadline or pick lock. Estimates are hidden; wait for the next automatic update.'; }
 }
 document.querySelector('#search')?.addEventListener('input', filter);
 document.querySelector('#basis')?.addEventListener('change', filter);
 filter(); expire(); setInterval(expire,30000);
 document.querySelectorAll('time[data-local]').forEach(e => { const d = new Date(e.dateTime); if (!isNaN(d)) {e.title=e.dateTime + ' UTC';e.textContent=d.toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZoneName:'short'});} });
})();
'''
NAV = [('index.html', 'Overview'), ('picks.html', 'All picks'), ('inventory.html', 'Full inventory'),
       ('unresolved.html', 'Unresolved picks'), ('flagged.html', 'Flagged for Review'), ('method.html', 'Method & sources')]


def page(title, active, body, b):
    nav = ''.join(f'<a href="{url}"' + (' aria-current="page"' if url == active else '') + f'>{label}</a>' for url, label in NAV)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} · Every-match picks</title><style>{CSS}</style></head><body>
<a class="skip" href="#main">Skip to content</a><header><div class="wrap"><div class="brand">HOTSPAWN / CS2 PICKS <span class="small">Independent analysis</span></div><nav aria-label="Main">{nav}</nav></div></header>
<main id="main" class="wrap" data-policy="{POLICY}">{body}<footer class="small">Source collection: <time datetime="{esc(b['collected_to_utc'])}">{esc(b['collected_to_utc'])}</time>. Eligibility evaluated: {esc(b['generated_utc'])}. Counts describe that evaluation, not a live feed.<br>Automatic checks every four hours (best-effort GitHub schedule). No manual input. HotSpawn supplies fixtures only; crowd picks never affect probabilities.<br>Model estimates are not verified outcomes or guarantees. 18+; gamble responsibly. Not affiliated with HotSpawn.<br><a href="../index.html">Main dashboard</a> · <a href="../ourline/index.html">Shared-engine research view</a> · <a href="../summary/index.html">Verification & sources hub</a> · <a href="../data/c64a5e19/board.json">JSON export</a></footer></main><script>{JS}</script></body></html>'''


def source_links(r):
    return ' · '.join(f'<a href="{esc(s["url"])}" rel="noopener">{esc(s["label"])}</a>' for s in r['sources'])


def picks_table(b):
    rows = []
    for r in b['open']:
        ln = r['line']
        basis = ('model' if ln['tier'] == 'B' else 'market') if ln else 'unverified'
        pick = ('No edge — equal probabilities' if not ln.get('pick_team') else 'Pick: ' + ln['pick_team']) if ln else 'Unverified — no supported pick'
        inputs = []
        for q in r['quotes']:
            # Show prices in fixture order, not silently reversed provider order.
            da, db = q['decimal_a'], q['decimal_b']
            if q['swapped']: da, db = db, da
            price_label = 'reciprocal yes midpoints' if q.get('kickoff_evidence') else 'decimal odds'
            inputs.append(f'{esc(q["source_name"])} {price_label}: {da:g} / {db:g} · observed {esc(q["retrieved_utc"])}')
            if q.get('kickoff_evidence'):
                proof = q['kickoff_evidence']
                inputs.append('Exchange fallback only · kickoff from both explicit contract rules: ' + esc(proof['start_utc']) +
                    '. Midpoints are not executable prices; volume may be low or zero. '
                    '<a href="../data/c64a5e19/board.json">Bid/ask, volume and verbatim rules</a>.')
        if ln and basis == 'model':
            va, vb = r['vrs']['team_a'], r['vrs']['team_b']
            inputs.append(f'Valve points: {va["points"]} / {vb["points"]}; snapshot {esc(b["vrs"]["snapshot"])}. Model estimate, not bookmaker odds.')
        if not ln: inputs.append('Missing or ambiguous evidence. Values intentionally blank, not 50/50.')
        rows.append(f'''<tr id="m-{esc(r['fixture_id'])}" data-match data-search="{esc((r['team_a']+' '+r['team_b']+' '+str(r.get('competition') or '')).lower())}" data-basis="{basis}" data-expires="{esc(r['valid_until_utc'])}" data-until="{esc(r['valid_until_utc'])}" data-lock="{esc(r['lock_utc'] or r['start_utc'])}">
<td data-label="Match"><b>{esc(r.get('competition'))}</b><div class="small"><time data-local datetime="{esc(r['start_utc'])}">{esc(r['start_utc'])}</time><br>Fixture #{esc(r['fixture_id'])} · Tier {esc(r.get('tier') or 'unverified')}</div></td>
<td data-label="Win probability"><div class="teams"><span>{esc(r['team_a'])}</span><span class="prob estimate" data-current>{pct(ln['prob_a']) if ln else '—'}</span><span>{esc(r['team_b'])}</span><span class="prob estimate" data-current>{pct(ln['prob_b']) if ln else '—'}</span></div><span class="expired-label expiry" hidden>— Expired / locked</span></td>
<td data-label="Pick & basis"><span class="pick estimate" data-current>{esc(pick)}</span><span class="badge {basis}">{'Market-derived' if basis == 'market' else 'VRS model · fallback only' if basis == 'model' else 'Unverified'}</span><div class="small">{'<br>'.join(inputs)}</div><a href="flagged.html#f-{esc(r['fixture_id'])}">Review evidence / flags</a></td>
<td data-label="Official sources" class="sources">{source_links(r)}</td></tr>''')
    return '''<div class="filters"><label>Find a team or tournament<input id="search" type="search" placeholder="Search matches…"></label><label>Evidence basis<select id="basis"><option value="">All matches</option value="market">Market-derived</option><option value="model">Model fallback</option><option value="unverified">Unverified</option></select></label></div><p id="visible-count" role="status" class="small"></p><p id="expiry-note" class="notice" role="status" hidden></p><noscript><p class="notice">JavaScript is off: these are dated estimates at the evaluation time below, not current picks. Check the source collection time and match lock before using them.</p></noscript><table><caption>Every open, lobby-listed CS2 fixture at evaluation. Times display in your timezone when available.</caption><thead><tr><th>Match</th><th>Win probability</th><th>Pick & basis</th><th>Official sources</th></tr></thead><tbody>''' + ''.join(rows) + '</tbody></table>'


def render_index(b):
    s = b['summary']
    stats = ''.join(f'<div class="stat"><b>{n}</b><span>{label}</span></div>' for n, label in [(s['open'],'Open fixtures'), (s['tier_a_market'],'Market-derived'), (s['tier_b_model'],'Model fallback'), (s['tier_d_none'],'Unverified / blank')])
    return page('Executive summary', 'index.html', f'''<section class="hero"><div class="eyebrow">Executive summary · Updated automatically</div><h1>Every match. One picks board.</h1><p class="muted">Start here for all open HotSpawn CS2 matches. See both teams’ win estimates, the pick, and the source behind it. No bookmaker coverage? We try verified Valve ratings only for those gaps.</p><div class="actions"><a class="button primary" href="#picks">See all picks ↓</a><a class="button" href="unresolved.html">Unresolved picks & limitations</a></div></section><div class="stats">{stats}</div>
<p class="small">Inventory: {s['listed']} lobby-listed CS2 fixtures. {s['with_pick']} open fixtures have a supported pick. <a href="{LOBBY}">Official lobby</a> · <a href="inventory.html">Open, locked & past inventory</a>.</p><div class="notice">Complete fixture coverage does not mean confirmed odds for every match. Missing prices or uncertain team identities stay blank and flagged — never filled using HotSpawn popularity, sibling rosters, or an invented 50/50.</div>
<h2>Unresolved picks &amp; limitations</h2><p>{s['tier_d_none']} open fixtures have no supported pick. <a href="unresolved.html">See every unresolved match, source attempt and reason</a>. {s['tier_b_model']} further fixtures use labelled model estimates, not bookmaker odds.</p><h2 id="picks">All open CS2 picks</h2>{picks_table(b)}<h2>Where to go next</h2><div class="cards"><div class="panel"><a href="picks.html">Full picks table</a><p class="small">The same matches, inputs and source links. Bookmark this page on your phone.</p></div><div class="panel"><a href="inventory.html">Full lobby inventory</a><p class="small">Every listed fixture, including locked, past and unverified source states.</p></div><div class="panel"><a href="method.html">How estimates are made</a><p class="small">No-vig market prices first; a clearly labelled rating model only when prices are missing.</p></div></div>''', b)


def render_picks(b):
    return page('All picks', 'picks.html', '<h1>All open CS2 picks</h1><p class="muted">Market first. Model only for uncovered fixtures. Blank when evidence is missing.</p>' + picks_table(b), b)


def render_inventory(b):
    rows = ''.join(f'<tr><td data-label="Fixture">{esc(r["team_a"])} vs {esc(r["team_b"])}<div class="small">#{esc(r["fixture_id"])} · {esc(r.get("competition"))}</div></td><td data-label="Start (UTC)">{esc(r["start_utc"])}</td><td data-label="Source status">{esc(r.get("status"))}</td><td data-label="Eligibility">{esc(r["state"])}' + (f' · <a href="picks.html#m-{esc(r["fixture_id"])}">Pick / evidence</a>' if r['state'] == 'open' else '') + f'</td><td data-label="Source"><a href="{esc(r["hotspawn_url"])}">Official HotSpawn listing</a></td></tr>' for r in b['inventory'])
    return page('Full inventory', 'inventory.html', '<h1>Full CS2 lobby inventory</h1><p class="muted">All fixtures in the captured public lobby response, not just featured cards. Closed fixtures are retained here without pretending a past price is a current pick. API-only records are excluded because current lobby membership is unconfirmed.</p><table><thead><tr><th>Fixture</th><th>Start (UTC)</th><th>Source status</th><th>Eligibility</th><th>Official source</th></tr></thead><tbody>' + rows + '</tbody></table>', b)


def render_unresolved(b):
    rows = []
    models = []
    for r in b['open']:
        if r.get('market'):
            continue
        review = r.get('research') or {'steps': [], 'limitations': limitations(r)}
        steps = ''.join(f'<li><a href="{esc(x["url"])}">{esc(x["label"])}</a><br>{esc(x["result"])}<br><span class="small">Read: {esc(x.get("at_utc") or "unverified")} · HTTP {esc(x.get("http_status") or "unverified")}</span></li>' for x in review['steps'])
        item = f'<tr id="u-{esc(r["fixture_id"])}"><td data-label="Match"><b>{esc(r["team_a"])} vs {esc(r["team_b"])}</b><br>#{esc(r["fixture_id"])} · {esc(r.get("competition"))}<br>{source_links(r)}</td><td data-label="Pick / probability">' + ('<a href="picks.html#m-' + esc(r['fixture_id']) + '">Labelled model estimate on picks page</a>' if r['line'] else '—<br>Unverified · no supported pick') + '</td><td data-label="Limitation">' + '<br>'.join(esc(x) for x in review['limitations']) + f'<details><summary>Source attempts &amp; next steps</summary><ol>{steps}</ol><p>Retry automatically on the next four-hour capture. A verified two-sided price or unique, current rating pair is required; there is no manual input.</p></details></td></tr>'
        (models if r['line'] else rows).append(item)
    def table(items):
        return '<table><thead><tr><th>Match / official source</th><th>Pick / probability</th><th>Limitation &amp; research</th></tr></thead><tbody>' + ''.join(items) + '</tbody></table>' if items else '<p>No rows in this category at the stated evaluation time. This is not a coverage guarantee.</p>'
    return page('Unresolved picks & limitations', 'unresolved.html', f'''<h1>Unresolved picks &amp; limitations</h1><p>Every open match remains in the picks list. Only matches without an accepted market line appear here. We do not replace featured picks with research.</p><p><a class="button primary" href="picks.html">Back to all picks</a> <a class="button" href="../audits/3faf40e8/index.html">Source research &amp; review findings</a></p><div class="notice">A blank is not 50/50. HLTV user votes are not betting lines; rankings are not win probabilities. Blocked access, unverified aliases and duplicate rosters are not evidence for a forced pick.</div><h2>{len(rows)} unresolved matches</h2>{table(rows)}<h2>{len(models)} rating-model fallbacks</h2><p>These have supported model inputs, but no eligible market quote. The probabilities are our estimates, not officially confirmed win chances. Check expiry on the picks page.</p>{table(models)}<p>Source-attempt times come from the same captured snapshot as these picks. HLTV access checks are explicitly distinguished from a verified match-specific odds extraction. A successful endpoint response does not establish that it prices a particular match. See <a href="method.html">method and evidence</a>.</p>''', b)


def render_flagged(b):
    rows = []
    for r in b['open']:
        # Every details link resolves, including eligible rows with no irregularity.
        flags = r['flags'] or ['No eligibility irregularity detected; estimate remains uncertain.']
        rows.append(f'<tr id="f-{esc(r["fixture_id"])}"><td data-label="Fixture">{esc(r["team_a"])} vs {esc(r["team_b"])}<div class="small">#{esc(r["fixture_id"])}</div></td><td data-label="Review">{"<br>".join(esc(f) for f in flags)}</td><td data-label="Official source" class="sources">{source_links(r)}</td></tr>')
    health = ''.join(f'<tr><td data-label="Provider">{esc(name)}</td><td data-label="Collection result">{esc(meta.get("status"))} {esc(meta.get("error"))} · read {esc(meta.get("at_utc"))}</td><td data-label="Source"><a href="{esc(meta.get("url") or LOBBY)}">Official endpoint</a></td></tr>' for name, meta in b['access'].items())
    return page('Flagged for Review', 'flagged.html', f'''<h1>Flagged for Review</h1><p><a href="unresolved.html">Unresolved picks &amp; per-match limitations</a> · <a href="../audits/3faf40e8/index.html">Latest source research and repository review</a></p><p><a href="../audits/49a181f8/index.html">Independent source-integrity review and parallel integration notes</a></p><div class="notice"><b>Unsupported numeric coverage removed.</b> Earlier versions used LFO sibling/floor ratings and WROTBERRY slot prices despite unresolved identity. Those assumptions are no longer current picks. <a href="../summary/gaps.html">Preserved conflicting-source research</a> is a dated review, not verified identity evidence.</div><p>Official <a href="{esc(b['vrs'].get('page_url') or 'https://github.com/ValveSoftware/counter-strike_regional_standings')}">Valve standings</a> do not justify transferring one roster’s strength to another. <a href="https://www.hltv.org/team/13999/wbt-academy">HLTV WBT Academy</a> and <a href="https://www.hltv.org/team/12457/roundsgg">HLTV Rounds</a> are research links only; this session has not verified a current fixture-roster join from them. Approximate exchange ticker times and thin books are not accepted odds. A separate canonical-only fallback can use explicit, agreeing full-match contract rules; it retains bid/ask, volume and verbatim kickoff statements and does not infer a roster alias. See the per-row exchange flags and JSON evidence.</p><p>Preserved independent reviews: <a href="../audits/5cd24fb4/index.html">Fallback identity audit</a> · <a href="../audits/8723ad37/REVIEW.md">Source-safety review</a>. These documents record their own read times, not current verified prices.</p><p>Rule-backed exchange resolutions retain their HLTV-first attempt history in the board JSON under gap_research. Existing accepted bookmaker picks are not repriced.</p><h2>Line-by-line fixture review</h2><table><thead><tr><th>Fixture</th><th>Review</th><th>Official source</th></tr></thead><tbody>{''.join(rows)}</tbody></table><h2>Collection health</h2><p>HTTP success does not mean a usable market exists. Blocked/unavailable sources never produce invented values. Original observation/cache times are retained across collection failures.</p><table><thead><tr><th>Provider</th><th>Collection result</th><th>Official source</th></tr></thead><tbody>{health}</tbody></table><h2>Coverage and freshness limitations</h2><p>Four-hour scheduled collection is best effort, not an uptime guarantee. Cache age counts toward the four-hour eligibility limit. Estimates expire in the browser at that limit or the match lock. Full inventory means the entire captured lobby response, not a guarantee that HotSpawn’s cached response contains every newly added fixture.</p><p>Historical alternate boards elsewhere in the repository may use different assumptions. They remain preserved for audit and are not inputs to this board. External-link reachability is not universally certified.</p>''', b)


def render_method(b):
    cal = b['calibration']
    return page('Method & sources', 'method.html', f'''<h1>Method & sources</h1><h2>1. Every fixture, not just featured matches</h2><p>Read the Angular transfer-state fixtures embedded in the public <a href="{LOBBY}">HotSpawn lobby</a>. Use the published CS2 game identifier and preserve all lobby-listed rows. A scheduled match is open only before its published lock. HotSpawn is never a probability input.</p><h2>2. Market first</h2><p>Try public Pinnacle, Bovada and Melbet full-match, two-team prices. Join both participants and source kickoff (maximum five-minute discrepancy); reject live markets, props, unknown/approximate times and stale quotes. The retained provider response must reproduce every consumed price and participant pair before publication.</p><p>For decimal odds dA and dB, our fair estimate is pA = (1/dA) / ((1/dA) + (1/dB)); pB = 1 − pA. Combine accepted sources with a declared weight of 2 for Pinnacle and 1 for others. This weighting is a modelling choice, not an official win probability. Market picks are not blended with rating estimates.</p><h2>3. Fallback research only for market gaps</h2><p>Research HLTV first; the captured probe and manual research limitations remain visible. Then try other esportsbooks/exchanges. A Kalshi full-match fallback requires two active binary outcome contracts, matching teams, consistent explicit originally-scheduled CS2 match rules, a verified EDT/EST/UTC timezone, and two usable bid/ask books (spread at most 10 cents each). A ticker, occurrence time, expected expiration or settlement deadline is never a kickoff. Retained official JSON must reproduce both rules and prices offline. These normalized yes midpoints are estimates, not executable odds; volume can be low or zero. This fallback is used only for market gaps and never changes an accepted featured/bookmaker estimate.</p><p>Use two uniquely identified teams in <a href="{esc(b['vrs'].get('page_url') or 'https://github.com/ValveSoftware/counter-strike_regional_standings')}">Valve’s official VRS standings</a> (snapshot {esc(b['vrs'].get('snapshot'))}; refuse duplicate roster names and unproven aliases. Standings older than 14 days are ineligible. Apply a logistic rating-difference model using <a href="{ENGINE.VALVE_GLICKO}">Valve’s Glicko code</a> and <a href="{ENGINE.VALVE_FIT}">fit parameters</a>; fit the slope to eligible priced fixtures in this snapshot when at least six pairs exist.</p><p>Current slope k={cal['k']:.4f}; eligible calibration pairs={cal['pairs_used']}; fitted={esc(cal['fitted'])}. A model-only estimate is not a bookmaker line, not a verified probability, and has no claimed out-of-sample accuracy. No sibling/floor ratings, ambiguous tournament-slot joins, or default 50/50s. Missing inputs stay blank.</p><h2>4. Expire, flag, retry</h2><p>Quotes and cache-adjusted fixture observations must be at most four hours old. Preserve last-known inventory on fetch failure, but never reset its evidence age. A backup timestamp cannot replace missing, failed, invalid or future retained HTTP metadata. When both HTTP and backup observation clocks exist, the earlier one and unchanged cache Age bound eligibility. Recheck all sources every four hours with GitHub Actions, and publish only after tests and source replay succeed. Schedule delays, caches and provider blocks are reported, not hidden.</p><h2>Evidence for manual review</h2><ul><li><a href="../data/c64a5e19/snapshot.json">Normalized source snapshot with read times and endpoints</a></li><li><a href="../data/c64a5e19/source_payloads.json">Official provider response payloads and hashes</a></li><li><a href="../data/c64a5e19/verification.json">Line-by-line provider replay results</a></li><li><a href="../data/c64a5e19/board.json">Derived board and all flags</a></li></ul><p>HLTV and Polymarket are checked for accessibility/coverage but no unsupported number is taken from either. Their absence does not prevent a verified rating fallback for an otherwise identified match.</p>''', b)


def main():
    snap = load(DATA / 'snapshot.json', None)
    if not snap:
        raise SystemExit('No captured snapshot; refusing to invent fixtures')
    now_dt = core.now_utc()
    snap_dt = core.parse_iso(snap.get('collected_to_utc'))
    eval_dt = now_dt if snap_dt and abs((now_dt - snap_dt).total_seconds()) <= 4 * 3600 else None
    board = build_board(snap, 'data/c64a5e19/snapshot.json', eval_dt)
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'board.json').write_text(json.dumps(board, indent=1, ensure_ascii=False, allow_nan=False) + '\n')
    # Fail publication if any consumed quote cannot be reconstructed from the provider.
    spec = importlib.util.spec_from_file_location('every_match_payload_check', ROOT / 'scripts/ae75c5c3/verify_source_payloads.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    verification = verifier.verify(DATA, quote_normalizer=RULES.enrich_quotes)
    from verify_inputs import verify
    inputs_check = verify(snap, load(DATA / 'official_inputs.json', {}), core)
    verification['official_inputs'] = inputs_check
    verification['failures'] += inputs_check['failures']
    (DATA / 'verification.json').write_text(json.dumps(verification, indent=1) + '\n')
    if verification['failures']:
        raise SystemExit('Provider evidence replay failed: ' + str(verification['failures']))
    SITE.mkdir(parents=True, exist_ok=True)
    for filename, render in [('index', render_index), ('picks', render_picks), ('inventory', render_inventory), ('unresolved', render_unresolved), ('flagged', render_flagged), ('method', render_method)]:
        (SITE / (filename + '.html')).write_text(render(board))
    print(json.dumps(board['summary'], indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
