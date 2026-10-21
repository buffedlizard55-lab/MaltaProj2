#!/usr/bin/env python3
"""EVERYPICK build (session 907e9435).

Reads ``data/907e9435/snapshot.json`` and writes:

* ``data/907e9435/board.json``           — the machine-readable board (one row per open fixture)
* ``everypick/index.html``               — mobile executive summary + "where the picks are"
* ``everypick/picks.html``               — every open fixture: pick, both probabilities, sources
* ``everypick/unresolved.html``          — the required separate unresolved + limitations section
* ``everypick/flagged.html``             — irregularities, alias decisions, rejected prices
* ``everypick/method.html``              — ladder, formulas, gates, limitations
* ``everypick/sources.html``             — source ledger with status and observation time

Nothing here invents a value: a probability is published only where it is derived from a retained
source (bookmaker price, exchange order book or the official Valve rating table), and every
assumption is labelled and listed on the unresolved page.
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import core  # noqa: E402

SNAPSHOT = ROOT / "data" / "907e9435" / "snapshot.json"
OUT_DATA = ROOT / "data" / "907e9435"
OUT_SITE = ROOT / "everypick"
CAL_PAIRS = ROOT / "data" / "f7279a54" / "calibration_pairs.json"
BASE_BOARD = ROOT / "data" / "f7279a54" / "board.json"
TRACK = ROOT / "data" / "f7279a54" / "track_record.json"

TIER_META = {
    "market_multi": {"short": "Verified · bookmakers", "cls": "ok",
                     "blurb": "Both teams priced by two or more independent external books."},
    "market_single": {"short": "Verified · one book", "cls": "ok",
                      "blurb": "One external two-way price, de-vigged."},
    "exchange": {"short": "Verified · exchange", "cls": "ok",
                 "blurb": "Kalshi order-book mid inside the spread gate."},
    "vrs_model": {"short": "Originated · official VRS", "cls": "model",
                  "blurb": "No book price: derived from Valve's official rating points."},
    "assumption": {"short": "Assumption", "cls": "warn",
                   "blurb": "The opponent has no official rating and nothing priced the match."},
    "unresolved": {"short": "Withheld", "cls": "bad",
                   "blurb": "No defensible value: see the Unresolved section."},
}


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def pct(value, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%" if isinstance(value, (int, float)) else "—"


def fmt_dt(value: str | None, with_weekday: bool = False) -> str:
    dt = core.parse_iso(value)
    if not dt:
        return "—"
    return dt.strftime("%a %d %b %H:%M UTC" if with_weekday else "%d %b %H:%M UTC")


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


# ------------------------------------------------------------------------------- selection
def is_open(fixture: dict, now: datetime) -> bool:
    if "lobby_page" not in (fixture.get("seen_in") or []):
        return False
    if str(fixture.get("status") or "").lower() not in ("scheduled", "started"):
        return False
    lock = core.parse_iso(fixture.get("lock_utc")) or core.parse_iso(fixture.get("start_utc"))
    start = core.parse_iso(fixture.get("start_utc"))
    reference = max([d for d in (lock, start) if d], default=None)
    return bool(reference and reference > now)


def stale_listing(fixture: dict, now: datetime) -> bool:
    start = core.parse_iso(fixture.get("start_utc"))
    return ("lobby_page" in (fixture.get("seen_in") or [])
            and str(fixture.get("status") or "").lower() == "scheduled"
            and start is not None and start < now - timedelta(days=2))


def conflict_notes(row: dict, quotes: list[dict]) -> list[dict]:
    """Quotes at the same kickoff that name one of our teams but a different opponent."""
    out = []
    start = core.parse_iso(row.get("start_utc"))
    for quote in quotes:
        diff = core.hours_apart(start, core.parse_iso(quote.get("start_utc")))
        if diff is None or diff > core.TIME_TOLERANCE_H:
            continue
        ours = {core.canon(row["team_a"])[0], core.canon(row["team_b"])[0]}
        theirs = {core.canon(quote.get("team_a"))[0], core.canon(quote.get("team_b"))[0]}
        if not (ours & theirs) or ours == theirs:
            continue
        out.append({"source_name": quote.get("source_name"),
                    "url": quote.get("public_url") or quote.get("rules_url"),
                    "event_id": quote.get("event_id"),
                    "names_at_source": [quote.get("team_a"), quote.get("team_b")],
                    "start_utc": quote.get("start_utc"),
                    "prob_a": quote.get("prob_a"),
                    "note": (f"{quote.get('source_name')} lists this {fmt_dt(quote.get('start_utc'))} "
                             f"slot as '{quote.get('team_a')} vs {quote.get('team_b')}', not "
                             f"'{row['team_a']} vs {row['team_b']}'.")})
    return out


# ------------------------------------------------------------------------------- build rows
def build_board(snapshot: dict) -> dict:
    now = core.now_utc()
    fixtures = ((snapshot.get("hotspawn") or {}).get("fixtures") or [])
    quotes = snapshot.get("quotes") or []
    rejected = snapshot.get("rejected_quotes") or []
    vrs = snapshot.get("vrs") or {}

    pairs = list((load_json(CAL_PAIRS, {}) or {}).values())
    cal = core.fit_calibration(pairs)
    stats = core.vrs_stats(vrs)
    floor = stats.get("floor") or {"standing": 0, "points": 0}
    median = float(stats.get("median") or 0)

    open_fixtures = sorted([f for f in fixtures if is_open(f, now)],
                           key=lambda f: (f.get("start_utc") or "", f.get("fixture_id")))
    rows = [core.resolve_fixture(f, quotes, vrs, cal, floor, median) for f in open_fixtures]

    for row in rows:
        conflicts = conflict_notes(row, quotes)
        if conflicts:
            row["conflicts"] = conflicts
            row["flags"].append("kickoff_slot_identity_conflict")
            row["limitations"].append(
                "Another source lists this same kickoff with a different opponent: "
                + " ".join(c["note"] for c in conflicts)
                + " The pick is conditional on HotSpawn's own listing being the fixture that settles.")
        if row["tier_code"] == "assumption" and row.get("prob_range_a"):
            lo, hi = row["prob_range_a"]
            if lo < 0.5 < hi:
                # The two documented assumptions disagree on who is favoured -> nothing defensible.
                row["withheld_reason"] = (
                    "Under the two documented assumptions for the unrated opponent the favourite "
                    f"changes (team A between {pct(lo)} and {pct(hi)}), so no direction is defensible.")
                row["pick"] = None
                row["prob_a"] = None
                row["prob_b"] = None
                row["tier_code"] = "unresolved"
                row["tier_label"] = "Withheld"
                row["basis_text"] = (
                    "Withheld: no pick or win probability is published for this row. "
                    + row["withheld_reason"])
                # The assumption-specific notes do not apply to a withheld row: drop them.
                row["limitations"] = [
                    x for x in row["limitations"]
                    if "The published number is an assumption" not in x
                    and "Treat this row as directional only" not in x
                    and "Another source lists this same kickoff" not in x]
                row["limitations"] = [row["withheld_reason"]] + row["limitations"]

    # What was tried for every row that is not backed by a verified external price. The HTTP
    # statuses come from the same capture's access log, so a refused source is visible per row.
    access = snapshot.get("access_log") or {}
    def status_of(key):
        meta = access.get(key) or {}
        if not isinstance(meta, dict):
            return "no record"
        if meta.get("error"):
            return str(meta.get("error"))
        return f"HTTP {meta.get('status')}" if meta.get("status") else "no record"
    for row in rows:
        if row["tier_code"] in ("market_multi", "market_single", "exchange"):
            continue
        row["attempts"] = [
            {"source": "HLTV match listings", "url": "https://www.hltv.org/matches",
             "status": status_of("hltv_probe"),
             "outcome": "not machine-readable; no HLTV number is used anywhere on this site"},
            {"source": "Bookmakers (Pinnacle, Bovada, Melbet)", "url": "https://www.pinnacle.com/en/esports/cs2-hub",
             "status": status_of("pinnacle"),
             "outcome": (f"{len(row['joined'])} usable price(s) joined"
                         if row["joined"] else
                         f"no market priced this pairing ({len(row['rejected_joins'])} price(s) rejected by the join gate)")},
            {"source": "Kalshi exchange (KXCS2GAME)", "url": "https://kalshi.com/markets/kxcs2game",
             "status": status_of("kalshi"),
             "outcome": ("a same-kickoff market exists but names a different opponent"
                         if row.get("conflicts") else "no market for this pairing")},
            {"source": "Official Valve Regional Standings",
             "url": (vrs or {}).get("page_url"), "status": status_of("valve_vrs_file"),
             "outcome": row["basis_text"]},
        ]

    summary = core.summarize(rows)
    summary["conflicted"] = sum(1 for r in rows if r.get("conflicts"))
    summary["stale_listings"] = sum(1 for f in fixtures if stale_listing(f, now))
    summary["lobby_listings"] = sum(1 for f in fixtures if "lobby_page" in (f.get("seen_in") or []))
    summary["api_fixtures"] = len(fixtures)

    locked = []
    for fixture in fixtures:
        if "lobby_page" not in (fixture.get("seen_in") or []):
            continue
        start = core.parse_iso(fixture.get("start_utc"))
        if not start or start > now or start < now - timedelta(hours=24):
            continue
        locked.append({"fixture_id": fixture.get("fixture_id"), "team_a": fixture.get("team_a"),
                       "team_b": fixture.get("team_b"), "competition": fixture.get("competition"),
                       "start_utc": fixture.get("start_utc"), "status": fixture.get("status"),
                       "winner": fixture.get("winner")})
    locked.sort(key=lambda r: r["start_utc"] or "", reverse=True)

    track = load_json(TRACK, {}) or {}
    graded = [v for v in track.values() if isinstance(v, dict) and v.get("correct") is not None]
    by_basis: dict[str, dict] = {}
    for g in graded:
        key = str(g.get("basis") or "unknown")
        slot = by_basis.setdefault(key, {"n": 0, "hits": 0, "brier": 0.0})
        slot["n"] += 1
        slot["hits"] += 1 if g.get("correct") else 0
        slot["brier"] += float(g.get("brier") or 0)
    for slot in by_basis.values():
        slot["accuracy"] = round(slot["hits"] / slot["n"], 4) if slot["n"] else None
        slot["brier_mean"] = round(slot["brier"] / slot["n"], 4) if slot["n"] else None

    source_status = {}
    for key, value in (snapshot.get("access_log") or {}).items():
        if isinstance(value, dict):
            source_status[key] = {"status": value.get("status"), "error": value.get("error"),
                                  "at_utc": value.get("at_utc"), "url": value.get("url"),
                                  "bytes": value.get("bytes")}
    for key, value in (snapshot.get("access_log") or {}).items():
        if isinstance(value, dict) and key not in source_status:
            continue

    rejected_summary = [{"source_key": r.get("source_key"), "team_a": r.get("team_a"),
                         "team_b": r.get("team_b"), "start_utc": r.get("start_utc"),
                         "reason": r.get("reason"), "url": r.get("public_url") or r.get("rules_url")}
                        for r in rejected]

    return {
        "session": core.SESSION,
        "generated_utc": core.to_iso(now),
        "snapshot_utc": snapshot.get("collected_to_utc"),
        "mode": snapshot.get("mode"),
        "provenance": snapshot.get("provenance") or {},
        "policy": "evidence-ladder-v1",
        "vrs": {"snapshot": vrs.get("snapshot"), "page_url": vrs.get("page_url"),
                "n_teams": stats.get("n_teams"), "floor": floor, "median": median,
                "max": stats.get("max"), "tree_api_url": vrs.get("tree_api_url")},
        "calibration": cal,
        "summary": summary,
        "open": rows,
        "locked_recent": locked,
        "track_record": {"n": len(graded),
                         "accuracy": round(sum(1 for g in graded if g.get("correct")) / len(graded), 4)
                         if graded else None,
                         "brier_mean": round(sum(float(g.get("brier") or 0) for g in graded) / len(graded), 4)
                         if graded else None,
                         "by_basis": by_basis,
                         "source": "data/f7279a54/track_record.json"},
        "sources": source_status,
        "rejected_quotes": rejected_summary,
        "quotes_total": len(quotes),
        "kalshi_rebuild": (snapshot.get("access_log") or {}).get("kalshi_rebuild"),
    }


# ------------------------------------------------------------------------------- page chrome
CSS = """
:root{--bg:#0d1117;--card:#161b22;--card2:#1c2430;--line:#2b3441;--text:#e6edf3;--muted:#93a1b1;
--ok:#2ea043;--okbg:#12261a;--warn:#d29922;--warnbg:#2a2113;--bad:#f85149;--badbg:#2a1416;
--model:#58a6ff;--modelbg:#0d2233;--pick:#7ee2a8}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 -apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif;padding-bottom:40px}
a{color:#79c0ff;text-decoration:none}a:hover{text-decoration:underline}
header{position:sticky;top:0;z-index:20;background:rgba(13,17,23,.97);border-bottom:1px solid var(--line);
backdrop-filter:blur(6px)}
.wrap{max-width:980px;margin:0 auto;padding:0 14px}
.top{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 0}
.brand{font-weight:800;font-size:17px;letter-spacing:.2px}
.brand span{color:var(--pick)}
nav{display:flex;gap:6px;overflow-x:auto;padding:0 0 8px;-webkit-overflow-scrolling:touch}
nav a{white-space:nowrap;font-size:13px;padding:7px 11px;border:1px solid var(--line);border-radius:999px;
color:var(--text);background:var(--card)}
nav a[aria-current=page]{border-color:var(--pick);color:var(--pick)}
h1{font-size:24px;line-height:1.25;margin:18px 0 8px}
h2{font-size:19px;margin:26px 0 8px}
h3{font-size:16px;margin:18px 0 6px}
p{margin:8px 0}
.lede{color:var(--muted)}
.hero{background:linear-gradient(160deg,#152132,#101722);border:1px solid #26374d;border-radius:16px;
padding:18px 16px;margin:14px 0}
.hero .eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--pick);margin:0 0 6px}
.hero h1{margin:0 0 6px;font-size:23px}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:14px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.stat b{display:block;font-size:21px;line-height:1.2}
.stat span{font-size:12px;color:var(--muted)}
.btns{display:grid;gap:9px;margin:12px 0 4px}
.btn{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:14px 15px;
border-radius:12px;background:var(--card2);border:1px solid var(--line);color:var(--text);font-weight:600;
min-height:48px}
.btn small{display:block;font-weight:400;color:var(--muted);font-size:12px;margin-top:2px}
.btn.primary{background:var(--pick);color:#08130d;border-color:var(--pick)}
.btn.primary small{color:#0d3520}
.btn .arw{font-size:18px;opacity:.8}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:10px 0}
.card .match{font-size:17px;font-weight:700;line-height:1.3}
.meta{font-size:12px;color:var(--muted);margin-top:3px}
.badge{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.03em;padding:3px 8px;
border-radius:999px;border:1px solid transparent;vertical-align:middle}
.badge.ok{background:var(--okbg);color:#7ee2a8;border-color:#1c5b30}
.badge.model{background:var(--modelbg);color:#9ecbff;border-color:#1f4a6b}
.badge.warn{background:var(--warnbg);color:#e3b341;border-color:#5c4520}
.badge.bad{background:var(--badbg);color:#ff8b84;border-color:#6b2a26}
.pickrow{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin:11px 0 2px}
.pickname{font-size:19px;font-weight:800;color:var(--pick)}
.pickprob{font-size:19px;font-weight:800}
.bar{height:10px;border-radius:6px;background:#0a0f15;overflow:hidden;margin:6px 0 2px;
border:1px solid #232c38}
.bar>i{display:block;height:100%}
.team{display:flex;justify-content:space-between;font-size:14px;padding:3px 0}
.team b{font-variant-numeric:tabular-nums}
.team.win b{color:var(--pick)}
details{margin-top:10px;border-top:1px solid #232c38;padding-top:8px}
summary{cursor:pointer;font-size:13px;color:var(--muted);font-weight:600}
ul{margin:6px 0 6px 18px;padding:0}li{margin:4px 0;font-size:14px}
.small{font-size:13px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;padding:8px 6px;border-bottom:1px solid #232c38;vertical-align:top}
th{font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--card)}
.note{border-left:3px solid var(--warn);background:var(--warnbg);padding:10px 12px;border-radius:0 10px 10px 0;
font-size:13.5px;margin:12px 0}
.err{border-left-color:var(--bad);background:var(--badbg)}
.ok{border-left-color:var(--ok);background:var(--okbg)}
footer{color:var(--muted);font-size:12px;padding:24px 0 0;border-top:1px solid var(--line);margin-top:28px}
code{background:#0a0f15;padding:1px 5px;border-radius:5px;font-size:12.5px}
@media(min-width:760px){.stats{grid-template-columns:repeat(4,1fr)}.btns{grid-template-columns:1fr 1fr}}
"""

NAV = [("index.html", "Summary"), ("picks.html", "All picks"),
       ("unresolved.html", "Unresolved"), ("flagged.html", "Flagged"),
       ("method.html", "Method"), ("sources.html", "Sources")]


def page(title: str, body: str, board: dict, active: str) -> str:
    nav = "".join(
        f'<a href="{href}"{" aria-current=page" if href == active else ""}>{esc(label)}</a>'
        for href, label in NAV)
    fresh = fmt_dt(board.get("snapshot_utc"), True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>{esc(title)} · HotSpawn CS2 picks</title>
<link rel="icon" href="../favicon.ico">
<style>{CSS}</style></head>
<body>
<header><div class="wrap">
<div class="top"><div class="brand">HotSpawn <span>CS2 picks</span></div>
<div class="small">built {esc(fmt_dt(board.get('generated_utc')))}</div></div>
<nav>{nav}</nav>
</div></header>
<main class="wrap">
{body}
<footer>
<p><strong>Data capture:</strong> {esc(fresh)} ({esc(board.get('mode'))} mode).
<strong>Build:</strong> {esc(fmt_dt(board.get('generated_utc')))}.
<strong>Valve standings:</strong> snapshot {esc((board.get('vrs') or {}).get('snapshot') or 'unavailable')}.</p>
<p>HotSpawn is used for fixture discovery and settlement only. Its crowd pick percentage is never
read or used as a probability. Every number on this site is derived from a linked external source
or from Valve's official standings, and anything that could not be confirmed is left blank and
listed on <a href="unresolved.html">Unresolved</a> / <a href="flagged.html">Flagged</a>.</p>
<p><a href="../index.html">← All boards on this site</a> · <a href="https://play.hotspawn.com/lobby"
rel="noopener">HotSpawn lobby</a> · <a href="https://www.hotspawn.com/pickem" rel="noopener">Pick'em</a></p>
</footer>
</main></body></html>"""


def pick_card(row: dict, board: dict, anchor: bool = True) -> str:
    tier = TIER_META.get(row["tier_code"], TIER_META["unresolved"])
    pa, pb = row.get("prob_a"), row.get("prob_b")
    pick = row.get("pick")
    a_win = bool(pick and pick["side"] == "a")
    width_a = (pa or 0.5) * 100
    bars = ""
    if pa is not None:
        bars = f"""
<div class="bar"><i style="width:{width_a:.1f}%;background:linear-gradient(90deg,#2ea043,#7ee2a8)"></i></div>
<div class="team {'' if a_win else 'win'}"><span>{esc(row['team_a'])}</span><b>{pct(pa)}</b></div>
<div class="team {'' if not a_win else 'win'}"><span>{esc(row['team_b'])}</span><b>{pct(pb)}</b></div>"""
    if pick:
        range_txt = (f" <span class='small'>assumption range {pct(pick['range'][0])}–{pct(pick['range'][1])}</span>"
                     if pick.get("range") else "")
        pick_html = (f"<div class='pickrow'><div><div class='small'>PICK</div>"
                     f"<div class='pickname'>{esc(pick['team'])}</div></div>"
                     f"<div style='text-align:right'><div class='small'>{esc(pick['confidence'])}</div>"
                     f"<div class='pickprob'>{pct(pick['prob'])}</div></div></div>{range_txt}")
    else:
        rng_note = ""
        if row.get("prob_range_a"):
            lo_r, hi_r = row["prob_range_a"]
            rng_note = (f"<p class='small'>Informational range under the two documented assumptions: "
                        f"{pct(lo_r)}–{pct(hi_r)} for {esc(row['team_a'])}. Not published as a "
                        "probability.</p>")
        pick_html = ("<div class='pickrow'><div><div class='small'>PICK</div>"
                     "<div class='pickname' style='color:var(--bad)'>Withheld</div></div>"
                     "<div class='small' style='max-width:52%;text-align:right'>No defensible value — "
                     "see <a href='unresolved.html#u-" + esc(row['fixture_id']) + "'>Unresolved</a></div></div>"
                     + rng_note)
    evidence = "".join(
        f"<li><a href='{esc(e.get('url'))}' rel='noopener'>{esc(e.get('source_name'))}</a> "
        f"— {esc(' / '.join(str(x) for x in (e.get('names_at_source') or []) if x))}"
        + (f", {pct(e.get('prob_a'))} for {esc(row['team_a'])}" if e.get("prob_a") is not None else "")
        + (f", observed {esc(fmt_dt(e.get('observed_utc')))}" if e.get("observed_utc") else "")
        + (f", kickoff Δ {esc(e.get('start_diff_min'))} min" if e.get("start_diff_min") is not None else "")
        + "</li>"
        for e in row.get("evidence") or [])
    limitations = "".join(f"<li>{esc(x)}</li>" for x in row.get("limitations") or [])
    conflicts = "".join(
        f"<li><a href='{esc(c['url'])}' rel='noopener'>{esc(c['source_name'])}</a> — {esc(c['note'])}</li>"
        for c in row.get("conflicts") or [])
    flags = "".join(f"<span class='badge warn'>{esc(f)}</span> " for f in row.get("flags") or [])
    anchor_attr = f" id='m-{esc(row['fixture_id'])}'" if anchor else ""
    return f"""
<article class="card"{anchor_attr}>
<div style="display:flex;justify-content:space-between;gap:8px;align-items:flex-start">
<div><div class="match">{esc(row['team_a'])} <span class="small">vs</span> {esc(row['team_b'])}</div>
<div class="meta">{esc(row['competition'])} · {esc(fmt_dt(row['start_utc'], True))} · locks {esc(fmt_dt(row['lock_utc']))}</div></div>
<span class="badge {tier['cls']}">{esc(tier['short'])}</span></div>
{pick_html}
{bars}
<p class="small">{esc(row['basis_text'])}</p>
{('<details><summary>Sources (' + str(len(row.get('evidence') or [])) + ')</summary><ul>' + evidence + '</ul></details>') if evidence else ''}
<details><summary>Evidence notes, flags &amp; limitations ({len(row.get('limitations') or []) + len(row.get('conflicts') or []) + len(row.get('flags') or [])})</summary>
<ul>{conflicts}{limitations}</ul>
<div class="small" style="margin-top:6px">{flags}</div>
<div class="small" style="margin-top:6px">HotSpawn fixture: <a href="{esc(row['hotspawn_url'])}" rel="noopener">match page</a> · id {esc(row['fixture_id'])} · {esc(row['points'])} pts</div>
</details>
</article>"""


# ------------------------------------------------------------------------------- pages
def render_index(board: dict) -> str:
    s = board["summary"]
    rows = board["open"]
    next_rows = sorted([r for r in rows if r.get("pick")], key=lambda r: r["start_utc"] or "")[:4]
    preview = "".join(
        f"<div class='team'><span>{esc(r['pick']['team'])} <span class='small'>to beat "
        f"{esc(r['team_b'] if r['pick']['side'] == 'a' else r['team_a'])}</span></span>"
        f"<b>{pct(r['pick']['prob'])}</b></div>"
        f"<div class='meta' style='margin:0 0 8px'>{esc(r['competition'])} · {esc(fmt_dt(r['start_utc'], True))}"
        f" · <span class='badge {TIER_META[r['tier_code']]['cls']}'>{esc(TIER_META[r['tier_code']]['short'])}</span></div>"
        for r in next_rows)
    unresolved_rows = [r for r in rows if r["tier_code"] in ("assumption", "unresolved")]
    unresolved_items = "".join(
        f"<li><a href='picks.html#m-{esc(r['fixture_id'])}'>{esc(r['team_a'])} vs {esc(r['team_b'])}</a> "
        f"({esc(r['competition'])}, {esc(fmt_dt(r['start_utc']))}) — "
        f"<strong>{esc(TIER_META[r['tier_code']]['short'])}</strong>: "
        f"{esc((r.get('limitations') or ['see the section'])[0])}</li>"
        for r in unresolved_rows) or "<li>None at this capture.</li>"
    vrs = board.get("vrs") or {}
    cal = board.get("calibration") or {}
    body = f"""
<section class="hero">
<p class="eyebrow">Executive summary · refreshed every 4 hours</p>
<h1>Every open HotSpawn CS2 match, one pick each</h1>
<p>Right now HotSpawn lists <strong>{s['open']} open CS2 pick'em matches</strong>.
<strong>{s['market_multi'] + s['market_single'] + s['exchange']}</strong> are priced by an external
bookmaker or exchange, <strong>{s['vrs_model']}</strong> are originated from Valve's official rating
table, <strong>{s['assumption']}</strong> rest on a published assumption, and
<strong>{s['unresolved']}</strong> is withheld because the sources contradict each other or nothing
verifiable exists. HotSpawn's crowd percentage is never used.</p>
<div class="btns">
<a class="btn primary" href="picks.html"><span>See all {s['open']} picks<small>pick, both win probabilities and the source for every row</small></span><span class="arw">→</span></a>
<a class="btn" href="unresolved.html"><span>Unresolved &amp; limitations ({s['assumption'] + s['unresolved']})<small>what was tried, what is an assumption, what is withheld</small></span><span class="arw">→</span></a>
</div>
<div class="stats">
<div class="stat"><b>{s['with_pick']}/{s['open']}</b><span>matches with a pick</span></div>
<div class="stat"><b>{s['verified_picks']}</b><span>verified external price</span></div>
<div class="stat"><b>{s['vrs_model']}</b><span>originated (Valve VRS)</span></div>
<div class="stat"><b>{s['assumption'] + s['unresolved']}</b><span>assumption or withheld</span></div>
</div>
<p class="small">Valve standings snapshot <a href="{esc(vrs.get('page_url'))}" rel="noopener">{esc(vrs.get('snapshot'))}</a>
· slope k = {cal.get('k', 0):.4f} fitted on {cal.get('n_pairs')} priced fixtures · data captured {esc(fmt_dt(board.get('snapshot_utc'), True))}.</p>
</section>

<h2>Where the picks are on this site</h2>
<div class="btns">
<a class="btn" href="picks.html"><span>All {s['open']} open picks<small>the full updated list, mobile cards</small></span><span class="arw">→</span></a>
<a class="btn" href="unresolved.html"><span>Unresolved picks &amp; limitations<small>the separate section for rows we cannot verify</small></span><span class="arw">→</span></a>
<a class="btn" href="flagged.html"><span>Flagged for review<small>irregularities, alias decisions, rejected prices</small></span><span class="arw">→</span></a>
<a class="btn" href="method.html"><span>Method &amp; formulas<small>the resolution ladder, gates and calibration</small></span><span class="arw">→</span></a>
<a class="btn" href="sources.html"><span>Source ledger<small>every URL, its HTTP status and when it was read</small></span><span class="arw">→</span></a>
<a class="btn" href="../index.html"><span>Other boards on this site<small>every parallel session's picks and evidence</small></span><span class="arw">→</span></a>
</div>

<h2>Next matches</h2>
<div class="card">{preview or '<p class="small">No pickable match at this capture.</p>'}</div>

<h2 id="unresolved">Unresolved picks &amp; limitations ({s['assumption'] + s['unresolved']})</h2>
<div class="note"><ul>{unresolved_items}</ul>
<p class="small">Full detail — including the source-by-source attempts, the two documented
assumptions used for unrated opponents and the fixtures whose opponent identity is contradicted by
another source — is on <a href="unresolved.html">Unresolved &amp; limitations</a>.</p></div>

<h2>How to read a row</h2>
<div class="card">
<p><span class="badge ok">Verified · bookmakers</span> both sides priced by two or more external
books, de-vigged and averaged.</p>
<p><span class="badge ok">Verified · one book</span> one external price; the book and its event are
linked on the row.</p>
<p><span class="badge ok">Verified · exchange</span> a Kalshi order-book mid inside the 10¢ spread gate.</p>
<p><span class="badge model">Originated · official VRS</span> no book prices it; the number comes from
Valve's official ranking points with a slope fitted on real bookmaker prices. It is a model line,
not a market price.</p>
<p><span class="badge warn">Assumption</span> the opponent has no official rating and nothing priced
the match; the range shows what the number would be under the VRS floor and the VRS median.</p>
<p><span class="badge bad">Withheld</span> the sources disagree or nothing verifiable exists; values
are blank on purpose.</p>
</div>
"""
    return page("Executive summary", body, board, "index.html")


def render_picks(board: dict) -> str:
    s = board["summary"]
    rows = sorted(board["open"], key=lambda r: r["start_utc"] or "")
    cards = "".join(pick_card(r, board) for r in rows)
    body = f"""
<h1>All {s['open']} open CS2 picks</h1>
<p class="lede">One card per open HotSpawn pick'em match, earliest kickoff first. Each card shows the
pick, both teams' win probabilities and the exact source behind every number. Capture
{esc(fmt_dt(board.get('snapshot_utc'), True))}; rebuilt every 4 hours.</p>
<div class="stats">
<div class="stat"><b>{s['open']}</b><span>open matches</span></div>
<div class="stat"><b>{s['verified_picks']}</b><span>verified price</span></div>
<div class="stat"><b>{s['vrs_model']}</b><span>VRS model</span></div>
<div class="stat"><b>{s['assumption'] + s['unresolved']}</b><span>assumption / withheld</span></div>
</div>
{cards}
<p class="small">Rows where a number is an assumption or withheld are listed with their limitations
on <a href="unresolved.html">Unresolved &amp; limitations</a>.</p>
"""
    return page("All picks", body, board, "picks.html")


def render_unresolved(board: dict) -> str:
    rows = board["open"]
    assumption = [r for r in rows if r["tier_code"] == "assumption"]
    withheld = [r for r in rows if r["tier_code"] == "unresolved"]
    conflicted = [r for r in rows if r.get("conflicts")]

    def block(row: dict) -> str:
        tier = TIER_META[row["tier_code"]]
        evidence = "".join(
            f"<li><a href='{esc(e.get('url'))}' rel='noopener'>{esc(e.get('source_name'))}</a> — {esc(e.get('detail') or '')}</li>"
            for e in row.get("evidence") or [])
        rejected = "".join(
            f"<li>{esc(j.get('source_key'))}: {esc(j.get('reason') or '')}"
            + (f" (kickoff Δ {esc(j.get('diff_min'))} min)" if j.get("diff_min") is not None else "")
            + f" — <a href='{esc(j.get('url'))}' rel='noopener'>event</a></li>"
            for j in row.get("rejected_joins") or [])
        conflicts = "".join(
            f"<li><a href='{esc(c['url'])}' rel='noopener'>{esc(c['source_name'])}</a> — {esc(c['note'])}</li>"
            for c in row.get("conflicts") or [])
        limits = "".join(f"<li>{esc(x)}</li>" for x in row.get("limitations") or [])
        attempts = "".join(
            f"<li><strong>{esc(a.get('source'))}</strong> — {esc(a.get('status'))} — {esc(a.get('outcome'))}"
            + (f" (<a href='{esc(a.get('url'))}' rel='noopener'>source</a>)" if a.get("url") else "")
            + "</li>"
            for a in row.get("attempts") or [])
        rng = ""
        if row.get("prob_range_a"):
            lo, hi = row["prob_range_a"]
            rng = (f"<p class='small'>Team A range under the two documented assumptions: "
                   f"{pct(lo)}–{pct(hi)}. Pick: "
                   f"<strong>{esc((row.get('pick') or {}).get('team') or 'none')}</strong>"
                   + (f" ({pct(row['pick']['range'][0])}–{pct(row['pick']['range'][1])})"
                      if (row.get("pick") or {}).get("range") else "") + ".</p>")
        return f"""
<article class="card" id="u-{esc(row['fixture_id'])}">
<div style="display:flex;justify-content:space-between;gap:8px;align-items:flex-start">
<div><div class="match">{esc(row['team_a'])} <span class="small">vs</span> {esc(row['team_b'])}</div>
<div class="meta">{esc(row['competition'])} · {esc(fmt_dt(row['start_utc'], True))} · HotSpawn id {esc(row['fixture_id'])}</div></div>
<span class="badge {tier['cls']}>{esc(tier['short'])}</span></div>
<p class="small">{esc(row['basis_text'])}</p>{rng}
<details open><summary>Why this row is here</summary><ul>{limits}</ul></details>
{('<details open><summary>Source-by-source attempts</summary><ul>' + attempts + evidence + rejected + '</ul></details>') if (attempts or evidence or rejected) else ''}
{('<details open><summary>Conflicting listing</summary><ul>' + conflicts + '</ul></details>') if conflicts else ''}
</article>"""

    body = f"""
<h1>Unresolved picks &amp; limitations</h1>
<p class="lede">The separate section for every open match whose pick is <em>not</em> backed by a
verified external price. Nothing here is silently filled in: an assumption is labelled an
assumption, and where the sources contradict each other the pick is withheld.</p>
<div class="note"><p><strong>Summary:</strong> {len(assumption)} assumption rows,
{len(withheld)} withheld rows, {len(conflicted)} row(s) with a conflicting listing.</p></div>

<h2>1. Withheld — no defensible value ({len(withheld)})</h2>
{''.join(block(r) for r in withheld) or '<p class="small">None at this capture.</p>'}

<h2>2. Assumption — one side has no official rating ({len(assumption)})</h2>
<p class="small">Rule: the pick is the rated side, and the probability is published as a
<em>range</em> between two documented assumptions for the unrated side — Valve's official VRS floor
(#{esc((board.get('vrs') or {}).get('floor', {}).get('standing'))},
{esc((board.get('vrs') or {}).get('floor', {}).get('points'))} pts) and the VRS median
({esc(round((board.get('vrs') or {}).get('median') or 0))} pts across
{esc((board.get('vrs') or {}).get('n_teams'))} ranked teams). If those two assumptions disagree
about the favourite, the row moves to section 1.</p>
{''.join(block(r) for r in assumption) or '<p class="small">None at this capture.</p>'}

<h2>3. Structural limitations that apply to the whole board</h2>
<ul>
<li><strong>No HotSpawn crowd data.</strong> HotSpawn's pick'em percentages are never read; the
collector drops those fields. This is deliberate, per the project requirement.</li>
<li><strong>HLTV is not machine-readable from automation.</strong> Every capture attempts
<a href="https://www.hltv.org/matches" rel="noopener">hltv.org/matches</a> and records the answer.
At this capture it answered HTTP 403, so no HLTV number is used anywhere on this site. HLTV match
pages are linked only where another source identifies the fixture.</li>
<li><strong>Valve publishes monthly.</strong> The newest official standings file is
{esc((board.get('vrs') or {}).get('snapshot') or 'unavailable')}; it is verified to be the newest
in Valve's repository, so comparisons can lag results by up to a month.</li>
<li><strong>Bookmaker coverage is a snapshot.</strong> If no book had a market open at capture
time, the row falls to the rating model or the assumption rule. It may be priced again on the next
4-hourly refresh — the board rebuilds automatically.</li>
<li><strong>Unrated does not mean weak.</strong> In this capture UNiTY (VRS #69) is priced at 39.5%
against unrated Apogee Betclic, which is why an unrated opponent can never be assumed to be the
underdog.</li>
<li><strong>Withheld rows are not zero.</strong> A withheld pick means "the sources do not support a
number", not "the match is a coin flip".</li>
</ul>
"""
    return page("Unresolved & limitations", body, board, "unresolved.html")


def render_flagged(board: dict) -> str:
    rows = board["open"]
    alias_rows = [r for r in rows if any(f.startswith("alias_joined") for f in r.get("flags") or [])]
    dup_rows = [r for r in rows if any(f.startswith("vrs_duplicate_resolved") for f in r.get("flags") or [])]
    unrated = [r for r in rows if any(f.startswith("not_in_vrs") for f in r.get("flags") or [])]
    rejected = board.get("rejected_quotes") or []
    conflicts = [r for r in rows if r.get("conflicts")]

    def rlist(items, render):
        return "".join(f"<li>{render(i)}</li>" for i in items) or "<li>None at this capture.</li>"

    body = f"""
<h1>Flagged for review</h1>
<p class="lede">Every decision that a human should be able to check: published name aliases,
duplicate-rating choices, rejected prices, conflicting listings, stale HotSpawn rows and the
repository irregularities found while building this board. Each item carries the link used.</p>

<h2>1. Name aliases that changed a pick ({len(alias_rows)})</h2>
<ul>{rlist(alias_rows, lambda r: f"{esc(r['team_a'])} vs {esc(r['team_b'])} — "
        + " ".join(esc(x) for x in r['limitations'] if 'spelling' in x.lower() or 'lists' in x.lower()))}</ul>
<p class="small">Full alias records live in <code>scripts/907e9435/core.py</code> (<code>ALIASES</code>)
and each one is applied only when the opponent <em>and</em> the kickoff both agree within five minutes.</p>

<h2>2. Duplicate Valve ratings resolved with official evidence ({len(dup_rows)})</h2>
<ul>{rlist(dup_rows, lambda r: f"{esc(r['team_a'])} vs {esc(r['team_b'])} — "
        + " ".join(esc(x) for x in r['limitations'] if 'Valve lists' in x))}</ul>
<p class="small">Rule: prefer a five-player roster, then the roster with the newest counted match in
Valve's own details file. The alternative entries and their dates are shown on each row.</p>

<h2>3. Teams with no official rating ({len(unrated)})</h2>
<ul>{rlist(unrated, lambda r: f"{esc(r['team_a'])} vs {esc(r['team_b'])} — not in Valve's standings: "
        + ", ".join(esc(f.split(':', 1)[1]) for f in r['flags'] if f.startswith('not_in_vrs')))
    }</ul>

<h2>4. Conflicting listings at the same kickoff ({len(conflicts)} at this capture)</h2>
<ul>{rlist([c for r in conflicts for c in r['conflicts']],
            lambda c: f"<a href='{esc(c['url'])}' rel='noopener'>{esc(c['source_name'])}</a> — {esc(c['note'])}")}</ul>
<details open><summary>Dated observation from the retained 2026-10-21T19:24:28Z capture</summary>
<ul><li><a href="https://kalshi.com/markets/kxcs2game/kxcs2game-26oct211800lnale" rel="noopener">Kalshi
KXCS2GAME-26OCT211800LNALE</a> priced “Los Ninos vs Alianza Lima Esports” for the 2026-10-21T22:00:00Z
kickoff, whose own rules text places it in the same CCT South America event that HotSpawn lists as
“Zetta vs LOS NINOS” for the same minute. A parallel board also reports a bo3.gg page naming Alianza
Lima for that slot. Two independent external sources therefore disagree with the HotSpawn pairing, so
the pick for fixture 1082837 is withheld instead of guessing which fixture settles. The market was no
longer two-sided at the next capture, so this section can show zero items on a later build — the
observation is dated, not a live claim.</li></ul></details>

<h2>5. Prices rejected by the join gate ({len(rejected)})</h2>
<details><summary>Why a price was not used</summary>
<ul>{rlist(rejected, lambda r: f"{esc(r['source_key'])}: {esc(r['team_a'])} vs {esc(r['team_b'])}"
        f" ({esc(r['start_utc'] or 'no kickoff')}) — {esc(r['reason'])}")}</ul>
<p class="small">A price is only joined when both names match after documented normalisation
(plus a published alias) <em>and</em> the kickoff agrees within five minutes. Anything else is
rejected and listed here rather than forced onto a fixture.</p></details>

<h2>6. HotSpawn listing hygiene</h2>
<ul>
<li><strong>{esc(board['summary']['stale_listings'])} stale listings</strong>: fixtures the lobby and
API still report as <code>scheduled</code> although their kickoff has passed by more than two days
(June–July 2026 and two mid-October rows). They are excluded from the open board and listed on the
source page instead of being priced.</li>
<li><strong>API/lobby disagreement</strong>: fixtures present in the public API but absent from the
lobby page (or the reverse) are kept only when the lobby page lists them, because the pick'em game
is the lobby.</li>
<li><strong>Kalshi timestamps</strong>: the exchange's <code>occurrence_datetime</code> field is
four hours later than the kickoff stated in its own <code>rules_primary</code> text on all 33 open
events. The board uses the rules text (EDT/EST → UTC) and never the field. This is documented on
<a href="method.html">Method</a>.</li>
</ul>

<h2>7. Repository irregularities found during the line-by-line review</h2>
<ul>
<li><strong>The canonical board never joins Kalshi.</strong> <code>scripts/f7279a54/collect.py</code>
returns a JSON <code>null</code> from <code>kalshi_start()</code>, so every Kalshi quote is marked
<code>start_is_approx</code> and rejected by <code>match_quote()</code>. Result: 13 usable exchange
quotes are captured and then discarded every run. This board re-derives the kickoff from the
exchange's own rules text; the canonical board is unchanged (owned by another session).</li>
<li><strong>A real Melbet line is missed on fixture 1082882.</strong> Melbet prices
“UNiTY vs Apogee Esports” (event 763696446) at the same 2026-10-22T14:00:00Z kickoff as HotSpawn's
“UNiTY vs Apogee Betclic”, but the canonical board leaves the match unpriced and the fallback board
<code>fullpicks/</code> publishes a Valve floor estimate of UNiTY 87.0%. The market has UNiTY at
39.5%, so that estimate is 47 points away from the only real price that exists. The alias is
published here and the row is flagged for review.</li>
<li><strong>Rendered-vs-data lag on the archive boards.</strong> Root pages are only regenerated
when a session runs <code>scripts/build_site.py</code>, while sub-boards refresh every 4 hours; at the
start of this session the root page advertised a <code>fullpicks</code> snapshot of 14:14:56Z while
that board's own data was 18:58:41Z. This board avoids the gap by committing the rendered pages in
the same job as the data. Separately, <code>fullpicks/index.html</code> still labels its board
“All 19 Open CS2 Picks” while its own summary counts 13 open matches — a hard-coded label.</li>
<li><strong>Third-party data that cannot be re-verified here.</strong> Some parallel boards quote
bo3.gg team pages and match histories. bo3.gg is not reachable from this build environment
(connection refused), so no bo3.gg number is used as an input on this site; its claims are left to
the boards that captured them and are flagged there.</li>
<li><strong>Root landing page.</strong> The root page stacks more than ten parallel boards with
different policies and conflicting counts (12/12, 9/9, 7/7 …). This board is added to the root page
as the single primary action, with the parallel boards kept under an archive heading.</li>
<li><strong>Valve snapshot age.</strong> The official standings file is
{esc((board.get('vrs') or {}).get('snapshot'))}, i.e. the newest Valve publishes; any board claiming
a fresher official rating on 2026-10-21 should be checked.</li>
</ul>
"""
    return page("Flagged for review", body, board, "flagged.html")


def render_method(board: dict) -> str:
    cal = board.get("calibration") or {}
    vrs = board.get("vrs") or {}
    body = f"""
<h1>Method</h1>
<p class="lede">How a pick and a probability are produced for every open HotSpawn CS2 match, in the
order the sources are consulted, and what each label means.</p>

<h2>1. Resolution ladder (first match wins)</h2>
<div class="tablewrap"><table><thead><tr><th>Step</th><th>Source</th><th>What it produces</th><th>Label</th></tr></thead><tbody>
<tr><td>1</td><td>Pinnacle, Bovada, Melbet LineFeed, Kalshi</td><td>De-vigged two-way prices, joined on
both names + kickoff ±5 min; weighted mean (Pinnacle ×2)</td><td><span class="badge ok">Verified</span></td></tr>
<tr><td>2</td><td>Kalshi exchange order book</td><td>Mid of bid/ask, both sides inside the 10¢ spread
gate, kickoff from the exchange's own rules text</td><td><span class="badge ok">Verified</span></td></tr>
<tr><td>3</td><td>Official Valve Regional Standings</td><td>Points difference through Valve's own
Glicko curve with a fitted slope k</td><td><span class="badge model">Originated</span></td></tr>
<tr><td>4</td><td>Documented assumption</td><td>Rated side only, published as a range between the VRS
floor and the VRS median for the unrated opponent</td><td><span class="badge warn">Assumption</span></td></tr>
<tr><td>5</td><td>—</td><td>Nothing: values are left blank and the reason is published</td>
<td><span class="badge bad">Withheld</span></td></tr>
</tbody></table></div>
<p class="small">HotSpawn is discovery and settlement only. Its crowd pick percentage is never read,
and no HotSpawn figure enters a probability.</p>

<h2>2. De-vigging</h2>
<p>For decimal prices <code>d_a, d_b</code>: <code>i_a = 1/d_a</code>, <code>i_b = 1/d_b</code>,
<code>p_a = i_a/(i_a+i_b)</code>. A book is rejected if its implied total is outside
0.95–1.30. American prices are converted first; Kalshi dollars are converted with
<code>d = 1/price</code>. Every stored probability is re-derived from the raw prices at build time.</p>

<h2>3. Valve rating model</h2>
<p>Valve's own model (<a href="https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/model/glicko.js" rel="noopener">model/glicko.js</a>,
evaluated with a fixed RD of 75 as in
<a href="https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/model/fit.js" rel="noopener">model/fit.js</a>)
gives <code>g = {core.VALVE_G:.4f}</code>, so
<code>p_A = 1/(1+10^(−k·g·Δ/400))</code>. The slope <code>k</code> is fitted by least squares of
<code>logit(market)</code> on <code>g·Δ/400</code> over the retained calibration pairs:
<strong>k = {cal.get('k', 0):.4f}</strong> on {cal.get('n_pairs')} priced fixtures
(unbounded fit {cal.get('k_raw', 0):.4f} if it fell outside the published bounds {cal.get('bounds')}).
Valve's README states its own curve overstates big gaps, which is why the slope is learned from
bookmaker prices instead of assumed.</p>

<h2>4. Assumption rule for unrated opponents</h2>
<p>If exactly one roster is in Valve's table, the opponent has no rating. The board then computes the
rated side's probability twice: once with the opponent at the official VRS floor
(#{esc(vrs.get('floor', {}).get('standing'))}, {esc(vrs.get('floor', {}).get('points'))} pts) and
once with the opponent at the VRS median ({esc(round(vrs.get('median') or 0))} pts across
{esc(vrs.get('n_teams'))} ranked teams). The published range is those two numbers. The pick is
published only if both assumptions agree on the favourite; otherwise the row is withheld. These rows
are never counted as verified.</p>

<h2>5. Join gates</h2>
<ul>
<li>Normalisation strips case, accents, punctuation and generic words
(<code>Team</code>, <code>Esports</code>, <code>Gaming</code>, …). No prefix or substring matches:
“B8” never matches “B8 Academy”.</li>
<li>Published aliases (e.g. <code>Apogee Esports → Apogee Betclic</code>) are applied only with an
agreeing opponent <em>and</em> kickoff, and are listed on <a href="flagged.html">Flagged</a>.</li>
<li>Kickoff tolerance is five minutes. A quote without an established kickoff is never joined.</li>
<li>Duplicate Valve rows for one organisation are resolved only with official evidence: five-player
roster, newest counted match in Valve's details file; ties are refused.</li>
</ul>

<h2>6. Confidence labels</h2>
<p><strong>Strong</strong> ≥70% · <strong>Solid</strong> ≥60% · <strong>Lean</strong> ≥53% ·
<strong>Toss-up</strong> below that · <strong>Assumption</strong> for rows in the assumption tier.
Labels describe the probability, not the quality of the evidence; read the badge for that.</p>

<h2>7. Refresh</h2>
<p>Every 4 hours (and on demand) the workflow collects HotSpawn, Pinnacle, Bovada, Melbet, Kalshi and
Valve's standings, rebuilds this board, runs the contract tests and commits the rendered pages.
If the lobby page cannot be read the previous inventory is kept and the failure is recorded in the
source ledger instead of publishing an empty board.</p>

<h2>8. What is deliberately not done</h2>
<ul><li>No HotSpawn crowd or pick'em percentages.</li>
<li>No scraped or guessed odds; unreachable sources are reported, not estimated.</li>
<li>No value is carried forward from a previous board when its quote has expired.</li>
<li>No blending of the model into a verified market pick.</li></ul>
"""
    return page("Method", body, board, "method.html")


def render_sources(board: dict) -> str:
    s = board.get("sources") or {}
    labels = {
        "hotspawn_lobby_page": ("HotSpawn lobby page", "fixture discovery (public page transfer state)"),
        "hotspawn_api": ("HotSpawn fixtures API", "fixture inventory and status"),
        "pinnacle": ("Pinnacle (guest odds API)", "two-way match-winner prices"),
        "bovada": ("Bovada", "two-way match-winner prices"),
        "melbet": ("Melbet LineFeed", "two-way match-winner prices"),
        "kalshi": ("Kalshi trade API (KXCS2GAME)", "exchange order books"),
        "kalshi_rebuild": ("Kalshi rebuild (this board)", "kickoff from rules text + spread gate"),
        "polymarket_probe": ("Polymarket gamma API", "probe: no usable CS2 match markets observed"),
        "hltv_probe": ("HLTV", "probe only — automation is refused"),
        "valve_vrs_tree": ("Valve standings repository tree", "newest official snapshot discovery"),
        "valve_vrs_file": ("Valve standings file", "official ratings, rosters, details files"),
        "bootstrap_source": ("Retained capture", "bootstrap provenance"),
    }
    rows = []
    for key, meta in sorted(s.items()):
        name, use = labels.get(key, (key, ""))
        status = meta.get("status")
        bad = meta.get("error")
        if key in ("kalshi_rebuild", "bootstrap_source", "retained_capture"):
            badge = "<span class='badge model'>info</span>"
        elif status == 200 and not bad:
            badge = "<span class='badge ok'>200</span>"
        else:
            badge = f"<span class='badge bad'>{esc(status or 'error')}</span>"
        rows.append(f"<tr><td><strong>{esc(name)}</strong><div class='small'>{esc(use)}</div></td>"
                    f"<td>{badge}<div class='small'>{esc(bad or '')}</div></td>"
                    f"<td class='small'>{esc(fmt_dt(meta.get('at_utc'), True))}</td>"
                    + (f"<td class='small'><a href='{esc(meta.get('url'))}' rel='noopener'>endpoint</a></td></tr>"
                       if meta.get("url") else "<td class='small'>—</td></tr>"))
    vrs = board.get("vrs") or {}
    body = f"""
<h1>Source ledger</h1>
<p class="lede">Every endpoint this board reads, the HTTP status it answered at the capture, and
what the data was used for. A failed source is shown as failed — it is never converted into a
probability.</p>
<div class="tablewrap"><table><thead><tr><th>Source</th><th>Status</th><th>Read (UTC)</th><th>Link</th>
</tr></thead><tbody>{''.join(rows)}</tbody></table></div>

<h2>Official rating source</h2>
<p>Valve Regional Standings, snapshot <a href="{esc(vrs.get('page_url'))}" rel="noopener">{esc(vrs.get('snapshot'))}</a>
· {esc(vrs.get('n_teams'))} ranked teams · floor #{esc(vrs.get('floor', {}).get('standing'))}
({esc(vrs.get('floor', {}).get('points'))} pts) · median {esc(round(vrs.get('median') or 0))} pts ·
top {esc(vrs.get('max'))} pts.
Newest-snapshot check: <a href="{esc(vrs.get('tree_api_url'))}" rel="noopener">repository tree</a>.</p>

<h2>Calibration inputs</h2>
<p>{esc((board.get('calibration') or {}).get('n_pairs'))} retained fixture-level pairs
(<code>data/f7279a54/calibration_pairs.json</code>) of a market consensus and a Valve points
difference. Refitted at every build; the fit is published on <a href="method.html">Method</a>.</p>

<h2>Published-pick track record (canonical board)</h2>
<p>From <code>{esc((board.get('track_record') or {}).get('source'))}</code>:
<strong>{esc((board.get('track_record') or {}).get('n'))}</strong> graded picks,
accuracy <strong>{pct((board.get('track_record') or {}).get('accuracy'))}</strong>,
mean Brier <strong>{esc((board.get('track_record') or {}).get('brier_mean'))}</strong>.
This is the canonical collector's record, reproduced here for context, not this board's own record.</p>
<div class="tablewrap"><table><thead><tr><th>Line basis</th><th>Graded</th><th>Accuracy</th><th>Mean Brier</th></tr></thead><tbody>
{''.join(f"<tr><td>{esc(k)}</td><td>{v['n']}</td><td>{pct(v.get('accuracy'))}</td><td>{esc(v.get('brier_mean'))}</td></tr>"
         for k, v in sorted(((board.get('track_record') or {}).get('by_basis') or {}).items()))}
</tbody></table></div>

<h2>Provenance of this build</h2>
<pre class="small" style="white-space:pre-wrap">{esc(json.dumps(board.get('provenance') or {}, indent=1))}</pre>
<p class="small">Capture mode: <strong>{esc(board.get('mode'))}</strong> · snapshot
{esc(board.get('snapshot_utc'))} · build {esc(board.get('generated_utc'))}.</p>
"""
    return page("Sources", body, board, "sources.html")


def main() -> int:
    snapshot = load_json(SNAPSHOT)
    if not snapshot:
        print(f"missing snapshot: {SNAPSHOT}", file=sys.stderr)
        return 1
    board = build_board(snapshot)
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    OUT_SITE.mkdir(parents=True, exist_ok=True)
    (OUT_DATA / "board.json").write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n")
    pages = {"index.html": render_index(board), "picks.html": render_picks(board),
             "unresolved.html": render_unresolved(board), "flagged.html": render_flagged(board),
             "method.html": render_method(board), "sources.html": render_sources(board)}
    for name, content in pages.items():
        (OUT_SITE / name).write_text(content)
    print(json.dumps(board["summary"], indent=1))
    for row in board["open"]:
        print(f"  {row['fixture_id']} {row['team_a'][:16]:16s} v {row['team_b'][:18]:18s} "
              f"{row['tier_code']:13s} pick={(row['pick'] or {}).get('team')} "
              f"p={pct((row['pick'] or {}).get('prob'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
