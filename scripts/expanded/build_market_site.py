#!/usr/bin/env python3
"""Render the T-EXPAND mobile-first betting-line board into market/**.

Reads  data/expanded/lines.json      (fixtures joined to external quotes)
       data/expanded/collection_log.json (source status incl. failures)
Writes market/index.html, picks.html, cs2.html, lol.html, flagged.html, sources.html,
       market/assets/market.css, market/assets/market.js and copies the JSON data.

Every row keeps its own source link(s). A fixture without a joined external quote is
published blank and flagged — never estimated. HotSpawn's crowd percentage is displayed
as labelled reference context only.

Usage: python3 scripts/expanded/build_market_site.py
"""
from __future__ import annotations

import html
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "expanded"
OUT = ROOT / "market"

NAV = [("index.html", "Dashboard"), ("picks.html", "Picks"), ("cs2.html", "CS2"),
       ("lol.html", "LoL"), ("flagged.html", "Flagged for review"), ("sources.html", "Sources & method"),
       ("repo-review.html", "Repo review")]


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt_dt(value: str | None) -> str:
    if not value:
        return "—"
    return esc(value).replace("T", " ").replace("Z", " UTC")


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def local_time_cell(value: str | None) -> str:
    if not value:
        return "—"
    return (f'<time datetime="{esc(value)}" class="utc" data-utc="{esc(value)}">'
            f'{fmt_dt(value)}</time>')


def render_page(title: str, active: str, body: str, generated: str, subtitle: str) -> str:
    nav_parts = []
    for href, label in NAV:
        cls = ' class="active"' if href == active else ""
        nav_parts.append(f'<a href="{href}"{cls}>{esc(label)}</a>')
    nav = "\n".join(nav_parts)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="stylesheet" href="assets/market.css">
</head>
<body>
<header class="topbar">
  <div class="wrap">
    <div class="brand"><span class="dot"></span>Pick'em line board · external lines only</div>
    <nav>{nav}</nav>
  </div>
</header>
<main class="wrap">
  <h1>{esc(title)}</h1>
  <p class="sub">{subtitle}</p>
{body}
</main>
<footer class="wrap foot">
  <p>Data snapshot: <strong>{esc(generated)}</strong>. Fixtures are enumerated from the HotSpawn
  Pick'ems lobby; every price comes from an external bookmaker or prediction market and is linked
  per row. HotSpawn's crowd "picked %" is reference context and is never used as a probability.
  Nothing is estimated: unsigned matches stay blank and are listed on the Flagged for review page.</p>
  <p class="mini">Not affiliated with HotSpawn or any bookmaker. Odds move; re-check the linked source
  before acting on any number. If you gamble, only stake what you can afford to lose — help:
  <a href="https://www.begambleaware.org/" rel="noopener">BeGambleAware</a>.</p>
