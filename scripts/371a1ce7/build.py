#!/usr/bin/env python3
"""Session 371a1ce7 — the single phone-first front door: start/.

Inputs (all read-only except this session's own data/371a1ce7/**):
  data/fe803b80/board.json  newest automated full-coverage board (every open HotSpawn CS2 fixture,
                            external lines, Valve VRS / Elo models). Refreshed on its own schedule.
  data/371a1ce7/crowd.json  HotSpawn crowd "picked %" (ownership only, NEVER a probability).
  data/371a1ce7/twc.json    TWC 2026 day 1-4 results (each read against HLTV) + day-5 lines and context.

Output: start/*.html and start/data/board.json. Pure standard library, deterministic for a given
(input, build time) pair. No number is invented: a probability the sources do not support stays blank.
"""
from __future__ import annotations

import html
import importlib.util
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "start"
BOARD_PATH = ROOT / "data/fe803b80/board.json"
CROWD_PATH = ROOT / "data/371a1ce7/crowd.json"
TWC_PATH = ROOT / "data/371a1ce7/twc.json"
CORE_PATH = ROOT / "scripts/fe803b80/core.py"

# Pick-rule constants (published on method.html; changing one changes the page, nothing else).
CLIMB_MIN_P = 0.40        # an underdog side must still be at least this likely on our own line
CLIMB_MAX_CROWD = 0.25    # ...and at most this share of the HotSpawn crowd may be on it
CLIMB_MIN_EDGE = 0.15     # ...and our probability must beat its crowd share by this much
TWC_CREDIBLE_UPSET = 0.35 # TWC: an underdog is called "credible" at or above this de-vigged price

VALVE_URL = "https://github.com/ValveSoftware/counter-strike_regional_standings"
LOBBY_URL = "https://play.hotspawn.com/lobby"

MANUAL_RESEARCH = {
    # fixture_id -> research ledger written from pages read by this session (2026-10-18 ~00:15Z).
    "1081863": {
        "verdict": "Direction only: Chinggis Warriors. No probability is published.",
        "steps": [
            ("HLTV", "Chinggis Warriors are listed with a full five (sk0R, ROUX, cool4st, fury5k, tikuak) and ranked #61 in HLTV's world ranking; WXM has no HLTV team page or ranking in the search index.",
             "https://www.hltv.org/team/12646/chinggis-warriors"),
            ("HLTV event", "Both teams are on HLTV's MaceMedia VOID Autumn Cup 2026 schedule (Bo3, 20 Oct).",
             "https://www.hltv.org/events/9435/macemedia-void-autumn-cup-2026"),
            ("Esportsbook aggregator (EGamersWorld)", "Prices the match at a flat 1.8 / 1.8 — the site's default placeholder, not a bookmaker line; WXM's lineup reads 'noName' x5 and it has 0 recorded wins in the last 5 and 10 matches.",
             "https://egamersworld.com/counterstrike/match/EJcHRdr5Vx/chinggis-warriors-vs-wxm-_ddme1I7dZ"),
            ("HotSpawn match page", "WXM has an empty lineup and an empty map breakdown; Chinggis Warriors lists four players.",
             "https://www.hotspawn.com/matches/chinggis-warriors-vs-wxm-void-autumn-cup-2026-1081863"),
            ("Valve VRS", "Chinggis Warriors are rated 685 points; WXM is absent from Valve's list, so there is no rating pair to put a number on.",
             VALVE_URL),
        ],
        "limit": "A brand-new or re-branded roster can be much stronger than its absence from every list suggests, so any 'bound' would be an assumption. The pick follows the only side with evidence of recent results; the probability is left blank.",
    },
}


