#!/usr/bin/env python3
"""Session f28afd9e: one mobile page with a pick for every CS2 match listed on the HotSpawn lobby.

Inventory (which matches)  data/live/board.json rows with listed_in_lobby = true whose pick lock
                           is still in the future (the lobby page's own published listing).
Probability (who wins)     first usable line, in this order, from boards the repository's own
                           collectors refresh automatically:
                             1. fe803b80 line whose basis includes bookmaker/exchange prices
                             2. c64a5e19 strict market line
                             3. b1fb1465 market / exchange line
                             4. fe803b80 originated line (Valve VRS + match-history Elo)
                             5. 7177d07f originated line (HLTV-checked identity + Valve VRS)
                           A board older than MAX_BOARD_AGE_H is skipped. No line -> unresolved.
Ownership (who else)       HotSpawn crowd split from the same live board, used ONLY to decide the
                           leaderboard pick (scripts/f28afd9e/strategy.py). Never a probability.

Outputs: data/f28afd9e/board.json, data/f28afd9e/history.json, strategy/*.html
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import strategy  # noqa: E402

DATA = ROOT / "data" / "f28afd9e"
SITE = ROOT / "strategy"
LOBBY = "https://play.hotspawn.com/lobby"
VALVE = ("https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/"
         "live/2026/standings_global_2026_10_05.md")
MAX_BOARD_AGE_H = 8.0
REFRESH_CRON = "37 */4 * * *"


# ----------------------------------------------------------------------------- helpers
def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def parse(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def load(rel):
    try:
        return json.loads((ROOT / rel).read_text(encoding="utf-8"))
    except Exception:
        return None


def esc(v):
    return html.escape("" if v is None else str(v), quote=True)


def pct(p):
    return "—" if p is None else f"{p * 100:.0f}%"


def norm(name):
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def board_age_h(board, now, key_candidates=("generated_utc", "generated_at_utc")):
    for k in key_candidates:
        t = parse((board or {}).get(k))
        if t:
            return (now - t).total_seconds() / 3600.0, iso(t)
    return None, None


# ----------------------------------------------------------------------------- probability ladder
def oriented(prob_a, src_a, team_a):
    """Return prob for our team_a given a source row whose team_a may be swapped."""
    if prob_a is None:
        return None
    return prob_a if norm(src_a) == norm(team_a) else 1.0 - prob_a


def candidate_lines(fid, team_a, boards, now):
    out = []
    fe, cm, b1, s7 = boards.get("fe803b80"), boards.get("c64a5e19"), boards.get("b1fb1465"), boards.get("7177d07f")

    def fresh(b):
        age, stamp = board_age_h(b, now)
        return (age is not None and age <= MAX_BOARD_AGE_H), stamp

    if fe:
        ok, stamp = fresh(fe)
        row = next((r for r in fe.get("open", []) if str(r["fixture_id"]) == fid), None)
        if ok and row and (row.get("line") or {}).get("prob_a") is not None:
            basis = row["line"].get("basis") or ""
            out.append({"rank": 1 if "market" in basis else 4, "board": "fe803b80", "board_url": "board/picks.html",
                        "board_stamp": stamp, "basis": "market" if "market" in basis else "model",
                        "basis_detail": basis, "prob_a": oriented(row["line"]["prob_a"], row["team_a"], team_a),
                        "market_prob_a": oriented((row.get("market") or {}).get("prob_a"), row["team_a"], team_a),
                        "market_books": (row.get("market") or {}).get("sources") or [],
                        "sources": [s for s in row.get("sources") or [] if s.get("url")],
                        "points": row.get("points"), "hotspawn_url": row.get("hotspawn_url"),
                        "flags": row.get("flags") or []})
    if cm:
        ok, stamp = fresh(cm)
        row = next((r for r in cm.get("open", []) if str(r["fixture_id"]) == fid), None)
        line = (row or {}).get("line") or {}
        if ok and row and line.get("prob_a") is not None and "market" in str(line.get("basis") or ""):
            out.append({"rank": 2, "board": "c64a5e19", "board_url": "picks-every-match/index.html",
                        "board_stamp": stamp, "basis": "market", "basis_detail": line.get("basis"),
                        "prob_a": oriented(line["prob_a"], row["team_a"], team_a),
                        "sources": [s for s in row.get("sources") or [] if isinstance(s, dict) and s.get("url")],
                        "points": row.get("points"), "hotspawn_url": row.get("hotspawn_url"),
                        "flags": row.get("flags") or []})
    if b1:
        ok, stamp = fresh(b1)
        row = next((r for r in b1.get("open", []) if str(r["fixture_id"]) == fid), None)
        if ok and row and row.get("prob_a") is not None and row.get("basis") in ("market", "exchange"):
            out.append({"rank": 3, "board": "b1fb1465", "board_url": "exec/index.html", "board_stamp": stamp,
                        "basis": row["basis"], "basis_detail": row["basis"],
                        "prob_a": oriented(row["prob_a"], row["team_a"], team_a),
                        "sources": [s for s in row.get("sources") or [] if s.get("url")],
                        "hotspawn_url": row.get("hotspawn_url"), "flags": row.get("flags") or []})
    if s7:
        ok, stamp = fresh(s7)
        row = next((r for r in s7.get("rows", []) if str(r["fixture_id"]) == fid), None)
        if ok and row and row.get("prob_a") is not None:
            srcs = []
            for e in row.get("evidence") or []:
                if isinstance(e, dict) and e.get("url"):
                    srcs.append({"label": e.get("label") or e.get("kind") or "evidence", "url": e["url"],
                                 "read_utc": e.get("read_utc")})
            out.append({"rank": 5, "board": "7177d07f", "board_url": "unresolved/index.html", "board_stamp": stamp,
                        "basis": "market" if row.get("basis") in ("featured", "esportsbook") else "model",
                        "basis_detail": row.get("basis"), "prob_a": oriented(row["prob_a"], row["team_a"], team_a),
                        "sources": srcs, "hotspawn_url": row.get("hotspawn_url"), "flags": row.get("flags") or []})
    out.sort(key=lambda c: c["rank"])
    return out


# ----------------------------------------------------------------------------- inventory
def lobby_inventory(live, fe, now):
    """Open lobby-listed fixtures. Primary: the live board's lobby listing. Fallback: fe803b80."""
    rows, source = [], None
    age, stamp = board_age_h(live, now)
    if live and age is not None and age <= MAX_BOARD_AGE_H:
        source = {"board": "live (3cd9787c)", "stamp": stamp, "url": LOBBY}
        for r in live.get("rows", []):
            if not r.get("listed_in_lobby") or str(r.get("status")) in ("cancelled", "ended", "finished"):
                continue
            lock = parse(r.get("lock_time_utc"))
            if not lock or lock <= now - timedelta(hours=14):
                continue
            c = r.get("hotspawn_pick_pct_reference_only") or {}
            rows.append({"fixture_id": str(r["fixture_id"]), "competition": r.get("competition"),
                         "tier": (r.get("tier") or "").upper(), "start_utc": r.get("start_time_utc"),
                         "lock_utc": r.get("lock_time_utc"), "status": r.get("status"),
                         "team_a": r["team_a"], "team_b": r["team_b"],
                         "hotspawn_url": r.get("hotspawn_match_url") or LOBBY,
                         "crowd": {"pct_a": c.get("team_a"), "pct_b": c.get("team_b"), "captured_utc": stamp}
                         if c.get("team_a") is not None else None})
    elif fe:
        age2, stamp2 = board_age_h(fe, now)
        source = {"board": "fe803b80 (fallback)", "stamp": stamp2, "url": LOBBY}
        for r in fe.get("open", []):
            rows.append({"fixture_id": str(r["fixture_id"]), "competition": r.get("competition"),
                         "tier": (r.get("tier") or "").upper(), "start_utc": r.get("start_utc"),
                         "lock_utc": r.get("lock_utc"), "status": r.get("status"),
                         "team_a": r["team_a"], "team_b": r["team_b"],
                         "hotspawn_url": r.get("hotspawn_url") or LOBBY, "crowd": None})
    rows.sort(key=lambda r: (r["start_utc"] or "", r["fixture_id"]))
    return rows, source


