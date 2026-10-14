#!/usr/bin/env python3
"""Every captured open CS2 fixture: market first, verified-rating fallback, otherwise blank.
No slot identity guesses, sibling/floor ratings or ticker-derived kickoffs.
"""
from __future__ import annotations
import html, json, re, sys
from datetime import timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "c64a5e19"
SITE = ROOT / "picks-every-match"
LOBBY = "https://play.hotspawn.com/lobby"
LIQUIPEDIA_ELISA = "https://liquipedia.net/counterstrike/Elisa/BreakOut_Series/2"
HLTV_ROUNDS = "https://www.hltv.org/team/12457/roundsgg"
HLTV_EAC = "https://www.hltv.org/team/13838/eac"
HLTV_WBT_ACAD = "https://www.hltv.org/team/13999/wbt-academy"

def esc(v): return html.escape("" if v is None else str(v), quote=True)
def load(p, d):
    try: return json.loads(Path(p).read_text())
    except (OSError, ValueError): return d
def pct(p): return f"{p*100:.1f}%" if isinstance(p, (int, float)) else "—"

def rating_index(vrs):
    """Different rosters sharing a name cannot be resolved by last match date."""
    groups = {}
    for team in vrs.get("teams", []):
        key, _ = core.canon(team["team"])
        if key: groups.setdefault(key, []).append(team)
    return ({k: v[0] for k, v in groups.items() if len(v) == 1},
            {k: v for k, v in groups.items() if len(v) > 1})


def rating_for(name, idx, dup):
    key, _ = core.canon(name)
    if key in dup: return None, "ambiguous_vrs_roster"
    return (idx[key], None) if key in idx else (None, "no_verified_vrs_rating")


def kalshi_start_from_ticker(event_id):
    # Ticker timezone/semantics are not confirmed by a kickoff field.
    return None


