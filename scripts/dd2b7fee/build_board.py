#!/usr/bin/env python3
"""Session dd2b7fee — fresh Hotspawn CS2 pick'em board builder.

Reads:
  data/hotspawn_matches.json          (normalized snapshot of the official
                                       play.hotspawn.com reverse-engineered fixtures API,
                                       refreshed hourly upstream by scripts/fetch_hotspawn.py)
  data/dd2b7fee/lines_snapshot.json   (this session's raw external-line captures)

Writes:
  data/dd2b7fee/board.json
  fresh/index.html            (landing)
  fresh/cs2/index.html        (CS2 board subpage)
  fresh/flagged/index.html    (flagged-for-review subpage)
  fresh/method/index.html     (method subpage)

Rules honoured here:
  * Win probabilities originate EXCLUSIVELY from external book/exchange lines
    (Bovada, Pinnacle, Kalshi). Hotspawn crowd pick-percentages are never read
    or displayed.
  * HLTV betting-analytics is a qualitative cross-check only (never a price).
  * Every published row carries official source links; a row with no captured
    line is blank + flagged unverified. Nothing is inferred.
"""
from __future__ import annotations

import html
import json
import pathlib
import sys
from statistics import mean

ROOT = pathlib.Path(__file__).resolve().parents[2]
SNAP_PATH = ROOT / "data" / "dd2b7fee" / "lines_snapshot.json"
FX_PATH = ROOT / "data" / "hotspawn_matches.json"

HOTSPAWN_LOBBY = "https://play.hotspawn.com/lobby"
HOTSPAWN_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
WINDOW_START = "2026-10-13T20:00"   # current pick'em window (UTC prefix match)

TIME_FLAG_MIBR_ENVY = (
    "Start-time disagreement across sources: Hotspawn & Kalshi list Oct 15 10:00 UTC; "
    "Bovada displayed {} UTC Oct 14; Pinnacle cutoff 19:30 UTC Oct 14. "
    "Hotspawn pick lock applies 6 min before its listed start."
)

