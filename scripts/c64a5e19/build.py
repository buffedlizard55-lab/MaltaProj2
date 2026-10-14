#!/usr/bin/env python3
"""EVERY-MATCH builder (session c64a5e19): snapshot -> board.json + picks-every-match/*.html.

Offline step. Every open HotSpawn CS2 fixture gets a pick tier:
  A Market  - accepted external price(s) (Pinnacle/Bovada/Melbet/Kalshi tight book), no-vig,
              blended with the calibrated Valve VRS model when both teams are rated.
  B Model   - no accepted price, but both teams Valve-VRS rated (calibrated VRS probability).
  C Fallback- ONLY for matches that cannot be resolved as A/B. Documented extra evidence:
              slot-priced Melbet/Kalshi books for the Elisa BreakOut slot whose HotSpawn label
              (WROTBERRY) differs from source labels (WhiteBIT Team / WBT Academy), Kalshi thin
              books (spread >10c, indicative only), the RoundsGG=ROUNDS VRS alias, and - for
              FORZE Reload vs LFO 10 - the VRS points of sibling LFO 7/8/9 rosters as a
              provisional range. Every C pick is flagged, confidence-capped, and ranged.
  D None    - no evidence at all: probability left blank, flagged (never invented).
HotSpawn crowd picked % is never read. If data/c64a5e19/snapshot.json does not exist yet
(local/offline build), the proven f7279a54 snapshot is used and that provenance is published.
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
        dated = sorted((r for r in rows if r.get("latest_match_date")), key=lambda r: r["latest_match_date"], reverse=True)
        if len(dated) == len(rows) and dated[0]["latest_match_date"] > dated[1]["latest_match_date"]:
            idx[key] = {**dated[0], "resolved_from_duplicates": [{k: r.get(k) for k in ("standing", "points", "roster", "latest_match_date", "details_path")} for r in rows]}
        else: dup[key] = {"candidates": [{k: r.get(k) for k in ("standing", "points", "roster", "latest_match_date", "details_path")} for r in rows]}
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
    m = re.search(r"-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})", str(event_id or ""))
    if not m: return None
    months = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()
    from datetime import datetime, timedelta, timezone
    try: dt = datetime(2000 + int(m.group(1)), months.index(m.group(2)) + 1, int(m.group(3)), int(m.group(4)), int(m.group(5)), tzinfo=timezone.utc)
    except ValueError: return None
    return dt + timedelta(hours=4)  # EDT approximation, join window only (as in collector)

import re
def build_board(snap, snap_source):
    now = core.parse_iso(snap["collected_to_utc"]) or core.now_utc()
    hs = snap["hotspawn"]; permalinks = hs.get("permalinks") or {}
    vrs = snap.get("vrs") or {}; idx, dup = rating_index(vrs)
    quotes = [q for q in snap.get("quotes", []) if q.get("prob_a") is not None]
    pre = [q for q in quotes if not q.get("live")]
    # thin (rejected) Kalshi books -> fallback evidence records
    thin = []
    for r in snap.get("rejected_quotes", []):
        books = r.get("books") or []
        if len(books) != 2: continue
        m0, m1 = thin_mid(books[0]), thin_mid(books[1])
        if m0 is None or m1 is None or (m0 + m1) <= 0: continue
        thin.append({"event_id": r.get("event_id"), "team_a": r.get("team_a"), "team_b": r.get("team_b"),
                     "public_url": r.get("public_url"), "mid_a": m0, "mid_b": m1,
                     "prob_a_norm": m0 / (m0 + m1), "books": books,
                     "start_approx": core.to_iso(kalshi_start_from_ticker(r.get("event_id")))})
    open_rows, stale_n, locked_n = [], 0, 0
    for fx in hs["fixtures"]:
        lock = core.parse_iso(fx.get("lock_utc")) or core.parse_iso(fx["start_utc"])
        status = str(fx.get("status") or "")
        if lock and lock > now and status == "scheduled": state = "open"
        elif status in ("scheduled", "started", "ended"): locked_n += 1; continue
        else: stale_n += 1; continue
        row = {**fx, "state": state, "hotspawn_url": permalinks.get(fx["fixture_id"]) or LOBBY,
               "hotspawn_url_kind": "match page" if fx["fixture_id"] in permalinks else "lobby", "flags": []}
        # ---- accepted market
        per_source: dict[str, dict] = {}
        for qq in pre:
            j = core.match_quote(fx, qq)
            if not j or j.get("rejected"): continue
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
        ra, ea = rating_for(fx["team_a"], idx, dup); rb, eb = rating_for(fx["team_b"], idx, dup)
        row["vrs"] = {"team_a": ra, "team_b": rb, "snapshot": vrs.get("snapshot"), "page_url": vrs.get("page_url")}
        row["_delta"] = (ra["points"] - rb["points"]) if ra and rb else None
        row["_ra"], row["_rb"], row["_ea"], row["_eb"] = ra, rb, ea, eb
        open_rows.append(row)
    # calibration from this snapshot's priced+rated fixtures
    pairs = [{"delta": r["_delta"], "market_prob_a": r["market"]["prob_a"]} for r in open_rows if r["market"] and r["_delta"] is not None]
    cal = core.fit_calibration(pairs); k = cal["k"]
    # if too few pairs in this snapshot, fall back to the published f7279a54 fitted slope (same formula)
    if not cal["fitted"]:
        prev = load(DATA.parent / "f7279a54" / "board.json", {})
        pk = ((prev.get("calibration") or {}).get("k"))
        if isinstance(pk, (int, float)) and prev.get("calibration", {}).get("fitted"):
            k = float(pk); cal = {**cal, "k": k, "fitted": True, "borrowed_from": "f7279a54 published calibration (same Valve formula)"}
    min_pts = min((t["points"] for t in vrs.get("teams", [])), default=None)
    for row in open_rows:
        delta = row.pop("_delta"); ra, rb, ea, eb = row.pop("_ra"), row.pop("_rb"), row.pop("_ea"), row.pop("_eb")
        model_p = core.vrs_prob(delta, 0, k) if delta is not None else None
        row["model"] = ({"prob_a": round(model_p, 4), "prob_b": round(1 - model_p, 4), "delta_points": delta, "k": round(k, 4)} if model_p is not None else None)
        mkt = row["market"]
        line = core.blend(mkt["prob_a"] if mkt else None, mkt["n_sources"] if mkt else 0, model_p)
        flags = row["flags"]
        fallback = None
        if line:
            tier = "A" if line["basis"] != "model" else "B"
        else:
            # ---------------- Fallback C: only where A/B impossible ----------------
            tier = "D"; prob_a = None; ev = []
            # The generic slot orientation above is fragile; Elisa-specific explicit handling:
            slot_prob_a = None; slot_q = None
            if "elisa" in str(row.get("competition") or "").lower():
                for qq in pre:
                    if qq.get("start_utc") != row["start_utc"]: continue
                    qa, qb = qq["team_a"], qq["team_b"]
                    # fixture team that appears in quote (via canon, incl EAC alias)
                    fa_in_a, _ = core.same_team(row["team_a"], qa); fa_in_b, _ = core.same_team(row["team_a"], qb)
                    fb_in_a, _ = core.same_team(row["team_b"], qa); fb_in_b, _ = core.same_team(row["team_b"], qb)
                    if (fa_in_a or fa_in_b) ^ (fb_in_a or fb_in_b):
                        # exactly one fixture team named at source; the other source label is the slot label
                        if fa_in_a: slot_prob_a = qq["prob_a"]
                        elif fa_in_b: slot_prob_a = 1 - qq["prob_a"]
                        elif fb_in_a: slot_prob_a = 1 - qq["prob_a"]
                        else: slot_prob_a = qq["prob_a"]
                        slot_q = qq; break
            if slot_q is not None:
                prob_a = slot_prob_a; tier = "C"
                ev.append({"kind": "slot_bookmaker_price", "source": slot_q["source_name"], "public_url": slot_q["public_url"], "api_url": slot_q["api_url"], "event_id": slot_q["event_id"], "names_at_source": [slot_q["team_a"], slot_q["team_b"]], "decimal": [slot_q["decimal_a"], slot_q["decimal_b"]], "prob_team_a": round(prob_a, 4), "note": "Price for the same Elisa BreakOut slot (same competition, same UTC start, same opponent) under a different team label at source. Not joined as a featured price; used only as fallback guidance."})
                flags.append("fallback_slot_price_label_differs_at_source")
            # C1b thin Kalshi books (direct or Elisa slot)
            thin_probs = []
            for th in thin:
                th_start = core.parse_iso(th.get("start_approx")); fx_start = core.parse_iso(row["start_utc"])
                if th_start and fx_start and abs((th_start - fx_start).total_seconds()) >= 2 * 3600: continue
                ta, tb = th["team_a"], th["team_b"]
                direct = (core.same_team(row["team_a"], ta)[0] and core.same_team(row["team_b"], tb)[0])
                swapped = (core.same_team(row["team_a"], tb)[0] and core.same_team(row["team_b"], ta)[0])
                slot_thin = False; p_thin = None
                if direct: p_thin = th["prob_a_norm"]
                elif swapped: p_thin = 1 - th["prob_a_norm"]
                elif "elisa" in str(row.get("competition") or "").lower():
                    fa = core.same_team(row["team_a"], ta)[0] or core.same_team(row["team_a"], tb)[0]
                    fb = core.same_team(row["team_b"], ta)[0] or core.same_team(row["team_b"], tb)[0]
                    if fa ^ fb:
                        slot_thin = True
                        # orient: if fixture team_a is quote team_a -> prob_a_norm; team_b in quote a -> 1-; etc.
                        if core.same_team(row["team_a"], ta)[0]: p_thin = th["prob_a_norm"]
                        elif core.same_team(row["team_a"], tb)[0]: p_thin = 1 - th["prob_a_norm"]
                        elif core.same_team(row["team_b"], ta)[0]: p_thin = 1 - th["prob_a_norm"]
                        else: p_thin = th["prob_a_norm"]
                if p_thin is None: continue
                # time check via ticker (approx, +-36h window like collector)
                thin_probs.append(p_thin)
                ev.append({"kind": "kalshi_thin_book_slot" if slot_thin else "kalshi_thin_book", "source": "Kalshi (exchange)", "public_url": th["public_url"], "event_id": th["event_id"], "names_at_source": [ta, tb], "mids": [round(th["mid_a"], 3), round(th["mid_b"], 3)], "prob_team_a_normalised_mid": round(p_thin, 4), "note": "Thin book rejected from featured prices (spread >10c). Indicative only."})
                flags.append("fallback_kalshi_thin_book_indicative")
            if tier != "C" and thin_probs:
                # thin + alias model (RoundsGG) or thin alone
                if model_p is not None:
                    prob_a = (model_p + sum(thin_probs) / len(thin_probs)) / 2; flags.append("fallback_model_plus_thin_book")
                else:
                    prob_a = sum(thin_probs) / len(thin_probs)
                tier = "C"
            elif tier == "C" and thin_probs and slot_q is not None:
                pass  # slot price stays primary; thin listed as corroboration range
            # C2 originated sibling/floor rating
            if tier == "D" and (ra or rb):
                rated, other_name = (ra, row["team_b"]) if ra and not rb else ((rb, row["team_a"]) if rb and not ra else (None, None))
                if rated:
                    first = str(other_name).split()[0].lower() if other_name else ""
                    sibs = [t for t in vrs.get("teams", []) if str(t["team"]).split()[0].lower() == first and core.canon(t["team"])[0] != core.canon(other_name)[0]]
                    if sibs:
                        probs = [core.vrs_prob(rated["points"], s["points"], k) if rated is ra else 1 - core.vrs_prob(s["points"], rated["points"], k) for s in sibs]
                        # probs above are P(rated beats sib); convert to P(team_a)
                        pa_list = []
                        for s in sibs:
                            p_rated = core.vrs_prob(rated["points"], s["points"], k)
                            pa_list.append(p_rated if rated is ra else 1 - p_rated)
                        prob_a = sum(pa_list) / len(pa_list); tier = "C"
                        ev.append({"kind": "originated_sibling_vrs_range", "source": "Valve VRS (official)", "public_url": vrs.get("page_url"), "siblings": [{"team": s["team"], "points": s["points"], "standing": s["standing"]} for s in sibs], "rated_team_points": rated["points"], "prob_team_a_range": [round(min(pa_list), 4), round(max(pa_list), 4)], "note": f"No VRS row for {other_name}. Provisional range uses the official VRS points of sibling rosters {', '.join(s['team'] for s in sibs)} from the same file. Originated estimate - not a verified rating for this roster."})
                        flags.append("fallback_originated_sibling_vrs_range_unverified_roster")
                    elif min_pts is not None:
                        p_rated = core.vrs_prob(rated["points"], min_pts, k)
                        prob_a = p_rated if rated is ra else 1 - p_rated; tier = "C"
                        ev.append({"kind": "originated_floor_vrs", "source": "Valve VRS (official)", "public_url": vrs.get("page_url"), "rated_team_points": rated["points"], "floor_points": min_pts, "note": "Opponent has no VRS row; provisional floor = lowest points in the official file. Originated upper-bound estimate."})
                        flags.append("fallback_originated_floor_rating_unverified")
            # corroboration: same-start quote with one team matching but opponent label differing (not joined)
            for qq in pre:
                if qq.get("start_utc") != row["start_utc"]: continue
                if any(e.get("event_id") == qq["event_id"] for e in ev): continue
                ma = core.same_team(row["team_a"], qq["team_a"])[0] or core.same_team(row["team_a"], qq["team_b"])[0]
                mb = core.same_team(row["team_b"], qq["team_a"])[0] or core.same_team(row["team_b"], qq["team_b"])[0]
                if ma ^ mb:
                    ev.append({"kind": "corroboration_opponent_label_differs_not_joined", "source": qq["source_name"], "public_url": qq["public_url"], "event_id": qq["event_id"], "names_at_source": [qq["team_a"], qq["team_b"]], "note": "Same UTC start and one team matches, but the opponent label differs from HotSpawn's. Shown as direction corroboration only; NOT joined and NOT averaged into the probability."})
                    flags.append("corroboration_opponent_label_differs_not_joined")
            if tier == "C" and prob_a is not None:
                line = {"basis": "fallback", "market_weight": 0.0, "prob_a": prob_a, "prob_b": 1 - prob_a}
                # range from evidence probs
                cand = [e["prob_team_a"] for e in ev if isinstance(e.get("prob_team_a"), (int, float))] + [e["prob_team_a_normalised_mid"] for e in ev if isinstance(e.get("prob_team_a_normalised_mid"), (int, float))]
                for e in ev:
                    rge = e.get("prob_team_a_range")
                    if rge: cand += list(rge)
                fallback = {"evidence": ev, "prob_a_range": [round(min(cand), 4), round(max(cand), 4)] if cand else None}
            else:
                fallback = {"evidence": ev, "prob_a_range": None}
                flags.append("no_line_unverified")
        # alias / thin corroboration notes for A/B rows (prob unchanged)
        for nm in (row["team_a"], row["team_b"]):
            _, note = core.canon(nm)
            if note: flags.append(f"alias_used:{nm}")
        if line and tier in ("A", "B"):
            corr = []
            fx_start2 = core.parse_iso(row["start_utc"])
            for th in thin:
                th_start = core.parse_iso(th.get("start_approx"))
                if th_start and fx_start2 and abs((th_start - fx_start2).total_seconds()) >= 2 * 3600: continue
                if (core.same_team(row["team_a"], th["team_a"])[0] and core.same_team(row["team_b"], th["team_b"])[0]) or (core.same_team(row["team_a"], th["team_b"])[0] and core.same_team(row["team_b"], th["team_a"])[0]):
                    corr.append({"source": "Kalshi (exchange)", "public_url": th["public_url"], "event_id": th["event_id"], "names_at_source": [th["team_a"], th["team_b"]], "note": "Thin book (spread >10c) for this exact fixture - corroboration only, not averaged into the featured probability."})
            if corr:
                row["thin_corroboration"] = corr; flags.append("thin_book_corroboration_only")
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
        if "elisa" in str(row.get("competition") or "").lower(): srcs.append({"label": "Liquipedia — Elisa BreakOut #2 (participants/fixtures)", "url": LIQUIPEDIA_ELISA})
        row["sources"] = srcs
    open_rows.sort(key=lambda r: (r["lock_utc"] or r["start_utc"], r["fixture_id"]))
    summary = {"open": len(open_rows), "tier_a_market": sum(1 for r in open_rows if r["line"] and r["line"]["tier"] == "A"), "tier_b_model": sum(1 for r in open_rows if r["line"] and r["line"]["tier"] == "B"), "tier_c_fallback": sum(1 for r in open_rows if r["line"] and r["line"]["tier"] == "C"), "tier_d_none": sum(1 for r in open_rows if not r["line"]), "with_pick": sum(1 for r in open_rows if r["line"]), "locked_or_past_listed": locked_n}
    return {"session": "c64a5e19", "generated_utc": snap["collected_to_utc"], "snapshot_source": snap_source, "snapshot_session": snap.get("session"), "week": hs.get("week"), "summary": summary, "calibration": {**cal, "pairs_used": len(pairs)}, "vrs": {k2: vrs.get(k2) for k2 in ("snapshot", "page_url", "api_url")}, "open": open_rows, "access": snap.get("access_log", {})}

# ------------------------------------------------------------------ rendering
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
document.querySelectorAll('[data-r]').forEach(function(e){e.textContent=rel(e.dataset.r);});})();
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
<p class="foot">Data collected {esc(board["generated_utc"])} UTC (<span data-r="{esc(board["generated_utc"])}"></span>) by an automated GitHub Actions run — no manual input. Probabilities are estimates derived from external bookmaker/exchange prices and Valve's official VRS ratings; HotSpawn crowd picks are never used. Fallback (C) picks use only the extra documented sources on the method page and are flagged individually. Not affiliated with HotSpawn or any bookmaker. Not betting advice. Section owner: session <code>c64a5e19</code>.</p>
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
    return (f'<div class="pickcard"><div class="when"><span data-t="{esc(r["start_utc"])}">{esc(r["start_utc"])}</span> · locks <span data-r="{esc(r["lock_utc"])}">{esc(r["lock_utc"])}</span> · {esc(r.get("competition"))} · Tier {esc(r.get("tier") or "?")}</div>'
            f'<div class="teams"><span class="team{" pk" if ln and ln["pick_side"]=="a" else ""}">{esc(r["team_a"])} <span class="pct">{pct(ln["prob_a"]) if ln else "—"}</span></span>'
            f'<span class="team{" pk" if ln and ln["pick_side"]=="b" else ""}" style="text-align:right">{esc(r["team_b"])} <span class="pct">{pct(ln["prob_b"]) if ln else "—"}</span></span></div>{meter}'
            f'<div><b>{esc(pick)}</b> {badge} <a href="picks.html#m-{esc(r["fixture_id"])}">details &amp; sources →</a></div></div>')

def render_index(b):
    s = b["summary"]
    cards = "".join(glance_card(r) for r in b["open"])
    body = f"""