# ----------------------------------------------------------------------------- build
def build(now=None):
    now = now or now_utc()
    boards = {k: load(f"data/{k}/board.json") for k in ("fe803b80", "c64a5e19", "b1fb1465", "7177d07f")}
    live = load("data/live/board.json")
    context = (load("data/f28afd9e/context.json") or {}).get("teams", {})
    fixtures, inv_source = lobby_inventory(live, boards["fe803b80"], now)
    closed = {str(r["fixture_id"]): r for r in (boards.get("fe803b80") or {}).get("closed", [])}

    rows = []
    for fx in fixtures:
        cands = candidate_lines(fx["fixture_id"], fx["team_a"], boards, now)
        primary = cands[0] if cands else None
        prob_a = primary["prob_a"] if primary else None
        points = next((c.get("points") for c in cands if c.get("points")), None) \
            or (closed.get(fx["fixture_id"]) or {}).get("points")
        own = strategy.ownership((fx.get("crowd") or {}).get("pct_a"), (fx.get("crowd") or {}).get("pct_b"))
        s = strategy.evaluate(fx["team_a"], fx["team_b"], prob_a, own, points, context, fx["start_utc"])
        hs = next((c["hotspawn_url"] for c in cands if c.get("hotspawn_url") and "hotspawn.com/matches" in c["hotspawn_url"]),
                  fx["hotspawn_url"])
        lock = parse(fx["lock_utc"])
        state = "open" if lock and lock > now else "locked"
        settled = closed.get(fx["fixture_id"]) or {}
        winner = None
        if settled.get("winner") in ("a", "b") and str(settled.get("status")) == "ended":
            winner = settled["team_a"] if settled["winner"] == "a" else settled["team_b"]
            winner = fx["team_a"] if norm(winner) == norm(fx["team_a"]) else fx["team_b"]
        flags = []
        if primary is None:
            flags.append("no_line_from_any_board")
        elif primary["basis"] == "model":
            flags.append("no_bookmaker_price_model_only")
        if own is None:
            flags.append("no_crowd_ownership")
        if primary and "single_market_source" in (primary.get("flags") or []):
            flags.append("single_market_source")
        if primary and primary["board"] != "fe803b80" and primary["basis"] != "model":
            flags.append(f"priced_by_fallback_board_{primary['board']}")
        if any("WROTBERRY" in (fx["team_a"], fx["team_b"]) for _ in [0]):
            flags.append("identity_contested_WROTBERRY_WBT_vs_WBT_Academy")
        disagree = [c for c in cands[1:] if c.get("prob_a") is not None and prob_a is not None
                    and (c["prob_a"] >= 0.5) != (prob_a >= 0.5)]
        if disagree:
            flags.append("boards_disagree_on_winner")
        rows.append({**fx, "hotspawn_url": hs, "points": points, "state": state, "winner": winner,
                     "prob_a": prob_a, "prob_b": None if prob_a is None else 1 - prob_a,
                     "basis": primary["basis"] if primary else "unresolved",
                     "line": primary, "cross_check": [{k: c.get(k) for k in ("board", "basis", "prob_a", "board_stamp")}
                                                     for c in cands],
                     "strategy": s, "flags": flags})
    strategy.apply_daily_cap(rows)

    open_rows = [r for r in rows if r["state"] == "open"]
    summary = {
        "listed_open": len(open_rows),
        "with_pick": sum(1 for r in open_rows if r["strategy"]["safe_pick"]),
        "market_priced": sum(1 for r in open_rows if r["basis"] == "market"),
        "exchange_priced": sum(1 for r in open_rows if r["basis"] == "exchange"),
        "model_only": sum(1 for r in open_rows if r["basis"] == "model"),
        "unresolved": sum(1 for r in open_rows if r["basis"] == "unresolved"),
        "contrarian": sum(1 for r in open_rows if r["strategy"]["leaderboard_pick"] != r["strategy"]["safe_pick"]),
        "locked_today": sum(1 for r in rows if r["state"] == "locked"),
    }
    excluded = []
    fe = boards.get("fe803b80") or {}
    listed_ids = {r["fixture_id"] for r in rows}
    for r in fe.get("open", []):
        if str(r["fixture_id"]) not in listed_ids:
            excluded.append({"fixture_id": str(r["fixture_id"]), "match": f"{r['team_a']} vs {r['team_b']}",
                             "start_utc": r.get("start_utc"), "competition": r.get("competition"),
                             "reason": "present in the HotSpawn fixture API but not in the lobby's rendered listing "
                                       "at this read; not a pick'em card, so no pick is published"})
    board = {"session": "f28afd9e", "generated_utc": iso(now), "inventory_source": inv_source,
             "boards_used": {k: board_age_h(v, now)[1] for k, v in boards.items() if v},
             "summary": summary, "rows": rows, "excluded_api_only": excluded,
             "policy": {"max_board_age_h": MAX_BOARD_AGE_H, "rules": strategy.__doc__.strip()}}
    return board


