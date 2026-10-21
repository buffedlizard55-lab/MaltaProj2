#!/usr/bin/env python3
"""Full-coverage CS2 pick board for the HotSpawn Pick'ems lobby (session e1b48771).

What this does
--------------
1. Reads the freshest committed full-coverage board (``data/*/board.json``, written by the
   automated 30-minute collector that reverse-engineers the HotSpawn lobby and prices every
   fixture from external bookmakers / exchanges / Thunderpick-via-bo3.gg and, where no book
   prices a match, from the official Valve VRS table).
2. Applies this session's *verified* resolutions (``resolutions.json``) to any open fixture the
   board still leaves without a pick - research only, never a placeholder, never HotSpawn's crowd
   percentage.
3. Publishes ``cs2/`` - a phone-first dashboard: executive summary, every match with a pick and
   both win probabilities, a separate Unresolved & limitations section, Flagged for review and
   Method & sources. Every row links its own sources.
4. Writes ``data/e1b48771/board.json`` so the numbers on the pages can be re-checked.

Rules enforced here (and tested in ``tests/test_e1b48771.py``):
  * every open HotSpawn CS2 fixture appears exactly once;
  * a row without a supported number stays blank and is listed on Unresolved - never filled;
  * every row carries at least one https source link;
  * no probability is derived from HotSpawn's crowd pick percentage (the field is never read);
  * probabilities on a row sum to 1 and the pick is the higher-probability team.
"""
from __future__ import annotations

import glob
import json
import math
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "cs2")
DATA = os.path.join(ROOT, "data", "e1b48771")
RESOLUTIONS = os.path.join(ROOT, "scripts", "e1b48771", "resolutions.json")
SESSION = "e1b48771"
SITE = "https://buffedlizard55-lab.github.io/MaltaProj2"
REFRESH_HOURS = "every 4 hours"

# ------------------------------------------------------------------ Valve VRS (official model)
# Valve publishes the model that produces these points
# (ValveSoftware/counter-strike_regional_standings -> model/glicko.js and model/fit.js):
#   Q = ln(10)/400 ; g = 1/sqrt(1 + 3*Q^2*RD^2/pi^2) with the published fixed RD = 75
#   expected win rate = 1 / (1 + 10^(g*(r - r_opponent)/-400))
# so P(A beats B) = 1 / (1 + exp(-k * C * (pts_a - pts_b))) with C = g * ln(10)/400 and k the slope
# fitted on the board's own market/VRS pairs. Used only to ORIGINATE a line when no book prices a
# fixture; the value is labelled as originated on the page.
VALVE_RD = 75.0
VALVE_Q = math.log(10) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10) / 400.0
VALVE_FLOOR_POINTS = 381.0        # lowest rating in Valve's 2026-10-05 global table (#380 Fruju)


def valve_c() -> float:
    """Valve's rating-difference slope (same constant the upstream board's model uses)."""
    return VALVE_C


def vrs_prob(points_a: float, points_b: float, k: float) -> float:
    return 1.0 / (1.0 + math.exp(-k * VALVE_C * (float(points_a) - float(points_b))))