<h1>Executive summary — where the picks are</h1>
<p class="mut">You want one place that tells you, on your phone, who to pick in every HotSpawn CS2 Pick'ems match. <b>This page is that place.</b> Every currently-open CS2 match is listed below with a pick and a win probability. It refreshes automatically (about every 30 minutes) — no manual input.</p>
<div class="stats">
<div class="stat"><b>{s["open"]}</b><span>matches open for picks</span></div>
<div class="stat"><b>{s["with_pick"]}</b><span>with a pick on this page</span></div>
<div class="stat"><b>{s["tier_a_market"]}</b><span>A · priced by bookmakers</span></div>
<div class="stat"><b>{s["tier_b_model"]}</b><span>B · VRS model only</span></div>
<div class="stat"><b>{s["tier_c_fallback"]}</b><span>C · fallback sources (flagged)</span></div>
<div class="stat"><b>{s["tier_d_none"]}</b><span>D · no evidence (blank)</span></div>
<div class="stat"><b><span data-r="{esc(b["generated_utc"])}">{esc(b["generated_utc"])}</span></b><span>last update ({esc(b["generated_utc"])} UTC)</span></div>
</div>
<h2>📱 On your phone — do this</h2>
<div class="note"><b>1.</b> Read the pick cards below (biggest, boldest team = our pick, % = win probability). <b>2.</b> Tap <i>details &amp; sources</i> on any match to see exactly which bookmaker prices / ratings produced the number. <b>3.</b> Matches marked <span class="badge b-C">C · Fallback</span> had no normal bookmaker price (low-tier or not listed on the usual sites) — they use only the extra documented sources on the <a href="method.html">method page</a> and are also listed on <a href="flagged.html">Flagged for review</a>. Treat them as low-confidence.</div>
<h2>Where to find updated picks (all pages on this site)</h2>
<div class="linkcards">
<div class="linkcard"><a href="index.html">⭐ This page — picks at a glance</a><p class="small">Every open match, pick + %, mobile cards. Updated automatically. Start here.</p></div>
<div class="linkcard"><a href="picks.html">All picks — full table</a><p class="small">Same matches with market prices, VRS inputs, fair odds and a source link on every row.</p></div>
<div class="linkcard"><a href="../ourline/index.html">Our line board</a><p class="small">Bookmaker+VRS board for priced/modelled matches, with a graded track record. No fallback picks.</p></div>
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
        rows.append(f'<tr id="m-{esc(r["fixture_id"])}"><td data-l="When"><span data-t="{esc(r["start_utc"])}">{esc(r["start_utc"])}</span><div class="small">{esc(r.get("competition"))} · Tier {esc(r.get("tier") or "?")} · #{esc(r["fixture_id"])}</div></td><td data-l="Win probability">{teams}<div class="small">{esc(quotes)}</div></td><td data-l="Pick">{pick}<div class="small">fair odds (pick) {esc(odds)}</div></td><td data-l="Inputs"><div class="small">{"<br>".join(esc(i) for i in inputs) if inputs else "—"}</div>{flags}</td><td data-l="Sources"><div class="small">{src}</div></td></tr>')
    body = f'<h1>All picks — full table</h1><p class="mut">Every CS2 fixture currently open in the HotSpawn lobby, with the inputs behind each probability and a source link on every row. A/B = featured resolution (bookmaker market / VRS model). C = fallback sources only (flagged, low confidence). D = no evidence, left blank.</p><div style="overflow-x:auto"><table class="cards"><thead><tr><th>When</th><th>Win probability</th><th>Pick</th><th>Inputs</th><th>Sources</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    return page("All picks (full table)", "picks.html", body, b)

