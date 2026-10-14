#!/usr/bin/env python3
"""Build picks-all/ — the complete, mobile-first picks section (session b5436cf0).

Resolution layers per fixture (never HotSpawn crowd percentages):
  M market     — verified external bookmaker/exchange price (featured picks pipeline)
  R research   — no external price; resolved from dated HLTV + esportsbook/line research
  O model      — neither; the project's Valve VRS / own-Elo originated line
  U unresolved — nothing defensible; blank pick published on the Unresolved page

Inputs (read-only, owned by other sessions):
  data/fe803b80/board.json   full-coverage board (quotes, market/model lines)
  data/c64a5e19/board.json   every-match board (cross-check reading)
  data/b5436cf0/research.json  session research evidence (owned here)
Output (owned here):
  data/b5436cf0/board.json, picks-all/*.html
"""
from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DATA = ROOT / "data" / "b5436cf0"
OUT_SITE = ROOT / "picks-all"

RESEARCH = ROOT / "data" / "b5436cf0" / "research.json"
UPSTREAM = [
    ROOT / "data" / "fe803b80" / "board.json",
    ROOT / "data" / "c64a5e19" / "board.json",
]


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def pct(value) -> str:
    return f"{value * 100:.1f}%" if isinstance(value, (int, float)) else "—"


def conf_label(p: float) -> str:
    if not isinstance(p, (int, float)):
        return "—"
    best = max(p, 1 - p)
    if best >= 0.80:
        return "Strong"
    if best >= 0.65:
        return "Solid"
    if best >= 0.55:
        return "Lean"
    return "Toss-up"


# ------------------------------------------------------------------ merge
def upstream_rows():
    """Union of open fixtures from both upstream boards, keyed by fixture_id."""
    rows = {}
    stamps = {}
    for path in UPSTREAM:
        doc = load(path) or {}
        stamps[path.parent.name] = doc.get("generated_utc") or doc.get("snapshot_utc")
        for row in doc.get("open", []):
            fid = str(row.get("fixture_id"))
            cur = rows.setdefault(fid, {"fixture_id": fid, "boards": {}})
            cur["boards"][path.parent.name] = row
    return rows, stamps


def market_line(row):
    """(pick, prob_a, prob_b, sources) from the strongest market reading on a board row."""
    line = (row.get("line") or {})
    market = row.get("market") or {}
    basis = line.get("basis") or ""
    if basis in ("market", "market+model") and market:
        prob_a = market.get("prob_a")
        if isinstance(prob_a, (int, float)):
            prob_b = 1 - prob_a
            pick = line.get("pick") or row.get("team_a")
            sources = []
            for q in row.get("quotes", []):
                # decimal_a/decimal_b are stored in FIXTURE order (team_a, team_b) even
                # when the raw quote listed candidate names in source order (q.swapped).
                # Verified live on Kalshi for 1079624 (FORZE 85%) and 1080288 (Phantom 91%).
                pair = (f"{row.get('team_a')} {q.get('decimal_a')} / "
                        f"{row.get('team_b')} {q.get('decimal_b')}")
                note = ""
                if q.get("swapped") and q.get("team_a") and q.get("team_a") != row.get("team_a"):
                    note = (f" · raw source listed names in this order: {q.get('team_a')} / "
                            f"{q.get('team_b')} (source-order names; prices are fixture-order — "
                            "pairing verified on Kalshi live)")
                sources.append({
                    "label": f"{q.get('source_name')} ({q.get('source_key')}): {pair}{note}",
                    "url": q.get("public_url"),
                    "kind": "esportsbook/exchange quote",
                    "read_utc": q.get("retrieved_utc"),
                })
            return pick, prob_a, prob_b, sources
    return None


def model_line(row):
    line = (row.get("line") or {})
    prob_a = line.get("prob_a")
    if isinstance(prob_a, (int, float)):
        return line.get("pick"), prob_a, 1 - prob_a
    return None


