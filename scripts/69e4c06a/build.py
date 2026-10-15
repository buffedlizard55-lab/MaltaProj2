#!/usr/bin/env python3
"""Dated TWC evidence + day-three decisions from the canonical current capture.

Results/roster facts are manually source-reviewed, never probability-model inputs.
Listed matches reuse canonical probabilities exactly. An unlisted tournament preview
can use replayed primary-bookmaker JSON, but cannot become a HotSpawn pick or acquire
invented ownership/points. No new network requests or refreshed source clocks here.
"""
from __future__ import annotations

import argparse
import copy
import html
import importlib.util
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('twc_private_engine', ROOT / 'scripts/c64a5e19/verified_engine.py')
_engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_engine)
COLLECTOR = _engine.load_engine('collect.py')
core = COLLECTOR.core
LOBBY = 'https://play.hotspawn.com/lobby'
POLICY = {'minimum_underdog_probability': 0.35, 'maximum_underdog_ownership': 0.20,
          'minimum_probability_to_ownership_ratio': 2.0, 'minimum_bookmaker_sources': 2,
          'maximum_deliberate_day_three_swings': 1,
          'description': 'Declared risk-selection heuristic, not a backtested or contest-optimal strategy.'}


def read(root, relative):
    return json.loads((Path(root) / relative).read_text())


def esc(value):
    return html.escape('' if value is None else str(value), quote=True)


def pct(value):
    return f'{value * 100:.2f}%' if isinstance(value, (int, float)) and math.isfinite(value) else '—'


def utc(value):
    return core.to_iso(value)


def pair(a, b):
    return sorted((core.canon(a)[0], core.canon(b)[0]))


def canonical_ownership(fixture, evidence):
    """Separate ownership context, exact fixture/participant ordering from official JSON."""
    source = evidence.get('lobby') or {}
    raw = [r for r in (source.get('transfer_state') or {}).get('fixtures', [])
           if str(r.get('id')) == fixture['fixture_id']]
    if len(raw) != 1:
        return None
    raw = raw[0]
    if [raw.get('participants0_name'), raw.get('participants1_name')] != [fixture['team_a'], fixture['team_b']]:
        return None
    values = [raw.get('participants0_picked_percent'), raw.get('participants1_picked_percent')]
    if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) or not 0 <= x <= 100 for x in values):
        return None
    # Do not renormalize inconsistent ownership or treat rounded zero as true zero.
    if abs(sum(values) - 100) > 1:
        return None
    total = raw.get('total_picks')
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        total = None
    return {'team_a': values[0] / 100, 'team_b': values[1] / 100, 'total_picks_reported': total,
            'observed_utc': source.get('metadata', {}).get('at_utc'),
            'cache_age_seconds': source.get('metadata', {}).get('age_header'),
            'source_url': source.get('url') or LOBBY,
            'limitation': 'HotSpawn ownership, never a win-probability input. Rounded percentages and a small changing sample.'}


def replay_bookmakers(payloads):
    """Parse primary retained responses directly; snapshot normalized prices are not inputs."""
    def response(url, *args, **kwargs):
        saved = (payloads.get('sources') or {}).get(url) or {}
        if saved.get('http_status') != 200:
            return None, {'status': saved.get('http_status'), 'error': 'No retained successful response'}
        return saved.get('payload'), {'status': 200, 'at_utc': saved.get('retrieved_utc')}
    quotes = []
    with patch.object(COLLECTOR, 'fetch_json', side_effect=response), patch.object(COLLECTOR.time, 'sleep'):
        COLLECTOR.collect_pinnacle(quotes)
        COLLECTOR.collect_bovada(quotes)
        COLLECTOR.collect_melbet(quotes)
    for quote in quotes:
        # The shared parser stamps parse time; replay must use the actual saved
        # response clock, not make historical prices fresh by re-rendering.
        quote['retrieved_utc'] = (payloads.get('sources', {}).get(quote['api_url']) or {}).get('retrieved_utc')
    return quotes


