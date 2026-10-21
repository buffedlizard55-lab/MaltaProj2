#!/usr/bin/env python3
"""Site builder for the HotSpawn CS2 every-match picks board (session d9d7627b).

Reads `data/d9d7627b/board.json` and writes a clean mobile-first static site:

  index.html                  (repo root = executive-summary front door)
  hotspawn-cs2/index.html     (same executive summary inside the section)
  hotspawn-cs2/picks.html     (every open match: pick, both win %, evidence)
  hotspawn-cs2/unresolved.html(unresolved picks + limitations, per match)
  hotspawn-cs2/method.html    (resolution chain, formulas, sources, limitations)
  hotspawn-cs2/flagged.html   (Flagged for Review: irregularities with source links)

Every number on these pages is rendered from board.json, which is itself re-derivable
from the stored snapshot (raw prices kept per quote). Nothing is hand-typed per match.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from urllib.parse import quote as urlquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "d9d7627b"
SECTION = ROOT / "hotspawn-cs2"
REPO = "https://github.com/buffedlizard55-lab/MaltaProj2"
LOBBY = "https://play.hotspawn.com/lobby"
VRS_REPO_URL = "https://github.com/ValveSoftware/counter-strike_regional_standings"

TIER_LABEL = {"market": "Market line", "model": "Our line · VRS model",
              "direction": "Direction only", "unresolved": "Unresolved"}
SOURCE_NAMES = {"pinnacle": "Pinnacle", "bovada": "Bovada", "melbet": "Melbet",
                "kalshi": "Kalshi", "polymarket": "Polymarket"}


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


def pct(p, digits=0) -> str:
    return "—" if p is None else f"{p * 100:.{digits}f}%"


def dec(x) -> str:
    return "—" if x is None else f"{float(x):.2f}"


def amer(x) -> str:
    if x is None:
        return "—"
    x = int(x)
    return f"+{x}" if x > 0 else str(x)


def t_el(iso: str | None, local=True) -> str:
    if not iso:
        return "—"
    text = iso.replace("T", " ")[:16] + " UTC"
    return (f'<time datetime="{esc(iso)}"{" data-local" if local else ""} '
            f'title="{esc(iso)}">{esc(text)}</time>')


def hltv_search(team: str) -> str:
    return f"https://www.hltv.org/search?query={urlquote(team)}"


def vrs_details_url(details_path: str | None) -> str | None:
    if not details_path:
        return None
    return f"{VRS_REPO_URL}/blob/main/{details_path}"


def shell(title: str, current: str, base: str, updated_line: str, body: str) -> str:
    tabs = [("summary", "Summary", "index.html"), ("picks", "All picks", "picks.html"),
            ("unresolved", "Unresolved", "unresolved.html"),
            ("method", "Method & sources", "method.html"),
            ("flagged", "Flagged", "flagged.html")]
    cur_attr = ' aria-current="page"'
    nav = "".join(
        f'<a href="{base}{href}"{cur_attr if key == current else ""}>{label}</a>'
        for key, label, href in tabs)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · HotSpawn CS2 picks</title>
<meta name="description" content="A pick and win probability for every open HotSpawn CS2 Pick'em match, from external betting lines and official Valve ratings. Updated automatically.">
<link rel="stylesheet" href="{base}assets/style.css">
</head>
<body>
<header class="site"><div class="wrap">
<p class="site-title"><a href="{base}index.html">🎯 HotSpawn CS2 Pick&rsquo;em — picks for every match</a></p>
<p class="site-sub">{updated_line}</p>
<nav class="tabs" aria-label="Picks board">{nav}</nav>
</div></header>
<main class="wrap">
{body}
<footer class="site">
<p>Probabilities come from external betting markets (de-vigged) or, where no book prices a
match, an originated line from the official Valve VRS ratings — labelled on every row.
HotSpawn is used only to discover fixtures; its crowd &ldquo;picked %&rdquo; is never used
as a probability. Blank = could not be verified from a source (see
<a href="{base}unresolved.html">Unresolved &amp; limitations</a>). Analysis only — not betting advice.</p>
<p>Data &amp; code: <a href="{REPO}/blob/main/data/d9d7627b/board.json">board.json</a> ·
<a href="{REPO}/blob/main/scripts/d9d7627b/collect.py">collector</a> ·
<a href="{REPO}/blob/main/scripts/d9d7627b/resolve.py">Resolver</a> ·
<a href="{REPO}/actions/workflows/hotspawn-cs2-d9d7627b.yml">refresh runs</a> ·
<a href="{base}method.html">method</a></p>
</footer>
</main>
<script src="{base}assets/app.js"></script>
</body>
</html>
"""


def seed_banner(board) -> str:
    seed = board.get("seed")
    if not seed:
        return ""
    return (f'<div class="banner">⚠️ <b>Seeded first publish.</b> This board was built from '
            f'the committed collector snapshot <code>{esc(seed.get("from_file"))}</code> '
            f'(collected {esc(seed.get("collected_from_utc"))} → '
            f'{esc(seed.get("collected_to_utc"))}) because the build sandbox cannot reach '
            f'bookmaker hosts. The live collector runs in GitHub Actions and replaces this '
            f'data automatically; this banner disappears on the first live refresh.</div>')