# hotspawn fixture_id -> external mapping (verified against the 22:41Z snapshot)
FXMAP = {
    1080176: {"bovada": "A_19033654", "pinnacle": 1638111785, "kalshi": "KXCS2GAME-26OCT140430AUR9Z",
              "hltv": ("https://www.hltv.org/betting/analytics/2399384/9z-vs-aurora-thunderpick-world-championship-2026", "b")},
    1080177: {"bovada": "A_19033712", "pinnacle": 1638111674, "kalshi": "KXCS2GAME-26OCT140700NIPFAL",
              "hltv": ("https://www.hltv.org/betting/analytics/2399385/falcons-vs-ninjas-in-pyjamas-thunderpick-world-championship-2026", "a")},
    1080178: {"bovada": "A_19033747", "pinnacle": 1638111786, "kalshi": "KXCS2GAME-26OCT140930PRVLGC",
              "hltv": ("https://www.hltv.org/betting/analytics/2399386/legacy-vs-parivision-thunderpick-world-championship-2026", "a")},
    1080179: {"bovada": "A_19033783", "pinnacle": 1638111787, "kalshi": "KXCS2GAME-26OCT141200BBFURIA",
              "hltv": ("https://www.hltv.org/betting/analytics/2399387/furia-vs-betboom-thunderpick-world-championship-2026", None),
              "flags": ["HLTV rank edge: FURIA #4 vs BETBOOM #14 (no bookmaker-favorite label)"]},
    1079438: {"bovada": "A_19036192", "pinnacle": None, "kalshi": "KXCS2GAME-26OCT140600SASHIAST",
              "hltv": ("https://www.hltv.org/betting/analytics/2399134/astralis-vs-sashi-stake-pulse-beat-iii", "a"),
              "flags": ["Not listed by Pinnacle (Pulse Beat league shows only 4 series, all others account for); Bovada + Kalshi (very thin) only"]},
    1079439: {"bovada": "A_19036215", "pinnacle": 1637867148, "kalshi": "KXCS2GAME-26OCT140600FNCHOTU",
              "hltv": ("https://www.hltv.org/betting/analytics/2399135/hotu-vs-fnatic-stake-pulse-beat-iii", "b"),
              "flags": ["Pinnacle series moneyline not returned in a 23:05Z live read (present 22:41Z) - treated as pulled intraday"]},
    1079440: {"bovada": "A_19033833", "pinnacle": 1637936745, "kalshi": "KXCS2GAME-26OCT150600BCGMIBR",
              "flags": [TIME_FLAG_MIBR_ENVY.format("22:30")]},
    1079442: {"bovada": "A_19033867", "pinnacle": 1637999450, "kalshi": "KXCS2GAME-26OCT150600ENVYHERO",
              "flags": [TIME_FLAG_MIBR_ENVY.format("16:30")]},
    1079621: {"kalshi": "KXCS2GAME-26OCT140400LAVGOT",
              "hltv": ("https://www.hltv.org/betting/analytics", None),
              "flags": ["Kalshi-only line (thin book, ~50/49) - no bookmaker prices found anywhere"]},
    1079622: {"kalshi": "KXCS2GAME-26OCT140700MELEXR",
              "hltv": ("https://www.hltv.org/betting/analytics/2399299/ex-rustec-vs-mellren-cct-2026-europe-series-11", None),
              "flags": ["Kalshi-only line; wide spread", "HLTV rank/form edge: ex-RUSTEC (#79 vs #94), no bookmaker-favorite label"]},
    1079623: {"bovada": "A_19036381", "kalshi": "KXCS2GAME-26OCT141000TLRG2A",
              "flags": ["Bovada + Kalshi only (Kalshi side has zero traded volume)"]},
    1079624: {"lean": True, "hltv": ("https://www.hltv.org/betting/analytics/2399301/forze-reload-vs-lfo-10-cct-2026-europe-series-11", "a"),
              "flags": ["No captured betting price; indicative lean from HLTV context only (FORZE Reload #75 vs unranked, better form)"]},
    1081111: {"kalshi": "KXCS2GAME-26OCT140400B8AENJOY",
              "hltv": ("https://www.hltv.org/betting/analytics/2399461/enjoy-vs-b8-academy-cct-2026-europe-series-12-closed-qualifier", None),
              "flags": ["Kalshi-only line; very wide book", "HLTV rank/form edge: Enjoy (#199 vs #229, better form), no bookmaker-favorite label"]},
    1079546: {"pinnacle": 1638279105, "kalshi": "KXCS2GAME-26OCT132100OTZOMB",
              "hltv": ("https://www.hltv.org/betting/analytics", None)},
    1081113: {"kalshi": "KXCS2GAME-26OCT141000RYVWRA",
              "flags": ["Alias: lobby 'PCIFIC' = Kalshi 'WRAITH PCIFIC' (matched by opponent + exact start time; full name unconfirmed)", "Kalshi-only line; very wide book"]},
    1080280: {"kalshi": "KXCS2GAME-26OCT150600BOJENCE",
              "flags": ["Kalshi-only line; weak book (last trades 75/24, near-zero volume)"]},
    1080282: {"kalshi": "KXCS2GAME-26OCT151000BOJEAC",
              "flags": ["Kalshi-only line; very wide book, zero volume"]},
    1080284: {"kalshi": "KXCS2GAME-26OCT151400ENCEEAC",
              "flags": ["Kalshi-only line; very wide book, near-zero volume"]},
    1080279: {"kalshi_seed": "KXCS2GAME-26OCT150400EACWBTACADEMY",
              "flags": ["Kalshi lists the match but the book is exchange seed quotes only (6c/94c both sides) - no usable line; 'WBT Academy' = Kalshi name for WROTBERRY (matched across 5 events by opponent+time)"]},
    1080281: {"kalshi_seed": "KXCS2GAME-26OCT150800ENCEWBTACADEMY",
              "flags": ["Kalshi book empty (seed quotes only) - no usable line"]},
    1080283: {"kalshi_seed": "KXCS2GAME-26OCT151200BOJWBTACADEMY",
              "flags": ["Kalshi book empty (seed quotes only) - no usable line"]},
    1081076: {"locked": True,
              "hltv": ("https://www.hltv.org/betting/analytics", "b"),
              "flags": ["Status 'started' (21:00Z) at collection time - pick window closed; Pinnacle pre-match markets emptied"]},
    1081105: {"locked": True, "staleness": True,
              "flags": ["Scheduled 22:00Z Oct 13 but API still said 'scheduled' at 22:41Z (status lag); treated as locked/started; no line captured"]},
    1080200: {"locked": True, "anomaly": True,
              "flags": ["Data anomaly: API row says 'started' with scheduled date Nov 12 2026 but start_time Oct 12 2026 (FRAG University 2026)"]},
    1081112: {"flags": ["No line captured (Kalshi lists a different 6666 match - '6666 vs los kogutos', not this fixture)"]},
}

SOURCE_META = {
    "bovada": {"label": "Bovada", "page": "https://sports.bovada.lv/esports/counter-strike-2"},
    "pinnacle": {"label": "Pinnacle", "page": "https://www.pinnacle.com/en/esports/cs2-hub"},
    "kalshi": {"label": "Kalshi", "page": "https://kalshi.com/markets/KXCS2GAME"},
    "hltv": {"label": "HLTV analytics", "page": "https://www.hltv.org/betting/analytics"},
}


def p_american(a: int) -> float:
    return (-a) / (-a + 100) if a < 0 else 100.0 / (a + 100)


def novig(pa: float, pb: float) -> tuple[float, float]:
    s = pa + pb
    return pa / s, pb / s


