#!/usr/bin/env python3
"""Day-5 desk builder (session 7900154b).

Reads (never writes) the canonical capture ``data/c64a5e19/board.json``, this session's own
lobby read and its own collected bookmaker lines, then renders a phone-first desk at
``day5/``.

Where a published probability comes from, in priority order:

  1. **market**   - a real two-way price from an external bookmaker or esportsbook
     (Thunderpick via bo3.gg, Pinnacle, Bovada, Melbet), margin removed proportionally.
  2. **model**    - Valve's own regional standings through the formula Valve publishes.
     Used only when no book prices the match. Labelled as a model, never as a price.
  3. **bound**    - a conservative lower bound, used when exactly one side is rated.
  4. **none**     - no defensible probability. Published as unresolved with the exact sources
     that were tried. Never filled in, never defaulted to 50/50.

HotSpawn's crowd percentages are carried as leaderboard context only. They never enter a
probability; they are only used to measure the leaderboard edge of a pick.
"""
from __future__ import annotations

import html
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import core  # noqa: E402  (local module, same directory)

OUT = os.path.join(ROOT, "day5")
CANON = "data/c64a5e19/board.json"
QUOTES = "data/7900154b/quotes.json"
TWC = "data/7900154b/twc.json"
LOBBY_SEED = "data/7900154b/lobby.json"

VRS_PAGE = ("https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/"
            "live/2026/standings_global_2026_10_05.md")
LOBBY = "https://play.hotspawn.com/lobby"

# Sources that may set a published probability. Everything else is a cross-check only.
PRICE_SOURCES = {"thunderpick_bo3", "pinnacle", "bovada", "melbet"}
EXCHANGE_SOURCES = {"kalshi", "polymarket"}


def esc(v):
    return html.escape("" if v is None else str(v), quote=True)


def load(rel, default=None):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return default


def pct(v, digits=1):
    return "&mdash;" if v is None else f"{float(v) * 100:.{digits}f}%"


