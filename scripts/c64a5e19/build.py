#!/usr/bin/env python3
"""Every-match inventory with evidence-gated picks.
Market quotes first; unique, fresh Valve ratings only for unpriced matches.
Unconfirmed identities/ratings remain blank. No HotSpawn crowd data is used.
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
    groups: dict[str, list] = {}
    for t in vrs.get("teams", []):
        key, _ = core.canon(t["team"])
        if key: groups.setdefault(key, []).append(t)
    idx, dup = {}, {}
    for key, rows in groups.items():
        if len(rows) == 1: idx[key] = rows[0]; continue
        dup[key] = {"candidates": rows}
    return idx, dup

def rating_for(name, idx, dup):
    key, _ = core.canon(name)
    if key in dup: return None, "ambiguous_vrs_name"
    rec = idx.get(key)
    if rec and rec.get("resolved_from_duplicates"): return rec, "vrs_duplicate_resolved_by_latest_match"
    return (rec, None) if rec else (None, "not_in_vrs")

def thin_mid(book):
    try:
        bid = float(book.get("yes_bid_dollars") or 0); ask = float(book.get("yes_ask_dollars") or 0)
    except (TypeError, ValueError): return None
    if bid <= 0 or ask <= 0 or ask < bid: return None
    return (bid + ask) / 2.0

def kalshi_start_from_ticker(event_id):
    # A ticker is not an official timezone-qualified kickoff field.
    return None


def build_board(snap, snap_source, now=None):
    now = now or core.parse_iso(snap["collected_to_utc"]) or core.now_utc()
    hs = snap["hotspawn"]; permalinks = hs.get("permalinks") or {}
    vrs = snap.get("vrs") or {}; idx, dup = rating_index(vrs)
    meta = (snap.get("access_log") or {}).get("hotspawn_lobby_page") or {}
    observed = core.parse_iso(snap.get("hotspawn_fallback_from") or meta.get("at_utc"))
    try: cache_age = max(0, int(meta.get("age_header") or 0))
    except (ValueError, TypeError): cache_age = 14401
    fixture_deadline = observed + timedelta(seconds=14400-cache_age) if observed else now
    fixture_fresh = observed is not None and observed <= now < fixture_deadline
    vrs_date = core.parse_iso(str(vrs.get("snapshot") or "").replace("_", "-") + "T00:00:00Z")
    vrs_fresh = vrs_date is not None and vrs_date <= now < vrs_date + timedelta(days=14)
    quotes = [q for raw in snap.get("quotes", []) if (q := core.rederive_quote(raw))]
    pre = [q for q in quotes if q.get("live") is False]
    open_rows, stale_n, locked_n = [], 0, 0
    for fx in hs["fixtures"]:
        if "lobby_page" not in fx.get("seen_in", []): continue
        lock = core.parse_iso(fx.get("lock_utc")) or core.parse_iso(fx["start_utc"])
        status = str(fx.get("status") or "")
        if lock and lock > now and core.parse_iso(fx["start_utc"]) > now and status == "scheduled": state = "open"
        elif status in ("scheduled", "started", "ended"): locked_n += 1; continue
        else: stale_n += 1; continue
        row = {**fx, "state": state, "hotspawn_url": permalinks.get(fx["fixture_id"]) or LOBBY,
               "hotspawn_url_kind": "match page" if fx["fixture_id"] in permalinks else "lobby", "flags": []}
        row["valid_until_utc"] = core.to_iso(min(fixture_deadline, lock, core.parse_iso(fx["start_utc"])))
        if not fixture_fresh: row["flags"].append("fixture_observation_stale_or_unverified")
        # ---- accepted market
        per_source: dict[str, dict] = {}
        for qq in pre:
            j = core.match_quote(fx, qq)
            if not j: continue
            if j.get("rejected"):
                row["flags"].append("unverified_start_not_joined:" + qq["source_key"])
                continue
            retrieved = core.parse_iso(qq.get("retrieved_utc"))
            if not fixture_fresh or not retrieved or not 0 <= (now-retrieved).total_seconds() < 14400:
                row["flags"].append("stale_or_unverified_quote:" + qq["source_key"])
                continue
            # A source event must join exactly one open lobby fixture, not a rematch.
            joins = [f for f in hs["fixtures"] if "lobby_page" in f.get("seen_in", [])
                     and f.get("status") == "scheduled"
                     and (m := core.match_quote(f, qq)) and not m.get("rejected")]
            if len(joins) != 1:
                row["flags"].append("ambiguous_fixture_join:" + qq["source_key"])
                continue
            cand = {**qq, "join": j, "prob_team_a": core.oriented_prob(qq, j["swapped"])}
            cur = per_source.get(qq["source_key"])
            kn = j["start_diff_h"] if j["start_diff_h"] is not None else 99
            ko = (cur["join"]["start_diff_h"] if cur and cur["join"]["start_diff_h"] is not None else 99)
            if cur is None or kn < ko: per_source[qq["source_key"]] = cand
        entries = [{"source_key": k, "prob_a": v["prob_team_a"]} for k, v in per_source.items()]
        mkt = core.consensus(entries)
        row["quotes"] = [{"source_key": v["source_key"], "source_name": v["source_name"], "public_url": v["public_url"], "api_url": v["api_url"], "event_id": v["event_id"], "names_at_source": [v["team_a"], v["team_b"]], "raw_format": v["raw_format"], "raw_a": v["raw_a"], "raw_b": v["raw_b"], "decimal_a": v["decimal_a"], "decimal_b": v["decimal_b"], "no_vig_prob_team_a": round(v["prob_team_a"], 4), "swapped": v["join"]["swapped"], "start_utc_at_source": v.get("start_utc"), "start_diff_h": v["join"]["start_diff_h"], "retrieved_utc": v["retrieved_utc"], "alias_notes": v["join"]["alias_notes"]} for v in sorted(per_source.values(), key=lambda x: x["source_key"])]
        row["market"] = ({**mkt, "prob_a": round(mkt["prob_a"], 4), "prob_b": round(mkt["prob_b"], 4)} if mkt else None)
        for v in per_source.values():
            if v["join"]["alias_notes"]: row["flags"].append(f"alias_join:{v['source_key']}")
        if per_source:
            row["valid_until_utc"] = core.to_iso(min(core.parse_iso(row["valid_until_utc"]),
                *(core.parse_iso(q["retrieved_utc"]) + timedelta(hours=4) for q in per_source.values())))
        ra, ea = rating_for(fx["team_a"], idx, dup); rb, eb = rating_for(fx["team_b"], idx, dup)
        row["vrs"] = {"team_a": ra, "team_b": rb, "snapshot": vrs.get("snapshot"), "page_url": vrs.get("page_url")}
        row["_delta"] = (ra["points"] - rb["points"]) if ra and rb and fixture_fresh and vrs_fresh else None
        row["_ra"], row["_rb"], row["_ea"], row["_eb"] = ra, rb, ea, eb
        open_rows.append(row)
    # calibration from this snapshot's priced+rated fixtures
    pairs = [{"delta": r["_delta"], "market_prob_a": r["market"]["prob_a"]} for r in open_rows if r["market"] and r["_delta"] is not None]
    cal = core.fit_calibration(pairs); k = cal["k"]
    for row in open_rows:
        delta = row.pop("_delta"); ra, rb, ea, eb = row.pop("_ra"), row.pop("_rb"), row.pop("_ea"), row.pop("_eb")
        model_p = core.vrs_prob(delta, 0, k) if delta is not None else None
        row["model"] = ({"prob_a": round(model_p, 4), "prob_b": round(1 - model_p, 4), "delta_points": delta, "k": round(k, 4)} if model_p is not None else None)
        mkt = row["market"]
        # Preserve eligible market probabilities; model is fallback-only, never a blend.
        line = core.blend(mkt["prob_a"] if mkt else None, mkt["n_sources"] if mkt else 0,
                          None if mkt else model_p)
        flags = row["flags"]
        fallback = None
        if line:
            tier = "A" if line["basis"] != "model" else "B"
        else:
            tier = "D"
            flags.append("no_line_unverified")
            for name, error in ((row["team_a"], ea), (row["team_b"], eb)):
                if error: flags.append(error + ":" + name)
            if not vrs_fresh: flags.append("vrs_snapshot_stale_or_unverified")
            # Research candidates are evidence for review, NEVER probability inputs.
            evidence = []
            for qq in pre:
                if qq.get("start_utc") != row["start_utc"]: continue
                matches = sum(core.same_team(n, qn)[0] for n in (row["team_a"], row["team_b"])
                              for qn in (qq["team_a"], qq["team_b"]))
                if matches == 1:
                    evidence.append({"kind": "identity_unverified_not_joined", "source": qq["source_name"],
                        "public_url": qq["public_url"], "event_id": qq["event_id"],
                        "names_at_source": [qq["team_a"], qq["team_b"]],
                        "note": "Only one participant agrees at this start time. Identity unconfirmed; no price transferred."})
            fallback = {"evidence": evidence, "prob_a_range": None}
        for nm in (row["team_a"], row["team_b"]):
            _, note = core.canon(nm)
            if note: flags.append(f"alias_used:{nm}")
        if line and line["basis"] == "model":
            flags.append("originated_estimate_not_official_probability")
            row["valid_until_utc"] = core.to_iso(min(core.parse_iso(row["valid_until_utc"]), vrs_date + timedelta(days=14)))
        if mkt: row["model"] = None
        if line:
            side = "a" if line["prob_a"] >= line["prob_b"] else "b"
            p_pick = max(line["prob_a"], line["prob_b"])
            conf = core.confidence_label(p_pick)
            if tier == "C": conf = "Low (" + conf.lower() + ")"
            fa, fb = 1 / line["prob_a"], 1 / line["prob_b"]
            row["line"] = {"basis": line["basis"], "tier": tier, "market_weight": line["market_weight"], "prob_a": round(line["prob_a"], 4), "prob_b": round(line["prob_b"], 4), "pick_side": side, "pick_team": row["team_a"] if side == "a" else row["team_b"], "pick_prob": round(p_pick, 4), "confidence": conf, "fair_decimal_a": round(fa, 3), "fair_decimal_b": round(fb, 3), "fair_american_a": core.decimal_to_american(fa), "fair_american_b": core.decimal_to_american(fb)}
        else:
            row["line"] = None
        row["fallback"] = fallback
        row["flags"] = sorted(set(flags))
        # sources list for the row
        srcs = [{"label": f"HotSpawn {row['hotspawn_url_kind']}", "url": row["hotspawn_url"]}]
        seen = set()
        for qq in row["quotes"]:
            if qq["public_url"] not in seen: srcs.append({"label": qq["source_name"], "url": qq["public_url"]}); seen.add(qq["public_url"])
        if fallback:
            for e in fallback["evidence"]:
                u = e.get("public_url")
                if u and u not in seen: srcs.append({"label": e.get("source", "evidence"), "url": u}); seen.add(u)
        if row["vrs"].get("page_url") and (ra or rb): srcs.append({"label": "Valve VRS (official)", "url": row["vrs"]["page_url"]})
        if any(core.norm(n) == "roundsgg" for n in (row["team_a"], row["team_b"])):
            srcs.append({"label": "HLTV ROUNDS identity / current roster", "url": HLTV_ROUNDS})
            row["flags"].append("historical_rating_current_roster_not_confirmed")
        row["sources"] = srcs
    open_rows.sort(key=lambda r: (r["lock_utc"] or r["start_utc"], r["fixture_id"]))
    summary = {"open": len(open_rows), "tier_a_market": sum(1 for r in open_rows if r["line"] and r["line"]["tier"] == "A"), "tier_b_model": sum(1 for r in open_rows if r["line"] and r["line"]["tier"] == "B"), "tier_c_fallback": sum(1 for r in open_rows if r["line"] and r["line"]["tier"] == "C"), "tier_d_none": sum(1 for r in open_rows if not r["line"]), "with_pick": sum(1 for r in open_rows if r["line"]), "locked_or_past_listed": locked_n}
    return {"session": "c64a5e19", "generated_utc": core.to_iso(now), "observed_utc": snap["collected_to_utc"], "fixture_valid_until_utc": core.to_iso(fixture_deadline), "snapshot_source": snap_source, "snapshot_session": snap.get("session"), "week": hs.get("week"), "summary": summary, "calibration": {**cal, "pairs_used": len(pairs)}, "vrs": {k2: vrs.get(k2) for k2 in ("snapshot", "page_url", "api_url")}, "open": open_rows, "access": snap.get("access_log", {})}

# ------------------------------------------------------------------ mobile-first rendering
CSS = """
:root{color-scheme:dark;--bg:#10151d;--card:#19222e;--line:#354458;--txt:#eff4fb;--mut:#b0bed0;--acc:#70edb6;--warn:#ffce85}
*{box-sizing:border-box}body{overflow-wrap:anywhere;margin:0;background:var(--bg);color:var(--txt);font:16px/1.6 system-ui,sans-serif}a{color:#91c8ff;overflow-wrap:anywhere}a:focus-visible,input:focus-visible{outline:3px solid var(--acc);outline-offset:3px}header{border-bottom:1px solid var(--line)}nav,main{max-width:1120px;margin:auto;padding:16px}nav{display:flex;gap:8px;flex-wrap:wrap}nav a,.button{display:inline-flex;align-items:center;min-height:44px;padding:8px 14px;background:var(--card);border:1px solid var(--line);border-radius:10px;text-decoration:none}.primary{background:var(--acc);color:#092518;font-weight:750}h1{font-size:clamp(1.8rem,4vw,2.8rem);line-height:1.2}h2{font-size:1.25rem;margin-top:28px}.mut,.small{color:var(--mut)}.small{font-size:.85rem}.stats,.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.stat,.pickcard,.note{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin:12px 0;min-width:0}.stat b{display:block;font-size:2rem}.teams{display:grid;grid-template-columns:1fr 1fr;gap:12px}.team strong{display:block;font-size:1.45rem}.pick{color:var(--acc);font-size:1.1rem;font-weight:750}.badge{border:1px solid var(--line);border-radius:6px;padding:3px 8px;font-size:.85rem}.warn{color:var(--warn)}.links{display:flex;flex-wrap:wrap;gap:6px 18px}.links a{display:inline-flex;align-items:center;min-height:44px}table{border-collapse:collapse;width:100%;table-layout:fixed}th,td{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}summary{cursor:pointer;min-height:44px;padding:8px 0}input{font:inherit;padding:10px;width:100%;max-width:600px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--txt)}[hidden]{display:none!important}.skip{position:absolute;left:-10000px}.skip:focus{left:8px;top:8px;background:var(--bg);padding:8px;z-index:10}footer{border-top:1px solid var(--line);margin-top:32px;padding-top:18px}.expiry{color:var(--warn)}
@media(max-width:760px){table thead{display:none}table tr{display:block;margin:16px 0;border:1px solid var(--line);border-radius:12px;padding:8px}table td{display:block;border:0;padding:8px}td:before{content:attr(data-l);display:block;color:var(--mut);font-size:.8rem}.grid{grid-template-columns:1fr}nav{gap:6px;padding:10px}nav a{font-size:.85rem;padding:7px 10px}}
"""
JS = """
(()=>{document.querySelectorAll('[data-t]').forEach(e=>{const d=new Date(e.dataset.t);if(!isNaN(d)){e.textContent=d.toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZoneName:'short'});e.title=e.dataset.t;}});
function expire(){document.querySelectorAll('[data-until]').forEach(e=>{if(Date.now()>=Date.parse(e.dataset.until)){e.querySelectorAll('[data-current]').forEach(n=>n.hidden=true);e.querySelectorAll('.expiry').forEach(n=>n.hidden=false);}});const notice=document.getElementById('stale-notice');if(notice&&Date.now()>=Date.parse(notice.dataset.deadline))notice.hidden=false;}
expire();setInterval(expire,30000);
const input=document.getElementById('search');if(input)input.addEventListener('input',()=>{let n=0;document.querySelectorAll('[data-search]').forEach(e=>{e.hidden=!e.dataset.search.includes(input.value.toLowerCase());if(!e.hidden)n++;});document.getElementById('search-count').textContent=n+' matches shown';});})();
"""
NAV = [("index.html", "Picks at a glance"), ("picks.html", "All picks (full table)"), ("flagged.html", "Flagged for review"), ("method.html", "Method & sources"), ("../index.html", "Main dashboard"), ("../ourline/index.html", "Our line board")]
BASIS_TXT = {"A": "Market-derived", "B": "Rating-model estimate", "C": "Unverified", "D": "Unverified — no pick"}

def source_links(r):
    return '<div class="links">' + ''.join(f'<a href="{esc(s["url"])}">{esc(s["label"])}</a>' for s in r["sources"]) + '</div>'

def page(title, active, body, board):
    nav = ''.join(f'<a href="{h}"' + (' aria-current="page"' if h == active else '') + f'>{esc(t)}</a>' for h,t in NAV)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} · Every-match picks</title><style>{CSS}</style></head><body><a class="skip" href="#main">Skip to content</a><header><nav aria-label="Main navigation">{nav}</nav></header><main id="main"><p class="small">HOTSPAWN CS2 / INDEPENDENT ANALYSIS</p><div id="stale-notice" class="note warn" data-deadline="{esc(board['fixture_valid_until_utc'])}" hidden>Fixture evidence has expired. This is a dated inventory, not a confirmed current lobby. Awaiting the next successful automatic refresh.</div>{body}<footer class="small">Source collection completed <time data-t="{esc(board['observed_utc'])}">{esc(board['observed_utc'])}</time>. Board evaluated {esc(board['generated_utc'])}. Counts describe that evaluation, not guaranteed live coverage.<br>Automatic collection is scheduled twice hourly; GitHub Actions or source delays are possible. A four-hour evidence limit hides expired picks. With JavaScript disabled, check the explicit “valid before” time on each row.<br>Probabilities are derived estimates, not official forecasts or guarantees. HotSpawn supplies fixtures only, never probability inputs. Not affiliated with HotSpawn or a bookmaker.</footer></main><script>{JS}</script></body></html>'''

def decision(r):
    ln=r['line']
    if not ln: return '<p class="warn">No pick — evidence unverified</p>'
    pick = f'Pick: {esc(ln["pick_team"])} · {pct(ln["pick_prob"])}' if ln['prob_a'] != ln['prob_b'] else 'No lean — equal derived probabilities'
    return f'''<div data-current><div class="teams"><div class="team">{esc(r['team_a'])}<strong>{pct(ln['prob_a'])}</strong></div><div class="team">{esc(r['team_b'])}<strong>{pct(ln['prob_b'])}</strong></div></div><p class="pick">{pick}</p><span class="badge">{BASIS_TXT[ln['tier']]}</span></div><p class="expiry" hidden>Pick expired or locked — probability hidden. Awaiting updated evidence.</p>'''

def glance_card(r):
    return f'''<article class="pickcard" id="m-{esc(r['fixture_id'])}" data-search="{esc((r['team_a']+' '+r['team_b']+' '+str(r.get('competition',''))).lower())}" data-until="{esc(r['valid_until_utc'])}"><p class="small"><time data-t="{esc(r['start_utc'])}">{esc(r['start_utc'])}</time> · {esc(r.get('competition'))}</p><h2>{esc(r['team_a'])} vs {esc(r['team_b'])}</h2>{decision(r)}<p class="small">Valid before {esc(r['valid_until_utc'])}. #{esc(r['fixture_id'])}</p><a class="button" href="picks.html#m-{esc(r['fixture_id'])}">Evidence &amp; odds</a>{source_links(r)}{'<a href="flagged.html#f-'+esc(r['fixture_id'])+'">Review flags</a>' if r['flags'] else ''}</article>'''

def render_index(b):
    s=b['summary']
    body=f'''<h1>Your CS2 picks, in one place.</h1><p class="mut">Every open match in the captured HotSpawn lobby, including low-tier CS2. External prices first; supported rating estimates only when prices are missing. No invented picks to fill gaps.</p><div class="links"><a class="button primary" href="#matches">See picks ↓</a><a class="button" href="picks.html">Full evidence table</a><a class="button" href="flagged.html">Flagged for review</a></div><div class="stats"><div class="stat"><b>{s['open']}</b>Open lobby matches in this snapshot</div><div class="stat"><b>{s['with_pick']}</b>With supported probabilities ({s['tier_a_market']} market / {s['tier_b_model']} model)</div><div class="stat"><b>{s['tier_d_none']}</b>Unverified — left blank</div></div><p class="note">Full match coverage is not the same as full probability coverage. An absent rating, disputed identity, stale source or missing kickoff cannot justify a win percentage. <a href="../cs2.html">View locked / historical lobby inventory</a> · <a href="../summary/index.html">Independent verification companion (dated)</a></p><h2 id="matches">Open matches · earliest lock first</h2><label for="search">Find a team or tournament</label><br><input id="search" type="search" placeholder="Search teams or tournament"><p id="search-count" role="status" class="small">{s['open']} matches shown</p><div class="grid">{''.join(glance_card(r) for r in b['open'])}</div>'''
    return page('Executive summary & picks at a glance','index.html',body,b)

def render_picks(b):
    rows=[]
    for r in b['open']:
        evidence=[]
        for q in r['quotes']:
            evidence.append(f'''<p><a href="{esc(q['api_url'])}">{esc(q['source_name'])} source payload</a>: {esc(q['names_at_source'][0])} {esc(q['raw_a'])} / {esc(q['names_at_source'][1])} {esc(q['raw_b'])} ({esc(q['raw_format'])}); no-vig P({esc(r['team_a'])}) {pct(q['no_vig_prob_team_a'])}. Read {esc(q['retrieved_utc'])}; kickoff {esc(q['start_utc_at_source'])}.</p>''')
        if r.get('model'):
            m=r['model']; evidence.append(f'<p>Historical Valve rating points: {r["vrs"]["team_a"]["points"]} / {r["vrs"]["team_b"]["points"]}; snapshot {esc(r["vrs"]["snapshot"])}. Model slope k={m["k"]}. Originated estimate, not an official probability.</p>')
        rows.append(f'''<tr id="m-{esc(r['fixture_id'])}" data-until="{esc(r['valid_until_utc'])}"><td data-l="Match"><b>{esc(r['team_a'])} vs {esc(r['team_b'])}</b><p>{esc(r.get('competition'))}</p><time data-t="{esc(r['start_utc'])}">{esc(r['start_utc'])}</time><p class="small">#{esc(r['fixture_id'])}<br>Valid before {esc(r['valid_until_utc'])}</p></td><td data-l="Probabilities & pick">{decision(r)}</td><td data-l="Evidence"><details><summary>Inputs (dated source evidence)</summary>{''.join(evidence) or 'No eligible input — unverified.'}</details>{source_links(r)}{'<a href="flagged.html#f-'+esc(r['fixture_id'])+'">Review flags</a>' if r['flags'] else ''}</td></tr>''')
    return page('All picks (full table)','picks.html','<h1>All picks — full table</h1><p>Market-derived probabilities or labelled rating estimates. Blank is unverified, not 50/50. Inputs inside evidence details are dated quotes, not current betting offers.</p><table><caption>Open HotSpawn CS2 matches at evaluation time</caption><thead><tr><th scope="col">Match</th><th scope="col">Probabilities &amp; pick</th><th scope="col">Evidence &amp; sources</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>',b)

def render_flagged(b):
    items=[]
    for r in b['open']:
        if not r['flags']: continue
        notes=''.join(f'<li>{esc(f)}</li>' for f in r['flags'])
        for e in (r.get('fallback') or {}).get('evidence',[]):
            notes+=f'<li>{esc(e["note"])} <a href="{esc(e["public_url"])}">{esc(e["source"])}: {esc(" / ".join(e["names_at_source"]))}</a></li>'
        items.append(f'<article class="pickcard" id="f-{esc(r["fixture_id"])}"><h2>{esc(r["team_a"])} vs {esc(r["team_b"])}</h2><ul>{notes}</ul>{source_links(r)}</article>')
    sources=b.get('access',{})
    health=''.join(f'<tr><td data-l="Source"><a href="{esc(v.get("url") or LOBBY)}">{esc(k)}</a></td><td data-l="HTTP / observation">{esc(v.get("status"))} / {esc(v.get("at_utc"))}</td><td data-l="Error">{esc(v.get("error") or v.get("crash") or "No recorded access error; not proof of match coverage")}</td></tr>' for k,v in sources.items())
    body='''<h1>Flagged for Review</h1><p>Unverified items do not block publication. They do block unsupported probabilities.</p><div class="note"><b>Corrections to the inherited board:</b> no more sibling/floor ratings for LFO 10, no price transfers between WROTBERRY / WBT / WBT Academy without a confirmed identity, no guessed timezone from Kalshi tickers, no thin-book fallback. All flagged A/B rows are shown here too.</div><p><a href="../audits/8723ad37/REVIEW.md">Source verification and scoped repository review</a> · <a href="https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md">Official Valve standings</a> · <a href="https://www.hltv.org/events/9332/elisa-breakout-series-2">HLTV Elisa event identity evidence</a></p><p>RoundsGG is an alias for ROUNDS; the historical rating roster includes Tumppis, while the HLTV team page read in this session lists four active players. The estimate uses historical team strength, not a verified upcoming five-player lineup. WBT vs WBT Academy remains disputed; LFO 10 has no exact row in the checked Valve file.</p>'''+''.join(items)+'<h2>Source access log</h2><table><thead><tr><th>Source</th><th>HTTP / observation</th><th>Error</th></tr></thead><tbody>'+health+'</tbody></table>'
    return page('Flagged for review','flagged.html',body,b)

def render_method(b):
    cal=b['calibration']
    body=f'''<h1>Method &amp; sources</h1><h2>Coverage and automatic refresh</h2><p>The collector reads the public <a href="{LOBBY}">HotSpawn lobby</a> Angular transfer-state /api/v1/fixtures response. Only CS2 rows actually listed on that page enter this board; the broader API cannot add or overwrite lobby entries. Open means scheduled, before kickoff and pick lock at evaluation. Retained data keeps its original observation and cache age after a fetch failure. HotSpawn crowd percentages are discarded.</p><p>The <a href="https://github.com/buffedlizard55-lab/MaltaProj2/actions/workflows/every-match-c64a5e19.yml">automatic workflow</a> is scheduled at minutes 12 and 42 hourly (faster than the requested 4–8 hours). Source errors and Actions delays are possible; schedules are not guarantees. Cache-adjusted fixtures and quotes expire after four hours. Valve snapshots expire after 14 days. These are project safety thresholds, not source claims.</p><h2>1. External market first</h2><p>Both team names and a timezone-qualified start within five minutes must agree; missing/approximate kickoff, live markets, stale quotes, ambiguous rematches and unknown participants are rejected. Probabilities are recalculated from raw prices, never trusted from stored derived percentages. Each source contributes once. Decimal no-vig P(A) = (1 / odds A) / ((1 / odds A) + (1 / odds B)); consensus weights Pinnacle ×2 and other sources ×1. That weighting is a modelling choice. Eligible market results are not blended with ratings.</p><h2>2. Rating fallback only where no eligible market exists</h2><p>Both teams need unique entries in the <a href="{esc(b['vrs'].get('page_url') or 'https://github.com/ValveSoftware/counter-strike_regional_standings')}">official Valve standings</a>. We apply a logistic transform based on <a href="https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/model/glicko.js">Valve's published expected-score formula</a>, RD=75, with slope k={cal['k']:.4f}. Calibration fits logit(market probability) against point difference for {cal['pairs_used']} eligible pairs in this snapshot. With fewer than six pairs, k=1 (uncalibrated). This is our estimate, not Valve's official match prediction or validated predictive accuracy. Roster changes, BO1/BO3 and map vetoes are not modelled.</p><h2>3. Missing evidence stays blank</h2><p>No other team's rating is assigned to an unrated team. No 50/50 fill, guessed floor, thin-book or one-participant slot join is permitted. HLTV can support identity research for uncovered fixtures; unavailable pages are logged, not invented. RoundsGG → ROUNDS is documented by <a href="{HLTV_ROUNDS}">HLTV's team page</a>; disputed WBT/WBT Academy labels remain unresolved. Every row has an official fixture link and every consumed market/rating input has its source link.</p><h2>Audit and limitations</h2><p><a href="../data/c64a5e19/board.json">Board JSON</a> · <a href="../data/c64a5e19/snapshot.json">Source snapshot</a> · <a href="../audits/8723ad37/REVIEW.md">Scoped line-by-line review</a>. Link existence and arithmetic are tested automatically. HTTP access does not establish betting availability in your jurisdiction. These are estimates, not financial advice or guarantees.</p>'''
    return page('Method & sources','method.html',body,b)


def main():
    own=DATA/'snapshot.json'
    snap=load(own,{})
    if not snap: raise SystemExit('Missing source snapshot; refusing to publish an empty board')
    board=build_board(snap,'data/c64a5e19/snapshot.json',now=core.now_utc())
    DATA.mkdir(parents=True,exist_ok=True); SITE.mkdir(parents=True,exist_ok=True)
    (DATA/'board.json').write_text(json.dumps(board,indent=1,ensure_ascii=False)+'\n')
    for name,render in [('index.html',render_index),('picks.html',render_picks),('flagged.html',render_flagged),('method.html',render_method)]:
        (SITE/name).write_text(render(board))
    print(json.dumps(board['summary'],indent=1))
    return 0

if __name__=='__main__': sys.exit(main())