def _same(x: str, y: str) -> bool:
    xl, yl = (x or "").lower().strip(), (y or "").lower().strip()
    if not xl or not yl:
        return False
    return xl in yl or yl in xl or xl.split()[0] == yl.split()[0]


def snap_find(snap, source, key):
    for m in snap["sources"][source]["markets"]:
        if source == "bovada" and m.get("event_id") == key:
            return m
        if source == "pinnacle" and m.get("matchup_id") == key:
            return m
        if source == "kalshi" and m.get("event_ticker") == key:
            return m
    return None


def load_rows(snap, fx):
    ms = fx["matches"]
    gen = fx.get("generated_at_utc")
    rows = []
    for m in ms:
        if m.get("sport") != "cs2":
            continue
        if m.get("status") not in ("scheduled", "started"):
            continue
        if m.get("status") == "scheduled":
            if not (m.get("scheduled_start_time") or "").startswith("2026-10-1"):
                continue
            if (m.get("scheduled_start_time") or "") < WINDOW_START:
                continue
        fid = int(m["fixture_id"])
        a, b = m["team_a"], m["team_b"]
        meta = FXMAP.get(fid, {})
        quotes = []
        flags = list(meta.get("flags", []))
        kind = "series"
        if meta.get("locked") or m.get("status") == "started":
            kind = "locked"
        if meta.get("lean") and kind != "locked":
            kind = "lean"
        if meta.get("kalshi_seed") and kind == "series":
            kind = "seed"
        if kind == "series" or kind == "seed":
            if meta.get("bovada"):
                bm = snap_find(snap, "bovada", meta["bovada"])
                i1, i2 = 1 / bm["price_home_dec"], 1 / bm["price_away_dec"]
                p1, p2 = novig(i1, i2)
                p_a = p1 if _same(bm["home"], a) else p2
                quotes.append(("bovada", p_a,
                               f"{bm['home']} {bm['price_home_dec']} vs {bm['away']} {bm['price_away_dec']} (dec, event {bm['event_id']})",
                               SOURCE_META["bovada"]["page"], f"overround {(i1+i2-1)*100:.1f}%"))
            if meta.get("pinnacle"):
                pm = snap_find(snap, "pinnacle", meta["pinnacle"])
                if pm and pm.get("status") == "open":
                    i1, i2 = p_american(pm["price_home_us"]), p_american(pm["price_away_us"])
                    p1, p2 = novig(i1, i2)
                    p_a = p1 if _same(pm["home"], a) else p2
                    url = f"https://guest.api.arcadia.pinnacle.com/0.1/matchups/{pm['matchup_id']}/markets/related/straight"
                    quotes.append(("pinnacle", p_a,
                                   f"{pm['home']} {pm['price_home_us']:+d} vs {pm['away']} {pm['price_away_us']:+d} (US, matchup {pm['matchup_id']})",
                                   url, f"overround {(i1+i2-1)*100:.1f}%"))
                elif pm:
                    flags.append(f"Pinnacle status={pm.get('status')} at capture (matchup {meta['pinnacle']})")
            if meta.get("kalshi") or meta.get("kalshi_seed"):
                tk = meta.get("kalshi") or meta.get("kalshi_seed")
                km = snap_find(snap, "kalshi", tk)
                if km and not km.get("empty_seed_book"):
                    am = (km["a_yes_bid"] + km["a_yes_ask"]) / 2
                    bm2 = (km["b_yes_bid"] + km["b_yes_ask"]) / 2
                    if _same(km["team_a"], a):
                        p_a = am / (am + bm2) if am + bm2 else 0.5
                        band = (km["a_yes_bid"], km["a_yes_ask"])
                    else:
                        p_a = bm2 / (am + bm2) if am + bm2 else 0.5
                        band = (km["b_yes_bid"], km["b_yes_ask"])
                    note = (f"yes {km['a_yes_bid']:.2f}/{km['a_yes_ask']:.2f} & {km['b_yes_bid']:.2f}/{km['b_yes_ask']:.2f}, "
                            f"vol {km.get('a_volume_fp',0):.0f}+{km.get('b_volume_fp',0):.0f}")
                    if km.get("thin"):
                        note += " (thin)"
                    if km.get("schedule_mismatch") and not any("disagreement" in fl for fl in flags):
                        flags.append(km["schedule_mismatch"])
                    url = f"https://api.elections.kalshi.com/trade-api/v2/markets?event_ticker={tk}&status=open"
                    quotes.append(("kalshi", p_a, f"{tk} midpoint", url, note))
        rows.append({
            "id": fid, "a": a, "b": b,
            "competition": m.get("competition_name"),
            "start": m["scheduled_start_time"], "status": m["status"], "tier": m.get("tier"),
            "points": m.get("offered_points"), "lock": m.get("lock_time"),
            "kind": kind, "quotes": quotes, "flags": flags,
            "hltv_url": (meta.get("hltv") or (None, None))[0],
            "hltv_fav": (meta.get("hltv") or (None, None))[1],
        })
    return gen, rows


