#!/usr/bin/env python3
"""OURLINE builder (session f7279a54): snapshot.json -> board.json + ourline/*.html.

Pure offline step. Re-derives every number from the raw quotes in the snapshot so the published
board can be audited against the evidence committed next to it.
"""
from __future__ import annotations

import html
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "f7279a54"
SITE = ROOT / "ourline"
LOBBY = "https://play.hotspawn.com/lobby"
HS_API_PUBLIC = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
VALVE_GLICKO = ("https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/"
                "model/glicko.js")
VALVE_FIT = ("https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/"
             "model/fit.js")
VALVE_README = ("https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/"
                "readme.md")
HIST_LIMIT = 600
RECENT_LOCK_H = 24


def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def load(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


# ------------------------------------------------------------------------------- ratings
def rating_index(vrs: dict) -> tuple[dict, dict]:
    """Index VRS rows by normalised name.

    VRS sometimes lists the same organisation twice (an older roster is kept as its own row).
    Such a name is resolved ONLY when Valve's own details files show one candidate has a strictly
    more recent counted match (that roster is the one currently playing); otherwise it stays
    ambiguous and no rating is used.
    """
    groups: dict[str, list] = {}
    for t in vrs.get("teams", []):
        key, _ = core.canon(t["team"])
        if key:
            groups.setdefault(key, []).append(t)
    idx: dict[str, dict] = {}
    dup: dict[str, dict] = {}
    for key, rows in groups.items():
        if len(rows) == 1:
            idx[key] = rows[0]
            continue
        dated = sorted((r for r in rows if r.get("latest_match_date")),
                       key=lambda r: r["latest_match_date"], reverse=True)
        if len(dated) == len(rows) and dated[0]["latest_match_date"] > dated[1]["latest_match_date"]:
            idx[key] = {**dated[0], "resolved_from_duplicates": [
                {k: r.get(k) for k in ("standing", "points", "roster", "latest_match_date", "details_path")}
                for r in rows]}
        else:
            dup[key] = {"candidates": [{k: r.get(k) for k in ("standing", "points", "roster",
                                                               "latest_match_date", "details_path")}
                                       for r in rows]}
    return idx, dup


def rating_for(name: str, idx: dict, dup: dict) -> tuple[dict | None, str | None]:
    key, _ = core.canon(name)
    if key in dup:
        return None, "ambiguous_vrs_name"
    rec = idx.get(key)
    if rec and rec.get("resolved_from_duplicates"):
        return rec, "vrs_duplicate_resolved_by_latest_match"
    return (rec, None) if rec else (None, "not_in_vrs")


# --------------------------------------------------------------------------------- board
def grade(hs_fixtures: list[dict], hist: dict, track: dict) -> dict:
    """Grade every pick this board published while a fixture was open, once HotSpawn reports a
    winner (status 'ended' with unequal scores). Persisted so results survive snapshot trimming."""
    for fx in hs_fixtures:
        h = hist.get(fx["fixture_id"])
        if not h or not fx.get("winner") or fx["fixture_id"] in track:
            continue
        ln = h["line"]
        p_a = ln["prob_a"]
        won_a = 1.0 if fx["winner"] == "a" else 0.0
        track[fx["fixture_id"]] = {
            "fixture_id": fx["fixture_id"], "teams": [fx["team_a"], fx["team_b"]],
            "competition": fx.get("competition"), "start_utc": fx["start_utc"],
            "pick_team": ln["pick_team"], "pick_prob": ln["pick_prob"], "basis": ln["basis"],
            "winner_team": fx["team_a"] if fx["winner"] == "a" else fx["team_b"],
            "correct": ln["pick_side"] == fx["winner"], "brier": round((p_a - won_a) ** 2, 4),
            "line_observed_utc": h["observed_utc"]}
    rows = list(track.values())

    def agg(rs):
        if not rs:
            return {"n": 0, "correct": 0, "accuracy": None, "brier": None, "mean_pick_prob": None}
        return {"n": len(rs), "correct": sum(1 for r in rs if r["correct"]),
                "accuracy": sum(1 for r in rs if r["correct"]) / len(rs),
                "brier": sum(r["brier"] for r in rs) / len(rs),
                "mean_pick_prob": sum(r["pick_prob"] for r in rs) / len(rs)}
    return {"all": agg(rows), "by_basis": {b: agg([r for r in rows if r["basis"] == b])
                                           for b in ("market+model", "market", "model")}}


def build_board(snap: dict, hist: dict, cal_pairs: dict, track: dict | None = None) -> dict:
    now = core.parse_iso(snap["collected_to_utc"]) or core.now_utc()
    hs = snap["hotspawn"]
    permalinks = hs.get("permalinks") or {}
    vrs = snap.get("vrs") or {}
    idx, dup = rating_index(vrs)
    quotes = [qq for qq in snap.get("quotes", []) if qq.get("prob_a") is not None]
    live_quotes = [qq for qq in quotes if qq.get("live")]
    pre_quotes = [qq for qq in quotes if not qq.get("live")]
    used_quote_ids: set[str] = set()

    open_rows, recent_rows, stale, conflicts = [], [], [], []
    for fx in hs["fixtures"]:
        lock = core.parse_iso(fx.get("lock_utc")) or core.parse_iso(fx["start_utc"])
        start = core.parse_iso(fx["start_utc"])
        listed_on_page = "lobby_page" in fx.get("seen_in", [])
        status = str(fx.get("status") or "")
        if lock and lock > now and status == "scheduled":
            state = "open"
        elif lock and lock > now and status != "scheduled":
            # e.g. status 'started' while the published start time is weeks away
            conflicts.append(fx)
            continue
        elif status in ("scheduled", "started") and start and now - start <= timedelta(hours=RECENT_LOCK_H):
            state = "locked_recent"
        elif status == "ended" and start and now - start <= timedelta(hours=RECENT_LOCK_H) and fx["fixture_id"] in hist:
            state = "locked_recent"
        else:
            if listed_on_page and status in ("scheduled", "started"):
                stale.append(fx)
            continue
        if state == "locked_recent" and not listed_on_page and fx["fixture_id"] not in hist:
            continue
        row = {**fx, "state": state,
               "hotspawn_url": permalinks.get(fx["fixture_id"]) or LOBBY,
               "hotspawn_url_kind": "match page" if fx["fixture_id"] in permalinks else "lobby",
               "flags": []}
        if not listed_on_page:
            row["flags"].append("api_only_not_on_cached_lobby_page")
        if state == "locked_recent":
            prev = hist.get(fx["fixture_id"])
            row["last_open_line"] = prev
            recent_rows.append(row)
            continue
        # ---- market
        per_source: dict[str, dict] = {}
        for qq in pre_quotes:
            j = core.match_quote(fx, qq)
            if not j:
                continue
            if j.get("rejected"):
                row.setdefault("rejected_joins", []).append({
                    "source_key": qq["source_key"], "source_name": qq["source_name"],
                    "public_url": qq["public_url"], "event_id": qq["event_id"],
                    "names_at_source": [qq["team_a"], qq["team_b"]], "start_utc_at_source": qq.get("start_utc"),
                    "start_diff_h": round(j["start_diff_h"], 1), "decimal": [qq["decimal_a"], qq["decimal_b"]]})
                row["flags"].append(f"start_time_mismatch_not_joined:{qq['source_key']}")
                continue
            cand = {**qq, "join": j, "prob_team_a": core.oriented_prob(qq, j["swapped"])}
            cur = per_source.get(qq["source_key"])
            key_new = j["start_diff_h"] if j["start_diff_h"] is not None else 99
            key_old = (cur["join"]["start_diff_h"] if cur and cur["join"]["start_diff_h"] is not None else 99)
            if cur is None or key_new < key_old:
                per_source[qq["source_key"]] = cand
        for qq in live_quotes:
            if core.match_quote(fx, qq):
                row["flags"].append("in_play_price_seen_and_excluded:" + qq["source_key"])
        entries = [{"source_key": k, "prob_a": v["prob_team_a"]} for k, v in per_source.items()]
        mkt = core.consensus(entries)
        for k, v in per_source.items():
            used_quote_ids.add(f"{k}:{v['event_id']}")
            if v["join"]["alias_notes"]:
                row["flags"].append(f"alias_join:{k}")
            d = v["join"]["start_diff_h"]
            if d is not None and d > core.TIME_WARN_H and not v.get("start_is_approx"):
                row["flags"].append(f"start_time_differs_{d:.1f}h:{k}")
        row["quotes"] = [{
            "source_key": v["source_key"], "source_name": v["source_name"], "public_url": v["public_url"],
            "api_url": v["api_url"], "event_id": v["event_id"], "names_at_source": [v["team_a"], v["team_b"]],
            "raw_format": v["raw_format"], "raw_a": v["raw_a"], "raw_b": v["raw_b"],
            "decimal_a": v["decimal_a"], "decimal_b": v["decimal_b"],
            "no_vig_prob_team_a": round(v["prob_team_a"], 4), "swapped": v["join"]["swapped"],
            "start_utc_at_source": v.get("start_utc"), "start_diff_h": v["join"]["start_diff_h"],
            "retrieved_utc": v["retrieved_utc"], "alias_notes": v["join"]["alias_notes"]}
            for v in sorted(per_source.values(), key=lambda x: x["source_key"])]
        row["market"] = ({**mkt, "prob_a": round(mkt["prob_a"], 4), "prob_b": round(mkt["prob_b"], 4)}
                         if mkt else None)
        # ---- VRS model inputs
        ra, ea = rating_for(fx["team_a"], idx, dup)
        rb, eb = rating_for(fx["team_b"], idx, dup)
        row["vrs"] = {"team_a": ra, "team_b": rb, "snapshot": vrs.get("snapshot"),
                      "page_url": vrs.get("page_url")}
        for side, err in (("team_a", ea), ("team_b", eb)):
            if err:
                row["flags"].append(f"{err}:{fx[side]}")
            if err == "ambiguous_vrs_name":
                row.setdefault("vrs_ambiguous", {})[side] = dup.get(core.canon(fx[side])[0])
        row["_delta"] = (ra["points"] - rb["points"]) if ra and rb else None
        if mkt and row["_delta"] is not None:
            cal_pairs[fx["fixture_id"]] = {
                "fixture_id": fx["fixture_id"], "teams": [fx["team_a"], fx["team_b"]],
                "delta": row["_delta"], "market_prob_a": mkt["prob_a"], "n_sources": mkt["n_sources"],
                "observed_utc": snap["collected_to_utc"], "start_utc": fx["start_utc"]}
        open_rows.append(row)

    # ---- calibration (bounded history of distinct fixtures, latest pre-lock observation each)
    pairs = sorted(cal_pairs.values(), key=lambda p: p["observed_utc"])[-HIST_LIMIT:]
    cal = core.fit_calibration(pairs)
    k = cal["k"]

    for row in open_rows:
        delta = row.pop("_delta")
        model = core.vrs_prob(delta, 0, k) if delta is not None else None
        row["model"] = ({"prob_a": round(model, 4), "prob_b": round(1 - model, 4), "delta_points": delta,
                         "k": round(k, 4), "valve_uncalibrated_prob_a": round(core.vrs_prob(delta, 0, 1.0), 4)}
                        if model is not None else None)
        mkt = row["market"]
        line = core.blend(mkt["prob_a"] if mkt else None, mkt["n_sources"] if mkt else 0, model)
        if line:
            side = "a" if line["prob_a"] >= line["prob_b"] else "b"
            p_pick = max(line["prob_a"], line["prob_b"])
            fair_a, fair_b = 1 / line["prob_a"], 1 / line["prob_b"]
            row["line"] = {
                "basis": line["basis"], "market_weight": line["market_weight"],
                "prob_a": round(line["prob_a"], 4), "prob_b": round(line["prob_b"], 4),
                "pick_side": side, "pick_team": row["team_a"] if side == "a" else row["team_b"],
                "pick_prob": round(p_pick, 4), "confidence": core.confidence_label(p_pick),
                "fair_decimal_a": round(fair_a, 3), "fair_decimal_b": round(fair_b, 3),
                "fair_american_a": core.decimal_to_american(fair_a),
                "fair_american_b": core.decimal_to_american(fair_b)}
            if mkt and model is not None:
                if (mkt["prob_a"] - 0.5) * (model - 0.5) < 0:
                    row["flags"].append("model_and_market_pick_different_teams")
                if abs(mkt["prob_a"] - model) >= 0.15:
                    row["flags"].append(f"model_market_gap_{abs(mkt['prob_a'] - model) * 100:.0f}pp")
            if mkt and mkt.get("spread_a") is not None and mkt["spread_a"] >= 0.08:
                row["flags"].append(f"sources_disagree_{mkt['spread_a'] * 100:.0f}pp")
            hist[row["fixture_id"]] = {"line": row["line"], "observed_utc": snap["collected_to_utc"],
                                       "teams": [row["team_a"], row["team_b"]]}
        else:
            row["line"] = None
            row["flags"].append("no_line_unverified")
        row["flags"] = sorted(set(row["flags"]))

    unmatched = [qq for qq in pre_quotes if f"{qq['source_key']}:{qq['event_id']}" not in used_quote_ids]
    access = {}
    for name, meta in (snap.get("access_log") or {}).items():
        if isinstance(meta, dict):
            ok = meta.get("status") == 200 and not meta.get("error") and not meta.get("looks_like_challenge")
            access[name] = {**{k2: meta.get(k2) for k2 in ("url", "status", "error", "bytes", "at_utc",
                                                          "age_header", "quotes", "looks_like_challenge",
                                                          "rows", "fixtures_in_transfer_state", "crash")},
                            "ok": ok}
    track_summary = grade(hs["fixtures"], hist, track if track is not None else {})
    n_open = len(open_rows)
    summary = {
        "open": n_open,
        "with_line": sum(1 for r in open_rows if r["line"]),
        "market_based": sum(1 for r in open_rows if r["line"] and r["line"]["basis"] != "model"),
        "model_only": sum(1 for r in open_rows if r["line"] and r["line"]["basis"] == "model"),
        "no_line": sum(1 for r in open_rows if not r["line"]),
        "locked_recent": len(recent_rows),
        "stale_listed": len(stale),
        "quotes_total": len(quotes), "quotes_live_excluded": len(live_quotes),
        "quotes_unmatched": len(unmatched),
        "sources_ok": sorted(k2 for k2, v in access.items() if v["ok"]),
        "sources_failed": sorted(k2 for k2, v in access.items() if not v["ok"]),
    }
    open_rows.sort(key=lambda r: (r["lock_utc"] or r["start_utc"], r["fixture_id"]))
    recent_rows.sort(key=lambda r: r["start_utc"], reverse=True)
    return {
        "session": "f7279a54", "generated_utc": snap["collected_to_utc"],
        "collected_from_utc": snap["collected_from_utc"], "week": hs.get("week"),
        "hotspawn_fallback_from": snap.get("hotspawn_fallback_from"),
        "summary": summary, "calibration": {**cal, "pairs_used": len(pairs)},
        "vrs": {k2: vrs.get(k2) for k2 in ("snapshot", "page_url", "api_url")},
        "vrs_ambiguous_keys": sorted(dup),
        "vrs_base_url": "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/",
        "open": open_rows, "locked_recent": recent_rows,
        "stale_listed": [{k2: f.get(k2) for k2 in ("fixture_id", "competition", "team_a", "team_b",
                                                   "start_utc", "lock_utc", "status")} for f in stale],
        "status_conflicts": [{k2: f.get(k2) for k2 in ("fixture_id", "competition", "team_a", "team_b",
                                                       "start_utc", "lock_utc", "status", "seen_in")}
                             for f in conflicts],
        "track_record": track_summary,
        "unmatched_quotes": unmatched, "rejected_quotes": snap.get("rejected_quotes", []),
        "access": access,
    }


# ------------------------------------------------------------------------------- render
CSS = """
:root{--bg:#0f1218;--card:#171b23;--line:#262c38;--txt:#e8ebf1;--mut:#9aa3b2;--acc:#3ddc97;
--acc2:#5aa9ff;--warn:#ffb547;--bad:#ff6b6b}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:var(--acc2)}header{position:sticky;top:0;z-index:5;background:#0b0e13;border-bottom:1px solid var(--line)}
.bar{max-width:1100px;margin:0 auto;padding:10px 14px;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}
.brand{font-weight:700;margin-right:auto}.bar nav{display:flex;gap:6px;flex-wrap:wrap}
.bar nav a{padding:6px 10px;border-radius:8px;text-decoration:none;color:var(--txt);background:#1c212b;font-size:14px}
.bar nav a.on{background:var(--acc);color:#04130c;font-weight:700}
main{max-width:1100px;margin:0 auto;padding:14px}
h1{font-size:22px;margin:6px 0 4px}h2{font-size:18px;margin:26px 0 8px}.mut{color:var(--mut)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin:12px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
.stat b{display:block;font-size:22px}.stat span{color:var(--mut);font-size:13px}
.tools{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}
.tools input{flex:1 1 200px;padding:9px 11px;border-radius:8px;border:1px solid var(--line);background:#11151c;color:var(--txt);font-size:15px}
.chip{padding:7px 11px;border-radius:999px;border:1px solid var(--line);background:#11151c;color:var(--txt);font-size:14px;cursor:pointer}
.chip.on{background:var(--acc2);color:#031326;border-color:var(--acc2);font-weight:600}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut);background:#131720}
.team{display:flex;align-items:center;gap:8px;margin:2px 0}.team .nm{flex:1;min-width:0}
.team.pk .nm{font-weight:700;color:var(--acc)}.pct{font-variant-numeric:tabular-nums;min-width:52px;text-align:right}
.meter{height:6px;background:#2a303c;border-radius:4px;overflow:hidden;margin:2px 0 6px}
.meter i{display:block;height:100%;background:var(--acc)}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:700}
.b-pick{background:var(--acc);color:#04130c}.b-Strong{background:#1f6f4d}.b-Solid{background:#245a85}
.b-Lean{background:#5b4c1c}.b-Toss-up{background:#4a2b2b}.b-flag{background:#5b3a12;color:#ffd9a3}
.b-basis{background:#232a36;color:var(--mut);font-weight:600}
.pickcell b{font-size:17px}.small{font-size:12.5px;color:var(--mut)}.src a{display:inline-block;margin-right:8px}
.empty{color:var(--warn);font-weight:600}.foot{margin:30px 0 10px;color:var(--mut);font-size:13px}
.note{background:#151a22;border-left:3px solid var(--acc2);padding:10px 12px;border-radius:6px;margin:10px 0}
code{background:#11151c;padding:1px 5px;border-radius:4px}
@media (max-width:760px){
 table.cards,table.cards tbody,table.cards tr,table.cards td{display:block;width:100%}
 table.cards thead{display:none}table.cards{background:none;border:0}
 table.cards tr{background:var(--card);border:1px solid var(--line);border-radius:12px;margin:0 0 10px;padding:6px 4px}
 table.cards td{border:0;padding:5px 10px}
 table.cards td[data-l]::before{content:attr(data-l);display:block;font-size:11px;text-transform:uppercase;color:var(--mut);letter-spacing:.05em}
 .wide{overflow-x:auto}
}
"""

JS = """
(function(){
 function fmt(iso){var d=new Date(iso);if(isNaN(d))return iso;
  return d.toLocaleString([], {weekday:'short',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});}
 function rel(iso){var s=(new Date(iso)-new Date())/1000,a=Math.abs(s),t;
  if(a<3600)t=Math.round(a/60)+' min';else if(a<172800)t=(a/3600).toFixed(1)+' h';else t=Math.round(a/86400)+' d';
  return s>=0?'in '+t:t+' ago';}
 document.querySelectorAll('[data-t]').forEach(function(e){e.textContent=fmt(e.dataset.t);e.title=e.dataset.t+' (UTC)';});
 document.querySelectorAll('[data-r]').forEach(function(e){e.textContent=rel(e.dataset.r);});
 var q=document.getElementById('q'),chips=document.querySelectorAll('.chip'),mode='all';
 function apply(){var s=(q&&q.value||'').toLowerCase(),n=0,now=Date.now();
  document.querySelectorAll('tr[data-row]').forEach(function(r){
   var ok=!s||r.dataset.s.indexOf(s)>=0;
   if(mode==='24h')ok=ok&&(new Date(r.dataset.lock)-now)<864e5;
   else if(mode==='line')ok=ok&&r.dataset.line!=='none';
   else if(mode==='noline')ok=ok&&r.dataset.line==='none';
   else if(mode.indexOf('tier-')===0)ok=ok&&r.dataset.tier===mode.slice(5);
   r.style.display=ok?'':'none';if(ok)n++;});
  var c=document.getElementById('count');if(c)c.textContent=n;}
 if(q)q.addEventListener('input',apply);
 chips.forEach(function(c){c.addEventListener('click',function(){chips.forEach(function(x){x.classList.remove('on')});
  c.classList.add('on');mode=c.dataset.m;apply();});});
})();
"""

NAV = [("index.html", "Picks"), ("results.html", "Track record"), ("sources.html", "Lines &amp; sources"),
       ("flagged.html", "Flagged for review"), ("method.html", "Method"), ("../index.html", "Main dashboard")]


def page(title: str, active: str, body: str, board: dict) -> str:
    nav = "".join(f'<a href="{h}"{" class=on" if h == active else ""}>{t}</a>' for h, t in NAV)
    gen = board["generated_utc"]
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Our line · HotSpawn CS2 Pick'ems</title>
<style>{CSS}</style></head><body>
<header><div class="bar"><div class="brand">🎯 Our line · CS2 Pick'ems</div><nav>{nav}</nav></div></header>
<main>{body}
<p class="foot">Data collected {esc(gen)} UTC (<span data-r="{esc(gen)}"></span>) by an automated GitHub Actions run — no manual input.
Probabilities are estimates derived from external bookmaker/exchange prices and Valve's official VRS ratings; HotSpawn crowd picks are never used.
Not affiliated with HotSpawn or any bookmaker. Not betting advice. Section owner: session <code>f7279a54</code>.</p>
</main><script>{JS}</script></body></html>
"""


def pct(p) -> str:
    return f"{p * 100:.1f}%" if isinstance(p, (int, float)) else ""


def amer(v) -> str:
    return "" if v is None else (f"+{v}" if v > 0 else str(v))


BASIS_TXT = {"market+model": "Bookmaker lines + VRS model", "market": "Bookmaker lines",
             "model": "VRS model only (no bookmaker line found)"}


def team_line(name: str, p, is_pick: bool) -> str:
    w = f"{p * 100:.1f}" if isinstance(p, (int, float)) else "0"
    badge = ' <span class="badge b-pick">PICK</span>' if is_pick else ""
    return (f'<div class="team{" pk" if is_pick else ""}"><span class="nm">{esc(name)}{badge}</span>'
            f'<span class="pct">{pct(p) or "—"}</span></div><div class="meter"><i style="width:{w}%"></i></div>')


def open_table(rows: list[dict]) -> str:
    out = ['<div class="wide"><table class="cards"><thead><tr><th>Locks / starts</th><th>Match &amp; win probability</th>'
           '<th>Pick</th><th>Fair odds</th><th>Inputs</th><th>Sources</th></tr></thead><tbody>']
    for r in rows:
        ln = r["line"]
        mk, md = r.get("market"), r.get("model")
        s = " ".join([r["team_a"], r["team_b"], r.get("competition") or ""]).lower()
        pick_a = bool(ln and ln["pick_side"] == "a")
        pick_b = bool(ln and ln["pick_side"] == "b")
        teams = team_line(r["team_a"], ln["prob_a"] if ln else None, pick_a) + \
            team_line(r["team_b"], ln["prob_b"] if ln else None, pick_b)
        if ln:
            pick = (f'<b>{esc(ln["pick_team"])}</b><br>{pct(ln["pick_prob"])} '
                    f'<span class="badge b-{esc(ln["confidence"])}">{esc(ln["confidence"])}</span>')
            side = ln["pick_side"]
            odds = (f'{ln["fair_decimal_" + side]:.2f} <span class="small">({amer(ln["fair_american_" + side])})</span>'
                    f'<div class="small">other side {ln["fair_decimal_" + ("b" if side == "a" else "a")]:.2f}</div>')
        else:
            pick = '<span class="empty">No pick — unverified</span><div class="small">no bookmaker line and no VRS rating for both teams</div>'
            odds = ""
        inputs = [f'<span class="badge b-basis">{esc(BASIS_TXT.get(ln["basis"], "")) if ln else "No line"}</span>']
        if mk:
            inputs.append(f'<div class="small">Market ({mk["n_sources"]} source{"s" if mk["n_sources"] > 1 else ""}): '
                          f'{esc(r["team_a"])} {pct(mk["prob_a"])}</div>')
        if md:
            inputs.append(f'<div class="small">VRS model: {esc(r["team_a"])} {pct(md["prob_a"])} '
                          f'(Δ {md["delta_points"]:+d} pts)</div>')
        flags = [f for f in r["flags"] if not f.startswith("api_only")]
        if flags:
            inputs.append(f'<div><a class="badge b-flag" href="flagged.html#f-{esc(r["fixture_id"])}">'
                          f'{len(flags)} flag{"s" if len(flags) > 1 else ""}</a></div>')
        src = [f'<a href="{esc(r["hotspawn_url"])}" rel="noopener">HotSpawn {esc(r["hotspawn_url_kind"])}</a>']
        for qq in r.get("quotes", []):
            src.append(f'<a href="{esc(qq["public_url"])}" rel="noopener">{esc(qq["source_name"])}</a>')
        if r["vrs"].get("page_url") and (r["vrs"].get("team_a") or r["vrs"].get("team_b")):
            src.append(f'<a href="{esc(r["vrs"]["page_url"])}" rel="noopener">Valve VRS</a>')
        meta = (f'<span data-t="{esc(r["start_utc"])}">{esc(r["start_utc"])}</span>'
                f'<div class="small">locks <span data-r="{esc(r["lock_utc"])}">{esc(r["lock_utc"])}</span></div>'
                f'<div class="small">{esc(r.get("competition"))} · Tier {esc(r.get("tier") or "?")} · {esc(r.get("points"))} pts</div>')
        out.append(
            f'<tr data-row data-s="{esc(s)}" data-lock="{esc(r["lock_utc"])}" data-tier="{esc(r.get("tier") or "")}" '
            f'data-line="{esc(ln["basis"] if ln else "none")}" id="m-{esc(r["fixture_id"])}">'
            f'<td data-l="When">{meta}</td><td data-l="Win probability">{teams}</td>'
            f'<td data-l="Pick" class="pickcell">{pick}</td><td data-l="Fair odds (pick)">{odds}</td>'
            f'<td data-l="Inputs">{"".join(inputs)}</td><td data-l="Sources" class="src">{"".join(src)}</td></tr>')
    out.append("</tbody></table></div>")
    return "".join(out)


def render_index(b: dict) -> str:
    s = b["summary"]
    cal = b["calibration"]
    tiers = sorted({r.get("tier") for r in b["open"] if r.get("tier")})
    chips = ['<button class="chip on" data-m="all">All</button>', '<button class="chip" data-m="24h">Locks &lt; 24h</button>',
             '<button class="chip" data-m="line">Has pick</button>', '<button class="chip" data-m="noline">No line</button>']
    chips += [f'<button class="chip" data-m="tier-{esc(t)}">Tier {esc(t)}</button>' for t in tiers]
    fallback = ""
    if b.get("hotspawn_fallback_from"):
        fallback = (f'<div class="note"><b>HotSpawn was unreachable on this run.</b> Fixture list carried over from '
                    f'{esc(b["hotspawn_fallback_from"])} UTC. See <a href="flagged.html#access">source access</a>.</div>')
    recent = ""
    if b["locked_recent"]:
        rows = []
        for r in b["locked_recent"]:
            last = (r.get("last_open_line") or {}).get("line")
            rows.append(f'<tr><td data-l="Started"><span data-t="{esc(r["start_utc"])}">{esc(r["start_utc"])}</span></td>'
                        f'<td data-l="Match">{esc(r["team_a"])} vs {esc(r["team_b"])}<div class="small">{esc(r.get("competition"))}</div></td>'
                        f'<td data-l="Our last line before lock">{(esc(last["pick_team"]) + " " + pct(last["pick_prob"])) if last else "<span class=small>not observed open by this board</span>"}</td>'
                        f'<td data-l="Source"><a href="{esc(r["hotspawn_url"])}">HotSpawn {esc(r["hotspawn_url_kind"])}</a></td></tr>')
        recent = ('<h2>Locked in the last 24 hours</h2><p class="mut">Picks are closed for these. Shown with the last line this board '
                  'published while the match was still open.</p><table class="cards"><thead><tr><th>Started</th><th>Match</th>'
                  '<th>Our last line before lock</th><th>Source</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>")
    body = f"""
<h1>Pick &amp; win probability for every open HotSpawn CS2 match</h1>
<p class="mut">Every CS2 fixture currently open for picks in the <a href="{LOBBY}">HotSpawn Pick'ems lobby</a>, with our
originated line: bookmaker prices (Pinnacle, Bovada, Melbet, Kalshi) with the margin removed, blended with Valve's official VRS
rating model calibrated to those prices. The <b>PICK</b> is the team our line makes more likely to win. Refreshed automatically.</p>
{fallback}
<div class="stats">
<div class="stat"><b>{s["open"]}</b><span>open matches</span></div>
<div class="stat"><b>{s["with_line"]}</b><span>with a pick</span></div>
<div class="stat"><b>{s["market_based"]}</b><span>priced by bookmakers</span></div>
<div class="stat"><b>{s["model_only"]}</b><span>VRS model only</span></div>
<div class="stat"><b>{s["no_line"]}</b><span>no line (flagged)</span></div>
<div class="stat"><b>{(str(b["track_record"]["all"]["correct"]) + "/" + str(b["track_record"]["all"]["n"])) if b["track_record"]["all"]["n"] else "—"}</b><span><a href="results.html">picks correct so far</a></span></div>
<div class="stat"><b><span data-r="{esc(b["generated_utc"])}">{esc(b["generated_utc"])}</span></b><span>last update</span></div>
</div>
<div class="tools"><input id="q" type="search" placeholder="Search team or tournament…" aria-label="Search">{"".join(chips)}</div>
<p class="small">Showing <span id="count">{s["open"]}</span> of {s["open"]} · times shown in your local time zone (hover/tap for UTC) ·
model slope k = {cal["k"]:.2f} ({"fitted on " + str(cal["n_pairs"]) + " priced fixtures" if cal["fitted"] else "Valve default — fewer than " + str(cal["min_pairs"]) + " priced fixtures so far"})</p>
{open_table(b["open"]) if b["open"] else '<p class="empty">No open CS2 fixtures were found in the lobby on this run.</p>'}
{recent}
"""
    return page("Picks", "index.html", body, b)


def render_sources(b: dict) -> str:
    rows = []
    for r in b["open"]:
        for qq in r.get("quotes", []):
            rows.append(f'<tr><td data-l="Match"><a href="index.html#m-{esc(r["fixture_id"])}">{esc(r["team_a"])} vs {esc(r["team_b"])}</a></td>'
                        f'<td data-l="Source"><a href="{esc(qq["public_url"])}">{esc(qq["source_name"])}</a><div class="small">event {esc(qq["event_id"])}</div></td>'
                        f'<td data-l="Names at source">{esc(qq["names_at_source"][0])} / {esc(qq["names_at_source"][1])}</td>'
                        f'<td data-l="Raw price">{esc(qq["raw_a"])} / {esc(qq["raw_b"])} <span class="small">{esc(qq["raw_format"])}</span></td>'
                        f'<td data-l="No-vig">{esc(r["team_a"])} {pct(qq["no_vig_prob_team_a"])}</td>'
                        f'<td data-l="Retrieved"><span data-t="{esc(qq["retrieved_utc"])}">{esc(qq["retrieved_utc"])}</span></td>'
                        f'<td data-l="API"><a href="{esc(qq["api_url"])}">endpoint</a></td></tr>')
    um = []
    for qq in b["unmatched_quotes"][:300]:
        um.append(f'<tr><td data-l="Source"><a href="{esc(qq["public_url"])}">{esc(qq["source_name"])}</a></td>'
                  f'<td data-l="Event">{esc(qq["team_a"])} vs {esc(qq["team_b"])}<div class="small">{esc(qq.get("league"))}</div></td>'
                  f'<td data-l="Start at source">{esc(qq.get("start_utc"))}</td>'
                  f'<td data-l="Price">{esc(qq["decimal_a"])} / {esc(qq["decimal_b"])}</td></tr>')
    vr = []
    seen = set()
    for r in b["open"]:
        for side in ("team_a", "team_b"):
            t = r["vrs"].get(side)
            if t and t["team"] not in seen:
                seen.add(t["team"])
                vr.append(f'<tr><td data-l="HotSpawn name">{esc(r[side])}</td><td data-l="VRS team">{esc(t["team"])}</td>'
                          f'<td data-l="Standing">#{t["standing"]}</td><td data-l="Points">{t["points"]}</td>'
                          f'<td data-l="Source"><a href="{esc(b["vrs"]["page_url"])}">Valve VRS {esc(b["vrs"]["snapshot"])}</a></td></tr>')
    body = f"""
<h1>Lines &amp; sources</h1>
<p class="mut">Every external price used on the Picks page, exactly as read from the source, with the margin-free probability derived from it.
Each row links to the official bookmaker/exchange page and the public endpoint it was read from.</p>
<h2>Prices used ({len(rows)})</h2>
<table class="cards"><thead><tr><th>Match</th><th>Source</th><th>Names at source</th><th>Raw price</th><th>No-vig</th><th>Retrieved</th><th>API</th></tr></thead>
<tbody>{"".join(rows) or '<tr><td colspan=7 class="empty">No external price matched an open fixture on this run.</td></tr>'}</tbody></table>
<h2>Valve VRS ratings used ({len(vr)})</h2>
<table class="cards"><thead><tr><th>HotSpawn name</th><th>VRS team</th><th>Standing</th><th>Points</th><th>Source</th></tr></thead>
<tbody>{"".join(vr) or '<tr><td colspan=5 class="empty">No VRS ratings matched.</td></tr>'}</tbody></table>
<h2>CS2 prices not matched to any open HotSpawn fixture ({len(b["unmatched_quotes"])})</h2>
<p class="mut">Listed for transparency. These are events the lobby does not list, or listings whose names/times did not pass the strict join rules.</p>
<table class="cards"><thead><tr><th>Source</th><th>Event</th><th>Start at source (UTC)</th><th>Decimal prices</th></tr></thead>
<tbody>{"".join(um) or '<tr><td colspan=4>None.</td></tr>'}</tbody></table>
"""
    return page("Lines & sources", "sources.html", body, b)


FLAG_TXT = {
    "no_line_unverified": "No probability published: no bookmaker price matched and at least one team has no Valve VRS rating.",
    "not_in_vrs": "Team not found (exact normalised name) in the latest official Valve VRS global standings.",
    "ambiguous_vrs_name": "Two VRS rows normalise to the same name — rating not used.",
    "alias_join": "Price joined through a published team-name alias (see Method).",
    "model_and_market_pick_different_teams": "VRS model and bookmaker market favour different teams.",
    "api_only_not_on_cached_lobby_page": "Fixture is in the lobby's public fixtures API but not yet in the (cached) lobby page.",
    "in_play_price_seen_and_excluded": "An in-play price was seen and excluded (pre-match prices only).",
    "start_time_mismatch_not_joined": "A price for the same teams exists but its start time differs from HotSpawn's by more than 14 h; not used (see table below).",
    "vrs_duplicate_resolved_by_latest_match": "VRS lists this name twice (two rosters); the row whose official details file shows the most recent counted match was used.",
}


def flag_text(f: str) -> str:
    key = f.split(":")[0]
    if key.startswith("start_time_differs"):
        return f"Source start time differs from HotSpawn by {key.split('_')[-1]} ({f.split(':')[1]}). Joined because the same pairing is within ±14 h."
    if key.startswith("model_market_gap"):
        return f"VRS model and market differ by {key.split('_')[-1]}."
    if key.startswith("sources_disagree"):
        return f"Bookmakers disagree by {key.split('_')[-1]} on this match."
    txt = FLAG_TXT.get(key, key)
    return txt + (f" ({f.split(':', 1)[1]})" if ":" in f else "")


def render_flagged(b: dict, review: dict) -> str:
    rows = []
    for r in b["open"]:
        flags = r["flags"]
        if not flags:
            continue
        extra = []
        base = "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/"
        for side, info in (r.get("vrs_ambiguous") or {}).items():
            for c in (info or {}).get("candidates", []):
                extra.append(f'<li class="small">{esc(r[side])} candidate: #{esc(c.get("standing"))}, {esc(c.get("points"))} pts, '
                             f'roster {esc(c.get("roster"))}, last counted match {esc(c.get("latest_match_date") or "unknown")} '
                             f'(<a href="{base}{esc(c.get("details_path"))}">VRS details</a>)</li>')
        for side in ("team_a", "team_b"):
            t = (r.get("vrs") or {}).get(side) or {}
            for c in t.get("resolved_from_duplicates") or []:
                used = " — used" if c.get("details_path") == t.get("details_path") else ""
                extra.append(f'<li class="small">{esc(r[side])} VRS row #{esc(c.get("standing"))}, {esc(c.get("points"))} pts, '
                             f'last counted match {esc(c.get("latest_match_date"))}{used} '
                             f'(<a href="{base}{esc(c.get("details_path"))}">VRS details</a>)</li>')
        rows.append(f'<tr id="f-{esc(r["fixture_id"])}"><td data-l="Match"><a href="index.html#m-{esc(r["fixture_id"])}">{esc(r["team_a"])} vs {esc(r["team_b"])}</a>'
                    f'<div class="small">{esc(r.get("competition"))} · <span data-t="{esc(r["start_utc"])}">{esc(r["start_utc"])}</span></div></td>'
                    f'<td data-l="Status">{"<span class=empty>Unverified — blank</span>" if not r["line"] else "Published with flag"}</td>'
                    f'<td data-l="Flags"><ul>{"".join("<li>" + esc(flag_text(f)) + "</li>" for f in flags)}{"".join(extra)}</ul></td>'
                    f'<td data-l="Sources"><a href="{esc(r["hotspawn_url"])}">HotSpawn</a> · <a href="{esc(r["vrs"].get("page_url") or VALVE_README)}">Valve VRS</a>'
                    + "".join(f' · <a href="{esc(qq["public_url"])}">{esc(qq["source_name"])}</a>' for qq in r.get("quotes", [])) + "</td></tr>")
    acc = []
    for name, a in sorted(b["access"].items()):
        acc.append(f'<tr><td data-l="Source">{esc(name)}</td><td data-l="Result">{"OK" if a["ok"] else "<span class=empty>FAILED / blocked</span>"}</td>'
                   f'<td data-l="HTTP">{esc(a.get("status"))} {esc(a.get("error") or "")}{" challenge page" if a.get("looks_like_challenge") else ""}</td>'
                   f'<td data-l="Detail">{esc(a.get("quotes") if a.get("quotes") is not None else (a.get("rows") or a.get("fixtures_in_transfer_state") or ""))}'
                   f'{" · cache Age " + esc(a.get("age_header")) + " s" if a.get("age_header") else ""}</td>'
                   f'<td data-l="URL"><a href="{esc(a.get("url"))}">{esc((a.get("url") or "")[:70])}</a></td></tr>')
    rj = []
    for r in b["open"]:
        for x in r.get("rejected_joins", []):
            rj.append(f'<tr><td data-l="HotSpawn match"><a href="index.html#m-{esc(r["fixture_id"])}">{esc(r["team_a"])} vs {esc(r["team_b"])}</a>'
                      f'<div class="small">HotSpawn start {esc(r["start_utc"])}</div></td>'
                      f'<td data-l="Source"><a href="{esc(x["public_url"])}">{esc(x["source_name"])}</a> event {esc(x["event_id"])}</td>'
                      f'<td data-l="Source start (UTC)">{esc(x["start_utc_at_source"])} ({x["start_diff_h"]} h apart)</td>'
                      f'<td data-l="Price not used">{esc(x["decimal"][0])} / {esc(x["decimal"][1])}</td></tr>')
    sc = []
    for f in b.get("status_conflicts", []):
        sc.append(f'<tr><td data-l="Fixture">{esc(f["fixture_id"])}</td><td data-l="Match">{esc(f["team_a"])} vs {esc(f["team_b"])}<div class="small">{esc(f["competition"])}</div></td>'
                  f'<td data-l="Status at source">{esc(f["status"])}</td><td data-l="Scheduled start (UTC)">{esc(f["start_utc"])}</td>'
                  f'<td data-l="Source"><a href="{HS_API_PUBLIC}">HotSpawn fixtures API</a></td></tr>')
    rej = []
    for x in b["rejected_quotes"]:
        rej.append(f'<tr><td data-l="Exchange event"><a href="{esc(x["public_url"])}">{esc(x["event_id"])}</a></td>'
                   f'<td data-l="Teams">{esc(x["team_a"])} / {esc(x["team_b"])}</td><td data-l="Reason">{esc(x["reason"])}</td></tr>')
    stale = []
    for f in b["stale_listed"][:200]:
        stale.append(f'<tr><td data-l="Fixture">{esc(f["fixture_id"])}</td><td data-l="Match">{esc(f["team_a"])} vs {esc(f["team_b"])}</td>'
                     f'<td data-l="Competition">{esc(f["competition"])}</td><td data-l="Scheduled (UTC)">{esc(f["start_utc"])}</td>'
                     f'<td data-l="Status at source">{esc(f["status"])}</td><td data-l="Source"><a href="{LOBBY}">lobby</a></td></tr>')
    rv = []
    for it in review.get("findings", []):
        links = " · ".join(f'<a href="{esc(u)}">{esc(t)}</a>' for t, u in it.get("links", []))
        rv.append(f'<tr><td data-l="ID">{esc(it["id"])}</td><td data-l="Finding">{esc(it["finding"])}'
                  + (f'<br><b>Update:</b> {esc(it["update_2026_10_14"])}' if it.get("update_2026_10_14") else "") + '</td>'
                  f'<td data-l="Status">{esc(it["status"])}</td><td data-l="Evidence">{links}</td></tr>')
    body = f"""
<h1>Flagged for review</h1>
<p class="mut">Everything this board could not confirm, joined through an alias, or found irregular. Nothing here is filled in or guessed:
an unverifiable probability stays blank. Flagged items do not block publication.</p>
<h2>Open matches with flags ({len(rows)})</h2>
<table class="cards"><thead><tr><th>Match</th><th>Status</th><th>Flags</th><th>Sources</th></tr></thead>
<tbody>{"".join(rows) or "<tr><td colspan=4>None.</td></tr>"}</tbody></table>
<h2 id="access">Source access on this run</h2>
<table class="cards"><thead><tr><th>Source</th><th>Result</th><th>HTTP</th><th>Detail</th><th>URL</th></tr></thead><tbody>{"".join(acc)}</tbody></table>
<h2>Prices not joined: same teams but start time too far apart ({len(rj)})</h2>
<p class="mut">The pairing matches but the source's start time differs from HotSpawn's by more than {core.TIME_TOLERANCE_H:.0f} h, so it could be a
different meeting of the same teams. The price is shown here and not used.</p>
<table class="cards"><thead><tr><th>HotSpawn match</th><th>Source</th><th>Source start (UTC)</th><th>Price not used</th></tr></thead><tbody>{"".join(rj) or "<tr><td colspan=4>None.</td></tr>"}</tbody></table>
<h2>Status conflicts in HotSpawn data ({len(sc)})</h2>
<p class="mut">Fixtures whose HotSpawn status is not "scheduled" although their lock time is still in the future. Not treated as open.</p>
<table class="cards"><thead><tr><th>Fixture</th><th>Match</th><th>Status at source</th><th>Scheduled start (UTC)</th><th>Source</th></tr></thead><tbody>{"".join(sc) or "<tr><td colspan=5>None.</td></tr>"}</tbody></table>
<h2>Exchange books rejected as too thin ({len(rej)})</h2>
<table class="cards"><thead><tr><th>Exchange event</th><th>Teams</th><th>Reason</th></tr></thead><tbody>{"".join(rej) or "<tr><td colspan=3>None.</td></tr>"}</tbody></table>
<h2>Listed by the lobby page but lock time long past ({len(b["stale_listed"])})</h2>
<p class="mut">These fixtures are still served in the lobby page's own fixture data with status "scheduled" although their lock time passed more than
{RECENT_LOCK_H} h ago. They cannot be picked, so they are excluded from the Picks page.</p>
<table class="cards"><thead><tr><th>Fixture</th><th>Match</th><th>Competition</th><th>Scheduled (UTC)</th><th>Status at source</th><th>Source</th></tr></thead>
<tbody>{"".join(stale) or "<tr><td colspan=6>None.</td></tr>"}</tbody></table>
<h2 id="repo">Repository review findings (session f7279a54)</h2>
<p class="mut">{esc(review.get("intro", ""))}</p>
<table class="cards"><thead><tr><th>ID</th><th>Finding</th><th>Status</th><th>Evidence</th></tr></thead><tbody>{"".join(rv)}</tbody></table>
"""
    return page("Flagged for review", "flagged.html", body, b)


def render_results(b: dict, track: dict) -> str:
    tr = b["track_record"]
    def line(label, a):
        if not a["n"]:
            return f"<tr><td data-l='Basis'>{esc(label)}</td><td data-l='Graded' colspan=4>no graded picks yet</td></tr>"
        return (f"<tr><td data-l='Basis'>{esc(label)}</td><td data-l='Graded'>{a['n']}</td>"
                f"<td data-l='Correct'>{a['correct']} ({pct(a['accuracy'])})</td>"
                f"<td data-l='Avg. pick probability'>{pct(a['mean_pick_prob'])}</td>"
                f"<td data-l='Brier score'>{a['brier']:.3f}</td></tr>")
    rows = []
    for r in sorted(track.values(), key=lambda x: x["start_utc"], reverse=True)[:400]:
        rows.append(f"<tr><td data-l='Started'><span data-t='{esc(r['start_utc'])}'>{esc(r['start_utc'])}</span></td>"
                    f"<td data-l='Match'>{esc(r['teams'][0])} vs {esc(r['teams'][1])}<div class='small'>{esc(r.get('competition'))}</div></td>"
                    f"<td data-l='Our pick'>{esc(r['pick_team'])} {pct(r['pick_prob'])}<div class='small'>{esc(BASIS_TXT.get(r['basis'], r['basis']))}</div></td>"
                    f"<td data-l='Winner (HotSpawn result)'>{esc(r['winner_team'])}</td>"
                    f"<td data-l='Result'>{'✅ correct' if r['correct'] else '❌ wrong'}</td>"
                    f"<td data-l='Source'><a href='{HS_API_PUBLIC}'>HotSpawn fixtures API</a></td></tr>")
    body = f"""
<h1>Track record</h1>
<p class="mut">Every pick this board published while a match was open is graded once HotSpawn's own fixture data reports the match as
<i>ended</i> with a winner. The line graded is the last one published before the match locked. Tracking started with this board on
2026-10-14, so early numbers are based on few matches and say little yet.</p>
<table class="cards"><thead><tr><th>Basis</th><th>Graded</th><th>Correct</th><th>Avg. pick probability</th><th>Brier score</th></tr></thead><tbody>
{line("All picks", tr["all"])}{line(BASIS_TXT["market+model"], tr["by_basis"]["market+model"])}
{line(BASIS_TXT["market"], tr["by_basis"]["market"])}{line(BASIS_TXT["model"], tr["by_basis"]["model"])}</tbody></table>
<p class="small">Brier score = mean of (our probability for team A − 1 if A won else 0)²; lower is better, 0.25 equals always saying 50%.
If our probabilities are well calibrated, "Correct" should be close to "Avg. pick probability" over many matches.</p>
<h2>Graded matches ({len(track)})</h2>
<table class="cards"><thead><tr><th>Started</th><th>Match</th><th>Our pick</th><th>Winner (HotSpawn result)</th><th>Result</th><th>Source</th></tr></thead>
<tbody>{"".join(rows) or "<tr><td colspan=6>No graded matches yet — results appear here automatically after matches end.</td></tr>"}</tbody></table>
"""
    return page("Track record", "results.html", body, b)


def render_method(b: dict) -> str:
    cal = b["calibration"]
    from core import ALIASES, SOURCE_WEIGHTS, VALVE_G, KALSHI_MAX_SPREAD, TIME_TOLERANCE_H
    al = "".join(f"<tr><td data-l='Source spelling (normalised)'><code>{esc(k)}</code></td><td data-l='HotSpawn team'><code>{esc(v[0])}</code></td><td data-l='Basis'>{esc(v[1])}</td></tr>"
                 for k, v in ALIASES.items())
    wt = ", ".join(f"{esc(k)} {v:g}" for k, v in SOURCE_WEIGHTS.items())
    body = f"""
<h1>Method</h1>
<div class="note">Short version: we take every bookmaker price for the match, remove the bookmaker's margin, average them, and
blend that with a rating model built on Valve's official CS2 standings. The model's steepness is learned from the bookmaker prices.
If no bookmaker prices the match, the calibrated model alone gives the line. If a team has no official rating and no bookmaker prices
the match, the row stays blank and is flagged.</div>
<h2>1. Which matches</h2>
<p>The fixture list comes from the public HotSpawn lobby (<a href="{LOBBY}">play.hotspawn.com/lobby</a>): the page embeds the response of
the lobby's own <code>/api/v1/fixtures</code> call in its Angular transfer state, and the same public endpoint is also read directly each run because the page is
served from a cache (its <code>Age</code> header is recorded on the Flagged page). A match is <b>open</b> while its HotSpawn lock time is in the future.
HotSpawn data is used only to know <i>which</i> matches exist and when they lock — crowd pick percentages are not read.</p>
<h2>2. Bookmaker and exchange prices</h2>
<ul>
<li><b>Pinnacle</b> — public guest odds API used by pinnacle.com; full-match moneyline (period 0, not alternate, status open). American odds converted to decimal.</li>
<li><b>Bovada</b> — public Counter-Strike 2 coupon JSON used by bovada.lv; main-period moneyline.</li>
<li><b>Melbet</b> — public LineFeed JSON (CS2 leagues only); match winner market.</li>
<li><b>Kalshi</b> — CFTC-regulated exchange, series <code>KXCS2GAME</code>; probability = midpoint of yes bid/ask, normalised over both teams. Books with a missing side or a spread wider than {KALSHI_MAX_SPREAD * 100:.0f}¢ are rejected.</li>
<li><b>Polymarket</b> and <b>HLTV</b> are probed each run; their result is on the Flagged page. HLTV is not machine-readable from the automated runner, so it is not a numeric input.</li>
</ul>
<p>Margin removal (proportional): <code>p_A = (1/d_A) / (1/d_A + 1/d_B)</code> where <code>d</code> are decimal odds
(implied-probability arithmetic as documented by <a href="https://help.smarkets.com/hc/en-gb/articles/214058369-How-to-calculate-implied-probability-in-betting">Smarkets</a>).
In-play prices are excluded. Market consensus = weighted mean of the per-source probabilities with weights {wt} (stated modelling choice: Pinnacle is weighted higher as a low-margin bookmaker).</p>
<p><b>Joining a price to a HotSpawn match</b> requires both team names to be equal after normalisation (case, accents, punctuation, and the
generic words <i>team / the / esports / gaming / club</i> at the start or end removed) and the source start time to be within ±{TIME_TOLERANCE_H:.0f} h.
No prefix/substring matching ("B8" never matches "B8 Academy"). Explicit aliases:</p>
<table class="cards"><thead><tr><th>Source spelling (normalised)</th><th>HotSpawn team</th><th>Basis</th></tr></thead><tbody>{al}</tbody></table>
<h2>3. Valve VRS rating model</h2>
<p>Ratings are the points in the latest official <a href="{esc(b["vrs"].get("page_url") or VALVE_README)}">Valve Regional Standings (global, {esc(b["vrs"].get("snapshot"))})</a>.
Valve's own code defines expected win rate from a points difference Δ: <a href="{VALVE_GLICKO}">model/glicko.js</a> ("rank delta of 400 points = 90% chance of victory",
<code>ev = 1/(1+10^(g·Δ/−400))</code>) evaluated with a fixed RD of 75 in <a href="{VALVE_FIT}">model/fit.js</a>, giving g = {VALVE_G:.4f}.
Valve's <a href="{VALVE_README}">readme</a> notes the curve is steeper than observed results, so we fit a slope factor <b>k</b>:
<code>p_A = 1/(1+10^(−k·g·Δ/400))</code>, by least squares of logit(market) on Δ over every fixture seen with both a market price and two ratings.</p>
<p>Current fit: k = <b>{cal["k"]:.3f}</b> {"(raw " + format(cal["k_raw"], ".3f") + ")" if cal.get("k_raw") is not None else ""} on {cal["n_pairs"]} fixtures
(minimum {cal["min_pairs"]} to fit, otherwise k = 1, Valve's own curve; k is bounded to {cal["bounds"][0]}–{cal["bounds"][1]}).
Mean absolute error vs market: calibrated {pct(cal.get("mae_prob"))}, Valve default {pct(cal.get("mae_prob_valve"))}.</p>
<h2>4. Our line and the pick</h2>
<p><code>logit(p_ours) = w·logit(p_market) + (1−w)·logit(p_model)</code> with w = 0.85 when two or more sources price the match, 0.75 with one
(stated modelling choice). Market only when a team lacks a rating; model only when no price exists. Fair odds = 1/p.
The <b>PICK</b> is the team with p ≥ 50%. Confidence: Strong ≥ 70%, Solid ≥ 60%, Lean ≥ 53%, otherwise Toss-up.</p>
<h2>5. Automation</h2>
<p><code>.github/workflows/ourline-f7279a54.yml</code> runs every 30 minutes and after each run of the repository's hourly <code>update-data</code> workflow:
<code>scripts/f7279a54/collect.py</code> → <code>scripts/f7279a54/build.py</code> → tests → commit of <code>data/f7279a54/</code> and <code>ourline/</code>,
which GitHub Pages publishes. Raw evidence: <code>data/f7279a54/snapshot.json</code>; derived board: <code>data/f7279a54/board.json</code>.</p>
<h2>Limits</h2>
<ul><li>These are estimates, not guarantees. A model-only line is weaker than a priced one and is labelled as such.</li>
<li>Bookmaker start times sometimes differ from HotSpawn's; joins with differences over 3 h are flagged.</li>
<li>Low-tier teams are often absent from both bookmakers and VRS; those rows stay blank.</li></ul>
"""
    return page("Method", "method.html", body, b)


def main() -> int:
    snap = load(DATA / "snapshot.json", None)
    if not snap:
        print("no snapshot", file=sys.stderr)
        return 1
    hist = load(DATA / "line_history.json", {})
    cal_pairs = load(DATA / "calibration_pairs.json", {})
    track = load(DATA / "track_record.json", {})
    board = build_board(snap, hist, cal_pairs, track)
    (DATA / "track_record.json").write_text(json.dumps(track, indent=1, sort_keys=True) + "\n")
    # bound history files
    if len(hist) > HIST_LIMIT:
        hist = dict(sorted(hist.items(), key=lambda kv: kv[1]["observed_utc"])[-HIST_LIMIT:])
    if len(cal_pairs) > HIST_LIMIT:
        cal_pairs = dict(sorted(cal_pairs.items(), key=lambda kv: kv[1]["observed_utc"])[-HIST_LIMIT:])
    (DATA / "line_history.json").write_text(json.dumps(hist, indent=1, sort_keys=True) + "\n")
    (DATA / "calibration_pairs.json").write_text(json.dumps(cal_pairs, indent=1, sort_keys=True) + "\n")
    (DATA / "board.json").write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n")
    review = load(DATA / "repo_review.json", {})
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "index.html").write_text(render_index(board))
    (SITE / "sources.html").write_text(render_sources(board))
    (SITE / "flagged.html").write_text(render_flagged(board, review))
    (SITE / "method.html").write_text(render_method(board))
    (SITE / "results.html").write_text(render_results(board, track))
    print(json.dumps(board["summary"], indent=1), "k=", round(board["calibration"]["k"], 3))
    return 0


if __name__ == "__main__":
    sys.exit(main())
