"""Canonical landing view of the existing strict-fallback-v2 board; no new model."""
from html import escape
from urllib.parse import urlsplit

LOBBY = 'https://play.hotspawn.com/lobby'

def esc(value):
    return escape(str(value if value is not None else ''), quote=True)

def link(url, label):
    # Source evidence can never inject executable URLs into a generated page.
    if urlsplit(str(url or '')).scheme != 'https':
        return ''
    return f'<a href="{esc(url)}" rel="noopener">{esc(label)}</a>'

def render(board):
    if board.get('policy') != 'strict-fallback-v2':
        return '<section id="executive-summary"><h2>Executive summary</h2><p>Evidence-backed picks unavailable. No probabilities inferred.</p><a class="btn" href="ourline/index.html">Open picks &amp; source status</a></section>'
    rows = board.get('open', [])
    counts = {'market': 0, 'model': 0, 'unverified': 0}
    rendered = []
    for row in rows:
        ln = row.get('line')
        basis = ln.get('basis') if ln else 'unverified'
        if basis not in ('market', 'model'):
            basis, ln = 'unverified', None
        counts[basis] += 1
        label = {'market': 'Market-derived', 'model': 'Model estimate', 'unverified': 'Unverified'}[basis]
        sources = [link(row.get('hotspawn_url') or LOBBY, 'HotSpawn fixture')]
        sources += [link(q.get('public_url'), q.get('source_name')) for q in row.get('quotes', [])]
        if basis == 'model':
            sources.append(link((row.get('vrs') or {}).get('page_url'), 'Valve standings'))
        a, b = (f'{ln["prob_a"]*100:.1f}%', f'{ln["prob_b"]*100:.1f}%') if ln else ('—', '—')
        pick = esc(ln['pick_team']) if ln and ln['prob_a'] != ln['prob_b'] else ('No edge' if ln else 'Unverified — no pick')
        reasons = ', '.join(row.get('flags', []))
        rendered.append(f'''<tr data-pick-row data-basis="{basis}" data-lock="{esc(row.get('lock_utc') or row.get('start_utc'))}" data-expiry="{esc(row.get('valid_until_utc'))}" id="pick-{esc(row['fixture_id'])}">
<td data-label="Match"><strong>{esc(row['team_a'])} vs {esc(row['team_b'])}</strong><br><span class="mini">{esc(row.get('competition'))}</span></td>
<td data-label="Start (UTC)"><time datetime="{esc(row.get('start_utc'))}">{esc(row.get('start_utc'))}</time></td>
<td data-label="Win probabilities"><span>{esc(row['team_a'])}: <strong data-prob>{a}</strong></span><br><span>{esc(row['team_b'])}: <strong data-prob>{b}</strong></span></td>
<td data-label="Pick"><strong data-pick>{pick}</strong><br><span class="basis basis-{basis}">{label}</span></td>
<td data-label="Evidence">{' · '.join(s for s in sources if s)}<br><a href="ourline/index.html#m-{esc(row["fixture_id"])}">Full analysis</a><details><summary>Verification notes</summary><p>{esc(reasons) or 'No additional row flags.'}</p><p>Valid until {esc(row.get('valid_until_utc'))}; never after lock.</p></details></td></tr>''')
    stats = ''.join(f'<div class="card"><div class="card-num">{value}</div><div class="card-label">{label}</div></div>' for value, label in [
        (len(rows), 'Open at observation'), (counts['market'], 'Market-derived picks'),
        (counts['model'], 'Model estimates'), (counts['unverified'], 'Unverified · no pick')])
    return f'''<section id="executive-summary" class="dashboard-summary" aria-labelledby="summary-heading">
<p class="dashboard-eyebrow">CS2 · HOTSPAWN PICK’EMS</p><h2 id="summary-heading">Executive summary</h2>
<p class="dashboard-intro">Your matches. The probabilities. One place to start.</p>
<p>Use the table below for every open CS2 match in the captured lobby. Eligible external betting lines come first; only matches without a line use a labelled Valve-rating estimate. Missing or disputed inputs stay blank.</p>
<div class="dashboard-actions"><a class="btn" href="#all-picks">See all match picks ↓</a><a class="btn ghost" href="ourline/index.html">Detailed picks &amp; odds</a></div>
<p class="dashboard-observed">Source snapshot: <time id="dashboard-observed" datetime="{esc(board.get('generated_utc'))}">{esc(board.get('generated_utc'))}</time>. Counts below are at this observation, not a live guarantee.</p>
<div class="cards">{stats}</div>
<p id="dashboard-freshness" role="status" hidden>Some entries have expired or locked. Their probabilities are hidden below; await the next source refresh.</p>
<noscript><p class="banner">JavaScript is off. This is a dated snapshot, not a live pick list. Check each row’s validity time and the official source before use.</p></noscript>
<div class="dashboard-links"><a href="cs2.html">Full lobby inventory</a><a href="ourline/flagged.html">Unverified matches</a><a href="flagged.html">Flagged for Review</a><a href="ourline/method.html">How probabilities work</a></div>
<p class="note">Automatic collection currently targets about 30 minutes, faster than the requested 4–8 hours; GitHub schedules and provider availability are best-effort. Quotes and fixture observations expire after four hours (including reported lobby cache age). <a href="https://github.com/buffedlizard55-lab/MaltaProj2/actions/workflows/ourline-f7279a54.yml">Check refresh runs</a>. No user input is required.</p>
</section>
<section id="all-picks" aria-labelledby="all-picks-heading"><h2 id="all-picks-heading">Every CS2 match currently open for picks — snapshot</h2>
<p>Probabilities are estimates, not verified outcomes. HotSpawn crowd percentages are never used. “Unverified” is not 50/50.</p>
<div class="dashboard-controls"><label for="dashboard-search">Find a team or tournament<input id="dashboard-search" type="search" placeholder="Search matches…" autocomplete="off"></label>
<label for="dashboard-basis">Evidence type<select id="dashboard-basis"><option value="all">All matches</option><option value="market">Market-derived</option><option value="model">Model estimates only</option><option value="unverified">Unverified</option></select></label></div>
<p id="dashboard-count" role="status">{len(rows)} matches in this snapshot</p>
<div class="tablewrap"><table class="dashboard-picks"><caption class="sr-only">All open CS2 fixtures with probability, pick, evidence type and official source links</caption><thead><tr><th scope="col">Match</th><th scope="col">Start (UTC)</th><th scope="col">Win probabilities</th><th scope="col">Pick</th><th scope="col">Evidence</th></tr></thead><tbody>{''.join(rendered)}</tbody></table></div>
<p id="dashboard-empty" hidden>No matches match these filters.</p>
</section>'''