def build_board(snap, snap_source):
    """All captured open lobby rows; current markets first, sourced ratings only as fallback."""
    now = core.parse_iso(snap["collected_to_utc"])
    if now is None: raise ValueError("Snapshot requires a timezone-qualified observation")
    hs = snap["hotspawn"]; vrs = snap.get("vrs") or {}
    meta = (snap.get("access_log") or {}).get("hotspawn_lobby_page") or {}
    observed = core.parse_iso(snap.get("hotspawn_fallback_from") or meta.get("at_utc"))
    try: cache_age = max(0, int(meta.get("age_header") or 0))
    except (ValueError, TypeError): cache_age = 14401
    age = (now - observed).total_seconds() + cache_age if observed else None
    fresh = age is not None and 0 <= age <= 14400
    vdate = core.parse_iso(str(vrs.get("snapshot") or "").replace("_", "-") + "T00:00:00Z")
    vfresh = vdate is not None and 0 <= (now-vdate).total_seconds() <= 14*86400
    idx, dup = rating_index(vrs)
    quotes = [q for raw in snap.get("quotes", []) if (q := core.rederive_quote(raw)) is not None]
    rows = []; locked = 0
    for fx in hs["fixtures"]:
        if "lobby_page" not in fx.get("seen_in", []): continue
        lock = core.parse_iso(fx.get("lock_utc")) or core.parse_iso(fx.get("start_utc"))
        if fx.get("status") != "scheduled" or not lock or lock <= now:
            locked += 1; continue
        url = (hs.get("permalinks") or {}).get(fx["fixture_id"]) or LOBBY
        row = {**fx, "state": "open", "hotspawn_url": url,
               "hotspawn_url_kind": "lobby" if url == LOBBY else "match page", "flags": []}
        if not fresh: row["flags"].append("fixture_observation_stale_or_unverified")
        chosen = {}
        for q in quotes:
            if q.get("live"): continue
            join = core.match_quote(fx, q)
            if not join: continue
            if join.get("rejected"):
                row["flags"].append("unverified_or_mismatched_kickoff:" + q["source_key"]); continue
            at = core.parse_iso(q.get("retrieved_utc"))
            if not fresh or at is None or not 0 <= (now-at).total_seconds() <= 14400:
                row["flags"].append("stale_or_unverified_quote:" + q["source_key"]); continue
            old = chosen.get(q["source_key"])
            if old is None or join["start_diff_h"] < old["join"]["start_diff_h"]:
                chosen[q["source_key"]] = {**q, "join": join, "prob_team_a": core.oriented_prob(q, join["swapped"])}
        row["quotes"] = [{**{k:q[k] for k in ("source_key", "source_name", "public_url", "api_url", "event_id", "raw_format", "raw_a", "raw_b", "decimal_a", "decimal_b", "retrieved_utc")},
            "names_at_source": [q["team_a"], q["team_b"]], "no_vig_prob_team_a": round(q["prob_team_a"], 4),
            "swapped": q["join"]["swapped"], "start_utc_at_source": q.get("start_utc"),
            "start_diff_h": q["join"]["start_diff_h"], "alias_notes": q["join"]["alias_notes"]} for q in chosen.values()]
        market = core.consensus([{"source_key": k, "prob_a": q["prob_team_a"]} for k,q in chosen.items()])
        row["market"] = market
        ra, ea = rating_for(fx["team_a"], idx, dup); rb, eb = rating_for(fx["team_b"], idx, dup)
        row["vrs"] = {"team_a": ra, "team_b": rb, "snapshot": vrs.get("snapshot"), "page_url": vrs.get("page_url")}
        row["_delta"] = ra["points"]-rb["points"] if ra and rb and vfresh and fresh else None
        if not market:
            for name, err in ((fx["team_a"], ea), (fx["team_b"], eb)):
                if err: row["flags"].append(err + ":" + name)
            if not vfresh: row["flags"].append("vrs_snapshot_stale_or_unverified")
        deadline = min(lock, observed + timedelta(seconds=14400-cache_age)) if observed else now
        if chosen: deadline = min(deadline, *(core.parse_iso(q["retrieved_utc"])+timedelta(hours=4) for q in chosen.values()))
        if not market and vdate: deadline = min(deadline, vdate+timedelta(days=14))
        row["valid_until_utc"] = core.to_iso(deadline)
        rows.append(row)
    pairs = [{"delta":r["_delta"], "market_prob_a":r["market"]["prob_a"]} for r in rows if r["market"] and r["_delta"] is not None]
    cal = core.fit_calibration(pairs)
    for row in rows:
        delta = row.pop("_delta"); market = row["market"]
        # Model guidance is fallback-only. It never changes a sourced market pick.
        mp = core.vrs_prob(delta, 0, cal["k"]) if not market and delta is not None else None
        row["model"] = {"prob_a":round(mp,4), "prob_b":round(1-mp,4), "delta_points":delta, "k":round(cal["k"],4)} if mp is not None else None
        line = core.blend(market["prob_a"] if market else None, market["n_sources"] if market else 0, mp)
        row["line"] = None; row["fallback"] = None
        if line:
            pa = line["prob_a"]; pb = line["prob_b"]; side = "a" if pa >= pb else "b"
            row["line"] = {**line, "tier":"A" if market else "B", "prob_a":round(pa,4), "prob_b":round(pb,4),
                "pick_side":side, "pick_team":row["team_"+side], "pick_prob":round(max(pa,pb),4),
                "confidence":core.confidence_label(max(pa,pb)), "fair_decimal_a":round(1/pa,3), "fair_decimal_b":round(1/pb,3),
                "fair_american_a":core.decimal_to_american(1/pa), "fair_american_b":core.decimal_to_american(1/pb)}
            if pa == pb: row["flags"].append("equal_probability_no_edge")
        else: row["flags"].append("no_line_unverified")
        if not market and line: row["flags"].append("model_estimate_not_verified_win_probability")
        row["flags"] = sorted(set(row["flags"]))
        row["sources"] = [{"label":"HotSpawn " + row["hotspawn_url_kind"], "url":row["hotspawn_url"]}]
        row["sources"] += [{"label":q["source_name"], "url":q["public_url"]} for q in row["quotes"]]
        if vrs.get("page_url"): row["sources"].append({"label":"Valve official standings", "url":vrs["page_url"]})
    rows.sort(key=lambda r:(r["lock_utc"] or r["start_utc"], r["fixture_id"]))
    a = sum(bool(r["market"]) for r in rows); b = sum(bool(r["model"]) for r in rows)
    return {"session":"c64a5e19", "policy":"strict-market-first-49a181f8", "generated_utc":snap["collected_to_utc"],
        "snapshot_source":snap_source, "snapshot_session":snap.get("session"), "week":hs.get("week"),
        "fixture_observation_age_seconds":age, "hotspawn_fallback_from":snap.get("hotspawn_fallback_from"),
        "summary":{"open":len(rows), "with_pick":a+b, "tier_a_market":a, "tier_b_model":b, "tier_c_fallback":0, "tier_d_none":len(rows)-a-b, "locked_or_past_listed":locked},
        "calibration":{**cal, "pairs_used":len(pairs)}, "vrs":{k:vrs.get(k) for k in ("snapshot", "page_url", "api_url")}, "open":rows, "access":snap.get("access_log", {})}