def render_flagged(b):
    items = []
    for r in b["open"]:
        if r["line"] and r["line"]["tier"] not in ("C",): continue
        if not r["flags"] and r["line"]: continue
        ev_html = ""
        if r.get("fallback") and r["fallback"].get("evidence"):
            lis = "".join(f'<li><b>{esc(e.get("kind"))}</b> — {esc(e.get("note"))} <a href="{esc(e.get("public_url") or "#")}" rel="noopener">{esc(e.get("source"))}</a> <span class="small">names at source: {esc("/".join(e.get("names_at_source") or []))} event {esc(e.get("event_id"))}</span></li>' for e in r["fallback"]["evidence"])
            ev_html = f"<ul>{lis}</ul>"
        src_links = " &middot; ".join('<a href="' + esc(s["url"]) + '">' + esc(s["label"]) + "</a>" for s in r["sources"])
        pick_txt = (r["line"]["pick_team"] + " " + pct(r["line"]["pick_prob"])) if r["line"] else "none - blank"
        basis_txt = BASIS_TXT[r["line"]["tier"]] if r["line"] else "D - No evidence"
        items.append(f'<div class="pickcard" id="f-{esc(r["fixture_id"])}"><b>{esc(r["team_a"])} vs {esc(r["team_b"])}</b> <span class="small">{esc(r.get("competition"))} &middot; <span data-t="{esc(r["start_utc"])}">{esc(r["start_utc"])}</span> &middot; #{esc(r["fixture_id"])}</span><div>Pick: <b>{esc(pick_txt)}</b> &middot; basis {esc(basis_txt)}</div><div class="small">Flags: {esc(", ".join(r["flags"]) or "none")}</div>{ev_html}<div class="small">Sources: {src_links}</div></div>')
    body = f'<h1>Flagged for review</h1><p class="mut">Every fallback (C) pick, identity mismatch, thin book and unverified item behind the every-match board. These do not block publication; review them here and request changes. Featured (A/B) picks are not listed unless flagged.</p>{"".join(items) if items else "<p>No flagged items on this run.</p>"}<h2>Known identity irregularities (verified 2026-10-14)</h2><div class="warnbox"><b>Elisa BreakOut Series #2 Group A slot:</b> HotSpawn lists <b>WROTBERRY</b>; Melbet prices the same slots (same competition, UTC start and opponent) as <b>WhiteBIT Team</b>; Kalshi books them as <b>WBT Academy</b>; Liquipedia/HLTV list the event participant as <b>WBT (WhiteBIT Team)</b>. Rosters differ between WBT (Valve VRS #60, 1201 pts) and WBT Academy (#130, 911 pts), so <b>no VRS rating is used</b> for this slot — only the slot prices, flagged. Sources: <a href="{LIQUIPEDIA_ELISA}">Liquipedia Elisa BreakOut #2</a>, <a href="{HLTV_WBT_ACAD}">HLTV WBT Academy</a>, <a href="{HLTV_EAC}">HLTV EAC</a>.</div><div class="warnbox"><b>FORZE Reload vs LFO 10:</b> LFO 10 has no row in Valve\'s official VRS file (sibling rosters LFO 7/8/9 do: 595/602/574 pts). The fallback range uses those siblings only, and is labelled originated/unverified. A same-start Kalshi book names the opponent “Sokerorg” — identity unverified, so it is corroboration only, never joined.</div><div class="warnbox"><b>RoundsGG:</b> priced/modelled as Valve VRS “ROUNDS” (#310, 548 pts) via the documented alias; HLTV team 12457 is “Rounds” (roundsgg). Fallback flag remains on both RoundsGG picks. Source: <a href="{HLTV_ROUNDS}">HLTV Rounds</a>.</div>'
    return page("Flagged for review", "flagged.html", body, b)