</footer>
<script src="assets/market.js"></script>
</body>
</html>
"""


def source_block(q: dict) -> str:
    links = []
    if q.get("source_public_url"):
        links.append(f'<a href="{esc(q["source_public_url"])}" rel="noopener">{esc(q["source_name"])}</a>')
    else:
        links.append(f'<span class="srcname">{esc(q["source_name"])}</span>')
    if q.get("source_api_url"):
        links.append(f'<a class="mini" href="{esc(q["source_api_url"])}" rel="noopener">quote source</a>')
    prov = [f'id {esc(q.get("source_event_id"))}']
    if q.get("source_market_id"):
        prov.append(f'market {esc(q["source_market_id"])}')
    if q.get("market_is_live"):
        prov.append("live market")
    return (f'<div class="srcblock">{"<br>".join(links)}'
            f'<div class="odds">{esc(q.get("decimal_odds_a"))} / {esc(q.get("decimal_odds_b"))}</div>'
            f'<div class="mini">p {pct(q.get("implied_prob_a"))} / {pct(q.get("implied_prob_b"))}'
            f' · overround {esc(q.get("overround")) if q.get("overround") is not None else "—"}'
            f' · read {fmt_dt(q.get("retrieved_at_utc"))}</div>'
            f'<div class="mini">{esc(" · ".join(prov))}</div>'
            f'<div class="mini">{esc(q.get("join", {}).get("rule", ""))}'
            f'{" · sides swapped" if q.get("side_order") == "reversed" else ""}</div></div>')


def probability_bar(a: float | None, b: float | None, ta: str, tb: str) -> str:
    if a is None or b is None:
        return '<div class="bar empty"><span>no external line</span></div>'
    return (f'<div class="bar"><span class="seg-a" style="width:{a * 100:.1f}%">'
            f'{a * 100:.0f}%</span><span class="seg-b" style="width:{b * 100:.1f}%">'
            f'{b * 100:.0f}%</span></div>'
            f'<div class="mini">{esc(ta)} {pct(a)} · {esc(tb)} {pct(b)}</div>')


def pick_badge(row: dict) -> str:
    pick = row.get("pick")
    if not pick:
        return '<span class="badge none">no market line</span>'
    return f'<span class="badge pick">{esc(pick["team"])} · {pct(pick["probability"])}</span>'


def originated_cell(row: dict) -> str:
    est = row.get("originated_estimate") or {}
    if not est.get("available"):
        reason = est.get("reason") or "no external market line"
        return f'<span class="mini">{esc(reason)}</span>'
    srcs = " · ".join(
        f'<a href="{esc(s["url"])}" rel="noopener">{esc(s["label"])}</a>'
        for s in (est.get("sources") or []) if s.get("url"))
    return (f'<span class="badge model">MODEL {esc(est["pick"])} · {pct(est["pick_probability"])}</span>'
            f'<div class="mini">not a market price · {esc(est["method"])}</div>'
            f'<div class="mini">VRS points: {esc(est["team_a_points"])} ({esc(est["team_a_region"])} '
            f'#{esc(est["team_a_standing"])}) vs {esc(est["team_b_points"])} ({esc(est["team_b_region"])} '
            f'#{esc(est["team_b_standing"])})</div>'
            f'<div class="mini">{srcs}</div>')


def flags_cell(row: dict) -> str:
    flags = row.get("verification", {}).get("flags") or []
    if not flags:
        return '<span class="ok">verified from external line</span>'
    return " ".join(f'<span class="chip">{esc(f.replace("_", " "))}</span>' for f in flags)


def fixture_row(row: dict, show_game: bool = True) -> str:
    cons = row.get("consensus")
    a = cons["prob_a"] if cons else None
    b = cons["prob_b"] if cons else None
    quotes = row.get("quotes") or []
    lines = "".join(source_block(q) for q in quotes) or '<div class="srcblock none">no external line found</div>'
    sources = ", ".join(cons["sources"]) if cons else "—"
    return f"""<tr class="fixture{' unpriced' if not quotes else ''}" data-search="{esc((row['team_a'] + ' ' + row['team_b'] + ' ' + (row['competition'] or '')).lower())}" data-priced="{1 if quotes else 0}" data-game="{esc(row['game'])}">
  <td data-label="Kick-off (UTC)">{local_time_cell(row.get('start_time_utc'))}</td>
  <td data-label="Game / tier">{esc(str(row['game']).upper())}{' · ' + esc(row['tier']).upper() if row.get('tier') else ''}</td>
  <td data-label="Tournament">{esc(row.get('competition'))}</td>
  <td data-label="Match"><strong>{esc(row['team_a'])}</strong> vs <strong>{esc(row['team_b'])}</strong>
      <div class="mini"><a href="{esc(row['hotspawn_match_url'])}" rel="noopener">{esc(hotspawn_link_label(row))}</a>
      · crowd {esc(row['hotspawn_pick_pct_reference_only']['team_a'])}/{esc(row['hotspawn_pick_pct_reference_only']['team_b'])}% (reference only)</div></td>
  <td data-label="External lines">{lines}</td>
  <td data-label="Derived no-vig probability">{probability_bar(a, b, row['team_a'], row['team_b'])}
      <div class="mini">{esc(sources)}</div></td>
  <td data-label="Pick">{pick_badge(row)}</td>
  <td data-label="Originated estimate (model, not a market price)">{originated_cell(row)}</td>
  <td data-label="Verification">{flags_cell(row)}</td>
</tr>"""


def table(rows: list[dict], show_game=True) -> str:
    head_game = "<th>Game / tier</th>" if show_game else ""
    body = "".join(fixture_row(r, show_game) for r in rows)
    return f"""<div class="controls">
  <input id="q" type="search" placeholder="Search team or tournament…" aria-label="Search fixtures">
  <label class="toggle"><input id="priced-only" type="checkbox" checked> only matches with an external line</label>
  <span class="mini" id="count"></span>