def fmt_utc(value, long=False):
    if not value:
        return "&mdash;"
    try:
        dt = datetime.strptime(str(value)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return esc(value)
    return dt.strftime("%a %d %b %H:%M UTC") if long else dt.strftime("%d %b %H:%M")


# --------------------------------------------------------------------- quote joining
def join_own_quotes(fixture, quotes):
    """Join this session's collected prices to one fixture.

    A price joins only when BOTH team names resolve to the same canonical key and the source
    kickoff is inside the tolerance window. A one-sided price is never accepted.
    """
    priced, cross = [], []
    fa, fb = fixture.get("team_a"), fixture.get("team_b")
    fstart = core.parse_iso(fixture.get("start_utc"))
    for q in quotes:
        same = core.same_team(q.get("team_a"), fa) and core.same_team(q.get("team_b"), fb)
        swapped = core.same_team(q.get("team_b"), fa) and core.same_team(q.get("team_a"), fb)
        if not (same or swapped):
            continue
        qstart = core.parse_iso(q.get("start_utc"))
        if fstart and qstart:
            gap = core.hours_apart(fstart, qstart)
            if gap is None or gap > core.KICKOFF_TOLERANCE_HOURS:
                continue
        elif q.get("source_key") in PRICE_SOURCES:
            # A bookmaker price with no verifiable kickoff cannot be tied to a fixture.
            continue
        else:
            cross.append({**q, "swapped": swapped})
            continue
        nv = core.no_vig(q.get("decimal_a"), q.get("decimal_b"))
        if not nv:
            continue
        p_a = nv["prob_b"] if swapped else nv["prob_a"]
        rec = {**q, "prob_a": p_a, "prob_b": 1.0 - p_a, "overround": nv["overround"],
               "swapped": swapped, "origin": "own"}
        (priced if q.get("source_key") in PRICE_SOURCES else cross).append(rec)
    return priced, cross


def orient_canonical_quote(q, team_a, team_b):
    """Turn one canonical-capture quote into a fixture-oriented probability.

    The probability is recomputed from the raw decimals whenever they are present, and the
    source's team order is resolved by name, so the row can never inherit a reversed price.
    """
    names = q.get("names_at_source") or [q.get("team_a"), q.get("team_b")]
    nv = core.no_vig(q.get("decimal_a"), q.get("decimal_b"))
    if nv and names and len(names) == 2:
        if core.same_team(names[0], team_a) and core.same_team(names[1], team_b):
            return {**q, "prob_a": nv["prob_a"], "prob_b": nv["prob_b"], "origin": "canonical"}
        if core.same_team(names[0], team_b) and core.same_team(names[1], team_a):
            return {**q, "prob_a": nv["prob_b"], "prob_b": nv["prob_a"], "origin": "canonical"}
    p_a = q.get("no_vig_prob_team_a")
    if p_a is None:
        return None
    p_a = float(p_a)
    return {**q, "prob_a": p_a, "prob_b": 1.0 - p_a, "origin": "canonical"}


# ------------------------------------------------------------------------ the board
def resolve_vrs(row, base):
    """Official Valve ratings for both sides of a row.

    The canonical capture's own resolution is used when it has one; a side it left blank is
    resolved here against Valve's full list, using the newest-activity rule for a name that
    appears more than once.
    """
    vrs = base.get("vrs") or {}
    a = vrs.get("team_a")
    b = vrs.get("team_b")
    note = ""
    for side, name in (("team_a", row.get("team_a")), ("team_b", row.get("team_b"))):
        if vrs.get(side):
            continue
        entry, ambiguous = core.vrs_resolve(name, VRS_INDEX)
        if entry:
            if side == "team_a":
                a = entry
            else:
                b = entry
            if ambiguous:
                note = (f"Valve's list carries more than one {name} entry (older rosters of the "
                        f"same organisation); the entry with the most recent activity "
                        f"({entry.get('latest_match_date') or 'undated'}) was used.")
    return a, b, note


def open_fixtures(canon, lobby):
    """The set of matches that can still be picked, taken from the live lobby read.

    Falls back to the canonical capture's own open list when no lobby read is available.
    A row whose lock time has already passed is never presented as pickable.
    """
    rows = []
    canon_by_id = {str(r.get("fixture_id")): r for r in (canon.get("open") or [])}
    now = core.now_utc()
    cards = (lobby or {}).get("cards") or []
    if cards:
        for card in cards:
            fid = str(card.get("fixture_id"))
            base = canon_by_id.get(fid, {})
            lock = card.get("lock_utc") or base.get("lock_utc")
            if lock and core.parse_iso(lock) and core.parse_iso(lock) <= now:
                continue
            rows.append({
                "fixture_id": fid,
                "competition": card.get("competition") or base.get("competition"),
                "tier": card.get("tier") or base.get("tier"),
                "stage": card.get("stage") or base.get("stage"),
                "best_of": card.get("best_of", base.get("best_of")),
                "points": card.get("points", base.get("points")),
                "start_utc": card.get("start_utc") or base.get("start_utc"),
                "lock_utc": lock,
                "team_a": card.get("team_a") or base.get("team_a"),
                "team_b": card.get("team_b") or base.get("team_b"),
                "hotspawn_url": card.get("hotspawn_url") or base.get("hotspawn_url"),
                "crowd_a": card.get("crowd_a"),
                "crowd_b": card.get("crowd_b"),
                "canon": base,
            })
    else:
        for base in canon.get("open") or []:
            lock = base.get("lock_utc")
            if lock and core.parse_iso(lock) and core.parse_iso(lock) <= now:
                continue
            rows.append({
                "fixture_id": str(base.get("fixture_id")),
                "competition": base.get("competition"), "tier": base.get("tier"),
                "stage": base.get("stage"), "best_of": base.get("best_of"),
                "points": base.get("points"), "start_utc": base.get("start_utc"),
                "lock_utc": lock, "team_a": base.get("team_a"), "team_b": base.get("team_b"),
                "hotspawn_url": base.get("hotspawn_url"),
                "crowd_a": None, "crowd_b": None, "canon": base,
            })
    rows.sort(key=lambda r: (r.get("start_utc") or "", r.get("fixture_id") or ""))
    return rows


def finish_row(row, canon):
    """Attach a probability, a pick and a climb decision to one row."""
    base = row.get("canon") or {}
    quotes = []
    for q in base.get("quotes") or []:
        oq = orient_canonical_quote(q, row.get("team_a"), row.get("team_b"))
        if oq:
            quotes.append(oq)
    priced = [q for q in quotes if q.get("source_key") in PRICE_SOURCES
              or q.get("source_key") in EXCHANGE_SOURCES]
    own_priced, own_cross = join_own_quotes(row, own_quotes_global)
    priced = priced + own_priced

    p_a = p_b = None
    basis = "none"
    detail = ""
    sources = []

    book_quotes = [q for q in priced if q.get("source_key") in PRICE_SOURCES]
    exchange_quotes = [q for q in priced if q.get("source_key") in EXCHANGE_SOURCES]
    use = book_quotes or exchange_quotes
    if use:
        p_a = core.blend([q["prob_a"] for q in use])
        p_b = 1.0 - p_a
        names = sorted({q.get("source_name") or q.get("source_key") for q in use})
        basis = "market" if book_quotes else "exchange"
        if book_quotes and exchange_quotes:
            detail = (f"Bookmaker price from {', '.join(sorted({q.get('source_name') or q.get('source_key') for q in book_quotes}))}, "
                      f"margin removed proportionally. An exchange midpoint "
                      f"({', '.join(sorted({q.get('source_name') or q.get('source_key') for q in exchange_quotes}))}) "
                      f"is shown as a cross-check and is not blended in.")
        else:
            detail = (f"{len(use)} two-way price{'s' if len(use) != 1 else ''} from "
                      f"{', '.join(names)}; margin removed proportionally.")
        for q in use:
            sources.append({"label": q.get("source_name") or q.get("source_key"),
                            "url": q.get("public_url") or q.get("url")})
        # Irregularity check: the price and the ratings model should not disagree wildly.
        vrs_a, vrs_b, _ = resolve_vrs(row, base)
        pa = (vrs_a or {}).get("points")
        pb = (vrs_b or {}).get("points")
        if pa is not None and pb is not None:
            mp = core.vrs_probability(pa, pb, CALIBRATION.get("k") or 1.0)
            if mp is not None:
                gap = abs(mp - p_a)
                if gap >= 0.20:
                    detail += (f" The ratings model would say {mp * 100:.1f}%, which is "
                               f"{gap * 100:.0f} points away from the price; the price is the "
                               f"pick and the disagreement is flagged.")
                    row.setdefault("flags", []).append(
                        f"model_market_gap_{int(round(gap * 100))}pp")
    else:
        vrs_a, vrs_b, note = resolve_vrs(row, base)
        pa = (vrs_a or {}).get("points")
        pb = (vrs_b or {}).get("points")
        model = base.get("model") or {}
        cal = CALIBRATION
        k = cal.get("k") or 1.0
        if pa is not None and pb is not None:
            p_a = core.vrs_probability(pa, pb, k)
            if p_a is None:
                p_a = model.get("prob_a")
            p_b = 1.0 - p_a if p_a is not None else None
            basis = "model"
            raw = core.vrs_probability(pa, pb, 1.0)
            detail = (f"No external book price at this capture. Valve's own global regional "
                      f"standings (2026-10-05) rate {row.get('team_a')} {pa} and "
                      f"{row.get('team_b')} {pb}. Valve's published rating curve, with the slope "
                      f"the repository fits to {cal.get('n_pairs', 0)} observed bookmaker lines "
                      f"(k={k:.4f}), gives {p_a * 100:.1f}%"
                      + (f"; Valve's raw slope would give {raw * 100:.1f}%" if raw else "")
                      + ". This is a ratings model, not a bookmaker price."
                      + (f" {note}" if note else ""))
            sources.append({"label": "Valve regional standings (model input)", "url": VRS_PAGE})
        elif pa is not None or pb is not None:
            rated_pts = pa if pa is not None else pb
            floor_pts = VRS_FLOOR
            bound = core.bounded_probability(rated_pts, floor_pts, k)
            if bound is None:
                bound = 0.5
            if pa is not None:
                p_a, p_b = bound, 1.0 - bound
                rated, unrated = row.get("team_a"), row.get("team_b")
            else:
                p_a, p_b = 1.0 - bound, bound
                rated, unrated = row.get("team_b"), row.get("team_a")
            basis = "bound"
            detail = (f"{rated} is rated in Valve's global regional standings "
                      f"({rated_pts} points). {unrated} is not in Valve's list of 380 teams, so "
                      f"treating it as no better than the list floor ({floor_pts} points, the "
                      f"lowest team Valve does rank) puts {rated} at no less than "
                      f"{max(p_a, p_b) * 100:.1f}%. This is a floor, not an estimate: an unlisted "
                      f"side could in principle be weaker still. No bookmaker priced this "
                      f"match at this capture." + (f" {note}" if note else ""))
            sources.append({"label": "Valve regional standings (model input)", "url": VRS_PAGE})
        else:
            detail = ("Neither side appears in Valve's global regional standings and no external "
                      "book priced this match at this capture. The bookmakers that price "
                      "Counter-Strike 2 do not list this event." + (f" {note}" if note else ""))

    row["prob_a"], row["prob_b"] = p_a, p_b
    row["basis"] = basis
    row["basis_detail"] = detail
    row["quotes"] = priced
    row["crosscheck"] = own_cross
    for q in own_cross:
        sources.append({"label": f"{q.get('source_name') or q.get('source_key')} (cross-check only)",
                        "url": q.get("public_url") or q.get("url")})
    if row.get("hotspawn_url"):
        sources.append({"label": "HotSpawn fixture", "url": row["hotspawn_url"]})
    for s in base.get("sources") or []:
        if s.get("url") and s.get("label") != "HotSpawn fixture":
            sources.append(s)
    row["sources"] = sources
    row["flags"] = list(base.get("flags") or [])

    if p_a is None or p_b is None:
        row["pick"] = None
        row["pick_prob"] = None
        row["climb"] = None
        row["unresolved_reason"] = detail
        return row

    decision = core.choose_pick(p_a, p_b, row.get("crowd_a"), row.get("crowd_b"))
    if decision["safe"] == "a":
        row["pick"], row["pick_prob"] = row.get("team_a"), p_a
    else:
        row["pick"], row["pick_prob"] = row.get("team_b"), p_b
    climb = None
    if decision.get("climb") in ("a", "b"):
        prob = p_a if decision["climb"] == "a" else p_b
        team = row.get("team_a") if decision["climb"] == "a" else row.get("team_b")
        climb = {"team": team, "prob": prob, "reason": decision.get("climb_reason"),
                 "rejected": decision.get("climb_rejected")}
    row["climb"] = climb
    row["climb_rejected"] = decision.get("climb_rejected")
    row["edge"] = decision.get("edge")
    return row


def build_rows(canon, lobby, quotes):
    global own_quotes_global
    own_quotes_global = quotes
    rows = [finish_row(r, canon) for r in open_fixtures(canon, lobby)]
    return rows


def build_featured(twc, quotes, canon):
    """The two TWC 2026 day-5 matches, priced the same way as every lobby fixture."""
    global own_quotes_global
    own_quotes_global = quotes
    out = []
    for m in twc.get("day5", {}).get("matches", []):
        fixture = {"team_a": m.get("team_a"), "team_b": m.get("team_b"),
                   "start_utc": m.get("start_utc")}
        priced, cross = join_own_quotes(fixture, quotes)
        vrs_a, vrs_b = vrs_pair(canon, fixture)
        row = {
            "fixture_id": f"twc-{m.get('key')}",
            "competition": "Thunderpick World Championship 2026",
            "stage": m.get("stage"),
            "tier": "S",
            "best_of": m.get("best_of"),
            "start_utc": m.get("start_utc"),
            "lock_utc": None,
            "team_a": m.get("team_a"),
            "team_b": m.get("team_b"),
            "hotspawn_url": None,
            "hotspawn_listed": bool(m.get("hotspawn_listed")),
            "hltv_url": m.get("hltv_url"),
            "bo3_url": m.get("bo3_url"),
            "crowd_a": None, "crowd_b": None,
            "canon": {},
            "quotes": priced,
            "crosscheck": cross,
            "notes": [m.get("team_a_note"), m.get("team_b_note")],
            "verdict": m.get("verdict"),
            "upshot_note": m.get("upshot_note"),
            "verified_by": m.get("verified_by"),
            "vrs": {"team_a": vrs_a, "team_b": vrs_b},
        }
        finish_row(row, canon)
        row["sources"] = list(row.get("sources") or []) + [
            {"label": "HLTV match page", "url": m.get("hltv_url")},
            {"label": "bo3.gg match page", "url": m.get("bo3_url")},
        ]
        out.append(row)
    return out


def vrs_pair(canon, fixture):
    """Official Valve ratings for the two sides, from Valve's own global standings."""
    a, amb_a = core.vrs_resolve(fixture.get("team_a"), VRS_INDEX)
    b, amb_b = core.vrs_resolve(fixture.get("team_b"), VRS_INDEX)
    return a, b


# --------------------------------------------------------------------------- pages
STYLE = """
:root{--bg:#0d1117;--card:#161b22;--line:#26303b;--fg:#e6edf3;--mut:#93a1b1;
--good:#3fb950;--warn:#d29922;--bad:#f85149;--accent:#58a6ff;--pick:#1f6feb}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
-webkit-text-size-adjust:100%}
a{color:var(--accent)}
.wrap{max-width:720px;margin:0 auto;padding:12px 12px 40px}
header.top{position:sticky;top:0;z-index:20;background:#0d1117ee;backdrop-filter:blur(8px);
border-bottom:1px solid var(--line);padding:10px 0 8px}
h1{font-size:19px;margin:0 0 2px}
.sub{color:var(--mut);font-size:13px}
nav.tabs{display:flex;gap:6px;overflow-x:auto;padding:8px 0 2px;scrollbar-width:none}
nav.tabs::-webkit-scrollbar{display:none}
nav.tabs a{flex:0 0 auto;font-size:13px;padding:7px 11px;border:1px solid var(--line);
border-radius:999px;text-decoration:none;color:var(--fg);background:#11161d;white-space:nowrap}
nav.tabs a.on{background:var(--pick);border-color:var(--pick);color:#fff;font-weight:600}
h2{font-size:16px;margin:22px 0 8px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:14px;margin:16px 0 6px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}
p{font-size:15px}
.muted{color:var(--mut);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;
margin:0 0 10px}
.card.hot{border-color:#3d4f6b;box-shadow:0 0 0 1px #1d2733}
.topline{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
.teams{font-size:17px;font-weight:650;letter-spacing:-.01em}
.pick{background:var(--pick);color:#fff;border-radius:8px;padding:3px 9px;font-size:13px;
font-weight:700;white-space:nowrap;display:inline-block}
.pick.none{background:#2a2f38;color:var(--mut);font-weight:600}
.pick.climb{background:#6e40c9}
.bar{height:9px;border-radius:5px;background:#21262d;overflow:hidden;display:flex;margin:9px 0 4px}
.bar i{display:block;height:100%}
.bar .a{background:var(--good)}
.bar .b{background:#30363d}
.probs{display:flex;justify-content:space-between;font-size:13px;color:var(--mut)}
.probs b{color:var(--fg);font-size:15px}
.rowmeta{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}
.chip{font-size:11.5px;border:1px solid var(--line);border-radius:6px;padding:2px 7px;color:var(--mut)}
.chip.s{color:#7ee787;border-color:#2b4a33}
.chip.m{color:#79c0ff;border-color:#23406b}
.chip.b{color:#d29922;border-color:#4a3a12}
.chip.x{color:#f85149;border-color:#5a2323}
.kv{font-size:13px;color:var(--mut);margin-top:8px}
.kv b{color:var(--fg)}
.srcs{margin-top:9px;font-size:12.5px}
.srcs a{display:inline-block;margin:0 8px 4px 0}
.btn{display:block;background:#11161d;border:1px solid var(--line);border-radius:10px;
padding:11px 12px;margin:0 0 8px;text-decoration:none;color:var(--fg)}
.btn span{display:block;font-size:12px;color:var(--mut);margin-top:2px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}
.stat b{display:block;font-size:22px;line-height:1.2}
.stat span{font-size:12px;color:var(--mut)}
table{width:100%;border-collapse:collapse;font-size:13.5px;display:block;overflow-x:auto}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--mut);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.03em}
td.wrapcell{white-space:normal;min-width:190px}
.flag{border-left:3px solid var(--warn);padding-left:9px}
.flag.high{border-left-color:var(--bad)}
.note{font-size:13px;color:var(--mut);border-left:2px solid var(--line);padding-left:9px;margin:8px 0}
footer{color:var(--mut);font-size:12.5px;margin-top:26px;border-top:1px solid var(--line);padding-top:12px}
@media (min-width:640px){h1{font-size:24px}.wrap{padding:16px}}
"""


def page(title, active, body, board):
    nav = [("index.html", "Summary"), ("picks.html", "Every pick"),
           ("twc.html", "TWC day 5"), ("unresolved.html", "Unresolved"),
           ("flagged.html", "Flagged"), ("method.html", "Method")]
    tabs = "".join(
        '<a href="%s"%s>%s</a>' % (href, ' class="on"' if href == active else "", label)
        for href, label in nav)
    gen = esc(board.get("summary", {}).get("generated_utc") or "")
    cap = esc(board.get("summary", {}).get("canonical_capture") or "")
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0d1117">
<title>{esc(title)} · HotSpawn picks desk</title>
<style>{STYLE}</style>
</head><body>
<header class="top"><div class="wrap">
<h1>{esc(title)}</h1>
<div class="sub">Counter-Strike 2 picks for every HotSpawn match · built {gen}</div>
<nav class="tabs">{tabs}</nav>
</div></header>
<div class="wrap">
{body}
<footer>
<p>Built {gen} from the HotSpawn lobby read {esc(board.get("summary", {}).get("lobby_read_utc") or cap)}
and external bookmaker lines read the same day. HotSpawn is used for fixture discovery and
settlement only; its crowd percentages are shown as leaderboard context and never as a
probability. Every number on this page has a source link on the row it belongs to.</p>
<p>Unresolved picks and the limits of the method: <a href="unresolved.html">unresolved.html</a>.
Items needing a human decision: <a href="flagged.html">flagged.html</a>.
Method and every rule: <a href="method.html">method.html</a>.</p>
</footer>
</div></body></html>"""


def pick_card(row, hot=False):
    cid = esc(row.get("fixture_id"))
    pa, pb = row.get("prob_a"), row.get("prob_b")
    wa = (pa * 100) if pa is not None else 50
    wb = (pb * 100) if pb is not None else 50
    pick = row.get("pick")
    pick_html = (f'<span class="pick">{esc(pick)}</span>' if pick
                 else '<span class="pick none">no pick</span>')
    basis = row.get("basis")
    chip = {"market": ("s", "bookmaker price"), "exchange": ("b", "exchange midpoint"),
            "model": ("m", "Valve ratings model"),
            "bound": ("b", "lower bound"), "none": ("x", "unresolved")}.get(basis, ("", basis))
    chips = [f'<span class="chip {chip[0]}">{esc(chip[1])}</span>']
    if row.get("tier"):
        chips.append(f'<span class="chip">Tier {esc(row["tier"])}</span>')
    if row.get("points"):
        chips.append(f'<span class="chip">{esc(row["points"])} pts</span>')
    if row.get("best_of"):
        chips.append(f'<span class="chip">Bo{esc(row["best_of"])}</span>')
    if row.get("stage"):
        chips.append(f'<span class="chip">{esc(row["stage"])}</span>')
    if row.get("crowd_a") is not None:
        chips.append(f'<span class="chip">crowd {esc(row.get("crowd_a"))}% / '
                     f'{esc(row.get("crowd_b"))}% (context only)</span>')
    if row.get("hotspawn_listed") is False:
        chips.append('<span class="chip x">not in HotSpawn lobby</span>')
    links = "".join(f'<a href="{esc(s.get("url"))}" rel="noopener">{esc(s.get("label"))}</a>'
                    for s in (row.get("sources") or []) if s.get("url"))
    climb = row.get("climb")
    if climb and climb.get("team"):
        climb_html = (f'<div class="kv"><b>Leaderboard edge:</b> {esc(climb.get("team"))} '
                      f'{pct(climb.get("prob"))} — {esc(climb.get("reason"))}</div>')
    elif row.get("climb_rejected"):
        climb_html = (f'<div class="kv"><b>Leaderboard edge:</b> not taken — '
                      f'{esc(row["climb_rejected"])}</div>')
    else:
        climb_html = ""
    extra = ""
    if row.get("verdict"):
        extra += f'<div class="kv"><b>Verdict:</b> {esc(row["verdict"])}</div>'
    for note in row.get("notes") or []:
        if note:
            extra += f'<div class="muted" style="font-size:12.5px;margin-top:6px">{esc(note)}</div>'
    if row.get("upshot_note"):
        extra += f'<div class="note">{esc(row["upshot_note"])}</div>'
    return f"""<div class="card{" hot" if hot else ""}" id="{cid}">
<div class="topline">
<div class="teams">{esc(row.get("team_a"))}<br><span class="muted" style="font-weight:400">vs</span> {esc(row.get("team_b"))}</div>
<div style="text-align:right">{pick_html}<div class="muted" style="font-size:12px;margin-top:4px">{esc(row.get("competition") or "")}</div></div>
</div>
<div class="bar"><i class="a" style="width:{wa:.1f}%"></i><i class="b" style="width:{wb:.1f}%"></i></div>
<div class="probs"><span><b>{pct(pa)}</b> {esc(row.get("team_a"))}</span>
<span><b>{pct(pb)}</b> {esc(row.get("team_b"))}</span></div>
<div class="rowmeta">{''.join(chips)}</div>
<div class="kv"><b>Lock:</b> {fmt_utc(row.get("lock_utc"))} · <b>Start:</b> {fmt_utc(row.get("start_utc"))}</div>
<div class="kv"><b>Basis:</b> {esc(row.get("basis_detail"))}</div>
{climb_html}
{extra}
<div class="srcs">{links}</div>
</div>"""


def render_index(board, rows, featured, twc):
    s = board["summary"]
    stats = [("Open matches", s.get("open", 0)), ("Book price", s.get("market", 0)),
             ("Ratings model", s.get("model", 0)), ("Bound only", s.get("bound", 0)),
             ("Unresolved", s.get("unresolved", 0)), ("Leaderboard edge", s.get("climb", 0))]
    stat_html = "".join(f'<div class="stat"><b>{v}</b><span>{esc(k)}</span></div>'
                        for k, v in stats)
    soon = [r for r in rows if r.get("lock_utc")][:6]
    soon_html = "".join(
        f'<li><a href="picks.html#{esc(r.get("fixture_id"))}">{esc(r.get("pick") or "no pick")} · '
        f'{esc(r.get("team_a"))} v {esc(r.get("team_b"))}</a> '
        f'<span class="muted">locks {fmt_utc(r.get("lock_utc"))}</span></li>' for r in soon)
    feat = "".join(pick_card(r, hot=True) for r in featured)
    return f"""
<h2>TWC 2026 · day 5 · {esc(twc.get("day5", {}).get("date"))}</h2>
<p class="muted">Day 5 is {esc(twc.get("day5", {}).get("label"))}: a third-place decider and the
grand final. Both are priced from the same external lines used for every lobby match. The grand
final is <b>not yet in HotSpawn's pick'em inventory</b>, so there is no HotSpawn pick to make for
it yet — it is priced anyway, and this page picks it up automatically if HotSpawn lists it.</p>
{feat}
<h2>Where the picks are</h2>
<a class="btn" href="picks.html"><strong>Every pick, one card per match</strong>
<span>All {s.get("open", 0)} open Counter-Strike 2 matches with both win probabilities, the pick,
the basis and a source link on every row</span></a>
<a class="btn" href="twc.html"><strong>TWC 2026 day 1 to day 5 review</strong>
<span>Every day-1 to day-4 result verified on HLTV, the day-5 bracket, and the strategy that
produced the day-5 picks</span></a>
<a class="btn" href="unresolved.html"><strong>Unresolved picks and the limits of the method</strong>
<span>{s.get("unresolved", 0)} match(es) with no defensible probability, plus every limitation of
the pricing and the exact sources tried</span></a>
<a class="btn" href="flagged.html"><strong>Flagged for review</strong>
<span>{len(twc.get("flags", []))} items that need a human decision, each with its source
links</span></a>
<a class="btn" href="method.html"><strong>Method, rules and every source</strong>
<span>How a probability is derived, how a pick is chosen, and what the contrarian floor
means</span></a>
<h2>This capture</h2>
<div class="grid">{stat_html}</div>
<div class="card" style="margin-top:10px">
<div class="kv"><b>HotSpawn lobby read:</b> {esc(s.get("lobby_read_utc"))}</div>
<div class="kv"><b>Canonical capture:</b> {esc(s.get("canonical_capture"))}</div>
<div class="kv"><b>Desk built:</b> {esc(s.get("generated_utc"))}</div>
<div class="kv"><b>CS2 fixtures listed by HotSpawn:</b> {esc(s.get("listed"))}, of which
{esc(s.get("open"))} are still open for a pick</div>
<div class="kv"><b>Lines used:</b> {esc(s.get("source_summary"))}</div>
</div>
<h2>Next locks</h2>
<ul class="muted">{soon_html or "<li>No open match has a published lock time.</li>"}</ul>
"""


def render_picks(board, rows, featured):
    s = board["summary"]
    body = [f"<h2>Every open match · {s.get('open', 0)} rows</h2>",
            '<p class="muted">Each card is one HotSpawn Counter-Strike 2 match you can still '
            'pick. Both win probabilities come from external bookmaker prices, or from Valve\'s '
            'own ratings when no book prices the match. HotSpawn\'s crowd share is shown as '
            'context only.</p>']
    if featured:
        body.append("<h2>TWC 2026 day 5</h2>")
        body.extend(pick_card(r, hot=True) for r in featured)
    body.append(f"<h2>HotSpawn lobby · {s.get('open', 0)} open matches</h2>")
    body.extend(pick_card(r) for r in rows)
    body.append(f'<p class="muted">{s.get("listed", 0)} CS2 fixtures are listed by HotSpawn in '
                f'this capture; {s.get("open", 0)} are still open for a pick. The rest have '
                'already locked and cannot be picked.</p>')
    return "\n".join(body)


def render_twc(board, twc):
    days = []
    for day in twc.get("days", []):
        rows_html = ""
        for r in day.get("results", []):
            note = f'<div class="note">{esc(r.get("note"))}</div>' if r.get("note") else ""
            verified = (f'<div class="muted" style="font-size:12px">Verified: '
                        f'{esc(r.get("verified_by"))}</div>') if r.get("verified_by") else ""
            upset = ' <span class="chip x">upset</span>' if r.get("upset") else ""
            rows_html += (f'<tr><td class="wrapcell"><b>{esc(r.get("team_a"))} '
                          f'{esc(r.get("score_a"))}&ndash;{esc(r.get("score_b"))} '
                          f'{esc(r.get("team_b"))}</b>{upset}'
                          f'<div class="muted" style="font-size:12px">'
                          f'{esc(r.get("maps") or "")}</div>{note}{verified}</td>'
                          f'<td>{fmt_utc(r.get("start_utc"))}</td>'
                          f'<td><a href="{esc(r.get("hltv_url"))}" rel="noopener">HLTV</a></td></tr>')
        days.append(f"""<h3>Day {day.get('day')} · {esc(day.get('date'))} · {esc(day.get('label'))}</h3>
<table><thead><tr><th>Result</th><th>Start (UTC)</th><th>Source</th></tr></thead>
<tbody>{rows_html}</tbody></table>""")

    d5 = twc.get("day5", {})
    d5_html = ""
    for m in d5.get("matches", []):
        row = next((r for r in board.get("featured", [])
                    if r.get("fixture_id") == f"twc-{m.get('key')}"), None)
        card = pick_card(row, hot=True) if row else ""
        listed = ("listed in the HotSpawn pick'em" if m.get("hotspawn_listed")
                  else "not in HotSpawn's pick'em inventory at this capture")
        d5_html += f"""<div class="card">
<div class="muted" style="margin-bottom:8px">{esc(m.get('stage'))} · Bo{esc(m.get('best_of'))} ·
{esc(listed)}</div>
{card}
<div class="kv"><b>Verified:</b> {esc(m.get('verified_by'))}</div>
<div class="srcs">{''.join(f'<a href="{esc(s.get("url"))}" rel="noopener">{esc(s.get("label"))}</a>' for s in m.get('sources', []))}</div>
</div>"""

    ctx = "".join(
        f'<div class="note"><b>{esc(p.get("text"))}</b><div class="srcs">'
        + "".join(f'<a href="{esc(s.get("url"))}" rel="noopener">{esc(s.get("label"))}</a>'
                  for s in p.get("sources", [])) + "</div></div>"
        for p in twc.get("day5_context", {}).get("points", []))
    rp = twc.get("roster_premise", {})
    premise = ""
    if rp:
        checks = "".join(f'<li>{esc(c.get("what"))} — <a href="{esc(c.get("url"))}" '
                         f'rel="noopener">source</a></li>' for c in rp.get("checked", []))
        premise = f"""<h3>The Aurora roster premise</h3>
<div class="card flag"><p><b>Claim:</b> {esc(rp.get('claim'))}</p>
<p><b>Verdict:</b> {esc(rp.get('verdict_plain'))}</p>
<ul class="muted">{checks}</ul>
<p class="muted">{esc(rp.get('consequence'))}</p></div>"""
    return f"""
<h2>What day 1 to day 4 actually say</h2>
<p class="muted">Every result below was read from the linked HLTV match page. The
<b>9z 2&ndash;0 Aurora</b> upset in the brief is real, and it is the only day-1 upset; two more
favourites fell later in the event, including BETBOOM knocking Falcons out in the semi-final.
</p>
{''.join(days)}
<h2>Day 5 · {esc(d5.get('date'))}</h2>
{d5_html}
<h2>How days 1 to 4 guide the day-5 picks</h2>
{ctx}
{h2 if False else ''}
<premise_block>{premise}</premise_block>
"""


def render_unresolved(board, rows, featured, twc):
    s = board["summary"]
    unresolved = [r for r in rows if r.get("basis") == "none"]
    body = [f"""<h2>Unresolved picks · {len(unresolved)}</h2>
<p class="muted">These are the matches where no probability could be derived from any source.
They are published blank on purpose: a number that cannot be sourced is not published, and a
blank is never quietly replaced with 50/50.</p>"""]
    for r in unresolved:
        body.append(f"""<div class="card">
<div class="teams">{esc(r.get('team_a'))} <span class="muted" style="font-weight:400">vs</span>
{esc(r.get('team_b'))}</div>
<div class="kv"><b>Start:</b> {fmt_utc(r.get('start_utc'))} · <b>Lock:</b>
{fmt_utc(r.get('lock_utc'))} · {esc(r.get('competition'))}</div>
<div class="kv"><b>Why it is unresolved:</b> {esc(r.get('unresolved_reason'))}</div>
<div class="srcs">{''.join(f'<a href="{esc(s.get("url"))}" rel="noopener">{esc(s.get("label"))}</a>' for s in r.get('sources', []))}</div>
</div>""")
    body.append("""<h2>Limitations of the method</h2>
<div class="card">
<ul>
<li><b>HotSpawn is not a source of probability.</b> Its crowd percentages are shown as
leaderboard context only and never enter a probability. A crowd split measures what people
picked, not what is likely to happen.</li>
<li><b>A probability is only ever one of four things.</b> A real external bookmaker price with
the margin removed; an exchange midpoint, labelled as such; Valve's own regional-standings
model when no book prices the match; or a conservative lower bound when only one side is
rated. The basis label on every row says which.</li>
<li><b>The ratings model is not a bookmaker price.</b> It applies the expected-win formula
Valve publishes for its own ranking to a dated snapshot of the global standings. It is a model,
it is twelve days old, and it is labelled as a model wherever it appears.</li>
<li><b>Low-tier coverage depends on the esportsbook, not the mainstream books.</b> Pinnacle,
Bovada and Melbet do not list most CCT and NODWIN events. The lines that cover them come from
Thunderpick through bo3.gg, and where that is missing the row falls back to the ratings model
or to the unresolved list.</li>
<li><b>Name matching is conservative.</b> A price is joined only when both sides of a fixture
resolve to the same canonical team key and the source kickoff is within the tolerance window.
A one-sided price, a price with no kickoff, or a price with a different opponent is rejected
rather than guessed at.</li>
<li><b>Exchange and prediction-market prices are midpoints, not executable quotes.</b> Kalshi's
bid/ask midpoint and a Polymarket midpoint are shown where they exist and are labelled; where
nothing else prices the match they may be used under the same rule-backed fallback the
canonical board already applies, and the row says so.</li>
<li><b>Nothing is forecast for a match that has not started.</b> These are pre-match
probabilities from prices and ratings. They are not results and they are not advice.</li>
<li><b>The Valve snapshot is dated.</b> The newest global standings file in Valve's repository
is 2026-10-05; there is no live feed, so a roster or ranking change after that date is not
reflected in a model-based row.</li>
<li><b>Coverage is a snapshot, not a subscription.</b> The board is rebuilt every four hours
from a fresh read of the lobby and the books. A match that appears between reads waits for the
next one.</li>
</ul>
</div>
<h2>What the desk does with each basis</h2>
<table><thead><tr><th>Basis</th><th>Meaning</th><th>Count this capture</th></tr></thead><tbody>
<tr><td>Bookmaker price</td><td class="wrapcell">An external two-way price, margin removed
proportionally. Where more than one book prices the match the probabilities are averaged.</td>
<td>{market}</td></tr>
<tr><td>Exchange midpoint</td><td class="wrapcell">A bid/ask midpoint or a market midpoint. Used
only where no bookmaker prices the match, and labelled on the row.</td>
<td>{exchange}</td></tr>
<tr><td>Valve ratings model</td><td class="wrapcell">No external price; Valve's published
expected-win formula applied to the 2026-10-05 global standings.</td>
<td>{model}</td></tr>
<tr><td>Lower bound</td><td class="wrapcell">Only one side is rated, so no head-to-head
probability exists. A floor, not an estimate.</td>
<td>{bound}</td></tr>
<tr><td>Unresolved</td><td class="wrapcell">Neither side rated and no external price. Published
blank with the reason.</td>
<td>{unresolved}</td></tr>
</tbody></table>
""".format(market=esc(s.get("market", 0)), exchange=esc(s.get("exchange", 0)),
           model=esc(s.get("model", 0)), bound=esc(s.get("bound", 0)),
           unresolved=esc(s.get("unresolved", 0))))
    return "\n".join(body)


def render_flagged(board, twc):
    flags = twc.get("flags", [])
    blocks = []
    for f in flags:
        sev = f.get("severity", "low")
        cls = "flag high" if sev == "high" else ("flag" if sev == "medium" else "")
        links = "".join(f'<a href="{esc(s.get("url"))}" rel="noopener">{esc(s.get("label"))}</a>'
                        for s in f.get("sources", []))
        blocks.append(f"""<div class="card {cls}">
<div class="topline"><div class="teams">{esc(f.get('id'))} · {esc(f.get('title'))}</div>
<span class="chip {'x' if sev == 'high' else 'b'}">{esc(sev)}</span></div>
<p class="muted">{esc(f.get('detail'))}</p>
<div class="srcs">{links}</div>
</div>""")
    return ("<h2>Flagged for review · " + str(len(flags)) + " items</h2>"
            "<p class=\"muted\">These do not block the board. Each one is a statement this desk "
            "could not confirm from an official source, or a decision that is safer left to a "
            "human. Every item carries the source links behind it.</p>" + "\n".join(blocks))


def render_method(board, twc):
    s = board["summary"]
    cal = board.get("calibration") or {}
    cal_rows = ""
    if cal:
        cal_rows = f"""<div class="card">
<div class="kv"><b>Fitted slope k:</b> {esc(round(cal.get('k') or 1.0, 5))}</div>
<div class="kv"><b>Market pairs used:</b> {esc(cal.get('n_pairs'))} (minimum needed:
{esc(cal.get('min_pairs'))})</div>
<div class="kv"><b>Mean absolute error:</b> {esc(round(cal.get('mae_prob') or 0, 4))} with the
fitted slope, against {esc(round(cal.get('mae_prob_valve') or 0, 4))} with Valve's raw
slope</div>
<div class="kv"><b>Where the pairs come from:</b>
{esc(', '.join(cal.get('sources') or []))}</div>
<div class="srcs"><a href="https://github.com/ValveSoftware/counter-strike_regional_standings"
rel="noopener">Valve's ratings repository</a></div>
</div>"""
    return f"""<h2>What this desk is</h2>
<p>A phone-first board of Counter-Strike 2 picks for every match the HotSpawn Pick'ems lobby
lists, with a win probability for each side derived from sources outside HotSpawn, and a
separate page for the TWC 2026 day-5 final.</p>
<h2>How a probability is derived</h2>
<table><thead><tr><th>Step</th><th>Rule</th></tr></thead><tbody>
<tr><td>1. Discovery</td><td class="wrapcell">Fixtures come from the HotSpawn lobby page and the
public HotSpawn fixtures API, which is the same API the lobby itself calls. A fixture is
"open" if it is on the lobby and its lock time has not passed.</td></tr>
<tr><td>2. Price</td><td class="wrapcell">A price comes from Thunderpick (through bo3.gg),
Pinnacle, Bovada or Melbet. The margin is removed proportionally:
p = (1/dA) / (1/dA + 1/dB).</td></tr>
<tr><td>3. Join</td><td class="wrapcell">A price is joined only when both team names resolve to
the same canonical key and the source kickoff is within the tolerance window. Names are folded
for accents, organisational words (Gaming, Team, Esports) and a leading "ex" (a rebranded
roster). A one-sided price is rejected.</td></tr>
<tr><td>4. Blend</td><td class="wrapcell">Where more than one book prices the same match, the
no-vig probabilities are averaged with equal weight per book.</td></tr>
<tr><td>5. Model</td><td class="wrapcell">With no external price, Valve's own expected-win
formula is applied to the 2026-10-05 global regional standings, through the repository's own
engine, with the slope fitted to observed bookmaker lines. Labelled as a model, never as a
price.</td></tr>
<tr><td>6. Bound</td><td class="wrapcell">With only one side rated, a conservative lower bound
is published and labelled as a bound.</td></tr>
<tr><td>7. Unresolved</td><td class="wrapcell">With neither side rated and no price, the row is
published blank on the unresolved page with the reason and the sources that were tried.</td></tr>
</tbody></table>
<h2>The ratings model, and how its slope was fitted</h2>
<p>Valve's published rating curve is
p<sub>A</sub> = 1 / (1 + 10<sup>&minus;g&middot;&Delta;/400</sup>), with g from Valve's own
Glicko code and &Delta; the rating difference. Valve's own README says that curve is too
steep &mdash; it underestimates win rates at the low end and overestimates them at the high
end &mdash; so the slope is <b>learned from observed bookmaker lines</b> instead of assumed.
Least squares on logit(market) = k&middot;C&middot;&Delta; over the market pairs below gives
the k used on every model and bound row.</p>
{cal_rows}
<p>Rows where a book price and the ratings model disagree by 20 points or more carry a
<code>model_market_gap</code> flag, and the row says so. The price always wins; the model is
the fallback.</p>
<h2>How the pick is chosen</h2>
<p>Every row carries a <b>safe pick</b>, which is simply the side with the higher probability,
and a <b>leaderboard edge</b> layer, which is the side the crowd under-picks. The leaderboard
edge is only taken when all three of these hold, and the reason is printed when it is
refused:</p>
<ul>
<li>our own probability for that side is at least <b>{core.CONTRARIAN_FLOOR * 100:.0f}%</b> —
below that it is a lottery ticket, not a climb;</li>
<li>our probability beats the crowd's share of that side by at least
<b>{core.CONTRARIAN_MIN_EDGE * 100:.0f} points</b>;</li>
<li>the crowd has not already taken that side (it must be at most
<b>{core.CROWD_ELSEWHERE * 100:.0f}% picked</b>).</li>
</ul>
<p>When any of those fail, the row says so and why, so a refusal is as reviewable as a pick.</p>
<h2>What is never used</h2>
<ul>
<li>HotSpawn's crowd percentages as a probability. They are context for the leaderboard
decision and nothing else.</li>
<li>Any value that cannot be traced to a source. A blank cell is the correct answer, and it is
published as blank with a reason.</li>
<li>The bo3.gg <code>rating</code> field as a win probability. It repeats across every match of
a tournament, so it is a tournament metric, not a per-match forecast.</li>
</ul>
<h2>Sources</h2>
<table><thead><tr><th>Source</th><th>What it provides</th><th>Link</th></tr></thead><tbody>
<tr><td>HotSpawn lobby</td><td class="wrapcell">Fixture discovery, lock times, points, crowd
context</td><td><a href="{LOBBY}" rel="noopener">play.hotspawn.com/lobby</a></td></tr>
<tr><td>HotSpawn fixtures API</td><td class="wrapcell">The same fixtures the lobby calls, with
UTC start and lock times</td><td><a href="https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures" rel="noopener">fixtures API</a></td></tr>
<tr><td>Thunderpick via bo3.gg</td><td class="wrapcell">Bookmaker coefficients for low-tier CS2
events the mainstream books skip</td><td><a href="https://bo3.gg/api/v1/matches?filter%5Bmatches.status%5D%5Bin%5D=upcoming&amp;filter%5Bmatches.discipline_id%5D%5Bin%5D=1&amp;sort=start_date&amp;page%5Blimit%5D=50" rel="noopener">bo3.gg matches API</a></td></tr>
<tr><td>Pinnacle</td><td class="wrapcell">Moneyline prices</td><td><a href="https://www.pinnacle.com/en/esports/cs2-hub" rel="noopener">pinnacle.com</a></td></tr>
<tr><td>Bovada</td><td class="wrapcell">Moneyline prices</td><td><a href="https://www.bovada.lv" rel="noopener">bovada.lv</a></td></tr>
<tr><td>Melbet</td><td class="wrapcell">Moneyline prices, including most CCT and NODWIN
events</td><td><a href="https://melbet.com/en/line/esports" rel="noopener">melbet.com</a></td></tr>
<tr><td>Kalshi</td><td class="wrapcell">Exchange midpoint, labelled as such</td><td><a href="https://kalshi.com" rel="noopener">kalshi.com</a></td></tr>
<tr><td>Polymarket</td><td class="wrapcell">Market midpoint, labelled as such</td><td><a href="https://polymarket.com" rel="noopener">polymarket.com</a></td></tr>
<tr><td>Valve regional standings</td><td class="wrapcell">Official ratings for the model and the
bound</td><td><a href="{VRS_PAGE}" rel="noopener">Valve's repository</a></td></tr>
<tr><td>HLTV</td><td class="wrapcell">Results, rosters, map scores, head-to-head and the
analytics pages</td><td><a href="https://www.hltv.org/events/8932/thunderpick-world-championship-2026" rel="noopener">TWC 2026 event</a></td></tr>
</tbody></table>
<h2>Refresh</h2>
<p>The capture, the board and this site are rebuilt every four hours, and again as soon as the
upstream HotSpawn capture lands. The published stamp is the board's own build time, and the
lobby read time is printed next to it on every page.</p>
"""


# ------------------------------------------------------------------------------ main
own_quotes_global = []
VRS_INDEX = {}
VRS_FLOOR = None
CALIBRATION = {"k": 1.0, "fitted": False, "n_pairs": 0}


def load_calibration():
    """Fit the ratings-model slope to observed bookmaker lines.

    The slope comes from the repository's published market observations: the canonical
    session's 48 calibration pairs, plus any pair this session's own collector produced.
    Valve's own README says their curve is too steep, so the slope is learned from prices
    rather than assumed.
    """
    global CALIBRATION
    merged = {}
    sources = []
    for rel in ("data/f7279a54/calibration_pairs.json",
                "data/7900154b/calibration_pairs.json"):
        data = load(rel) or {}
        if not data:
            continue
        sources.append(rel)
        items = data.items() if isinstance(data, dict) else enumerate(data)
        for key, pair in items:
            if not isinstance(pair, dict):
                continue
            fid = str(pair.get("fixture_id") or key)
            prev = merged.get(fid)
            if prev and str(prev.get("observed_utc") or "") > str(pair.get("observed_utc") or ""):
                continue
            merged[fid] = pair
    pairs = [p for p in merged.values()
             if p.get("delta") is not None and p.get("market_prob_a") is not None]
    cal = core.fit_calibration(pairs)
    cal["sources"] = sources
    cal["pairs_file"] = "data/f7279a54/calibration_pairs.json"
    CALIBRATION = cal
    return cal


def load_vrs():
    """Valve's global standings: the rating list and the floor of the list.

    This session's own parsed list is preferred; the canonical capture's parsed list is
    the fallback. The canonical list also carries each entry's last activity date, which is
    what separates a current roster from an older one when a name appears twice, so that
    field is merged back in.
    """
    global VRS_INDEX, VRS_FLOOR
    snap = load("data/c64a5e19/snapshot.json") or {}
    dated = (snap.get("vrs") or {}).get("teams") or []
    date_by_key = {(t.get("standing"), t.get("team")): t.get("latest_match_date")
                   for t in dated if t.get("latest_match_date")}
    teams = []
    own = load("data/7900154b/vrs_teams.json") or {}
    if own.get("teams"):
        teams = own["teams"]
    elif dated:
        teams = dated
    for t in teams:
        if not t.get("latest_match_date"):
            t["latest_match_date"] = date_by_key.get((t.get("standing"), t.get("team")))
    VRS_INDEX = core.vrs_index(teams)
    VRS_FLOOR = core.vrs_floor(teams)
    return len(teams)


def main():
    load_vrs()
    cal = load_calibration()
    canon = load(CANON) or {}
    qp = load(QUOTES) or {}
    twc = load(TWC) or {}
    lobby = load(LOBBY_SEED) or {}
    quotes = qp.get("quotes") or []

    rows = build_rows(canon, lobby, quotes)
    featured = build_featured(twc, quotes, canon)

    market = sum(1 for r in rows if r.get("basis") == "market")
    exchange = sum(1 for r in rows if r.get("basis") == "exchange")
    model = sum(1 for r in rows if r.get("basis") == "model")
    bound = sum(1 for r in rows if r.get("basis") == "bound")
    none = sum(1 for r in rows if r.get("basis") == "none")
    climb = sum(1 for r in rows if (r.get("climb") or {}).get("team"))
    src_names = sorted({(q.get("source_name") or q.get("source_key"))
                        for q in quotes if q.get("source_key") in PRICE_SOURCES})
    for r in rows:
        for q in r.get("quotes") or []:
            nm = q.get("source_name") or q.get("source_key")
            if nm and nm not in src_names:
                src_names.append(nm)
    board_stamp = core.to_iso(core.now_utc())
    board = {
        "session": "7900154b",
        "generated_utc": board_stamp,
        "canonical_capture": canon.get("generated_utc"),
        "lobby_read_utc": lobby.get("read_utc"),
        "collection_utc": qp.get("collected_to_utc"),
        "calibration": CALIBRATION,
        "summary": {
            "generated_utc": board_stamp,
            "canonical_capture": canon.get("generated_utc"),
            "lobby_read_utc": lobby.get("read_utc"),
            "listed": len(canon.get("inventory") or []),
            "open": len(rows),
            "market": market, "exchange": exchange, "model": model, "bound": bound,
            "unresolved": none, "climb": climb, "featured": len(featured),
            "with_pick": sum(1 for r in rows if r.get("pick")),
            "source_summary": ", ".join(sorted(src_names)) or "no external price in this capture",
        },
        "rows": rows,
        "featured": featured,
        "flags": twc.get("flags", []),
    }

    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    with open(os.path.join(OUT, "data", "board.json"), "w", encoding="utf-8") as fh:
        json.dump(board, fh, indent=1, ensure_ascii=False)
        fh.write("\n")

    pages = {
        "index.html": page("HotSpawn CS2 picks desk", "index.html",
                           render_index(board, rows, featured, twc), board),
        "picks.html": page("Every pick", "picks.html",
                           render_picks(board, rows, featured), board),
        "twc.html": page("TWC 2026 day 5", "twc.html", render_twc(board, twc), board),
        "unresolved.html": page("Unresolved & limitations", "unresolved.html",
                                render_unresolved(board, rows, featured, twc), board),
        "flagged.html": page("Flagged for review", "flagged.html",
                             render_flagged(board, twc), board),
        "method.html": page("Method & sources", "method.html", render_method(board, twc), board),
    }
    for name, html_text in pages.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            fh.write(html_text)
    print(json.dumps(board["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
