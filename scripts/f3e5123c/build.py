#!/usr/bin/env python3
"""Session f3e5123c — render hotspawn-picks/ (mobile-first front door).

Reads ONLY data/f3e5123c/board.json (produced by resolve.py from committed
upstream captures). Every probability row carries its source links; blank is
rendered blank. No network. Run after resolve.py.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "data/f3e5123c/board.json"
OUT = ROOT / "hotspawn-picks"

BASIS_LABEL = {
    "market": ("★ Book line (featured)", "b-market"),
    "esportsbook": ("Book line (fallback)", "b-market"),
    "exchange": ("Exchange (fallback)", "b-exch"),
    "model": ("VRS model (originated)", "b-model"),
    "floor_estimate": ("† Directional floor", "b-floor"),
}

CSS = """
:root{--bg:#0b111c;--card:#141e30;--card2:#18253c;--ink:#eaf1fb;--mut:#9fb2cc;--grn:#38d996;--amb:#ffcf7d;--red:#ff9a9a;--line:#2a3a57;--chip:#1f3050}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.55 system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif;padding-bottom:74px}
a{color:#8fd0ff}main{max-width:1060px;margin:0 auto;padding:14px 14px 30px}
header.top{position:sticky;top:0;z-index:20;background:#0d1626f2;border-bottom:1px solid var(--line);backdrop-filter:blur(6px)}
header.top .in{max-width:1060px;margin:0 auto;padding:10px 14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.logo{font-weight:800;font-size:19px;color:var(--ink);text-decoration:none}.logo b{color:var(--grn)}
nav.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-left:auto}
nav.tabs a{min-height:44px;display:inline-flex;align-items:center;padding:8px 13px;border:1px solid var(--line);border-radius:999px;color:var(--ink);text-decoration:none;font-size:15px;background:var(--card)}
nav.tabs a.on{background:var(--grn);color:#062015;font-weight:700;border-color:var(--grn)}
nav.bottom{position:fixed;left:0;right:0;bottom:0;z-index:30;background:#0d1626f7;border-top:1px solid var(--line);display:none}
nav.bottom a{flex:1;text-align:center;color:var(--ink);text-decoration:none;padding:9px 2px 11px;font-size:13px;min-height:56px}
nav.bottom a.on{color:var(--grn);font-weight:800}
h1{font-size:27px;line-height:1.25;margin:10px 0 8px}h2{font-size:21px;margin:26px 0 10px}h3{font-size:17px;margin:18px 0 8px}
.hero{background:linear-gradient(160deg,#0f2a1e,#122036);border:2px solid var(--grn);border-radius:16px;padding:18px;margin:14px 0}
.cta{display:flex;justify-content:space-between;align-items:center;gap:10px;min-height:56px;background:var(--grn);color:#062015;font-weight:800;font-size:18px;text-decoration:none;border-radius:12px;padding:13px 16px;margin:12px 0 8px}
.cta2{display:flex;justify-content:space-between;align-items:center;gap:10px;min-height:52px;border:1px solid var(--amb);color:var(--amb);font-weight:700;text-decoration:none;border-radius:12px;padding:11px 15px;margin:8px 0;background:#241c0f}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:9px;margin:12px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;text-align:center}
.stat b{display:block;font-size:26px}.stat span{font-size:13px;color:var(--mut)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:10px 0}
.pickline{font-size:19px}.pick{background:#0e3320;border:1px solid var(--grn);color:#a9f5cf;border-radius:999px;padding:3px 12px;font-weight:800;white-space:nowrap}
.vs{color:var(--mut);font-size:14px}.meta{color:var(--mut);font-size:14px}
.bar{display:flex;height:26px;border-radius:8px;overflow:hidden;margin:9px 0 4px;border:1px solid var(--line);font-size:13px;font-weight:700}
.bar .a{background:#1d4d33;color:#c9ffe2;display:flex;align-items:center;padding:0 8px;white-space:nowrap;overflow:hidden}
.bar .b{background:#3a2b14;color:#ffe4b0;display:flex;align-items:center;padding:0 8px;white-space:nowrap;overflow:hidden;justify-content:flex-end}
.chip{display:inline-block;border-radius:999px;padding:2px 10px;font-size:13px;font-weight:700;border:1px solid var(--line);background:var(--chip);margin:2px 3px 2px 0}
.b-market{border-color:var(--grn);color:#a9f5cf}.b-exch{border-color:#7dc4ff;color:#bfe4ff}.b-model{border-color:#b49aff;color:#ddccff}.b-floor{border-color:var(--amb);color:var(--amb)}
.src{font-size:13.5px;color:var(--mut);word-break:break-word}
table{width:100%;border-collapse:collapse;font-size:15px;margin:8px 0 18px}
th,td{border:1px solid var(--line);padding:9px;vertical-align:top;text-align:left}
th{background:var(--card2)}
.warn{background:#2a1d0e;border:1px solid var(--amb);border-radius:12px;padding:12px 14px;margin:12px 0}
.bad{background:#2c1418;border:1px solid var(--red);border-radius:12px;padding:12px 14px;margin:12px 0}
.ok{background:#0e2418;border:1px solid var(--grn);border-radius:12px;padding:12px 14px;margin:12px 0}
.links a{display:flex;justify-content:space-between;gap:8px;min-height:50px;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 14px;margin:8px 0;color:var(--ink);text-decoration:none}
.links a small{color:var(--mut)}
details{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 14px;margin:8px 0}
summary{cursor:pointer;font-weight:700;min-height:44px;display:flex;align-items:center}
code{background:#0a0f18;border:1px solid var(--line);border-radius:6px;padding:1px 6px;font-size:13.5px;word-break:break-all}
.small{font-size:14px;color:var(--mut)}footer{color:var(--mut);font-size:13.5px;margin-top:30px;border-top:1px solid var(--line);padding-top:14px}
@media(max-width:760px){
 body{font-size:16.5px}h1{font-size:24px}nav.tabs{display:none}nav.bottom{display:flex}
 table,thead,tbody,tr,th,td{display:block;width:100%}
 thead{display:none}tr{background:var(--card);border:1px solid var(--line);border-radius:12px;margin:10px 0;padding:6px}
 th,td{border:none;padding:6px 8px}td:before{content:attr(data-h)' ';font-weight:700;color:var(--mut);font-size:12.5px;text-transform:uppercase;letter-spacing:.4px}
 td.noH:before{content:''}.stats{grid-template-columns:1fr 1fr}
}
"""


def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def pct(p) -> str:
    return f"{float(p) * 100:.1f}%" if isinstance(p, (int, float)) else "—"


def tstr(iso) -> str:
    return esc(str(iso or "—").replace("T", " ").replace("Z", " UTC"))


def basis_chip(line) -> str:
    if not line:
        return '<span class="chip b-floor">No verified line — blank</span>'
    lab, cls = BASIS_LABEL.get(line.get("basis"), (line.get("basis"), ""))
    return f'<span class="chip {cls}">{esc(lab)}</span><span class="chip">{esc(line.get("confidence"))}</span>'


def probbar(r) -> str:
    ln = r.get("line")
    if not ln:
        return '<p class="meta">Win %: <strong>— / — (unverified, left blank by rule)</strong></p>'
    pa = float(ln["prob_a"]) * 100
    return (f'<div class="bar" role="img" aria-label="{esc(r["team_a"])} {pa:.1f} percent, {esc(r["team_b"])} {100-pa:.1f} percent">'
            f'<div class="a" style="width:{pa:.1f}%">{esc(r["team_a"])} {pa:.1f}%</div>'
            f'<div class="b" style="width:{100-pa:.1f}%">{100-pa:.1f}% {esc(r["team_b"])}</div></div>')


def source_bits(r) -> str:
    bits = []
    for q in (r.get("quotes") or []):
        bits.append(
            f'{esc(q.get("source_name"))} <code>{esc(q.get("decimal_a"))} / {esc(q.get("decimal_b"))}</code> '
            f'(event {esc(q.get("event_id"))}) <a href="{esc(q.get("public_url"))}">source</a>')
    res = r.get("resolution") or {}
    for side in ("team_a_vrs", "team_b_vrs"):
        v = res.get(side)
        if v:
            bits.append(f'VRS {esc(v.get("team"))} #{esc(v.get("standing"))} ({esc(v.get("points"))} pts) '
                        f'<a href="{esc(v.get("details_url"))}">Valve details</a>')
    ln = r.get("line") or {}
    if ln.get("basis") == "market" and not bits:
        bits.append('Featured consensus quotes: see <a href="sources.html">line-by-line ledger</a>')
    return ('<p class="src">' + " · ".join(bits) + "</p>") if bits else ""


def match_card(r, anchor_prefix="row") -> str:
    ln = r.get("line") or {}
    pick_html = (f'PICK <span class="pick">✓ {esc(ln.get("pick_team"))} {pct(ln.get("pick_prob"))}</span>'
                 if ln else '<span class="pick" style="border-color:var(--amb);color:var(--amb);background:#241c0f">NO PICK — unresolved</span>')
    fair = ""
    if ln:
        fair = (f'<span class="meta">Fair odds {esc(ln.get("fair_decimal_a"))} / {esc(ln.get("fair_decimal_b"))} '
                f'({esc(ln.get("fair_american_a"))} / {esc(ln.get("fair_american_b"))})</span>')
    xc = r.get("crosscheck_fe80") or {}
    xc_html = (f'<p class="src">Cross-check (independent blended board, unfitted slope): P({esc(r["team_a"])}) '
               f'{pct(xc.get("prob_a"))} [{esc(xc.get("basis"))}] — context only, never blended.</p>') if xc else ""
    flags = [f for f in (r.get("flags") or [])]
    flag_html = ('<p class="src">⚠ ' + "; ".join(esc(f) for f in flags) + "</p>") if flags else ""
    note = ln.get("resolution_note") or ""
    note_html = f'<p class="small">{esc(note)}</p>' if note else ""
    return f"""<article class="card" id="{anchor_prefix}-{esc(r['fixture_id'])}">
<p class="meta">#{esc(r['fixture_id'])} · <span data-utc="{esc(r.get('start_utc'))}">{tstr(r.get('start_utc'))}</span> · {esc(r.get('competition'))} · Tier {esc(r.get('tier') or '—')} · lock {tstr(r.get('lock_utc'))}</p>
<p class="pickline"><strong>{esc(r['team_a'])}</strong> <span class="vs">vs</span> <strong>{esc(r['team_b'])}</strong></p>
<p>{pick_html} {basis_chip(r.get('line'))} {fair}</p>
{probbar(r)}
{note_html}{source_bits(r)}{xc_html}{flag_html}
{('<p class="src"><a href="' + esc(r.get('hotspawn_url') or 'https://play.hotspawn.com/lobby') + '">HotSpawn match</a> · <a href="unresolved.html#u-' + esc(r['fixture_id']) + '">research ledger</a> · <a href="sources.html#s-' + esc(r['fixture_id']) + '">sources</a></p>') if r.get('resolution') else ('<p class="src"><a href="' + esc(r.get('hotspawn_url') or 'https://play.hotspawn.com/lobby') + '">HotSpawn match</a> · <a href="sources.html#s-' + esc(r['fixture_id']) + '">sources</a></p>')}
</article>"""


PAGES = [("index.html", "🏠 Summary"), ("picks.html", "📋 All picks"), ("unresolved.html", "🧩 Unresolved"),
         ("tournaments.html", "🏆 By event"), ("sources.html", "🔎 Sources"), ("flagged.html", "🚩 Flagged"),
         ("method.html", "⚙ Method")]


def shell(title, active, body, b) -> str:
    tabs = "".join(f'<a class="{"on" if h == active else ""}" href="{h}">{t}</a>' for h, t in PAGES)
    bottom = "".join(f'<a class="{"on" if h == active else ""}" href="{h}">{t.split(" ",1)[0]}<br>{esc(t.split(" ",1)[1] if " " in t else t)}</a>'
                     for h, t in PAGES[:5])
    s = b["summary"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)} · HotSpawn CS2 Picks — Every Match</title>
<meta name="description" content="A pick and win probability for every open HotSpawn CS2 match, from outside betting lines + official Valve VRS. Mobile-first, refreshed every 4 hours.">
<style>{CSS}</style></head><body>
<header class="top"><div class="in"><a class="logo" href="index.html">🎯 HotSpawn <b>CS2 Picks</b></a><nav class="tabs">{tabs}</nav></div></header>
<main>
<div class="ok" id="freshness"><strong>Snapshot {tstr(b.get('generated_utc'))}</strong> · Week {esc((b.get('week') or {}).get('weekId'))} ·
<strong>{s['with_pick']}/{s['open']} open lobby matches have a pick</strong> ({s['featured_market']} featured book lines · {s['fallback_market']} fallback book/exchange · {s['vrs_model']} VRS-model · {s['floor_directional']}† directional · {s['unresolved']} blank) ·
auto-refresh every 4 hours. <span class="small">If this snapshot is &gt;8h old or a match has locked, treat its line as stale.</span></div>
{body}
<footer>Probabilities come from OUTSIDE betting markets (Pinnacle/Bovada/Melbet/Thunderpick/Kalshi) de-vigged, or — only where no market exists — originated from official Valve VRS points. HotSpawn crowd % is never used as a probability. †Directional floor = rated team vs the last VRS team; a lower bound, not a betting line. Analysis for HotSpawn pick'em only — not betting advice. Times show UTC and convert to your device time. Machine data: <a href="../data/f3e5123c/board.json">data/f3e5123c/board.json</a> · <a href="../index.html">Site home</a></footer>
</main><nav class="bottom">{bottom}</nav>
<script>
document.querySelectorAll('[data-utc]').forEach(function(el){{var d=new Date(el.getAttribute('data-utc'));if(!isNaN(d))el.title='Your time: '+d.toLocaleString();}});
(function(){{var b=document.getElementById('freshness');var d=new Date("{esc(b.get('generated_utc'))}");if(!isNaN(d)&&Date.now()-d.getTime()>8*3600*1000){{b.className='warn';b.innerHTML='⚠ <strong>STALE SNAPSHOT</strong> — captured '+d.toUTCString()+' (&gt;8h ago). Picks/locks may have changed on HotSpawn; verify before picking. '+b.innerHTML;}}}})();
</script></body></html>"""


SITE_DIRECTORY = [
    ("picks.html", "📋 THIS board — every open match pick (start here)", "featured + fallback resolution, updated 4-hourly"),
    ("unresolved.html", "🧩 Unresolved picks & limitations (this board)", "HLTV → books → VRS attempt ledger per low-tier match"),
    ("tournaments.html", "🏆 Same picks grouped by tournament (this board)", "CCT, Circuit X, Stake CQ, DFRAG, Moscow Cyber Games…"),
    ("sources.html", "🔎 Line-by-line sources (this board)", "every quote + Valve rating with a link"),
    ("../board/picks.html", "Expanded canonical board (fe803b80, ~30-min collector)", "blended market+model — see Flagged F3/F4 before use"),
    ("../fullpicks/picks.html", "Fullpicks every-match board (51197e5b, 4h)", "earlier fallback board — see Flagged F1/F2 for two corrected picks"),
    ("../dashboard/picks.html", "Evidence-only desk (cbf92764, 4h)", "strictest blank-if-unverified view"),
    ("../hotspawn-live/picks.html", "Live-lobby board (82a9a0cc)", "alternate same-lobby rendering"),
    ("../ourline/index.html", "Ourline featured board (f7279a54 = this board's featured source)", "primary bookmaker consensus only"),
    ("../fullboard/picks.html", "Fullboard calibrated board (ff88c096)", "preserved parallel session"),
    ("../picks-every-match/picks.html", "Picks-every-match canonical history (c64a5e19)", "preserved parallel session"),
    ("../cs2.html", "Root CS2 table (all fixtures + lines)", "site-wide table view"),
    ("../index.html", "Site home / dashboard", "all categories incl. LoL inventory & research archive"),
]


def build_index(b) -> str:
    s = b["summary"]
    rows = b["open"]
    glance = "".join(
        f'<tr><td data-h="Start" class="noH"><span data-utc="{esc(r.get("start_utc"))}">{tstr(r.get("start_utc"))}</span></td>'
        f'<td data-h="Match"><a href="picks.html#row-{esc(r["fixture_id"])}">{esc(r["team_a"])} vs {esc(r["team_b"])}</a><br><span class="meta">{esc(r.get("competition"))}</span></td>'
        f'<td data-h="Pick">{("<strong>✓ "+esc(r["line"]["pick_team"])+" "+pct(r["line"]["pick_prob"])+"</strong>") if r.get("line") else "— blank"}</td>'
        f'<td data-h="Win %">{(pct(r["line"]["prob_a"])+" / "+pct(r["line"]["prob_b"])) if r.get("line") else "— / —"}</td>'
        f'<td data-h="Basis">{basis_chip(r.get("line"))}</td></tr>'
        for r in rows)
    lowtier = [r for r in rows if (r.get("line") or {}).get("basis") in
               ("exchange", "esportsbook", "model", "floor_estimate") or not r.get("line")]
    low_list = "".join(
        f'<li><a href="unresolved.html#u-{esc(r["fixture_id"])}">{esc(r["team_a"])} vs {esc(r["team_b"])}</a> — '
        f'{esc(BASIS_LABEL.get((r.get("line") or {}).get("basis"), ("blank",))[0])}: '
        f'{esc(((r.get("line") or {}).get("pick_team") or "no pick"))} {pct((r.get("line") or {}).get("pick_prob")) if r.get("line") else ""}</li>'
        for r in lowtier)
    directory = "".join(f'<a href="{h}"><span>{esc(t)}<br><small>{esc(d)}</small></span><span>→</span></a>'
                        for h, t, d in SITE_DIRECTORY)
    body = f"""
<section class="hero" id="executive-summary">
<h1>Executive summary — a pick for EVERY open HotSpawn CS2 match</h1>
<p>Every Counter-Strike 2 match currently open in the <a href="https://play.hotspawn.com/lobby">HotSpawn pick'em lobby</a> is listed below with an outside-market win probability for <strong>both</strong> teams and one obvious pick. Featured bookmaker lines are kept unchanged; low-tier matches with no featured price (the Polymarket-coverage gaps) are resolved by a documented fallback ladder — <strong>HLTV identity check → esportsbooks/exchange lines → official Valve VRS originated line</strong> — and anything that still cannot be priced stays blank in the separate Unresolved section. HotSpawn crowd % is never used as a probability.</p>
<a class="cta" href="picks.html"><span>📋 See EVERY pick ({s['with_pick']}/{s['open']} matches)</span><span>→</span></a>
<a class="cta2" href="unresolved.html"><span>🧩 Unresolved picks &amp; limitations ({s['floor_directional']}† directional · {s['unresolved']} blank · {s['status_conflicts']} status conflicts)</span><span>→</span></a>
<div class="stats">
<div class="stat"><b>{s['open']}</b><span>open lobby matches</span></div>
<div class="stat"><b>{s['with_pick']}</b><span>with pick + both %</span></div>
<div class="stat"><b>{s['featured_market']}</b><span>featured book lines ★</span></div>
<div class="stat"><b>{s['fallback_market']} + {s['vrs_model']} + {s['floor_directional']}†</b><span>fallback: books + VRS-model + directional</span></div>
<div class="stat"><b>{s['unresolved']}</b><span>blank / unresolved</span></div>
<div class="stat"><b>4h</b><span>auto-refresh</span></div>
</div>
<p class="small">Two fallback corrections matter this snapshot — both flip the favourite vs a naive ratings read: <a href="picks.html#row-1082837">Zetta vs LOS NINOS → LOS NINOS</a> (Kalshi market under the Alianza Lima name, 5/5 roster identity) and <a href="picks.html#row-1082882">UNiTY vs Apogee Betclic → Apogee Betclic</a> (it is VRS #45 Betclic; Melbet + Thunderpick lines exist). Details: <a href="flagged.html">Flagged F1–F2</a>.</p>
</section>

<h2>📱 On your phone: where the updated picks live (this site)</h2>
<p>Bookmark <strong>this page</strong>. The newest complete list is always one tap away; older parallel boards are kept below as a labelled archive so there is exactly one recommended starting point.</p>
<div class="links">{directory}</div>

<h2>All {s['open']} open matches at a glance</h2>
<table><thead><tr><th>Start (UTC)</th><th>Match</th><th>Pick</th><th>Win % (A / B)</th><th>Basis</th></tr></thead><tbody>{glance}</tbody></table>
<p class="small">† Directional floor picks (amber) are lower bounds vs the last Valve-rated team — direction only, not a betting line. Tap any match for the full card with sources.</p>

<h2>🧩 Separate section: unresolved-grade picks &amp; limitations (summary)</h2>
<div class="warn"><p><strong>{len(lowtier)} open matches had no featured price</strong> (low-tier CCT/regional or far-future pre-market fixtures). Each was researched HLTV-first, then across esportsbooks/exchanges, then against official Valve VRS. Outcomes:</p>
<ul>{low_list}</ul>
<p><strong>Standing limitations:</strong> (1) unrated regional stacks have no official VRS points, so only a directional floor bound exists; (2) sponsor-name variants (Zetta/Alianza, Apogee/Betclic) hide real markets from naive name joins — resolved here only with 5/5 roster evidence; (3) thin exchange books (29–88¢ spreads, ~$5 Polymarket volume) are listed-but-not-priced and rejected; (4) books post DFRAG/Moscow lines 24–72h out, so model rows auto-upgrade on later refreshes; (5) VRS-model error is roughly ±8–12pp. Full per-match attempt ledgers: <a href="unresolved.html">Unresolved &amp; Limitations →</a></p></div>

<h2>How a pick is made (30-second version)</h2>
<div class="card"><ol>
<li><strong>Featured ★</strong> — de-vigged consensus of primary bookmakers, copied unchanged. Never overwritten by fallback research.</li>
<li><strong>HLTV</strong> — fixture/roster/schedule identity only (no odds feed; bot probe 403 recorded).</li>
<li><strong>Esportsbooks/exchange</strong> — Pinnacle, Bovada, Melbet, Thunderpick, Kalshi quotes joined on both teams + kickoff (±15 min); alias joins only with 5/5 roster evidence.</li>
<li><strong>Valve VRS model</strong> — official points → Glicko curve with market-calibrated slope k={esc(round(float(b['calibration']['k']),4))} (fit on {esc(b['calibration'].get('n_pairs'))} priced pairs).</li>
<li><strong>† Floor / blank</strong> — one team unrated → directional bound; neither priced nor rated → blank, never invented.</li>
</ol><p class="small">Formulas, calibration error, and the HotSpawn reverse-engineering notes: <a href="method.html">Method →</a> · Repository problems found this audit: <a href="flagged.html">Flagged for Review (F1–F8) →</a></p></div>
"""
    return shell("Executive summary", "index.html", body, b)


def build_picks(b) -> str:
    cards = "".join(match_card(r) for r in b["open"])
    sc = "".join(match_card(r, "sc") for r in b["status_conflicts"])
    locked = b.get("locked_recent") or []
    lr_rows = ""
    for r in locked:
        ln = r.get("last_open_line") or r.get("line") or {}
        lr_rows += (f'<tr><td data-h="Start">{tstr(r.get("start_utc"))}</td>'
                    f'<td data-h="Match">{esc(r.get("team_a"))} vs {esc(r.get("team_b"))}<br><span class="meta">{esc(r.get("competition"))}</span></td>'
                    f'<td data-h="Last pick">{esc(ln.get("pick_team") or "—")} {pct(ln.get("pick_prob")) if ln.get("pick_prob") is not None else ""}</td>'
                    f'<td data-h="Winner">{esc(r.get("winner") or "pending/locked")}</td>'
                    f'<td data-h="HotSpawn"><a href="{esc(r.get("hotspawn_url") or "https://play.hotspawn.com/lobby")}">match</a></td></tr>')
    body = f"""<h1>📋 Every open HotSpawn CS2 pick ({b['summary']['with_pick']}/{b['summary']['open']})</h1>
<p>One card per match, soonest first. The green <span class="pick">✓ PICK</span> is the team to select in HotSpawn pick'em; the bar shows both teams' win %. Check the basis chip: ★ featured book line → fallback book/exchange → VRS model → † directional (weakest). Re-check before lock — lines move.</p>
{cards}
<h2 id="status-conflicts">⚠ API-only / status-conflict fixtures ({len(b['status_conflicts'])} — NOT in the playable lobby)</h2>
<p>Present in HotSpawn's API but not pickable in the lobby page (cancelled/started/far-future status). Resolved for tracking only — do not count these in lobby coverage. See Flagged F4.</p>
{sc}
<h2 id="locked">Recently locked (last 24h, {len(locked)})</h2>
<table><thead><tr><th>Start</th><th>Match</th><th>Last open pick</th><th>Winner</th><th>HotSpawn</th></tr></thead><tbody>{lr_rows}</tbody></table>
"""
    return shell("All picks", "picks.html", body, b)


def build_unresolved(b) -> str:
    parts = []
    targets = [r for r in b["open"] if r.get("resolution")] + list(b["status_conflicts"])
    for r in targets:
        res = r.get("resolution") or {}
        steps = "".join(
            f'<tr><td data-h="Step">{esc(a.get("step"))}. {esc(a.get("source"))}</td>'
            f'<td data-h="Result"><strong>{esc(a.get("outcome"))}</strong> — {esc(a.get("status"))}<br><span class="small">{esc(a.get("detail"))}</span></td>'
            f'<td data-h="Link"><a href="{esc(a.get("url"))}">open</a></td></tr>'
            for a in res.get("attempts", []))
        alias_html = ""
        seen_g = set()
        for q in (r.get("quotes") or []):
            for g in (q.get("alias_groups") or []):
                if g["group"] in seen_g:
                    continue
                seen_g.add(g["group"])
                ev = " · ".join(f'<a href="{esc(u)}">evidence</a>' for u in g.get("evidence", []))
                alias_html += f'<div class="ok"><strong>Roster-verified alias: {esc(g.get("display"))}</strong> (verified {esc(g.get("verified_utc"))})<br><span class="small">{esc(g.get("note"))}</span><br><span class="src">{ev}</span></div>'
        lim = "".join(f"<li>{esc(x)}</li>" for x in res.get("Limitations", []))
        ln = r.get("line") or {}
        verdict = (f'Resolved: <strong>✓ {esc(ln.get("pick_team"))} {pct(ln.get("pick_prob"))}</strong> [{esc(ln.get("basis"))}]'
                   if ln else "<strong>UNRESOLVED — probabilities blank by rule.</strong>")
        parts.append(f"""<details open id="u-{esc(r['fixture_id'])}" ><summary>#{esc(r['fixture_id'])} {esc(r['team_a'])} vs {esc(r['team_b'])} — {esc(r.get('competition'))} · {tstr(r.get('start_utc'))}</summary>
<p>{verdict}</p>{alias_html}
<table><thead><tr><th>Research step</th><th>Result</th><th>Source</th></tr></thead><tbody>{steps}</tbody></table>
<p><strong>Limitations for generating this pick:</strong></p><ul>{lim}</ul>
<p class="src">Card: <a href="picks.html#row-{esc(r['fixture_id'])}">picks</a> · Ledger: <a href="sources.html#s-{esc(r['fixture_id'])}">sources</a> · <a href="{esc(r.get('hotspawn_url') or 'https://play.hotspawn.com/lobby')}">HotSpawn</a></p></details>""")
    notes = "".join(f'<div class="card"><h3>{esc(n.get("topic"))} <span class="meta">({esc(n.get("date"))})</span></h3><p class="small">{esc(n.get("finding"))}</p><p class="src">'
                    + " · ".join(f'<a href="{esc(u)}">{esc(u)}</a>' for u in n.get("urls", [])) + "</p></div>"
                    for n in b.get("research_notes", []))
    body = f"""<h1>🧩 Unresolved picks &amp; limitations — fallback research ledger</h1>
<p>This is the separate section for every match that <strong>cannot be resolved the featured way</strong> (low-tier CS, missing Polymarket/book coverage, or far-future pre-market). Featured picks are never touched here. Ladder per match: <strong>1 HLTV → 2 esportsbooks/exchange → 3 official Valve VRS → 4 bo3.gg context</strong>. †Directional rows and blanks are the honest residue: the unrated team's strength is officially unknown.</p>
<div class="warn"><strong>Why low-tier matches lack lines:</strong> Pinnacle/Polymarket list selectively; regional CCT/DFRAG fixtures are often priced only by Melbet/Thunderpick/Kalshi — sometimes under a sponsor name (Alianza Lima, Apogee) — or not until 24–72h before start. 'No line found' always means 'no verified two-way price in captured feeds at snapshot time', never 'match is a formality'.</div>
{''.join(parts)}
<h2>Dated manual research notes (web-verified identities)</h2>
{notes}
<h2>Standing methodological limitations</h2>
<div class="card"><ul>
<li><strong>Unrated teams:</strong> Valve VRS requires counted matches with a stable Core; new stacks (TitanFlow, Off Chops, Staqued, LOS NINOS) have no official points. Floor bounds assume 'no stronger than the weakest rated team' only for direction.</li>
<li><strong>Duplicate VRS names:</strong> the same org appears with old/new Cores (Banda Chuya #165 vs #373; Betclic #45 vs #183). Only the active 5-player Core with the latest counted match (or a roster-verified Core) is used; ambiguous pairs stay blank.</li>
<li><strong>Thin exchanges:</strong> Kalshi books with &gt;10¢ spreads and ~$5-volume Polymarket markets are rejected as prices. A mid-price from a crossed/empty book is not a probability.</li>
<li><strong>Snapshot decay:</strong> odds expire at lock or after ~4–8h. The 4-hourly bot re-runs the whole ladder; model rows upgrade to market rows automatically when books post.</li>
<li><strong>HLTV access:</strong> automated HLTV reads are 403-blocked; HLTV is used via dated manual event/team reads for identity, which do not scale to every future fixture — new sponsor aliases may be missed until flagged.</li>
</ul></div>
"""
    return shell("Unresolved & limitations", "unresolved.html", body, b)


def build_tournaments(b) -> str:
    from collections import defaultdict
    groups = defaultdict(list)
    for r in b["open"] + list(b["status_conflicts"]):
        groups[str(r.get("competition") or "Unknown competition")].append(r)
    secs = ""
    for comp in sorted(groups, key=lambda c: min(str(x.get("start_utc")) for x in groups[c])):
        rows = sorted(groups[comp], key=lambda x: str(x.get("start_utc")))
        cards = "".join(match_card(r) for r in rows)
        secs += f'<h2>{esc(comp)} <span class="meta">({len(rows)} open)</span></h2>{cards}'
    return shell("By tournament", "tournaments.html",
                 f"<h1>🏆 Picks by tournament / category</h1><p>Same every-match board, grouped. Low-tier regional events (CCT Challengers, DFRAG, Moscow Cyber Games) are where fallback/model picks concentrate — see basis chips.</p>{secs}", b)


def build_sources(b) -> str:
    secs = ""
    for r in b["open"] + list(b["status_conflicts"]):
        qrows = ""
        for q in (r.get("quotes") or []):
            qrows += (f'<tr><td data-h="Source">{esc(q.get("source_name"))} (event {esc(q.get("event_id"))})</td>'
                      f'<td data-h="At source">{esc(" vs ".join(str(x) for x in (q.get("names_at_source") or [])))} · raw {esc(q.get("raw_format"))} {esc(q.get("raw_a"))}/{esc(q.get("raw_b"))}</td>'
                      f'<td data-h="Decimal">{esc(q.get("decimal_a"))} / {esc(q.get("decimal_b"))} → no-vig P(A) {pct(q.get("no_vig_prob_team_a"))}</td>'
                      f'<td data-h="When">retrieved {tstr(q.get("retrieved_utc"))} · Δkickoff {esc(q.get("start_diff_h"))}h</td>'
                      f'<td data-h="Link"><a href="{esc(q.get("public_url"))}">official page</a></td></tr>')
        if not qrows:
            qrows = '<tr><td data-h="Quotes" colspan="5">No bookmaker/exchange quote joined this fixture (see Unresolved ledger steps).</td></tr>'
        vrow = ""
        res = r.get("resolution") or {}
        for lbl, key in ((r["team_a"], "team_a_vrs"), (r["team_b"], "team_b_vrs")):
            v = res.get(key)
            if v:
                vrow += (f'<tr><td data-h="Team">{esc(lbl)}</td><td data-h="VRS">#{esc(v.get("standing"))} · {esc(v.get("points"))} pts · {esc(v.get("match_kind"))}</td>'
                         f'<td data-h="Roster">{esc(v.get("roster"))}</td><td data-h="Link"><a href="{esc(v.get("details_url"))}">Valve details</a></td></tr>')
            elif res:
                vrow += f'<tr><td data-h="Team">{esc(lbl)}</td><td data-h="VRS" colspan="3">No official VRS row (unrated/ambiguous) — blank by rule</td></tr>'
        ln = r.get("line") or {}
        secs += f"""<h3 id="s-{esc(r['fixture_id'])}">#{esc(r['fixture_id'])} {esc(r['team_a'])} vs {esc(r['team_b'])} — pick: {esc(ln.get('pick_team') or '—')} {pct(ln.get('pick_prob')) if ln else ''} [{esc(ln.get('basis') or 'blank')}]</h3>
<table><thead><tr><th>Quote source</th><th>Names / raw</th><th>Price → probability</th><th>Retrieved</th><th>Official link</th></tr></thead><tbody>{qrows}</tbody></table>
{('<table><thead><tr><th>Team</th><th>Official Valve VRS</th><th>Counted roster</th><th>Link</th></tr></thead><tbody>'+vrow+'</tbody></table>') if vrow else ''}
<p class="src">Fixture: <a href="{esc(r.get('hotspawn_url') or 'https://play.hotspawn.com/lobby')}">HotSpawn</a> · VRS table: <a href="{esc(b['vrs'].get('page_url'))}">standings_global_{esc(b['vrs'].get('snapshot'))}</a></p>"""
    acc = b.get("access") or {}
    accrows = "".join(f'<tr><td data-h="Probe">{esc(k)}</td><td data-h="HTTP">{esc(v.get("status"))}</td>'
                      f'<td data-h="At">{tstr(v.get("at_utc"))}</td><td data-h="URL"><a href="{esc(v.get("url"))}">{esc(v.get("url"))}</a></td></tr>'
                      for k, v in acc.items() if isinstance(v, dict))
    body = f"""<h1>🔎 Sources — line-by-line evidence ledger</h1>
<p>Every probability on this board re-derives from the rows below: raw bookmaker/exchange prices (de-vigged proportionally) or official Valve VRS points (calibrated Glicko). No row uses HotSpawn percentages. Featured rows reproduce the f7279a54 consensus quotes exactly (see board JSON quotes).</p>
<h2>Upstream probe health (this snapshot)</h2>
<table><thead><tr><th>Probe</th><th>HTTP</th><th>At (UTC)</th><th>URL</th></tr></thead><tbody>{accrows}</tbody></table>
{secs}
"""
    return shell("Sources", "sources.html", body, b)


def build_flagged(b) -> str:
    cards = ""
    for f in b.get("irregularities", []):
        urls = " · ".join(f'<a href="{esc(u)}">{esc(u)}</a>' for u in f.get("urls", []))
        cards += (f'<div class="card"><h3>{esc(f.get("id"))} — {esc(f.get("title"))}</h3>'
                  f'<p><span class="chip b-floor">{esc(f.get("severity"))}</span></p>'
                  f'<p class="small">{esc(f.get("detail"))}</p><p class="src">{urls}</p></div>')
    rowflags = ""
    for r in b["open"] + list(b["status_conflicts"]):
        fl = r.get("flags") or []
        if fl:
            rowflags += (f'<tr><td data-h="Match"><a href="picks.html#row-{esc(r["fixture_id"])}">{esc(r["team_a"])} vs {esc(r["team_b"])}</a></td>'
                         f'<td data-h="Flags">{esc("; ".join(str(x) for x in fl))}</td></tr>')
    body = f"""<h1>🚩 Flagged for Review — repository &amp; match irregularities</h1>
<p>Nothing here blocks publication; everything here needs a human glance. Flags never change a probability silently — the stated rule outcome is published and the doubt is published next to it.</p>
{cards}
<h2>Per-fixture flags carried on this snapshot</h2>
<table><thead><tr><th>Match</th><th>Flags</th></tr></thead><tbody>{rowflags or '<tr><td colspan="2">None</td></tr>'}</tbody></table>
<p class="small">Preserved historical audits: <a href="../flagged.html">root Flagged page</a> · <a href="../fullpicks/flagged.html">fullpicks R1–R7</a> · <a href="../board/flagged.html">expanded board flags</a>. This session adds F1–F8 only; other sessions' flags are unchanged.</p>
"""
    return shell("Flagged for Review", "flagged.html", body, b)


def build_method(b) -> str:
    c = b["calibration"]
    body = f"""<h1>⚙ Method — reverse engineering, formulas &amp; 4-hour refresh</h1>
<h2>1. What 'every match on HotSpawn' means</h2>
<div class="card"><p>The playable inventory is the CS2 fixtures rendered in <a href="https://play.hotspawn.com/lobby">play.hotspawn.com/lobby</a> single-page app, whose data comes from its public fixtures API (upstream collectors record both the lobby transfer-state and a 12,016-row API pull; CS2 rows filtered by <code>sportAlias=cs2</code> + current week). A match counts as <strong>open</strong> only if <code>seen_in</code> includes <code>lobby_page</code> and its lock is in the future. API-only rows (cancelled/started ghosts) go to Status Conflicts — see F4. This snapshot: week {esc((b.get('week') or {}).get('weekId'))}, {esc(b['summary']['open'])} open.</p></div>
<h2>2. Resolution ladder (featured first; fallback ONLY for gaps)</h2>
<div class="card"><ol>
<li><strong>Featured consensus (unchanged):</strong> Pinnacle (×2 weight)/Bovada/Melbet/Kalshi two-way match-winner prices, de-vigged, kickoff-verified. Copied byte-for-byte from <code>data/f7279a54/board.json</code>.</li>
<li><strong>HLTV:</strong> identity/schedule/roster confirmation. No odds feed exists; 403 bot outcome is logged, dated manual reads are cited.</li>
<li><strong>Fallback books/exchange:</strong> all captured quotes from both upstream snapshots (this run: {esc(b['summary'].get('quotes_scanned'))} usable) re-joined with roster-verified alias groups only. Sponsor aliases require identical 5 starters on an official/registry page.</li>
<li><strong>Valve VRS model:</strong> official <a href="{esc(b['vrs'].get('page_url'))}">standings {esc(b['vrs'].get('snapshot'))}</a> ({esc(b['vrs'].get('n_teams'))} teams). <code>P(A)=1/(1+exp(-k·C·(ptsA-ptsB)))</code>, C from Valve's Glicko (RD 75).</li>
<li><strong>† Floor / blank:</strong> as defined on the Unresolved page.</li></ol></div>
<h2>3. No-vig + calibration numbers</h2>
<div class="card"><p>Two-way de-vig (proportional): <code>pA=(1/oddsA)/((1/oddsA)+(1/oddsB))</code>; books with implied sum outside 0.94–1.30 are rejected. Kalshi: yes-mid $ → decimal 1/mid, books &gt;10¢ spread rejected upstream.</p>
<p>Calibrated slope <strong>k = {esc(round(float(c['k']), 4))}</strong> (least-squares vs bookmaker probabilities, n={esc(c.get('n_pairs'))} pairs, MAE {esc(round(float(c.get('mae_prob') or 0)*100,1))}pp; unfitted Valve slope MAE {esc(round(float(c.get('mae_prob_valve_unfitted') or 0)*100,1))}pp — source: {esc(c.get('source'))}). Read model % as ±8–12pp. Fair odds = 1/p; American odds are display conversions of the same p.</p></div>
<h2>4. Refresh architecture (every 4–8 hours, zero manual input)</h2>
<div class="card"><p>Upstream Actions bots re-capture HotSpawn + books + VRS on their own schedules (~30 min–4h). This board's workflow <code>.github/workflows/hotspawn-picks-f3e5123c.yml</code> runs every 4 hours and after upstream board workflows: <code>resolve.py → build.py → contract tests → commit board+site (own scope only, pull --rebase, never force-push)</code>. GitHub Pages then republishes. A snapshot older than 8h shows a red stale banner in your browser; locked matches roll off automatically because the lobby set is rebuilt each run.</p>
<p class="small">Reproduce locally: <code>python3 scripts/f3e5123c/resolve.py &amp;&amp; python3 scripts/f3e5123c/build.py &amp;&amp; python3 -m unittest tests.test_f3e5123c -v</code></p></div>
<h2>5. Hard rules</h2>
<div class="card"><ul><li>HotSpawn crowd % never enters any probability (not collected into this board at all).</li><li>Unverified = blank + flagged; secondary aggregator numbers are leads, never prices.</li><li>Featured lines are immutable here; disagreement is displayed as a cross-check, never blended.</li><li>Every rendered row links its official sources (book/exchange page, Valve details file, HotSpawn match).</li></ul></div>
"""
    return shell("Method", "method.html", body, b)


def main() -> int:
    b = json.loads(BOARD.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    pages = {
        "index.html": build_index(b),
        "picks.html": build_picks(b),
        "unresolved.html": build_unresolved(b),
        "tournaments.html": build_tournaments(b),
        "sources.html": build_sources(b),
        "flagged.html": build_flagged(b),
        "method.html": build_method(b),
    }
    for name, doc in pages.items():
        (OUT / name).write_text(doc, encoding="utf-8")
        print(f"wrote hotspawn-picks/{name} ({len(doc)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