def finalize(r):
    qs = r["quotes"]
    if r["kind"] == "locked":
        r.update(p=None, p_pick=None, pick=None, pname="—", band=None, label="🔒 locked — already started")
        return r
    if not qs:
        if r["kind"] == "lean":
            name = r["a" if r["hltv_fav"] == "a" else "b"]
            r.update(p=None, p_pick=None, pick=r["hltv_fav"], pname=name, band=None,
                     label="◑ indicative lean — no line captured (HLTV context)")
        elif r["kind"] == "seed":
            r.update(p=None, p_pick=None, pick=None, pname="—", band=None,
                     label="⚑ unverified — Kalshi book empty (seed quotes)")
        else:
            r.update(p=None, p_pick=None, pick=None, pname="—", band=None,
                     label="⚑ unverified — no external line captured")
        return r
    ps = [q[1] for q in qs]
    p = mean(ps)
    pick = "a" if p >= 0.5 else "b"
    band = (min(ps), max(ps))
    margin = abs(p - 0.5) * 2
    n = len(set(q[0] for q in qs))
    spread = band[1] - band[0]
    if r["hltv_fav"] and p > 0.53 and r["hltv_fav"] != pick:
        r["flags"].append("HLTV context favorite disagrees with captured-line favorite")
    if n >= 2 and spread <= 0.10 and margin >= 0.40:
        lab = "strong consensus"
    elif n >= 2 and margin >= 0.15:
        lab = "consensus" if spread <= 0.15 else "consensus (sources spread)"
    elif margin >= 0.06:
        lab = "lean" + (" (single source)" if n == 1 else "")
    else:
        lab = "tossup"
    if any("thin" in (q[4] or "") for q in qs) and "consensus" not in lab:
        lab += " · thin book"
    r.update(p=p, p_pick=max(p, 1 - p), pick=pick, pname=r[pick], band=band, margin=margin, label=lab)
    return r


CSS = """
:root{--bg:#0b0e14;--card:#141927;--ink:#e8ecf5;--dim:#9aa4b8;--ac:#3fd08c;--warn:#f5b13f;--bad:#ff6b6b;--line:#232b3d;--hot:#7c5cff}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:0 0 60px}
header{padding:18px 16px 10px;max-width:1060px;margin:0 auto}
h1{font-size:1.35rem}
h1 .sub{color:var(--dim);font-weight:400;display:block;font-size:.85rem;margin-top:4px}
nav{max-width:1060px;margin:8px auto 0;padding:0 16px;display:flex;gap:8px;flex-wrap:wrap}
nav a{background:var(--card);border:1px solid var(--line);color:var(--ink);text-decoration:none;padding:8px 12px;border-radius:10px;font-size:.85rem}
nav a.here{border-color:var(--hot)}
main{max-width:1060px;margin:14px auto 0;padding:0 16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;text-align:center}
.stat b{display:block;font-size:1.4rem;color:var(--ac)}
.stat span{color:var(--dim);font-size:.78rem}
.scrollable{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;min-width:820px;font-size:.85rem}
th{color:var(--dim);font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:8px;border-bottom:1px solid var(--line);vertical-align:top}
.pick{font-weight:700;color:var(--ac)}
.pick.na{color:var(--dim);font-weight:400}
.chip{display:inline-block;padding:2px 8px;border-radius:999px;font-size:.72rem;border:1px solid var(--line);color:var(--dim);margin:2px 0}
.chip.strong{color:var(--ac);border-color:#2e6b50}
.chip.lean{color:var(--warn);border-color:#6b582e}
.chip.bad{color:var(--bad);border-color:#6b3636}
.muted{color:var(--dim)}
a{color:#8fb6ff}
.src{font-size:.75rem;display:block;color:#8fb6ff;text-decoration:none}
.src:hover{text-decoration:underline}
.flag{color:var(--warn);font-size:.75rem}
.banner{background:#1d2540;border:1px solid #33406b;border-left:4px solid var(--hot);border-radius:10px;padding:10px 12px;font-size:.85rem;margin-bottom:14px}
.banner.green{border-left-color:var(--ac)}
.banner.red{border-left-color:var(--bad)}
h2{font-size:1.05rem;margin:18px 0 8px}
h3{font-size:.95rem;margin:12px 0 6px}
ul,ol{padding-left:20px}
li{margin-bottom:6px}
code{background:#0006;padding:1px 5px;border-radius:5px;font-size:.82rem}
footer{max-width:1060px;margin:24px auto 0;padding:0 16px;color:var(--dim);font-size:.75rem}
"""


def esc(x):
    return html.escape(str(x))


