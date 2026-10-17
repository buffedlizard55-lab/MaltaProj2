"""Render session c32f1b93's audit pages from the built board.

Consumes data/c32f1b93/board.json (+ research.json for the TWC deep dive)
and emits audits/c32f1b93/{index,twc-day4,unresolved,flagged,method}.html
and audits/c32f1b93/style.css. No network access; every number rendered
here is already published in the retained JSON inputs.
"""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import devig  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "c32f1b93"
OUT = ROOT / "audits" / "c32f1b93"

board = json.loads((DATA / "board.json").read_text())
research = json.loads((DATA / "research.json").read_text())

SESSION = board["session"]
GEN = board["generated_utc"]
DATA_AS_OF = board["data_as_of"]

NAV = [
    ("index.html", "Picks board"),
    ("twc-day4.html", "TWC Day 4"),
    ("unresolved.html", "Unresolved"),
    ("flagged.html", "Flagged"),
    ("method.html", "Method"),
]


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def pct(p, digits=1):
    return f"{100 * float(p):.{digits}f}%"


def conf_badge(conf: str) -> str:
    cls = {"Strong": "b-strong", "Solid": "b-solid",
           "Lean": "b-lean", "Toss-up": "b-toss"}.get(conf, "b-none")
    return f'<span class="badge {cls}">{esc(conf)}</span>'


def basis_chip(basis: str) -> str:
    label = {"market": "market", "model": "model", "market+model": "market+model",
             "blank": "BLANK"}.get(basis, basis)
    return f'<span class="chip chip-{basis.replace("+", "p")}">{esc(label)}</span>'


def flag_chips(flags: list[str]) -> str:
    if not flags:
        return '<span class="chip chip-none">clean</span>'
    return " ".join(f'<span class="chip chip-flag">{esc(f)}</span>' for f in flags)


def prob_bar(pa: float) -> str:
    return (f'<div class="pbar"><div class="pbar-a" style="width:{100 * pa:.1f}%"></div>'
            f'<div class="pbar-b" style="width:{100 * (1 - pa):.1f}%"></div></div>')


def page(title: str, active: str, body: str, extra_head: str = "") -> str:
    nav = " · ".join(
        f'<a href="{href}" class="{"nav-on" if href == active else ""}">{esc(label)}</a>'
        for href, label in NAV)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="stylesheet" href="style.css">
{extra_head}
</head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header">
  <div class="header-inner">
    <div class="brand">CS2 Pick&rsquo;em Board <span class="session-tag">{esc(SESSION)}</span></div>
    <nav class="site-nav" aria-label="Session pages">{nav}</nav>
  </div>
</header>
<main id="main" class="wrap">
{body}
</main>
<footer class="site-footer">
  <p>Session {esc(SESSION)} &middot; board generated {esc(GEN)}<br>
  Independent re-derivation from retained primary evidence only (no network at build time).
  Crowd shares are sentiment, never prices. Not betting advice.</p>