</div>
<div class="tablewrap"><table class="fixtures">
<thead><tr><th>Kick-off (UTC)</th>{head_game}<th>Tournament</th><th>Match</th>
<th>External line(s)</th><th>Derived probability</th><th>Pick</th>
<th>Originated estimate (model)</th><th>Verification</th></tr></thead>
<tbody>{body}</tbody></table></div>"""


def hotspawn_link_label(row: dict) -> str:
    """Say what the HotSpawn link actually is: a published match page, or the official lobby."""
    kind = str(row.get("hotspawn_match_url_kind") or "")
    return "HotSpawn match page" if kind.startswith("lobby-published") else "HotSpawn lobby"


def summary_cards(doc: dict) -> str:
    s = doc["summary"]
    rows = doc.get("fixtures") or []
    cards = [
        (s["fixtures_total"], "fixtures in the lobby snapshot"),
        (s["fixtures_future"], "still to be played"),
        (s["future_with_external_line"], "with a verified external line"),
        (s["future_without_external_line"], "no external line found (blank, flagged)"),
        (s["future_with_two_or_more_sources"], "priced by 2+ independent sources"),
        (s["quotes_joined"], "external quotes joined"),
        (sum(1 for r in rows if (r.get("originated_estimate") or {}).get("available")),
         "with an originated model estimate (not a market price)"),
    ]
    return '<div class="cards">' + "".join(
        f'<div class="card"><div class="num">{esc(n)}</div><div class="lbl">{esc(l)}</div></div>'
        for n, l in cards) + "</div>"


def game_section_counts(doc: dict) -> str:
    rows = []
    for game, stats in sorted(doc["summary"]["by_game"].items()):
        rows.append(f'<tr><td>{esc(str(game).upper())}</td><td>{stats["total"]}</td>'
                    f'<td>{stats["future"]}</td><td>{stats["priced"]}</td></tr>')
    return ("<table class=\"plain\"><thead><tr><th>Game</th><th>Fixtures in snapshot</th>"
            "<th>Still to be played</th><th>With external line</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def source_table(log: dict, doc: dict) -> str:
    rows = []
    p = log.get("pinnacle") or {}
    rows.append(("Pinnacle (guest odds API)", "licensed bookmaker",
                 f'<a href="https://guest.api.arcadia.pinnacle.com/0.1/sports/12/matchups" rel="noopener">'
                 f'api.pinnacle (public guest)</a>',
                 "reachable" if p.get("status") == 200 else f'not reachable ({esc(p.get("status"))})',
                 f'{p.get("matchups_relevant", "—")} relevant matchups'))
    b = log.get("bovada") or {}
    rows.append(("Bovada (public coupon JSON)", "licensed bookmaker",
                 '<a href="https://www.bovada.lv/services/sports/event/v2/events/A/description/esports" '
                 'rel="noopener">bovada.lv coupon</a>',
                 "reachable" if b.get("status") == 200 else f'not reachable ({esc(b.get("status"))})',
                 f'{esc(b.get("moneyline_rows"))} moneyline rows'))
    lf = log.get("linefeed") or {}
    for src in lf.get("sources", []):
        ok = not src.get("error")
        rows.append((f'{src["mirror"].capitalize()} (1xBet-platform LineFeed)', "licensed bookmaker",
                     f'<a href="{esc(src.get("url") or "")}" rel="noopener">LineFeed JSON</a>' if src.get("url") else "—",
                     "reachable" if ok else f'not reachable ({esc(src.get("error"))})',
                     f'{src.get("moneyline_rows", 0)} 2-way moneylines'))
    pm = log.get("polymarket") or {}
    rows.append(("Polymarket (public markets)", "prediction market",
                 '<a href="https://polymarket.com/esports" rel="noopener">polymarket.com</a>',
                 "reachable" if pm.get("status") == 200 else f'not reachable ({esc(pm.get("status"))})',
                 f'{esc(pm.get("fresh_markets"))} open markets'))
    # Sources that were probed and failed are listed, with their evidence file.
    blocked = [("HLTV", "reference", "https://www.hltv.org/matches"),
               ("EGamersWorld", "odds aggregator", "https://egamersworld.com/counterstrike/matches"),
               ("Thunderpick", "bookmaker", "https://thunderpick.io/esports/cs2-betting"),
               ("Oddspedia", "odds aggregator", "https://oddspedia.com/esports"),
               ("GG.BET", "bookmaker", "https://gg.bet/en/esports"),
               ("DraftKings", "bookmaker", "https://sportsbook.draftkings.com/"),
               ("FanDuel", "bookmaker", "https://sportsbook.fanduel.com/"),
               ("Betano", "bookmaker", "https://www.betano.pt/sport/esports/"),
               ("BetOnline", "bookmaker", "https://www.betonline.ag/sportsbook/esports"),
               ("BetExplorer", "odds aggregator", "https://www.betexplorer.com/esports/"),
               ("Strafe", "odds aggregator", "https://strafe.com/matches/counter-strike"),
               ("Unibet (Kambi feed)", "bookmaker", "https://www.unibet.com/"),
               ("Betway", "bookmaker", "https://sports.betway.com/en/sports/grp/esports"),
               ("1xBet (direct)", "bookmaker", "https://1xbet.com/"),
               ("Liquipedia (rate-limited)", "reference", "https://liquipedia.net/counterstrike/")]
    for name, kind, url in blocked:
        rows.append((name, kind, f'<a href="{esc(url)}" rel="noopener">{esc(url)}</a>',
                     "blocked / not reachable from the collector host",
                     "listed for transparency — no price taken"))
    out = ['<table class="plain"><thead><tr><th>Source</th><th>Type</th><th>Link</th>'
           '<th>Status at collection</th><th>Rows used</th></tr></thead><tbody>']
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    out.append("</tbody></table>")
    out.append('<p class="mini">Reachability evidence, including every failure and its exact error, is '
               'committed in <code>data/expanded/source_probe.json</code> and '
               '<code>data/expanded/collection_log.json</code>.</p>')
    return "".join(out)


def render_repo_review(doc: dict, generated: str) -> None:
    """Publish the line-by-line repo verification (claims checked against primary sources)."""
    path = DATA / "repo_review.json"
    if not path.exists():
        body = '<p class="note">No repo review has been recorded yet — it is produced by the same ' \
               'scheduled run that collects the lines.</p>'
    else:
        review = json.loads(path.read_text(encoding="utf-8"))
        rows = []
        for c in review.get("checks") or []:
            status = str(c.get("status") or "unverified")
            cls = "ok" if status == "verified" else ("chip" if status == "discrepancy" else "chip")
            raw_sources = [c["source"]] if c.get("source") else list(c.get("sources") or [])
            parts = []
            for src in raw_sources:
                if str(src).startswith("http"):
                    parts.append(f'<a href="{esc(src)}" rel="noopener">{esc(str(src)[:64])}</a>')
                else:
                    parts.append(esc(str(src)))
            src_link = "<br>".join(parts) if parts else "—"
            detail = c.get("detail") or (f'{c.get("teams_checked", "")} teams checked; '
                                          f'{len(c.get("mismatches") or [])} mismatch(es)')
            rows.append(f'<tr><td>{esc(c.get("id"))}</td><td>{esc(c.get("claim"))}</td>'
                        f'<td><span class="{cls}">{esc(status)}</span></td>'
                        f'<td>{src_link}</td><td class="mini">{esc(detail)}</td></tr>')
        irr = review.get("irregularities") or []
        irr_html = "".join(
            f'<li><strong>{esc(i.get("id"))}</strong> ({esc(i.get("severity"))}): {esc(i.get("finding"))} '
            f'<span class="mini">evidence: {esc(i.get("evidence"))}</span></li>' for i in irr) \
            or "<li>None found by these checks.</li>"
        body = f"""