def update_history(board):
    path = DATA / "history.json"
    hist = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"rows": {}}
    for r in board["rows"]:
        s = r["strategy"]
        rec = hist["rows"].get(r["fixture_id"])
        if r["state"] == "open" and s["safe_pick"]:
            hist["rows"][r["fixture_id"]] = {
                "fixture_id": r["fixture_id"], "match": f"{r['team_a']} vs {r['team_b']}",
                "start_utc": r["start_utc"], "points": r["points"], "safe_pick": s["safe_pick"],
                "safe_prob": round(s["safe_prob"], 4), "leaderboard_pick": s["leaderboard_pick"],
                "rule": s["rule"], "published_utc": board["generated_utc"], "winner": None}
        elif rec and r.get("winner"):
            rec["winner"] = r["winner"]
    hist["updated_utc"] = board["generated_utc"]
    path.write_text(json.dumps(hist, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return hist


# ----------------------------------------------------------------------------- rendering
CSS = """
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--text:#e6edf3;--mut:#9aa7b4;--ok:#3fb950;--warn:#d29922;--bad:#f85149;--acc:#58a6ff}
*{box-sizing:border-box}body{margin:0;font:16px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--text)}
a{color:var(--acc)}main{max-width:860px;margin:0 auto;padding:12px}
nav{display:flex;flex-wrap:wrap;gap:8px;padding:10px 12px;background:#010409;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:2}
nav a{min-height:44px;display:inline-flex;align-items:center;padding:0 12px;border:1px solid var(--line);border-radius:8px;text-decoration:none;color:var(--text);font-size:15px}
nav a.on{background:#1f6feb;border-color:#1f6feb}
h1{font-size:1.5rem;margin:14px 0 6px}h2{font-size:1.15rem;margin:22px 0 8px}
.mut{color:var(--mut);font-size:.9rem}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin:12px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}.tile b{display:block;font-size:1.5rem}
.btns{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.btn{min-height:48px;display:inline-flex;align-items:center;padding:0 16px;border-radius:10px;background:#1f6feb;color:#fff;text-decoration:none;font-weight:600}
.btn.alt{background:var(--card);border:1px solid var(--line);color:var(--text)}
.m{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:10px 0}
.m.contra{border-left:5px solid var(--warn)}.m.locked{opacity:.75}
.top{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;font-size:.85rem;color:var(--mut)}
.teams{display:grid;grid-template-columns:1fr auto;gap:4px 10px;margin:8px 0;font-size:1.05rem}
.teams .p{font-weight:700;text-align:right}.fav{color:var(--ok)}
.bar{height:8px;border-radius:4px;background:#30363d;overflow:hidden;margin:4px 0 8px}.bar i{display:block;height:100%;background:var(--ok)}
.picks{display:grid;grid-template-columns:1fr 1fr;gap:8px}.pk{background:#0d1117;border:1px solid var(--line);border-radius:8px;padding:8px}
.pk small{display:block;color:var(--mut);font-size:.78rem}.pk b{font-size:1.05rem}.pk.lb b{color:var(--warn)}
.why{font-size:.88rem;color:var(--mut);margin:8px 0 0}details{margin-top:8px}summary{cursor:pointer;min-height:36px;color:var(--acc)}
.src{font-size:.85rem;word-break:break-word}.src li{margin:3px 0}
.tag{display:inline-block;font-size:.75rem;padding:2px 7px;border-radius:999px;border:1px solid var(--line);margin:2px 4px 0 0;color:var(--mut)}
.tag.w{border-color:var(--warn);color:var(--warn)}.tag.b{border-color:var(--bad);color:var(--bad)}.tag.g{border-color:var(--ok);color:var(--ok)}
table{width:100%;border-collapse:collapse;font-size:.9rem}th,td{border-bottom:1px solid var(--line);padding:7px 5px;text-align:left;vertical-align:top}
.tw{overflow-x:auto}footer{color:var(--mut);font-size:.8rem;margin:30px 0 20px}
@media(max-width:480px){.picks{grid-template-columns:1fr}h1{font-size:1.3rem}}
"""

PAGES = [("index.html", "Picks"), ("unresolved.html", "Unresolved & limits"), ("day1.html", "Day 1 review"),
         ("method.html", "How it works")]


def page(name, title, body, generated):
    nav = "".join(f'<a href="{f}"{" class=on" if f == name else ""}>{esc(l)}</a>' for f, l in PAGES)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)} · CS2 pick\'em strategy</title><style>{CSS}</style></head><body>'
            f'<nav><a href="../index.html">← Home</a>{nav}</nav><main>{body}'
            f'<footer>Built {esc(generated)} UTC by scripts/f28afd9e/build.py · refreshed automatically every 4 hours '
            f'and after each data refresh · HotSpawn crowd % is shown as <em>ownership</em> only and never used as a '
            f'probability · Not affiliated with HotSpawn · 18+, estimates are not guarantees.</footer></main></body></html>')