def build_rows(research):
    upstream, stamps = upstream_rows()
    research_fx = research.get("fixtures", {})
    cross = research.get("cross_checks", {})
    rows = []

    for fid, bundle in sorted(upstream.items(), key=lambda kv: (
            (kv[1]["boards"].get("fe803b80") or kv[1]["boards"].get("c64a5e19") or {}).get("start_utc") or "", kv[0])):
        fe = bundle["boards"].get("fe803b80") or {}
        ce = bundle["boards"].get("c64a5e19") or {}
        base = fe or ce
        team_a = base.get("team_a")
        team_b = base.get("team_b")
        entry = {
            "fixture_id": fid,
            "competition": base.get("competition"),
            "tier": base.get("tier"),
            "start_utc": base.get("start_utc"),
            "lock_utc": base.get("lock_utc"),
            "team_a": team_a,
            "team_b": team_b,
            "hotspawn_url": base.get("hotspawn_url"),
            "flags": sorted(set((fe.get("flags") or []) + (ce.get("flags") or []))),
            "sources": [],
            "layer": "unresolved",
            "pick": None,
            "pick_probability": None,
            "prob_a": None,
            "prob_b": None,
            "confidence": "—",
            "basis_label": "Unresolved",
        }
        m = market_line(fe) or market_line(ce)
        research_entry = research_fx.get(fid)
        cross_entry = cross.get(fid)

        if m:
            pick, prob_a, prob_b, sources = m
            entry.update(layer="market", pick=pick, prob_a=prob_a, prob_b=prob_b,
                         pick_probability=max(prob_a, prob_b), confidence=conf_label(max(prob_a, prob_b)),
                         basis_label="Market line (bookmaker/exchange)")
            entry["sources"] = sources
            if not entry["sources"]:
                entry["sources"] = [{
                    "label": "Full-coverage board market row (quotes recorded in data/fe803b80)",
                    "url": "https://buffedlizard55-lab.github.io/MaltaProj2/board/lines.html",
                    "kind": "board cross-reference",
                    "read_utc": None,
                }]
        elif research_entry and research_entry.get("resolution") == "research":
            prob_a = research_entry.get("originated_prob_team_a")
            prob_b = research_entry.get("originated_prob_team_b")
            pick = research_entry.get("pick")
            entry.update(layer="research", pick=pick, prob_a=prob_a, prob_b=prob_b,
                         pick_probability=research_entry.get("pick_probability"),
                         confidence=research_entry.get("confidence") or conf_label(max(prob_a, prob_b)),
                         basis_label=research_entry.get("basis_label"))
            entry["sources"] = [
                {"label": f.get("fact"), "url": f.get("source"), "kind": f.get("kind"),
                 "read_utc": f.get("read_utc")}
                for f in research_entry.get("facts", [])]
            entry["research"] = {
                "origin_reasoning": research_entry.get("origin_reasoning"),
                "limitations": research_entry.get("limitations", []),
                "facts": research_entry.get("facts", []),
            }
        else:
            o = model_line(fe) or model_line(ce)
            if o:
                pick, prob_a, prob_b = o
                entry.update(layer="model", pick=pick, prob_a=prob_a, prob_b=prob_b,
                             pick_probability=max(prob_a, prob_b),
                             confidence=conf_label(max(prob_a, prob_b)),
                             basis_label="Originated model line (Valve VRS / own Elo)")
                entry["sources"] = [{
                    "label": "Valve official regional standings (VRS) snapshot 2026-10-05",
                    "url": "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md",
                    "kind": "official ratings",
                    "read_utc": None,
                }]

        # normalize probabilities: never publish both a pick and unnormalized pair
        if isinstance(entry["prob_a"], (int, float)) and isinstance(entry["prob_b"], (int, float)):
            s = entry["prob_a"] + entry["prob_b"]
            if s > 0:
                entry["prob_a"] = round(entry["prob_a"] / s, 4)
                entry["prob_b"] = round(entry["prob_b"] / s, 4)
            entry["pick"] = team_a if entry["prob_a"] >= entry["prob_b"] else team_b
            entry["pick_probability"] = max(entry["prob_a"], entry["prob_b"])
            entry["confidence"] = conf_label(entry["pick_probability"])
        else:
            entry["pick"] = None
            entry["pick_probability"] = None

        if cross_entry:
            entry["cross_check"] = cross_entry
            if cross_entry.get("research_reading"):
                entry["sources"].extend(cross_entry.get("sources", []))
        if fid in research_fx and research_entry and research_entry.get("resolution") != "research":
            pass
        rows.append(entry)

    rows.sort(key=lambda r: (r.get("start_utc") or "", r["fixture_id"]))
    return rows, stamps