# ------------------------------------------------------------------ rendering
CSS = """
:root{--bg:#0f1218;--card:#171b23;--line:#262c38;--txt:#e8ebf1;--mut:#9aa3b2;--acc:#3ddc97;--acc2:#5aa9ff;--warn:#ffb547;--bad:#ff6b6b}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
[hidden]{display:none!important}a{color:var(--acc2)}a:focus-visible{outline:3px solid var(--acc2);outline-offset:3px}.bar nav a{min-height:44px;display:inline-flex;align-items:center}.team,td,.small{overflow-wrap:anywhere}header{position:sticky;top:0;z-index:5;background:#0b0e13;border-bottom:1px solid var(--line)}
.bar{max-width:1100px;margin:0 auto;padding:10px 14px;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}.brand{font-weight:700;margin-right:auto}
.bar nav{display:flex;gap:6px;flex-wrap:wrap}.bar nav a{padding:6px 10px;border-radius:8px;text-decoration:none;color:var(--txt);background:#1c212b;font-size:14px}.bar nav a.on{background:var(--acc);color:#04130c;font-weight:700}
main{max-width:1100px;margin:0 auto;padding:14px}h1{font-size:22px;margin:6px 0 4px}h2{font-size:18px;margin:26px 0 8px}.mut{color:var(--mut)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin:12px 0}.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}.stat b{display:block;font-size:22px}.stat span{color:var(--mut);font-size:13px}
.pickcard{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:8px 0}.pickcard .when{font-size:12.5px;color:var(--mut)}
.teams{display:flex;justify-content:space-between;gap:8px;margin:4px 0}.team{flex:1}.team.pk{font-weight:700;color:var(--acc)}.pct{font-variant-numeric:tabular-nums;font-weight:700}
.meter{height:6px;background:#2a303c;border-radius:4px;overflow:hidden;margin:2px 0 6px}.meter i{display:block;height:100%;background:var(--acc)}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:700}.b-A{background:#1f6f4d}.b-B{background:#245a85}.b-C{background:#5b3a12;color:#ffd9a3}.b-D{background:#5b2222}.b-flag{background:#5b3a12;color:#ffd9a3}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut);background:#131720}
.small{font-size:12.5px;color:var(--mut)}.note{background:#151a22;border-left:3px solid var(--acc2);padding:10px 12px;border-radius:6px;margin:10px 0}.warnbox{background:#221a10;border-left:3px solid var(--warn);padding:10px 12px;border-radius:6px;margin:10px 0}
.linkcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}.linkcard{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}.linkcard a{font-weight:700;font-size:16px}
.foot{margin:30px 0 10px;color:var(--mut);font-size:13px}code{background:#11151c;padding:1px 5px;border-radius:4px}
@media (max-width:760px){table.cards thead{display:none}table.cards tr{display:block;border-bottom:2px solid var(--line);padding:6px 0}table.cards td{display:block;border:none;padding:4px 10px}table.cards td:before{content:attr(data-l);display:block;font-size:11px;text-transform:uppercase;color:var(--mut);letter-spacing:.05em}}
"""
JS = """
(function(){function fmt(iso){var d=new Date(iso);if(isNaN(d))return iso;return d.toLocaleString([], {weekday:'short',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});}
function rel(iso){var s=(new Date(iso)-new Date())/1000,a=Math.abs(s),t;if(a<3600)t=Math.round(a/60)+' min';else if(a<172800)t=(a/3600).toFixed(1)+' h';else t=Math.round(a/86400)+' d';return s>=0?'in '+t:t+' ago';}
document.querySelectorAll('[data-t]').forEach(function(e){e.textContent=fmt(e.dataset.t);e.title=e.dataset.t+' (UTC)';});
document.querySelectorAll('[data-r]').forEach(function(e){e.textContent=rel(e.dataset.r);});
function expire(){document.querySelectorAll('[data-expiry]').forEach(function(row){if(Date.now()>=Date.parse(row.dataset.expiry)&&!row.dataset.expired){row.dataset.expired='true';row.querySelectorAll('[data-value]').forEach(function(e){e.textContent='— expired / refresh required';});row.querySelectorAll('.meter').forEach(function(e){e.hidden=true;});}});}
expire();setInterval(expire,30000);})();
"""
NAV = [("index.html", "⭐ Picks at a glance"), ("picks.html", "All picks (full table)"), ("flagged.html", "Flagged for review"), ("method.html", "Method & sources"), ("../index.html", "Main dashboard"), ("../ourline/index.html", "Our line board")]
BASIS_TXT = {"A": "A · Bookmaker market", "B": "B · VRS model only", "C": "C · Fallback (see flags)", "D": "D · No evidence"}
def page(title, active, body, board):
    nav = "".join(f'<a href="{h}"{" class=on" if h == active else ""}>{t}</a>' for h, t in NAV)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Every-match picks · HotSpawn CS2 Pick'ems</title><style>{CSS}</style></head><body>