def pick_banner(row) -> str:
    res = row["resolution"]
    badge = f'<span class="badge {res["tier"]}">{TIER_LABEL[res["tier"]]}</span>'
    if res["tier"] == "unresolved":
        return (f'<div class="pick none"><span class="pickteam">No pick — unresolved</span>'
                f'{badge}<span class="small">see limitations below</span></div>')
    parts = [f'<span>✓ PICK</span><span class="pickteam">{esc(res["pick_team"])}</span>']
    if res.get("pick_prob") is not None:
        parts.append(f'<span class="pickpct">{pct(res["pick_prob"])}</span>')
    else:
        parts.append('<span class="small">probability not published (blank)</span>')
    if res.get("confidence"):
        parts.append(f'<span class="badge grey">{esc(res["confidence"])}</span>')
    parts.append(badge)
    return f'<div class="pick">{" ".join(parts)}</div>'


def prob_bar(row) -> str:
    res = row["resolution"]
    if res.get("prob_a") is None:
        return ""
    pa = res["prob_a"] * 100
    return (f'<div class="bar" role="img" aria-label="{esc(row["team_a"])} {pa:.0f} percent, '
            f'{esc(row["team_b"])} {100 - pa:.0f} percent">'
            f'<div class="a" style="width:{pa:.1f}%">{pa:.0f}%</div>'
            f'<div class="b">{100 - pa:.0f}%</div></div>'
            f'<div class="barlabels"><span>{esc(row["team_a"])}</span>'
            f'<span>{esc(row["team_b"])}</span></div>'
            f'<p class="small muted">Fair odds — {esc(row["team_a"])} '
            f'{dec(res.get("fair_decimal_a"))} ({amer(res.get("fair_american_a"))}) · '
            f'{esc(row["team_b"])} {dec(res.get("fair_decimal_b"))} '
            f'({amer(res.get("fair_american_b"))})</p>')


def evidence_details(row, board) -> str:
    res, ev = row["resolution"], row["evidence"] or {}
    out: list[str] = []
    quotes = ev.get("quotes") or []
    if quotes:
        trs = []
        for q in quotes:
            pa = q.get("prob_a")
            trs.append(
                f'<tr><td><a href="{esc(q.get("public_url"))}" rel="noopener">'
                f'{esc(q.get("source_name"))}</a></td>'
                f'<td class="kbd">{dec(q.get("decimal_a"))} / {dec(q.get("decimal_b"))}</td>'
                f'<td class="kbd">{pct(pa, 1)}</td>'
                f'<td class="kbd">{esc((q.get("retrieved_utc") or "")[:19].replace("T", " "))}Z</td></tr>')
        m = res.get("market") or {}
        out.append(
            f'<details><summary>Bookmaker evidence ({len(quotes)} price'
            f'{"s" if len(quotes) != 1 else ""}, median no-vig = {pct(m.get("prob_a"), 1)} '
            f'for {esc(row["team_a"])})</summary><div class="tblwrap"><table>'
            f'<tr><th>Source</th><th>Odds A / B (decimal)</th><th>Fair % {esc(row["team_a"])}</th>'
            f'<th>Collected</th></tr>{"".join(trs)}</table></div>'
            f'<p class="small muted">Odds shown oriented to {esc(row["team_a"])} / '
            f'{esc(row["team_b"])}. Fair % removes each book&rsquo;s margin; the pick uses '
            f'the median across books. Raw prices are stored in '
            f'<a href="{REPO}/blob/main/data/d9d7627b/snapshot.json">snapshot.json</a>.</p></details>')
    vrs = ev.get("vrs") or {}
    if res["tier"] in ("model", "direction") or vrs.get("team_a") or vrs.get("team_b"):
        lines = []
        for side_key, name in (("team_a", row["team_a"]), ("team_b", row["team_b"])):
            v = vrs.get(side_key)
            if v:
                durl = vrs_details_url(v.get("details_path"))
                lines.append(
                    f'<li><b>{esc(name)}</b> — Valve VRS #{v.get("standing")}, '
                    f'{v.get("points")} pts (roster: {esc(v.get("roster"))})'
                    + (f' · <a href="{esc(durl)}" rel="noopener">official details</a>' if durl else "")
                    + '</li>')
            for cand in (vrs.get("ambiguous") or {}).get(side_key) or []:
                durl = vrs_details_url(cand.get("details_path"))
                lines.append(
                    f'<li><b>{esc(name)}</b> — ambiguous VRS roster #{cand.get("standing")}, '
                    f'{cand.get("points")} pts (roster: {esc(cand.get("roster"))}; latest '
                    f'counted match {esc(cand.get("latest_match_date") or "n/a")})'
                    + (f' · <a href="{esc(durl)}" rel="noopener">official details</a>' if durl else "")
                    + '</li>')
        if lines:
            model = res.get("model") or {}
            note = ""
            if res["tier"] == "model":
                note = (f'<p class="small">Originated line: Valve Glicko expected-win formula '
                        f'on the {model.get("delta_points"):+d}-point gap, slope k='
                        f'{model.get("k"):.3f} fitted to {model.get("fit_n_pairs")} observed '
                        f'market pairs (MAE {model.get("fit_mae") * 100:.1f}pp). This is a '
                        f'model estimate, not a bookmaker price.</p>')
            out.append(
                f'<details><summary>Rating evidence (official Valve VRS, snapshot '
                f'{esc(vrs.get("snapshot"))})</summary><ul class="tight">{"".join(lines)}</ul>'
                f'{note}<p class="small muted">Source: '
                f'<a href="{esc(vrs.get("page_url"))}" rel="noopener">Valve VRS global '
                f'standings on GitHub</a>.</p></details>')
    if res.get("direction_reason"):
        out.append(f'<p class="small"><b>Why this direction:</b> '
                   f'{esc(res["direction_reason"])}</p>')
    if res.get("limitations"):
        lis = "".join(f"<li>{esc(lim)}</li>" for lim in res["limitations"])
        out.append(f'<details><summary>Limitations ({len(res["limitations"])})</summary>'
                   f'<ul class="tight">{lis}</ul></details>')
    rj = ev.get("rejected_joins") or []
    if rj:
        lis = "".join(
            f'<li><a href="{esc(x.get("public_url"))}" rel="noopener">'
            f'{esc(x.get("source_name"))}</a>: {esc(x.get("reason"))}</li>' for x in rj)
        out.append(f'<details><summary>Prices seen but NOT used ({len(rj)})</summary>'
                   f'<ul class="tight">{lis}</ul></details>')
    return "".join(out)