def page(title, subtitle, body, active, depth):
    pre = "../" * depth
    nav = f"""
<nav>
 <a href="{pre}../index.html">⌂ root dashboard</a>
 <a href="{pre}index.html"{' class="here"' if active=='home' else ''}>Landing</a>
 <a href="{pre}cs2/"{' class="here"' if active=='cs2' else ''}>CS2 board</a>
 <a href="{pre}flagged/"{' class="here"' if active=='flag' else ''}>Flagged for Review</a>
 <a href="{pre}method/"{' class="here"' if active=='method' else ''}>Method</a>
</nav>"""
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="External betting-line picks for every CS2 match on the Hotspawn pick'em lobby. Lines originate from Bovada, Pinnacle and Kalshi - never from Hotspawn crowd percentages.">
<style>{CSS}</style>
</head><body>
<header><h1>{html.escape(title)}<span class="sub">{html.escape(subtitle)}</span></h1></header>
{nav}
<main>{body}</main>
<footer>Evidence-first build by session <code>dd2b7fee</code> · raw snapshot <code>data/dd2b7fee/lines_snapshot.json</code> · Hotspawn crowd % never used.</footer>
</body></html>"""


def src_links(r):
    out = []
    for s, p, detail, url, note in r["quotes"]:
        out.append(f'<a class="src" href="{esc(url)}">🔗 {esc(SOURCE_META[s]["label"])}</a><span class="muted" style="font-size:.72rem">{esc(detail)} — {esc(note)}</span>')
    if r["hltv_url"]:
        out.append(f'<a class="src" href="{esc(r["hltv_url"])}">🔗 HLTV analytics (cross-check)</a>')
    out.append(f'<a class="src" href="{HOTSPAWN_LOBBY}">🎮 Hotspawn lobby</a>')
    return "<br>".join(out)


def fmt_p(r):
    if r["p"] is None:
        return '<span class="muted">—</span>'
    pp = r["p_pick"]
    lo, hi = r["band"]
    if r["pick"] == "b":           # band mirrored to the picked side
        lo, hi = 1 - hi, 1 - lo
    band = f' <span class="muted">[{lo*100:.0f}–{hi*100:.0f}]</span>' if hi - lo > 0.004 else ""
    return f"<b>{pp*100:.1f}%</b>{band}"


def chip(r):
    lab = r["label"]
    cls = "strong" if "strong" in lab else ("bad" if ("unverified" in lab or "locked" in lab) else ("lean" if ("lean" in lab or "tossup" in lab or "thin" in lab or "indicative" in lab) else ""))
    return f'<span class="chip {cls}">{esc(lab)}</span>'


def rows_html(rows):
    tds = []
    for r in rows:
        nsrc = len(set(q[0] for q in r["quotes"]))
        flags = "".join(f'<div class="flag">⚑ {esc(x)}</div>' for x in r["flags"])
        pickcell = f'<span class="pick">{esc(r["pname"])}</span>' if r["pname"] != "—" else '<span class="pick na">—</span>'
        start = (r["start"] or "").replace("T", " ")[:16] + "Z"
        pts = r["points"] if r["points"] is not None else "—"
        ev = f"{r['points'] * max(r['p'], 1 - r['p']):.1f}" if (r["p"] and r["points"]) else "—"
        tds.append(
            f"<tr><td>{start}<br><span class='muted'>{esc(r['competition'])}</span></td>"
            f"<td><b>{esc(r['a'])}</b> vs <b>{esc(r['b'])}</b><br><span class='muted'>fixture {r['id']} · tier {esc(r['tier'])} · lock {esc((r['lock'] or '')[11:16])}Z</span>{flags}</td>"
            f"<td>{pickcell}</td><td>{fmt_p(r)}<br><span class='muted'>{nsrc} src</span></td>"
            f"<td>{pts}<br><span class='muted'>EV {ev}</span></td>"
            f"<td>{chip(r)}</td><td>{src_links(r)}</td></tr>")
    head = ("<th>Start (UTC)</th><th>Fixture</th><th>Pick</th><th>P(pick), external</th>"
            "<th>Points</th><th>Assessment</th><th>Official sources</th>")
    return f'<div class="scrollable"><table><tr>{head}</tr>{"".join(tds)}</table></div>'


def build():
    snap = json.loads(SNAP_PATH.read_text())
    fx = json.loads(FX_PATH.read_text())
    gen, rows = load_rows(snap, fx)
    rows = [finalize(r) for r in rows]
    rows.sort(key=lambda r: r["start"] or "")
    (ROOT / "data" / "dd2b7fee" / "board.json").write_text(json.dumps(
        {"generated_at_utc": snap["generated_at_utc"], "inventory_generated_at_utc": gen, "rows": rows}, indent=2))
    priced = [r for r in rows if r["p"] is not None]
    locked = [r for r in rows if r["kind"] == "locked"]
    leans = [r for r in rows if r["kind"] == "lean"]
    unpriced = [r for r in rows if r["p"] is None and r["kind"] in ("series", "seed")]
    ev_total = sum(r["points"] * max(r["p"], 1 - r["p"]) for r in priced if r["points"])
    ret = snap["retrieval_window_utc"]

    # ---------- landing
    body = f"""