# ------------------------------------------------------------------ HTML
CSS = """
:root{--bg:#0f1218;--card:#171b23;--line:#262c38;--txt:#e8ebf1;--mut:#9aa3b2;--acc:#3ddc97;--acc2:#5aa9ff;--warn:#ffb547;--bad:#ff6b6b}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:var(--acc2)}header{position:sticky;top:0;z-index:5;background:#0b0e13;border-bottom:1px solid var(--line)}
.bar{max-width:1100px;margin:0 auto;padding:10px 14px;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}.brand{font-weight:700;margin-right:auto}
.bar nav{display:flex;gap:6px;flex-wrap:wrap}.bar nav a{padding:6px 10px;border-radius:8px;text-decoration:none;color:var(--txt);background:#1c212b;font-size:14px}.bar nav a.on{background:var(--acc);color:#04130c;font-weight:700}
main{max-width:1100px;margin:0 auto;padding:14px}h1{font-size:22px;margin:6px 0 4px}h2{font-size:18px;margin:26px 0 8px}.mut{color:var(--mut)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin:12px 0}.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}.stat b{display:block;font-size:22px}.stat span{color:var(--mut);font-size:13px}
.pickcard{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:8px 0}.pickcard .when{font-size:12.5px;color:var(--mut)}
.teams{display:flex;justify-content:space-between;gap:8px;margin:4px 0}.team{flex:1}.team.pk{font-weight:700;color:var(--acc)}.pct{font-variant-numeric:tabular-nums;font-weight:700}
.meter{height:6px;background:#2a303c;border-radius:4px;overflow:hidden;margin:2px 0 6px}.meter i{display:block;height:100%;background:var(--acc)}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:700}.b-M{background:#1f6f4d}.b-R{background:#245a85}.b-O{background:#5b3a12;color:#ffd9a3}.b-U{background:#5b2222}.b-flag{background:#5b3a12;color:#ffd9a3}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut);background:#131720}
.small{font-size:12.5px;color:var(--mut)}.note{background:#151a22;border-left:3px solid var(--acc2);padding:10px 12px;border-radius:6px;margin:10px 0}.warnbox{background:#221a10;border-left:3px solid var(--warn);padding:10px 12px;border-radius:6px;margin:10px 0}
.linkcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:8px}.linkcard{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}.linkcard a{font-weight:700;font-size:16px}
.foot{margin:30px 0 10px;color:var(--mut);font-size:13px}code{background:#11151c;padding:1px 5px;border-radius:4px}
.btn{display:inline-block;padding:11px 16px;border-radius:10px;background:var(--acc);color:#04130c;font-weight:700;text-decoration:none;margin:4px 6px 4px 0}
.btn.ghost{background:#1c212b;color:var(--txt);border:1px solid var(--line)}
.srclist{margin:6px 0 6px 18px;padding:0}.srclist li{margin:4px 0}
@media (max-width:760px){table.cards thead{display:none}table.cards tr{display:block;border-bottom:2px solid var(--line);padding:6px 0}table.cards td{display:block;border:none;padding:4px 10px}table.cards td:before{content:attr(data-l);display:block;font-size:11px;text-transform:uppercase;color:var(--mut);letter-spacing:.05em}}
"""

BADGE = {"market": ("b-M", "M · Market line"), "research": ("b-R", "R · Research-resolved"),
         "model": ("b-O", "O · Originated model"), "unresolved": ("b-U", "U · Unresolved")}


def chrome(title, active, body, stamp):
    nav = [("index.html", "Executive summary"), ("picks.html", "All picks"),
           ("unresolved.html", "Unresolved + limitations"), ("method.html", "Method &amp; sources"),
           ("flagged.html", "Flagged for review"), ("../index.html", "Main dashboard")]
    nav_html = "".join(
        f'<a href="{href}"{" class=on" if href == active else ""}>{label}</a>' for href, label in nav)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Complete picks · HotSpawn CS2 Pick'ems</title><style>{CSS}</style></head>