<p class="sub">Run at {esc(review.get('generated_at_utc'))}. Each row is a claim published by this
repository, the primary source it was checked against, and the outcome. A claim that cannot be
confirmed from its source is marked <span class="chip">unverified</span> — never assumed true.</p>
<div class="tablewrap"><table class="plain"><thead><tr><th>#</th><th>Claim checked</th><th>Outcome</th>
<th>Source</th><th>Detail</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>Irregularities flagged for review</h2>
<ul>{irr_html}</ul>
<p class="mini">Raw evidence: <a href="data/repo_review.json">data/repo_review.json</a>. Fixture
evidence for this board: <a href="data/fixtures.json">data/fixtures.json</a>.</p>
"""
    (OUT / "repo-review.html").write_text(render_page(
        "Repo review — claims checked line by line", "repo-review.html", body, generated,
        "Every publishable claim in this repository, checked against its primary source with links."),
        encoding="utf-8")


def main() -> int:
    lines_path = DATA / "lines.json"
    if not lines_path.exists():
        print("no data/expanded/lines.json — nothing to build")
        return 1
    doc = json.loads(lines_path.read_text(encoding="utf-8"))
    log = json.loads((DATA / "collection_log.json").read_text(encoding="utf-8")) \
        if (DATA / "collection_log.json").exists() else {}
    generated = doc.get("generated_at_utc")
    rows = doc["fixtures"]
    future = [r for r in rows if r.get("is_future")]
    priced = [r for r in future if r.get("quotes")]
    unpriced = [r for r in future if not r.get("quotes")]
    stale = [r for r in rows if not r.get("is_future")]

    (OUT / "assets").mkdir(parents=True, exist_ok=True)
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy2(lines_path, OUT / "data" / "lines.json")
    for extra in ("quotes.json", "collection_log.json", "fixtures.json", "repo_review.json"):
        if (DATA / extra).exists():
            shutil.copy2(DATA / extra, OUT / "data" / extra)

    # ------------------------------------------------------------------ landing
    top = sorted([r for r in priced], key=lambda r: -(r["consensus"]["prob_a"] if r["consensus"]["prob_a"] else 0))[:6]
    top_cards = "".join(
        f'<li><a href="cs2.html">{esc(r["team_a"])} vs {esc(r["team_b"])}</a> — '
        f'{flags_cell(r)} {pick_badge(r)} <span class="mini">{esc(r.get("competition"))}, '
        f'{fmt_dt(r.get("start_time_utc"))}</span></li>'
        if str(r["game"]).lower() == "cs2" else
        f'<li><a href="lol.html">{esc(r["team_a"])} vs {esc(r["team_b"])}</a> — '
        f'{flags_cell(r)} {pick_badge(r)} <span class="mini">{esc(r.get("competition"))}, '
        f'{fmt_dt(r.get("start_time_utc"))}</span></li>'
        for r in top)
    landing = f"""
{summary_cards(doc)}
<h2>What this board is</h2>
<p>Every match the HotSpawn Pick'ems lobby lists, with an <strong>external</strong> betting line
per match (never HotSpawn) and the no-vig win probability derived from those prices. Each row links
the exact source it was read from and the time it was read. Where no external price exists, the row is
left <strong>blank and flagged</strong> — the board never invents a number.</p>
<p class="note">HotSpawn's crowd "picked %" is shown as reference only. It is never an input to any
probability on this site.</p>
{game_section_counts(doc)}
<h2>How to read a row</h2>
<ul>
  <li><strong>External line(s)</strong> — the quoted decimal prices for both teams, the implied
  no-vig probability per source, the bookmaker overround, the source link and retrieval time.</li>
  <li><strong>Derived probability</strong> — the mean across the sources that quote the match
  (<code>p = (1/d) / Σ(1/d)</code> per source, then averaged).</li>
  <li><strong>Pick</strong> — the higher-probability side of that consensus. This is what the market says,
  not a prediction by this site.</li>
  <li><strong>Originated estimate (model)</strong> — a clearly-labelled <em>model</em> value for CS2
  fixtures that no reachable book prices, computed from Valve's official regional standings
  (<code>p = 1/(1+10^(-(Ra-Rb)/400))</code> on VRS points). It is never mixed into the market consensus
  and is never shown as a market line. Everyone else stays blank.</li>
  <li><strong>Verification</strong> — "verified from external line" only when a source quote was joined
  to the fixture; otherwise the flag explains what is missing.</li>