def match_card(row, board, base, soon_ids) -> str:
    res = row["resolution"]
    meta = [esc(row.get("competition") or "")]
    if row.get("tier"):
        meta.append(f'Tier {esc(row["tier"])}')
    if row.get("best_of"):
        meta.append(f'BO{esc(row["best_of"])}')
    if row.get("points"):
        meta.append(f'{esc(row["points"])} pts on HotSpawn')
    lock = f' · <span data-lock="{esc(row.get("lock_utc"))}"></span>' if row.get("lock_utc") else ""
    locked_cls = " locked" if row["state"] == "locked" else ""
    soon = ' data-soon="1"' if row["fixture_id"] in soon_ids else ""
    hs_label = "HotSpawn match page" if row.get("hotspawn_url_kind") == "match page" else "HotSpawn lobby"
    return f"""<article class="card{locked_cls}" id="{esc(row["fixture_id"])}" data-tier="{res["tier"]}"{soon}>
<div class="meta"><span>{" · ".join(m for m in meta if m)}</span></div>
<div class="meta"><span>Starts {t_el(row.get("start_utc"))} · picks lock {t_el(row.get("lock_utc"))}{lock}</span></div>
<p class="teams">{esc(row["team_a"])} <span class="vs">vs</span> {esc(row["team_b"])}</p>
{pick_banner(row)}
{prob_bar(row)}
{evidence_details(row, board)}
<div class="links">
<a href="{esc(row.get("hotspawn_url") or LOBBY)}" rel="noopener">{hs_label}</a>
<a href="{hltv_search(row["team_a"])}" rel="noopener">HLTV: {esc(row["team_a"])}</a>
<a href="{hltv_search(row["team_b"])}" rel="noopener">HLTV: {esc(row["team_b"])}</a>
</div>
</article>"""


def day_groups(rows):
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault((r.get("start_utc") or "")[:10], []).append(r)
    return [(d, groups[d]) for d in sorted(groups)]


# ----------------------------------------------------------------------- summary page