<header><div class="bar"><div class="brand">🎯 Every-match picks · CS2 Pick'ems</div><nav>{nav}</nav></div></header>
<main>{body}
<p class="foot">Data collected {esc(board["generated_utc"])} UTC (<span data-r="{esc(board["generated_utc"])}"></span>) by an automated GitHub Actions run — no manual input. Probabilities are estimates derived from external bookmaker/exchange prices and Valve's official VRS ratings; HotSpawn crowd picks are never used. Rating fallbacks are estimates, not official win probabilities. Unsupported inputs stay blank. Not affiliated with HotSpawn or any bookmaker. Not betting advice. Section owner: session <code>c64a5e19</code>.</p>
</main><script>{JS}</script></body></html>
"""
def glance_card(r):
    ln = r["line"]
    if ln:
        pa, pb = ln["prob_a"], ln["prob_b"]
        meter = f'<div class="meter"><i style="width:{pa*100:.0f}%"></i></div>'
        pick = f'PICK: {esc(ln["pick_team"])} · {pct(ln["pick_prob"])} · {esc(ln["confidence"])}'
        badge = f'<span class="badge b-{ln["tier"]}">{esc(BASIS_TXT[ln["tier"]])}</span>'
    else:
        meter = ""; pick = 'NO PICK — insufficient evidence (flagged)'; badge = '<span class="badge b-D">D · No evidence</span>'
    return (f'<div class="pickcard" data-expiry="{esc(r["valid_until_utc"])}"><div class="when"><span data-t="{esc(r["start_utc"])}">{esc(r["start_utc"])}</span> · locks <span data-r="{esc(r["lock_utc"])}">{esc(r["lock_utc"])}</span> · {esc(r.get("competition"))} · Tier {esc(r.get("tier") or "?")}</div>'
            f'<div class="teams"><span class="team{" pk" if ln and ln["pick_side"]=="a" else ""}">{esc(r["team_a"])} <span class="pct" data-value>{pct(ln["prob_a"]) if ln else "—"}</span></span>'
            f'<span class="team{" pk" if ln and ln["pick_side"]=="b" else ""}" style="text-align:right">{esc(r["team_b"])} <span class="pct" data-value>{pct(ln["prob_b"]) if ln else "—"}</span></span></div>{meter}'
            f'<div><b data-value>{esc(pick)}</b> {badge} <a href="picks.html#m-{esc(r["fixture_id"])}">details &amp; sources →</a></div></div>')

def render_index(b):
    s = b["summary"]
    cards = "".join(glance_card(r) for r in b["open"])
    body = f"""