RULE_TEXT = {
    "chalk": "Market favourite. The underdog is not live enough (or not under-owned enough) to be worth fading.",
    "chalk_contrarian": "The betting-market favourite is ALSO the side most players are fading — free leverage: take it.",
    "chalk_capped": "A swing qualified, but today's limit of 3 swings is reached — keep the safe pick.",
    "R1_coinflip_fade": "Near coin flip by the market, but most players are on the other side: take the less-owned team. Costs almost nothing in expected points.",
    "R2_upset_swing": "Live underdog (≥35% by the market) that ≤20% of players picked: if it lands you jump most of the field.",
    "R3_context_swing": "Market gives the underdog ≥25%, ≤10% of players picked it, and verified context (roster change, stand-in, rest or head-to-head) backs the upset.",
    "no_probability": "No usable line from any source — see Unresolved.",
}


def src_list(row):
    items = [f'<li><a href="{esc(row["hotspawn_url"])}">HotSpawn match / lobby</a> (listing only)</li>']
    line = row.get("line") or {}
    seen = set()
    for s in line.get("sources") or []:
        if s["url"] in seen or "hotspawn" in s["url"]:
            continue
        seen.add(s["url"])
        items.append(f'<li><a href="{esc(s["url"])}">{esc(s.get("label") or s["url"])}</a>'
                     f'{" · read " + esc(s.get("read_utc")) if s.get("read_utc") else ""}</li>')
    for c in (row["strategy"].get("context") or []):
        for u in c.get("sources") or []:
            if u not in seen:
                seen.add(u)
                items.append(f'<li><a href="{esc(u)}">Context: {esc(c["team"])} — {esc(c["type"])}</a></li>')
    return "<ul class=src>" + "".join(items) + "</ul>"