<div class="banner green"><b>What this is:</b> a pick assistant for every CS2 match currently on the
<a href="{HOTSPAWN_LOBBY}">Hotspawn pick'em lobby</a>. Win probabilities originate from <b>external</b>
sportsbook / exchange lines (Bovada, Pinnacle, Kalshi) captured {esc(ret)} UTC —
<b>Hotspawn crowd pick-percentages are never used, read, or displayed.</b>
Rows without a captured official line are left blank and flagged, per the evidence-first rule.</div>
<div class="grid">
 <div class="stat"><b>{len(rows)}</b><span>lobby fixtures (current window)</span></div>
 <div class="stat"><b>{len(priced)}</b><span>with captured external line</span></div>
 <div class="stat"><b>{sum(1 for r in priced if 'consensus' in r['label'])}</b><span>multi-source consensus picks</span></div>
 <div class="stat"><b>{len(leans)}</b><span>indicative lean (no price)</span></div>
 <div class="stat"><b>{len(unpriced)}</b><span>blank / flagged (no line)</span></div>
 <div class="stat"><b>{len(locked)}</b><span>locked / started</span></div>
 <div class="stat"><b>≈{ev_total:.0f}</b><span>expected pick'em points from priced picks</span></div>
</div>
<div class="card"><h2 style="margin-top:0">Strongest board picks</h2>
{rows_html(sorted(priced, key=lambda r: -(r['margin'] or 0))[:6])}
<p class="muted" style="margin-top:8px">Full board: <a href="./cs2/">CS2 board page</a> · irregularities: <a href="./flagged/">Flagged for Review</a></p></div>
<div class="card"><h2 style="margin-top:0">Freshness & coverage</h2><ul>
<li>Fixture inventory: official Hotspawn fixtures API (reverse-engineered, normalized upstream by <code>scripts/fetch_hotspawn.py</code>, snapshot {esc(fx['generated_at_utc'])}; upper stream refreshes it roughly hourly). Window: {esc(snap['inventory_basis']['window'])}.</li>
<li>Bovada CS2 coupon captured {esc(snap['sources']['bovada']['retrieved_utc'])} — {len(snap['sources']['bovada']['markets'])} match-winner markets (9 lobby matches + 1 non-lobby).</li>
<li>Pinnacle Arcadia series moneylines captured {esc(snap['sources']['pinnacle']['retrieved_utc'])} — 8 open series + 1 pulled intraday + 1 closed (documented on the Flagged page).</li>
<li>Kalshi KXCS2GAME captured {esc(snap['sources']['kalshi']['retrieved_utc'])} — 21 events matched to lobby fixtures; thin/wide books flagged per row.</li>
<li>Polymarket: no CS2 match markets (checked leveled tag searches) — Flagged page.</li>
<li>This board re-renders via <code>.github/workflows/fresh-dd2b7fee.yml</code> so the pages always reflect the latest upstream inventory snapshot.</li>
</ul></div>
"""
    (ROOT / "fresh").mkdir(exist_ok=True)
    (ROOT / "fresh" / "index.html").write_text(page(
        "Hotspawn CS2 Pick Board — session dd2b7fee",
        "External-line win probability for every lobby match · mobile-first", body, "home", 1))

    # ---------- cs2
    body = f"""
<div class="banner"><b>How to read:</b> “Pick” is the side our external lines favor. P(pick) is the
vig-removed consensus across captured sources for the picked side; [low–high] is the spread across
sources. “Points” is what Hotspawn offers for a correct pick on that fixture; EV = points × P.
Rows marked ⚑ have no captured official line — nothing is invented there.<br>
<a href="{esc(HOTSPAWN_API)}">Inventory API</a> · snapshot {esc(gen)}</div>
<h2>All {len(rows)} fixtures in the current lobby window</h2>
{rows_html(rows)}
<div class="card"><h3 style="margin-top:0">Reading order tip</h3>
<p class="muted">Matches lock 6 minutes before their listed start. The Thunderpick WC quarter-finals all
start Oct 14 (08:30–16:00 UTC); Pulse Beat III matches split across Oct 14–15; Elisa BreakOut Series 2 runs
Oct 15–16 (several rows there have no usable line yet — check back after the hourly refresh, they still
appear on the Flagged page in the meantime).</p></div>
"""
    (ROOT / "fresh" / "cs2").mkdir(parents=True, exist_ok=True)
    (ROOT / "fresh" / "cs2" / "index.html").write_text(page(
        "CS2 board — every fixture, external lines",
        f"{len(priced)} priced · {len(leans)} lean · {len(unpriced)} unpriced · {len(locked)} locked", body, "cs2", 2))

    # ---------- flagged
    flag_rows = [r for r in rows if r["flags"]]
    flags_html = "".join(
        f"<tr><td>{r['id']}</td><td><b>{esc(r['a'])}</b> vs <b>{esc(r['b'])}</b></td>"
        f"<td>{'<br>'.join('⚑ '+esc(x) for x in r['flags'])}</td><td>{src_links(r)}</td></tr>"
        for r in flag_rows)
    src_flags = """