def render_method(b):
    cal = b["calibration"]
    body = f"""
<h1>Method &amp; sources</h1>
<h2>Fixture inventory (what “every match” means)</h2>
<p>Fixtures come from the public HotSpawn Pick'ems lobby (<a href="{LOBBY}">play.hotspawn.com/lobby</a>): the Angular transfer-state embedded in the page (its <code>/api/v1/fixtures</code> response) merged with the same public fixtures API the lobby calls, CS2 only, <code>scheduled</code> with lock time in the future at collection time. HotSpawn is used for discovery only. Its crowd “picked %” is never copied into the snapshot and never used as a probability. The collector re-runs automatically on GitHub Actions (about every 30 min); a failed HotSpawn fetch keeps the previous inventory and flags it, never an empty board.</p>
<h2>Featured resolution (tiers A/B) — tried first for every match</h2>
<ul>
<li><b>Bookmaker/exchange prices:</b> Pinnacle guest API (licensed bookmaker), Bovada coupon JSON (licensed bookmaker), Melbet LineFeed (licensed bookmaker), Kalshi KXCS2GAME (CFTC-regulated exchange; only books with bid/ask spread ≤ 10c on both sides). A price joins a fixture only when both team names match after the published normalisation/aliases <i>and</i> the source start time is within the tolerance window. No substring matches.</li>
<li><b>No-vig:</b> <code>p_i = (1/odds_i) / Σ(1/odds_j)</code> per source; consensus = weighted mean (Pinnacle ×2, others ×1).</li>
<li><b>Valve VRS model:</b> official points from <a href="{esc(b["vrs"].get("page_url"))}">ValveSoftware/counter-strike_regional_standings {esc(b["vrs"].get("snapshot"))}</a>, Valve's own Glicko expected-win formula with its slope re-fitted to observed market prices (k = {cal["k"]:.3f}, fitted on {cal.get("pairs_used")} priced fixtures this snapshot; k=1 would be uncalibrated Valve). Market+model blend: 85% market / 15% model (≥2 sources) or 75/25 (1 source), in logit space — a stated modelling choice, not a source value.</li>
<li><b>HLTV:</b> probed every run; it returns 403 to automation, so no HLTV number is ever used as a price. HLTV team pages are linked only as identity evidence for fallback aliases (Rounds, EAC, WBT Academy).</li>
<li><b>Polymarket:</b> probed every run; no open CS2 match markets have been observed, so nothing is taken from it. Low-tier matches are therefore resolved by B/C below, not by waiting for Polymarket.</li>
</ul>
<h2>Fallback resolution (tier C) — only where A/B is impossible</h2>
<ul>
<li><b>Slot prices (Elisa BreakOut):</b> where Melbet/Kalshi price the same competition + UTC start + opponent under a different team label (WhiteBIT Team / WBT Academy for HotSpawn's WROTBERRY; EA Copenhagen = EAC per Liquipedia/HLTV), the slot price's no-vig probability is used as indicative guidance. Identity is flagged; no VRS rating is used for the ambiguous slot.</li>
<li><b>Kalshi thin books:</b> books rejected from featured prices for spread &gt; 10c are used, fallback-only, as normalised bid/ask mids. Raw bid/ask is stored in the snapshot evidence.</li>
<li><b>RoundsGG alias:</b> RoundsGG → Valve VRS ROUNDS (548 pts) only in fallback, blended with the thin book where one exists.</li>
<li><b>Sibling/floor VRS (originated):</b> where one roster has no VRS row (LFO 10), the official points of sibling rosters in the same VRS file (LFO 7/8/9) give a probability range; the midpoint is published, labelled originated and unverified. If no siblings exist, the file's lowest points are used as a provisional floor.</li>
</ul>
<p>Every C pick is confidence-capped (“Low”), ranged, flagged, and listed on <a href="flagged.html">Flagged for review</a> with its evidence links. If no evidence of any kind exists (tier D), the probability is left blank — never invented.</p>
<h2>Verification</h2>
<p>Unit tests (<code>tests/test_c64a5e19.py</code>) re-derive every probability from the stored odds/ratings, check that every open fixture has exactly one tier, that fallback is used only when no accepted market exists, that slot joins require competition+start+opponent, and that every rendered row carries a source link. The workflow runs them before publishing.</p>
<h2>Limitations</h2>
<p>Probabilities are estimates, not verified win probabilities or betting advice. Bookmaker prices move; the board shows the collection time on every page. Elisa group matches are Bo1 per Liquipedia, so single-map variance is higher. Fallback picks are materially weaker than A/B picks — that is why they are labelled and ranged.</p>
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