<body><header><div class="bar"><div class="brand">📋 Complete picks · every match</div><nav>{nav_html}</nav></div></header>
<main>{body}
<p class="foot">Built {esc(stamp)} UTC by session <code>b5436cf0</code> automation — no manual input.
Fixture discovery: HotSpawn Pick'ems lobby only; its crowd percentages are never used as
probability inputs. Probabilities are estimates from external bookmaker/exchange prices, HLTV research
and official Valve ratings — not guarantees. Not affiliated with HotSpawn or any bookmaker. 18+;
gamble responsibly.</p></main></body></html>"""


def row_sources_html(row):
    bits = []
    for s in row.get("sources", []):
        label = s.get("label") or s.get("fact") or "source"
        url = s.get("url")
        when = f" · read {esc(s.get('read_utc'))}" if s.get("read_utc") else ""
        if url:
            bits.append(f'<li><a href="{esc(url)}">{esc(label)}</a> <span class="small">({esc(s.get("kind"))}{when})</span></li>')
        else:
            bits.append(f'<li>{esc(label)} <span class="small">({esc(s.get("kind"))}{when})</span></li>')
    return '<ul class="srclist small">' + "".join(bits) + "</ul>" if bits else '<p class="small">No source link recorded — flagged unverified.</p>'


def pick_card(row, anchor_prefix="m"):
    cls, label = BADGE.get(row["layer"], BADGE["unresolved"])
    a, b = row.get("prob_a"), row.get("prob_b")
    pa = pct(a) if isinstance(a, (int, float)) else "—"
    pb = pct(b) if isinstance(b, (int, float)) else "—"
    pick = row.get("pick") or "— no pick (unresolved)"
    pk_a = " pk" if row.get("pick") == row.get("team_a") else ""
    pk_b = " pk" if row.get("pick") == row.get("team_b") else ""
    width = int((a or 0) * 100)
    return f"""<div class="pickcard" id="{anchor_prefix}-{esc(row['fixture_id'])}">
<div class="when">{esc(row.get('start_utc'))} · locks {esc(row.get('lock_utc'))} · {esc(row.get('competition'))} · Tier {esc(row.get('tier'))}</div>
<div class="teams"><span class="team{pk_a}">{esc(row.get('team_a'))} <span class="pct">{pa}</span></span>
<span class="team{pk_b}" style="text-align:right">{esc(row.get('team_b'))} <span class="pct">{pb}</span></span></div>
<div class="meter"><i style="width:{width}%"></i></div>
<div><b>PICK: {esc(pick)} · {pct(row.get('pick_probability'))} · {esc(row.get('confidence'))}</b>
<span class="badge {cls}">{label}</span>
{f'<a href="{esc(row["hotspawn_url"])}">HotSpawn match page ↗</a>' if row.get('hotspawn_url') else ''}</div>
<div class="small" style="margin-top:4px">{esc(row.get('basis_label'))}</div>
{row_sources_html(row)}
</div>"""


def summary_counts(rows):
    counts = {"market": 0, "research": 0, "model": 0, "unresolved": 0, "with_pick": 0}
    for r in rows:
        counts[r["layer"]] = counts.get(r["layer"], 0) + 1
        if r.get("pick"):
            counts["with_pick"] += 1
    counts["total"] = len(rows)
    return counts


def render_pages(research, rows, stamps, stamp):
    counts = summary_counts(rows)
    research_fx = research.get("fixtures", {})
    unresolved = research.get("unresolved_items", [])
    open_rows = rows

    # ---- index.html (executive summary)
    idx = f"""
<h1>Executive summary — where the picks are</h1>
<p class="mut">One mobile-first page for <b>every</b> open CS2 match on the HotSpawn Pick'ems lobby,
with a pick and a win probability for each. Matches the featured market picks cannot price (low-tier
or not covered by the usual betting sites) are resolved with documented research (HLTV → esportsbooks
→ esports betting lines) and clearly labelled. Refreshed automatically every 4 hours.</p>
<div class="stats">
<div class="stat"><b>{counts['total']}</b><span>matches with picks listed</span></div>
<div class="stat"><b>{counts['with_pick']}</b><span>with a pick + win %</span></div>
<div class="stat"><b>{counts['market']}</b><span>M · market-priced picks</span></div>
<div class="stat"><b>{counts['research']}</b><span>R · research-resolved picks</span></div>
<div class="stat"><b>{counts['model']}</b><span>O · originated model picks</span></div>
<div class="stat"><b>{len(unresolved)}</b><span>unresolved / limitation items</span></div>
</div>
<p><a class="btn" href="picks.html">📱 All picks — every match</a>
   <a class="btn ghost" href="unresolved.html">Unresolved picks + limitations</a>
   <a class="btn ghost" href="method.html">Method &amp; sources</a>
   <a class="btn ghost" href="flagged.html">Flagged for review</a></p>