<h1>Executive summary — where the picks are</h1>
<p class="mut">You want one place that tells you, on your phone, who to pick in every HotSpawn CS2 Pick'ems match. <b>This page is that place.</b> Every captured open CS2 match is listed below. Supported picks have probabilities; missing or ambiguous evidence stays blank and flagged. It refreshes automatically (about every 30 minutes) — no manual input.</p>
<div class="stats">
<div class="stat"><b>{s["open"]}</b><span>matches open for picks</span></div>
<div class="stat"><b>{s["with_pick"]}</b><span>with a pick on this page</span></div>
<div class="stat"><b>{s["tier_a_market"]}</b><span>A · priced by bookmakers</span></div>
<div class="stat"><b>{s["tier_b_model"]}</b><span>B · VRS model only</span></div>
<div class="stat"><b>{s["tier_c_fallback"]}</b><span>unsupported shortcuts disabled</span></div>
<div class="stat"><b>{s["tier_d_none"]}</b><span>D · no evidence (blank)</span></div>
<div class="stat"><b><span data-r="{esc(b["generated_utc"])}">{esc(b["generated_utc"])}</span></b><span>last update ({esc(b["generated_utc"])} UTC)</span></div>
</div>
<h2>📱 On your phone — do this</h2>
<div class="note"><b>1.</b> Read the pick cards below (biggest, boldest team = our pick, % = win probability). <b>2.</b> Tap <i>details &amp; sources</i> on any match to see exactly which bookmaker prices / ratings produced the number. <b>3.</b> Matches marked <span class="badge b-B">B · Rating fallback</span> had no normal bookmaker price (low-tier or not listed on the usual sites) — they use only the extra documented sources on the <a href="method.html">method page</a> and are also listed on <a href="flagged.html">Flagged for review</a>. Treat them as low-confidence.</div>
<h2>Where to find updated picks (all pages on this site)</h2>
<div class="linkcards">
<div class="linkcard"><a href="index.html">⭐ This page — picks at a glance</a><p class="small">Every captured open match, supported picks and explicit gaps, mobile cards. Updated automatically. Start here.</p></div>
<div class="linkcard"><a href="picks.html">All picks — full table</a><p class="small">Same matches with market prices, VRS inputs, fair odds and a source link on every row.</p></div>
<div class="linkcard"><a href="../ourline/index.html">Our line board</a><p class="small">Independent market-first board with rating fallbacks and a graded track record.</p></div>
<div class="linkcard"><a href="../index.html">Main dashboard (strict)</a><p class="small">Only strictly eligible Pinnacle/Bovada prices; everything else blank + flagged. The conservative view.</p></div>
<div class="linkcard"><a href="../probabilities.html">Probabilities (strict, mobile)</a><p class="small">Strict-board probabilities in mobile table form; unpriced rows stay blank.</p></div>
<div class="linkcard"><a href="flagged.html">Flagged for review</a><p class="small">Every fallback pick, identity mismatch, thin book and unverified item, with source links.</p></div>
</div>
<h2>Picks at a glance — every open match ({s["open"]})</h2>
{cards if cards else '<p>No open CS2 fixtures in the lobby on this run.</p>'}
<p class="small">Snapshot provenance: {esc(b["snapshot_source"])} (session {esc(b.get("snapshot_session"))}). Fixture inventory: HotSpawn lobby (see <a href="method.html">method</a>). Times convert to your local time zone automatically.</p>
"""
    return page("Executive summary & picks at a glance", "index.html", body, b)

def render_picks(b):
    rows = []
    for r in b["open"]:
        ln = r["line"]
        if ln:
            teams = f'<b>{esc(r["team_a"])}</b> {pct(ln["prob_a"])} vs <b>{esc(r["team_b"])}</b> {pct(ln["prob_b"])}<div class="meter"><i style="width:{ln["prob_a"]*100:.0f}%"></i></div>'
            pick = f'<b>{esc(ln["pick_team"])}</b><br>{pct(ln["pick_prob"])} · {esc(ln["confidence"])}<br><span class="badge b-{ln["tier"]}">{esc(BASIS_TXT[ln["tier"]])}</span>'
            side = ln["pick_side"]; odds = f'{ln["fair_decimal_" + side]:.2f}'
        else:
            teams = f'<b>{esc(r["team_a"])}</b> — vs <b>{esc(r["team_b"])}</b> —'; pick = '<b>No pick</b><br><span class="badge b-D">D · No evidence</span>'; odds = "—"
        inputs = []
        if r.get("market"): inputs.append(f'Market ({r["market"]["n_sources"]} src): {esc(r["team_a"])} {pct(r["market"]["prob_a"])}')
        if r.get("model"): inputs.append(f'VRS model: {esc(r["team_a"])} {pct(r["model"]["prob_a"])} (Δ{r["model"]["delta_points"]:+d} pts, k={r["model"]["k"]})')
        if r.get("fallback") and r["fallback"].get("evidence"):
            for e in r["fallback"]["evidence"]: inputs.append(f'Fallback: {esc(e.get("kind"))} — {esc(e.get("source"))}')
            if r["fallback"].get("prob_a_range"): inputs.append(f'Fallback range {esc(r["team_a"])}: {pct(r["fallback"]["prob_a_range"][0])}–{pct(r["fallback"]["prob_a_range"][1])}')
        flags = "".join(f'<div><a class="badge b-flag" href="flagged.html#f-{esc(r["fixture_id"])}">{esc(f)}</a></div>' for f in r["flags"])
        src = "<br>".join(f'<a href="{esc(s["url"])}" rel="noopener">{esc(s["label"])}</a>' for s in r["sources"])
        quotes = "<br>".join(f'{esc(q["source_name"])}: {esc(q["names_at_source"][0])} {esc(q["decimal_a"])} / {esc(q["names_at_source"][1])} {esc(q["decimal_b"])} → {pct(q["no_vig_prob_team_a"])}' for q in r["quotes"])
        rows.append(f'<tr id="m-{esc(r["fixture_id"])}" data-expiry="{esc(r["valid_until_utc"])}"><td data-l="When"><span data-t="{esc(r["start_utc"])}">{esc(r["start_utc"])}</span><div class="small">{esc(r.get("competition"))} · Tier {esc(r.get("tier") or "?")} · #{esc(r["fixture_id"])}</div></td><td data-l="Win probability"><span>{esc(r["team_a"])} vs {esc(r["team_b"])}</span><div data-value>{teams}</div><div class="small">{esc(quotes)}</div></td><td data-l="Pick"><span data-value>{pick}</span><div data-value class="small">fair odds (pick) {esc(odds)}</div></td><td data-l="Inputs"><div class="small" data-value>{"<br>".join(esc(i) for i in inputs) if inputs else "—"}</div>{flags}</td><td data-l="Sources"><div class="small">{src}</div></td></tr>')
    body = f'<h1>All picks — full table</h1><p class="mut">Every CS2 fixture currently open in the HotSpawn lobby, with the inputs behind each probability and a source link on every row. A = external market prices. B = sourced rating fallback only when no eligible price exists. D = insufficient verified evidence, left blank.</p><div style="overflow-x:auto"><table class="cards"><thead><tr><th>When</th><th>Win probability</th><th>Pick</th><th>Inputs</th><th>Sources</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    return page("All picks (full table)", "picks.html", body, b)

def render_flagged(b):
    items = []
    for r in b["open"]:
        if not r["flags"] and r["line"]: continue
        ev_html = ""
        if r.get("fallback") and r["fallback"].get("evidence"):
            lis = "".join(f'<li><b>{esc(e.get("kind"))}</b> — {esc(e.get("note"))} <a href="{esc(e.get("public_url") or "#")}" rel="noopener">{esc(e.get("source"))}</a> <span class="small">names at source: {esc("/".join(e.get("names_at_source") or []))} event {esc(e.get("event_id"))}</span></li>' for e in r["fallback"]["evidence"])
            ev_html = f"<ul>{lis}</ul>"
        src_links = " &middot; ".join('<a href="' + esc(s["url"]) + '">' + esc(s["label"]) + "</a>" for s in r["sources"])
        pick_txt = (r["line"]["pick_team"] + " " + pct(r["line"]["pick_prob"])) if r["line"] else "none - blank"
        basis_txt = BASIS_TXT[r["line"]["tier"]] if r["line"] else "D - No evidence"
        items.append(f'<div class="pickcard" id="f-{esc(r["fixture_id"])}"><b>{esc(r["team_a"])} vs {esc(r["team_b"])}</b> <span class="small">{esc(r.get("competition"))} &middot; <span data-t="{esc(r["start_utc"])}">{esc(r["start_utc"])}</span> &middot; #{esc(r["fixture_id"])}</span><div>Pick: <b>{esc(pick_txt)}</b> &middot; basis {esc(basis_txt)}</div><div class="small">Flags: {esc(", ".join(r["flags"]) or "none")}</div>{ev_html}<div class="small">Sources: {src_links}</div></div>')
    body = f'<h1>Flagged for review</h1><p>All missing lines, model estimates and eligibility flags. A flagged match remains in the inventory; no value is invented.</p>{"".join(items) or "<p>No flags.</p>"}<h2>Source-integrity review</h2><p>The previous board used sibling/floor ratings for unrated opponents and slot prices for ambiguous team labels. Those shortcuts are now disabled. <a href="../audits/49a181f8/index.html">Review findings and official sources</a>. <a href="../summary/gaps.html">Earlier identity research</a> is retained as dated research, not confirmation.</p>'
    return page("Flagged for review", "flagged.html", body, b)

def render_method(b):
    cal = b["calibration"]
    body = f"""