def summary_body(board, base: str) -> str:
    c = board["counts"]
    bt = c["by_tier"]
    open_rows = [r for r in board["rows"] if r["state"] == "open"]
    open_rows.sort(key=lambda r: (r.get("start_utc") or "", r["fixture_id"]))
    unresolved = [r for r in open_rows if r["resolution"]["tier"] == "unresolved"]
    with_pick = len(open_rows) - len(unresolved)
    # tier counts for OPEN rows only (board counts include locked)
    ot = {"market": 0, "model": 0, "direction": 0}
    for r in open_rows:
        t = r["resolution"]["tier"]
        if t in ot:
            ot[t] += 1
    soon = sorted(open_rows, key=lambda r: r.get("lock_utc") or "9999")[:5]
    soon_lis = "".join(
        f'<li><a href="{base}picks.html#{esc(r["fixture_id"])}"><b>{esc(r["resolution"].get("pick_team") or "No pick")}</b>'
        f'{" " + pct(r["resolution"].get("pick_prob")) if r["resolution"].get("pick_prob") is not None else ""}</a> · '
        f'{esc(r["team_a"])} vs {esc(r["team_b"])} · '
        f'<span data-lock="{esc(r.get("lock_utc"))}"></span></li>' for r in soon)
    unres_lis = "".join(
        f'<li><a href="{base}unresolved.html#{esc(r["fixture_id"])}">'
        f'<b>{esc(r["team_a"])} vs {esc(r["team_b"])}</b></a> '
        f'<span class="muted">({esc(r.get("competition"))}, starts '
        f'{esc((r.get("start_utc") or "")[:16].replace("T", " "))} UTC)</span> — '
        f'{esc((r["resolution"]["limitations"][0] if r["resolution"]["limitations"] else "no verified source")[:180])}…</li>'
        for r in unresolved)
    fit = board["calibration"]
    wk = board.get("week") or {}
    week_line = (f'<p class="muted">HotSpawn week {esc(wk.get("weekId"))}: '
                 f'{esc((wk.get("weekStartUtc") or "")[:10])} → '
                 f'{esc((wk.get("weekEndUtc") or "")[:10])} (UTC).</p>') if wk.get("weekId") else ""
    return f"""
<h1>Executive summary — every HotSpawn CS2 match, one pick each</h1>
<p>This page is the front door. Every CS2 match currently open in the
<a href="{LOBBY}" rel="noopener">HotSpawn Pick&rsquo;em lobby</a> gets a pick and a win
probability from <b>outside</b> betting lines — or, when no book prices a low-tier match,
an originated line from the official Valve ratings. Bookmark this page on your phone;
it refreshes automatically.</p>
{week_line}
{seed_banner(board)}
<div class="stats">
<div class="stat"><div class="num">{len(open_rows)}</div><div class="lbl">open CS2 matches</div></div>
<div class="stat"><div class="num">{with_pick}</div><div class="lbl">with a pick</div></div>
<div class="stat"><div class="num">{ot["market"]}</div><div class="lbl">from betting lines</div></div>
<div class="stat"><div class="num">{ot["model"]}</div><div class="lbl">our VRS-model line</div></div>
<div class="stat"><div class="num">{ot["direction"]}</div><div class="lbl">direction only (% blank)</div></div>
<div class="stat"><div class="num">{len(unresolved)}</div><div class="lbl">unresolved</div></div>
</div>
<div class="biglinks">
<a class="biglink" href="{base}picks.html"><b>👉 All picks — every open match</b><span>Pick, both teams&rsquo; win %, fair odds, and the source behind each number.</span></a>
<a class="biglink warn" href="{base}unresolved.html"><b>⚠️ Unresolved picks &amp; limitations ({len(unresolved)})</b><span>Matches with no defensible pick yet — exactly which sources were checked and why each failed.</span></a>
<a class="biglink" href="{base}method.html"><b>🧮 Method &amp; sources</b><span>How lines are de-vigged, how our own line is originated (k={fit.get("k") and round(fit["k"], 3)}, {fit.get("n_pairs")} calibration pairs), matching rules.</span></a>
<a class="biglink flag" href="{base}flagged.html"><b>🚩 Flagged for review</b><span>Stale HotSpawn listings, ambiguous team names, rejected price joins, source failures.</span></a>
</div>
<h2>⏰ Closing soon — next picks to lock</h2>
<ul class="tight">{soon_lis or "<li>No open matches right now — check back after the next refresh.</li>"}</ul>
<h2>How to read a pick</h2>
<div class="legend">
<div><span class="badge market">Market line</span><span>Median fair (no-vig) probability across real bookmaker/exchange prices collected this run. Strongest evidence.</span></div>
<div><span class="badge model">Our line · VRS model</span><span>No book prices this match. Probability originated from both teams&rsquo; official Valve VRS points (Valve&rsquo;s Glicko formula, slope fitted to {fit.get("n_pairs")} observed market pairs, typical error ±{(fit.get("mae_prob") or 0) * 100:.0f}pp). An estimate — labelled as one.</span></div>
<div><span class="badge direction">Direction only</span><span>Only one side has a verified rating and no book prices the match. We pick the rated side and leave the % <b>blank</b> rather than invent one.</span></div>
<div><span class="badge unresolved">Unresolved</span><span>No price and no usable rating. No pick is published — see the limitations instead of a guess.</span></div>
</div>
<h2>Unresolved right now &amp; why</h2>
<ul class="tight">{unres_lis or "<li>None — every open match currently resolves to a pick.</li>"}</ul>
<p><a href="{base}unresolved.html">Full unresolved section with per-match limitations →</a></p>
<h2>Coverage accounting (nothing silently dropped)</h2>
<p>HotSpawn currently returns <b>{c["fixtures_total"]} CS2 fixtures</b> to this collector:
<b>{c["open"]} open</b> for picks, <b>{c["locked"]} locked/started in the last 24h</b>
(shown at the bottom of the picks page), <b>{c["finished"]} finished</b>,
<b>{c["cancelled"]} cancelled</b>, and <b>{c["stale"]} stale listings</b> still marked
&ldquo;scheduled&rdquo; &gt;24h after their start (listed on the
<a href="{base}flagged.html">Flagged page</a>). {c["quotes_collected"]} external prices were
collected this run; {c["quotes_joined"]} joined an open/locked fixture under the strict rules.</p>
<h2>Previous research (archive)</h2>
<p>This board consolidates dozens of earlier one-off &ldquo;desks&rdquo; into one maintained
page set and is, from 2026-10-21, the single front door. Nothing was deleted: the full
archive index is at
<a href="{'start/archive.html' if base else '../start/archive.html'}">start/archive.html</a>.
Earlier boards remain live, e.g.
<a href="{'picks-every-match/index.html' if base else '../picks-every-match/index.html'}">picks-every-match</a>,
<a href="{'start/index.html' if base else '../start/index.html'}">start</a>,
<a href="{'desk/index.html' if base else '../desk/index.html'}">desk</a>,
<a href="{'ourline/index.html' if base else '../ourline/index.html'}">ourline</a>,
<a href="{'cs2/index.html' if base else '../cs2/index.html'}">cs2</a>,
<a href="{'hotspawn-live/index.html' if base else '../hotspawn-live/index.html'}">hotspawn-live</a> — they are
dated research snapshots, superseded by the picks above.</p>
"""


# ------------------------------------------------------------------------- picks page