def card(r):
    s = r["strategy"]
    pa, pb = r["prob_a"], r["prob_b"]
    contra = s["leaderboard_pick"] and s["leaderboard_pick"] != s["safe_pick"]
    cls = "m" + (" contra" if contra else "") + (" locked" if r["state"] == "locked" else "")
    crowd = r.get("crowd") or {}
    ca = f' · crowd {crowd.get("pct_a")}%' if crowd.get("pct_a") is not None else ""
    cb = f' · crowd {crowd.get("pct_b")}%' if crowd.get("pct_b") is not None else ""
    fav_a = pa is not None and pa >= 0.5
    tags = []
    basis_tag = {"market": ("g", "bookmaker line"), "exchange": ("w", "exchange only"), "model": ("w", "model only"),
                 "unresolved": ("b", "unresolved")}[r["basis"]]
    tags.append(f'<span class="tag {basis_tag[0]}">{basis_tag[1]}</span>')
    for f in r["flags"]:
        if f.startswith("identity_contested"):
            tags.append('<span class="tag w">team identity contested</span>')
        elif f == "boards_disagree_on_winner":
            tags.append('<span class="tag w">boards disagree</span>')
    if r["state"] == "locked":
        tags.append('<span class="tag">locked</span>')
    if r.get("winner"):
        ok = r["winner"] == s["leaderboard_pick"]
        tags.append(f'<span class="tag {"g" if ok else "b"}">winner: {esc(r["winner"])}</span>')
    lev = s.get("leverage")
    why = RULE_TEXT.get(s["rule"], "")
    if lev and s.get("own_dog") is not None:
        why += f" Underdog leverage {lev:.1f}× (win chance ÷ share of players)."
    return f"""<article class="{cls}" id="m-{esc(r['fixture_id'])}">
<div class="top"><span>{esc(r['competition'])} · tier {esc(r['tier'])} · {esc(r['points'] or '?')} pts</span><span>{esc((r['start_utc'] or '').replace('T', ' ')[:16])} UTC · locks {esc((r['lock_utc'] or '')[11:16])}</span></div>
<div class="teams"><span class="{ 'fav' if fav_a else ''}">{esc(r['team_a'])}<span class=mut>{esc(ca)}</span></span><span class="p">{pct(pa)}</span>
<span class="{ 'fav' if (pa is not None and not fav_a) else ''}">{esc(r['team_b'])}<span class=mut>{esc(cb)}</span></span><span class="p">{pct(pb)}</span></div>
<div class="bar"><i style="width:{0 if pa is None else round(pa * 100)}%"></i></div>
<div class="picks"><div class="pk"><small>Safe pick (most likely)</small><b>{esc(s['safe_pick'] or '—')}</b> {pct(s['safe_prob'])}</div>
<div class="pk lb"><small>Leaderboard pick</small><b>{esc(s['leaderboard_pick'] or '—')}</b> {pct(s['leaderboard_prob'])}</div></div>
<p class="why">{esc(why)}</p><div>{''.join(tags)}</div>
<details><summary>Sources &amp; cross-check</summary>{src_list(r)}
<p class=mut>Line from board <a href="../{esc((r.get('line') or {}).get('board_url', 'board/picks.html'))}">{esc((r.get('line') or {}).get('board', '—'))}</a> ({esc((r.get('line') or {}).get('basis_detail'))}, built {esc((r.get('line') or {}).get('board_stamp'))}). Other boards: {esc(', '.join(f"{c['board']} {pct(c['prob_a'])}" for c in r['cross_check'][1:]) or 'none')}.</p></details>
</article>"""