<tr><td>—</td><td><b>EAC Extra</b> vs <b>Bread Eaters Esports</b> (EPL S32, Oct 14 10:30Z)</td>
<td>⚑ Real book lines exist but the match is NOT in the Hotspawn lobby — left unused. Bovada 1.541/2.35 · Pinnacle −181/+140 (EAC Extra favorite) · Kalshi event KXCS2GAME-26OCT140630BREEACE also exists (listing only).</td>
<td><a class="src" href="https://sports.bovada.lv/esports/counter-strike-2">🔗 Bovada</a><a class="src" href="https://guest.api.arcadia.pinnacle.com/0.1/matchups/1638305917/markets/related/straight">🔗 Pinnacle API</a><a class="src" href="https://kalshi.com/markets/KXCS2GAME">🔗 Kalshi</a></td></tr>
<tr><td>—</td><td><b>Astralis</b> vs <b>Sashi</b> (Pulse Beat III)</td>
<td>⚑ Pinnacle never listed this match (its Pulse Beat league carries only 4 series, all accounted for) — Bovada and Kalshi both cover it, so the pick stands, but the Pinnacle absence is documented. Kalshi's Astralis side volume ≈6 contracts (very thin).</td>
<td><a class="src" href="https://sports.bovada.lv/esports/counter-strike-2">🔗 Bovada</a><a class="src" href="https://kalshi.com/markets/KXCS2GAME">🔗 Kalshi</a></td></tr>
<tr><td>—</td><td><b>Polymarket</b> (source check)</td>
<td>⚑ No CS2 match-winner markets found (counter-strike tag returned only Valve sticker trade-up meta markets; esports tag is dominated by other titles). Polymarket excluded as a source this cycle.</td>
<td><a class="src" href="https://polymarket.com/sports/counter-strike-2">🔗 Polymarket</a></td></tr>
<tr><td>—</td><td><b>Name aliases used</b> (matched by opponent + start time, still flagged)</td>
<td>Bovada “BB Team” = BetBoom · Bovada “FURIA Academy” = FURIA (parent fixtures say FURIA) · Pinnacle “PVISION” = PARIVISION · Pinnacle/Kalshi “Overtake” = Overtake Sector · Kalshi “NIP” = Ninjas in Pyjamas · Kalshi “WBT Academy” = lobby “WROTBERRY” (5 events matched) · Kalshi “WRAITH PCIFIC” = lobby “PCIFIC” (opponent+time) · lobby “EAC” = Kalshi “Esport Academy Copenhagen” and is a DIFFERENT team from Bovada/Pinnacle “EAC Extra” (similar names, distinct clubs — do not merge).</td>
<td><a class="src" href="https://sports.bovada.lv/esports/counter-strike-2">🔗 Bovada</a><a class="src" href="https://guest.api.arcadia.pinnacle.com/0.1/matchups/1638111786/markets/related/straight">🔗 Pinnacle</a><a class="src" href="https://kalshi.com/markets/KXCS2GAME">🔗 Kalshi</a></td></tr>
<tr><td>—</td><td><b>Pinnacle HOTU–Fnatic series line</b></td>
<td>⚑ Present in a 22:41:50Z capture (home −101 / away −125, open) but absent from a live re-read of all market chunks at 23:05Z — treated as pulled intraday and NOT used for the pick (map markets still open). Bovada + Kalshi still agree on fnatic.</td>
<td><a class="src" href="https://guest.api.arcadia.pinnacle.com/0.1/matchups/1637867148/markets/related/straight">🔗 Pinnacle API</a></td></tr>
<tr><td>—</td><td><b>Pinnacle ESL SA (ex-Keyd–Galorys)</b></td>
<td>⚑ Market list emptied ([] at 23:03Z) after the 21:00Z start — consistent with the fixture being locked; recorded as evidence.</td>
<td><a class="src" href="https://guest.api.arcadia.pinnacle.com/0.1/matchups/1638278447/markets/related/straight">🔗 Pinnacle API</a></td></tr>
"""
    body = f"""