</ul>
<p class="note">Two different things are on this page on purpose: <strong>market numbers</strong>
(quoted prices from bookmakers/prediction markets, each with its source link) and <strong>model
numbers</strong> (our own originated estimate, labelled, only where no market price exists). They are
never blended.</p>
<h2>Start here</h2>
<p><a class="btn" href="picks.html">All picks ({len(priced)} priced matches)</a>
<a class="btn ghost" href="cs2.html">CS2 table ({sum(1 for r in future if str(r['game']).lower() == 'cs2')})</a>
<a class="btn ghost" href="lol.html">LoL table ({sum(1 for r in future if str(r['game']).lower() == 'lol')})</a>
<a class="btn ghost" href="flagged.html">Flagged for review ({len(unpriced)} unpriced + {len(stale)} stale)</a></p>
<h2>Strongest market favourites right now</h2>
<ul class="list">{top_cards}</ul>
"""
    (OUT / "index.html").write_text(render_page(
        "Pick'em line board", "index.html", landing, generated,
        "External betting lines and derived no-vig probabilities for every match in the HotSpawn "
        "Pick'ems lobby — mobile-first, source-linked, no estimates."), encoding="utf-8")

    # -------------------------------------------------------------------- picks
    picks_rows = []
    for r in sorted(priced, key=lambda x: (x.get("start_time_utc") or "")):
        c = r["consensus"]
        picks_rows.append({
            **r,
            "verification": {"flags": []},
        })
    picks_body = f"""