def render(board, day1, hist):
    SITE.mkdir(exist_ok=True)
    g = board["generated_utc"]
    sm = board["summary"]
    open_rows = [r for r in board["rows"] if r["state"] == "open"]
    locked = [r for r in board["rows"] if r["state"] == "locked"]
    contra = [r for r in open_rows if r["strategy"]["leaderboard_pick"] != r["strategy"]["safe_pick"]]
    unresolved = [r for r in open_rows if r["basis"] in ("unresolved", "model", "exchange")
                  or any(f.startswith(("identity", "priced_by_fallback")) or f in ("boards_disagree_on_winner", "single_market_source")
                         for f in r["flags"])]
    d1 = day1.get("summary", {}) if day1 else {}
    exec_html = f"""<h1>CS2 pick'em: every match, one page</h1>
<p class=mut>Every CS2 match on the <a href="{LOBBY}">HotSpawn lobby</a> that is still open for picks. Two picks each:
<b>Safe</b> (most likely winner from betting lines) and <b>Leaderboard</b> (the contrarian-but-not-stupid card for climbing). Updated {esc(g.replace('T', ' ')[:16])} UTC.</p>
<div class="tiles"><div class="tile"><b>{sm['listed_open']}</b>open matches</div><div class="tile"><b>{sm['with_pick']}</b>with a pick</div>
<div class="tile"><b>{sm['market_priced'] + sm['exchange_priced']}</b>priced by books/exchange</div><div class="tile"><b>{sm['model_only']}</b>model only</div>
<div class="tile"><b>{sm['unresolved']}</b>no pick</div><div class="tile"><b>{sm['contrarian']}</b>contrarian picks</div></div>
<div class="btns"><a class="btn" href="#picks">See all picks ↓</a><a class="btn alt" href="unresolved.html">Unresolved &amp; limitations</a><a class="btn alt" href="day1.html">Day 1 review</a></div>
<h2>Executive summary</h2><ul>
<li><b>Day 1 lesson:</b> 9z beat Aurora 2-0 although {_d1own(day1, '1080176', '9z')} of players picked 9z while the betting market gave them about 30%. Aurora rebuilt in July (new IGL kyxsan, Jimpphat, coach ash; first international lineup). The crowd piles 90%+ onto favourites the market rates only ~70%. <a href="day1.html">Full review</a>.</li>
<li><b>Backtest of the leaderboard rules on day 1:</b> {d1.get('leaderboard_correct', '?')}/{d1.get('settled', '?')} correct, {d1.get('leaderboard_points', '?'):g} points — same points as the safe card ({d1.get('safe_correct', '?')}/{d1.get('settled', '?')}, {d1.get('safe_points', '?'):g} pts), but its points came where most players scored zero (9z, HOTU). Small sample; treat as illustration, not proof.</li>
<li><b>Today's contrarian spots:</b> {', '.join(f'<a href="#m-{esc(r["fixture_id"])}">{esc(r["strategy"]["leaderboard_pick"])}</a> ({pct(r["strategy"]["leaderboard_prob"])})' for r in contra) or 'none qualify right now'}.</li>
<li><b>Strict list:</b> the canonical <a href="../picks-every-match/index.html">strict board</a> keeps unsupported numbers blank; this page gives a best-available pick for those too and labels the limitation. Root <a href="../day-one.html">day-one review</a>.</li>
<li><b>Unresolved / limited:</b> {sm['unresolved']} with no pick, {sm['model_only']} priced only by our rating model, plus contested identities — <a href="unresolved.html">see the separate section</a>.</li></ul>"""
    body = exec_html + '<h2 id="picks">All open matches</h2>' + ("".join(card(r) for r in open_rows) or "<p>No open matches in the current lobby read.</p>")
    if locked:
        body += "<h2>Locked in the last 14 hours</h2>" + "".join(card(r) for r in locked)
    if board.get("excluded_api_only"):
        body += "<h2>Not on the lobby (API-only rows)</h2><ul>" + "".join(
            f"<li>{esc(e['match'])} · {esc(e['competition'])} · {esc(e['start_utc'])} — {esc(e['reason'])}</li>" for e in board["excluded_api_only"]) + "</ul>"
    (SITE / "index.html").write_text(page("index.html", "Every CS2 pick", body, g), encoding="utf-8")

    # unresolved
    rows_html = []
    for r in unresolved:
        lim = []
        if r["basis"] == "unresolved":
            lim.append("No bookmaker, exchange or official-rating line was available from any board at this build.")
        if r["basis"] == "model":
            lim.append("No bookmaker or exchange quotes this match; the probability is our originated rating line (Valve VRS points and/or bo3.gg match-history Elo), lower confidence.")
        if r["basis"] == "exchange":
            lim.append("Only an exchange order book prices this match (no bookmaker); books can be thin.")
        if any(f.startswith("identity") for f in r["flags"]):
            lim.append("HotSpawn's 'WROTBERRY' is matched by HLTV/Pinnacle/bo3.gg to WBT (Valve #60), but Kalshi titles the same slots 'WBT Academy' (Valve #130). Bookmaker prices follow the WBT reading.")
        if "boards_disagree_on_winner" in r["flags"]:
            lim.append("Independent boards in this repository disagree on the winner: " + ", ".join(f"{c['board']} {pct(c['prob_a'])} {esc(r['team_a'])}" for c in r["cross_check"]) + ".")
        if "single_market_source" in r["flags"] or any(f.startswith("priced_by_fallback") for f in r["flags"]):
            lim.append(f"Not priced on the main all-picks board's book set; the line comes from the {(r.get('line') or {}).get('board')} board"
                       f" built {(r.get('line') or {}).get('board_stamp')} and rests on a single bookmaker/exchange quote.")
        if "no_crowd_ownership" in r["flags"]:
            lim.append("No HotSpawn crowd split captured, so the leaderboard pick defaults to the safe pick.")
        rows_html.append(f"<tr><td><a href='index.html#m-{esc(r['fixture_id'])}'>{esc(r['team_a'])} vs {esc(r['team_b'])}</a><br><span class=mut>{esc(r['start_utc'])}</span></td>"
                         f"<td>{esc(r['strategy']['safe_pick'] or '—')} {pct(r['strategy']['safe_prob'])}</td><td>{esc(r['basis'])}</td>"
                         f"<td>{'<br>'.join(esc(x) for x in lim)}</td><td><a href='{esc(r['hotspawn_url'])}'>HotSpawn</a>"
                         + "".join(f"<br><a href='{esc(s['url'])}'>{esc((s.get('label') or 'source')[:40])}</a>" for s in ((r.get('line') or {}).get('sources') or [])[1:4])
                         + "</td></tr>")
    ub = f"""<h1>Unresolved picks &amp; limitations</h1>
<p class=mut>Matches where a pick could not be resolved the same way as the featured (bookmaker-priced) picks. Each still shows the best available pick when one exists; where no defensible line exists the pick stays blank. Nothing is invented.</p>
<div class="tiles"><div class="tile"><b>{sm['unresolved']}</b>no pick at all</div><div class="tile"><b>{sm['model_only']}</b>model only</div><div class="tile"><b>{sm['exchange_priced']}</b>exchange only</div><div class="tile"><b>{len(unresolved)}</b>listed here</div></div>
<div class=tw><table><tr><th>Match</th><th>Best pick</th><th>Basis</th><th>Limitation</th><th>Sources</th></tr>{''.join(rows_html) or '<tr><td colspan=5>None at this build.</td></tr>'}</table></div>
<h2>Research order used for these matches</h2><ol><li><b>HLTV</b> (team, match and analytics pages) for identity, rosters and ranking — HLTV's "Best odds" fields were empty for these low-tier matches when read, and HLTV blocks automated runners (403), so HLTV is identity/context only.</li>
<li><b>Esportsbooks and betting lines</b>: Pinnacle, Bovada, Melbet/1xBet LineFeed, Thunderpick coefficients via bo3.gg, Kalshi exchange — collected automatically by the repository's collectors.</li>
<li><b>Originated line</b>: official <a href="{VALVE}">Valve VRS</a> points and bo3.gg match-history Elo, only where no price exists.</li></ol>
<h2 id="flagged">Flagged for review (session f28afd9e)</h2><ul>
<li><b>Aurora "recent roster change":</b> the latest verified change is the July 2026 rebuild (kyxsan, Jimpphat, coach ash). <a href="https://www.hltv.org/team/11861/aurora">HLTV's team page</a> read 15 Oct shows the same five; no October change was found. Please confirm if you know of a newer one.</li>
<li><b>Timezones:</b> HLTV rendered TWC times in UTC-4 for our reader (9z vs Falcons "07:00") while HotSpawn shows 11:00 UTC for the same match. All times on this site are UTC.</li>
<li><b>Crowd % moves:</b> the crowd split is captured by the hourly collector; the lobby can differ by a point or two minutes later (9z 5% at 09:56Z vs 6% on a manual read ~09:36Z).</li>
<li><b>Wildcard vs DENDELE (1080200):</b> present in HotSpawn's fixture API dated 12 Nov but not on the lobby; session 94b3d48a reports HLTV shows it was played 11 Oct. Not re-verified here; no pick published.</li>
<li><b>Secondary source:</b> the ash onboarding interview is cited via cs2news.com, not the HLTV original.</li>
<li><b>Fallback-board rows:</b> some low-tier rows are priced only by the executive board's older single-source (Melbet) quote; they are listed in the table above.</li>
<li><b>Strict board vs this page:</b> the canonical strict list (<a href="../picks-every-match/index.html">picks-every-match</a>) withholds a number when roster identity or evidence freshness fails its rules (e.g. WROTBERRY and RoundsGG rows). This page shows the best available line from the repository's other automatically refreshed boards for those matches and lists every such row in the table above, so you always have a pick plus its limitation.</li>
<li><b>Pipeline repairs:</b> the red hourly data refresh and Pages public check were repaired in parallel by session 778756a1 (PR #112) and this session; the merge keeps 778756a1's stricter test versions. Details in COORDINATION.md.</li></ul>
<h2>General limitations</h2><ul><li>Polymarket lists no current CS2 match markets for these events; it is not used.</li>
<li>HotSpawn's lobby is read by GitHub-hosted runners every hour; between reads, new matches can appear. This page refreshes every 4 hours and after each data refresh.</li>
<li>HotSpawn crowd % is ownership, not probability.</li></ul>"""
    (SITE / "unresolved.html").write_text(page("unresolved.html", "Unresolved & limitations", ub, g), encoding="utf-8")

    # day 1
    drows = []
    for r in (day1 or {}).get("rows", []):
        s = r["strategy"]; c = r.get("crowd") or {}
        res = "pending" if not r.get("winner") else r["winner"]
        drows.append(f"<tr><td>{esc(r['team_a'])} vs {esc(r['team_b'])}<br><span class=mut>{esc(r['start_utc'][:16])} · {esc(r['points'])} pts</span></td>"
                     f"<td>{pct(r['prelock_prob_a'])} / {pct(1 - r['prelock_prob_a'])}</td><td>{esc(c.get('pct_a', '—'))}% / {esc(c.get('pct_b', '—'))}%</td>"
                     f"<td>{esc(s['safe_pick'])} {'✅' if r.get('safe_correct') else ('❌' if r.get('safe_correct') is False else '')}</td>"
                     f"<td>{esc(s['leaderboard_pick'])} {'✅' if r.get('leaderboard_correct') else ('❌' if r.get('leaderboard_correct') is False else '')}<br><span class=mut>{esc(s['rule'])}</span></td>"
                     f"<td>{esc(res)}</td><td><a href='{esc(r['hotspawn_url'])}'>HotSpawn</a></td></tr>")
    aur = (load("data/f28afd9e/context.json") or {}).get("teams", {}).get("Aurora", [])
    ctx_html = "".join(f"<li><b>{esc(e['date'])}</b> — {esc(e['summary'])} " + " ".join(f"<a href='{esc(u)}'>[source]</a>" for u in e.get('sources', []))
                       + (f" <span class='tag w'>secondary source</span>" if e.get('secondary') else "") + "</li>" for e in aur)
    db = f"""<h1>Day 1 review (14–15 Oct): the 9z upset</h1>
<p><b>9z 2-0 Aurora</b> (<a href="https://www.hltv.org/matches/2399384/9z-vs-aurora-thunderpick-world-championship-2026">HLTV match</a>, <a href="https://www.hltv.org/news/45718/9z-beat-aurora-2-0-to-kick-off-twc-2026">HLTV report</a>): Inferno 13-11, Nuke 13-1. Before the match the betting line gave 9z about {pct(next((r['prelock_prob_a'] for r in (day1 or {}).get('rows', []) if r['fixture_id'] == '1080176'), None))} while {_d1own(day1, '1080176', '9z')} of HotSpawn players picked them.</p>
<p class=mut>See also the root <a href="../day-one.html">day-one review</a> (session 778756a1), which covers all four TWC openers with specialist sources; this page adds the pre-lock crowd ownership and the leaderboard backtest.</p>
<h2>Aurora context (verified)</h2><ul>{ctx_html}</ul>
<p class=mut>The user brief mentions a recent Aurora roster change. The most recent change found on official/primary pages is the July 2026 rebuild; HLTV's team page read today shows the same five (XANTARES, woxic, Jimpphat, kyxsan, Wicadia; coach ash). No October change was found — flagged for review rather than assumed.</p>
<h2>What it teaches about climbing the leaderboard</h2><ul>
<li>The crowd routinely puts 88–96% on favourites the market prices at 70–75% (Aurora 96% crowd vs ~70% market; Fnatic 92% vs ~53%).</li>
<li>Those are the cheapest places to separate: an underdog the market rates as live, that almost nobody owns.</li>
<li>But not every underdog: the rules skip dogs below 25% and dogs the crowd already likes, and cap big swings at 3 a day.</li></ul>
<h2>Backtest: safe card vs leaderboard card</h2><div class=tiles><div class=tile><b>{d1.get('safe_correct')}/{d1.get('settled')}</b>safe correct</div><div class=tile><b>{d1.get('safe_points', 0):g}</b>safe points</div>
<div class=tile><b>{d1.get('leaderboard_correct')}/{d1.get('settled')}</b>leaderboard correct</div><div class=tile><b>{d1.get('leaderboard_points', 0):g}</b>leaderboard points</div></div>
<div class=tw><table><tr><th>Match</th><th>Line before lock</th><th>Crowd before lock</th><th>Safe</th><th>Leaderboard</th><th>Winner</th><th>Source</th></tr>{''.join(drows)}</table></div>
<p class=mut>Lines: last publication before kick-off on the <a href="../board/picks.html">all-picks board</a> (bookmaker/exchange prices). Crowd: last HotSpawn split captured before lock by the live collector (git commit stored per row in data/f28afd9e/day1_review.json). Winners: HotSpawn settlement; TWC results checked on <a href="https://www.hltv.org/results?event=8932">HLTV</a>. Thirteen settled matches is a small sample.</p>"""
    (SITE / "day1.html").write_text(page("day1.html", "Day 1 review", db, g), encoding="utf-8")

    hrows = sorted(hist.get("rows", {}).values(), key=lambda x: x["start_utc"] or "")
    settled = [h for h in hrows if h.get("winner")]
    mb = f"""<h1>How the picks work</h1>
<h2>1. Which matches</h2><p>Every CS2 match listed on the <a href="{LOBBY}">HotSpawn lobby</a> whose pick lock is in the future, as captured by the repository's hourly lobby collector (inventory from {esc((board.get('inventory_source') or {}).get('board'))}, read {esc((board.get('inventory_source') or {}).get('stamp'))}). API-only rows that are not lobby cards are listed separately, never picked.</p>
<h2>2. Win probability</h2><p>First usable line in this order (boards older than {MAX_BOARD_AGE_H:g} h are skipped): bookmaker/exchange consensus with the margin removed (Pinnacle, Bovada, Melbet, Thunderpick via bo3.gg, Kalshi) → strict market board → executive market/exchange board → originated rating line (official Valve VRS points, bo3.gg match-history Elo) → HLTV-checked originated line → unresolved (blank). HotSpawn data is never a probability input.</p>
<h2>3. Leaderboard pick</h2><pre style="white-space:pre-wrap;font-size:.85rem">{esc(strategy.__doc__.strip())}</pre>
<h2>4. Refresh</h2><p>GitHub Actions workflow <code>strategy-f28afd9e.yml</code>, cron <code>{REFRESH_CRON}</code> (every 4 hours) plus after each lobby/board refresh; no manual input.</p>
<h2>5. Track record of this page</h2><p>{len(settled)} settled of {len(hrows)} published picks. Safe correct: {sum(1 for h in settled if h['winner'] == h['safe_pick'])}; leaderboard correct: {sum(1 for h in settled if h['winner'] == h['leaderboard_pick'])}.</p>
<h2>6. Boards used at this build</h2><ul>{''.join(f'<li>{esc(k)}: built {esc(v)}</li>' for k, v in board['boards_used'].items())}</ul>"""
    (SITE / "method.html").write_text(page("method.html", "How it works", mb, g), encoding="utf-8")


def _d1own(day1, fid, team):
    for r in (day1 or {}).get("rows", []):
        if r["fixture_id"] == fid and r.get("crowd"):
            own = strategy.ownership(r["crowd"]["pct_a"], r["crowd"]["pct_b"])
            return f"{(own[0] if r['team_a'] == team else own[1]) * 100:.0f}%"
    return "few"


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    board = build()
    (DATA / "board.json").write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    hist = update_history(board)
    render(board, load("data/f28afd9e/day1_review.json"), hist)
    print(json.dumps(board["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