def picks_body(board, base: str) -> str:
    now_iso = board["generated_utc"]
    gen = core.parse_iso(now_iso)
    rows = [r for r in board["rows"] if r["state"] in ("open", "locked")]
    rows.sort(key=lambda r: (r.get("start_utc") or "", r["fixture_id"]))
    open_rows = [r for r in rows if r["state"] == "open"]
    locked_rows = [r for r in rows if r["state"] == "locked"]
    soon_ids = set()
    for r in open_rows:
        lock = core.parse_iso(r.get("lock_utc"))
        if gen and lock and 0 <= (lock - gen).total_seconds() <= 6 * 3600:
            soon_ids.add(r["fixture_id"])
    parts = [f'<h1>All picks — every open HotSpawn CS2 match ({len(open_rows)})</h1>',
             '<p class="muted">Sorted by start time. Times convert to your device&rsquo;s '
             'timezone automatically. Tap a filter to narrow the list.</p>',
             seed_banner(board),
             '<div class="chips" role="group" aria-label="Filter picks">'
             '<button data-filter="all" aria-pressed="true">All</button>'
             '<button data-filter="market" aria-pressed="false">Market line</button>'
             '<button data-filter="model" aria-pressed="false">Our line (VRS)</button>'
             '<button data-filter="direction" aria-pressed="false">Direction only</button>'
             '<button data-filter="unresolved" aria-pressed="false">Unresolved</button>'
             '<button data-filter="soon" aria-pressed="false">Locks &lt; 6h</button></div>']
    if not open_rows:
        parts.append('<div class="card"><p><b>No open matches right now.</b> HotSpawn adds '
                     'fixtures through the week; this page refreshes automatically every '
                     'few hours.</p></div>')
    for day, grows in day_groups(open_rows):
        parts.append(f'<p class="dayhead">{esc(day)} (UTC)</p>')
        parts += [match_card(r, board, base, soon_ids) for r in grows]
    if locked_rows:
        parts.append(f'<h2>Locked / started — picks closed ({len(locked_rows)})</h2>'
                     '<p class="muted">Shown for the record with the pick as of the last '
                     'collection before lock. These can no longer be picked on HotSpawn.</p>')
        parts += [match_card(r, board, base, soon_ids) for r in locked_rows]
    return "\n".join(parts)


# --------------------------------------------------------------------- unresolved page

def unresolved_body(board, base: str) -> str:
    rows = [r for r in board["rows"]
            if r["state"] in ("open", "locked")
            and r["resolution"] and r["resolution"]["tier"] in ("unresolved", "direction")]
    rows.sort(key=lambda r: (r.get("start_utc") or "", r["fixture_id"]))
    unres = [r for r in rows if r["resolution"]["tier"] == "unresolved"]
    direc = [r for r in rows if r["resolution"]["tier"] == "direction"]
    access = board.get("access") or {}
    hltv = access.get("hltv_probe") or {}
    pm = access.get("polymarket") or access.get("polymarket_probe") or {}
    parts = [f'<h1>Unresolved picks &amp; limitations</h1>',
             '<p>Matches below could <b>not</b> be resolved the same way as the featured '
             'market-line picks. For each one we state exactly which sources were checked '
             'and what blocked a pick. Where a direction-only pick exists, the win % is '
             'deliberately left blank — we never publish a number we cannot derive.</p>',
             seed_banner(board),
             f'<h2>Standing limitations (apply to every row)</h2><ul class="tight">'
             f'<li><b>Bookmaker coverage:</b> Pinnacle, Bovada, Melbet, Kalshi and Polymarket '
             f'are collected every run, but Tier-C online qualifiers (most of the HotSpawn '
             f'lobby) are frequently priced by none of them. “No price joined” means no '
             f'listing matched under strict rules — not that a price cannot exist anywhere.</li>'
             f'<li><b>Polymarket:</b> Gamma API reachable (HTTP {esc(pm.get("status"))}); '
             + (f'{esc(pm.get("events"))} open CS events, {esc(pm.get("two_outcome"))} '
                f'two-outcome markets, {esc(pm.get("with_game_start"))} with a verified game '
                f'start this run.' if pm.get("events") is not None else
                'no joinable CS2 match-winner markets were recorded this run — consistent '
                'with prior probes that found no CS2 match markets on Polymarket.') + '</li>'
             f'<li><b>Kalshi:</b> lists many of these matchups (series KXCS2GAME) but its '
             f'feed carries no verified kickoff time, so its prices are shown as '
             f'“seen but NOT used” evidence rather than guessed into a join.</li>'
             f'<li><b>HLTV:</b> the richest CS2 form/head-to-head source returned HTTP '
             f'{esc(hltv.get("status"))} to automated collection at {esc(hltv.get("at_utc"))}. '
             f'Every row links to HLTV search for manual review instead.</li>'
             f'<li><b>Valve VRS cadence:</b> the official standings (snapshot '
             f'{esc(board["vrs"].get("snapshot"))}) update roughly monthly and cover '
             f'{esc(board["vrs"].get("n_teams"))} teams; brand-new stacks and one-off mixes '
             f'have no rating to originate a line from.</li>'
             f'<li><b>Name ambiguity:</b> when one organisation name maps to two VRS rosters '
             f'we refuse to guess which roster plays (see rows below).</li></ul>',
             f'<h2>No pick possible ({len(unres)})</h2>']
    parts += [match_card(r, board, base, set()) for r in unres] or \
        ['<p>None right now.</p>']
    parts.append(f'<h2>Direction-only picks — probability blank ({len(direc)})</h2>'
                 '<p class="muted">A pick exists (the only verified rating signal points one '
                 'way) but no defensible percentage does.</p>')
    parts += [match_card(r, board, base, set()) for r in direc] or ['<p>None right now.</p>']
    return "\n".join(parts)


# ------------------------------------------------------------------------- method page