<h1>Method &amp; sources</h1>
<h2>Every match, not invented coverage</h2>
<p><a href="{LOBBY}">HotSpawn's public lobby</a> supplies the fixture inventory only: CS2, scheduled, lock in the future, present in the captured lobby transfer state. API-only historical rows are not counted as current lobby picks. Crowd percentages are excluded. Every captured open match remains listed even if its probabilities are blank.</p>
<h2>Market first</h2><p>Both teams must match and the explicit source kickoff must agree within five minutes. Missing, approximate or ticker-inferred starts are rejected. No-vig probability = (1 / decimal odds) / sum of both inverse prices. Consensus weights are Pinnacle 2, other accepted sources 1: a disclosed modelling choice. Raw prices are re-derived, not stored probability fields. Market picks are never blended with fallback ratings.</p>
<h2>Fallback only for unpriced matches</h2><p><a href="{esc(b["vrs"].get("page_url") or 'https://github.com/ValveSoftware/counter-strike_regional_standings')}">Valve's official standings</a> provide rating inputs, not verified win probabilities. Both names must resolve to unique rating rows. Our expected-win estimate uses Valve's Glicko curve with slope k={cal["k"]:.3f}; {cal["pairs_used"]} priced/rated fixtures were available for fitting. With fewer than six, the uncalibrated default is explicitly retained. No missing roster is replaced by siblings or the lowest-rated team. Ambiguous identities and unverified HLTV aliases remain blank.</p>
<h2>Freshness and automation</h2><p>Fixture observations (including HTTP cache Age) and quotes expire after four hours. Ratings expire after fourteen days. These are conservative project policies, not source guarantees. Each card expires at its earliest evidence deadline or lock. Refresh is scheduled every thirty minutes; GitHub delays and blocked sources are possible. A failed lobby read retains the original observation time, never resets it.</p>
<h2>Source access</h2><p>Pinnacle, Bovada, Melbet and Kalshi are attempted by the existing collector. HLTV and Polymarket access failures or absent markets never justify made-up lines. Missing inputs and <a href="flagged.html">review flags</a> are published. <a href="../audits/49a181f8/index.html">Verification scope and source links</a>.</p>
<p>All probabilities are estimates, not guarantees or betting advice. Model confidence labels describe the percentage, not independently measured predictive accuracy.</p>
"""
    return page("Method & sources", "method.html", body, b)

def main():
    own = DATA / "snapshot.json"
    if own.exists(): snap, src = load(own, {}), f"data/c64a5e19/snapshot.json (collected {own.stat().st_size} bytes file)"
    else:
        snap = load(DATA.parent / "f7279a54" / "snapshot.json", {}); src = "data/f7279a54/snapshot.json (proven snapshot reused offline; own collector runs on GitHub Actions)"
    board = build_board(snap, src)
    DATA.mkdir(parents=True, exist_ok=True); SITE.mkdir(parents=True, exist_ok=True)
    (DATA / "board.json").write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n")
    (SITE / "index.html").write_text(render_index(board))
    (SITE / "picks.html").write_text(render_picks(board))
    (SITE / "flagged.html").write_text(render_flagged(board))
    (SITE / "method.html").write_text(render_method(board))
    print(json.dumps(board["summary"], indent=1)); print("generated", board["generated_utc"], "snapshot", src)
    return 0

if __name__ == "__main__": sys.exit(main())