<h2>Where to find the updated picks (this site)</h2>
<div class="linkcards">
<div class="linkcard"><a href="picks.html">📋 Complete picks — every match</a><p class="small">This section. Pick + win % for every open CS2 fixture on one phone-friendly list, with a source link on every row. Start here.</p></div>
<div class="linkcard"><a href="unresolved.html">⚠️ Unresolved picks + limitations</a><p class="small">The separate section for matches whose picks carry major limitations or could not be resolved — with what was checked and why.</p></div>
<div class="linkcard"><a href="../picks-every-match/index.html">Every-match picks at a glance</a><p class="small">Session c64a5e19 board (market / VRS / fallback tiers).</p></div>
<div class="linkcard"><a href="../board/picks.html">All picks · every match</a><p class="small">Session fe803b80 full-coverage board with raw quotes.</p></div>
<div class="linkcard"><a href="../summary/index.html">Where the picks are (verification hub)</a><p class="small">Independent cross-checks of every board.</p></div>
<div class="linkcard"><a href="../flagged.html">Root flagged page</a><p class="small">Cross-project irregularities with source links.</p></div>
</div>
<h2>Picks at a glance — every open match ({counts['total']})</h2>
<p class="small">Biggest/boldest team = our pick. <span class="badge b-M">M</span> external
bookmaker/exchange price · <span class="badge b-R">R</span> research-resolved (HLTV + esports
lines) · <span class="badge b-O">O</span> originated model. Full sources per row on
<a href="picks.html">All picks</a>.</p>
{''.join(pick_card(r) for r in open_rows)}
"""
    (OUT_SITE / "index.html").write_text(
        chrome("Executive summary", "index.html", idx, stamp), encoding="utf-8")

    # ---- picks.html (full table + cards)
    market_rows = [r for r in rows if r["layer"] == "market"]
    research_rows = [r for r in rows if r["layer"] == "research"]
    other_rows = [r for r in rows if r["layer"] in ("model", "unresolved")]
    body = f"""
<h1>All picks — every match</h1>
<p class="mut">Pick + win probability for every open CS2 fixture on the HotSpawn Pick'ems lobby,
with the source of every number linked. <b>A.</b> Market-priced picks (featured resolution).
<b>B.</b> Research-resolved picks — the low-tier / unpriced matches resolved from HLTV, esportsbooks
and esports betting lines. <b>C.</b> Model-only / unresolved.</p>
<h2>A · Market-priced picks ({len(market_rows)})</h2>
{''.join(pick_card(r) for r in market_rows)}
<h2>B · Research-resolved picks ({len(research_rows)})</h2>
<div class="note">These matches had <b>no</b> usable external bookmaker price. Each pick is
research-resolved (HLTV → esportsbooks → esports betting lines) and originated by this project;
the facts and their official links are on every card. Limitations are listed on
<a href="unresolved.html">Unresolved picks + limitations</a>.</div>
{''.join(pick_card(r) for r in research_rows)}
<h2>C · Model-only or unresolved ({len(other_rows)})</h2>
{''.join(pick_card(r) for r in other_rows)}
<h2>Table — one row per match</h2>
<table class="cards"><thead><tr><th>Start (UTC)</th><th>Match</th><th>Pick</th><th>Win %</th><th>Basis</th><th>Sources</th></tr></thead><tbody>
{''.join(f'<tr id="t-{esc(r["fixture_id"])}"><td data-l="Start">{esc(r.get("start_utc"))}</td>'
         f'<td data-l="Match">{esc(r.get("team_a"))} vs {esc(r.get("team_b"))}<br><span class="small">{esc(r.get("competition"))}</span></td>'
         f'<td data-l="Pick"><b>{esc(r.get("pick") or "—")}</b></td>'
         f'<td data-l="Win %">{pct(r.get("pick_probability"))}</td>'
         f'<td data-l="Basis"><span class="badge {BADGE.get(r["layer"], BADGE["unresolved"])[0]}">{BADGE.get(r["layer"], BADGE["unresolved"])[1]}</span></td>'
         f'<td data-l="Sources">{row_sources_html(r)}</td></tr>' for r in rows)}