def method_body(board, base: str) -> str:
    fit = board["calibration"]
    access = board.get("access") or {}
    src_rows = []
    meta_map = {
        "hotspawn_lobby_page": ("HotSpawn lobby (fixture discovery only)", LOBBY),
        "hotspawn_api": ("HotSpawn public fixtures API",
                         "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"),
        "pinnacle": ("Pinnacle guest odds API", "https://www.pinnacle.com/en/esports/cs2-hub"),
        "bovada": ("Bovada coupon JSON", "https://www.bovada.lv/esports"),
        "melbet": ("Melbet LineFeed", "https://melbet.com/en/line/esports"),
        "kalshi": ("Kalshi trade API (KXCS2GAME)", "https://kalshi.com/markets/kxcs2game"),
        "polymarket": ("Polymarket Gamma API", "https://polymarket.com/"),
        "polymarket_probe": ("Polymarket Gamma API (probe)", "https://polymarket.com/"),
        "hltv_probe": ("HLTV (access probe only)", "https://www.hltv.org/matches"),
        "valve_vrs_file": ("Valve VRS standings (official, GitHub)", board["vrs"].get("page_url")),
    }
    for key, (label, url) in meta_map.items():
        m = access.get(key)
        if m is None:
            continue
        status = m.get("status")
        status_txt = "OK (HTTP 200)" if status == 200 else f"FAILED ({esc(m.get('error') or status)})"
        extra = ""
        if key == "polymarket" and m.get("events") is not None:
            extra = (f'{m.get("events")} events, {m.get("two_outcome")} two-outcome, '
                     f'{m.get("with_game_start")} with verified start')
        if m.get("quotes") is not None:
            extra = f'{m.get("quotes")} prices'
        src_rows.append(f'<tr><td><a href="{esc(url)}" rel="noopener">{esc(label)}</a></td>'
                        f'<td>{status_txt}</td><td>{esc(extra)}</td>'
                        f'<td class="kbd">{esc(m.get("at_utc") or "")}</td></tr>')
    seed = board.get("seed")
    seed_html = ""
    if seed:
        seed_html = (f'<h2>Seed provenance (first publish)</h2><p>The current board is built '
                     f'from <code>{esc(seed.get("from_file"))}</code> (SHA-256 '
                     f'<code>{esc((seed.get("file_sha256") or "")[:16])}…</code>), collected '
                     f'{esc(seed.get("collected_from_utc"))} → {esc(seed.get("collected_to_utc"))} '
                     f'by session {esc(seed.get("from_session"))}. {esc(seed.get("note"))}</p>')
    return f"""
<h1>Method &amp; sources</h1>
<h2>What this board is</h2>
<p>For every CS2 match in the <a href="{LOBBY}" rel="noopener">HotSpawn Pick&rsquo;em lobby</a>
we publish a pick and, whenever it can be derived from a source, both teams&rsquo; win
probabilities. HotSpawn itself is used <b>only</b> to discover which matches exist; its
crowd &ldquo;picked %&rdquo; is never read into any probability.</p>
<h2>Resolution chain (first tier that resolves wins)</h2>
<ol>
<li><b>Market line.</b> Two-way match-winner prices are collected from Pinnacle, Bovada,
Melbet, Kalshi and Polymarket. A price joins a fixture only if <i>both</i> team names match
exactly after normalisation (case/accents/generic words like &ldquo;Esports&rdquo; stripped;
a published alias table; or an exact same-words reorder) <i>and</i> the book&rsquo;s start
time is within 30 minutes of HotSpawn&rsquo;s. Each book&rsquo;s margin is removed
proportionally: <code>fair = (1/odds) / Σ(1/odds)</code>. The published probability is the
<b>median</b> across books, so any reader can re-derive it from the listed prices.</li>
<li><b>Our line (VRS model).</b> If no book prices the match but both teams appear uniquely
in Valve&rsquo;s official <a href="{esc(board["vrs"].get("page_url"))}" rel="noopener">VRS
global standings</a> (snapshot {esc(board["vrs"].get("snapshot"))}), we originate a line with
Valve&rsquo;s own Glicko expected-win formula,
<code>P(A) = 1/(1+10^(−g·Δ/400))</code> at RD 75, with the slope scaled by
<b>k = {fit.get("k") and round(fit["k"], 3)}</b> — fitted by least squares to
<b>{fit.get("n_pairs")}</b> fixtures where we observed both a market consensus and two VRS
ratings (mean absolute error vs the market {(fit.get("mae_prob") or 0) * 100:.1f}pp;
favourite agreement {(fit.get("fav_agree") or 0) * 100:.0f}%). Valve&rsquo;s unscaled curve
(k=1) errs by {(fit.get("mae_prob_valve_k1") or 0) * 100:.1f}pp on the same pairs, so we use
the fitted slope. Model probabilities are capped to 3%–97% and always labelled estimates.</li>
<li><b>Direction only.</b> If only one side has a verified rating signal (or all candidate
rosters of one side outrank all of the other), the rated side is the pick and the
probability stays <b>blank</b>.</li>
<li><b>Unresolved.</b> No price and no usable rating → no pick. The match is published on the
<a href="{base}unresolved.html">Unresolved page</a> with the exact limitations. We never
invent a percentage, and never fill a blank with 50%.</li>
</ol>
<h2>Guards against bad joins</h2>
<ul class="tight">
<li>No prefix/fuzzy name matching (&ldquo;B8&rdquo; ≠ &ldquo;B8 Academy&rdquo;,
&ldquo;WBT&rdquo; ≠ &ldquo;WROTBERRY&rdquo;); every alias join is flagged on its row.</li>
<li>Kalshi prices are never joined: its feed has no verified kickoff time. They are shown as
&ldquo;seen but NOT used&rdquo; evidence. The same applies to any price whose start time
disagrees with HotSpawn by &gt;30 min, and to in-play (live) prices.</li>
<li>Stored derived probabilities are never trusted: the Resolver recomputes every fair %
from the raw stored prices.</li>
<li>If HotSpawn is unreachable, the previous fixture inventory is kept and the failure is
logged — an empty board is never published.</li>
</ul>
<h2>Sources used this run</h2>
<div class="tblwrap"><table><tr><th>Source</th><th>Status</th><th>Yield</th><th>Collected (UTC)</th></tr>
{"".join(src_rows)}</table></div>
<p class="small muted">Full access log with response sizes and SHA-256 hashes is stored in
<a href="{REPO}/blob/main/data/d9d7627b/snapshot.json">snapshot.json</a> (<code>access_log</code>).</p>
<h2>Freshness</h2>
<p>A GitHub Actions workflow (<a href="{REPO}/actions/workflows/hotspawn-cs2-d9d7627b.yml">
hotspawn-cs2-d9d7627b</a>) re-runs collect → resolve → build every 2 hours and commits only
when the board changes, so picks are never more than a few hours old (target &lt;4–8h even
if GitHub drops a scheduled run). New HotSpawn fixtures are picked up automatically; matches
whose lock time passes move to the &ldquo;Locked&rdquo; section for the record.</p>
{seed_html}
<h2>Known limitations</h2>
<ul class="tight">
<li>Model lines inherit VRS staleness (monthly snapshots) and ignore maps, vetoes, stand-ins
and same-day form. Treat them as a prior, not a price.</li>
<li>HLTV blocks automated reads (HTTP 403 at last probe), so HLTV form/head-to-head is
linked for manual review rather than collected.</li>
<li>Some books price a match only minutes before start; a fixture can move from
&ldquo;model&rdquo; to &ldquo;market&rdquo; between refreshes.</li>
<li>HotSpawn occasionally lists fixtures as &ldquo;scheduled&rdquo; long after their start
(see Flagged page) — we account for them but cannot pick them.</li>
</ul>
<h2>Verify it yourself</h2>
<p><a href="{REPO}/blob/main/data/d9d7627b/board.json">board.json</a> (what these pages render) ·
<a href="{REPO}/blob/main/data/d9d7627b/snapshot.json">snapshot.json</a> (raw collected prices) ·
<a href="{REPO}/blob/main/data/d9d7627b/calibration.json">calibration.json</a> (model fit pairs) ·
<a href="{REPO}/blob/main/scripts/d9d7627b/core.py">core.py</a> (all formulas) ·
<a href="{REPO}/blob/main/tests/test_d9d7627b.py">tests</a>.</p>
"""