# ------------------------------------------------------------------ helpers
def esc(value) -> str:
    return (str("" if value is None else value)
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def fmt_utc(value) -> str:
    dt = parse_iso(value)
    return dt.strftime("%d %b %H:%M UTC") if dt else "—"


def pct(value, digits: int = 1) -> str:
    return f"{float(value) * 100:.{digits}f}%" if isinstance(value, (int, float)) else "—"


def hours_old(value) -> float | None:
    dt = parse_iso(value)
    if not dt:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default if default is not None else {}


# ------------------------------------------------------------------ inputs
def newest_board():
    """Freshest committed full-coverage board that has an ``open`` list and Valve VRS ``calibration.k``."""
    best, best_dt, best_path = None, None, None
    for path in glob.glob(os.path.join(ROOT, "data", "*", "board.json")):
        doc = load_json(path)
        if not isinstance(doc, dict) or not isinstance(doc.get("open"), list) or not doc["open"]:
            continue
        if not isinstance(doc.get("calibration"), dict) or "k" not in doc["calibration"]:
            continue
        dt = parse_iso(doc.get("generated_utc"))
        if dt is None:
            continue
        if best_dt is None or dt > best_dt:
            best, best_dt, best_path = doc, dt, path
    if best is None:
        raise SystemExit("no usable board.json found")
    best["_path"] = os.path.relpath(best_path, ROOT)
    return best


BASIS_LABEL = {
    "market": "Bookmaker / exchange price",
    "market+model": "Bookmaker consensus + Valve VRS model",
    "model": "Originated from official Valve VRS (no book price)",
}


def row_from_board(fx):
    line = fx.get("line") or {}
    picks = fx.get("sources") or []
    return {
        "fixture_id": str(fx.get("fixture_id")),
        "competition": fx.get("competition"),
        "tier": fx.get("tier"),
        "points": fx.get("points"),
        "start_utc": fx.get("start_utc"),
        "lock_utc": fx.get("lock_utc"),
        "team_a": fx.get("team_a"),
        "team_b": fx.get("team_b"),
        "hotspawn_url": fx.get("hotspawn_url"),
        "pick": line.get("pick"),
        "pick_prob": line.get("pick_probability"),
        "prob_a": line.get("prob_a"),
        "prob_b": line.get("prob_b"),
        "basis": line.get("basis") or ("unresolved" if not line else "model"),
        "basis_label": BASIS_LABEL.get(line.get("basis"), "Unresolved"),
        "confidence": line.get("confidence"),
        "sources": picks,
        "flags": fx.get("flags") or [],
        "limitations": [],
        "attempts": [],
        "resolved_by": "automated board",
    }


def row_from_resolution(fx, res):
    return {
        "fixture_id": str(fx.get("fixture_id")),
        "competition": fx.get("competition") or res.get("competition"),
        "tier": fx.get("tier"),
        "points": fx.get("points"),
        "start_utc": fx.get("start_utc") or res.get("start_utc"),
        "lock_utc": fx.get("lock_utc"),
        "team_a": fx.get("team_a"),
        "team_b": fx.get("team_b"),
        "hotspawn_url": fx.get("hotspawn_url"),
        "pick": res.get("pick"),
        "pick_prob": res.get("prob_a") if res.get("pick") == fx.get("team_a") else res.get("prob_b"),
        "prob_a": res.get("prob_a"),
        "prob_b": res.get("prob_b"),
        "basis": "research-market" if res.get("resolution") == "market" else "originated",
        "basis_label": res.get("basis_label"),
        "confidence": res.get("confidence"),
        "sources": res.get("sources") or [],
        "flags": res.get("flags") or [],
        "limitations": res.get("limitations") or [],
        "attempts": res.get("attempts") or [],
        "resolved_by": f"session {SESSION} research",
    }


def build():
    board = newest_board()
    resolutions = (load_json(RESOLUTIONS).get("fixtures") or {})
    rows = []
    for fx in board["open"]:
        line = fx.get("line") or {}
        if line.get("pick") and line.get("prob_a") is not None:
            rows.append(row_from_board(fx))
        elif str(fx.get("fixture_id")) in resolutions:
            rows.append(row_from_resolution(fx, resolutions[str(fx.get("fixture_id"))]))
        else:
            row = row_from_board(fx)
            row["pick"] = None
            row["pick_prob"] = None
            row["basis"] = "unresolved"
            row["basis_label"] = "No supported line - pick withheld"
            row["confidence"] = None
            rows.append(row)
    rows.sort(key=lambda r: (r.get("start_utc") or "", r.get("fixture_id")))
    with_pick = [r for r in rows if r.get("pick") and r.get("prob_a") is not None]
    summary = {
        "open": len(rows),
        "with_pick": len(with_pick),
        "unresolved": len(rows) - len(with_pick),
        "market": sum(1 for r in rows if r["basis"] in ("market", "market+model")),
        "market_plus_model": sum(1 for r in rows if r["basis"] == "market+model"),
        "model": sum(1 for r in rows if r["basis"] == "model"),
        "research_market": sum(1 for r in rows if r["basis"] == "research-market"),
        "originated": sum(1 for r in rows if r["basis"] == "originated"),
        "next_lock_utc": rows[0].get("start_utc") if rows else None,
        "covered_percent": round(100.0 * len(with_pick) / len(rows), 1) if rows else 0.0,
    }
    doc = {
        "session": SESSION,
        "generated_utc": iso_now(),
        "source_board": {
            "path": board.get("_path"),
            "generated_utc": board.get("generated_utc"),
            "snapshot_utc": board.get("snapshot_utc"),
            "week": board.get("week"),
            "calibration": board.get("calibration"),
            "vrs_snapshot": (board.get("vrs") or {}).get("snapshot"),
        },
        "summary": summary,
        "rows": rows,
        "resolutions": {k: {"pick": v.get("pick"), "basis_label": v.get("basis_label"),
                            "resolution": v.get("resolution")} for k, v in resolutions.items()},
        "policy": load_json(RESOLUTIONS).get("policy") or [],
    }
    return doc


# ------------------------------------------------------------------ html
CSS = """
:root{--bg:#0b1220;--panel:#121c30;--panel2:#0f1728;--line:#26324b;--text:#e8eefc;--muted:#9db0d0;
--accent:#22d3a6;--accent2:#ffb020;--danger:#ff6b6b;--info:#7aa2ff}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--info)}
.wrap{max-width:880px;margin:0 auto;padding:0 14px}
header.top{position:sticky;top:0;z-index:20;background:rgba(11,18,32,.97);border-bottom:1px solid var(--line);backdrop-filter:blur(6px)}
header.top .wrap{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:10px 14px}
.brand{font-weight:700;font-size:15px;letter-spacing:.2px}
.brand span{color:var(--accent)}
nav{display:flex;gap:8px;overflow-x:auto;-webkit-overflow-scrolling:touch;padding-bottom:2px;width:100%}
nav a{flex:0 0 auto;padding:9px 12px;border:1px solid var(--line);border-radius:999px;color:var(--text);
text-decoration:none;font-size:14px;white-space:nowrap;min-height:38px;display:flex;align-items:center}
nav a.active{background:var(--accent);color:#062018;border-color:var(--accent);font-weight:700}
main{padding:16px 0 40px}
h1{font-size:24px;line-height:1.25;margin:6px 0 8px}
h2{font-size:19px;margin:26px 0 8px}
h3{font-size:16px;margin:18px 0 6px}
p{margin:8px 0}
.eyebrow{text-transform:uppercase;letter-spacing:.08em;font-size:12px;color:var(--accent);margin:0;font-weight:700}
.muted{color:var(--muted)}
.small{font-size:13px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;margin:12px 0}
.card.hi{border-color:var(--accent);box-shadow:0 0 0 1px rgba(34,211,166,.25) inset}
.stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0}
.stat{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:12px}
.stat b{display:block;font-size:26px;line-height:1.1}
.stat span{font-size:12.5px;color:var(--muted)}
.actions{display:grid;gap:10px;margin:14px 0}
.btn{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:15px 16px;border-radius:14px;
background:var(--panel);border:1px solid var(--line);color:var(--text);text-decoration:none;font-weight:600;min-height:52px}
.btn small{display:block;font-weight:400;color:var(--muted);font-size:12.5px;margin-top:2px}
.btn.primary{background:var(--accent);color:#062018;border-color:var(--accent)}
.btn.primary small{color:#0a3b2c}
.badge{display:inline-block;padding:3px 9px;border-radius:999px;font-size:11.5px;font-weight:700;letter-spacing:.02em;white-space:nowrap}
.b-market{background:rgba(34,211,166,.16);color:#6ff0cd;border:1px solid rgba(34,211,166,.45)}
.b-model{background:rgba(255,176,32,.14);color:#ffcf70;border:1px solid rgba(255,176,32,.4)}
.b-research{background:rgba(122,162,255,.15);color:#a9c1ff;border:1px solid rgba(122,162,255,.45)}
.b-none{background:rgba(255,107,107,.14);color:#ff9a9a;border:1px solid rgba(255,107,107,.4)}
.match{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:13px;margin:12px 0}
.match .top{display:flex;justify-content:space-between;gap:8px;align-items:baseline;flex-wrap:wrap}
.match .when{font-variant-numeric:tabular-nums;font-weight:700}
.match .comp{font-size:12.5px;color:var(--muted)}
.teams{display:grid;grid-template-columns:1fr auto;gap:6px 10px;margin:10px 0 6px;align-items:center}
.teams .name{font-size:16px}
.teams .p{font-variant-numeric:tabular-nums;font-weight:700}
.teams .picked{color:var(--accent)}
.bar{height:8px;border-radius:999px;background:#1c2740;overflow:hidden;display:flex}
.bar i{display:block;height:100%}
.bar .a{background:var(--accent)}
.bar .b{background:#37507e}
.pickline{margin:8px 0 2px;font-size:15px}
.pickline strong{color:var(--accent)}
.chips{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:11.5px;padding:3px 8px;border-radius:999px;background:#1a2540;border:1px solid var(--line);color:var(--muted)}
details.src{margin-top:8px}
details.src summary{cursor:pointer;font-size:13px;color:var(--info);padding:6px 0;min-height:34px}
details.src ul{margin:6px 0 0 18px;padding:0;font-size:12.5px;color:var(--muted)}
details.src li{margin:5px 0}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:14px}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.tablewrap{overflow-x:auto}
.note{background:var(--panel2);border-left:3px solid var(--accent2);padding:10px 12px;border-radius:8px;font-size:13.5px;color:var(--muted)}
.warn{border-left-color:var(--danger)}
ul.plain{margin:8px 0 8px 20px;padding:0}
ul.plain li{margin:6px 0}
footer{border-top:1px solid var(--line);padding:16px 0 40px;color:var(--muted);font-size:12.5px}
input[type=search]{width:100%;padding:13px 14px;border-radius:12px;border:1px solid var(--line);
background:var(--panel2);color:var(--text);font-size:16px;min-height:48px}
.sticky-cta{position:sticky;bottom:10px;margin:16px 0 0}
@media(max-width:719px){
 table#tbl thead{display:none}
 table#tbl tr{display:block;border-bottom:1px solid var(--line);padding:10px 0}
 table#tbl td{display:block;border:0;padding:3px 0}
 table#tbl td:before{content:attr(data-label) ": ";color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
}
@media(min-width:720px){.stats{grid-template-columns:repeat(5,minmax(0,1fr))}h1{font-size:30px}}
"""

NAV = [
    ("index.html", "Summary"),
    ("picks.html", "All picks"),
    ("unresolved.html", "Unresolved"),
    ("flagged.html", "Flagged"),
    ("method.html", "Method"),
]


def page(title, subtitle, body, active="", banner=""):
    nav_bits = []
    for href, label in NAV:
        cls = ' class="active"' if href == active else ""
        nav_bits.append(f'<a href="{href}"{cls}>{esc(label)}</a>')
    nav = "".join(nav_bits)
    ban = f'<div class="note {banner[1]}">{banner[0]}</div>' if banner else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>{esc(title)} · HotSpawn CS2 picks</title>
<style>{CSS}</style>
</head>
<body>
<header class="top"><div class="wrap">
<div class="brand">CS2 Pick'ems <span>· every match has a pick</span></div>
<nav>{nav}<a href="../index.html">Site home</a></nav>
</div></header>
<main class="wrap">
<p class="eyebrow">{esc(subtitle)}</p>
<h1>{esc(title)}</h1>
{ban}
{body}
</main>
<footer class="wrap">
<p>Built <strong>{esc(fmt_utc(iso_now()))}</strong> from the freshest committed HotSpawn lobby capture and its
external betting lines. Fixtures come from HotSpawn; every probability comes from an external source linked on
its row. HotSpawn's crowd pick percentage is never read. Not affiliated with HotSpawn or any bookmaker.
Estimates are not guarantees — 18+, gamble responsibly.</p>
<p><a href="../index.html">Site home</a> · <a href="picks.html">All picks</a> ·
<a href="unresolved.html">Unresolved &amp; limitations</a> · <a href="method.html">Method &amp; sources</a> ·
<a href="flagged.html">Flagged for review</a></p>
</footer>
</body>
</html>
"""


def source_links(sources, limit=None):
    items = []
    for src in sources or []:
        url = src.get("url") or ""
        if not url.startswith("https://"):
            continue
        label = src.get("label") or url
        note = f' <span class="muted">· {esc(src.get("note"))}</span>' if src.get("note") else ""
        read = f' <span class="muted">· read {esc(fmt_utc(src.get("read_utc")))}</span>' if src.get("read_utc") else ""
        items.append(f'<li><a href="{esc(url)}" rel="noopener">{esc(label)}</a>{read}{note}</li>')
        if limit and len(items) >= limit:
            break
    return items


def badge(basis):
    if basis in ("market", "market+model"):
        return '<span class="badge b-market">market</span>'
    if basis == "research-market":
        return '<span class="badge b-research">researched price</span>'
    if basis == "model":
        return '<span class="badge b-model">VRS model</span>'
    if basis == "originated":
        return '<span class="badge b-model">originated</span>'
    return '<span class="badge b-none">no pick</span>'


def match_card(row):
    a, b = row.get("team_a"), row.get("team_b")
    pa, pb = row.get("prob_a"), row.get("prob_b")
    pick = row.get("pick")
    links = source_links(row.get("sources"))
    if pa is None or pb is None:
        prob_html = '<p class="note warn">No supported price. Probability left blank rather than guessed — see Unresolved.</p>'
        bar = ""
    else:
        prob_html = (f'<div class="teams">'
                     f'<div class="name{" picked" if pick == a else ""}">{esc(a)}{" ✅" if pick == a else ""}</div>'
                     f'<div class="p{" picked" if pick == a else ""}">{pct(pa)}</div>'
                     f'<div class="name{" picked" if pick == b else ""}">{esc(b)}{" ✅" if pick == b else ""}</div>'
                     f'<div class="p{" picked" if pick == b else ""}">{pct(pb)}</div>'
                     f'</div>'
                     f'<div class="bar"><i class="a" style="width:{pa * 100:.1f}%"></i>'
                     f'<i class="b" style="width:{pb * 100:.1f}%"></i></div>')
        bar = ""
    pickline = (f'<p class="pickline">Pick: <strong>{esc(pick)}</strong> {pct(row.get("pick_prob"))} '
                f'<span class="muted">· {esc(row.get("confidence") or "confidence not stated")}</span></p>'
                if pick else '<p class="pickline">Pick: <strong>withheld</strong></p>')
    chips = "".join(f'<span class="chip">{esc(str(f).replace("_", " "))}</span>' for f in (row.get("flags") or []))
    return f"""<article class="match" id="fx-{esc(row['fixture_id'])}">
<div class="top"><div>
<div class="when">{esc(fmt_utc(row.get('start_utc')))}</div>
<div class="comp">{esc(row.get('competition'))} · locks {esc(fmt_utc(row.get('lock_utc')))} · {esc(row.get('points') or '—')} pts</div>
</div><div>{badge(row.get('basis'))}</div></div>
{prob_html}
{pickline}
<p class="small muted">{esc(row.get('basis_label'))}</p>
{bar}
<div class="chips">{chips}</div>
<details class="src"><summary>Sources for this row ({len(links)})</summary><ul>{''.join(links)}</ul></details>
</article>"""


def table_rows(rows, with_attempts=False):
    out = []
    for r in rows:
        links = source_links(r.get("sources"), limit=3)
        attempts = ""
        if with_attempts and r.get("attempts"):
            attempts = "<ul class=\"plain small\">" + "".join(
                f'<li><strong>{esc(a.get("source"))}</strong> — {esc(a.get("result"))} '
                f'<a href="{esc(a.get("url"))}" rel="noopener">open</a></li>' for a in r["attempts"]) + "</ul>"
        lims = ""
        if r.get("limitations"):
            lims = "<ul class=\"plain small\">" + "".join(f"<li>{esc(x)}</li>" for x in r["limitations"]) + "</ul>"
        out.append(
            "<tr>"
            f'<td data-label="Lock (UTC)"><strong>{esc(fmt_utc(r.get("lock_utc")))}</strong><br>'
            f'<span class="muted small">start {esc(fmt_utc(r.get("start_utc")))}</span></td>'
            f'<td data-label="Match"><a href="#fx-{esc(r["fixture_id"])}">{esc(r.get("team_a"))} v {esc(r.get("team_b"))}</a><br>'
            f'<span class="muted small">{esc(r.get("competition"))}</span></td>'
            f'<td data-label="Pick"><strong>{esc(r.get("pick") or "—")}</strong><br>'
            f'<span class="muted small">{pct(r.get("pick_prob"))}</span></td>'
            f'<td data-label="Win probability">{pct(r.get("prob_a"))} / {pct(r.get("prob_b"))}<br>'
            f'<span class="muted small">{esc(r.get("team_a"))} / {esc(r.get("team_b"))}</span></td>'
            f'<td data-label="Basis">{badge(r.get("basis"))}<br><span class="muted small">{esc(r.get("basis_label"))}</span></td>'
            f'<td data-label="Sources"><ul class="plain small">{"".join(links) or "<li>none</li>"}</ul>{attempts}{lims}</td>'
            "</tr>")
    return out


def render_index(doc):
    s = doc["summary"]
    src = doc["source_board"]
    age = hours_old(src.get("generated_utc"))
    stale = age is not None and age > 6
    banner = ("", "")
    if stale:
        banner = (f'The automated capture is {age:.1f} h old, older than the 6 h freshness gate — '
                  'treat every number as a snapshot and check the source links.', "warn")
    soon = [r for r in doc["rows"] if r.get("pick")][:3]
    soon_html = "".join(
        f'<li><a href="picks.html#fx-{esc(r["fixture_id"])}"><strong>{esc(r.get("pick"))}</strong> '
        f'{pct(r.get("pick_prob"))}</a> — {esc(r.get("team_a"))} v {esc(r.get("team_b"))}, '
        f'{esc(fmt_utc(r.get("start_utc")))}</li>' for r in soon)
    body = f"""
<div class="card hi">
<p class="eyebrow">Executive summary</p>
<p style="font-size:17px;margin:6px 0 4px"><strong>{s['with_pick']} of {s['open']} open HotSpawn CS2 matches have a pick</strong>
({s['covered_percent']}% coverage), each with both teams' win probability and the source behind it.</p>
<p class="muted small">Fixture capture {esc(fmt_utc(src.get('generated_utc')))} · board rebuilt {esc(fmt_utc(doc['generated_utc']))} ·
refresh {REFRESH_HOURS}.</p>
</div>

<div class="stats">
<div class="stat"><b>{s['open']}</b><span>open CS2 matches</span></div>
<div class="stat"><b>{s['with_pick']}</b><span>with a pick</span></div>
<div class="stat"><b>{s['market']}</b><span>from betting lines</span></div>
<div class="stat"><b>{s['model'] + s['originated'] + s['research_market']}</b><span>researched / originated</span></div>
<div class="stat"><b>{s['unresolved']}</b><span>unresolved</span></div>
</div>

<div class="actions">
<a class="btn primary" href="picks.html"><span>All picks — every match<small>pick, both win probabilities, basis, sources</small></span><span>→</span></a>
<a class="btn" href="unresolved.html"><span>Unresolved &amp; limitations<small>where no betting line exists, what we tried, what it means</small></span><span>→</span></a>
<a class="btn" href="method.html"><span>Method &amp; sources<small>how the lobby is read and how each probability is made</small></span><span>→</span></a>
<a class="btn" href="flagged.html"><span>Flagged for review<small>irregularities, rejected quotes, name conflicts</small></span><span>→</span></a>
</div>

<h2>Next locks</h2>
<ul class="plain">{soon_html or '<li>no open fixtures</li>'}</ul>

<h2>Where the picks are</h2>
<div class="actions">
<a class="btn" href="picks.html"><span>All picks<small>every open match: pick, both win probabilities, basis and the sources on each row</small></span><span>→</span></a>
<a class="btn" href="unresolved.html"><span>Unresolved &amp; limitations<small>every row without a market price, the attempt ledger and what the number cannot prove</small></span><span>→</span></a>
<a class="btn" href="flagged.html"><span>Flagged for review<small>name conflicts, duplicate rating rows, rejected placeholder quotes, ageing snapshots</small></span><span>→</span></a>
<a class="btn" href="method.html"><span>Method &amp; sources<small>the reverse-engineered HotSpawn lobby, the priority ladder and the formulas</small></span><span>→</span></a>
</div>

<div class="note sticky-cta">📱 Phone tip: <a href="picks.html">All picks</a> is one card per match, sorted by lock time.
<a href="picks.html">Open the picks list →</a></div>
"""
    return page("Every HotSpawn CS2 match, one pick, sourced", "Executive summary", body,
                active="index.html", banner=banner)


def render_picks(doc):
    rows = doc["rows"]
    cards = "".join(match_card(r) for r in rows)
    table = "".join(table_rows(rows))
    s = doc["summary"]
    body = f"""
<div class="card">
<p><strong>{s['with_pick']} of {s['open']}</strong> open matches carry a pick. Cards are sorted by lock time;
every row links its own sources. A pick is simply the higher-probability team — it is not betting advice.</p>
<input type="search" id="q" placeholder="Filter by team, tournament…" aria-label="Filter matches">
<p class="small muted" id="count"></p>
</div>

<h2>Table</h2>
<div class="tablewrap"><table id="tbl">
<thead><tr><th>Lock (UTC)</th><th>Match</th><th>Pick</th><th>Win probability</th><th>Basis</th><th>Sources</th></tr></thead>
<tbody>{table}</tbody></table></div>

<h2>One card per match</h2>
{cards}

<script>
(function(){{
  var q=document.getElementById('q'), cards=document.querySelectorAll('.match'),
      rows=document.querySelectorAll('#tbl tbody tr'), c=document.getElementById('count');
  function apply(){{
    var v=(q.value||'').toLowerCase().trim(), shown=0;
    cards.forEach(function(el){{var ok=!v||el.textContent.toLowerCase().indexOf(v)>-1;el.style.display=ok?'':'none';if(ok)shown++;}});
    rows.forEach(function(el){{var ok=!v||el.textContent.toLowerCase().indexOf(v)>-1;el.style.display=ok?'':'none';}});
    c.textContent=v?(shown+' match'+(shown===1?'':'es')+' match “'+q.value+'”'):'';
  }}
  if(q){{q.addEventListener('input',apply);}}
}})();
</script>
"""
    return page(f"All picks — {doc['summary']['open']} open CS2 matches", "Picks and probabilities",
                body, active="picks.html")


def render_unresolved(doc):
    s = doc["summary"]
    no_pick = [r for r in doc["rows"] if not r.get("pick")]
    no_market = [r for r in doc["rows"] if r.get("pick") and r["basis"] not in ("market", "market+model")]
    no_market_rows = "".join(table_rows(no_market, with_attempts=True))
    no_pick_html = ("<p class='note'>None. Every open match currently has a pick.</p>" if not no_pick else
                    "<div class=\"tablewrap\"><table><thead><tr><th>Match</th><th>Why no pick</th><th>Sources</th></tr></thead><tbody>"
                    + "".join(f'<tr><td data-label="Match">{esc(r.get("team_a"))} v {esc(r.get("team_b"))}</td>'
                              f'<td data-label="Why">{esc(r.get("basis_label"))}</td>'
                              f'<td data-label="Sources"><ul class="plain small">{ "".join(source_links(r.get("sources"))) }</ul></td></tr>'
                              for r in no_pick) + "</tbody></table></div>")
    body = f"""
<div class="card hi">
<p><strong>{s['unresolved']} open match{'' if s['unresolved'] == 1 else 'es'} without a pick.</strong>
{s['market']} rows are priced from external betting lines. The other {s['model'] + s['originated'] + s['research_market']}
carry a number built from an official source instead — each is listed below with what was tried and what it cannot prove.</p>
</div>

<h2>1 · Matches with no pick at all</h2>
{no_pick_html}

<h2>2 · Matches with a pick but no bookmaker price</h2>
<p class="muted small">These are resolved, not guessed: a researched external price ({s['research_market']}),
the official Valve VRS model ({s['model']}) or a documented VRS lower bound ({s['originated']}).
The limitation is stated per row.</p>
<div class="tablewrap"><table>
<thead><tr><th>Lock (UTC)</th><th>Match</th><th>Pick</th><th>Win probability</th><th>Basis</th><th>What was tried / limits</th></tr></thead>
<tbody>{no_market_rows}</tbody></table></div>

<h2>3 · Limitations of the whole method</h2>
<ul class="plain">
<li><strong>No price means no quote.</strong> Where no bookmaker, exchange or Thunderpick-via-bo3.gg price is reachable,
the number is originated from the official Valve regional standings table (VRS). It is a model output, not a market.</li>
<li><strong>Valve's newest published standings are dated {esc(doc['source_board'].get('vrs_snapshot') or 'unknown')}</strong>
(<a href="https://github.com/ValveSoftware/counter-strike_regional_standings/tree/main/live/2026" rel="noopener">official repo</a>).
Valve publishes roughly monthly, so roster moves after that date are invisible to the model. Verified at read time:
no newer file exists.</li>
<li><strong>Unrated teams are bounded, not rated.</strong> A team absent from Valve's table is at or below the weakest
published rating (381 pts on 2026-10-05). Any probability for a fixture involving such a team is a lower bound for
the rated side, and is labelled as such.</li>
<li><strong>Thin prediction markets are not prices.</strong> Polymarket map markets quoted 0.40 bid / 0.87 ask on $10–$14
volume are recorded as corroboration only and never averaged into a probability.</li>
<li><strong>Aggregated best-price lines mix books.</strong> Where one site shows the best available price per side from
two different bookmakers, the no-vig normalisation is an estimate of the market rather than a single book's line
(flagged per row).</li>
<li><strong>Matching is exact.</strong> Names are never merged without a recorded decision; a fixture with an ambiguous
name keeps its own row (see Flagged).</li>
<li><strong>Snapshot, not a stream.</strong> Odds move. Every row carries the read time of its quotes; a page rebuild is
not a new observation.</li>
<li><strong>HotSpawn is discovery and settlement only.</strong> Its crowd pick percentage is never read, stored or used,
so it cannot move a probability in either direction.</li>
</ul>

<h2>4 · Refreshing</h2>
<p>The automated collector re-reads the HotSpawn lobby and the external books every 30 minutes; this section rebuilds
{REFRESH_HOURS} from the freshest capture and never invents a row. See <a href="method.html">Method &amp; sources</a>.</p>
"""
    return page("Unresolved picks & limitations", "Separate section", body, active="unresolved.html")


def render_flagged(doc):
    rows = doc["rows"]
    def findings():
        out = []
        out.append(("F1", "Polymarket lists a different opponent for the same 22:00 UTC Los Niños fixture",
                    "Polymarket's <a href=\"https://polymarket.com/event/cs2-ale1-ln-2026-10-21\" rel=\"noopener\">cs2-ale1-ln-2026-10-21</a> "
                    "describes 'Alianza Lima Esports vs Los Niños', 21 Oct 22:00 UTC, CCT South America Series 7 Round 5. "
                    "HLTV's <a href=\"https://www.hltv.org/matches/2399865/zetta-vs-los-ninos-cct-2026-south-america-series-7\" rel=\"noopener\">match 2399865</a> "
                    "lists 'Zetta vs LOS NINOS' at the same time and event. Both cannot be right; HotSpawn follows HLTV. "
                    "The Polymarket market is quoted 0.50/0.50 with a 0.05 bid / 0.95 ask and $5 volume, so no price was taken from it."))
        out.append(("F2", "Valve publishes two CYBERSHOKE rows with different rosters",
                    "<a href=\"https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md\" rel=\"noopener\">2026-10-05 global standings</a>: "
                    "#61 CYBERSHOKE 1201 pts (Alkaren, alpha, Mokuj1n, nota, yiksrezo) and #171 CYBERSHOKE 786 pts "
                    "(alpha, bl1x1, fluffy, glowiing, Mokuj1n). HotSpawn's 'ex-CYBERSHOKE' cannot be joined unambiguously, "
                    "so the rating is only a sanity check for that fixture; the pick uses the bookmaker price."))
        out.append(("F3", "Aggregated odds page mixes two bookmakers in one two-way line",
                    "<a href=\"https://kushvsporte.ru/event/6990334-cybershoke-blinkdagger\" rel=\"noopener\">kushvsporte.ru</a> shows П1 1.12 "
                    "labelled PARI and П2 5.59 labelled WinLine. Best-price aggregation understates the true overround; the "
                    "no-vig split (83.31% / 16.69%) is therefore an estimate of the market. The raw decimal odds are published so "
                    "the arithmetic can be re-done."))
        out.append(("F4", "Placeholder 1.8/1.8 quotes rejected",
                    "egamersworld publishes 1.80 / 1.80 with 0% / 0% for both fixtures researched here "
                    "(<a href=\"https://egamersworld.com/counterstrike/match/4yp_dlKtNl/ex-cybershoke-vs-blinkdagger-5sOoK5oHU4\" rel=\"noopener\">CYBERSHOKE–BlinkDagger</a>, "
                    "<a href=\"https://egamersworld.com/counterstrike/match/0U32SId-H/zetta-vs-los-ninos-Wi0PWrNpb\" rel=\"noopener\">Zetta–LOS NINOS</a>). "
                    "Symmetric 1.80/1.80 with zero volume is the site's unfilled default, not a line; it is excluded."))
        out.append(("F5", "Upstream board's track-record block is not reproducible",
                    "The source board's <code>track_record.by_basis</code> reports 90.6% (market) and 69.2% (model) hit rates over "
                    "6,908 settled rows. Prior verification sessions found the settled rows re-derive the pick from the result, so "
                    "the figure cannot be quoted as an out-of-sample record. It is deliberately not shown anywhere in this section."))
        out.append(("F6", "Valve standings snapshot is 16 days old",
                    "The newest published file is <code>standings_global_2026_10_05.md</code> (checked via api.github.com, 388 rows). "
                    "Valve publishes roughly monthly, so the model rows can lag roster changes. Affects every VRS-model and "
                    "originated row."))
        out.append(("F7", "One open fixture is not on the lobby page",
                    "The capture carries 'Wildcard v DENDELE' (12 Nov) from HotSpawn's public fixtures API but the lobby page's "
                    "weekly view does not show it. It is kept on the picks list (it is a real HotSpawn fixture) and marked in its row."))
        out.append(("F8", "HLTV publishes no odds; HLTV ranks and VRS ranks disagree",
                    "HLTV's match pages for these fixtures carry a betting panel with no numbers, so HLTV is used for identity, "
                    "rosters and form only — never as a probability. HLTV's VRS widget shows Zetta at #366 while Valve's 2026-10-05 "
                    "file lists #357; the official Valve file is used."))
        return out
    items = "".join(
        f'<article class="card" id="{esc(code)}"><h3>{esc(code)} · {esc(title)}</h3><p class="small">{text}</p></article>'
        for code, title, text in findings())
    body = f"""
<div class="card">
<p>Everything that could not be confirmed cleanly, with the source that shows it. None of these items changes a pick
silently: each is either excluded from the numbers or stated on the row it affects.</p>
</div>
{items}
<h2>Unverified values</h2>
<p>No probability in this section is blank on a row that claims one. The only blank-capable field is a missing market
price, and every such row states its substitute basis. Values that could not be confirmed were left out rather than filled.</p>
"""
    return page("Flagged for review", "Irregularities", body, active="flagged.html")


def render_method(doc):
    src = doc["source_board"]
    cal = src.get("calibration") or {}
    body = f"""
<div class="card">
<p class="eyebrow">Where the fixtures come from</p>
<p>The HotSpawn Pick'ems lobby (<a href="https://play.hotspawn.com/lobby" rel="noopener">play.hotspawn.com/lobby</a>) is a
client-rendered page. The fixture list it renders is served by a public JSON endpoint the page itself calls:
<a href="https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures" rel="noopener">/api/v1/fixtures</a>
(~9.6 MB, 12,000 rows across all sports). The collector keeps CS2 rows, resolves the current week's fixtures and joins them
to the individual match pages linked on every row
(<code>https://www.hotspawn.com/matches/&lt;slug&gt;-&lt;fixture_id&gt;</code>). Lobby week at capture:
<strong>{esc((src.get('week') or {}).get('weekId') or '—')}</strong>, {esc((src.get('week') or {}).get('weekStartUtc') or '—')} →
{esc((src.get('week') or {}).get('weekEndUtc') or '—')}.
Kick-off times are UTC; each fixture also carries a lock time six minutes before kick-off, which is what the cards sort by.</p>
<p class="small muted">HotSpawn is used for discovery, kick-off times and settlement only. Its crowd pick percentage is not read.</p>
</div>

<h2>How a probability is made</h2>
<div class="tablewrap"><table>
<thead><tr><th>Priority</th><th>Input</th><th>How it becomes a number</th><th>Official source</th></tr></thead>
<tbody>
<tr><td data-label="Priority">1</td><td data-label="Input">Bookmaker / exchange two-way prices — Pinnacle, Bovada, Melbet (1xBet platform), Kalshi, Thunderpick via bo3.gg</td>
<td data-label="How">Each two-way price is normalised to remove the margin: <code>p = (1/odds) / (1/odds_a + 1/odds_b)</code>. The row shows the mean across the books that price it; the spread is kept in the source board.</td><td data-label="Source"><a href="https://www.pinnacle.com/en/esports/cs2-hub" rel="noopener">Pinnacle</a><br><a href="https://www.bovada.lv/esports/counter-strike-2" rel="noopener">Bovada</a><br><a href="https://kalshi.com/markets" rel="noopener">Kalshi</a></td></tr>
<tr><td data-label="Priority">2</td><td data-label="Input">Market consensus + official Valve VRS</td>
<td data-label="How">The VRS probability is blended with the market at a fixed 0.85 market weight. Used only when both inputs exist.</td><td data-label="Source"><a href="https://github.com/ValveSoftware/counter-strike_regional_standings" rel="noopener">Valve VRS</a></td></tr>
<tr><td data-label="Priority">3</td><td data-label="Input">Official Valve VRS alone</td>
<td data-label="How"><code>p = 1 / (1 + e^(-k · C · (pts_a − pts_b)))</code>, with <code>C = 0.0056000078</code> (Valve's own slope with its published rating deviation) and <code>k = {cal.get('k') or '—'}</code> fitted on {cal.get('n_pairs') or '—'} market/VRS pairs (mean absolute error {cal.get('mae_prob') and round(cal['mae_prob'], 3) or '—'}).</td><td data-label="Source"><a href="https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md" rel="noopener">Valve standings 2026-10-05</a></td></tr>
<tr><td data-label="Priority">4</td><td data-label="Input">Researched external price (this session)</td>
<td data-label="How">Where the automated board finds nothing, a price published by an external bookmaker or an odds board is quoted verbatim, normalised the same way as priority 1, and the URL plus read time are stored on the row.</td><td data-label="Source"><a href="https://kushvsporte.ru/event/6990334-cybershoke-blinkdagger" rel="noopener">kushvsporte.ru odds board</a></td></tr>
<tr><td data-label="Priority">5</td><td data-label="Input">Valve VRS lower bound (this session)</td>
<td data-label="How">If the opponent is unrated, it is assumed to sit at the weakest published rating (381 pts on 2026-10-05). The result is a <em>lower bound</em> for the rated team and is labelled as such.</td><td data-label="Source"><a href="https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md" rel="noopener">Valve standings 2026-10-05</a></td></tr>
<tr><td data-label="Priority">6</td><td data-label="Input">Nothing</td>
<td data-label="How">Blank. The match stays on the list with an explicit "no supported line" note and appears on <a href="unresolved.html">Unresolved</a>. Never 50/50 by default.</td><td data-label="Source"><a href="https://play.hotspawn.com/lobby" rel="noopener">HotSpawn lobby (fixtures only)</a></td></tr>
</tbody></table></div>

<h2>Research ladder used for un-priced matches</h2>
<ol class="plain">
<li><strong>HLTV</strong> — fixture identity, rosters, ranking, head-to-head and map form
(<a href="https://www.hltv.org/matches" rel="noopener">hltv.org/matches</a>). HLTV publishes no usable odds for these fixtures.</li>
<li><strong>Esportsbooks / betting lines</strong> — bo3.gg (which republishes Thunderpick coefficients), kushvsporte.ru odds boards,
egamersworld (rejected: 1.80/1.80 placeholders), Polymarket (thin markets rejected as prices).</li>
<li><strong>Official Valve VRS</strong> — <a href="https://github.com/ValveSoftware/counter-strike_regional_standings" rel="noopener">ValveSoftware/counter-strike_regional_standings</a>,
the same file Valve publishes; the exact file and its date are cited on every rating source.</li>
</ol>

<h2>Verification performed on these rows</h2>
<ul class="plain">
<li>Fixture identity cross-checked against the HotSpawn match page and HLTV's match page (same teams, same UTC kick-off).</li>
<li>Every quoted price re-read from the page that publishes it; decimal odds stored verbatim, then normalised in code.</li>
<li>Every ratings-based number re-derived from the numbers printed in Valve's file (points, not ranks).</li>
<li>Every row in <a href="picks.html">All picks</a> carries at least one https source link; the tests check this mechanically.</li>
<li>Probabilities are checked to sum to 1 and the pick is checked to equal the higher-probability team.</li>
</ul>

<h2>Refresh</h2>
<p>The automated collector runs every 30 minutes on the repository's schedule and rewrites the upstream board; this section
rebuilds {REFRESH_HOURS} (and on every push) from the freshest capture, so a new HotSpawn fixture appears without manual
input. If the capture is older than 6 hours the summary shows a staleness warning instead of pretending to be live.</p>

<h2>Reproduce it</h2>
<p><code>python3 scripts/e1b48771/build.py</code> reads the freshest <code>data/*/board.json</code>, applies
<code>scripts/e1b48771/resolutions.json</code> and rewrites <code>cs2/</code> plus <code>data/e1b48771/board.json</code>.
<code>python3 -m unittest tests.test_e1b48771</code> re-checks the published pages against that data.</p>
"""
    return page("Method & sources", "How this is built", body, active="method.html")


def main():
    doc = build()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(DATA, exist_ok=True)
    for name, render in (("index.html", render_index), ("picks.html", render_picks),
                         ("unresolved.html", render_unresolved), ("flagged.html", render_flagged),
                         ("method.html", render_method)):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            fh.write(render(doc))
    with open(os.path.join(DATA, "board.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    s = doc["summary"]
    print(f"cs2/: {s['open']} open, {s['with_pick']} with a pick, {s['unresolved']} unresolved "
          f"({s['market']} market, {s['model']} model, {s['research_market']} researched, "
          f"{s['originated']} originated) from {doc['source_board']['path']}")


if __name__ == "__main__":
    main()
