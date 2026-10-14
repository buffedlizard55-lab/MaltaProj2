#!/usr/bin/env python3
"""EVERY-MATCH builder (session af573ff1): featured board + fallback inputs -> board + site.

Pure offline step. Resolution order for every open HotSpawn CS2 fixture:

  1. FEATURED   — the line published by the featured Our-line board
                  (session f7279a54) is copied verbatim. Never recomputed here.
  2. FALLBACK MARKET (only if featured has no line) — an external bookmaker /
                  exchange price found under a published alias:
                  expanded-board Melbet (1xBet platform) quotes, this session's
                  fresh Melbet/Kalshi quotes, then the EGamersWorld widget
                  (1.80/1.80 placeholders rejected).
  3. FALLBACK MODEL — Valve VRS expected-win curve with the featured board's
                  market-fitted slope k, after evidence-linked alias resolution
                  (e.g. WROTBERRY -> VRS 'WBT', RoundsGG -> VRS 'ROUNDS').
  4. SINGLE-RATING ESTIMATE — one team rated, the other not in any Valve file:
                  rated team vs the lowest points value in the official global
                  standings (a stated population prior), shrunk and clamped.
  5. NO INFORMATION — 50/50, pick shown is the first-listed team and is
                  labelled as a coin flip with no verified information.

HotSpawn crowd percentages are never read. Every row carries source links.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "af573ff1"
SITE = ROOT / "picks-every-match"
LOBBY = "https://play.hotspawn.com/lobby"
VRS_REPO_URL = "https://github.com/ValveSoftware/counter-strike_regional_standings"


def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


# --------------------------------------------------------------------- ratings
def rating_index(vrs_teams: list) -> dict:
    """normalised HotSpawn-side key -> VRS row. Exact name first, alias second.

    Duplicate VRS names (same org, two roster rows) are only used when all rows
    agree on team identity is impossible to establish — such keys are dropped
    (returned in the ambiguous set) rather than guessed.
    """
    groups: dict[str, list] = {}
    for t in vrs_teams:
        key, _n, _u = core.canon(t["team"])
        if key:
            groups.setdefault(key, []).append(t)
    idx, ambiguous = {}, set()
    for key, rows in groups.items():
        if len(rows) == 1:
            idx[key] = rows[0]
        else:
            # Prefer a global-file row — global and regional files list the same
            # team at the same points; a second distinct-points row stays ambiguous.
            points = {r["points"] for r in rows}
            if len(points) == 1:
                idx[key] = sorted(rows, key=lambda r: (r.get("region_file") != "global", r["standing"]))[0]
            else:
                ambiguous.add(key)
    return idx, ambiguous


def rating_for(name, idx, ambiguous):
    key, note, url = core.canon(name)
    if key in ambiguous:
        return None, "ambiguous_vrs_name", note, url
    rec = idx.get(key)
    if rec:
        return rec, ("alias_resolved" if note else None), note, url
    return None, "not_in_vrs", note, url


# ------------------------------------------------------------------ board core
def build_board(featured: dict, expanded: dict, egw: dict, fresh: dict | None) -> dict:
    now = core.now_utc()
    k = float(((featured.get("calibration") or {}).get("k")) or 1.0)
    # VRS universe: featured snapshot (global) + this session's fresh files (global+regional).
    vrs_teams, seen = [], set()
    for src in (((featured.get("_snapshot_vrs") or {}).get("teams") or []),
                (((fresh or {}).get("vrs") or {}).get("teams") or [])):
        for t in src:
            sig = (core.canon(t["team"])[0], t.get("points"), t.get("roster"))
            if sig not in seen:
                seen.add(sig)
                vrs_teams.append(t)
    idx, ambiguous = rating_index(vrs_teams)
    global_rows = [t for t in vrs_teams if t.get("region_file") in (None, "global")]
    prior_points = min((t["points"] for t in global_rows), default=None)

    expanded_by_id = {f["fixture_id"]: f for f in (expanded.get("fixtures") or [])}
    egw_by_id = {str(r["fixture_id"]): r for r in (egw.get("rows") or []) if r.get("fixture_id")}
    fresh_quotes = ((fresh or {}).get("quotes") or [])

    rows = []
    featured_ids = set()
    for fx in featured.get("open") or []:
        featured_ids.add(fx["fixture_id"])
        row = {"fixture_id": fx["fixture_id"], "team_a": fx["team_a"], "team_b": fx["team_b"],
               "competition": fx.get("competition"), "tier": fx.get("tier"),
               "points": fx.get("points"), "start_utc": fx["start_utc"], "lock_utc": fx.get("lock_utc"),
               "hotspawn_url": fx.get("hotspawn_url") or LOBBY,
               "hotspawn_url_kind": fx.get("hotspawn_url_kind") or "lobby",
               "featured": {"line": fx.get("line"), "market": fx.get("market"),
                            "model": fx.get("model"), "vrs": fx.get("vrs"),
                            "quotes": fx.get("quotes") or [],
                            "flags": fx.get("flags") or []}}
        rows.append(row)
    # Fixtures a fresh HotSpawn check lists as open that the featured board has
    # not picked up yet (its refresh runs on its own chain) — same cascade, no featured line.
    fresh_fx = ((fresh or {}).get("hotspawn") or {}).get("fixtures") or []
    fresh_generated = (fresh or {}).get("collected_to_utc")
    if fresh_generated and core.parse_iso(fresh_generated) and core.parse_iso(fresh_generated) >= (core.parse_iso(featured.get("generated_utc") or "") or core.parse_iso("2000-01-01T00:00:00Z")):
        perma = ((fresh or {}).get("hotspawn") or {}).get("permalinks") or {}
        for fx in fresh_fx:
            if fx["fixture_id"] in featured_ids:
                continue
            rows.append({"fixture_id": fx["fixture_id"], "team_a": fx["team_a"], "team_b": fx["team_b"],
                         "competition": fx.get("competition"), "tier": fx.get("tier"),
                         "points": fx.get("points"), "start_utc": fx["start_utc"],
                         "lock_utc": fx.get("lock_utc"),
                         "hotspawn_url": perma.get(fx["fixture_id"]) or LOBBY,
                         "hotspawn_url_kind": "match page" if fx["fixture_id"] in perma else "lobby",
                         "featured": {"line": None, "market": None, "model": None, "quotes": [],
                                      "flags": ["not_yet_on_featured_board"]}})

    for row in rows:
        line = row["featured"]["line"]
        if line:
            row["resolution"] = {
                "level": "featured", "basis_label": "Featured — bookmaker lines / featured model",
                "prob_a": line["prob_a"], "prob_b": line["prob_b"],
                "pick_team": line["pick_team"], "pick_side": line["pick_side"],
                "pick_prob": line["pick_prob"], "confidence": line.get("confidence"),
                "featured_basis": line.get("basis"),
                "sources": [{"name": "Featured Our-line board (this pick, verbatim)",
                             "url": "../ourline/index.html#m-" + row["fixture_id"], "kind": "featured board"}]
                           + [{"name": q["source_name"], "url": q["public_url"], "kind": "bookmaker/exchange quote",
                               "detail": f"{q['names_at_source'][0]} {q['decimal_a']} / {q['names_at_source'][1]} {q['decimal_b']} · read {q['retrieved_utc']}"}
                              for q in row["featured"]["quotes"]]
                           + ([{"name": "Valve VRS (featured board rating input)",
                                "url": fx["vrs"]["page_url"], "kind": "official Valve rating"}]
                              if (fx.get("vrs") or {}).get("page_url") and fx.get("model") else []),
                "flags": [f for f in row["featured"]["flags"] if not f.startswith("no_line")]}
            continue
        row["resolution"] = resolve_fallback(row, expanded_by_id, egw_by_id, fresh_quotes,
                                             idx, ambiguous, prior_points, k)
    rows.sort(key=lambda r: (r["lock_utc"] or r["start_utc"], r["fixture_id"]))
    counts = {}
    for r in rows:
        counts[r["resolution"]["level"]] = counts.get(r["resolution"]["level"], 0) + 1
    return {
        "session": "af573ff1", "generated_utc": core.to_iso(now),
        "inputs": {"featured_board_generated_utc": featured.get("generated_utc"),
                   "expanded_lines_generated_utc": expanded.get("generated_at_utc"),
                   "egamersworld_generated_utc": egw.get("generated_at_utc"),
                   "fresh_snapshot_generated_utc": (fresh or {}).get("collected_to_utc"),
                   "access_log": (fresh or {}).get("access_log") or {}},
        "calibration": {"k": k, "source": "featured board calibration (market-fitted Valve VRS slope)",
                        "pairs_used": (featured.get("calibration") or {}).get("pairs_used")},
        "prior": {"points": prior_points, "n_global_vrs_teams": len(global_rows),
                  "basis": "lowest points value in the official Valve global standings file used"},
        "summary": {"open": len(rows), "with_pick": sum(1 for r in rows if r["resolution"]["level"] != "no_information"),
                    "no_information": counts.get("no_information", 0),
                    "featured": counts.get("featured", 0),
                    "fallback_market": counts.get("fallback_market", 0),
                    "fallback_model": counts.get("fallback_model", 0),
                    "fallback_single_rating": counts.get("fallback_single_rating", 0),
                    "locked_recent": len(featured.get("locked_recent") or [])},
        "rows": rows}


def resolve_fallback(row, expanded_by_id, egw_by_id, fresh_quotes, idx, ambiguous, prior_points, k):
    flags, sources = [], []
    fx = {"team_a": row["team_a"], "team_b": row["team_b"], "start_utc": row["start_utc"]}

    # ---- F1a: expanded-board market consensus (Melbet 1xBet platform, alias-joined there)
    ex = expanded_by_id.get(row["fixture_id"])
    if ex and ex.get("consensus") and ex.get("quotes"):
        cons = ex["consensus"]
        prob_a = float(cons["prob_a"])
        for q in ex["quotes"]:
            sources.append({"name": q["source_name"], "url": q["source_public_url"], "kind": "bookmaker quote (expanded board)",
                            "detail": f"{q['team_a_name']} {q['decimal_odds_a']} / {q['team_b_name']} {q['decimal_odds_b']} · read {q['retrieved_at_utc']} · aliases: {', '.join(q.get('aliases_applied') or []) or 'none'}"})
        flags.append("featured_board_no_line_alias_join")
        return _pick(row, "fallback_market", "Fallback market — bookmaker price under a verified team alias",
                     prob_a, sources, flags)

    # ---- F1b: this session's fresh Melbet/Kalshi quotes
    best = {}
    for q in fresh_quotes:
        if q.get("live"):
            continue
        nv = core.no_vig(q["decimal_a"], q["decimal_b"])
        if not nv:
            continue
        j = core.match_quote(fx, {**q, "prob_a": nv["prob_a"]})
        if not j:
            continue
        cand = {**q, "join": j, "prob_team_a": core.oriented_prob({"prob_a": nv["prob_a"]}, j["swapped"])}
        cur = best.get(q["source_key"])
        if cur is None or (j["start_diff_h"] or 99) < (cur["join"]["start_diff_h"] or 99):
            best[q["source_key"]] = cand
    if best:
        entries = list(best.values())
        prob_a = sum(e["prob_team_a"] for e in entries) / len(entries)
        for e in entries:
            sources.append({"name": e["source_name"], "url": e["public_url"], "kind": "bookmaker/exchange quote (fresh fallback collection)",
                            "detail": f"{e['team_a']} {e['decimal_a']} / {e['team_b']} {e['decimal_b']} · read {e['retrieved_utc']}"})
            for note in e["join"]["alias_notes"]:
                flags.append("alias_join:" + e["source_key"])
                sources.append({"name": "Alias evidence", "url": (e["join"]["evidence_urls"] or [LOBBY])[0],
                                "kind": "identity evidence", "detail": note})
        return _pick(row, "fallback_market", "Fallback market — bookmaker/exchange price (fresh collection)",
                     prob_a, sources, flags)

    # ---- F1c: EGamersWorld widget (aggregator; placeholders already rejected by no_vig)
    eg = egw_by_id.get(row["fixture_id"])
    if eg:
        nv = core.no_vig(eg.get("decimal_odds_a"), eg.get("decimal_odds_b"))
        if nv:
            sources.append({"name": "EGamersWorld odds widget", "url": eg["source_url"],
                            "kind": "odds aggregator widget (bookmaker not named in capture)",
                            "detail": f"{eg['decimal_odds_a']} / {eg['decimal_odds_b']} · read {eg['retrieved_at_utc']} · {eg.get('join_note') or ''}"})
            flags.append("single_aggregator_source_may_be_stale")
            return _pick(row, "fallback_market", "Fallback market — odds-aggregator widget (single source)",
                         nv["prob_a"], sources, flags)
        flags.append("egamersworld_placeholder_rejected")

    # ---- ratings for F2/F3
    ra, ea, na, ua = rating_for(row["team_a"], idx, ambiguous)
    rb, eb, nb, ub = rating_for(row["team_b"], idx, ambiguous)
    for side, rec, err, note, url in (("a", ra, ea, na, ua), ("b", rb, eb, nb, ub)):
        if note:
            sources.append({"name": "Alias evidence", "url": url or LOBBY, "kind": "identity evidence", "detail": note})
        if rec:
            sources.append({"name": f"Valve VRS — {rec['team']} #{rec['standing']} ({rec['points']} pts)",
                            "url": f"{VRS_REPO_URL}/blob/main/{rec['details_path']}" if rec.get("details_path") else VRS_REPO_URL,
                            "kind": "official Valve rating", "detail": f"roster: {rec.get('roster') or ''}"})
    if ra and rb:
        prob_a = core.vrs_prob(ra["points"], rb["points"], k)
        flags.append("vrs_model_after_alias_resolution")
        return _pick(row, "fallback_model", "Fallback model — Valve VRS ratings (alias-resolved, calibrated curve)",
                     prob_a, sources, flags)
    if (ra or rb) and prior_points is not None:
        rated_is_a = ra is not None
        prob_a = core.single_rating_prob((ra or rb)["points"], prior_points, k, rated_is_a)
        flags.append(f"single_rating_estimate:{row['team_b'] if rated_is_a else row['team_a']}_not_in_vrs")
        return _pick(row, "fallback_single_rating",
                     "Fallback estimate — one Valve VRS rating vs unrated-team prior (shrunk, capped, low confidence)",
                     prob_a, sources, flags, force_confidence="Low")
    flags.append("no_verified_information")
    return {"level": "no_information", "basis_label": "No verified information — 50/50 coin flip, do not treat as an edge",
            "prob_a": 0.5, "prob_b": 0.5, "pick_team": row["team_a"], "pick_side": "a",
            "pick_prob": 0.5, "confidence": "None", "sources": sources or
            [{"name": "HotSpawn lobby (fixture only)", "url": LOBBY, "kind": "fixture discovery"}],
            "flags": sorted(set(flags))}


def _pick(row, level, label, prob_a, sources, flags, force_confidence=None):
    prob_a = float(min(max(prob_a, 0.01), 0.99))
    side = "a" if prob_a >= 0.5 else "b"
    p_pick = max(prob_a, 1 - prob_a)
    return {"level": level, "basis_label": label, "prob_a": round(prob_a, 4), "prob_b": round(1 - prob_a, 4),
            "pick_team": row["team_a"] if side == "a" else row["team_b"], "pick_side": side,
            "pick_prob": round(p_pick, 4),
            "confidence": force_confidence or core.confidence_label(p_pick),
            "sources": sources, "flags": sorted(set(flags))}


# ----------------------------------------------------------------------- render
CSS = """
:root{--bg:#0f1218;--card:#171b23;--line:#262c38;--txt:#e8ebf1;--mut:#9aa3b2;--acc:#3ddc97;
--acc2:#5aa9ff;--warn:#ffb547;--bad:#ff6b6b;--feat:#1f6f4d;--fb:#245a85;--low:#5b4c1c}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:var(--acc2)}header{position:sticky;top:0;z-index:5;background:#0b0e13;border-bottom:1px solid var(--line)}
.bar{max-width:900px;margin:0 auto;padding:10px 14px;display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center}
.brand{font-weight:700;margin-right:auto}.bar nav{display:flex;gap:6px;flex-wrap:wrap}
.bar nav a{padding:8px 11px;border-radius:8px;text-decoration:none;color:var(--txt);background:#1c212b;font-size:14px;min-height:40px;display:inline-flex;align-items:center}
.bar nav a.on{background:var(--acc);color:#04130c;font-weight:700}
main{max-width:900px;margin:0 auto;padding:14px}h1{font-size:23px;margin:6px 0 6px;line-height:1.25}h2{font-size:19px;margin:26px 0 8px}
.mut{color:var(--mut)}.small{font-size:13px;color:var(--mut)}
.exec{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--acc);border-radius:12px;padding:14px;margin:12px 0}
.exec b.big{font-size:20px}.btn{display:inline-block;background:var(--acc);color:#04130c;font-weight:700;text-decoration:none;
padding:12px 16px;border-radius:10px;margin:6px 8px 2px 0;min-height:48px}
.btn.ghost{background:#1c212b;color:var(--txt);border:1px solid var(--line)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin:12px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}.stat b{display:block;font-size:22px}
.tools{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0;position:sticky;top:52px;background:var(--bg);padding:6px 0;z-index:4}
.tools input{flex:1 1 200px;padding:11px;border-radius:8px;border:1px solid var(--line);background:#11151c;color:var(--txt);font-size:16px}
.chip{padding:9px 12px;border-radius:999px;border:1px solid var(--line);background:#11151c;color:var(--txt);font-size:14px;cursor:pointer;min-height:44px}
.chip.on{background:var(--acc2);color:#031326;font-weight:700}
.match{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:0 0 12px}
.match .when{font-size:13px;color:var(--mut)}
.teamrow{display:flex;align-items:center;gap:8px;margin:8px 0 2px}.teamrow .nm{flex:1;font-size:17px;min-width:0}
.teamrow.pk .nm{font-weight:800;color:var(--acc)}.pct{font-variant-numeric:tabular-nums;font-weight:700;font-size:17px}
.meter{height:8px;background:#2a303c;border-radius:4px;overflow:hidden}.meter i{display:block;height:100%;background:var(--acc)}
.meter.b i{background:#4a5568}
.pickline{margin-top:10px;font-size:17px}.badge{display:inline-block;padding:3px 9px;border-radius:999px;font-size:12.5px;font-weight:700;vertical-align:middle}
.b-pick{background:var(--acc);color:#04130c}.b-featured{background:var(--feat);color:#eafff3}.b-fallback_market{background:var(--fb);color:#eaf4ff}
.b-fallback_model{background:#3a4a6b;color:#eaf4ff}.b-fallback_single_rating{background:var(--low);color:#ffe9ad}.b-no_information{background:#5b2b2b;color:#ffd7d7}
.src{font-size:13.5px}.src a{display:inline-block;margin:2px 8px 2px 0}
.note{background:#151a22;border-left:3px solid var(--acc2);padding:10px 12px;border-radius:6px;margin:10px 0}
.foot{margin:30px 0 10px;color:var(--mut);font-size:13px}table{width:100%;border-collapse:collapse}
td,th{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;font-size:14px}
@media (max-width:640px){.tools{top:0}.teamrow .nm{font-size:16px}}
"""

JS = """
(function(){
 function fmt(iso){var d=new Date(iso);if(isNaN(d))return iso;return d.toLocaleString([], {weekday:'short',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});}
 function rel(iso){var s=(new Date(iso)-new Date())/1000,a=Math.abs(s),t;if(a<3600)t=Math.round(a/60)+' min';else if(a<172800)t=(a/3600).toFixed(1)+' h';else t=Math.round(a/86400)+' d';return s>=0?'locks in '+t:'locked '+t+' ago';}
 document.querySelectorAll('[data-t]').forEach(function(e){e.textContent=fmt(e.dataset.t);e.title=e.dataset.t+' (UTC)';});
 document.querySelectorAll('[data-r]').forEach(function(e){e.textContent=rel(e.dataset.r);e.title=e.dataset.r+' (UTC)';});
 var q=document.getElementById('q'),cards=[].slice.call(document.querySelectorAll('[data-row]')),count=document.getElementById('count'),mode='all';
 function apply(){var s=(q&&q.value||'').toLowerCase(),n=0;cards.forEach(function(r){var ok=!s||r.dataset.s.indexOf(s)>=0;
  if(mode==='soon')ok=ok&&(new Date(r.dataset.lock)-new Date())/3600000<24&&new Date(r.dataset.lock)>new Date();
  else if(mode!=='all')ok=ok&&r.dataset.level===mode;
  r.style.display=ok?'':'none';if(ok)n++;});if(count)count.textContent=n;}
 if(q)q.addEventListener('input',apply);
 document.querySelectorAll('.chip').forEach(function(c){c.addEventListener('click',function(){
  document.querySelectorAll('.chip').forEach(function(x){x.classList.remove('on')});c.classList.add('on');mode=c.dataset.m;apply();});});
})();
"""

NAV = [("index.html", "📱 All picks"), ("method.html", "Method & sources"),
       ("flagged.html", "Flagged for review"), ("../index.html", "Main dashboard"),
       ("../ourline/index.html", "Featured picks")]


def page(title, active, body, board):
    nav = "".join(f'<a href="{h}"{" class=on" if h == active else ""}>{t}</a>' for h, t in NAV)
    gen = board["generated_utc"]
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Picks for every match · HotSpawn CS2</title><style>{CSS}</style></head><body>
<header><div class="bar"><div class="brand">🎯 Picks for every match</div><nav>{nav}</nav></div></header>
<main>{body}
<p class="foot">Board generated {esc(gen)} UTC (<span data-r="{esc(gen)}"></span>) from the featured board
({esc(board["inputs"]["featured_board_generated_utc"])}) plus fallback sources read at the times shown on each match.
Probabilities are estimates derived from external bookmaker/exchange prices and Valve's official VRS ratings;
HotSpawn crowd picks are never used. Not affiliated with HotSpawn or any bookmaker. Not betting advice. 18+.</p>
</main><script>{JS}</script></body></html>"""


def pct(p):
    return f"{p * 100:.1f}%" if isinstance(p, (int, float)) else "—"


LEVEL_TXT = {"featured": "⭐ Featured", "fallback_market": "Fallback market", "fallback_model": "Fallback VRS model",
             "fallback_single_rating": "Single-rating estimate", "no_information": "No information"}


def match_card(r):
    z = r["resolution"]
    pa, pb = z["prob_a"], z["prob_b"]
    src = "".join(f'<a href="{esc(s["url"])}" rel="noopener">{esc(s["name"])}</a>' for s in z["sources"][:8])
    flags = ""
    if z["flags"]:
        flags = (f' <a class="badge b-no_information" href="flagged.html#f-{esc(r["fixture_id"])}">'
                 f'{len(z["flags"])} flag{"s" if len(z["flags"]) > 1 else ""}</a>')
    search = f'{r["team_a"]} {r["team_b"]} {r.get("competition") or ""}'.lower()
    return f"""<article class="match" data-row data-s="{esc(search)}" data-lock="{esc(r["lock_utc"] or r["start_utc"])}" data-level="{esc(z["level"])}" id="m-{esc(r["fixture_id"])}">
<div class="when"><span data-t="{esc(r["start_utc"])}">{esc(r["start_utc"])}</span> · <span data-r="{esc(r["lock_utc"] or r["start_utc"])}"></span> · {esc(r.get("competition"))} · Tier {esc(r.get("tier") or "?")} · {esc(r.get("points"))} pts</div>
<div class="teamrow{' pk' if z["pick_side"] == "a" else ""}"><span class="nm">{esc(r["team_a"])}{' <span class="badge b-pick">PICK</span>' if z["pick_side"] == "a" else ""}</span><span class="pct">{pct(pa)}</span></div>
<div class="meter"><i style="width:{pa * 100:.1f}%"></i></div>
<div class="teamrow{' pk' if z["pick_side"] == "b" else ""}"><span class="nm">{esc(r["team_b"])}{' <span class="badge b-pick">PICK</span>' if z["pick_side"] == "b" else ""}</span><span class="pct">{pct(pb)}</span></div>
<div class="meter b"><i style="width:{pb * 100:.1f}%"></i></div>
<div class="pickline">Pick: <b>{esc(z["pick_team"])}</b> · {pct(z["pick_prob"])} · {esc(z["confidence"] or "")}
 <span class="badge b-{esc(z["level"])}">{esc(LEVEL_TXT.get(z["level"], z["level"]))}</span>{flags}</div>
<div class="small">{esc(z["basis_label"])}</div>
<div class="src"><a href="{esc(r["hotspawn_url"])}" rel="noopener">HotSpawn {esc(r["hotspawn_url_kind"])}</a>{src}</div>
</article>"""


def render_index(b):
    s = b["summary"]
    body = f"""
<h1>Every open HotSpawn CS2 match — with a pick</h1>
<section class="exec" aria-label="Executive summary">
<p><b class="big">Executive summary — start here.</b></p>
<p><b>{s["with_pick"]} of {s["open"]} open matches have a pick</b> ({s["featured"]} featured,
{s["fallback_market"]} fallback-market, {s["fallback_model"]} fallback-model,
{s["fallback_single_rating"]} single-rating estimate{s[", plus " + str(s["no_information"]) + " with no verified information (50/50, flagged)"] if s["no_information"] else ""}).
This page is the updated list of picks. It is rebuilt automatically whenever the featured board refreshes
(about every 30 minutes) and re-checks the HotSpawn lobby for new matches — no manual input.</p>
<p>
<a class="btn" href="#picks">⬇ All picks (this page)</a>
<a class="btn ghost" href="../ourline/index.html">⭐ Featured picks only</a>
<a class="btn ghost" href="../probabilities.html">Strict bookmaker-priced board</a>
<a class="btn ghost" href="method.html">How each pick is made</a>
<a class="btn ghost" href="flagged.html">Flagged for review</a>
<a class="btn ghost" href="../index.html">Main dashboard</a>
</p>
<p class="small">How to read a card: the team marked <span class="badge b-pick">PICK</span> is the pick; the
percentage is our originated win probability for that team. ⭐ Featured picks come from bookmaker lines on the
featured board. Fallback picks are used <b>only</b> where no featured line exists, and are labelled with the
exact source used — a bookmaker price found under a verified alias, Valve VRS ratings, or a low-confidence
single-rating estimate. HotSpawn crowd percentages are never used.</p>
</section>
<div class="stats">
<div class="stat"><b>{s["open"]}</b><span>open matches</span></div>
<div class="stat"><b>{s["with_pick"]}/{s["open"]}</b><span>with a pick</span></div>
<div class="stat"><b>{s["featured"]}</b><span>featured</span></div>
<div class="stat"><b>{s["fallback_market"] + s["fallback_model"] + s["fallback_single_rating"]}</b><span>fallback-resolved</span></div>
<div class="stat"><b>{s["no_information"]}</b><span>no information</span></div>
</div>
<div class="tools"><input id="q" type="search" placeholder="Search team or tournament…" aria-label="Search">
<button class="chip on" data-m="all">All</button><button class="chip" data-m="soon">Locks &lt; 24h</button>
<button class="chip" data-m="featured">⭐ Featured</button><button class="chip" data-m="fallback_market">Fallback market</button>
<button class="chip" data-m="fallback_model">Fallback model</button><button class="chip" data-m="fallback_single_rating">Low-confidence</button></div>
<p class="small">Showing <span id="count">{s["open"]}</span> of {s["open"]} · sorted by pick-lock time · times in your local time zone</p>
<div id="picks">{"".join(match_card(r) for r in b["rows"]) if b["rows"] else '<p class="note">No open CS2 fixtures were found in the lobby on this run.</p>'}</div>
"""
    return page("All picks", "index.html", body, b)


def render_flagged(b):
    rows = []
    for r in b["rows"]:
        z = r["resolution"]
        if not z["flags"] and z["level"] not in ("fallback_single_rating", "no_information"):
            continue
        src = "<br>".join(f'<a href="{esc(s["url"])}">{esc(s["name"])}</a>' for s in z["sources"][:6])
        rows.append(f'<tr id="f-{esc(r["fixture_id"])}"><td>{esc(r["team_a"])} vs {esc(r["team_b"])}<br>'
                    f'<span class="small">{esc(r.get("competition"))} · {esc(r["start_utc"])}</span></td>'
                    f'<td>{esc(LEVEL_TXT.get(z["level"], z["level"]))}<br><span class="small">{esc("; ".join(z["flags"]))}</span></td>'
                    f'<td>{esc(z["pick_team"])} {pct(z["pick_prob"])}</td><td class="src">{src}</td></tr>')
    body = f"""
<h1>Flagged for review</h1>
<p>Every fallback-resolved or unverified row, with the source links used. Fallback picks are published
because a pick was requested for every match; they are <b>not</b> featured-grade. A row here does not block
the featured board, which still leaves these matches blank.</p>
<table><thead><tr><th>Match</th><th>Level / flags</th><th>Pick</th><th>Sources</th></tr></thead>
<tbody>{"".join(rows) or '<tr><td colspan="4">No flagged fallback rows on this run.</td></tr>'}</tbody></table>
<h2>Known irregularities carried forward</h2>
<div class="note"><b>EGamersWorld 1.80/1.80</b> is a widget placeholder (opponent field blank in the capture),
documented in <a href="../data/current_board.json">data/current_board.json</a> irregularities — rejected here, never priced.</div>
<div class="note"><b>HLTV</b> is used only as identity evidence (team pages/roster checks, linked per alias).
Automated reads of HLTV return 403 to the collectors, so no HLTV number enters any probability; the probe
result is recorded in the access log inside <a href="../data/af573ff1/board.json">data/af573ff1/board.json</a>
(and in data/af573ff1/snapshot.json after a fresh collection run).</div>
<div class="note"><b>Aliases</b> (WROTBERRY = WBT/WhiteBIT Team, RoundsGG = ROUNDS, EAC = EA Copenhagen) are
evidence-linked on each affected row and on the <a href="method.html#aliases">method page</a>. LFO 7/8/9 are
different rosters from LFO 10 and are never used as its rating.</div>
"""
    return page("Flagged for review", "flagged.html", body, b)


def render_method(b):
    cal, prior = b["calibration"], b["prior"]
    body = f"""
<h1>Method &amp; sources</h1>
<h2>Resolution order (fallback sources only where the featured board has no line)</h2>
<table><thead><tr><th>Level</th><th>What it means</th><th>Confidence</th></tr></thead><tbody>
<tr><td>⭐ Featured</td><td>Copied verbatim from the <a href="../ourline/index.html">featured Our-line board</a>:
Pinnacle/Bovada/Melbet/Kalshi no-vig consensus blended with the Valve VRS model. This board never changes it.</td><td>As published there</td></tr>
<tr><td>Fallback market</td><td>An external price the featured join missed, found under a published alias:
the expanded board's Melbet (1xBet platform) quotes, this board's fresh Melbet/Kalshi collection, or the
EGamersWorld widget. Both teams + start time (≤90 min) must match; the 1.80/1.80 widget placeholder is rejected.</td><td>Market-grade, single source unless stated</td></tr>
<tr><td>Fallback model</td><td>Valve VRS expected-win curve after alias resolution, using the featured board's
market-fitted slope k = {cal["k"]:.3f} (fitted on {cal["pairs_used"]} priced fixtures; source: featured board calibration).</td><td>Model estimate</td></tr>
<tr><td>Single-rating estimate</td><td>Only one team is in any Valve standings file. The unrated team is assigned
the lowest points value in the official global file ({prior["points"]} pts across {prior["n_global_vrs_teams"]} global rows) as a
population prior; the raw probability is then shrunk toward 50/50 (logit × {core.SINGLE_RATING_SHRINK}) and clamped to
{core.SINGLE_RATING_CLAMP[0]:.0%}–{core.SINGLE_RATING_CLAMP[1]:.0%}. This only ever makes the estimate more conservative.</td><td>Low — always labelled</td></tr>
<tr><td>No information</td><td>No price and no usable rating for either team. Shown as 50/50; the "pick" is the
first-listed team and is labelled a coin flip. It carries no edge and is counted separately above.</td><td>None</td></tr>
</tbody></table>
<h2 id="aliases">Alias evidence</h2>
<table><thead><tr><th>Source/VRS name</th><th>HotSpawn name</th><th>Evidence</th></tr></thead><tbody>
{"".join(f'<tr><td>{esc(k)}</td><td>{esc(v[0])}</td><td>{esc(v[1])} <a href="{esc(v[2])}">source</a></td></tr>' for k, v in sorted(core.ALIASES.items()))}
</tbody></table>
<h2>Sources</h2>
<p>Fixtures: <a href="https://play.hotspawn.com/lobby">HotSpawn Pick'ems lobby</a> (discovery only; crowd % never used).
Featured lines: <a href="../ourline/index.html">Our-line board</a> and its <a href="../ourline/sources.html">source list</a>.
Fallback prices: <a href="https://melbet.com/en/line/esports">Melbet LineFeed</a>,
<a href="https://kalshi.com/markets/kxcs2game">Kalshi KXCS2GAME</a>,
<a href="https://egamersworld.com/counterstrike/matches">EGamersWorld widget</a> (aggregator, labelled).
Ratings: <a href="{VRS_REPO_URL}">Valve CS2 Regional Standings (official)</a> global + regional files.
Identity checks: HLTV team pages linked per alias (read manually; automation is blocked and that is recorded, not bypassed).
Match-list cross-check: <a href="https://bo3.gg/matches/current">bo3.gg</a> upcoming-fixtures API (probe in the fresh snapshot access log).</p>
<h2>Updates</h2>
<p><code>.github/workflows/picks-every-match-af573ff1.yml</code> runs on a schedule, after the featured board
refreshes, and on demand: it re-checks the HotSpawn lobby/API for new open fixtures, refreshes fallback
Melbet/Kalshi quotes and Valve ratings, rebuilds this board, runs the tests, commits only
<code>data/af573ff1/**</code> and <code>picks-every-match/**</code>, and dispatches the Pages workflow.
If a source is unreachable, its access log records the failure and the last committed inputs are reused —
staleness is shown from the read times on each row, never hidden.</p>
"""
    return page("Method & sources", "method.html", body, b)


def main() -> int:
    featured = load(ROOT / "data/f7279a54/board.json", {})
    featured["_snapshot_vrs"] = (load(ROOT / "data/f7279a54/snapshot.json", {}) or {}).get("vrs") or {}
    expanded = load(ROOT / "data/expanded/lines.json", {})
    egw = load(ROOT / "data/cs2_odds_egamersworld.json", {})
    fresh = load(DATA / "snapshot.json", None)
    board = build_board(featured, expanded, egw, fresh)
    DATA.mkdir(parents=True, exist_ok=True)
    SITE.mkdir(parents=True, exist_ok=True)
    (DATA / "board.json").write_text(json.dumps(board, indent=1) + "\n")
    (SITE / "index.html").write_text(render_index(board))
    (SITE / "flagged.html").write_text(render_flagged(board))
    (SITE / "method.html").write_text(render_method(board))
    print(json.dumps(board["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