# ------------------------------------------------------------------------------ helpers
def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def parse_iso(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def iso(dt) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_utc(v) -> str:
    dt = v if isinstance(v, datetime) else parse_iso(v)
    return dt.strftime("%a %d %b %H:%M UTC") if dt else "unverified"


def pct(p, digits=1):
    return None if p is None else f"{p * 100:.{digits}f}%"


def load_core():
    spec = importlib.util.spec_from_file_location("core_fe803b80_ro", CORE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CORE = load_core()


def series_prob(p_map: float, best_of: int) -> float:
    need = best_of // 2 + 1
    total = 0.0
    for lost in range(need):
        total += math.comb(need - 1 + lost, lost) * p_map ** need * (1 - p_map) ** lost
    return total


def implied_map_prob(p_series: float, best_of: int) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if series_prob(mid, best_of) < p_series:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def until(dt_target: datetime, now: datetime) -> str:
    secs = int((dt_target - now).total_seconds())
    if secs <= 0:
        return "locked"
    h, m = divmod(secs // 60, 60)
    if h >= 48:
        return f"in {h // 24}d {h % 24}h"
    return f"in {h}h {m:02d}m" if h else f"in {m}m"


# ------------------------------------------------------------------------------ rows
def basis_label(row: dict) -> tuple[str, str]:
    line = row.get("line") or {}
    b = line.get("basis")
    mk = (row.get("market") or {}).get("sources") or []
    names = {"pinnacle": "Pinnacle", "bovada": "Bovada", "melbet": "Melbet", "kalshi": "Kalshi",
             "thunderpick": "Thunderpick", "polymarket": "Polymarket"}
    shown = " + ".join(names.get(s, s) for s in mk)
    if b == "market":
        return "lines", f"Betting lines: {shown}"
    if b == "market+model":
        return "lines", f"Betting lines ({shown}) blended with Valve rating model"
    if b == "model":
        m = (row.get("model") or {}).get("basis") or ""
        if m.startswith("originated_elo") or "elo" in m:
            return "model", "No book prices it — our Elo over bo3.gg results"
        if m == "originated_rank":
            return "model", "No book prices it — ranking-prior model"
        return "model", "No book prices it — Valve rating model (fitted slope)"
    return "none", "No supported probability"


def build_rows(board: dict, crowd: dict, now: datetime):
    crowd_by_id = {str(r["fixture_id"]): r for r in (crowd.get("rows") or [])}
    open_rows, locked, anomalies = [], [], []
    for o in board.get("open") or []:
        fid = str(o["fixture_id"])
        lobby_listed = fid in crowd_by_id
        start = parse_iso(o.get("start_utc"))
        lock = parse_iso(o.get("lock_utc"))
        if o.get("status") != "scheduled" or (not lobby_listed and start and start > now and
                                              (start - now).days > 7):
            anomalies.append(o)
            continue
        line = o.get("line") or {}
        pa, pb = line.get("prob_a"), line.get("prob_b")
        a, b = o["team_a"], o["team_b"]
        c = crowd_by_id.get(fid) or {}
        ca = None if c.get("crowd_a") is None else c["crowd_a"] / 100.0
        cb = None if c.get("crowd_b") is None else c["crowd_b"] / 100.0
        basis_kind, basis_text = basis_label(o)
        row = {
            "fixture_id": fid, "competition": o.get("competition"), "tier": o.get("tier"),
            "points": o.get("points"), "start_utc": o.get("start_utc"), "lock_utc": o.get("lock_utc"),
            "team_a": a, "team_b": b, "prob_a": pa, "prob_b": pb,
            "basis_kind": basis_kind, "basis": basis_text,
            "confidence": line.get("confidence"), "flags": o.get("flags") or [],
            "crowd_a": ca, "crowd_b": cb,
            "hotspawn_url": o.get("hotspawn_url"), "sources": o.get("sources") or [],
            "vrs_a": (o.get("vrs_a") or {}).get("points"), "vrs_b": (o.get("vrs_b") or {}).get("points"),
            "n_book_sources": len((o.get("market") or {}).get("sources") or []),
            "alias_note": o.get("alias_note"), "total_picks": c.get("total_picks"),
        }
        # ---- safe pick
        if pa is not None and pb is not None:
            side = "a" if pa >= pb else "b"
            row["pick_side"] = side
            row["pick"] = a if side == "a" else b
            row["pick_prob"] = pa if side == "a" else pb
            row["direction_only"] = False
        else:
            # one rated side only: direction without a number
            va, vb = row["vrs_a"], row["vrs_b"]
            if (va is None) != (vb is None):
                side = "a" if va is not None else "b"
                row["pick_side"] = side
                row["pick"] = a if side == "a" else b
                row["pick_prob"] = None
                row["direction_only"] = True
                row["basis_kind"], row["basis"] = "direction", "Direction only — only one side has any rating or results"
            else:
                row["pick_side"] = row["pick"] = row["pick_prob"] = None
                row["direction_only"] = False
        # ---- crowd / climb layer
        row["pick_crowd"] = (ca if row.get("pick_side") == "a" else cb) if row.get("pick_side") else None
        row["leverage"] = (None if row["pick_prob"] is None or row["pick_crowd"] is None
                           else row["pick_prob"] - row["pick_crowd"])
        row["climb"] = {"kind": "none", "text": "No crowd read for this match."}
        if row.get("pick_side") and row["pick_prob"] is not None and row["pick_crowd"] is not None:
            opp_side = "b" if row["pick_side"] == "a" else "a"
            p_opp = pb if opp_side == "b" else pa
            c_opp = cb if opp_side == "b" else ca
            opp_name = b if opp_side == "b" else a
            if row["pick_crowd"] <= CLIMB_MAX_CROWD:
                row["climb"] = {"kind": "same", "pick": row["pick"],
                                "text": f"Same pick — and the crowd is on the other side ({row['pick_crowd']*100:.0f}% on {row['pick']}): +{row['leverage']*100:.0f} pts of leverage."}
            elif (p_opp is not None and c_opp is not None and p_opp >= CLIMB_MIN_P
                  and c_opp <= CLIMB_MAX_CROWD and p_opp - c_opp >= CLIMB_MIN_EDGE
                  and row["n_book_sources"] >= 1):
                row["climb"] = {"kind": "switch", "pick": opp_name, "prob": p_opp,
                                "text": f"Climb pick: {opp_name} ({p_opp*100:.0f}% on our line, {c_opp*100:.0f}% of the crowd)."}
            else:
                row["climb"] = {"kind": "same", "pick": row["pick"],
                                "text": "Same pick — no underdog clears the climb rule here."}
        elif row.get("direction_only"):
            row["climb"] = {"kind": "same", "pick": row["pick"], "text": "Same pick — direction only, no number to weigh a switch."}
        if lock and lock <= now:
            locked.append(row)
        else:
            open_rows.append(row)
    open_rows.sort(key=lambda r: (r["lock_utc"] or "", r["fixture_id"]))
    locked.sort(key=lambda r: (r["lock_utc"] or "", r["fixture_id"]))
    return open_rows, locked, anomalies


# ------------------------------------------------------------------------------ TWC
def twc_day5(twc: dict) -> list:
    out = []
    for m in twc["day5"]:
        ln = m["line"]
        nv = CORE.no_vig(ln["dec_a"], ln["dec_b"])
        mk_a = nv["prob_a"]
        va, vb = m["valve"]["a"], m["valve"]["b"]
        mod_a = CORE.vrs_prob(va, vb, twc["vrs_k"]["value"])
        w = CORE.market_weight(1)
        bl_a = CORE.sigmoid(w * CORE.logit(mk_a) + (1 - w) * CORE.logit(mod_a))
        side = "a" if bl_a >= 0.5 else "b"
        fav = m["team_a"] if side == "a" else m["team_b"]
        dog = m["team_b"] if side == "a" else m["team_a"]
        p_fav = bl_a if side == "a" else 1 - bl_a
        mk_fav = mk_a if side == "a" else 1 - mk_a
        mk_dog = 1 - mk_fav
        credible = mk_dog >= TWC_CREDIBLE_UPSET
        out.append({**m, "market_a": mk_a, "market_b": 1 - mk_a, "overround": nv["overround"],
                    "model_a": mod_a, "model_b": 1 - mod_a, "blend_a": bl_a, "blend_b": 1 - bl_a,
                    "favourite": fav, "underdog": dog, "fav_prob": p_fav, "dog_prob_market": mk_dog,
                    "credible_upset": credible,
                    "implied_map_fav": implied_map_prob(mk_fav, m["best_of"])})
    return out


# ------------------------------------------------------------------------------ HTML
CSS = """
:root{--bg:#0f141a;--card:#161d26;--card2:#1b2430;--line:#2a3646;--tx:#e8eef5;--mut:#9fb0c3;--ac:#ffb020;--ok:#37c978;--bad:#ff6b6b;--lnk:#7cc4ff}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--tx);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:var(--lnk)}a:focus,summary:focus{outline:3px solid var(--ac);outline-offset:2px}
header.top{position:sticky;top:0;z-index:5;background:#0b1015;border-bottom:1px solid var(--line)}
header.top .in{max-width:980px;margin:0 auto;padding:8px 12px}
.brand{font-weight:700;font-size:15px;color:var(--mut)}.brand b{color:var(--ac)}
nav.tabs{display:flex;gap:6px;overflow-x:auto;padding:6px 0 2px;scrollbar-width:thin}
nav.tabs a{flex:0 0 auto;text-decoration:none;color:var(--tx);background:var(--card);border:1px solid var(--line);border-radius:999px;padding:8px 14px;font-size:15px;min-height:40px;display:inline-flex;align-items:center}
nav.tabs a[aria-current=page]{background:var(--ac);color:#111;border-color:var(--ac);font-weight:700}
main{max-width:980px;margin:0 auto;padding:12px}
h1{font-size:24px;line-height:1.2;margin:10px 0 6px}h2{font-size:20px;margin:22px 0 8px}h3{font-size:17px;margin:0 0 6px}
.mut{color:var(--mut)}.small{font-size:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:12px 0}
.hero{border-color:#3a4c63;background:linear-gradient(180deg,#1a2431,#151c26)}
.pickline{font-size:22px;font-weight:800;line-height:1.25}.pickline .p{color:var(--ok)}
.btns{display:grid;gap:8px;margin:12px 0}
.btn{display:flex;justify-content:space-between;align-items:center;gap:10px;min-height:52px;padding:10px 14px;border-radius:12px;background:var(--card2);border:1px solid var(--line);color:var(--tx);text-decoration:none}
.btn strong{display:block}.btn span.s{font-size:14px;color:var(--mut)}.btn.pri{background:var(--ac);color:#111;border-color:var(--ac)}.btn.pri span.s{color:#3b2a00}
@media(min-width:700px){.btns{grid-template-columns:1fr 1fr}}
.chip{display:inline-block;border-radius:999px;padding:2px 9px;font-size:13px;border:1px solid var(--line);background:var(--card2);color:var(--mut);margin:0 4px 4px 0}
.chip.lines{border-color:#2f7d54;color:#9be3bd}.chip.model{border-color:#8a6d1f;color:#f1d27a}.chip.direction,.chip.none{border-color:#8a3a3a;color:#ffb0b0}
.chip.climb{border-color:#6a4bb0;color:#cdb8ff}
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:13px;color:var(--mut);text-transform:uppercase;letter-spacing:.03em}
table.resp td strong.pk{color:var(--ok)}
.bar{display:flex;height:9px;border-radius:5px;overflow:hidden;background:#2a3646;margin:4px 0 2px;min-width:110px}.bar i{display:block;background:var(--ok)}.bar i+i{background:#4a5b70}
.blank{color:var(--bad);font-weight:600}
@media(max-width:699px){
 table.resp thead{display:none}table.resp,table.resp tbody,table.resp tr,table.resp td{display:block;width:100%}
 table.resp tr{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:8px 12px;margin:12px 0}
 table.resp td{border:0;padding:5px 0;display:grid;grid-template-columns:104px 1fr;gap:8px}
 table.resp td::before{content:attr(data-label);color:var(--mut);font-size:13px;text-transform:uppercase;letter-spacing:.03em;padding-top:2px}
}
details.archive{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:8px 12px;margin:10px 0}
details summary{cursor:pointer;min-height:40px;display:flex;align-items:center;font-weight:600}
.jump{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0}.jump a{border:1px solid var(--line);background:var(--card2);border-radius:999px;padding:6px 12px;text-decoration:none;color:var(--tx);font-size:14px}
ul.tight{padding-left:20px;margin:6px 0}ul.tight li{margin:4px 0}
footer{max-width:980px;margin:18px auto;padding:0 12px 28px;color:var(--mut);font-size:14px}
.tag-up{color:var(--bad);font-weight:700}
"""

TABS = [("index.html", "Summary"), ("picks.html", "All picks"), ("twc.html", "TWC final day"),
        ("unresolved.html", "Unresolved"), ("flagged.html", "Flagged"), ("method.html", "Method"),
        ("archive.html", "Archive")]


def page(active: str, title: str, body: str, built: datetime) -> str:
    cur = ' aria-current="page"'
    tabs = "".join(f'<a href="{h}"{cur if h == active else ""}>{esc(t)}</a>' for h, t in TABS)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · CS2 pick'em picks</title>
<style>{CSS}</style></head>
<body>
<header class="top"><div class="in"><div class="brand"><b>CS2</b> pick'em · picks from betting lines</div>
<nav class="tabs" aria-label="Sections">{tabs}</nav></div></header>
<main id="main">
{body}
</main>
<footer>Built <strong>{esc(fmt_utc(built))}</strong> · <a href="../index.html">Site home</a> · <a href="../flagged.html">Site-wide flagged items</a>.
HotSpawn supplies the match list and crowd shares only — never a win probability. Estimates are not guarantees. 18+; gamble responsibly.</footer>
</body></html>
"""


def src_links(row) -> str:
    seen, out = set(), []
    for s in row.get("sources") or []:
        u = s.get("url")
        if not u or u in seen:
            continue
        seen.add(u)
        label = (s.get("label") or "source").split(" · ")[0]
        label = label.replace(" (fixture discovery only)", "").replace("HotSpawn Pick'ems lobby", "HotSpawn match")
        out.append(f'<a href="{esc(u)}" rel="noopener">{esc(label)}</a>')
    return " · ".join(out) or '<span class="blank">no source</span>'


def prob_cell(row) -> str:
    if row["pick_prob"] is None:
        return '<span class="blank">blank</span> <span class="small mut">(unverified — no rating pair)</span>'
    pa, pb = row["prob_a"], row["prob_b"]
    return (f'<strong class="pk">{row["pick"]} {pct(row["pick_prob"])}</strong>'
            f'<div class="bar" role="img" aria-label="{esc(row["team_a"])} {pct(pa)} vs {esc(row["team_b"])} {pct(pb)}">'
            f'<i style="width:{pa*100:.1f}%"></i><i style="width:{pb*100:.1f}%"></i></div>'
            f'<span class="small mut">{esc(row["team_a"])} {pct(pa)} · {esc(row["team_b"])} {pct(pb)}</span>')


def pick_table(rows, built, with_lock=True) -> str:
    if not rows:
        return '<p class="mut">None right now.</p>'
    trs = []
    for r in rows:
        lock = parse_iso(r["lock_utc"])
        crowd = ("—" if r["crowd_a"] is None else
                 f'{esc(r["team_a"])} {r["crowd_a"]*100:.0f}% · {esc(r["team_b"])} {r["crowd_b"]*100:.0f}%')
        if r.get("total_picks") is not None:
            crowd += f' <span class="small mut">(n={esc(r["total_picks"])})</span>'
        lev = "" if r["leverage"] is None else f' <span class="chip">{r["leverage"]*100:+.0f} vs crowd</span>'
        climb = r["climb"]
        climb_chip = ('<span class="chip climb">Climb: switch to ' + esc(climb["pick"]) + "</span>") if climb["kind"] == "switch" else ""
        extra = ""
        if r["n_book_sources"] == 1 and r["basis_kind"] == "lines":
            extra += '<br><span class="small mut">Single price source — thinner evidence.</span>'
        if r.get("alias_note"):
            extra += f'<br><span class="small mut">Name match: {esc(r["alias_note"])}</span>'
        dir_chip = '<br><span class="chip direction">direction only</span>' if r["direction_only"] else ""
        pick_name = esc(r["pick"]) if r["pick"] else '<span class="blank">no pick</span>'
        trs.append(
            f'<tr id="m{esc(r["fixture_id"])}">'
            f'<td data-label="Match"><strong>{esc(r["team_a"])} vs {esc(r["team_b"])}</strong><br>'
            f'<span class="small mut">{esc(r["competition"])} · tier {esc((r["tier"] or "").upper())} · {esc(r["points"])} pts</span><br>'
            f'<span class="small">Locks {esc(fmt_utc(lock))} ({esc(until(lock, built)) if lock else "?"})</span></td>'
            f'<td data-label="Pick"><span class="pickline" style="font-size:19px">✅ {pick_name}</span>'
            f'{dir_chip}</td>'
            f'<td data-label="Win chance">{prob_cell(r)}</td>'
            f'<td data-label="Crowd">{crowd}{lev}</td>'
            f'<td data-label="Climb">{climb_chip}<span class="small">{esc(climb["text"])}</span></td>'
            f'<td data-label="Basis"><span class="chip {esc(r["basis_kind"])}">{esc(r["basis"])}</span>{extra}</td>'
            f'<td data-label="Sources">{src_links(r)}</td></tr>')
    head = "<thead><tr><th>Match</th><th>Pick</th><th>Win chance</th><th>Crowd (HotSpawn)</th><th>Climb</th><th>Basis</th><th>Sources</th></tr></thead>"
    return f'<div class="tablewrap"><table class="resp">{head}<tbody>{"".join(trs)}</tbody></table></div>'


def twc_card(m, built, detail=False) -> str:
    start = parse_iso(m["start_utc"])
    ln = m["line"]
    dog_note = (f'<span class="chip climb">Credible upset shot: {esc(m["underdog"])} {pct(m["dog_prob_market"], 0)} on the book</span>'
                if m["credible_upset"] else
                f'<span class="chip">{esc(m["underdog"])} only {pct(m["dog_prob_market"], 0)} on the book — below the {TWC_CREDIBLE_UPSET*100:.0f}% credible-upset line</span>')
    return f"""<div class="card hero" id="{esc(m['key'])}">
<p class="mut small" style="margin:0">{esc(m['stage'])} · Bo{m['best_of']} · {esc(fmt_utc(start))} ({esc(until(start, built))})</p>
<div class="pickline">✅ Pick: {esc(m['favourite'])} <span class="p">{pct(m['fav_prob'],1)}</span> <span class="mut" style="font-size:16px;font-weight:600">vs {esc(m['underdog'])} {pct(1-m['fav_prob'],1)}</span></div>
<div class="bar"><i style="width:{(m['blend_a'] if m['favourite']==m['team_a'] else m['blend_b'])*100:.1f}%"></i><i style="width:{(1-(m['blend_a'] if m['favourite']==m['team_a'] else m['blend_b']))*100:.1f}%"></i></div>
<p style="margin:6px 0">{dog_note}</p>
<p class="small mut" style="margin:6px 0">Book {esc(ln['dec_a'])} / {esc(ln['dec_b'])} ({esc(m['team_a'])} / {esc(m['team_b'])}) → de-vigged {pct(m['market_a'])} / {pct(m['market_b'])}; Valve-rating model {pct(m['model_a'])} / {pct(m['model_b'])}. Blend 75/25 market/model.</p>
<p class="small" style="margin:6px 0"><a href="{esc(m['hltv_url'])}" rel="noopener">HLTV match</a> · <a href="{esc(m['bo3_url'])}" rel="noopener">bo3.gg (Thunderpick price)</a> · <a href="{esc(m['hltv_odds_url'])}" rel="noopener">HLTV odds page</a></p>
</div>"""


# ------------------------------------------------------------------------------ pages
def build_pages(board, crowd, twc, built):
    now = built
    open_rows, locked, anomalies = build_rows(board, crowd, now)
    d5 = twc_day5(twc)
    n = len(open_rows)
    n_lines = sum(r["basis_kind"] == "lines" for r in open_rows)
    n_model = sum(r["basis_kind"] == "model" for r in open_rows)
    n_dir = sum(r["basis_kind"] == "direction" for r in open_rows)
    n_blank = sum(r["pick"] is None for r in open_rows)
    switches = [r for r in open_rows if r["climb"]["kind"] == "switch"]
    board_t = parse_iso(board.get("generated_utc"))
    crowd_t = parse_iso(crowd.get("read_utc"))
    age_h = (now - board_t).total_seconds() / 3600 if board_t else None
    stale = age_h is not None and age_h > 8
    unresolved = [r for r in open_rows if r["basis_kind"] in ("model", "direction", "none")]

    # leverage list: our pick, ≥50% on our line, crowd least on it
    plays = sorted([r for r in open_rows if r["pick_prob"] is not None and r["leverage"] is not None and r["pick_prob"] >= 0.5],
                   key=lambda r: -r["leverage"])[:5]

    # ---------- index
    nxt = open_rows[:4]
    nxt_html = "".join(
        f'<li><a href="picks.html#m{esc(r["fixture_id"])}"><strong>{esc(r["pick"] or "no pick")}</strong>'
        f'{" " + pct(r["pick_prob"],0) if r["pick_prob"] is not None else ""}</a> · {esc(r["team_a"])} v {esc(r["team_b"])} · locks {esc(until(parse_iso(r["lock_utc"]), now))}</li>'
        for r in nxt) or "<li>No open match right now.</li>"
    play_html = "".join(
        f'<li><a href="picks.html#m{esc(r["fixture_id"])}"><strong>{esc(r["pick"])}</strong> {pct(r["pick_prob"],0)}</a> '
        f'<span class="mut">({esc(r["team_a"])} v {esc(r["team_b"])}; crowd only {r["pick_crowd"]*100:.0f}% on it)</span></li>' for r in plays) \
        or "<li>None qualifies right now.</li>"
    unres_rows = "".join(
        f'<tr><td data-label="Match"><a href="unresolved.html#m{esc(r["fixture_id"])}">{esc(r["team_a"])} v {esc(r["team_b"])}</a></td>'
        f'<td data-label="Pick">{esc(r["pick"] or "none")}</td>'
        f'<td data-label="Win chance">{pct(r["pick_prob"],0) if r["pick_prob"] is not None else "<span class=blank>blank</span>"}</td>'
        f'<td data-label="Why">{esc(r["basis"])}</td></tr>' for r in unresolved)
    stale_banner = (f'<div class="card" style="border-color:var(--bad)"><strong>Data is {age_h:.0f} h old.</strong> The line board has not refreshed '
                    f'since {esc(fmt_utc(board_t))}. Picks below may be out of date — check the lock times.</div>') if stale else ""
    body = f"""
<h1>CS2 pick'em — what to pick right now</h1>
<p class="mut small">Probabilities come from outside betting lines and ratings — never from HotSpawn. Lines {esc(fmt_utc(board_t))}
· crowd read {esc(fmt_utc(crowd_t))} · built {esc(fmt_utc(now))}. Rebuilt about every 4 hours.</p>
{stale_banner}
<h2 style="margin-top:6px">🏆 TWC 2026 final day — Sun 18 Oct</h2>
{''.join(twc_card(m, now) for m in d5)}
<p class="small mut">Neither TWC match is on the HotSpawn lobby, so there is no crowd to fade; these are for any other pick'em you play. <a href="twc.html">Full day 1–5 review, Aurora roster check and the upset case →</a></p>

<div class="card">
<h2 style="margin-top:0">HotSpawn lobby · {n} open CS2 matches</h2>
<p style="margin:0 0 6px"><strong>{n_lines}</strong> priced from betting lines · <strong>{n_model}</strong> from rating models (no book prices them) ·
<strong>{n_dir}</strong> direction only · <strong>{n_blank}</strong> no pick.</p>
<p class="small mut" style="margin:0 0 8px">Every open match has a pick except where noted; a blank probability means the sources do not support a number — never a 50/50 guess.</p>
<h3>Locking next</h3><ul class="tight">{nxt_html}</ul>
<h3>Best climb plays (our pick, crowd mostly elsewhere)</h3><ul class="tight">{play_html}</ul>
<p class="small mut">Underdog switches that pass the climb rule right now: <strong>{len(switches)}</strong>{(" — " + ", ".join(esc(r['climb']['pick']) for r in switches)) if switches else ""}.</p>
</div>

<div class="btns">
<a class="btn pri" href="picks.html"><div><strong>All picks — every open match</strong><span class="s">pick, win % for both teams, crowd, sources</span></div><span>→</span></a>
<a class="btn" href="twc.html"><div><strong>TWC day 1–5</strong><span class="s">results, Aurora roster check, final-day case</span></div><span>→</span></a>
<a class="btn" href="unresolved.html"><div><strong>Unresolved &amp; limitations</strong><span class="s">{len(unresolved)} matches with no book price + research ledger</span></div><span>→</span></a>
<a class="btn" href="flagged.html"><div><strong>Flagged for review</strong><span class="s">irregularities with source links</span></div><span>→</span></a>
<a class="btn" href="method.html"><div><strong>Method &amp; sources</strong><span class="s">how every number is made; refresh schedule</span></div><span>→</span></a>
<a class="btn" href="archive.html"><div><strong>Archive</strong><span class="s">older boards from earlier sessions (superseded)</span></div><span>→</span></a>
</div>

<h2 id="unresolved">Unresolved picks &amp; limitations</h2>
<p>These matches have <strong>no bookmaker or exchange price</strong>. Each still gets a pick where the sources allow it, built from
Valve's ratings or our own Elo and labelled as such. Where only one side has any rating or result history, the pick is a direction
with the probability left blank.</p>
<div class="tablewrap"><table class="resp"><thead><tr><th>Match</th><th>Pick</th><th>Win chance</th><th>Basis</th></tr></thead><tbody>{unres_rows}</tbody></table></div>
<ul class="tight small">
<li>Low-tier matches are not listed by Pinnacle, Bovada, Melbet, Kalshi or Thunderpick; HLTV and bo3.gg carry results but no betting line for them.</li>
<li>Valve's ratings are dated {esc(twc['valve_snapshot']['date'])} and cover the top ~380 teams, so very small teams are unrated.</li>
<li>Crowd shares come from small samples (a few dozen picks on low-tier matches) and are shown only to find leverage.</li>
</ul>
<p><a href="unresolved.html">Research ledger and every limitation →</a></p>
"""
    pages = {"index.html": page("index.html", "Summary", body, built)}

    # ---------- picks
    day_groups: dict[str, list] = {}
    for r in open_rows:
        key = (r["lock_utc"] or "")[:10]
        day_groups.setdefault(key, []).append(r)
    jump = "".join(f'<a href="#d{k}">{esc(datetime.fromisoformat(k).strftime("%a %d %b"))} · {len(v)}</a>' for k, v in day_groups.items())
    sections = "".join(f'<h2 id="d{k}">Locks {esc(datetime.fromisoformat(k).strftime("%A %d %b"))} (UTC)</h2>{pick_table(v, now)}' for k, v in day_groups.items())
    locked_html = (f'<h2>Locked or in play ({len(locked)})</h2><p class="small mut">Too late to pick on HotSpawn; shown so the list stays complete.</p>{pick_table(locked, now)}') if locked else ""
    body = f"""
<h1>All picks · {n} open matches</h1>
<p class="mut small">✅ = our pick (higher win chance on outside lines). <strong>Crowd</strong> = share of HotSpawn players on each side (ownership only).
<strong>Climb</strong> = what to do if you are chasing the leaderboard: we only switch to an underdog that is ≥{CLIMB_MIN_P*100:.0f}% on our line while
≤{CLIMB_MAX_CROWD*100:.0f}% of the crowd is on it. Lines {esc(fmt_utc(board_t))} · crowd {esc(fmt_utc(crowd_t))}.</p>
<div class="jump">{jump}</div>
{sections}{locked_html}
<p class="small mut">Rows without a bookmaker price are repeated, with their research, on <a href="unresolved.html">Unresolved &amp; limitations</a>.</p>
"""
    pages["picks.html"] = page("picks.html", "All picks", body, built)

    # ---------- twc
    vr = twc["valve_rank"]
    def winner_loser(r):
        return (r["team_a"], r["team_b"]) if r["score_a"] > r["score_b"] else (r["team_b"], r["team_a"])
    def is_upset(r):
        w, l = winner_loser(r)
        return vr[w] > vr[l]          # higher Valve rank number = lower-ranked team won
    upsets = [r for r in twc["results"] if is_upset(r)]
    res_rows = "".join(
        f'<tr><td data-label="Day">{r["day"]} · {esc(r["date"][5:])}</td>'
        f'<td data-label="Stage">{esc(r["stage"])}</td>'
        f'<td data-label="Result"><strong>{esc(r["team_a"])} {r["score_a"]}–{r["score_b"]} {esc(r["team_b"])}</strong>'
        f'{" <span class=tag-up>UPSET</span>" if is_upset(r) else ""}</td>'
        f'<td data-label="Note">{esc(r["note"] or "")}</td>'
        f'<td data-label="Source"><a href="{esc(r["hltv_url"])}" rel="noopener">HLTV match {r["hltv_id"]}</a></td></tr>' for r in twc["results"])
    d5_detail = ""
    for m in d5:
        facts = "".join(
            f'<li>{esc(f["t"])} <span class="small">' + " · ".join(f'<a href="{esc(u)}" rel="noopener">{esc(l)}</a>' for l, u in f["s"]) + "</span></li>"
            for f in m["facts"])
        d5_detail += f"""<h3 style="margin-top:14px">{esc(m['team_a'])} vs {esc(m['team_b'])} — the case</h3>
<ul class="tight">
<li>Strength: Valve global standings {esc(twc['valve_snapshot']['date'])} #{m['valve']['a_rank']} {esc(m['team_a'])} ({m['valve']['a']} pts) vs #{m['valve']['b_rank']} {esc(m['team_b'])} ({m['valve']['b']}); HLTV ranking #{m['hltv_rank']['a']} vs #{m['hltv_rank']['b']}. <a href="{esc(twc['valve_snapshot']['url'])}" rel="noopener">Valve standings</a></li>
<li>The book's {pct(m['fav_prob'] if False else max(m['market_a'], m['market_b']),1)} series price for {esc(m['favourite'])} implies about {pct(m['implied_map_fav'],1)} per map in a Bo{m['best_of']} (computed; assumes independent, equal maps).</li>
{facts}
</ul>"""
    au = twc["aurora"]
    tl = "".join(f'<tr><td data-label="Date">{esc(x["date"])}</td><td data-label="Event">{esc(x["event"])}</td>'
                 f'<td data-label="Source"><a href="{esc(x["url"])}" rel="noopener">source</a></td></tr>' for x in au["timeline"])
    f_m = next(m for m in d5 if m["key"] == "final")
    t_m = next(m for m in d5 if m["key"] == "third")
    body = f"""
<h1>TWC 2026 — Day 1 to final day</h1>
<p class="mut small">Thunderpick World Championship, Malta, 14–18 Oct 2026 · <a href="https://www.hltv.org/events/8932/thunderpick-world-championship-2026" rel="noopener">HLTV event</a> · <a href="https://blast.tv/cs/tournaments/thunderpick-world-championship-2026" rel="noopener">BLAST</a>.</p>
<h2>Day 5 picks (18 Oct)</h2>
{''.join(twc_card(m, now) for m in d5)}
<div class="card"><h3>How to use them to climb</h3><ul class="tight">
<li><strong>Safe:</strong> {esc(t_m['favourite'])} (3rd place) and {esc(f_m['favourite'])} (final).</li>
<li><strong>Contrarian but not stupid — 3rd place:</strong> {esc(t_m['underdog'])} is a credible shot at {pct(t_m['dog_prob_market'],0)} on the book (above the {TWC_CREDIBLE_UPSET*100:.0f}% line), with a fresher semi (2 maps vs 3), a low-stakes decider and a roster-onboarding story that is already 14 weeks old — take it only if you need variance.</li>
<li><strong>Final:</strong> {esc(f_m['underdog'])} is {pct(f_m['dog_prob_market'],0)} on the book — below the line, in a Bo5 that rewards the favourite, after losing 0-2 to FURIA a few days ago and playing 11 maps in 4 days. Real fatigue and a first-ban on Inferno argue for FURIA; a {esc(f_m['underdog'])} pick is a chase, not an edge.</li>
<li>No HotSpawn crowd exists for either match, so there is no leaderboard leverage to measure.</li></ul></div>
{d5_detail}
<h2>Aurora — the roster-change premise</h2>
<p><strong>{esc(au['verdict'])}</strong></p>
<div class="tablewrap"><table class="resp"><thead><tr><th>Date</th><th>Event</th><th>Source</th></tr></thead><tbody>{tl}</tbody></table></div>
<p>{esc(au['reading'])}</p>
<h2>Every result, days 1–4</h2>
<p class="small mut">{esc(twc['verification'])} “Upset” = the lower Valve-ranked team won.</p>
<div class="tablewrap"><table class="resp"><thead><tr><th>Day</th><th>Stage</th><th>Result</th><th>Note</th><th>Source</th></tr></thead><tbody>{res_rows}</tbody></table></div>
<h2>What days 1–4 teach for day 5</h2>
<ul class="tight">
<li><strong>{len(upsets)} of {len(twc["results"])}</strong> results went to the lower Valve-ranked team (Valve standings {esc(twc['valve_snapshot']['date'])}): {esc("; ".join(f"{winner_loser(r)[0]} (#{vr[winner_loser(r)[0]]}) over {winner_loser(r)[1]} (#{vr[winner_loser(r)[1]]}), {max(r['score_a'], r['score_b'])}-{min(r['score_a'], r['score_b'])}" for r in upsets))}. Valve rank is a rough guide, so this is a count, not a model.</li>
<li>{sum(1 for r in upsets if min(r['score_a'], r['score_b']) == 1)} of those {len(upsets)} upsets went the full three maps; the only sweep was the Day-1 one, which Aurora reversed 2-0 on Day 3. Upsets came as one-off series, not as a trend.</li>
<li>Both finalists beat Valve's #2 side on the way; BETBOOM did it 2-1 and are on three straight 2-1 wins, at the cost of 11 maps in 4 days against FURIA's 7.</li>
<li>For the pick'em: lower-ranked winners were common enough that an underdog at 35%+ is worth a look in a Bo3; in the Bo5 final the format works against the underdog.</li></ul>
"""
    pages["twc.html"] = page("twc.html", "TWC final day", body, built)

    # ---------- unresolved
    cards = []
    for r in unresolved:
        mr = MANUAL_RESEARCH.get(r["fixture_id"])
        ledger_rows = [
            ("HLTV", "HLTV's odds pages carried no moneyline in our reads, and team pages for the sides in this match were not individually read in this build (see Limitations)." if not mr else "see manual steps below", "https://www.hltv.org/matches"),
            ("Betting lines", "The board collector queried Pinnacle, Bovada, Melbet and its mirrors, Kalshi and Thunderpick (via bo3.gg); none returned a two-sided price that joins to this fixture.", "https://bo3.gg/matches/current"),
            ("Valve VRS", f"{esc(r['team_a'])}: {esc(r['vrs_a']) if r['vrs_a'] is not None else 'unrated'}; {esc(r['team_b'])}: {esc(r['vrs_b']) if r['vrs_b'] is not None else 'unrated'} points (standings {esc(twc['valve_snapshot']['date'])}).", twc["valve_snapshot"]["url"]),
        ]
        led = "".join(f'<tr><td data-label="Tried">{esc(a)}</td><td data-label="Result">{b if a=="Valve VRS" else esc(b)}</td><td data-label="Source"><a href="{esc(u)}" rel="noopener">link</a></td></tr>' for a, b, u in ledger_rows)
        manual = ""
        if mr:
            steps = "".join(f'<tr><td data-label="Tried">{esc(a)}</td><td data-label="Result">{esc(b)}</td><td data-label="Source"><a href="{esc(u)}" rel="noopener">link</a></td></tr>' for a, b, u in mr["steps"])
            manual = f'<h4 style="margin:10px 0 4px">Manual research</h4><div class="tablewrap"><table class="resp"><thead><tr><th>Tried</th><th>Result</th><th>Source</th></tr></thead><tbody>{steps}</tbody></table></div><p class="small"><strong>{esc(mr["verdict"])}</strong> {esc(mr["limit"])}</p>'
        pr = (f'{esc(r["pick"])} {pct(r["pick_prob"],1)}' if r["pick_prob"] is not None else (f'{esc(r["pick"])} — probability <span class="blank">blank</span> (unverified)' if r["pick"] else '<span class="blank">no pick</span>'))
        cards.append(f'''<div class="card" id="m{esc(r["fixture_id"])}"><h3>{esc(r["team_a"])} vs {esc(r["team_b"])}</h3>
<p class="small mut" style="margin:0">{esc(r["competition"])} · locks {esc(fmt_utc(r["lock_utc"]))} · <a href="{esc(r["hotspawn_url"])}" rel="noopener">HotSpawn match</a></p>
<p style="margin:6px 0"><strong>Pick:</strong> {pr} <span class="chip {esc(r["basis_kind"])}">{esc(r["basis"])}</span></p>
<div class="tablewrap"><table class="resp"><thead><tr><th>Tried</th><th>Result</th><th>Source</th></tr></thead><tbody>{led}</tbody></table></div>{manual}
<p class="small mut">Flags: {esc(", ".join(f.replace("_"," ") for f in r["flags"]) or "none")}.</p></div>''')
    body = f"""
<h1>Unresolved picks &amp; limitations</h1>
<p>{len(unresolved)} of {n} open matches have no bookmaker or exchange price. Research order for each: <strong>HLTV → esportsbooks / exchanges → Valve ratings → our own Elo</strong>.
A pick is given wherever a labelled model or any one-sided evidence exists; a probability is left blank when no source supports a number.</p>
{''.join(cards) or '<p>No unresolved matches right now.</p>'}
<h2>Limitations</h2>
<ul class="tight">
<li>No bookmaker lists most tier-C CS2 fixtures; an API answering is not proof it prices a match.</li>
<li>Valve's list ({esc(twc['valve_snapshot']['date'])}) is the newest the board holds and covers only the top ~380 teams; rebrands and new rosters can sit outside it. <a href="{esc(twc['valve_snapshot']['url'])}" rel="noopener">Valve standings</a></li>
<li>Our slope for turning rating gaps into probabilities is fitted to the few market pairs available ({esc(board['calibration'].get('n_pairs'))} this board, MAE {board['calibration'].get('mae_prob', 0)*100:.0f} pts) — model rows are weaker than market rows.</li>
<li>Individual HLTV team pages were read by hand only for Chinggis Warriors (the one-sided case); the other model-only rows rely on Valve's ratings or bo3.gg results, not an HLTV page read.</li>
<li>Rosters in small events change without notice; the board only knows the names HotSpawn prints.</li>
<li>HotSpawn's crowd shares are tiny samples on small matches and are never a probability.</li></ul>
"""
    pages["unresolved.html"] = page("unresolved.html", "Unresolved & limitations", body, built)

    # ---------- flagged
    fl = []
    def flag(i, title, detail, links, sev="review"):
        fl.append((i, title, detail, links, sev))
    flag("F1", "The 'recent Aurora roster change' is about 14 weeks old", "Jimpphat and coach ashhh joined 3 Jul 2026 and kyxsan 8 Jul 2026; no change is visible inside the event. The premise is treated as onboarding context only and moves no number.",
         [("Strafe roster tracker", "https://www.strafe.com/news/read/cs2-roster-moves-tracker-summer-2026/"), ("Liquipedia Aurora", "https://liquipedia.net/counterstrike/Aurora_Gaming"), ("HLTV Aurora", "https://www.hltv.org/team/11861/aurora")])
    flag("F2", "TWC main-event matches are not on the HotSpawn lobby", "The lobby's tournament filter lists only 'Thunderpick World Championship 2026: South American Series #1' — the Malta playoffs are absent, so TWC picks have no crowd split and no HotSpawn fixture id.",
         [("HotSpawn lobby", LOBBY_URL)])
    flag("F3", "TWC lines come from a single book", "Day-5 prices are Thunderpick's, read from bo3.gg's match pages at 00:10Z on 18 Oct; HLTV's odds pages do not show a moneyline in our reads. A one-book price is blended 75/25 with the Valve model, as the board's method prescribes for single-source prices. Lines move before kick-off.",
         [("bo3.gg 3rd place", twc["day5"][0]["bo3_url"]), ("bo3.gg final", twc["day5"][1]["bo3_url"])])
    flag("F4", "Chinggis Warriors vs WXM: pick without a probability", "WXM has no lineup, no results and no rating anywhere we looked; the pick follows the only side with evidence and the probability is left blank rather than assumed.",
         [("HotSpawn match", "https://www.hotspawn.com/matches/chinggis-warriors-vs-wxm-void-autumn-cup-2026-1081863"), ("EGamersWorld match", "https://egamersworld.com/counterstrike/match/EJcHRdr5Vx/chinggis-warriors-vs-wxm-_ddme1I7dZ")])
    for r in open_rows:
        if r.get("alias_note"):
            flag("F9", f"{r['team_a']} vs {r['team_b']} — team-name alias applied",
                 f"The price is listed under a different team name and was joined on roster evidence: {r['alias_note']} This is third-party evidence (HLTV, bo3.gg), not a statement from the organiser.",
                 [("HotSpawn match", r["hotspawn_url"])])
        if r["n_book_sources"] == 1 and r["basis_kind"] == "lines" and r["tier"] == "C":
            flag("F10", f"{r['team_a']} vs {r['team_b']} — one price source on a tier-C match",
                 f"Only one source prices this match, so the probability ({pct(r['pick_prob'])} for {r['pick']}) has no cross-check and could move or be stale.",
                 [("Price source", next((x["url"] for x in r["sources"] if x.get("kind") == "price"), r["hotspawn_url"]))])
    for o in anomalies:
        flag("F5", f"{o['team_a']} vs {o['team_b']} — fixture in an inconsistent state", f"HotSpawn's fixtures API lists {o.get('competition')} fixture {o['fixture_id']} with status '{o.get('status')}' and a start of {o.get('start_utc')}, and the lobby page does not show it. Excluded from the pick count; the board's own line ({(o.get('line') or {}).get('pick') or 'none'}) is not republished.",
             [("HotSpawn match", o.get("hotspawn_url") or LOBBY_URL)])
    flag("F6", "Earlier boards disagree with this one", "Older desks on this site (day5/, finals/, desk/, day4/) carry different probabilities for the same matches because they used older captures or other blends (for example NEXVOID vs Off Chops). This front door uses the newest automated line board (30-minute refresh). Do not mix their numbers.",
         [("Archive of earlier boards", "archive.html")])
    flag("F7", "Valve standings date", f"The newest Valve global standings the board holds are dated {twc['valve_snapshot']['date']}; ratings may have moved since.",
         [("Valve standings", twc["valve_snapshot"]["url"])])
    flag("F8", "Crowd shares are a snapshot", "The crowd split was read from the lobby at the time shown on each page and moves as players pick; the 4-hourly refresh re-reads it from HotSpawn's public fixtures API when reachable.",
         [("HotSpawn lobby", LOBBY_URL)])
    items = "".join(
        f'<div class="card" id="{i}"><h3>{i} · {esc(t)}</h3><p>{esc(d)}</p><p class="small">' +
        " · ".join(f'<a href="{esc(u)}" rel="noopener">{esc(l)}</a>' for l, u in ls) + "</p></div>" for i, t, d, ls, _ in fl)
    body = f"""<h1>Flagged for review</h1>
<p class="mut small">Items that could not be fully confirmed from an official source, or that look irregular. None blocks the picks; each is stated rather than silently fixed. Older flags: <a href="../flagged.html">site-wide Flagged for Review</a>.</p>
{items}"""
    pages["flagged.html"] = page("flagged.html", "Flagged for review", body, built)

    # ---------- method
    body = f"""<h1>Method &amp; sources</h1>
<h2>Where each number comes from</h2>
<div class="tablewrap"><table class="resp"><thead><tr><th>Input</th><th>Used for</th><th>Source</th></tr></thead><tbody>
<tr><td data-label="Input">Match list &amp; lock times</td><td data-label="Used for">Which matches exist, when they lock</td><td data-label="Source"><a href="{LOBBY_URL}" rel="noopener">HotSpawn lobby</a> (fixtures only)</td></tr>
<tr><td data-label="Input">Betting lines</td><td data-label="Used for">Win probability (margin removed, then weighted)</td><td data-label="Source"><a href="https://www.pinnacle.com/en/esports/cs2-hub" rel="noopener">Pinnacle</a> · <a href="https://www.bovada.lv/sports/esports" rel="noopener">Bovada</a> · <a href="https://melbet.com/en/line/esports" rel="noopener">Melbet</a> · <a href="https://kalshi.com/" rel="noopener">Kalshi</a> · <a href="https://bo3.gg/matches/current" rel="noopener">Thunderpick via bo3.gg</a></td></tr>
<tr><td data-label="Input">Valve ratings</td><td data-label="Used for">Model probability where no line exists; blend partner for lines</td><td data-label="Source"><a href="{VALVE_URL}" rel="noopener">Valve regional standings</a></td></tr>
<tr><td data-label="Input">Results &amp; rankings</td><td data-label="Used for">Our Elo for unrated teams; the TWC review</td><td data-label="Source"><a href="https://bo3.gg/" rel="noopener">bo3.gg</a> · <a href="https://www.hltv.org/" rel="noopener">HLTV</a></td></tr>
<tr><td data-label="Input">Crowd %</td><td data-label="Used for">Leaderboard leverage only</td><td data-label="Source"><a href="{LOBBY_URL}" rel="noopener">HotSpawn lobby</a></td></tr></tbody></table></div>
<h2>Formulas</h2>
<ul class="tight">
<li><strong>De-vig:</strong> p = (1/odds) ÷ (1/oddsA + 1/oddsB).</li>
<li><strong>Several books:</strong> weighted mean of de-vigged probabilities (Pinnacle 2, Bovada 1.5, Thunderpick 1.5, Kalshi 1, Melbet 1).</li>
<li><strong>Blend with ratings:</strong> logit blend, market weight 0.85 with two or more books, 0.75 with one (TWC uses one book).</li>
<li><strong>Valve model:</strong> p = 1/(1+e<sup>−k·c·Δpoints</sup>), c from Valve's own Glicko code, slope k fitted to published market pairs (board k = {esc(board['calibration'].get('k'))}; TWC k = {twc['vrs_k']['value']} fitted to 48 pairs).</li>
<li><strong>Pick:</strong> the side with the higher probability. If only one side has any rating or result history: that side, probability blank.</li>
<li><strong>Climb rule:</strong> keep the pick unless the other side is ≥{CLIMB_MIN_P*100:.0f}% on our line, ≤{CLIMB_MAX_CROWD*100:.0f}% of the crowd and beats its crowd share by ≥{CLIMB_MIN_EDGE*100:.0f} pts, with at least one book price behind it. Contrarian is only worth it when it is close to a coin-flip.</li>
<li><strong>TWC credible upset:</strong> an underdog at or above {TWC_CREDIBLE_UPSET*100:.0f}% on the de-vigged book price.</li></ul>
<h2>Refresh</h2>
<p>The line board refreshes about every 30 minutes (workflow <code>board (fe803b80)</code>); this front door rebuilds every 4 hours and whenever the board workflow finishes, re-reading HotSpawn's crowd split. A banner appears if the lines are more than 8 hours old. Matches past their lock time move to the "Locked" table automatically.</p>
<p class="small"><a href="https://github.com/buffedlizard55-lab/MaltaProj2/actions" rel="noopener">GitHub Actions status</a></p>
<h2>HotSpawn lobby, reverse-engineered</h2>
<p>The lobby is an Angular page. Its public fixtures API (<code>/api/v1/fixtures</code>) lists every fixture with status, kickoff, lock time (6 minutes before kickoff), points and per-side <code>picked_percent</code>; the page's embedded state carries the same list. We use it for discovery, locks, results and the crowd split only.</p>
"""
    pages["method.html"] = page("method.html", "Method & sources", body, built)

    # ---------- archive
    arch = [
        ("../day5/index.html", "Day-5 desk (7900154b)", "Earlier capture 17 Oct ~20:50Z; slower 4-hourly line collector."),
        ("../finals/index.html", "TWC finals desk (782adb47)", "Earlier capture 17 Oct ~20:20Z."),
        ("../desk/index.html", "Picks desk (3e1be203)", "Day-4 era desk, 17 Oct ~13:46Z."),
        ("../day4/index.html", "Day-4 desk (1c8f79f8)", "TWC semi-final desk."),
        ("../picks-every-match/index.html", "Canonical every-match picks (c64a5e19)", "Strict market-only canonical board."),
        ("../board/picks.html", "Full-coverage board (fe803b80)", "The data feeding this front door, in its own format."),
        ("../twc-2026/index.html", "Day 2 → Day 3 review (69e4c06a)", "Earlier review pages."),
        ("../day-one.html", "Day-one review", "9z–Aurora and the opening day."),
        ("../audits/e2d16060/index.html", "Independent line-by-line audit", "Dated audit."),
        ("../research.html", "Research archive", "Everything else, by session."),
        ("../flagged.html", "Site-wide Flagged for Review", "Every earlier flag."),
    ]
    rows = "".join(f'<tr><td data-label="Page"><a href="{esc(h)}">{esc(t)}</a></td><td data-label="What it is">{esc(d)}</td></tr>' for h, t, d in arch)
    body = f"""<h1>Archive — earlier boards</h1>
<p class="mut">These pages come from earlier work sessions. They were correct for their own capture time and are kept for review, but
<strong>their probabilities differ from the live board</strong> and should not be mixed with it. Start from the <a href="index.html">summary</a>.</p>
<div class="tablewrap"><table class="resp"><thead><tr><th>Page</th><th>What it is</th></tr></thead><tbody>{rows}</tbody></table></div>"""
    pages["archive.html"] = page("archive.html", "Archive", body, built)

    machine = {
        "session": "371a1ce7", "generated_utc": iso(built), "board_generated_utc": board.get("generated_utc"),
        "crowd_read_utc": crowd.get("read_utc"),
        "summary": {"open": n, "locked": len(locked), "lines": n_lines, "model": n_model, "direction_only": n_dir,
                    "no_pick": n_blank, "climb_switches": len(switches), "anomalies": len(anomalies)},
        "twc_day5": [{k: m[k] for k in ("key", "stage", "team_a", "team_b", "start_utc", "favourite", "fav_prob",
                                         "market_a", "market_b", "model_a", "model_b", "blend_a", "blend_b", "credible_upset", "hltv_url")} for m in d5],
        "open": open_rows, "locked": locked,
        "anomalies": [{"fixture_id": o["fixture_id"], "teams": [o["team_a"], o["team_b"]], "status": o.get("status"), "start_utc": o.get("start_utc")} for o in anomalies],
    }
    return pages, machine


def main(argv=None) -> int:
    board = load_json(BOARD_PATH)
    crowd = load_json(CROWD_PATH, {"rows": []})
    twc = load_json(TWC_PATH)
    if not board or not twc:
        print("missing inputs; leaving start/ untouched", file=sys.stderr)
        return 1
    now = datetime.now(timezone.utc).replace(microsecond=0)
    if argv and "--at" in argv:           # deterministic builds for tests
        now = parse_iso(argv[argv.index("--at") + 1])
    pages, machine = build_pages(board, crowd, twc, now)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "data").mkdir(exist_ok=True)
    for name, content in pages.items():
        (OUT / name).write_text(content, encoding="utf-8")
    (OUT / "data/board.json").write_text(json.dumps(machine, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    s = machine["summary"]
    print(f"wrote start/ ({len(pages)} pages): open {s['open']} · lines {s['lines']} · model {s['model']} · "
          f"direction {s['direction_only']} · no-pick {s['no_pick']} · switches {s['climb_switches']} · anomalies {s['anomalies']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