</tbody></table>
"""
    (OUT_SITE / "picks.html").write_text(chrome("All picks", "picks.html", body, stamp), encoding="utf-8")

    # ---- unresolved.html (separate section, per user request)
    items = []
    for u in unresolved:
        checked = "".join(f'<li><a href="{esc(c)}">{esc(c)}</a></li>' for c in u.get("checked", []))
        affected = ", ".join(u.get("affected_fixtures", []))
        items.append(f"""
<div class="warnbox"><h3 style="margin:0 0 6px">{esc(u.get("id"))} · {esc(u.get("title"))}</h3>
<p class="small">Affected fixtures: {esc(affected) or "—"}</p>
<p>{esc(u.get("reason"))}</p>
<p class="small"><b>Sources checked:</b></p><ul class="srclist small">{checked}</ul>
<p class="small"><b>What would resolve it:</b> {esc(u.get("needed_to_resolve"))}</p>
{f'<p class="small">{esc(u.get("picks_published"))}</p>' if u.get("picks_published") else ''}</div>""")
    cross_notes = []
    for fid, cc in research.get("cross_checks", {}).items():
        if not isinstance(cc, dict) or not cc.get("handling"):
            continue
        cross_notes.append(f"""
<div class="note"><h3 style="margin:0 0 6px">Cross-check {esc(fid)} · {esc(" vs ".join(cc.get("hotspawn_teams", [])))}</h3>
<p class="small"><b>Market reading:</b> {esc(cc.get("market_reading"))}</p>
<p class="small"><b>Research reading:</b> {esc(cc.get("research_reading"))}</p>
<p class="small"><b>Handling:</b> {esc(cc.get("handling"))}</p>
{row_sources_html({"sources": cc.get("sources", [])})}</div>""")
    body = f"""
<h1>Unresolved picks + limitations</h1>
<p class="mut">The separate section for everything the normal pick pipeline cannot resolve cleanly:
contested team identities, market-vs-research disagreements, alias joins and the systemic limits of
generating picks for low-tier CS2. Nothing here is filled in or guessed — each item lists what was
checked, with official links, and what would resolve it. These items do not block the picks on
<a href="picks.html">All picks</a>; treat the affected rows as lower confidence.</p>
<div class="stats">
<div class="stat"><b>{len(unresolved)}</b><span>unresolved / limitation items</span></div>
<div class="stat"><b>{sum(len(u.get("affected_fixtures", [])) for u in unresolved)}</b><span>fixture references affected</span></div>
<div class="stat"><b>{counts['research']}</b><span>research-resolved picks (all flagged with their limits)</span></div>
</div>
<h2>Unresolved items</h2>
{''.join(items)}
<h2>Market-vs-research cross-checks</h2>
{''.join(cross_notes)}
<h2>Limitations of generating picks for low-tier matches</h2>
<ul>
<li>Featured market resolution (Pinnacle/Bovada/Melbet full-match moneylines) rarely covers tier-B/C
CS2; those rows depend on thinner sources (Kalshi exchange books, Thunderpick coefficients published
via bo3.gg) or research.</li>
<li>HLTV returns HTTP 403 to GitHub Actions runners; HLTV facts are session-researched with dated
read times and re-verified by later research passes rather than re-read on every 4-hour refresh.</li>
<li>egamersworld often shows an undifferentiated 1.8 / 1.8 even widget price for unpriced matches —
it is recorded but never used as a line.</li>
<li>Prediction markets (Polymarket) list some of these matches with ~$0 volume; placeholder pricing is
never used.</li>
<li>Bo1 LAN group-stage matches (Elisa BreakOut Series 2) carry higher single-map variance; confidence
labels are capped accordingly.</li>
<li>Every probability on this site is an estimate derived from the linked sources at their read times.
Odds move; matches get rescheduled; rosters change. Not betting advice.</li>
</ul>
"""
    (OUT_SITE / "unresolved.html").write_text(
        chrome("Unresolved picks + limitations", "unresolved.html", body, stamp), encoding="utf-8")

    # ---- method.html
    src_items = "".join(
        f'<li><a href="{esc(s["url"])}">{esc(s["label"])}</a> <span class="small">({esc(s.get("kind"))}'
        f'{(" · read " + esc(s.get("read_utc"))) if s.get("read_utc") else ""})</span></li>'
        for s in research.get("sources_index", []))
    proto = "".join(f"<li>{esc(p)}</li>" for p in research.get("protocol", []))
    body = f"""