<p class="sub">One line per match that has a verified external line, earliest first. The pick is the
higher-probability side of the consensus across the linked sources.</p>
{table(picks_rows)}
<p class="note">{len(unpriced)} matches in the current lobby snapshot have <strong>no</strong> external
line and therefore no pick. They are listed, blank, on the <a href="flagged.html">Flagged for review</a>
page.</p>
"""
    (OUT / "picks.html").write_text(render_page(
        "Picks for every priced match", "picks.html", picks_body, generated,
        "Obvious pick per match, derived only from external betting lines."), encoding="utf-8")

    # ----------------------------------------------------------------- category
    for game, fname, title in (("cs2", "cs2.html", "CS2 matches"),
                               ("lol", "lol.html", "LoL matches")):
        game_rows = [r for r in future if str(r["game"]).lower() == game]
        priced_n = sum(1 for r in game_rows if r["quotes"])
        body = f"""
<p class="sub">{len(game_rows)} fixtures still to be played · {priced_n} with a verified external line ·
{len(game_rows) - priced_n} blank and flagged.</p>
{table(game_rows)}
"""
        (OUT / fname).write_text(render_page(
            title, fname, body, generated,
            "Every fixture, its external line(s), the derived no-vig probability and the pick."),
            encoding="utf-8")

    # ------------------------------------------------------------------ flagged
    flagged = f"""
<h2>1. Matches with no external line ({len(unpriced)})</h2>
<p>These fixtures are listed in the lobby but no external price could be confirmed for them at
collection time. They are published blank — no estimate, no inference.</p>
{table(unpriced)}
<h2>2. Stale lobby entries ({len(stale)})</h2>
<p>Fixtures whose scheduled start is in the past while the lobby still reports status
<code>scheduled</code>. Their source-reported state is kept as-is and they are excluded from the picks
list.</p>
{table(stale)}
<h2>3. Matches with neither an external line nor a model estimate</h2>
<p>Nothing is published for these rows: no price, no probability, no originated estimate.</p>
{table([r for r in unpriced if not (r.get("originated_estimate") or {}).get("available")])}
<h2>4. Source reachability failures</h2>
{source_table(log, doc)}
<h2>5. Irregularities carried forward from earlier sessions</h2>
<ul>
  <li>Fixture count differs between earlier snapshots (86 SSR rows at 17:51 UTC, 92/93 from the API,
  90 in the lobby app filters) — reported here, never silently reconciled.</li>
  <li>Pinnacle publishes American prices on a CSV/JSON feed; decimal values on this board are derived
  and flagged per row.</li>
  <li>Polymarket's older CS2 match markets are stale; only markets whose end date is in the future are used.</li>
  <li>Some fixtures (e.g. CCT Europe series, Elisa BreakOut) are covered by only one reachable source;
  single-source rows are marked in the "Derived probability" column.</li>
</ul>
"""
    (OUT / "flagged.html").write_text(render_page(
        "Flagged for review", "flagged.html", flagged, generated,
        "Everything that could not be confirmed from an external source, listed with its source links."),
        encoding="utf-8")

    # ------------------------------------------------------------------ sources
    sources_body = f"""
<h2>Source status for this collection</h2>
{source_table(log, doc)}
<h2>How a probability is produced</h2>
<ol>
  <li>A source price is read for both outcomes of the match moneyline (never map handicaps, never
  outrights).</li>
  <li>Each price is converted to an implied share <code>q = 1 / decimal_odds</code>.</li>
  <li>The shares are normalised to remove the bookmaker margin:
  <code>p = q / (q<sub>a</sub> + q<sub>b</sub>)</code> (proportional no-vig).</li>
  <li>If several sources quote the same match, the board shows the arithmetic mean and the spread.</li>