def preview_line(template, quotes, now):
    """No synthetic HotSpawn fixture; this is explicitly an unlisted event preview."""
    selected = {}
    for raw in quotes:
        quote = core.rederive_quote(raw)
        if not quote or quote.get('live') or quote.get('fallback_only'):
            continue
        join = core.match_quote(template, quote)
        observed = core.parse_iso(quote.get('retrieved_utc'))
        start = core.parse_iso(template.get('start_utc'))
        if (not join or join.get('rejected') or not observed or not start or now >= start
                or not 0 <= (now - observed).total_seconds() <= 4 * 3600):
            continue
        if quote['source_key'] in selected:
            # Ambiguous multiple same-book events are not arbitrarily selected.
            selected[quote['source_key']] = None
            continue
        selected[quote['source_key']] = {**quote, 'swapped': join['swapped'],
                                        'oriented_prob_a': core.oriented_prob(quote, join['swapped'])}
    selected = [q for q in selected.values() if q]
    consensus = core.consensus([{'source_key': q['source_key'], 'prob_a': q['oriented_prob_a']} for q in selected])
    if not consensus:
        return None, [], utc(now)
    probability = round(consensus['prob_a'], 4)
    line = {'prob_a': probability, 'prob_b': round(1 - probability, 4), 'basis': 'market',
            'pick_team': template['team_a'] if probability > .5 else template['team_b'] if probability < .5 else None}
    deadline = min([core.parse_iso(template['start_utc'])] +
                   [core.parse_iso(q['retrieved_utc']) + timedelta(hours=4) for q in selected])
    return line, selected, utc(deadline)


def decision(row):
    """Ownership chooses risk, never estimates a match win probability."""
    line, own = row.get('line'), row.get('ownership')
    output = {'qualified': False, 'pick_team': None, 'underdog_probability': None,
              'underdog_ownership': None, 'probability_to_ownership_ratio': None,
              'expected_points_sacrificed': None, 'favorite_expected_points': None,
              'underdog_expected_points': None, 'reason': 'No eligible two-book, listed-market ownership comparison.'}
    if not row.get('listed_on_hotspawn') or not line or line.get('basis') != 'market' or not own:
        return output
    pa, pb = line['prob_a'], line['prob_b']
    if pa == pb:
        output['reason'] = 'No identified underdog; equal estimates are not an edge.'
        return output
    dog_side = 'a' if pa < pb else 'b'
    probability = min(pa, pb)
    ownership = own['team_' + dog_side]
    ratio = probability / ownership if ownership > 0 else None
    output.update(underdog_probability=probability, underdog_ownership=ownership,
                  probability_to_ownership_ratio=ratio)
    points = row.get('offered_points')
    if isinstance(points, (float, int)) and not isinstance(points, bool) and points > 0:
        output.update(expected_points_sacrificed=round(points * abs(pa - pb), 4),
                      favorite_expected_points=round(points * max(pa, pb), 4),
                      underdog_expected_points=round(points * probability, 4))
    books = {q['source_key'] for q in row.get('quotes', []) if q['source_key'] in ('pinnacle', 'bovada', 'melbet')}
    qualifies = (probability >= POLICY['minimum_underdog_probability']
                 and 0 < ownership <= POLICY['maximum_underdog_ownership']
                 and ratio >= POLICY['minimum_probability_to_ownership_ratio']
                 and len(books) >= POLICY['minimum_bookmaker_sources'])
    output.update(qualified=qualifies, pick_team=row['team_' + dog_side] if qualifies else None,
                  reason='Optional high-variance leaderboard swing; the favorite still maximizes expected match points.' if qualifies else
                         'No deliberate swing: probability, ownership/leverage or two-book source gate not met.')
    return output