</footer>
</body>
</html>"""


def write(name: str, content: str):
    (OUT / name).write_text(content, encoding="utf-8")
    print(f"wrote audits/c32f1b93/{name}")


# ============================================================ index (picks board)
def render_index() -> str:
    s = board["summary"]
    cal = board["calibration"]
    rows = board["open"]

    stat_cards = f"""
    <section class="stats" aria-label="Board statistics">
      <div class="stat"><div class="stat-num">{s['open_fixtures']}</div><div class="stat-label">open fixtures</div></div>
      <div class="stat"><div class="stat-num">{s['with_market_line']}</div><div class="stat-label">market lines</div></div>
      <div class="stat"><div class="stat-num">{s['model_only_line']}</div><div class="stat-label">model-only lines</div></div>
      <div class="stat"><div class="stat-num">{s['blank_unresolved']}</div><div class="stat-label">blank (unresolved)</div></div>
      <div class="stat"><div class="stat-num">{s['strong_picks']}</div><div class="stat-label">Strong picks</div></div>
      <div class="stat"><div class="stat-num">{s['contrarian_climb']}</div><div class="stat-label">contrarian climbs</div></div>
      <div class="stat"><div class="stat-num">{s['n_sources_total']}</div><div class="stat-label">price sources</div></div>
      <div class="stat"><div class="stat-num">{s['flags_raised']}</div><div class="stat-label">flags raised</div></div>
    </section>"""

    cal_card = f"""
    <section class="card">
      <h2>Calibration (our own fit, published raw)</h2>
      <p>The Valve-VRS slope <em>k</em> is fitted by least squares through the origin on the
      {cal['n_pairs']} fixtures that carry both a market median and a two-side VRS join:
      <strong>k = {cal['k']:.4f}</strong> (raw {cal['k_raw']:.4f}, unclamped, inside the
      [{cal['bounds'][0]}, {cal['bounds'][1]}] stability band; k=1 reproduces Valve's own
      curve, where a 400-point rank delta is a 90% win probability), median absolute
      probability error <strong>{cal['mae_prob']:.4f}</strong>. For comparison, session
      fe803b80 published k=0.275 with MAE 0.1002 on the same pair count. Our slope is
      steeper because the live Oct-16 ladder compressed several mid-tier deltas (TWC
      point swings, 128-day decay) while the markets held &mdash; the same markets now
      imply more certainty per rating point. Four pairs imply a negative slope (market
      and ladder disagree on the favourite); they are published in full on the
      <a href="method.html">method page</a> rather than dropped.</p>
    </section>"""

    # Headline semis
    sf_rows = [r for r in rows if r.get("twc")]
    semi_html = '<section class="card"><h2>Headline: Thunderpick World Championship semifinals (Bo3)</h2>'
    for r in sf_rows:
        twc = r["twc"]
        semi_html += f"""
        <article class="semi">
          <h3>{esc(r['team_a'])} vs {esc(r['team_b'])} &middot; {esc(r['start_utc'])}</h3>
          <p class="semi-line">Pick: <strong>{esc(r['pick'])}</strong> {pct(r['pick_probability'])}
          {conf_badge(r['confidence'])} {basis_chip(r['basis'])}</p>
          {prob_bar(r['line']['prob_a'])}
          <p class="semi-detail">Market median {pct(r['market']['prob_a'])} over {r['market']['n_sources']} sources
          ({esc(', '.join(r['market']['sources']))}) &middot; model {pct(r['model']['prob_a'])}
          (live VRS delta {r['model']['vrs']['delta']:+.0f} pt) &middot; blend 85/15.</p>
          <p class="semi-detail">{esc(twc.get('read_note', ''))}</p>
        </article>"""
    semi_html += '<p class="dim">Full day-1&ndash;3 results, lineups, form and the contrarian framing: <a href="twc-day4.html">TWC Day 4 page</a>.</p></section>'

    # Full board table
    trs = []
    for r in rows:
        crowd = r.get("crowd")
        crowd_html = (f'{r["crowd"]["crowd_a"]}&nbsp;% / {r["crowd"]["crowd_b"]}&nbsp;%'
                      + (f' <span class="dim">(via {esc(r["crowd"].get("matchup_mapped_from_ledger_fixture_id", r["fixture_id"]))})</span>'
                         if r["crowd"].get("matchup_mapped_from_ledger_fixture_id") else "")
                      if crowd else '<span class="dim">not captured</span>')
        model = r.get("model") or {}
        if model.get("basis") == "valve_vrs":
            model_html = (f'VRS {pct(model["prob_a"])}<br><span class="dim">delta {model["vrs"]["delta"]:+.0f} pt'
                          f' &middot; k={model["vrs"]["k"]:.3f} &middot; RD={model["vrs"]["rd"]:.0f}</span>')
        elif model.get("basis"):
            model_html = (f'Elo {pct(model["prob_a"])}<br><span class="dim">{esc(model["basis"].replace("_", " "))}'
                          f' &middot; k={model["elo"]["k"]:.0f} &middot; {model["elo"]["n_matches"]} matches</span>')
        else:
            model_html = '<span class="dim">&ndash;</span>'
        if r.get("market"):
            spread = r["market"].get("spread_a")
            spread_txt = f"{spread:.3f}" if spread is not None else "n/a"
            market_html = (f'{pct(r["market"]["prob_a"])}<br>'
                           f'<span class="dim">{r["market"]["n_sources"]} source(s)'
                           f' &middot; spread {spread_txt}</span>')
        else:
            market_html = '<span class="dim">no usable price</span>'
        line_html = (f'<strong>{pct(r["line"]["prob_a"])}</strong>' if r.get("line")
                     else '<span class="dim">BLANK</span>')
        fix_link = (f'<a href="{esc(r["fixture_url"])}">{esc(r["fixture_id"])}</a>'
                    if r.get("fixture_url") else f'<span class="dim">{esc(r["fixture_id"])}</span>')
        trs.append(f"""
        <tr data-conf="{esc(r['confidence'])}" data-basis="{esc(r['basis'])}" data-comp="{esc(r['competition'])}">
          <td data-label="Fixture">{fix_link}</td>
            <span class="dim">{esc(r['competition'])} &middot; tier {esc(str(r['tier']))} &middot; {esc(r['start_utc'])}</span></td>
          <td data-label="Matchup"><strong>{esc(r['team_a'])}</strong> vs <strong>{esc(r['team_b'])}</strong></td>
          <td data-label="Market">{market_html}</td>
          <td data-label="Model">{model_html}</td>
          <td data-label="Published line">{line_html}<br>{conf_badge(r['confidence'])} {basis_chip(r['basis'])}</td>
          <td data-label="Crowd">{crowd_html}</td>
          <td data-label="Role / flags">{esc(r.get('role') or '')}<br>{flag_chips(r['flags'])}</td>
        </tr>""")

    table = f"""
    <section class="card">
      <h2>Every open fixture ({len(rows)})</h2>
      <p class="dim">All times UTC. Crowd % is HotSpawn pick'em ownership (sentiment context, never a price).
      Filter: <input id="f-conf" aria-label="filter by confidence" placeholder="confidence">
      <input id="f-text" aria-label="filter by text" placeholder="team, competition, flag&hellip;"></p>
      <div class="table-scroll">
      <table class="board" id="board-table">
        <thead><tr>
          <th>Fixture</th><th>Matchup</th><th>Market</th><th>Model</th>
          <th>Published line</th><th>Crowd</th><th>Role / flags</th>
        </tr></thead>
        <tbody>{''.join(trs)}</tbody>
      </table>
      </div>
    </section>"""

    body = f"""
    <h1>Independent CS2 picks board &mdash; session {esc(SESSION)}</h1>
    <p class="lede">Every probability on this board is re-derived from retained primary evidence
    (Valve's official VRS ladder, bookmaker/exchange quotes, bo3.gg history, HLTV live ladders).
    No prior board's numbers are inherited: the VRS joins, the market medians, the Elo fallback and
    the slope fit are all recomputed here, and every join is audited on the
    <a href="method.html">method page</a>. Data as of {esc(DATA_AS_OF)}; board generated {esc(GEN)}.</p>
    {stat_cards}
    {cal_card}
    {semi_html}
    {table}
    <section class="card">
      <h2>Ledger pages</h2>
      <ul>
        <li><a href="twc-day4.html">TWC Day 4</a> &mdash; both semifinals line-by-line, day 1&ndash;3 results, bracket state</li>
        <li><a href="unresolved.html">Unresolved &amp; limitations</a> &mdash; the one BLANK fixture, its 8-step attempt ledger, and what this board does not know</li>
        <li><a href="flagged.html">Flagged for review</a> &mdash; corrections to prior boards, irregularities, and all {s['flags_raised']} flags grouped by type</li>
        <li><a href="method.html">Method &amp; calibration</a> &mdash; the seven published rules, the 19-pair fit, the VRS join ledger, the Elo fallback</li>
      </ul>
    </section>"""
    extra = """<script>
function filterBoard(){
  var c=document.getElementById('f-conf').value.toLowerCase();
  var t=document.getElementById('f-text').value.toLowerCase();
  document.querySelectorAll('#board-table tbody tr').forEach(function(tr){
    var ok=(c===''||tr.getAttribute('data-conf').toLowerCase().indexOf(c)===0)
        &&(t===''||tr.textContent.toLowerCase().indexOf(t)!==-1);
    tr.style.display=ok?'':'none';
  });
}
document.getElementById('f-conf').addEventListener('input',filterBoard);
document.getElementById('f-text').addEventListener('input',filterBoard);
</script>"""
    return page("Picks board · " + SESSION, "index.html", body, extra)


# ============================================================ TWC day 4
def render_twc() -> str:
    twc = board["twc"]
    ev = twc["event"]
    res = twc["results"]
    sf1 = research["semifinal_lines_fresh"]["sf1_furia_aurora"]
    sf2 = research["semifinal_lines_fresh"]["sf2_falcons_betboom"]
    rows = {r["fixture_id"]: r for r in board["open"]}

    def semi_block(fid, sf, title):
        r = rows[fid]
        qtrs = "".join(
            f"<tr><td>{esc(q['source_key'])}</td><td>{q['decimal_a']:.2f}</td>"
            f"<td>{q['decimal_b']:.2f}</td>"
            f"<td>{pct(devig(q['decimal_a'], q['decimal_b'])[0])}</td>"
            f"<td>{pct(devig(q['decimal_a'], q['decimal_b'])[1])}</td>"
            f"<td class='dim'>{esc(q.get('note', '') or '&ndash;')}</td></tr>"
            for q in sf["quotes"])
        mkt = r["market"]
        mdl = r["model"]
        line = r["line"]
        fan = sf.get("hltv_fan_vote")
        analytics = sf.get("hltv_analytics")
        live = sf.get("live_vrs")
        form = sf.get("form", {})
        lu = sf["lineups"]

        if fan:
            sentiment_html = (
                f"<p>HLTV fan vote: <strong>{fan['aurora_pct']:.1f}% {esc(r['team_b'])}</strong> / "
                f"{fan['furia_pct']:.1f}% {esc(r['team_a'])} "
                f"(<span class='dim'>{esc(fan['note'])}</span>). HLTV analytics prose favours "
                f"{esc(r['team_b'])} (<span class='dim'>{esc(analytics['fans_of'])}</span>). "
                "The published prices and the live Valve ladder do not agree with that prose: "
                f"the market median backs {esc(r['pick'])} and the live VRS delta is "
                f"{mdl['vrs']['delta']:+.0f} pt. Crowd share is sentiment, never a price (policy rule 6).</p>")
        else:
            sentiment_html = ""
        if sf.get("betboom_upset_context"):
            sentiment_html += f"<p>{esc(sf['betboom_upset_context'])}</p>"
        h2h_html = esc(sf.get("h2h") or (analytics["h2h_alltime"] if analytics else ""))
        if live:
            live_links = " ".join(
                f'<a href="{esc(u)}">{esc(u)}</a>' for u in live.get("sources", []))
            live_html = (f"<p class='dim'>Live VRS read: {esc(live.get('note', ''))} "
                         f"Sources: {live_links}</p>")
        else:
            live_html = ""
        return f"""
        <article class="card semi-detail" id="{fid}">
          <h2>{esc(title)}</h2>
          <p class="dim">{esc(r['competition'])} &middot; {esc(r['start_utc'])} (Bo3) &middot;
          <a href="{esc(r['fixture_url'])}">fixture evidence (HLTV match page)</a></p>

          <h3>Published line</h3>
          <p class="big-line"><strong>{esc(r['pick'])}</strong> {pct(r['pick_probability'])}
          {conf_badge(r['confidence'])} {basis_chip(r['basis'])}</p>
          {prob_bar(line['prob_a'])}
          <p>Blend: 0.85 &times; market median {pct(mkt['prob_a'])} + 0.15 &times; model {pct(mdl['prob_a'])}
          = <strong>{pct(line['prob_a'])}</strong>. Market spread across {mkt['n_sources']} sources:
          {mkt.get('spread_a') and f"{mkt['spread_a']:.3f}"} (tight). Model: live VRS delta
          {mdl['vrs']['delta']:+.0f} pt at fitted k={mdl['vrs']['k']:.3f} &rarr; {pct(mdl['prob_a'])}.</p>

          <h3>Price evidence (no-vig per source)</h3>
          <div class="table-scroll"><table>
            <thead><tr><th>Source</th><th>dec. {esc(r['team_a'])}</th><th>dec. {esc(r['team_b'])}</th>
            <th>P({esc(r['team_a'])})</th><th>P({esc(r['team_b'])})</th><th>Note</th></tr></thead>
            <tbody>{qtrs}</tbody>
          </table></div>
          <p class="dim">Median of per-source no-vig probabilities is our published market rule
          (robust to a single outlier book; prior sessions used a source-weighted mean).</p>

          <h3>Verified starting fives</h3>
          <p><strong>{esc(r['team_a'])}:</strong> {esc(', '.join(lu['furhia'] if 'furhia' in lu else lu.get('falcons', [])))}<br>
             <strong>{esc(r['team_b'])}:</strong> {esc(', '.join(lu['aurora'] if 'aurora' in lu else lu.get('betboom', [])))}</p>
          <p class="dim">Source: {esc(lu['source'])}</p>

          <h3>Form into the semifinal</h3>
          <p>{esc(r['team_a'])}: {esc(form.get('furhia') or form.get('falcons') or '')}<br>
             {esc(r['team_b'])}: {esc(form.get('aurora') or form.get('betboom') or '')}<br>
             <span class="dim">Rest: {esc(form.get('rest', ''))}</span></p>

          <h3>Sentiment vs prices (the contrarian framing)</h3>
          {sentiment_html}

          <h3>Head-to-head &amp; context</h3>
          <p>{h2h_html}</p>
          {live_html}
        </article>"""

    # Day 1-3 results
    day_labels = {"day1_2026_10_14": "Day 1 &middot; 2026-10-14",
                  "day2_2026_10_15": "Day 2 &middot; 2026-10-15",
                  "day3_2026_10_16": "Day 3 &middot; 2026-10-16"}
    day_html = ""
    for day_key in ("day1_2026_10_14", "day2_2026_10_15", "day3_2026_10_16"):
        day_html += f"<h3>{day_labels[day_key]}</h3><ul>"
        for m in res.get(day_key, []):
            upset = " <span class='badge b-warn'>upset</span>" if m.get("upset") else ""
            maps = f" &middot; {esc(m['maps'])}" if m.get("maps") else ""
            note = f" &middot; {esc(m['note'])}" if m.get("note") else ""
            veto = f"<br><span class='dim'>Veto: {esc(m['veto'])}</span>" if m.get("veto") else ""
            link = (f" <a href='{esc(m['url'])}'>HLTV match</a>"
                    if m.get("url") else "")
            day_html += (f"<li>Group {esc(m.get('group', ''))} {esc(m.get('stage', ''))}: "
                         f"<strong>{esc(m['winner'])}</strong> {esc(m.get('series', ''))} "
                         f"{esc(m['loser'])}{upset}{maps}{note}{veto}{link}</li>")
        day_html += "</ul>"

    bracket = res.get("playoff_bracket") or {}
    bracket_html = ""
    if bracket:
        parts = []
        for bkey in sorted(bracket):
            b = bracket[bkey]
            if isinstance(b, dict):
                teams = " vs ".join(esc(t) for t in b.get("teams", []))
                when = esc(b.get("start_utc", ""))
                ev_url = f" <a href='{esc(b['url'])}'>HLTV</a>" if b.get("url") else ""
                parts.append(f"<li><strong>{esc(bkey.replace('_', ' '))}</strong>: {teams} &middot; {when}{ev_url}"
                             + (f"<br><span class='dim'>Start-time evidence: {esc(b.get('start_evidence', ''))}</span>"
                                if b.get("start_evidence") else "")
                             + "</li>")
            else:
                parts.append(f"<li>{esc(str(b))}</li>")
        bracket_html = "<h3>Playoff bracket state</h3><ul>" + "".join(parts) + "</ul>"

    body = f"""
    <h1>Thunderpick World Championship 2026 &mdash; Day 4 (semifinals)</h1>
    <p class="lede">{esc(ev['name'])} &middot; {esc(ev['dates'])} &middot; {esc(ev['location'])} &middot;
    {esc(ev['format'])} &middot; prize pool {esc(ev['prize_pool_note'])}<br>
    <span class="dim">Event page: <a href="{esc(ev['url'])}">{esc(ev['url'])}</a> &middot;
    {esc(ev['nip_replacement_note'])} (<a href="{esc(ev['nip_replacement_source'])}">source</a>)</span></p>

    <section class="card">
      <h2>Day 1&ndash;3 verified results</h2>
      {day_html}
      {bracket_html}
      <p class="dim">Aurora roster verdict: {esc(twc['aurora_roster_verdict'])}</p>
    </section>

    {semi_block('1080207', sf1, 'Semifinal 1 &middot; FURIA vs Aurora &middot; 14:00 UTC')}
    {semi_block('1080208', sf2, 'Semifinal 2 &middot; Falcons vs BETBOOM &middot; 17:00 UTC')}

    <section class="card">
      <h2>Final preview (Bo5, Oct 18)</h2>
      <p>The final pits the SF1 winner against the SF2 winner. Our published lines cover the semis
      only; the final will be ledgered by whichever session is live when the bracket resolves.
      Watchlist notes: BETBOOM carried 8 maps in 3 days into SF2 (fatigue) but owns the
      Legacy upset's momentum; Aurora has one day less rest than FURIA and lost the sole 2026
      meeting 1&ndash;2 (EPL S24, HLTV 2398743) while FURIA leads the all-time series 9&ndash;4.</p>
    </section>"""
    return page("TWC Day 4 · " + SESSION, "twc-day4.html", body)


# ============================================================ unresolved
def render_unresolved() -> str:
    un = board["unresolved"]
    items = []
    for u in un:
        ledger = "".join(
            f"<li><strong>{esc(step['step'])}</strong> &mdash; {esc(step['result'])}"
            f"{' <a href=' + esc(step['url']) + '>source</a>' if step.get('url') else ''}</li>"
            for step in u.get("attempt_ledger", []))
        items.append(f"""
        <article class="card">
          <h2>{esc(u['match'])} &middot; fixture {esc(u['fixture_id'])}</h2>
          <p class="dim">{esc(u['competition'])} &middot; {esc(u['start_utc'])} &middot;
          {f"<a href='{esc(u['fixture_url'])}'>fixture evidence</a>" if u.get("fixture_url") else "no fixture link captured"}</p>
          <p>Directional read (not a probability): <strong>{esc(u.get('directional_pick') or 'none')}</strong></p>
          <p><strong>Why blank:</strong> {esc(u.get('policy', 'no derived line'))}</p>
          <h3>Attempt ledger (every avenue tried, in order)</h3>
          <ol>{ledger}</ol>
          {flag_chips(u.get('flags', []))}
        </article>""")
    body = f"""
    <h1>Unresolved &amp; limitations</h1>
    <p class="lede">{len(un)} fixture stays BLANK. Policy rule 1: a probability is published only
    when it can be derived from a retained source; otherwise the cell stays blank and the fixture
    is ledgered here with the full attempt trail.</p>
    {''.join(items)}
    <section class="card">
      <h2>Scheduling disclosure</h2>
      <p>Fixture 1080200 (Wildcard vs DENDELE, 2026-11-12) is included with the
      <span class="chip chip-flag">placeholder_scheduling</span> flag: HotSpawn carries it with
      status &ldquo;started&rdquo; although kickoff is 26 days after the capture &mdash; a
      placeholder-data quirk (a match cannot be in progress before it starts). Session fe803b80
      included the same fixture; we do too, flagged. Both teams now carry live Oct-16 VRS rows
      (Wildcard AM #8 / 1332 pt, DENDELE AM #7 / 1355 pt), so the model line is a genuine
      two-side VRS join: DENDELE {pct([r for r in board['open'] if r['fixture_id']=='1080200'][0]['line']['prob_b'])}.</p>
    </section>
    <section class="card">
      <h2>Known limitations</h2>
      <ul>
        <li>The Oct-16 live ladder read covers Europe top-145, Americas top-28 and Asia top-26.
        Deep-tail teams outside those ranges (Privateer, Bebop, Donstu) keep their Oct-5 file
        values, disclosed per row on the method page.</li>
        <li>The fitted slope k is a through-origin least-squares fit on 19 joined pairs; four
        pairs imply a negative slope (market/ladder disagreement). The raw fit, the MAE and every
        pair are published &mdash; nothing is trimmed.</li>
        <li>Melbet and bc.game (via egamersworld) are single-book lines on several fixtures;
        the <span class="chip chip-flag">single_source</span> flag marks every such row.</li>
        <li>Crowd shares are HotSpawn pick'em ownership at read time &mdash; sentiment context
        only, never a price input (rule 6).</li>
        <li>XomA's assistant-coach date is unverified-secondary; FURIA/Aurora analyst prose and
        the fetched prices diverge (flagged, not adjudicated).</li>
      </ul>
    </section>"""
    return page("Unresolved · " + SESSION, "unresolved.html", body)


# ============================================================ flagged
def render_flagged() -> str:
    corrections = board["corrections"]
    corr_html = "".join(f"""
      <article class="card">
        <h2>{esc(c['title'])} <span class="dim">&middot; {esc(c.get('fixture_id', ''))}</span></h2>
        <p>{esc(c['detail'])}</p>
        <p class="dim">Evidence: {' '.join(f'<a href="{esc(u)}">{esc(u)}</a>' if u.startswith('http') else f'<code>{esc(u)}</code>' for u in c.get('evidence', []))}</p>
      </article>""" for c in corrections)

    # group flags
    groups: dict[str, list] = {}
    for r in board["open"]:
        for fl in r["flags"]:
            groups.setdefault(fl, []).append(r)
    flag_html = "".join(f"""
      <article class="card">
        <h2><span class="chip chip-flag">{esc(fl)}</span> &middot; {len(rs)} fixture(s)</h2>
        <ul>{''.join(f"<li><a href='index.html#{r['fixture_id']}'>{esc(r['fixture_id'])}</a> {esc(r['team_a'])} vs {esc(r['team_b'])}</li>" for r in rs)}</ul>
      </article>""" for fl, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])))

    irregularities = [
        ("fe803b80 joined Betclic to the wrong Valve row",
         "The prior board's duplicate-name default (highest standing number) joined Apogee Betclic to row #183 (Demho, Dr3nquu, eskyy, hades, Prism &mdash; the pre-August hades era, 765 pt) instead of row #45 (1333 pt, the current five). That manufactured a &minus;690 pt delta on 1081515 and dragged the prior calibration fit to k=0.0927 (clamped). This board's default is the lowest-standing row, verified for all 31 duplicate names against the live Oct-16 ladder, and Betclic's lineage is pinned by roster evidence (HLTV team/12916: ultimate replaced hades on Aug 11; the quartet inherited KOLESIE's VRS position on Jul 22)."),
        ("fe803b80 joined ex-RUSTEC to a stale row",
         "Row #152 (823.9 pt, last played 2026-08-17) instead of the active #92 lineage (1066.4 pt, last played 2026-09-27). The pick on 1079638 flips from ILLYRIANS to ex-RUSTEC (+172 pt live delta)."),
        ("fe803b80 joined Chinggis Warriors to a stale row",
         "Row #220 (685 pt, Aceari/hasteka five) instead of #87 (1084 pt, the current four-fifths). The fixture stays blank for the WXM reason, but the directional read strengthens: Chinggis now carries a live AS #5 / 1200 pt row."),
        ("fe803b80's published slope is internally inconsistent",
         "The prior board published k=0.275, but its own row-implied effective slopes range 0.10&ndash;1.33 (FURIA&ndash;Aurora 0.5434 at delta +113 &rArr; k&asymp;0.119; ASTRAL&ndash;Leo 0.7073 at delta +71 &rArr; k&asymp;0.96; BandaChuya&ndash;Enjoy 0.3269 at delta &minus;70 &rArr; k&asymp;1.33). A single through-origin slope cannot reproduce all three &mdash; the prior board's rows were computed with mixed join vintages. This board re-fits on uniformly joined pairs and publishes the raw fit."),
        ("9z day-1 Nuke score capture error",
         "An earlier desk capture recorded 9z&ndash;Aurora Nuke as 16&ndash;14; the HLTV match page reads 13&ndash;1. The verified day-1 result stands: 9z 2&ndash;0 Aurora (Inferno 13&ndash;11, Nuke 13&ndash;1) &mdash; the day's upset."),
        ("HLTV analytics prose vs fetched prices (SF1)",
         "HLTV's analytics blurb favours Aurora (better form ranking, won the only 2026 meeting) while the fetched 7-source median (51.0% FURIA) and the live VRS delta (&minus;21 pt) sit on FURIA's side. Both are published; the blend lands at 50.6% FURIA &mdash; a toss-up, flagged as such."),
        ("Glicko RD inconsistency across prior boards",
         "Prior boards used varying RD assumptions; this board uses Valve's documented default RD=75 (fit.js) everywhere and publishes the constant."),
        ("Duplicate team names on the Valve ladder",
         "The Oct-5 file carries 31 canon keys with two rows each (main roster + academy/stale lineage), and the live Oct-16 ladder repeats the pattern (e.g. Sashi, Johnny Speeds, Chinggis, The Huns, ex-RUSTEC, Betclic, CYBERSHOKE, RBLS, WBT/WBT Academy). Join rule: lowest standing number = main roster, pinned by roster evidence where it matters (FIXTURE_VRS_PICKS)."),
    ]
    irr_html = "".join(f"<article class='card'><h2>{esc(t)}</h2><p>{esc(d)}</p></article>"
                       for t, d in irregularities)

    body = f"""
    <h1>Flagged for review</h1>
    <p class="lede">Corrections applied to prior boards, known irregularities, and every flag
    raised on this board's rows (grouped by type).</p>
    <h2>Corrections to prior boards</h2>
    {corr_html}
    <h2>Irregularities &amp; disclosures</h2>
    {irr_html}
    <h2>Flags raised on this board ({board['summary']['flags_raised']})</h2>
    {flag_html}"""
    return page("Flagged · " + SESSION, "flagged.html", body)


# ============================================================ method
def render_method() -> str:
    cal = board["calibration"]
    rules = board["rules"]
    elo = board["elo"]
    vrs = board["vrs_file"]

    import math as _m
    C = 1.0 / _m.sqrt(1.0 + 3.0 * (_m.log(10) / 400.0) ** 2 * 75.0 ** 2 / _m.pi ** 2) * (_m.log(10) / 400.0)
    pair_rows = []
    for p in cal["pairs"]:
        x = C * p["delta"]
        ik = (_m.log(p["market_prob_a"] / (1 - p["market_prob_a"])) / x) if abs(x) > 1e-9 else float("inf")
        pair_rows.append(
            f"<tr><td>{esc(p['fixture_id'])}</td><td>{p['delta']:+.1f}</td>"
            f"<td>{p['market_prob_a']:.4f}</td><td>{ik:.3f}</td></tr>")
    pairs_html = "".join(pair_rows)

    # VRS join ledger from the board rows
    join_rows = []
    for r in board["open"]:
        mdl = r.get("model") or {}
        if mdl.get("basis") == "valve_vrs":
            v = mdl["vrs"]
            join_rows.append(
                f"<tr><td>{esc(r['fixture_id'])}</td><td>{esc(r['team_a'])}</td>"
                f"<td>{v['points_a']:.0f} pt ({esc(str(v.get('standing_a', '')))})</td>"
                f"<td>{esc(r['team_b'])}</td><td>{v['points_b']:.0f} pt ({esc(str(v.get('standing_b', '')))})</td>"
                f"<td>{v['delta']:+.1f}</td><td class='dim'>{esc(str(v.get('join_a', ''))[:120])}<br>{esc(str(v.get('join_b', ''))[:120])}</td></tr>")
        elif mdl.get("basis"):
            e = mdl.get("elo", {})
            join_rows.append(
                f"<tr><td>{esc(r['fixture_id'])}</td><td>{esc(r['team_a'])}</td>"
                f"<td class='dim'>Elo {e.get('rating_a', 0):.0f}</td>"
                f"<td>{esc(r['team_b'])}</td><td class='dim'>Elo {e.get('rating_b', 0):.0f}</td>"
                f"<td class='dim'>&ndash;</td><td class='dim'>{esc(mdl['basis'])}</td></tr>")
    join_html = "".join(join_rows)

    body = f"""
    <h1>Method &amp; calibration</h1>
    <p class="lede">The seven published rules, the slope fit, and the complete VRS join ledger.
    Everything here is recomputed from retained evidence; nothing is inherited from a prior board.</p>

    <section class="card">
      <h2>The seven published rules</h2>
      <ol>
        <li><strong>Blank policy.</strong> {esc(rules['blank_policy'])}</li>
        <li><strong>Market consensus.</strong> {esc(rules['market_consensus'])}</li>
        <li><strong>Valve VRS model.</strong> {esc(rules['vrs_model'])}</li>
        <li><strong>Elo (last resort).</strong> {esc(rules['elo_model'])}</li>
        <li><strong>Published line.</strong> {esc(rules['blend'])} &mdash; market median when at least one usable price exists, else the model, else BLANK.</li>
        <li><strong>Crowd policy.</strong> {esc(rules['crowd_policy'])}</li>
        <li><strong>Seed policy.</strong> {esc(rules['seed_policy'])}</li>
      </ol>
    </section>

    <section class="card">
      <h2>Calibration &mdash; our own fit</h2>
      <p>Valve's README states the published curve is too steep at both ends, so the slope is
      learned from observed bookmaker lines instead of assuming k=1. Fit: least squares through
      the origin on ln(market/(1-market)) = k &middot; C &middot; (points<sub>a</sub> &minus; points<sub>b</sub>),
      C = g&middot;ln10/400 with g = 1/sqrt(1 + 3Q&sup2;RD&sup2;/&pi;&sup2;), RD = 75 (Valve's fit.js default).</p>
      <p><strong>k = {cal['k']:.4f}</strong> (raw {cal['k_raw']:.4f}, {"clamped to band" if cal['clamped'] else "unclamped, inside band"},
      band [{cal['bounds'][0]}, {cal['bounds'][1]}], minimum {cal['min_pairs']} pairs),
      n = {cal['n_pairs']} pairs, MAE(prob) = <strong>{cal['mae_prob']:.4f}</strong>.
      fe803b80 published k=0.275, MAE 0.1002 on 19 pairs. Our slope is steeper
      (0.497 vs 0.275) because the live Oct-16 ladder compressed several mid-tier deltas
      (TWC point swings and 128-day decay) while the markets held &mdash; and our MAE is
      lower (0.059 vs 0.100), i.e. the fit is better, not just different.</p>
      <div class="table-scroll"><table id="calibration-pairs">
        <thead><tr><th>Fixture</th><th>VRS delta (pt)</th><th>Market P(team A)</th><th>Row-implied k</th></tr></thead>
        <tbody>{pairs_html}</tbody>
      </table></div>
      <p class="dim">Row-implied k = logit(market) / (C&middot;delta), natural logit (fe803b80 convention). Negative values mark
      market/ladder disagreements (published, not trimmed). The spread is the reason the fit is
      disclosed with its MAE rather than presented as exact.</p>
    </section>

    <section class="card">
      <h2>VRS join ledger (every fixture team)</h2>
      <p>Point vintages: <strong>live Oct-16</strong> rows come from HLTV's rendered regional
      ladders (read {esc(research['form_notes']['live_vrs_reads']['ladder_2026_10_16']['read_utc'])};
      the Oct-5 global file is the latest full ladder in the repo); <strong>file</strong> rows are the
      retained Oct-5 Valve ladder. TWC participants must use live rows &mdash; the Oct-5 file
      predates the group stage. Duplicate-name rule: lowest standing number = main roster
      (verified for all 31 duplicate keys against the live ladder). Fixture-specific lineage
      pins (roster evidence) are marked &ldquo;lineage pinned&rdquo;.</p>
      <div class="table-scroll"><table>
        <thead><tr><th>Fixture</th><th>Team A</th><th>Rating A</th><th>Team B</th><th>Rating B</th><th>Delta</th><th>Join notes</th></tr></thead>
        <tbody>{join_html}</tbody>
      </table></div>
    </section>

    <section class="card">
      <h2>Elo fallback</h2>
      <p>{elo['n_matches']} usable matches from {elo['n_history_teams']} teams in the retained
      bo3.gg history (the 950-match capture list, filtered to canon-joinable rows),
      {elo['n_seeded']} teams seeded from the VRS table. Parameters: base {elo['params']['base']:.0f},
      k={elo['params']['k']:.0f}, {elo['params']['passes']} chronological passes,
      {esc(elo['params']['anchor'])}. Source: {esc(elo['source'])}.</p>
    </section>

    <section class="card">
      <h2>Valve file &amp; live ladder provenance</h2>
      <p>Retained Valve VRS global ladder: {esc(vrs['path'])} ({vrs['teams_in_file']} team rows),
      source <a href="{esc(vrs['source'])}">{esc(vrs['source'])}</a>.</p>
      <p>Live Oct-16 regional ladders (read for overrides):
      <a href="https://www.hltv.org/valve-ranking/teams/2026/october/16/region/Europe">Europe</a> &middot;
      <a href="https://www.hltv.org/valve-ranking/teams/2026/october/16/region/Americas">Americas</a> &middot;
      <a href="https://www.hltv.org/valve-ranking/teams/2026/october/16/region/Asia">Asia</a>.
      HLTV marks the ladder &ldquo;Beta: includes matches and secured prize money from unfinished events&rdquo;.</p>
    </section>"""
    return page("Method · " + SESSION, "method.html", body)


# ============================================================ style.css
STYLE_CSS = """/* c32f1b93 audit pages — mobile-first dark theme */
:root{
  --bg:#0b1020; --panel:#131b33; --panel-alt:#182242; --border:#283663;
  --text:#eef2ff; --muted:#a5b4fc; --accent:#38bdf8;
  --good:#34d399; --warn:#fbbf24; --bad:#f87171;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,sans-serif;
  line-height:1.5;overflow-x:hidden}
a{color:var(--accent);text-decoration:underline;word-break:break-word}
a:hover{color:#7dd3fc}
.skip-link{position:absolute;left:-9999px;top:0;background:var(--accent);color:#061224;
  padding:.5rem 1rem;font-weight:700;z-index:999}
.skip-link:focus{left:.5rem;top:.5rem}
.site-header{background:#0e162e;border-bottom:1px solid var(--border);
  padding:.85rem 1rem;position:sticky;top:0;z-index:50}
.header-inner{max-width:1240px;margin:0 auto;display:flex;flex-wrap:wrap;
  align-items:center;justify-content:space-between;gap:.65rem}
.brand{font-weight:800;font-size:1.05rem}
.session-tag{display:inline-block;background:var(--panel-alt);border:1px solid var(--border);
  border-radius:999px;padding:.05rem .55rem;font-size:.72rem;color:var(--muted);
  font-weight:600;margin-left:.4rem;vertical-align:middle}
.site-nav{font-size:.85rem}
.site-nav a{margin-left:.6rem;color:var(--muted);text-decoration:none}
.site-nav a.nav-on{color:var(--accent);font-weight:700;text-decoration:underline}
.wrap{max-width:1240px;margin:0 auto;padding:1rem}
h1{font-size:1.45rem;margin:.4rem 0 .6rem}
h2{font-size:1.12rem;margin:1.1rem 0 .5rem}
h3{font-size:.98rem;margin:.9rem 0 .35rem}
p{margin:.45rem 0}
.lede{font-size:1.02rem;color:var(--muted)}
.dim{color:var(--muted);font-size:.85rem}
.card{background:var(--panel);border:1px solid var(--border);border-radius:14px;
  padding:1rem;margin:1rem 0}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:.6rem;margin:1rem 0}
.stat{background:var(--panel);border:1px solid var(--border);border-radius:12px;
  padding:.7rem .8rem}
.stat-num{font-size:1.5rem;font-weight:800}
.stat-label{color:var(--muted);font-size:.78rem}
@media(min-width:720px){.stats{grid-template-columns:repeat(4,1fr)}}
.badge{display:inline-block;border-radius:999px;padding:.08rem .55rem;
  font-size:.72rem;font-weight:700;vertical-align:middle}
.b-strong{background:rgba(52,211,153,.16);color:var(--good);border:1px solid var(--good)}
.b-solid{background:rgba(56,189,248,.14);color:var(--accent);border:1px solid var(--accent)}
.b-lean{background:rgba(251,191,36,.14);color:var(--warn);border:1px solid var(--warn)}
.b-toss{background:rgba(165,180,252,.12);color:var(--muted);border:1px solid var(--muted)}
.b-none,.b-warn{background:rgba(248,113,113,.14);color:var(--bad);border:1px solid var(--bad)}
.chip{display:inline-block;border-radius:6px;padding:.05rem .4rem;font-size:.7rem;
  font-weight:600;margin:.1rem .15rem .1rem 0;border:1px solid var(--border);
  background:var(--panel-alt);color:var(--muted)}
.chip-flag{background:rgba(251,191,36,.10);color:var(--warn);border-color:#5a4a1e}
.chip-market{background:rgba(56,189,248,.10);color:var(--accent);border-color:#1e3a5f}
.chip-model{background:rgba(167,139,250,.12);color:#c4b5fd;border-color:#3b2f66}
.chip-marketpmodel{background:rgba(52,211,153,.10);color:var(--good);border-color:#1e4d3a}
.chip-blank{background:rgba(248,113,113,.10);color:var(--bad);border-color:#5f2b2b}
.chip-none{color:var(--muted)}
.pbar{display:flex;height:10px;border-radius:6px;overflow:hidden;background:var(--panel-alt);
  margin:.5rem 0}
.pbar-a{background:var(--accent)}
.pbar-b{background:#334155}
.table-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.86rem;margin:.5rem 0}
th,td{border:1px solid var(--border);padding:.45rem .55rem;text-align:left;
  vertical-align:top}
th{background:var(--panel-alt);color:var(--muted);font-weight:700}
tbody tr:nth-child(even){background:rgba(255,255,255,.015)}
.big-line{font-size:1.15rem}
.semi{border-top:1px solid var(--border);padding:.8rem 0}
.semi-detail{color:var(--muted);font-size:.9rem}
input[type="text"],input:not([type]){background:var(--panel-alt);border:1px solid var(--border);
  border-radius:8px;color:var(--text);padding:.4rem .6rem;font-size:.9rem;margin:.2rem .3rem .2rem 0}
input:focus{outline:2px solid var(--accent);outline-offset:1px}
.site-footer{border-top:1px solid var(--border);margin-top:2rem;padding:1.2rem 1rem;
  color:var(--muted);font-size:.8rem;text-align:center}
@media(max-width:720px){
  table.board thead{display:none}
  table.board,table.board tbody,table.board tr,table.board td{display:block;width:100%}
  table.board tr{border:1px solid var(--border);border-radius:12px;margin:.6rem 0;
    padding:.4rem;background:var(--panel)}
  table.board td{border:none;border-top:1px solid var(--border);padding:.5rem .6rem}
  table.board td:first-child{border-top:none}
  table.board td::before{content:attr(data-label);display:block;font-size:.68rem;
    font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:.15rem}
}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    write("index.html", render_index())
    write("twc-day4.html", render_twc())
    write("unresolved.html", render_unresolved())
    write("flagged.html", render_flagged())
    write("method.html", render_method())
    (OUT / "style.css").write_text(STYLE_CSS, encoding="utf-8")
    print("wrote audits/c32f1b93/style.css")


if __name__ == "__main__":
    main()