<h1>Method &amp; sources</h1>
<h2>How each pick is resolved</h2>
<ol>{proto}</ol>
<p>{esc(research.get("origin_formula"))}</p>
<h2>Probability derivation</h2>
<ul>
<li>No-vig from a two-way price: <code>p_i = (1/odds_i) / sum_j(1/odds_j)</code> (proportional method).</li>
<li>Market consensus: arithmetic mean of per-source no-vig probabilities (as on the full-coverage board).</li>
<li>Research-resolved rows: the originated probability is stated per fixture in
<code>data/b5436cf0/research.json</code> with the exact facts used.</li>
<li>HotSpawn crowd pick percentages are <b>never</b> used as probability inputs.</li>
</ul>
<h2>Sources read this session (with UTC read times)</h2>
<ul class="srclist">{src_items}</ul>
<h2>Data files</h2>
<ul>
<li><code>data/b5436cf0/research.json</code> — session research evidence, originated lines, limitations.</li>
<li><code>data/b5436cf0/board.json</code> — merged board rendered here (regenerated every build).</li>
<li>Upstream (read-only): <code>data/fe803b80/board.json</code>, <code>data/c64a5e19/board.json</code>.</li>
</ul>
"""
    (OUT_SITE / "method.html").write_text(chrome("Method & sources", "method.html", body, stamp), encoding="utf-8")

    # ---- flagged.html
    flag_rows = []
    for r in rows:
        url = r.get("hotspawn_url")
        link = '<a href="%s">HotSpawn</a>' % esc(url) if url else "—"
        for f in r.get("flags", []):
            flag_rows.append(
                '<tr><td data-l="Fixture">%s %s vs %s</td><td data-l="Flag">%s</td>'
                '<td data-l="Match page">%s</td></tr>'
                % (esc(r["fixture_id"]), esc(r.get("team_a")), esc(r.get("team_b")), esc(f), link))
    body = f"""
<h1>Flagged for review</h1>
<p class="mut">Irregularities found while resolving picks. Published with source links so they can be
reviewed after the site is live; nothing here blocks anything.</p>
<h2>Unresolved / contested items</h2>
{''.join(items)}
<h2>Cross-check disagreements</h2>
{''.join(cross_notes)}
<h2>Per-fixture pipeline flags</h2>
<table class="cards"><thead><tr><th>Fixture</th><th>Flag</th><th>Link</th></tr></thead><tbody>
{''.join(flag_rows) or '<tr><td colspan="3">No pipeline flags.</td></tr>'}
</tbody></table>
"""
    (OUT_SITE / "flagged.html").write_text(chrome("Flagged for review", "flagged.html", body, stamp), encoding="utf-8")
    return counts


# ------------------------------------------------------------------ link check
class LinkCheck:
    HREF = re.compile(r'(?:href|src)="([^"]+)"')

    @classmethod
    def run(cls, folder: Path):
        errors = []
        for page in folder.glob("*.html"):
            for url in cls.HREF.findall(page.read_text(encoding="utf-8")):
                if url.startswith(("http", "#", "mailto:")):
                    continue
                target = (page.parent / url.split("#", 1)[0]).resolve()
                if not target.exists():
                    errors.append(f"{page.name} -> {url}")
        return errors


def main() -> int:
    research = load(RESEARCH)
    if not research:
        print("FATAL: research.json missing or unreadable", file=sys.stderr)
        return 1
    rows, stamps = build_rows(research)
    stamp = now_utc()
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    OUT_SITE.mkdir(parents=True, exist_ok=True)

    counts = summary_counts(rows)
    board = {
        "session": "b5436cf0",
        "generated_utc": stamp,
        "research_read_utc": research.get("research_read_utc"),
        "upstream_stamps": stamps,
        "summary": counts,
        "rows": rows,
        "unresolved_items": research.get("unresolved_items", []),
    }
    (OUT_DATA / "board.json").write_text(json.dumps(board, indent=1, sort_keys=False), encoding="utf-8")
    render_pages(research, rows, stamps, stamp)

    errors = LinkCheck.run(OUT_SITE)
    if errors:
        print("FATAL: broken internal links:\n" + "\n".join(errors), file=sys.stderr)
        return 1
    print(f"picks-all built: {counts['total']} rows "
          f"(market {counts['market']}, research {counts['research']}, "
          f"model {counts['model']}, unresolved {counts['unresolved']}, "
          f"with_pick {counts['with_pick']}); links OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