def derive(root=ROOT, now=None):
    now = now or core.now_utc()
    facts = read(root, 'data/69e4c06a/research.json')
    board = read(root, 'data/c64a5e19/board.json')
    evidence = read(root, 'data/c64a5e19/official_inputs.json')
    payloads = read(root, 'data/c64a5e19/source_payloads.json')
    replayed = replay_bookmakers(payloads)
    rows = []
    for template in facts['day_three']:
        candidates = [r for r in board['open'] if pair(r['team_a'], r['team_b']) == pair(template['team_a'], template['team_b'])
                      and r['start_utc'][:10] == template['date']]
        row = copy.deepcopy(template)
        row.update(fixture_id=None, listed_on_hotspawn=False, ownership=None, offered_points=None,
                   line=None, quotes=[], lock_utc=None, hotspawn_url=LOBBY, valid_until_utc=utc(now), flags=[])
        if len(candidates) == 1:
            original = candidates[0]
            # Preserve the actual canonical fixture order, not a silently reversed line.
            row.update({key: copy.deepcopy(original.get(key)) for key in
                        ('fixture_id', 'team_a', 'team_b', 'start_utc', 'lock_utc', 'hotspawn_url', 'offered_points', 'quotes', 'valid_until_utc')})
            row['offered_points'] = original.get('points')
            row['listed_on_hotspawn'] = True
            row['ownership'] = canonical_ownership(original, evidence)
            row['flags'] = copy.deepcopy(original.get('flags', []))
            deadline = core.parse_iso(original.get('valid_until_utc'))
            lock = core.parse_iso(original.get('lock_utc') or original.get('start_utc'))
            if deadline and lock and now < min(deadline, lock):
                row['line'] = copy.deepcopy(original.get('line'))
            else:
                row['flags'].append('source_expired_or_match_locked')
        elif candidates:
            row['flags'].append('ambiguous_canonical_fixture_pair')
            row['start_utc'] = None
        else:
            row['line'], row['quotes'], row['valid_until_utc'] = preview_line(row, replayed, now)
            row['reviewed_start_utc'] = template['start_utc']
            row['start_utc'] = row['quotes'][0]['start_utc'] if row['line'] and row['quotes'] else None
            row['flags'].append('tournament_preview_not_a_hotspawn_pick')
        row['decision'] = decision(row)
        own = row.get('ownership') or {}
        if own.get('total_picks_reported') is not None and own['total_picks_reported'] < 25:
            row['flags'].append('ownership_sample_below_25_reported_picks')
        rows.append(row)
    # This intentionally small day-three slate permits at most one variance swing.
    qualified = sorted([r for r in rows if r['decision']['qualified']],
                       key=lambda r: r['decision']['probability_to_ownership_ratio'], reverse=True)
    for row in qualified[POLICY['maximum_deliberate_day_three_swings']:]:
        row['decision'].update(qualified=False, pick_team=None, reason='One-swing day-three risk budget already used.')
    gaps = [{key: copy.deepcopy(row.get(key)) for key in ('fixture_id', 'team_a', 'team_b', 'start_utc', 'hotspawn_url', 'flags')}
            for row in board['open'] if not row.get('line')]
    return {'schema_version': 1, 'session': '69e4c06a', 'evaluated_utc': utc(now),
            'canonical_generated_utc': board['generated_utc'], 'source_collected_utc': board['collected_to_utc'],
            'canonical_policy': board['policy'], 'canonical_summary': board['summary'],
            'research_reviewed_date_utc': facts['reviewed_date_utc'], 'policy': POLICY,
            'day_three': rows, 'canonical_unresolved': gaps,
            'roster_announcements': [{**r, 'calendar_days_before_day_one':
                (date(2026, 10, 14) - date.fromisoformat(r['announcement_utc'][:10])).days}
                for r in facts['roster_announcements']], 'facts': facts}


