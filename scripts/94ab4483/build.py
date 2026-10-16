#!/usr/bin/env python3
"""Render the source-linked TWC Day 4 audit from its frozen evidence ledger."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "94ab4483" / "review.json"
OUT = ROOT / "audits" / "94ab4483"

CSS = r"""
:root{color-scheme:dark;--bg:#0b1220;--panel:#121d30;--panel2:#17243a;--ink:#f3f6fb;--muted:#b9c5d7;--line:#32435c;--gold:#f3c96a;--blue:#9dd6ff;--red:#ffb4a8;--green:#a6e3bb;--focus:#fff08a;font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);line-height:1.6;font-size:1rem}a{color:var(--blue);text-decoration-thickness:.08em;text-underline-offset:.18em;overflow-wrap:anywhere}a:hover{color:#d8efff}a:focus-visible,button:focus-visible{outline:3px solid var(--focus);outline-offset:3px}.skip-link{position:absolute;left:-10000px;top:0;padding:.7rem 1rem;background:#fff;color:#000;z-index:5}.skip-link:focus{left:1rem;top:1rem}.site-header{border-bottom:1px solid var(--line);background:#0e1829}.wrap{width:min(1120px,calc(100% - 2rem));margin-inline:auto}.brand{padding:1rem 0 .35rem;font-weight:800;letter-spacing:.1em;color:var(--gold);font-size:.85rem}.brand span{color:var(--muted);font-weight:500;letter-spacing:0;margin-left:.5rem}.main-nav{display:flex;flex-wrap:wrap;gap:.5rem 1rem;padding:.65rem 0 1rem}.main-nav a{font-size:.93rem}.main-nav a[aria-current=page]{color:var(--gold);font-weight:750}.main{padding:2rem 0 3.5rem}.eyebrow{text-transform:uppercase;letter-spacing:.12em;color:var(--gold);font-size:.78rem;font-weight:800}.hero{padding:1rem 0 1.3rem;max-width:850px}.hero h1{font-size:clamp(2rem,5vw,3.4rem);line-height:1.08;letter-spacing:-.035em;margin:.45rem 0 1rem}.hero p{color:var(--muted);font-size:1.1rem;max-width:76ch}.actions{display:flex;flex-wrap:wrap;gap:.7rem;margin:1rem 0 1.6rem}.button{display:inline-flex;align-items:center;justify-content:center;padding:.72rem 1rem;border:1px solid var(--gold);border-radius:.65rem;background:var(--gold);color:#151b26;font-weight:800;text-decoration:none}.button:hover{background:#ffdc83;color:#151b26}.button.secondary{background:transparent;color:var(--ink);border-color:var(--line)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr));gap:1rem}.card,.panel{background:var(--panel);border:1px solid var(--line);border-radius:.9rem;padding:1rem 1.1rem}.card h2,.card h3{margin:.2rem 0 .5rem}.big{font-size:clamp(1.7rem,4vw,2.4rem);font-weight:850;line-height:1.15;color:var(--gold)}.muted{color:var(--muted)}.notice{border-left:5px solid var(--gold);background:#241f15;padding:1rem 1.1rem;border-radius:.35rem;margin:1.2rem 0}.warning{border-left-color:var(--red);background:#291a21}.success{border-left-color:var(--green);background:#15261f}.neutral{border-left-color:var(--blue);background:#142235}.badge{display:inline-block;border:1px solid var(--line);border-radius:99px;padding:.12rem .55rem;color:var(--muted);font-size:.82rem;font-weight:700}.badge.warn{color:var(--red);border-color:#7a4947}.badge.good{color:var(--green);border-color:#427153}section{margin:2rem 0}section h2{font-size:1.55rem;line-height:1.25;margin:.2rem 0 .8rem}section h3{margin:1.2rem 0 .45rem}p{max-width:86ch}ul,ol{padding-left:1.35rem}li{margin:.35rem 0}.table-wrap{width:100%;overflow-x:auto;border:1px solid var(--line);border-radius:.75rem;background:var(--panel)}table{width:100%;border-collapse:collapse;text-align:left}caption{text-align:left;padding:.75rem 1rem;color:var(--muted);font-weight:700}th,td{padding:.78rem .8rem;vertical-align:top;border-bottom:1px solid var(--line)}th{background:var(--panel2);font-size:.9rem}tr:last-child td{border-bottom:0}td{color:#e6ebf4}.source-list{margin:0;padding-left:1.1rem}.source-list li{margin:.1rem 0}.num{font-variant-numeric:tabular-nums;white-space:nowrap}.blank{color:var(--red);font-weight:800}.footer{border-top:1px solid var(--line);padding:1.25rem 0 2rem;color:var(--muted);font-size:.9rem}.footer p{margin:.3rem 0}.kicker{font-size:.87rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:750}.split{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:1rem}.call{font-size:1.07rem}.small{font-size:.9rem;color:var(--muted)}.formula{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere;background:#09101d;border:1px solid var(--line);border-radius:.55rem;padding:.7rem}.sr-only{position:absolute!important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:700px){.wrap{width:min(100% - 1.1rem,1120px)}.main{padding-top:1.25rem}.main-nav{gap:.35rem .8rem}.main-nav a{font-size:.88rem}.table-wrap{overflow:visible;border:0;background:transparent}table,thead,tbody,tr,th,td{display:block;width:100%}thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}tbody{display:grid;gap:.75rem}tr{border:1px solid var(--line);border-radius:.75rem;background:var(--panel);overflow:hidden}td{display:grid;grid-template-columns:minmax(6.2rem,34%) minmax(0,1fr);gap:.65rem;padding:.65rem .75rem;border-bottom:1px solid #26374f;overflow-wrap:anywhere}td:last-child{border-bottom:0}td::before{content:attr(data-label);font-weight:800;color:var(--muted);font-size:.84rem}.table-wrap caption{padding:.7rem .2rem}.button{width:100%}.actions{display:grid}.notice{margin:1rem 0}.footer{font-size:.86rem}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
""".strip()


def load_data() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def esc(value: object) -> str:
    return escape(str(value), quote=True)


def source_link(data: dict, key: str, label: str | None = None) -> str:
    item = data["sources"][key]
    text = label or item["label"]
    url = item["url"]
    if not url.startswith("https://"):
        raise ValueError(f"Non-HTTPS source for {key}: {url}")
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(text)}</a>'


def source_refs(data: dict, keys: list[str]) -> str:
    if not keys:
        return '<span class="blank">No source recorded</span>'
    return '<ul class="source-list">' + "".join(
        f"<li>{source_link(data, key)}</li>" for key in keys
    ) + "</ul>"


def footer(data: dict) -> str:
    return f"""
    <footer class="footer wrap">
      <p>Snapshot reviewed 16 October 2026. Quotes and match states can change; this is research, not a live feed or betting advice.</p>
      <p>HotSpawn crowd ownership is never used as match probability. Unverified participant, ownership, point-value, rest and causal-impact fields remain blank.</p>
      <p><a href="../../picks-every-match/index.html">All-match CS2 picks</a> · <a href="../../picks-every-match/unresolved.html">All-match unresolved picks</a> · <a href="../../twc-2026/results.html">Existing TWC results</a> · <a href="../../twc-2026/roster.html">Roster/rest evidence</a> · <a href="../../data/94ab4483/review.json">This audit's evidence JSON</a> · <a href="../../index.html">Project home</a></p>
      <p class="small">No automated bets or account actions. Not affiliated with HotSpawn. 18+; gamble responsibly.</p>
    </footer>
    """


def layout(data: dict, title: str, active: str, body: str) -> str:
    nav_items = [
        ("index.html", "Day 4 preview", "home"),
        ("unresolved.html", "Unresolved", "unresolved"),
        ("flagged.html", "Flagged for Review", "flags"),
        ("method.html", "Method & sources", "method"),
        ("../../picks-every-match/index.html", "All CS2 picks", ""),
        ("../../picks-every-match/unresolved.html", "All-match limits", ""),
    ]
    nav = "".join(
        f'<a href="{href}"' + (' aria-current="page"' if key == active else "") + f'>{esc(label)}</a>'
        for href, label, key in nav_items
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Source-linked, mobile-first TWC 2026 Day 4 match research and unresolved-picks audit.">
  <title>{esc(title)} · TWC 2026 Day 4 audit</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>
  <header class="site-header"><div class="wrap">
    <div class="brand">HOTSPAWN / TWC 2026 <span>Independent source audit · 94ab4483</span></div>
    <nav class="main-nav" aria-label="Audit navigation">{nav}</nav>
  </div></header>
  <main id="main" class="main wrap">{body}</main>
  {footer(data)}
</body>
</html>
"""


def table_open(caption: str, headers: list[str]) -> str:
    return '<div class="table-wrap"><table><caption>' + esc(caption) + '</caption><thead><tr>' + "".join(
        f'<th scope="col">{esc(h)}</th>' for h in headers
    ) + "</tr></thead><tbody>"


def table_close() -> str:
    return "</tbody></table></div>"


def td(label: str, content: str) -> str:
    return f'<td data-label="{esc(label)}">{content}</td>'


def render_day4(data: dict) -> str:
    items = []
    for fixture in data["day4_fixtures"]:
        if fixture["resolved_pairing"]:
            probabilities = fixture["probability"]
            fixture_html = (
                f'<strong>{esc(fixture["resolved_pairing"])}</strong><br>'
                f'<span class="small">HotSpawn #{esc(fixture["fixture_id"])} card still reads “{esc(fixture["official_page_card"])}”</span>'
            )
            prob_html = (
                f'<span class="num">{esc(fixture["resolved_pairing"])}</span><br>'
                f'<strong>{probabilities["FURIA"] * 100:.0f}% FURIA / {probabilities["Aurora"] * 100:.0f}% Aurora</strong><br>'
                '<span class="small">Market-only no-vig; both readings tie.</span>'
            )
            decision = '<strong>NO DIRECTIONAL PICK</strong><br><span class="small">No verified crowd ownership or priced edge. Do not manufacture a contrarian lean.</span>'
            coverage = '<span class="badge warn">Pick’em inclusion unverified</span>'
        else:
            fixture_html = (
                f'<strong>Falcons vs unverified opponent</strong><br>'
                f'<span class="small">HotSpawn #{esc(fixture["fixture_id"])} card reads “{esc(fixture["official_page_card"])}”</span>'
            )
            probs = '<span class="blank">—</span><br><span class="small">No probability until the opponent and market are verified.</span>'
            prob_html = probs
            decision = '<strong class="blank">UNRESOLVED — leave blank</strong><br><span class="small">Do not name the opponent until the BetBoom–Legacy decider is final.</span>'
            coverage = '<span class="badge warn">Placeholder; Pick’em inclusion unverified</span>'
        schedule = fixture["scheduled_utc"].replace("T", " ").replace(":00Z", " UTC")
        row = "<tr>" + td("Fixture", fixture_html + f'<br><span class="small">{esc(fixture["format"])}</span>')
        row += td("Schedule", f'<span class="num">{esc(schedule)}</span><br><span class="small">Pick’em points: <span class="blank">— not published</span></span>')
        row += td("Probability", prob_html)
        row += td("Decision", decision)
        row += td("Coverage", coverage)
        row += td("Sources", source_refs(data, fixture["sources"]))
        row += "</tr>"
        items.append(row)
    return table_open("Day-four semifinal slots: only source-supported values are shown.", ["Fixture", "Schedule", "Probability", "Decision", "Coverage", "Sources"]) + "".join(items) + table_close()


def render_results(data: dict) -> str:
    rows = []
    for item in data["results"]:
        maps = "<br>".join(esc(value) for value in item["map_scores"])
        row = "<tr>" + td("Day", f'<strong>Day {item["day"]}</strong>')
        row += td("Match / series", f'<strong>{esc(item["team_a"])} vs {esc(item["team_b"])}</strong><br><span class="num">{esc(item["series_score"])}</span>')
        row += td("Map scores", maps)
        row += td("Research note", esc(item["takeaway"]))
        row += td("Sources", source_refs(data, item["sources"]))
        row += "</tr>"
        rows.append(row)
    return table_open("Results reviewed from the official HotSpawn event reports and match pages.", ["Day", "Match / series", "Map scores", "Research note", "Sources"]) + "".join(rows) + table_close()


def render_roster(data: dict) -> str:
    rows = []
    for change in data["roster_and_rest"]["aurora_changes"]:
        row = "<tr>" + td("Change", f'<strong>{esc(change["person"])}</strong><br>{esc(change["change"])}')
        row += td("Announcement", f'<span class="num">{esc(change["announcement_date"])}</span><br><span class="small">{esc(change["announcement_utc"])}</span>')
        row += td("Before opener", f'<span class="num">{change["calendar_days_before_opener"]} calendar days</span>')
        row += td("Source", source_link(data, change["source_url_key"])) + "</tr>"
        rows.append(row)
    return table_open("Official Aurora roster changes found in the checked team announcements.", ["Change", "Announcement UTC", "Before opener", "Source"]) + "".join(rows) + table_close()


def render_market(data: dict) -> str:
    rows = []
    for quote in data["market_evidence"]["observations"]:
        row = "<tr>" + td("Source", f'<strong>{esc(quote["operator"])}</strong><br><span class="small">{esc(quote["source_kind"])}</span>')
        row += td("Captured", f'<span class="num">{esc(quote["retrieved_utc"])}</span>')
        row += td("Decimal odds", f'<span class="num">{esc(quote["team_a"])} {quote["decimal_a"]:.2f} / {esc(quote["team_b"])} {quote["decimal_b"]:.2f}</span>')
        row += td("No-vig", f'<span class="num">{quote["no_vig_a"]:.0%} / {quote["no_vig_b"]:.0%}</span><br><span class="small">overround {quote["overround"]:.2%}</span>')
        row += td("Quote source", source_link(data, quote["source_url_key"]))
        row += "</tr>"
        rows.append(row)
    return table_open("FURIA vs Aurora: preserved exact feed capture times; later same-day display checks had no exact response timestamp.", ["Operator / method", "Captured UTC", "Decimal odds", "No-vig estimate", "Source"]) + "".join(rows) + table_close()


def render_index(data: dict) -> str:
    live = data["live_match"]
    boards = data["board_freshness"]
    board_rows = []
    for key, label in (("canonical", "Canonical market-first board"), ("independent", "Separate full-coverage board")):
        board = boards[key]
        if key == "canonical":
            summary = f'{board["listed"]} listed · {board["open"]} open · {board["market_based"]} market-based · {board["model_only"]} model-only · {board["blank"]} blank'
        else:
            summary = f'{board["fixtures_total"]} total · {board["open"]} open · {board["open_with_market"]} with market evidence · {board["open_model_only"]} model-only · {board["open_blank"]} blank'
        source_key = "canonical_board" if key == "canonical" else "coverage_board"
        row = "<tr>" + td("Board", f'<strong>{esc(label)}</strong><br><span class="small">{esc(board["policy"])}</span>')
        row += td("Capture UTC", f'<span class="num">{esc(board["capture_utc"])}</span>')
        row += td("Snapshot counts", esc(summary))
        row += td("Source", source_link(data, source_key)) + "</tr>"
        board_rows.append(row)
    roster = data["roster_and_rest"]
    live_map_list = " · ".join(live["maps_observed"])
    return f"""
    <div class="hero">
      <div class="eyebrow">Day 4 preview · source-linked · reviewed 16 October 2026</div>
      <h1>TWC Day 4: market tie, one bracket slot still unresolved.</h1>
      <p>This is a dated research snapshot, not a live scoreboard. I verified the Day 1–3 results, checked the semifinal market without using HotSpawn crowd picks, and left unverified bracket and Pick’ems values blank.</p>
    </div>
    <div class="actions"><a class="button" href="#day4">See Day 4 decisions</a><a class="button secondary" href="unresolved.html">Unresolved picks &amp; limitations</a><a class="button secondary" href="../../picks-every-match/index.html">All CS2 picks</a></div>
    <div class="notice neutral"><strong>Executive summary:</strong> FURIA–Aurora is <strong>50% / 50%</strong> after no-vig normalization at each observed bookmaker-labelled source. There is no priced edge, and HotSpawn ownership was not visible—so a leaderboard “contrarian” angle cannot be measured. The second semifinal is Falcons vs an unverified opponent until BetBoom–Legacy is final; do not name a winner or opponent from a placeholder.</div>
    <div class="grid" aria-label="Key Day 4 facts">
      <article class="card"><div class="kicker">FURIA vs Aurora</div><div class="big">50 / 50</div><p class="muted">Two even source readings; no directional pick.</p><p><a href="#market">View line math and source capture times</a></p></article>
      <article class="card"><div class="kicker">Falcons semifinal</div><div class="big">Opponent blank</div><p class="muted">Conditional on BetBoom–Legacy. No winner verified in the latest checked match view.</p><p><a href="unresolved.html#second-semi">Why it stays unresolved</a></p></article>
      <article class="card"><div class="kicker">Pick’em coverage</div><div class="big">Unverified</div><p class="muted">The lobby filter shows one TWC match and BetBoom/Legacy team counts, but the match rows did not load.</p><p>{source_link(data, "hotspawn_pickems", "Check the HotSpawn Pick’ems lobby")}</p></article>
    </div>

    <section id="day4"><h2>Day 4 picks and probabilities</h2><p>The date and slots come from HotSpawn’s tournament schedule. Probabilities are sourced from external lines only; crowd ownership is not a probability input. A null pick is deliberate when a directional choice is unsupported.</p>{render_day4(data)}<div class="notice"><strong>Contrarian-but-not-stupid rule:</strong> do not select an underdog merely because 9z upset Aurora on Day 1. Aurora beat NIP on Day 2 and defeated 9z 2–0 in the Day 3 rematch. The observed semifinal odds are still tied, and no HotSpawn ownership percentage is available to estimate leverage.</div></section>

    <section id="market"><h2>FURIA–Aurora external line snapshot</h2><p>Each source’s two-way decimal line independently normalizes to 50% / 50%. The primary feed and mirrored bookmaker-labelled line are shown separately; this is not represented as a broad independent-book consensus. Same-day rechecks still displayed the even prices, but the fetch interface did not supply an exact timestamp for those rechecks.</p>{render_market(data)}<p class="small">Melbet’s exact repository capture is 19:20:59Z; Thunderpick-via-bo3.gg is 19:21:46Z. The formal arithmetic and excluded sources are on <a href="method.html">Method &amp; sources</a>.</p></section>

    <section id="results"><h2>What happened on Days 1–3</h2><p>The 9z upset is retained as an outcome, not carried forward as a forecast. Aurora changed its veto for the Day 3 rematch and won 2–0; that is relevant match context, not a calibrated causal adjustment.</p>{render_results(data)}<div class="notice warning"><strong>Group B decider — no winner claim:</strong> at the latest checked HLTV view, BetBoom–Legacy was LIVE at 1–1 in maps ({esc(live["maps_observed"][0])}; {esc(live["maps_observed"][1])}; Mirage not started in that view). HotSpawn’s match page showed 0–0 and “Waiting for information,” while its tournament card labelled the match “UPCOMING.” <strong>Series result: unverified.</strong> {source_link(data, "hltv_betboom_legacy", "HLTV live match view")} · {source_link(data, "hotspawn_betboom_legacy", "HotSpawn match page")}</div></section>

    <section id="roster"><h2>Aurora roster, onboarding and rest</h2><p>The reviewed official announcements confirm a July rebuild, not a newly verified October roster move. Calendar time since signing does not measure practice or adaptation, so no probability penalty is applied.</p>{render_roster(data)}<p>Additional context: {source_link(data, "hltv_aurora_roster")} · <a href="../../twc-2026/roster.html">existing roster/rest review and its search limitations</a>.</p><p><strong>Rest hours:</strong> <span class="blank">— unverified</span>. No verified rest/sleep/travel schedule was collected, and no numeric fatigue adjustment is made. {source_link(data, "hotspawn_day2", "Day 2 match schedule and results")}</p></section>

    <section id="coverage"><h2>Coverage boundary and refresh freshness</h2><p>The tournament page lists two semifinal placeholders (#1080207 and #1080208), but the Pick’ems lobby rendered no fixture card. They are documented here as tournament fixtures; we do not assert that either is currently selectable in Pick’ems. See <a href="unresolved.html">Unresolved</a> for the exact unknowns and next evidence needed.</p>{table_open("Two repository snapshots are not interchangeable; capture time and policy are shown.", ["Board", "Capture UTC", "Snapshot counts", "Source"])}{"".join(board_rows)}{table_close()}<div class="notice warning">The newer independent capture is {boards["capture_gap_seconds"] // 3600}h {(boards["capture_gap_seconds"] % 3600) // 60}m {(boards["capture_gap_seconds"] % 60)}s newer than the canonical capture. The counts/policies are different and must not be mixed. The canonical board’s configured four-hour refresh workflow is best-effort; check its run history for current data. {source_link(data, boards["canonical_refresh_workflow_url_key"], "Open the 4-hour refresh workflow")}</div><p>Latest main check observed at 19:43Z: the dashboard verification run failed at its post-refresh source-linked-row recheck, while the GitHub Pages deployment completed successfully. The checked-out suite passed 731 tests (3 skipped), and this audit’s 8 targeted tests passed. The hosted check is flagged, not claimed fixed; details are on <a href="flagged.html#ci">Flagged for Review</a>.</p></section>
    """


def render_unresolved(data: dict) -> str:
    live = data["live_match"]
    issues = [
        ("Falcons’ semifinal opponent", "", "Leave opponent, winner pick, and probability blank until the BetBoom–Legacy decider is final and the official semifinal pairing is verified.", ["hotspawn_tournament", "hltv_betboom_legacy", "hotspawn_betboom_legacy"]),
        ("Are either Day 4 semifinal slots selectable in Pick’ems?", "UNVERIFIED", "The lobby filter lists one TWC event and BetBoom/Legacy team counts, but no match row loaded. Do not claim the semis are present or absent.", ["hotspawn_pickems", "hotspawn_tournament"]),
        ("HotSpawn ownership for FURIA–Aurora", "", "No ownership percentage was visible; do not manufacture a leaderboard leverage ratio.", ["hotspawn_pickems"]),
        ("Pick’em point values for the two semifinal placeholders", "", "No point values were visible on the placeholder cards. Leave blank.", ["hotspawn_tournament", "hotspawn_pickems"]),
        ("BetBoom–Legacy series winner", "", f"HLTV was {live['hltv_status_observed']} at 1–1 in maps; Mirage had not started in that fetched view. HotSpawn displayed 0–0 / Waiting for information. Do not report a winner.", ["hltv_betboom_legacy", "hotspawn_betboom_legacy"]),
        ("Exact live rest/fatigue hours for Aurora", "", "No verified rest, sleep, travel or practice-hours record. Map count is not rest time.", ["hotspawn_day2", "hotspawn_aurora_day3"]),
        ("Causal win-probability effect of Aurora’s July roster onboarding", "", "The official July signings are confirmed; a causal October probability adjustment is not. No arbitrary penalty is applied.", ["aurora_jimpphat", "aurora_ash", "aurora_kyxsan"]),
        ("Fresh live odds at decision time", "DATED SNAPSHOT", "Exact feed captures are 19:20:59Z and 19:21:46Z. Later same-day checks showed the same even prices but did not expose exact response times; treat the published numbers as dated evidence, not a live quote.", ["melbet_feed", "thunderpick_mirror"]),
        ("Canonical board after the independent 19:22 capture", "FRESHNESS FLAG", "Canonical board capture is 13:13:13Z; separate full-coverage capture is 19:22:09Z. Their fixture inventories and fallback policies differ; do not combine counts.", ["canonical_board", "coverage_board", "canonical_refresh_workflow"]),
        ("Other CS2 fixtures without verified market prices", "See all-match page", "This TWC report does not overwrite the repository’s all-match board. Use its dedicated unresolved section for all non-TWC/low-tier blanks and fallbacks.", ["canonical_board", "coverage_board"]),
    ]
    rows = []
    for question, value, reason, keys in issues:
        row = "<tr>" + td("Unknown", f'<strong>{esc(question)}</strong>')
        row += td("Value", f'<span class="blank">{esc(value) if value else "—"}</span>')
        row += td("Why blank / next evidence", esc(reason))
        row += td("Sources", source_refs(data, keys)) + "</tr>"
        rows.append(row)
    return f"""
    <div class="hero"><div class="eyebrow">No unsupported values</div><h1>Unresolved picks &amp; limitations</h1><p>Anything without a source-backed participant, price, ownership figure or measurement remains blank. This is a separate limitations page, not a hidden footnote.</p></div>
    <div id="second-semi" class="notice warning"><strong>Second semifinal:</strong> Falcons’ opponent is not verified until BetBoom–Legacy is final. No winner is reported for the 1–1 decider.</div>
    {table_open("Open facts and values withheld rather than inferred.", ["Question / field", "Value", "Why blank / next evidence", "Review links"])}{"".join(rows)}{table_close()}
    <section><h2>Where to go next</h2><ul>
      <li><a href="index.html#day4">Day 4 slots and supported 50/50 FURIA–Aurora probability</a></li>
      <li><a href="flagged.html">Flagged for Review: source-state conflicts and CI note</a></li>
      <li><a href="../../picks-every-match/unresolved.html">All-match unresolved CS2 picks and limitations</a></li>
      <li><a href="../../picks-every-match/index.html">All-match CS2 picks board</a></li>
      <li><a href="../../twc-2026/results.html">Prior TWC results page</a></li>
    </ul></section>
    """


def render_flagged(data: dict) -> str:
    rows = [
        ("F1 · Inconsistent tournament status cards", "HotSpawn’s tournament page showed Aurora–9z as LIVE after the official Day 3 article said Aurora won 2–0. It showed BetBoom–Legacy as UPCOMING while HLTV showed the decider LIVE at 1–1. Treat the tournament card status as stale/inconsistent until corroborated.", ["hotspawn_tournament", "hotspawn_aurora_day3", "hltv_betboom_legacy"]),
        ("F2 · HotSpawn match page is behind the live match", "BetBoom–Legacy’s match page showed 0–0 and “Waiting for information”; HLTV showed Nuke 16–13 BetBoom, Dust2 13–11 Legacy, with Mirage not started. No winner verified.", ["hotspawn_betboom_legacy", "hltv_betboom_legacy"]),
        ("F3 · Pick’ems fixture card missing", "The lobby filters showed TWC (1), BetBoom (1) and Legacy (1), but the list area said “Check back in a minute” / “Fresh info is on the way.” This is not sufficient to verify semifinal inclusion, exact row mapping, or crowd ownership.", ["hotspawn_pickems"]),
        ("F4 · Market source quality differs", "Melbet’s retained line is from its public feed; its human page was country-restricted in a direct fetch. Thunderpick is labelled on a bo3.gg mirror, not a direct operator page. EGamersWorld’s displayed 1.83/1.90 did not identify a bookmaker. Kalshi’s 15¢ and 13¢ spreads exceed the board’s 10¢ threshold. Only the two even source readings are shown as evidence, with caveats.", ["melbet_feed", "melbet_public", "thunderpick_mirror", "egamersworld", "kalshi"]),
        ("F5 · Quote timestamp precision", "Exact repository captures are 19:20:59Z (Melbet) and 19:21:46Z (Thunderpick via bo3.gg). A later same-day recheck remained even, but the fetcher did not expose an exact time. These are dated observations, not guaranteed live odds.", ["melbet_feed", "thunderpick_mirror"]),
        ("F6 · Board captures differ in time and policy", "The canonical market-first board is 13:13:13Z; a separate broader capture is 19:22:09Z. The second capture is 6h 8m 56s newer but has a different inventory/fallback policy. Keep counts separate.", ["canonical_board", "coverage_board", "canonical_refresh_workflow"]),
        ("F7 · Hosted dashboard validation was red", "GitHub Actions reported failure at “Recheck generated site and every source-linked row” on main SHA 9115942 (observed 19:43Z). The Pages deployment run succeeded; the local full suite passed on the checked-out tree and this session’s targeted suite passed. Detailed remote log retrieval returned EOF; cause is not inferred, and the hosted recheck is not claimed resolved.", ["dashboard_check_run", "pages_deploy_run"]),
        ("F8 · Roster/rest story is bounded", f"Three official Aurora announcements were from July. {esc(data['roster_and_rest']['recent_change_finding'])} Actual rest hours and a causal probability effect remain blank.", ["aurora_jimpphat", "aurora_ash", "aurora_kyxsan"]),
        ("F9 · A tie is not a contrarian edge", "The two bookmaker-labelled readings are 50/50 after removing overround, and HotSpawn ownership was not available. A forced team choice would be arbitrary; no contrarian pick is published.", ["melbet_feed", "thunderpick_mirror", "hotspawn_pickems"]),
    ]
    table_rows = []
    for title, note, keys in rows:
        row = "<tr>" + td("Flag", f'<strong>{esc(title)}</strong>')
        row += td("Finding", esc(note))
        row += td("Source links", source_refs(data, keys)) + "</tr>"
        table_rows.append(row)
    return f"""
    <div class="hero"><div class="eyebrow">Separate public review page</div><h1>Flagged for Review</h1><p>These issues affect confidence, coverage or source freshness. Values were not “fixed” by guessing; each flag links back to the evidence needed to re-check it.</p></div>
    <div class="notice warning"><strong>Important:</strong> a successful Pages deployment does not erase a failed validation check. The hosted recheck remains flagged even though the local suite passed.</div>
    <div id="ci"></div>
    {table_open("Nine source, status, freshness and verification flags.", ["Flag", "Finding", "Review links"])}{"".join(table_rows)}{table_close()}
    <section><h2>Review state</h2><p>The Day 4 HTML pages are generated from <a href="../../data/94ab4483/review.json">the frozen evidence ledger</a> by the <a href="https://github.com/buffedlizard55-lab/MaltaProj2/blob/main/scripts/94ab4483/build.py">versioned build script</a>. A fresh deployment does not automatically refresh this dated research snapshot; its date and quote-capture times remain visible.</p></section>
    """


def render_method(data: dict) -> str:
    market = data["market_evidence"]
    rows = []
    for quote in market["observations"]:
        inv_a = Decimal(1) / Decimal(str(quote["decimal_a"]))
        inv_b = Decimal(1) / Decimal(str(quote["decimal_b"]))
        overround = inv_a + inv_b - Decimal(1)
        fair_a = inv_a / (inv_a + inv_b)
        fair_b = inv_b / (inv_a + inv_b)
        row = "<tr>" + td("Operator", esc(quote["operator"]))
        row += td("Raw odds", f'<span class="num">{quote["decimal_a"]:.2f} / {quote["decimal_b"]:.2f}</span>')
        row += td("Implied / overround", f'<span class="num">{inv_a:.6f} / {inv_b:.6f}; {overround:.6%}</span>')
        row += td("Fair probability", f'<span class="num">{fair_a:.2%} / {fair_b:.2%}</span>')
        row += td("Source", source_link(data, quote["source_url_key"])) + "</tr>"
        rows.append(row)
    excluded = []
    for item in market["excluded_or_secondary"]:
        label = data["sources"][item["source_url_key"]]["label"]
        reason = item.get("reason", "Not used as a match probability.")
        excluded.append(f'<li>{source_link(data, item["source_url_key"], label)} — {esc(reason)}</li>')
    roster_sources = " · ".join(source_link(data, key) for key in data["roster_and_rest"]["source_url_keys"])
    return f"""
    <div class="hero"><div class="eyebrow">Reproducible arithmetic · explicit fallbacks</div><h1>Method &amp; source hierarchy</h1><p>Each published probability must be traceable to a dated, named source. HotSpawn match ownership is not a probability input.</p></div>
    <section><h2>Probability calculation: FURIA vs Aurora</h2><p>The decimal line is converted to implied probability, then normalized to remove the two-way overround. No additional roster, recency, fatigue or crowd adjustment is applied.</p><div class="formula">implied = 1 / decimal odds<br>overround = (1 / odds A) + (1 / odds B) − 1<br>no-vig P(A) = (1 / odds A) / ((1 / odds A) + (1 / odds B))</div>{table_open("Re-derived from each preserved source price; team order is FURIA / Aurora.", ["Operator", "Raw odds", "Implied / overround", "Fair probability", "Source"])}{"".join(rows)}{table_close()}<p>{esc(market["summary_method"])}</p></section>
    <section><h2>What was excluded</h2><ul>{"".join(excluded)}</ul><p>HLTV’s match-page “Pick a winner” panel is a user poll, not a sportsbook market; it is not used. HotSpawn ownership was not visible in the rendered lobby, so no crowd leverage is computed.</p></section>
    <section><h2>Decision rule and tie handling</h2><ul><li>When two verified source readings both normalize to 50/50, publish the supported probabilities but leave the directional team pick blank. A forced side is arbitrary; missing ownership makes contrarian expected points uncomputable.</li><li>When a team or opponent is a tournament-page placeholder, do not emit a probability or pick until official pairing and relevant price are confirmed.</li><li>Roster announcements can be verified without proving a causal win-probability effect. No numerical adjustment is made for Aurora’s July additions.</li><li>Actual rest hours were not verified; match count is not converted into fatigue probability.</li><li>For other CS2 fixtures, use the repository’s all-match board and its dedicated unresolved page; this TWC preview does not overwrite their method or counts.</li></ul></section>
    <section><h2>Roster, refresh and repository links</h2><p>{roster_sources}</p><p>Canonical pick pages use an automated four-hour refresh (best-effort; a workflow configuration is not a guarantee that each scheduled run succeeded). {source_link(data, "canonical_refresh_workflow", "See the refresh workflow and run history")}.</p><p>Source snapshots: {source_link(data, "canonical_board")} · {source_link(data, "coverage_board")} · <a href="../../data/94ab4483/review.json">this audit’s line-by-line ledger</a>.</p></section>
    """


def verify_evidence(data: dict) -> dict:
    if data.get("reviewed_date_utc") != "2026-10-16":
        raise ValueError("Unexpected review date")
    for key, source in data["sources"].items():
        if not source["url"].startswith("https://"):
            raise ValueError(f"Source {key} is not HTTPS")
    recalculated = []
    for quote in data["market_evidence"]["observations"]:
        a = Decimal(1) / Decimal(str(quote["decimal_a"]))
        b = Decimal(1) / Decimal(str(quote["decimal_b"]))
        fair_a = a / (a + b)
        fair_b = b / (a + b)
        overround = a + b - Decimal(1)
        for key, actual, expected in (
            ("no_vig_a", Decimal(str(quote["no_vig_a"])), fair_a),
            ("no_vig_b", Decimal(str(quote["no_vig_b"])), fair_b),
            ("overround", Decimal(str(quote["overround"])), overround),
        ):
            if abs(actual - expected) > Decimal("0.000002"):
                raise ValueError(f"{quote['operator']} {key} mismatch: {actual} != {expected}")
        recalculated.append({
            "operator": quote["operator"],
            "decimal_odds_furia_aurora": [quote["decimal_a"], quote["decimal_b"]],
            "no_vig_furia_aurora": [float(fair_a), float(fair_b)],
            "overround": float(overround),
            "capture_utc": quote["retrieved_utc"],
            "source_url": data["sources"][quote["source_url_key"]]["url"],
        })
    if len(data["results"]) != 9:
        raise ValueError("Expected 9 verified Day 1–3 result rows")
    if len(data["day4_fixtures"]) != 2:
        raise ValueError("Expected two semifinal schedule slots")
    unresolved = [f for f in data["day4_fixtures"] if f["probability"] is None or f["pick"] is None]
    if not unresolved:
        raise ValueError("The conditional semifinal must remain unresolved")
    if data["market_evidence"]["crowd_ownership"] is not None:
        raise ValueError("Do not publish unverified HotSpawn ownership")
    board = data["board_freshness"]
    t0 = datetime.fromisoformat(board["canonical"]["capture_utc"].replace("Z", "+00:00"))
    t1 = datetime.fromisoformat(board["independent"]["capture_utc"].replace("Z", "+00:00"))
    gap = int((t1 - t0).total_seconds())
    if gap != board["capture_gap_seconds"]:
        raise ValueError("Board capture gap arithmetic mismatch")
    return {
        "session_id": data["session_id"],
        "event": data["event"],
        "reviewed_date_utc": data["reviewed_date_utc"],
        "status": "published with explicit unresolved/flagged values",
        "result_rows": len(data["results"]),
        "day1_rows": sum(1 for item in data["results"] if item["day"] == 1),
        "day2_rows": sum(1 for item in data["results"] if item["day"] == 2),
        "day3_final_rows": sum(1 for item in data["results"] if item["day"] == 3),
        "day4_semifinal_slots": len(data["day4_fixtures"]),
        "market_quotes_rederived": recalculated,
        "hotspawn_ownership_used_as_probability": False,
        "unresolved_fixture_ids": [f["fixture_id"] for f in unresolved],
        "canonical_capture_gap_seconds": gap,
        "pages": ["index.html", "unresolved.html", "flagged.html", "method.html"],
        "html_link_policy": "Every research table row renders at least one external HTTPS review link.",
    }


def main() -> None:
    data = load_data()
    report = verify_evidence(data)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "style.css").write_text(CSS + "\n", encoding="utf-8")
    pages = {
        "index.html": layout(data, "Day 4 preview", "home", render_index(data)),
        "unresolved.html": layout(data, "Unresolved picks & limitations", "unresolved", render_unresolved(data)),
        "flagged.html": layout(data, "Flagged for Review", "flags", render_flagged(data)),
        "method.html": layout(data, "Method & sources", "method", render_method(data)),
    }
    for name, content in pages.items():
        clean = "\n".join(line.rstrip() for line in content.splitlines()).strip() + "\n"
        (OUT / name).write_text(clean, encoding="utf-8")
    (OUT / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Rendered {len(pages)} TWC Day 4 audit pages to {OUT.relative_to(ROOT)}")
    print(f"Verified {report['result_rows']} results, {len(report['market_quotes_rederived'])} odds rows, {len(report['unresolved_fixture_ids'])} unresolved semifinal slot(s).")


if __name__ == "__main__":
    main()