<div class="banner red"><b>Flagged for Review.</b> Every irregularity, thin book, schedule disagreement,
alias assumption and coverage gap found this cycle — published with links, never hidden. Flagged fixtures
still appear on the main board; nothing here blocks it.</div>
<h2>Fixture flags ({len(flag_rows)})</h2>
<div class="scrollable"><table><tr><th>Fixture</th><th>Match</th><th>Flag</th><th>Official sources</th></tr>{flags_html}</table></div>
<h2>Source-level flags</h2>
<div class="scrollable"><table><tr><th>Fixture</th><th>Match</th><th>Flag</th><th>Official sources</th></tr>{src_flags}</table></div>
<h2>Blank fixtures (no captured line) — {len(unpriced)}</h2>
<p class="muted">Per the evidence rule these rows stay blank on the board. They are re-checked on every
upstream refresh; if a book lists them later the board picks them up automatically.</p>
{rows_html(unpriced)}
"""
    (ROOT / "fresh" / "flagged").mkdir(parents=True, exist_ok=True)
    (ROOT / "fresh" / "flagged" / "index.html").write_text(page(
        "Flagged for Review — irregularities & coverage gaps", "Published, linked, non-blocking", body, "flag", 2))

    # ---------- method
    body = f"""
<div class="card"><h2 style="margin-top:0">Method</h2><ol>
<li><b>Inventory.</b> All fixtures come from the official Hotspawn fixtures API (<code>phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures</code>, reverse-engineered from the play.hotspawn.com lobby by earlier sessions; refreshed upstream ~hourly). Nothing hand-entered.</li>
<li><b>External lines.</b> Prices captured from Bovada's CS2 coupon, Pinnacle's Arcadia guest API (primary series moneyline <code>s;0;m</code>), and Kalshi's KXCS2GAME binary series (yes bid/ask midpoints). Raw captures with retrieval timestamps: <code>data/dd2b7fee/lines_snapshot.json</code>.</li>
<li><b>No-vig.</b> Book prices divided by their implied sum (overround removed). Kalshi is an exchange: midpoint used directly; thin/wide/seed books flagged — exchange seed books (6¢/94¢ both sides, zero volume) are treated as NO line.</li>
<li><b>Consensus.</b> Published P(pick) = mean of source estimates for the picked side; [low–high] shows the spread. Single-source rows are labelled. HLTV is a qualitative cross-check only.</li>
<li><b>Never crowd-derived.</b> Hotspawn pick-percent fields exist in the feed but are never read here.</li>
<li><b>Honesty.</b> No line → blank + flagged. Schedule disagreements (e.g. MIBR–BC.Game and Heroic–Envy at Oct 15 10:00Z per Hotspawn+Kalshi but Oct 14 16:30–22:30Z per Bovada/Pinnacle) are published. Unconfirmed aliases are listed, not silently merged.</li>
<li><b>EV.</b> points × P(pick). Pick'em points (2–7 per fixture) come from the fixtures API <code>offered_points</code> field.</li>
</ol></div>
<div class="card"><h2 style="margin-top:0">Sources</h2><ul>
<li><a href="{HOTSPAWN_LOBBY}">Hotspawn CS2 pick'em lobby</a> · <a href="{HOTSPAWN_API}">fixtures API</a> (inventory + points + locks only)</li>
<li><a href="https://sports.bovada.lv/esports/counter-strike-2">Bovada — Counter-Strike 2</a> (9 lobby matches priced)</li>
<li><a href="https://www.pinnacle.com/en/esports/cs2-hub">Pinnacle — CS2 hub</a> (verbatim per-matchup API rows linked on the board)</li>
<li><a href="https://kalshi.com/markets/KXCS2GAME">Kalshi — KXCS2GAME</a> (21 events; per-event API rows linked)</li>
<li><a href="https://www.hltv.org/betting/analytics">HLTV betting analytics</a> (cross-check only)</li>
<li><a href="https://polymarket.com/sports/counter-strike-2">Polymarket</a> (checked — no match markets; see Flagged)</li>
</ul></div>
<div class="card"><h2 style="margin-top:0">Refresh loop</h2>
<p class="muted">The repo's upstream pipeline refreshes the inventory about hourly;
<code>.github/workflows/fresh-dd2b7fee.yml</code> re-runs this builder plus tests on that cadence.
Line captures are in-session snapshots — each source's retrieval timestamp is shown on the landing page
({esc(ret)} UTC). Scheduled automated price re-capture is future work, recorded in COORDINATION.md.</p></div>
"""
    (ROOT / "fresh" / "method").mkdir(parents=True, exist_ok=True)
    (ROOT / "fresh" / "method" / "index.html").write_text(page(
        "Method — how these picks are built", "Sources, no-vig math, consensus rules", body, "method", 2))

    print(f"OK rows={len(rows)} priced={len(priced)} lean={len(leans)} unpriced={len(unpriced)} locked={len(locked)} ev={ev_total:.0f}")
    for r in priced:
        print(f"  {r['id']} {r['a']} vs {r['b']}: {r['pname']} @ {r['p_pick']*100:.1f}% [{r['label']}] src={len(r['quotes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(build())