CSS = '''
:root{color-scheme:dark;--bg:#0c131c;--panel:#141f2c;--line:#2d3c4d;--text:#edf3fa;--muted:#b2c0d0;--green:#69e4bd;--amber:#ffce80}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}a{color:#92caff;text-underline-offset:3px}a:focus-visible,summary:focus-visible{outline:3px solid var(--amber);outline-offset:3px}header{border-bottom:1px solid var(--line)}.wrap{max-width:1160px;margin:auto;padding:20px}.brand{font-weight:750;letter-spacing:.02em}nav{display:flex;flex-wrap:wrap;gap:4px 16px;margin-top:10px}nav a{padding:8px 0;min-height:44px;text-decoration:none}nav a[aria-current]{color:var(--green);font-weight:700}.skip{position:absolute;left:-9999px}.skip:focus{position:static}h1{font-size:clamp(1.9rem,5vw,2.8rem);line-height:1.15;max-width:870px;margin:12px 0 18px}h2{font-size:1.35rem;margin:30px 0 12px}.eyebrow{color:var(--green);font-size:.8rem;letter-spacing:.1em;text-transform:uppercase;font-weight:700}.muted,.small{color:var(--muted)}.small{font-size:.85rem}.actions{display:flex;flex-wrap:wrap;gap:10px;margin:22px 0}.button{display:inline-block;padding:12px 18px;border:1px solid var(--line);border-radius:8px;min-height:48px;text-decoration:none;font-weight:650}.button.primary{background:var(--green);color:#071a14;border-color:var(--green)}.notice,.panel{border:1px solid var(--line);border-radius:10px;padding:16px;background:var(--panel);margin:16px 0}.notice{border-left:3px solid var(--amber)}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.grid .panel{margin:0}.badge{display:inline-block;padding:3px 8px;border-radius:5px;background:#203648;font-size:.8rem;font-weight:650}.pick{color:var(--green);font-weight:750}.risk{color:var(--amber);font-weight:750}table{width:100%;border-collapse:collapse;font-size:.94rem;margin:16px 0 28px}caption{text-align:left;color:var(--muted);margin-bottom:10px}th,td{text-align:left;padding:14px 12px;vertical-align:top;border-bottom:1px solid var(--line);overflow-wrap:anywhere}th{font-size:.78rem;text-transform:uppercase;color:var(--muted);letter-spacing:.035em}td{min-width:0}td a{display:inline-block;margin:3px 0}.teams{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:5px 12px;min-width:150px}.prob{font-weight:750;font-variant-numeric:tabular-nums}.sources{font-size:.85rem}.blank{color:var(--amber)}details summary{cursor:pointer;min-height:44px;padding:9px 0}footer{border-top:1px solid var(--line);margin-top:36px;padding-top:18px}.expired [data-live]{display:none!important}.expiry{display:none;color:var(--amber)}.expired .expiry{display:block}[hidden]{display:none!important}code{overflow-wrap:anywhere}
@media(max-width:800px){.wrap{padding:16px}.grid{grid-template-columns:1fr}table,tbody,tr,td{display:block;width:100%}thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}tr{border:1px solid var(--line);border-radius:9px;margin-bottom:14px;background:var(--panel)}td{display:grid;grid-template-columns:105px minmax(0,1fr);gap:10px;padding:12px;border-bottom:1px solid var(--line)}td:last-child{border:0}td::before{content:attr(data-label);color:var(--muted);font-size:.75rem;font-weight:650;text-transform:uppercase}.teams{min-width:0}.actions .button{flex:1 1 auto;text-align:center}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
'''
JS = '''
(() => {
 function expire() {
  const now=Date.now(); let n=0;
  document.querySelectorAll('[data-deadline]').forEach(el=>{
   const until=Date.parse(el.dataset.deadline), lock=Date.parse(el.dataset.lock);
   const old=!Number.isFinite(until)||!Number.isFinite(lock)||now>=Math.min(until,lock);
   el.classList.toggle('expired',old); if(old)n++;
  });
  const note=document.querySelector('#expiry-note');
  if(note){note.hidden=!n;note.textContent='Some forecasts are expired, locked or unsupported. Estimates and risk selections are hidden; the dated research remains available. Use the current canonical board after its next automatic refresh.';}
 }
 expire(); setInterval(expire,30000);
})();
'''
NAV = [('index.html', 'Day-three decisions'), ('results.html', 'Days 1–2 results'),
       ('roster.html', 'Roster & rest'), ('flagged.html', 'Flagged for Review'), ('method.html', 'Method'),
       ('../picks-every-match/index.html', 'All CS2 picks'), ('../index.html', 'Home')]