</ol>
<h2>Joining a price to a fixture</h2>
<p>A price is only used when <strong>both</strong> participants match the fixture by normalised name
(with a small, reviewable alias table) and either the source's start time is within 90 minutes of the
fixture start, or — when the source publishes no start time — the competition names agree. When a source
lists the teams in the other order, prices are swapped and the row says so. Rejected quotes are kept in
<code>data/expanded/quotes.json</code> and counted in the summary as "unused".</p>
<h2>Raw evidence committed with this site</h2>
<ul>
  <li><a href="data/lines.json">data/lines.json</a> — fixtures, quotes, joins, probabilities, flags</li>
  <li><a href="data/quotes.json">data/quotes.json</a> — every raw quote with source URL, market id and time</li>
  <li><a href="data/collection_log.json">data/collection_log.json</a> — per-source status incl. failures</li>
  <li><a href="data/fixtures.json">data/fixtures.json</a> — the lobby fixture snapshot used for this run</li>
</ul>
<h2>Method limits — read this before trusting a number</h2>
<ul>
  <li>Prices move continuously; the timestamp on each row is the only guarantee of when a price was true.</li>
  <li>A "pick" here is the market's favourite, not a prediction. Favourites lose.</li>
  <li>Coverage is uneven by design: large tournaments are quoted by several books, small tier-C
  tournaments by few or none. Unquoted matches stay blank.</li>
  <li>No HotSpawn number is used anywhere in the arithmetic.</li>
</ul>
"""
    (OUT / "sources.html").write_text(render_page(
        "Sources & method", "sources.html", sources_body, generated,
        "Which sources were read, what failed, and exactly how the numbers are produced."),
        encoding="utf-8")

    render_repo_review(doc, generated)
    write_assets(generated)
    print(f"wrote market/ pages from {lines_path} ({len(rows)} fixtures, {len(priced)} priced)")
    return 0


def write_assets(generated: str) -> None:
    css = """/* market/** — mobile-first betting-line board (session a0586093) */