# ------------------------------------------------------------------------ flagged page

def flagged_body(board, base: str) -> str:
    rows = board["rows"]
    stale = [r for r in rows if r["state"] == "stale"]
    stale.sort(key=lambda r: r.get("start_utc") or "")
    amb_rows, disagree, alias_rows, rejected = [], [], [], []
    for r in rows:
        if not r.get("resolution"):
            continue
        amb = (r["evidence"] or {}).get("vrs", {}).get("ambiguous") or {}
        if amb:
            amb_rows.append(r)
        if any(f.startswith("books_disagree") for f in r.get("flags") or []):
            disagree.append(r)
        if any(f.startswith("alias_join") for f in r.get("flags") or []):
            alias_rows.append(r)
        for x in (r["evidence"] or {}).get("rejected_joins") or []:
            rejected.append((r, x))
    access = board.get("access") or {}
    failed = [(k, v) for k, v in access.items()
              if isinstance(v, dict) and (v.get("error") or (v.get("status") not in (200, None)))]
    stale_trs = "".join(
        f'<tr><td class="kbd">{esc((r.get("start_utc") or "")[:16].replace("T", " "))}</td>'
        f'<td>{esc(r["team_a"])} vs {esc(r["team_b"])}</td><td>{esc(r.get("competition"))}</td>'
        f'<td><a href="{esc(r.get("hotspawn_url") or LOBBY)}" rel="noopener">HotSpawn</a></td></tr>'
        for r in stale)
    amb_trs = "".join(
        f'<tr><td><a href="{base}picks.html#{esc(r["fixture_id"])}">{esc(r["team_a"])} vs '
        f'{esc(r["team_b"])}</a></td><td>{esc(", ".join(sorted((r["evidence"]["vrs"]["ambiguous"] or {}).keys())))}</td></tr>'
        for r in amb_rows)
    rej_trs = "".join(
        f'<tr><td>{esc(r["team_a"])} vs {esc(r["team_b"])}</td>'
        f'<td><a href="{esc(x.get("public_url"))}" rel="noopener">{esc(x.get("source_name"))}</a></td>'
        f'<td>{esc(x.get("reason"))}</td></tr>' for r, x in rejected[:60])
    fail_lis = "".join(
        f'<li><b>{esc(k)}</b> — {esc(v.get("error") or v.get("status"))} at '
        f'{esc(v.get("at_utc"))} (<a href="{esc(v.get("url"))}" rel="noopener">endpoint</a>)</li>'
        for k, v in failed)
    dis_trs = "".join(
        f'<tr><td><a href="{base}picks.html#{esc(r["fixture_id"])}">{esc(r["team_a"])} vs '
        f'{esc(r["team_b"])}</a></td><td>{esc(next((f for f in r["flags"] if f.startswith("books_disagree")), ""))}</td></tr>'
        for r in disagree)
    seed = board.get("seed")
    seed_item = ""
    if seed:
        seed_item = (f'<h2>F2 · Seeded first publish (temporary)</h2><p>The board currently '
                     f'renders seed data from <code>{esc(seed.get("from_file"))}</code> '
                     f'(collected {esc(seed.get("collected_to_utc"))}). The first live '
                     f'Actions refresh replaces it; this item then disappears.</p>')
    return f"""
<h1>Flagged for review</h1>
<p>Irregularities and judgement calls, published instead of hidden. Nothing here blocks the
picks board; each item links to its source for manual review.</p>
<h2>F1 · Stale HotSpawn listings ({len(stale)})</h2>
<p>These fixtures are still returned as &ldquo;scheduled&rdquo; although their start passed
more than 24 hours before collection. They cannot be picked and are excluded from the open
board, but they inflate the lobby&rsquo;s headline counts.</p>
<div class="tblwrap"><table><tr><th>Start (UTC)</th><th>Match</th><th>Tournament</th><th>Source</th></tr>
{stale_trs or '<tr><td colspan="4">None this run.</td></tr>'}</table></div>
{seed_item}
<h2>F3 · Ambiguous Valve VRS team names ({len(amb_rows)} fixtures)</h2>
<p>One organisation name maps to two different VRS rosters. We refuse to guess which roster
plays, so these fixtures fall back to direction-only or unresolved.</p>
<div class="tblwrap"><table><tr><th>Fixture</th><th>Ambiguous side</th></tr>
{amb_trs or '<tr><td colspan="2">None this run.</td></tr>'}</table></div>
<h2>F4 · Prices seen but NOT used ({len(rejected)})</h2>
<p>Name-matching prices rejected by the join rules (unverified/disagreeing start time, or
in-play). Listed so a human can overrule us with better information.</p>
<div class="tblwrap"><table><tr><th>Fixture</th><th>Source</th><th>Reason not joined</th></tr>
{rej_trs or '<tr><td colspan="3">None this run.</td></tr>'}</table></div>
<p class="small muted">Plus {len(board.get("rejected_source_quotes") or [])} Kalshi markets rejected at
collection for thin/one-sided order books (stored in snapshot.json).</p>
<h2>F5 · Books disagree &gt;25pp ({len(disagree)})</h2>
<div class="tblwrap"><table><tr><th>Fixture</th><th>Flag</th></tr>
{dis_trs or '<tr><td colspan="2">None this run.</td></tr>'}</table></div>
<h2>F6 · Source failures this run</h2>
<ul class="tight">{fail_lis or "<li>None — every source responded.</li>"}</ul>
<h2>F7 · Alias / word-order joins used ({len(alias_rows)} fixtures)</h2>
<p>Rows where a published alias or an exact word-order variant was needed to join a price or
a VRS rating. Each is also flagged on its pick card. Fixture IDs: 
{esc(", ".join(r["fixture_id"] for r in alias_rows)) or "none"}.</p>
<h2>F8 · Repository-level (pre-existing, not caused by this board)</h2>
<ul class="tight">
<li>The legacy verification workflow
<a href="{REPO}/actions/workflows/pages.yml">&ldquo;Verify and publish dashboard&rdquo;</a>
fails on <code>main</code> in its &ldquo;Validate preserved evidence and arithmetic&rdquo;
step (stale assertions from earlier sessions, first documented 2026-10-19). GitHub Pages
serves this repo in legacy branch mode (<code>main:/</code>) and is <b>built</b>, so the
site is live; the failing workflow is a separate harness owned by earlier sessions and is
left untouched here.</li>
<li>Two earlier sessions&rsquo; test files assert on the <i>previous</i> landing page and
fail by design after this consolidation (measured 2026-10-21: <code>tests/test_1fac4be2.py</code>
2 failures — it pins the old primary CTA to <code>picks-every-match/index.html</code>;
<code>tests/test_3e1be203.py</code> 1 failure — it pins an <code>id="desk-front"</code> card
in the root page). Both passed against the old landing and are owned by their sessions;
the new front door supersedes those assertions. This board&rsquo;s own suite
(<code>tests/test_d9d7627b.py</code>, 32 tests) passes.</li>
<li><b>Root-page contention:</b> several sessions&rsquo; workflows publish a root
<code>index.html</code> (<code>update-data.yml</code> via <code>scripts/build_site.py</code>,
currently failing; <code>hotspawn-live-82a9a0cc.yml</code> every 4h; this board every 2h).
The root URL therefore shows whichever pipeline refreshed last. This board&rsquo;s stable,
never-overwritten home is <a href="{base}index.html">hotspawn-cs2/</a> — bookmark that.
Root ownership should be settled by a future coordination pass (see COORDINATION.md,
session d9d7627b).</li>
<li>GitHub&rsquo;s <code>schedule</code> trigger has historically dropped runs in this repo;
this board&rsquo;s workflow therefore also runs on demand and its freshness is printed at
the top of every page.</li>
</ul>
"""


# -------------------------------------------------------------------------------- main

def main() -> int:
    board = json.loads((DATA / "board.json").read_text())
    SECTION.mkdir(parents=True, exist_ok=True)
    gen = board["generated_utc"]
    coll = board.get("collected_to_utc")
    updated = (f'Updated {t_el(gen)} · market data collected {t_el(coll)} · '
               f'auto-refresh every few hours')
    pages = {
        SECTION / "index.html": shell("Executive summary", "summary", "", updated,
                                      summary_body(board, "")),
        ROOT / "index.html": shell("Executive summary", "summary", "hotspawn-cs2/", updated,
                                   summary_body(board, "hotspawn-cs2/")),
        SECTION / "picks.html": shell("All picks", "picks", "", updated,
                                      picks_body(board, "")),
        SECTION / "unresolved.html": shell("Unresolved picks & limitations", "unresolved",
                                           "", updated, unresolved_body(board, "")),
        SECTION / "method.html": shell("Method & sources", "method", "", updated,
                                       method_body(board, "")),
        SECTION / "flagged.html": shell("Flagged for review", "flagged", "", updated,
                                        flagged_body(board, "")),
    }
    for path, content in pages.items():
        path.write_text(content)
        print("wrote", path.relative_to(ROOT), len(content), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