def page(title, active, body, data):
    nav = ''.join(f'<a href="{url}"' + (' aria-current="page"' if url == active else '') + f'>{label}</a>' for url, label in NAV)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} · TWC 2026 evidence</title><link rel="stylesheet" href="assets.css"></head><body><a class="skip" href="#main">Skip to content</a><header><div class="wrap"><div class="brand">HOTSPAWN / TWC 2026 <span class="small">Independent research</span></div><nav aria-label="Main">{nav}</nav></div></header><main id="main" class="wrap">{body}<footer class="small">Research reviewed {esc(data['research_reviewed_date_utc'])}; source collection {esc(data['source_collected_utc'])}; eligibility evaluated {esc(data['evaluated_utc'])}. Probabilities are dated estimates, not verified future outcomes.<br>Canonical fixtures/prices refresh every four hours via GitHub Actions (best effort, not an uptime guarantee). This dated result/roster review is not an automated live news service.<br><a href="../data/69e4c06a/day3.json">Decision JSON</a> · <a href="../data/69e4c06a/research.json">Source-reviewed factual ledger</a> · <a href="../picks-every-match/unresolved.html">All unresolved picks</a><br>HotSpawn percentages are ownership context only. No automated bets or account actions. Not affiliated with HotSpawn. 18+; gamble responsibly.</footer></main><script src="app.js"></script></body></html>'''


def table(headers, rows, caption=''):
    heading = ''.join('<th scope="col">' + esc(h) + '</th>' for h in headers)
    body = ''.join('<tr' + attrs + '>' + ''.join('<td data-label="' + esc(h) + '"><div>' + value + '</div></td>'
                   for h, value in zip(headers, cells)) + '</tr>' for attrs, cells in rows)
    return '<table>' + ('<caption>' + esc(caption) + '</caption>' if caption else '') + '<thead><tr>' + heading + '</tr></thead><tbody>' + body + '</tbody></table>'


def live(value):
    return '<div data-live>' + value + '</div><span class="expiry">— Unverified / expired / locked</span>'


def day_three_table(data):
    rows = []
    for row in data['day_three']:
        line, choice = row['line'], row['decision']
        probabilities = '<div class="teams"><span>' + esc(row['team_a']) + '</span><span class="prob">' + pct((line or {}).get('prob_a')) + '</span><span>' + esc(row['team_b']) + '</span><span class="prob">' + pct((line or {}).get('prob_b')) + '</span></div>'
        favorite = '<b class="pick">' + esc((line or {}).get('pick_team') or '— No supported estimate') + '</b>'
        favorite += '<br><span class="small">' + ('Canonical baseline pick' if row['listed_on_hotspawn'] else 'Tournament preview only; not a HotSpawn pick') + '</span>'
        risk = '<b class="risk">' + esc(choice['pick_team']) + '</b> · optional swing' if choice['qualified'] else 'No qualified leaderboard swing'
        if not choice['qualified'] and choice['underdog_probability'] is not None:
            dog = row['team_a'] if line['prob_a'] < line['prob_b'] else row['team_b']
            risk = '<b>Watchlist: ' + esc(dog) + '</b><br>No active swing under the declared gates.'
            risk += '<br><span class="small">Underdog estimate ' + pct(choice['underdog_probability']) + '; rule floor ' + pct(POLICY['minimum_underdog_probability']) + '. Do not force a fade.</span>'
        risk += '<br><span class="small">' + esc(choice['reason']) + '</span>'
        if choice['expected_points_sacrificed'] is not None:
            risk += f'<br><span class="small">Underdog costs {choice["expected_points_sacrificed"]:.2f} expected match points vs the favorite, assuming {esc(row["offered_points"])} offered points for a correct pick.</span>'
        own = row.get('ownership')
        ownership = '—<br><span class="small">No confirmed HotSpawn ownership for an unlisted match.</span>'
        if own:
            ownership = esc(row['team_a']) + ' ' + pct(own['team_a']) + '<br>' + esc(row['team_b']) + ' ' + pct(own['team_b'])
            ownership += '<br><span class="small">Ownership only · reported picks: ' + esc(own['total_picks_reported'] if own['total_picks_reported'] is not None else 'unverified') + '</span>'
            if choice['probability_to_ownership_ratio'] is not None:
                ownership += f'<br><span class="small">Underdog probability / ownership: {choice["probability_to_ownership_ratio"]:.2f}×</span>'
        sources = '<a href="' + esc(row['hltv_url']) + '">HLTV match / stage</a><br><a href="' + esc(row['official_publisher_url']) + '">Official HotSpawn day-two report</a><br><a href="' + esc(row['hotspawn_url']) + '">HotSpawn ' + ('fixture' if row['listed_on_hotspawn'] else 'lobby (not listed in this capture)') + '</a>'
        for quote in row['quotes']:
            sources += '<br><a href="' + esc(quote['api_url']) + '">' + esc(quote['source_name']) + ' official input</a> · <span class="small">' + esc(quote['retrieved_utc']) + '</span>'
            names = quote.get('names_at_source') or [quote.get('team_a'), quote.get('team_b')]
            sources += '<br><span class="small">' + esc(names[0] or '— Unverified') + ': ' + esc(quote['raw_a']) + ' / ' + esc(names[1] or '— Unverified') + ': ' + esc(quote['raw_b']) + ' (' + esc(quote['raw_format']) + ')</span>'
        if not row['listed_on_hotspawn']:
            risk += '<br><span class="small">Wait for a listed fixture and verified ownership; do not invent either.</span>'
        attrs = f' id="{esc(row["key"])}" data-deadline="{esc(row["valid_until_utc"])}" data-lock="{esc(row["lock_utc"] or row["start_utc"])}"'
        rows.append((attrs, [f'<b>{esc(row["team_a"])} vs {esc(row["team_b"])}</b><br>{esc(row["stage"])}<br><span class="small">{esc(row["start_utc"])}</span>',
                             live(probabilities), live(favorite), live(risk), live(ownership), sources]))
    return table(['Match', 'Both win estimates', 'Baseline favorite', 'Leaderboard option', 'Ownership, not probability', 'Sources'], rows,
                 '16 October deciders. Listed rows reuse canonical probabilities; an unlisted preview is explicitly not pickable on HotSpawn.')


def render_index(data):
    s = data['canonical_summary']
    contexts = ''.join('<article class="panel"><h2>' + esc(r['team_a']) + ' vs ' + esc(r['team_b']) + '</h2><p>' + esc(r['upset_context']) + '</p><p class="small"><a href="' + esc(r['hltv_url']) + '">Match / veto status</a> · <a href="' + esc(r['official_publisher_url']) + '">Day-two results</a></p></article>' for r in data['day_three'])
    body = f'''<div class="eyebrow">15 October review → 16 October decisions</div><h1>Real upset potential. Not a blind underdog slate.</h1><p class="muted">Day one gave 9z a genuine head-to-head case. Day two added a competitive Falcons series — and an Aurora rebound. Keep the market favorite separate from an optional leaderboard swing.</p><div class="actions"><a class="button primary" href="../picks-every-match/index.html">All current CS2 picks</a><a class="button" href="../picks-every-match/unresolved.html">Unresolved picks & limitations</a><a class="button" href="results.html">Verified days 1–2</a></div><div class="notice">The canonical capture retains <b>{s['listed']} listed fixtures</b>: {s['open']} open, {s['with_pick']} supported picks and {s['no_line']} blank/flagged. This category is a focused TWC review, not a competing all-match board. <a href="../picks-every-match/inventory.html">Full captured inventory</a> · <a href="{LOBBY}">Official lobby</a>.</div><h2>Day-three decision sheet</h2><p id="expiry-note" class="notice" role="status" hidden></p><noscript><p class="notice">JavaScript is off: all forecasts are historical values at the stated source/evaluation time, not confirmed current picks. Check lock and source age on the canonical board.</p></noscript>{day_three_table(data)}<div class="notice"><b>The favorite still maximizes expected match points.</b> An underdog selection deliberately trades expected score for a less common successful outcome. The one-swing, two-book probability/ownership gates are <a href="method.html">declared heuristics</a>, not proof of an optimal contest entry. Ownership can move quickly, especially when the reported sample is small.</div><h2>What day two actually changed</h2><div class="grid">{contexts}</div><h2>Do not manufacture a roster or rest penalty</h2><p>Aurora’s Jimpphat and ash announcements were on <b>3 July</b>; captain kyxsan’s was on <b>8 July</b>, not this week. Those are 103 and 98 calendar days before the opener, not measured practice or adaptation time. Aurora played two maps on day two; 9z played three. Actual rest hours and causal onboarding effects remain blank. <a href="roster.html">Primary announcements and explicit unknowns →</a></p><p><a href="flagged.html">Flagged for Review</a>: incomplete/contested roster identities, exchange liquidity limits, small ownership samples, missing vetoes and the unlisted Group B decider are published, not hidden.</p>'''
    return page('Day-two review and day-three decisions', 'index.html', body, data)


def render_results(data):
    sections = []
    for day in (1, 2):
        rows = []
        for result in data['facts']['results']:
            if result['day'] != day:
                continue
            maps = '<br>'.join(esc(m['name']) + f' {m["score_a"]}–{m["score_b"]}' for m in result['maps'])
            source = '<a href="' + esc(result['official_publisher_url']) + '">Official HotSpawn report</a><br><a href="' + esc(result['specialist_url']) + '">HLTV cross-check</a>'
            rows.append(('', [esc(result['team_a']) + ' vs ' + esc(result['team_b']) + '<br><span class="small">' + esc(result['date']) + ' · ' + esc(result['stage']) + '</span>',
                              f'<b>{result["series_a"]}–{result["series_b"]}</b><br>' + maps, esc(result['takeaway']), source]))
        sections.append('<h2>Day ' + str(day) + ' · ' + ('14' if day == 1 else '15') + ' October 2026</h2>' +
                        table(['Match', 'Series / maps', 'What it establishes', 'Sources'], rows, 'Scores are in the displayed team order; no unverified kickoff/finish time is inferred.'))
    body = '<div class="eyebrow">Verified factual ledger</div><h1>All eight results. Context without hindsight claims.</h1><p>Each row was checked against the official HotSpawn publisher and HLTV. The day-one surprise was already known when this review was written; it is not a retrospectively claimed successful pre-match pick.</p>' + ''.join(sections) + '<div class="notice">Falcons and FURIA advanced on day two; Ninjas in Pyjamas and PARIVISION were eliminated. Aurora–9z and Legacy–BETBOOM are the day-three deciders. These results explain the bracket, not a causal or calibrated probability change. <a href="https://www.hltv.org/events/8932/thunderpick-world-championship-2026">HLTV event</a> · <a href="' + esc(data['facts']['event']['official_publisher_url']) + '">Official day-two report</a>.</div><a class="button primary" href="index.html">Back to day-three decisions</a>'
    return page('Verified days one and two', 'results.html', body, data)


def render_roster(data):
    rows = []
    for item in data['roster_announcements']:
        rows.append(('', [esc(item['subject']) + '<br><span class="small">' + esc(item['role']) + '</span>', esc(item['announcement_utc']),
                         str(item['calendar_days_before_day_one']) + ' calendar days',
                         '<a href="' + esc(item['primary_url']) + '">Aurora’s official announcement</a><br><q>' + esc(item['excerpt']) + '</q>']))
    unknowns = [('', [esc(u['subject']), '<span class="blank">— Unverified</span><br>' + esc(u['reason']),
                      '<a href="' + esc(u['source_url']) + '">Source / manual review</a>']) for u in data['facts']['unknowns']]
    interview = data['facts']['legacy_interview']
    body = '<div class="eyebrow">Primary-source roster timeline</div><h1>A July rebuild is not a new IGL this week.</h1><p>These three announcements were verified directly on Aurora’s official account. The calendar-day calculation ends at 14 October, the TWC opener; it is not a claim about scrim hours, communication quality or adaptation.</p>' + table(['Confirmed change', 'Official timestamp (UTC)', 'Before opener', 'Primary source'], rows) + '<p><a href="' + esc(data['facts']['roster_report_url']) + '">HLTV’s rebuild report</a> provides the wider international-lineup context. No arbitrary percent is subtracted from the current bookmaker estimate for it.</p><h2>Known workload is not measured rest</h2><p>Aurora’s day-two series lasted two maps; 9z’s lasted three. Their actual prior match finish, sleep, travel and practice schedules were not independently established. <a href="' + esc(data['facts']['event']['official_publisher_url']) + '">Official day-two map results</a>.</p>' + table(['Unconfirmed value', 'Blank / limitation', 'Source'], unknowns) + '<h2>Legacy: distinguish first-person preparation context</h2><p>On ' + esc(interview['date']) + ', arT told HLTV <q>' + esc(interview['excerpt']) + '</q> while describing his absence and disrupted practice. This is directly attributed context, not a medical diagnosis or a numerical probability adjustment. <a href="' + esc(interview['url']) + '">Read the original interview</a>.</p><div class="notice">Team signings can be verified without proving they caused a particular result. The pricing engine does not ingest this narrative review.</div>'
    return page('Aurora roster and rest evidence', 'roster.html', body, data)


def render_flagged(data):
    rows = []
    for item in data['facts']['unknowns']:
        rows.append(('', [esc(item['subject']), '<span class="blank">—</span><br>' + esc(item['reason']), '<a href="' + esc(item['source_url']) + '">Source for review</a>']))
    for gap in data['canonical_unresolved']:
        rows.append(('', [esc(gap['team_a']) + ' vs ' + esc(gap['team_b']) + '<br>#' + esc(gap['fixture_id']),
                         '<span class="blank">Pick / probabilities: —</span><br>' + '<br>'.join(esc(f) for f in gap['flags']),
                         '<a href="' + esc(gap['hotspawn_url']) + '">Official HotSpawn listing</a><br><a href="../picks-every-match/unresolved.html#u-' + esc(gap['fixture_id']) + '">Full source attempts</a>']))
    rows += [('', ['Exchange fallback quality', 'Explicit rules, not ticker/settlement clocks, establish kickoff. Two-sided midpoints can still be illiquid; low/zero volume is disclosed and no execution price is promised.', '<a href="https://kalshi.com/markets/kxcs2game">Official exchange</a><br><a href="../data/c64a5e19/board.json">Verbatim rules, bid/ask and volume</a>']),
             ('', ['Ownership and contest strategy', 'HotSpawn percentages are a rounded, changing ownership sample, never probabilities. A qualifying fade sacrifices expected match points; no optimality or backtested edge is asserted.', '<a href="' + LOBBY + '">Official lobby</a><br><a href="method.html">Declared heuristic / formulas</a>']),
             ('', ['Unlisted Group B decider', 'A replayed tournament preview does not prove HotSpawn lists the match. Ownership, offered points and a HotSpawn pick remain blank until the canonical captured lobby confirms it.', '<a href="https://www.hltv.org/matches/2399413/betboom-vs-legacy-thunderpick-world-championship-2026">HLTV decider</a><br><a href="' + LOBBY + '">Official lobby</a>']),
             ('', ['Evidence capture and access', 'Manual research retains source URLs, reviewed date and selected excerpts, not a raw HTTP body or inferred server clock. Hosted collection retains the official raw JSON and cache metadata; requesting no-cache alone never proves freshness.', '<a href="' + LOBBY + '">Official source</a><br><a href="../data/c64a5e19/verification.json">Automated source replay</a>'])]
    attempts = [('', [esc(a['fixture_id']), esc(a['conclusion']), '<a href="' + esc(a['hltv_url']) + '">HLTV first-pass research</a>']) for a in data['facts']['fallback_research']]
    body = '<div class="eyebrow">Published limitations</div><h1>Flagged for Review</h1><p>Needs-review findings do not block publication; unsupported picks do not get invented to remove them. The live coverage gap list below comes from the same canonical board as the homepage.</p>' + table(['Item', 'Limitation / blank', 'Sources'], rows) + '<h2>Fallback-only manual source checks · 15 October</h2><p>HLTV research precedes other-book/exchange evaluation in the research ladder. These dated observations do not establish fresh bookmaker coverage and never override an already accepted featured pick. Detailed automated attempt/HTTP clocks remain in the canonical board.</p>' + table(['Fixture', 'Observed limitation', 'Source'], attempts) + '<p><a class="button primary" href="../picks-every-match/unresolved.html">All current unresolved picks</a> <a class="button" href="../flagged.html">Repository-wide Flagged for Review</a></p>'
    return page('Research limitations and unresolved evidence', 'flagged.html', body, data)


def render_method(data):
    body = f'''<div class="eyebrow">Reproducible, separate layers</div><h1>Estimate first. Choose risk second.</h1><h2>1. Canonical probability, not crowd popularity</h2><p>A listed day-three match copies its accepted canonical win estimates exactly. For decimal odds dA / dB, pA = (1/dA) / ((1/dA) + (1/dB)); pB = 1 − pA. Accepted source weights are 2 for Pinnacle, 1 for other primary providers. Qualitative results/roster notes do not alter the price. <a href="../picks-every-match/method.html">Full strict source, identity and freshness gates</a>.</p><h2>2. Unlisted tournament preview</h2><p>Primary bookmaker JSON is independently re-parsed from the retained official responses. Both participants, a sourced kickoff within five minutes, prematch state and observation age at most four hours are required. The preview has no synthetic fixture ID, ownership or offered points. It cannot become a HotSpawn pick. <a href="../data/c64a5e19/source_payloads.json">Retained primary response payloads</a>.</p><h2>3. Optional one-swing leaderboard rule</h2><ul><li>Listed, accepted external-market match with at least {POLICY['minimum_bookmaker_sources']} primary bookmaker sources.</li><li>Underdog win estimate at least 35%; verified rounded HotSpawn ownership above zero and at most 20%.</li><li>Probability / ownership at least 2×. A displayed zero is not treated as exact zero ownership.</li><li>At most one deliberate underdog swing across the two day-three deciders. Missing evidence means no swing, not a coin flip.</li></ul><p>This is a declared heuristic, not a backtest, a predicted contest rank, a bankroll recommendation or a proof of contest-optimality. The prior 9z upset is already known; it is not an out-of-sample successful pick claimed by this review.</p><h2>4. Show the tradeoff</h2><p>If a correct pick awards the same displayed m points to either side, expected match points are m × p. Sacrificed expectation for an underdog = m × (pFavorite − pUnderdog). Probability / ownership is only a descriptive leverage ratio, not expected profit or a guaranteed leaderboard edge. Correlation, ties, future matches, payout structure and the user’s current leaderboard position are not modelled.</p><h2>5. Evidence and expiry</h2><p>Ownership is read from the exact retained official lobby fixture in canonical participant order and never supplied to the probability parser. Forecasts expire at the earlier of source deadline and match lock; re-rendering never refreshes source clocks. The browser hides expired estimates, while dated result/roster facts remain readable. Automatic four-hour updates are best effort.</p><p><a href="../data/69e4c06a/day3.json">All derived decisions and policy inputs</a> · <a href="../data/69e4c06a/research.json">Primary-linked factual ledger</a> · <a href="{LOBBY}">Official HotSpawn fixture/ownership source</a>.</p>'''
    return page('Decision rules and probability method', 'method.html', body, data)


def build(root=ROOT, now=None):
    root = Path(root)
    data = derive(root, now)
    (root / 'data/69e4c06a').mkdir(parents=True, exist_ok=True)
    (root / 'data/69e4c06a/day3.json').write_text(json.dumps(data, ensure_ascii=False, indent=1, allow_nan=False) + '\n')
    site = root / 'twc-2026'
    site.mkdir(parents=True, exist_ok=True)
    (site / 'assets.css').write_text(CSS)
    (site / 'app.js').write_text(JS)
    for name, renderer in [('index', render_index), ('results', render_results), ('roster', render_roster),
                           ('flagged', render_flagged), ('method', render_method)]:
        (site / (name + '.html')).write_text(renderer(data))
    print('TWC category: 5 pages; decisions from canonical ' + data['canonical_generated_utc'])
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    build(args.root)


if __name__ == '__main__':
    main()