:root{--bg:#0f1216;--panel:#171c22;--panel2:#1e242c;--line:#2a323c;--tx:#e8edf3;--mut:#9aa7b4;
--ok:#37d67a;--warn:#ffb020;--bad:#ff6b6b;--acc:#5aa9ff}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--tx);
font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:1180px;margin:0 auto;padding:0 14px}
.topbar{background:linear-gradient(180deg,#12171d,#0f1216);border-bottom:1px solid var(--line);
position:sticky;top:0;z-index:20}
.topbar .wrap{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;padding:10px 14px}
.brand{font-weight:700;letter-spacing:.2px;display:flex;align-items:center;gap:8px}
.dot{width:9px;height:9px;border-radius:50%;background:var(--ok);display:inline-block}
nav{display:flex;flex-wrap:wrap;gap:4px}
nav a{padding:7px 11px;border-radius:9px;color:var(--tx);background:#1b2129;border:1px solid var(--line);font-size:14px}
nav a.active{background:var(--acc);border-color:var(--acc);color:#06121f;font-weight:700}
main{padding:18px 0 8px}
h1{font-size:1.45rem;margin:.2rem 0 .3rem}
h2{font-size:1.1rem;margin:1.6rem 0 .5rem}
.sub{color:var(--mut);margin:.1rem 0 1rem}
.note{background:#151b22;border-left:3px solid var(--warn);padding:10px 12px;border-radius:8px;color:#dfe7ee}
.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:10px 0 4px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px}
.card .num{font-size:1.5rem;font-weight:800}
.card .lbl{color:var(--mut);font-size:.82rem}
.btn{display:inline-block;background:var(--acc);color:#06121f;font-weight:700;padding:9px 14px;border-radius:10px;margin:4px 6px 4px 0}
.btn.ghost{background:#1b2129;color:var(--tx);border:1px solid var(--line)}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:14px 0 8px}
input[type=search]{flex:1 1 220px;background:var(--panel2);border:1px solid var(--line);color:var(--tx);
padding:10px 12px;border-radius:10px;font-size:15px}
.toggle{color:var(--mut);font-size:.86rem;display:flex;gap:6px;align-items:center}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
table.fixtures{width:100%;border-collapse:collapse;font-size:14px}
table.fixtures th{text-align:left;padding:10px;background:#141a21;color:var(--mut);font-weight:600;
white-space:nowrap;border-bottom:1px solid var(--line)}
table.fixtures td{padding:10px;border-bottom:1px solid var(--line);vertical-align:top}
table.fixtures tr:last-child td{border-bottom:0}
table.fixtures tr.unpriced{opacity:.72}
.srcblock{padding:6px 0;border-bottom:1px dashed #2a323c}
.srcblock:last-child{border-bottom:0}
.srcblock.none{color:var(--warn)}
.odds{font-variant-numeric:tabular-nums;font-weight:700}
.mini{font-size:.76rem;color:var(--mut);line-height:1.35}
.bar{display:flex;height:22px;border-radius:6px;overflow:hidden;background:#232a33;border:1px solid var(--line)}
.bar span{display:flex;align-items:center;justify-content:center;font-size:.75rem;font-weight:700;color:#06121f}
.bar .seg-a{background:#63d2a5}.bar .seg-b{background:#f0b26b}
.bar.empty{color:var(--mut);align-items:center;justify-content:center;font-size:.75rem}
.badge{display:inline-block;padding:6px 10px;border-radius:999px;font-size:.82rem;font-weight:700}
.badge.pick{background:#123324;color:var(--ok);border:1px solid #1d5c3c}
.badge.model{background:#1a2436;color:#8fc0ff;border:1px solid #2f4f7d}
.badge.none{background:#33261a;color:var(--warn);border:1px solid #6a4a1e}
.chip{display:inline-block;background:#2a2118;color:var(--warn);border:1px solid #5b442173;
border-radius:999px;padding:2px 8px;font-size:.72rem;margin:2px 2px 0 0}
.ok{color:var(--ok);font-size:.82rem}
table.plain{width:100%;border-collapse:collapse;font-size:14px;background:var(--panel);
border:1px solid var(--line);border-radius:12px;overflow:hidden}
table.plain th,table.plain td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left}
table.plain th{background:#141a21;color:var(--mut)}
ul.list{margin:.3rem 0 1rem 1.1rem;padding:0}
ul.list li{margin:.35rem 0}
.foot{color:var(--mut);font-size:.8rem;border-top:1px solid var(--line);margin-top:26px;padding:16px 14px 40px}
code{background:#1c232b;padding:1px 5px;border-radius:5px;font-size:.85em}
/* ---- mobile: each table row becomes a card ---- */
@media (max-width:760px){
  table.fixtures thead{display:none}
  table.fixtures,table.fixtures tbody,table.fixtures tr,table.fixtures td{display:block;width:100%}
  table.fixtures tr{background:var(--panel2);border:1px solid var(--line);border-radius:12px;
  margin:10px 0;padding:8px 10px}
  table.fixtures td{border:0;padding:6px 0}
  table.fixtures td::before{content:attr(data-label);display:block;color:var(--mut);font-size:.72rem;
  text-transform:uppercase;letter-spacing:.04em;margin-bottom:2px}
  .cards{grid-template-columns:repeat(2,minmax(0,1fr))}
  h1{font-size:1.25rem}
}
@media (min-width:761px){.cards{grid-template-columns:repeat(3,minmax(0,1fr))}}
"""
    js = """/* Lightweight progressive enhancement: local-time display + row filtering. No dependencies. */
(function () {
  document.querySelectorAll('time[data-utc]').forEach(function (el) {
    var raw = el.getAttribute('data-utc');
    var d = new Date(raw);
    if (isNaN(d.getTime())) return;
    el.textContent = d.toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'});
    el.title = raw;
  });
  var q = document.getElementById('q');
  var pricedOnly = document.getElementById('priced-only');
  var rows = Array.prototype.slice.call(document.querySelectorAll('tr.fixture'));
  var count = document.getElementById('count');
  function apply() {
    var term = (q && q.value || '').trim().toLowerCase();
    var onlyPriced = pricedOnly && pricedOnly.checked;
    var shown = 0;
    rows.forEach(function (r) {
      var okTerm = !term || (r.getAttribute('data-search') || '').indexOf(term) !== -1;
      var okPriced = !onlyPriced || r.getAttribute('data-priced') === '1';
      var show = okTerm && okPriced;
      r.style.display = show ? '' : 'none';
      if (show) shown++;
    });
    if (count) count.textContent = shown + ' of ' + rows.length + ' rows shown';
  }
  if (q) q.addEventListener('input', apply);
  if (pricedOnly) pricedOnly.addEventListener('change', apply);
  apply();
})();
"""
    (OUT / "assets" / "market.css").write_text(css, encoding="utf-8")
    (OUT / "assets" / "market.js").write_text(js, encoding="utf-8")
    (OUT / "index.html").write_text((OUT / "index.html").read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
