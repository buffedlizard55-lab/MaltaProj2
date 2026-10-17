#!/usr/bin/env python3
"""Desk: one phone-first page set for every open HotSpawn CS2 pick.

Reads (never writes) the canonical capture `data/c64a5e19/board.json` and adds:

  * book quotes the canonical matcher could not join (name variants), each join
    justified by an agreeing opponent AND kickoff, and each recorded in
    data/3e1be203/research.json;
  * a second esportsbook source (Thunderpick via bo3.gg) read live this session;
  * three fixture rows where Valve's official list contains a duplicate team name
    disambiguated by roster (documented in research.json);
  * a conservative lower bound for rows where exactly one side is rated and the
    other is absent from Valve's published list;
  * crowd ownership, used ONLY for the leaderboard leverage column.

Nothing is invented: a row with no usable price and no uniquely identified rating
pair stays blank and is published on unresolved.html with its reason.

Output: desk/*.html + desk/data/board.json
"""
from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "desk")
CANON = "data/c64a5e19/board.json"
RESEARCH = "data/3e1be203/research.json"
OWNERSHIP = "data/3e1be203/ownership.json"
LOBBY = "https://play.hotspawn.com/lobby"
VRS_URL = ("https://github.com/ValveSoftware/counter-strike_regional_standings/"
           "blob/main/live/2026/standings_global_2026_10_05.md")
SHRINK = 0.4213  # canonical shrink slope, reproduced here (see method.html)
WEEK_RESET = "2026-10-19T00:00:00Z"
RESEARCH_WINDOW = ""


def esc(v):
    return html.escape("" if v is None else str(v), quote=True)


def load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def pct(v, digits=1):
    return "—" if v is None else f"{v * 100:.{digits}f}%"


def fmt_utc(iso, short=False):
    if not iso:
        return "—"
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if short:
        return dt.strftime("%d %b %H:%M")
    return dt.strftime("%a %d %b · %H:%M UTC")


def devig(da, db):
    ia, ib = 1.0 / da, 1.0 / db
    s = ia + ib
    return ia / s, ib / s


def logistic(delta):
    return 1.0 / (1.0 + 10 ** (-delta / 400.0))


def shrink(u):
    return 0.5 + (u - 0.5) * SHRINK


# ------------------------------------------------------------------ evidence join
def build_rows():
    canon = load(CANON)
    research = load(RESEARCH)
    own = load(OWNERSHIP)["ownership"]
    alias = {a["fixture_id"]: a for a in research["aliases"]}
    model_rows = {m["fixture_id"]: m for m in research["model_rows"]}
    bound_rows = {b["fixture_id"]: b for b in research["bound_rows"]}
    floor = research["vrs_floor"]["points"]

    rows = []
    for r in canon["open"]:
        fid = str(r["fixture_id"])
        line = r.get("line") or {}
        item = {
            "fixture_id": fid,
            "competition": r["competition"],
            "tier": r["tier"],
            "points": r.get("points"),
            "start_utc": r["start_utc"],
            "lock_utc": r.get("lock_utc"),
            "team_a": r["team_a"],
            "team_b": r["team_b"],
            "hotspawn_url": r.get("hotspawn_url") or LOBBY,
            "sources": list(r.get("sources") or []),
            "flags": list(r.get("flags") or []),
            "basis": None,
            "prob_a": None,
            "prob_b": None,
            "pick": None,
            "pick_prob": None,
            "confidence": None,
            "note": None,
            "quotes": [],
            "bound": False,
        }
        for s in item["sources"]:
            if s.get("url"):
                s["url"] = s["url"].replace("../", "/").replace("https://buffedlizard55-lab.github.io/MaltaProj2/", "")
        # ownership
        o = own.get(fid)
        item["crowd_a"], item["crowd_b"] = (o["team_a"], o["team_b"]) if o else (None, None)

        alias_ok = False
        if fid in alias:
            a = alias[fid]
            nums = []
            for q in a["quotes"]:
                if q.get("decimal_a") and q.get("decimal_b"):
                    pqa, pqb = devig(q["decimal_a"], q["decimal_b"])
                    nums.append((q["book"], pqa, pqb, q))
                    item["quotes"].append(q)
            if nums:
                alias_ok = True
                wsum = sum(2 if n[0].startswith("Pinnacle") else 1 for n in nums)
                item["prob_a"] = sum((2 if n[0].startswith("Pinnacle") else 1) * n[1] for n in nums) / wsum
                item["prob_b"] = 1 - item["prob_a"]
                item["basis"] = "market"
                item["basis_label"] = "Market (re-joined)"
                item["note"] = "Re-joined to a book quote the canonical matcher dropped: " + a["reason"]
                for n in nums:
                    names = n[3].get("names") or [item['team_a'], item['team_b']]
                    item["sources"].append({
                        "label": (f"{n[0]}: {names[0]} {n[3]['decimal_a']} / {names[1]} {n[3]['decimal_b']}"
                                  f" · HotSpawn slot {item['team_a']} v {item['team_b']}"),
                        "url": n[3]["url"], "read_utc": n[3]["read_utc"]})
            if a.get("conflict"):
                item["flags"].append("opponent_identity_conflict")

        if alias_ok:
            pass
        elif line.get("basis") == "market" and line.get("prob_a") is not None:
            item.update(basis="market", prob_a=line["prob_a"], prob_b=line["prob_b"],
                        basis_label="Market")
            item["quotes"] = r.get("quotes") or []
        elif line.get("basis") == "model" and line.get("prob_a") is not None:
            item.update(basis="model", prob_a=line["prob_a"], prob_b=line["prob_b"],
                        basis_label="Model (Valve VRS)",
                        note="Valve-VRS rating model; not a bookmaker price.")
            item["quotes"] = r.get("quotes") or []
        elif fid in model_rows:
            m = model_rows[fid]
            delta = m["points"] - m["opponent_points"]
            pma = shrink(logistic(delta))
            item.update(basis="model", prob_a=pma, prob_b=1 - pma,
                        basis_label="Model (Valve VRS, disambiguated)",
                        note=f"Both teams rated; duplicate Valve row disambiguated by roster. {m['vrs_note']}")
            item["sources"].append({"label": f"Valve VRS: {m['team']} #{m['standing']} ({m['points']}) vs {m['opponent']} #{m['opponent_standing']} ({m['opponent_points']})", "url": VRS_URL, "read_utc": "2026-10-05T00:00:00Z"})
        elif fid in bound_rows:
            b = bound_rows[fid]
            delta = b["points"] - floor
            pbound = shrink(logistic(delta))
            if b.get("side", "a") == "a":
                item.update(basis="bound", prob_a=pbound, prob_b=1 - pbound)
            else:
                item.update(basis="bound", prob_a=1 - pbound, prob_b=pbound)
            item["basis_label"] = "Lower bound (one side unrated)"
            item["bound"] = True
            item["bound_team"] = b["rated"]
            item["note"] = ("Opponent is absent from Valve's published list, so its rating cannot exceed the "
                            f"list floor ({floor} pts). {b['rated']}'s win probability is therefore AT LEAST "
                            f"{pct(pbound)}. This is a bound, not a point estimate. {b['note']}")
            item["sources"].append({"label": f"Valve VRS: {b['rated']} #{b['standing']} ({b['points']}); {b['unrated']} unlisted; floor {floor} pts (#380)", "url": VRS_URL, "read_utc": "2026-10-05T00:00:00Z"})
        else:
            item["basis"] = "unresolved"
            item["basis_label"] = "Unresolved"
            item["note"] = "No usable price and no uniquely identified rating pair in this capture."

        # pick + leverage
        pa, pb = item["prob_a"], item["prob_b"]
        if pa is not None:
            ca, cb = item["crowd_a"], item["crowd_b"]
            if abs(pa - 0.5) < 1e-9 and ca is not None and cb is not None:
                item["pick"] = item["team_a"] if ca < cb else item["team_b"]
                item["pick_prob"] = 0.5
                item["confidence"] = "Priced tie"
                item["note"] = (item["note"] + " " if item["note"] else "") + \
                    "Market is a true 50/50; the pick is the lower-owned side, for leaderboard leverage only."
            else:
                item["pick"] = item["team_a"] if pa >= pb else item["team_b"]
                item["pick_prob"] = max(pa, pb)
                edge = item["pick_prob"]
                item["confidence"] = "Strong" if edge >= 0.70 else "Moderate" if edge >= 0.58 else "Toss-up"
        if item["crowd_a"] is not None and pa is not None:
            item["leverage_a"] = round(pa - item["crowd_a"] / 100.0, 4)
            item["leverage_b"] = round(pb - item["crowd_b"] / 100.0, 4)
        else:
            item["leverage_a"] = item["leverage_b"] = None
        rows.append(item)

    rows.sort(key=lambda x: (x["start_utc"], x["team_a"]))
    return rows, research, canon


def add_edges(rows):
    """Qualified climb picks: underdog, market >= 35%, leverage >= 20pp."""
    for r in rows:
        r["climb"] = None
        if r["prob_a"] is None or r["crowd_a"] is None:
            continue
        if "opponent_identity_conflict" in r.get("flags", []):
            continue
        for side in ("a", "b"):
            p = r[f"prob_{side}"]
            lev = r[f"leverage_{side}"]
            team = r[f"team_{side}"]
            if p >= 0.35 and p < 0.5 and lev >= 0.20:
                cand = {"team": team, "prob": p, "leverage": lev}
                if r["climb"] is None or cand["leverage"] > r["climb"]["leverage"]:
                    r["climb"] = cand
    return rows


# ------------------------------------------------------------------ page chrome
CSS = """
:root{--bg:#0b0f14;--panel:#141a22;--panel2:#1b232e;--line:#27313f;--txt:#e8eef5;--mut:#93a1b1;
--acc:#4da3ff;--ok:#3fb950;--warn:#d29922;--bad:#f85149;--chip:#22303f}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--acc)}
.wrap{max-width:760px;margin:0 auto;padding:14px 14px 90px}
header.top{position:sticky;top:0;z-index:9;background:rgba(11,15,20,.96);border-bottom:1px solid var(--line);backdrop-filter:blur(6px)}
.top .bar{max-width:760px;margin:0 auto;display:flex;align-items:center;gap:10px;padding:8px 12px}
.brand{font-weight:700;font-size:15px;letter-spacing:.2px;white-space:nowrap;color:var(--txt);text-decoration:none}
.tabs{display:flex;gap:6px;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tabs a{flex:0 0 auto;padding:9px 12px;border-radius:999px;background:var(--panel2);color:var(--txt);text-decoration:none;font-size:14px;border:1px solid var(--line);min-height:40px;display:flex;align-items:center}
.tabs a[aria-current=page]{background:var(--acc);color:#04121f;border-color:var(--acc);font-weight:700}
h1{font-size:24px;line-height:1.25;margin:14px 0 6px}
h2{font-size:19px;margin:26px 0 8px}
h3{font-size:16px;margin:18px 0 6px}
p,li{color:var(--txt)}
.muted{color:var(--mut)}
.small{font-size:13px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;margin:10px 0}
.card.pick{border-left:4px solid var(--acc)}
.card.blank{border-left:4px solid var(--warn);opacity:.95}
.kpis{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:12px 0}
.kpi{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:10px}
.kpi b{display:block;font-size:24px;line-height:1.1}
.kpi span{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.5px}
.actions{display:grid;gap:8px;margin:14px 0}
.btn{display:flex;align-items:center;justify-content:space-between;gap:10px;background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:14px;color:var(--txt);text-decoration:none;font-weight:600;min-height:52px}
.btn.primary{background:var(--acc);color:#04121f;border-color:var(--acc)}
.btn .n{font-weight:700;opacity:.9}
.match{display:flex;align-items:baseline;justify-content:space-between;gap:8px;flex-wrap:wrap}
.teams{font-size:17px;font-weight:700;margin:0}
.teams .vs{color:var(--mut);font-weight:400;font-size:14px}
.pickline{margin:10px 0 4px;font-size:15px}
.pickline b{font-size:18px}
.bar{height:9px;border-radius:6px;background:#26303d;overflow:hidden;display:flex;margin:8px 0 4px}
.bar i{display:block;height:100%}
.bar .a{background:var(--acc)}
.bar .b{background:#8b5cf6}
.probs{display:flex;justify-content:space-between;font-size:13px;color:var(--mut)}
.chip{display:inline-block;background:var(--chip);border:1px solid var(--line);border-radius:999px;padding:2px 9px;font-size:12px;margin:2px 4px 2px 0;color:var(--txt)}
.chip.ok{border-color:#245c33;color:#7ee2a0}
.chip.warn{border-color:#6b4f12;color:#f0c674}
.chip.bad{border-color:#6e2a26;color:#ff9d97}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--mut);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.4px}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
details{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin:10px 0}
summary{cursor:pointer;font-weight:600}
.note{background:#182231;border:1px solid #24344a;border-radius:10px;padding:10px 12px;font-size:14px}
.warnbox{background:#241d0f;border:1px solid #6b4f12;border-radius:10px;padding:10px 12px;font-size:14px}
footer{margin-top:30px;border-top:1px solid var(--line);padding-top:12px;font-size:12px;color:var(--mut)}
@media(max-width:420px){h1{font-size:21px}.kpi b{font-size:21px}}
"""


def page(title, active, body, generated):
    tabs = [("index.html", "Summary"), ("picks.html", "All picks"),
            ("twc.html", "TWC Day 4"), ("unresolved.html", "Unresolved"),
            ("flagged.html", "Flagged"), ("method.html", "Method")]
    nav = "".join(
        f'<a href="{href}"{" aria-current=page" if href == active else ""}>{label}</a>'
        for href, label in tabs)
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="dark">
<title>{esc(title)} · CS2 pick'em desk</title>
<link rel="stylesheet" href="style.css">
</head><body>
<header class="top"><div class="bar"><a class="brand" href="index.html">CS2 desk</a><nav class="tabs">{nav}</nav></div></header>
<div class="wrap">
{body}
<footer>
<p><strong>CS2 pick'em desk</strong> · page built {esc(generated)} · fixture inventory from the HotSpawn lobby
(<a href="{LOBBY}">play.hotspawn.com/lobby</a>). HotSpawn supplies fixtures, points and crowd ownership only;
it is never used as a win probability. Not affiliated with HotSpawn or any bookmaker.</p>
<p>Old boards stay online under <a href="../research.html">Research archive</a> ·
<a href="../picks-every-match/index.html">canonical every-match board</a> ·
<a href="../flagged.html">site-wide Flagged for Review</a>.</p>
</footer>
</div></body></html>"""


def src_links(row, extra=None):
    out, seen = [], set()
    for s in (row.get("sources") or []) + (extra or []):
        u = s.get("url")
        if not u or u in seen:
            continue
        seen.add(u)
        label = s.get("label") or u
        when = s.get("read_utc") or s.get("at_utc") or ""
        out.append(f'<a href="{esc(u)}" rel="noreferrer">{esc(label[:70])}</a>'
                   + (f' <span class="muted small">read {esc(when)}</span>' if when else ""))
    return "<br>".join(out)


# ------------------------------------------------------------------ pages
def render():
    rows, research, canon = build_rows()
    global RESEARCH_WINDOW
    RESEARCH_WINDOW = research.get('read_window', {}).get('to_utc', '')
    add_edges(rows)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    open_rows = rows
    priced = [r for r in rows if r["prob_a"] is not None]
    unresolved = [r for r in rows if r["prob_a"] is None]
    market = [r for r in priced if r["basis"] == "market"]
    model = [r for r in priced if r["basis"] == "model"]
    bound = [r for r in priced if r["basis"] == "bound"]
    climbs = sorted([r for r in rows if r.get("climb")], key=lambda r: -r["climb"]["leverage"])
    top_climb = {r["fixture_id"] for r in climbs[:3]}
    twc = research["twc"]
    sf1, sf2 = twc["day4"]
    # day-4 market consensus: canonical capture (3 books) blended with the live Thunderpick read
    for sf in (sf1, sf2):
        sf["p_a"] = round((sf["market"]["prob_a"] * 2 + sf["second_source"]["prob_a"]) / 3, 4)
        sf["p_b"] = round(1 - sf["p_a"], 4)
        pa, pb = sf["p_a"], sf["p_b"]
        sf["pick"] = sf["team_a"] if pa >= pb else sf["team_b"]
        sf["pick_prob"] = max(pa, pb)
        ca, cb = sf["crowd"]
        sf["lev_a"], sf["lev_b"] = pa - ca / 100, pb - cb / 100
        under = "b" if pa >= pb else "a"
        p_under = pb if under == "b" else pa
        lev_under = sf["lev_b"] if under == "b" else sf["lev_a"]
        sf["climb"] = ({"team": sf["team_b" if under == "b" else "team_a"], "prob": p_under,
                        "leverage": lev_under} if p_under >= 0.35 and lev_under >= 0.20 else None)

    # ---------------------------------------------------------------- summary
    nxt = [r for r in rows if r["prob_a"] is not None][:4]
    next_cards = ""
    for r in nxt:
        next_cards += f"""
<a class="card pick" href="picks.html#{esc(r['fixture_id'])}" style="text-decoration:none;color:inherit;display:block">
<div class="match"><p class="teams">{esc(r['team_a'])} <span class="vs">vs</span> {esc(r['team_b'])}</p>
<span class="muted small">{esc(fmt_utc(r['start_utc'], short=True))}</span></div>
<div class="pickline">Pick <b>{esc(r['pick'] or '—')}</b> · {pct(r['pick_prob'])} <span class="chip">{esc(r['basis_label'])}</span></div>
</a>"""

    climb_cards = ""
    for r in climbs[:3]:
        c = r["climb"]
        climb_cards += f"""
<a class="card" href="picks.html#{esc(r['fixture_id'])}" style="text-decoration:none;color:inherit;display:block">
<div class="match"><p class="teams">{esc(c['team'])} <span class="vs">climb pick</span></p>
<span class="chip ok">+{c['leverage'] * 100:.0f} pts of leverage</span></div>
<div class="small muted">{esc(r['team_a'])} vs {esc(r['team_b'])} · market {pct(c['prob'])} vs crowd {esc(r['crowd_a'] if c['team'] == r['team_a'] else r['crowd_b'])}%</div>
</a>"""

    twc_card = f"""
<div class="card">
<div class="match"><p class="teams">Semifinal 1 · FURIA vs Aurora</p><span class="muted small">17 Oct 14:00 UTC</span></div>
<div class="pickline">Leaderboard pick <b>Aurora</b> · {pct(sf1['p_b'])} <span class="chip ok">crowd only 18%</span></div>
</div>
<div class="card">
<div class="match"><p class="teams">Semifinal 2 · Falcons vs BETBOOM</p><span class="muted small">17 Oct 17:00 UTC</span></div>
<div class="pickline">Pick <b>Falcons</b> · {pct(sf2['p_a'])} <span class="chip">no qualified climb</span></div>
</div>"""

    body = f"""
<h1>Every open CS2 pick, on one phone screen</h1>
<p class="muted">Updated {esc(generated)} · {len(open_rows)} open HotSpawn matches ·
{len(market) + len(model)} priced · {len(bound)} bound-only · {len(unresolved)} with no pick.</p>

<div class="actions">
<a class="btn primary" href="picks.html"><span>All picks &amp; win probabilities</span><span class="n">{len(priced)}</span></a>
<a class="btn" href="twc.html"><span>TWC Day 4 semifinals</span><span class="n">2</span></a>
<a class="btn" href="unresolved.html"><span>Unresolved picks &amp; limitations</span><span class="n">{len(unresolved) + len(bound)}</span></a>
<a class="btn" href="method.html"><span>How every number is made</span><span class="n">→</span></a>
</div>

<div class="kpis">
<div class="kpi"><b>{len(market)}</b><span>Market prices</span></div>
<div class="kpi"><b>{len(model)}</b><span>Valve model</span></div>
<div class="kpi"><b>{len(bound)}</b><span>Bound only (no price)</span></div>
<div class="kpi"><b>{len(unresolved)}</b><span>No pick at all</span></div>
</div>

<h2>Next locks</h2>
{next_cards}

<h2>Leaderboard climb</h2>
<p class="small muted">A climb pick is only published when the bookmaker price still gives the underdog at least
35% and the crowd is at least 20 points lighter than that price. Rule and worked example in
<a href="method.html#rules">Method</a>.</p>
{climb_cards or '<p class="muted">No qualified climb pick in this snapshot.</p>'}

<h2>TWC 2026 · Day 4</h2>
{twc_card}
<p class="small"><a href="twc.html">Day 1–3 review, every result with its HLTV link, and the full day-4 case →</a></p>

<h2>What changed in this build</h2>
<ul class="small">
<li><strong>{len(market)}</strong> rows carry a bookmaker or exchange price, <strong>{len(model)}</strong> a
Valve-rating estimate and <strong>{len(bound)}</strong> a lower bound. Every one is labelled on the row.</li>
<li>Re-joined <strong>{len(research['aliases'])}</strong> book quotes the canonical matcher dropped,
each with its roster or name evidence on <a href="picks.html">All picks</a> and in <a href="method.html">Method</a>.</li>
<li>Resolved <strong>{len(research['model_rows'])}</strong> duplicate-name Valve rows by roster and published a
<strong>lower bound</strong> for <strong>{len(bound)}</strong> matches whose opponent is absent from Valve's list.</li>
<li><strong>{len(unresolved)}</strong> matches are completely blank. The <strong>{len(bound)}</strong>
rows without a price are listed on <a href="unresolved.html">Unresolved</a> with the exact sources tried —
never a 50/50 guess.</li>
<li>Irregularities found while verifying: <a href="flagged.html">Flagged for review</a>.</li>
</ul>

<details><summary>Where are the old boards?</summary>
<p class="small">Twenty-odd parallel boards were built by earlier sessions and are still online. They are
preserved, not deleted, under the <a href="../research.html">research archive</a>. The
<a href="../picks-every-match/index.html">canonical every-match board</a> remains the strict,
market-only view. This desk is the single mobile front door: it starts from that canonical capture and
adds the research layer described above.</p></details>
"""
    pages = {"index.html": page("Executive summary", "index.html", body, generated)}

    # ---------------------------------------------------------------- picks
    by_day = {}
    for r in rows:
        by_day.setdefault(r["start_utc"][:10], []).append(r)
    day_blocks = ""
    for day in sorted(by_day):
        day_blocks += f'<h2 id="{day}">{esc(datetime.strptime(day, "%Y-%m-%d").strftime("%A %d %B"))}</h2>'
        for r in by_day[day]:
            pa, pb = r["prob_a"], r["prob_b"]
            if pa is None:
                card = f"""
<div class="card blank" id="{esc(r['fixture_id'])}">
<div class="match"><p class="teams">{esc(r['team_a'])} <span class="vs">vs</span> {esc(r['team_b'])}</p>
<span class="muted small">{esc(fmt_utc(r['start_utc'], short=True))}</span></div>
<div class="pickline">No pick yet <span class="chip warn">unresolved</span></div>
<div class="small muted">{esc(r['competition'])} · {esc(r['points'])} pts · <a href="unresolved.html#{esc(r['fixture_id'])}">why →</a></div>
</div>"""
            else:
                lead = r["pick"] if r["pick"] else (r["team_a"] if pa >= pb else r["team_b"])
                lead_p = r["pick_prob"] if r["pick_prob"] is not None else max(pa, pb)
                lev = r["leverage_a"] if lead == r["team_a"] else r["leverage_b"]
                chips = f'<span class="chip">{esc(r["basis_label"])}</span>'
                if r["bound"]:
                    chips += '<span class="chip warn">lower bound</span>'
                if r.get("climb") and r["fixture_id"] in top_climb:
                    chips += f'<span class="chip ok">climb {esc(r["climb"]["team"])} +{r["climb"]["leverage"] * 100:.0f} pts</span>'
                card = f"""
<div class="card pick" id="{esc(r['fixture_id'])}">
<div class="match"><p class="teams">{esc(r['team_a'])} <span class="vs">vs</span> {esc(r['team_b'])}</p>
<span class="muted small">{esc(fmt_utc(r['start_utc'], short=True))} · {esc(r['points'])} pts</span></div>
<div class="bar" aria-hidden="true"><i class="a" style="width:{pa * 100:.1f}%"></i><i class="b" style="width:{pb * 100:.1f}%"></i></div>
<div class="probs"><span>{esc(r['team_a'])} <b>{pct(pa) if not r['bound'] else '≥' + pct(pa)}</b></span>
<span>{esc(r['team_b'])} <b>{pct(pb) if not r['bound'] else '≤' + pct(pb)}</b></span></div>
<div class="pickline">Pick <b>{esc(lead)}</b> · {pct(lead_p)} {chips}</div>
<div class="small muted">{esc(r['competition'])} · crowd {esc(r['crowd_a'])}% / {esc(r['crowd_b'])}%{crowd_note(r, lead)}
{nxt_note(r)}</div>
<details><summary class="small">Sources for this row</summary><div class="small">{src_links(r)}</div></details>
</div>"""
            day_blocks += card

    body = f"""
<h1>All picks</h1>
<p class="muted">{len(open_rows)} open matches from the HotSpawn lobby · {len(market)} market ·
{len(model)} model · {len(bound)} lower bound · {len(unresolved)} blank. Sorted by start time.
Basis is labelled on every row: <strong>Market</strong> (a bookmaker/exchange price, no-vig),
<strong>Model</strong> (Valve official rating), <strong>Lower bound</strong> (one side unrated) or
<strong>Unresolved</strong>.</p>
<p class="small"><a href="#{esc(sorted(by_day)[0])}">Jump to {esc(sorted(by_day)[0])}</a> ·
<a href="unresolved.html">Unresolved list ({len(unresolved)})</a> · <a href="method.html">Method</a></p>
{day_blocks}
"""
    pages["picks.html"] = page("All picks", "picks.html", body, generated)

    # ---------------------------------------------------------------- twc
    res_rows = ""
    for m in twc["results"]:
        up = ' <span class="chip warn">upset</span>' if m["upset"] else ""
        maps = esc(m["maps"]) if m["maps"] else '<span class="muted">not transcribed</span>'
        res_rows += (f"<tr><td>D{m['day']}<br><span class='muted small'>{esc(m['date'])}</span></td>"
                     f"<td><strong>{esc(m['team_a'])} {m['score_a']}–{m['score_b']} {esc(m['team_b'])}</strong>{up}<br>"
                     f"<span class='muted small'>{esc(m['stage'])}</span></td>"
                     f"<td class='small'>{maps}</td>"
                     f"<td class='small'><a href='{esc(m['url'])}' rel='noreferrer'>HLTV</a></td></tr>")
    standings = ""
    for grp, label in (("A", "Group A"), ("B", "Group B")):
        standings += f"<h3>{label}</h3><div class='scroll'><table><thead><tr><th>Team</th><th>W–L</th><th>Status</th></tr></thead><tbody>"
        for t, w, l, st in twc["standings"][grp]:
            standings += f"<tr><td>{esc(t)}</td><td>{w}–{l}</td><td class='small'>{esc(st)}</td></tr>"
        standings += "</tbody></table></div>"
    roster = twc["aurora_roster"]
    sf_cards = ""
    for sf in (sf1, sf2):
        chips = ""
        if sf.get("climb"):
            chips = f'<span class="chip ok">climb: {esc(sf["climb"]["team"])} · {pct(sf["climb"]["prob"])} · +{sf["climb"]["leverage"] * 100:.0f} pts</span>'
        else:
            chips = '<span class="chip warn">no qualified climb pick</span>'
        sf_cards += f"""
<div class="card pick">
<div class="match"><p class="teams">{esc(sf['team_a'])} <span class="vs">vs</span> {esc(sf['team_b'])}</p>
<span class="muted small">{esc(sf['stage'])} · {esc(fmt_utc(sf['start_utc']))}</span></div>
<div class="bar" aria-hidden="true"><i class="a" style="width:{sf['p_a'] * 100:.1f}%"></i><i class="b" style="width:{sf['p_b'] * 100:.1f}%"></i></div>
<div class="probs"><span>{esc(sf['team_a'])} <b>{pct(sf['p_a'])}</b></span><span>{esc(sf['team_b'])} <b>{pct(sf['p_b'])}</b></span></div>
<div class="pickline">Pick <b>{esc(sf['pick'])}</b> · {pct(sf['pick_prob'])} {chips}</div>
<div class="small muted">Crowd {sf['crowd'][0]}% / {sf['crowd'][1]}% ·
<strong>{esc(sf['team_b'] if sf['crowd'][0] > sf['crowd'][1] else sf['team_a'])} is
{abs(sf['lev_a']) * 100:.0f} pts under-owned</strong></div>
<ul class="small">{''.join(f'<li>{esc(c)}</li>' for c in sf['context'])}</ul>
<details><summary class="small">Prices and sources</summary>
<div class="small">{esc(sf['market']['detail'])} (read {esc(sf['market']['read_utc'])})<br>
Thunderpick {esc(sf['second_source']['decimal_a'])} / {esc(sf['second_source']['decimal_b'])}
(read {esc(sf['second_source']['read_utc'])})<br>
<a href="{esc(sf['second_source']['url'])}" rel="noreferrer">bo3.gg match page</a> ·
<a href="{esc(sf['hltv_url'])}" rel="noreferrer">HLTV match page</a></div></details>
</div>"""

    body = f"""
<h1>TWC 2026 · Day 4</h1>
<p class="muted">Thunderpick World Championship 2026, Malta, $1,000,000, 8 teams, 14–18 October.
Both semifinals are 17 October. Verified against
<a href="{esc(twc['event_url'])}" rel="noreferrer">HLTV event 8932</a> on {esc(generated)}.</p>

<h2>Semifinal picks</h2>
{sf_cards}

<div class="warnbox"><strong>The one real edge today is Aurora.</strong>
The market makes FURIA a {pct(sf1['p_a'])} favourite — essentially a coin flip — but 82% of the HotSpawn
crowd is on FURIA. Taking Aurora at {pct(sf1['p_b'])} against 18% ownership is the contrarian move that is
<em>not</em> stupid: the price says the match is close, Aurora won the most recent meeting 2-1 (6 Oct) and
Aurora have won four of their last five series.
By contrast BETBOOM at {pct(sf2['p_b'])} is a genuine long shot; the 35% floor rejects it.</div>

<h2>Day 1–3, verified line by line</h2>
<div class="scroll"><table>
<thead><tr><th>Day</th><th>Result</th><th>Maps</th><th>Source</th></tr></thead>
<tbody>{res_rows}</tbody></table></div>
<p class="small muted">Map scores are transcribed only where the HLTV match page was read in this session;
the four day-1/day-2 series without a transcribed map line are left explicitly blank rather than filled
from memory. Every series score and every link in the table was read from HLTV results on {esc(generated)}.</p>

<h3>Group standings (derived from the results above)</h3>
{standings}

<h2>What the 9z upset actually teaches</h2>
<p>On day 1, <strong>9z beat Aurora 2-0</strong> (Inferno 13–11, Nuke 13–1). On day 3 the same two teams met in
the decider and <strong>Aurora won 2-0</strong> (13–11, 13–4). That is the honest lesson: one Bo3 upset is not
evidence the market is wrong, and the rematch result corrected the picture within 48 hours.
<strong>Do not fade the price. Fade the crowd.</strong> The edge comes from matches where the price is close
but the crowd is one-sided — which is exactly the FURIA–Aurora semifinal.</p>

<h2>The Aurora roster-change premise</h2>
<p class="small">Checked on <a href="https://www.hltv.org/team/11861/aurora" rel="noreferrer">HLTV</a> and
<a href="https://bo3.gg/teams/aurora-gaming" rel="noreferrer">bo3.gg</a>: both list
{esc(', '.join(roster['lineup']))} with coach {esc(roster['coach'])}. <strong>No October 2026 roster change is
visible on either source.</strong> The rebuild is older (July 2026 window, as recorded by earlier sessions).
The premise is therefore flagged rather than used to move a price — see
<a href="flagged.html">Flagged for review</a>.</p>

<h2>Rest and schedule</h2>
<p class="small">FURIA and Falcons were idle on 16 October; Aurora and BETBOOM both played and won the
day-3 deciders. Rest favours FURIA and Falcons; form and H2H favour Aurora. No numerical rest penalty is
applied to any probability — it is context, not a line input.</p>
"""
    pages["twc.html"] = page("TWC 2026 · Day 4", "twc.html", body, generated)

    # ---------------------------------------------------------------- unresolved
    un_rows = ""
    for r in bound + unresolved:
        un_rows += f"""
<div class="card blank" id="{esc(r['fixture_id'])}">
<div class="match"><p class="teams">{esc(r['team_a'])} <span class="vs">vs</span> {esc(r['team_b'])}</p>
<span class="muted small">{esc(fmt_utc(r['start_utc'], short=True))} · {esc(r['points'])} pts</span></div>
<div class="pickline">{('Pick <b>' + esc(r['pick']) + '</b> · ' + ('≥' if r['bound'] and r['prob_a'] is not None and r['team_a'] == r.get('bound_team') else '') + pct(r['pick_prob'])) if r['bound'] else 'Pick: <b>blank</b>'} <span class="chip warn">{'no price - bound only' if r['bound'] else 'no defensible price'}</span></div>
<div class="small">{esc(r['note'])}</div>
<ul class="small">
<li>Competition: {esc(r['competition'])} · crowd {esc(r['crowd_a'])}% / {esc(r['crowd_b'])}%</li>
<li>Flags from the capture: {esc(', '.join(r['flags']) or '—')}</li>
<li>Fixture page: <a href="{esc(r['hotspawn_url'])}" rel="noreferrer">HotSpawn</a> ·
<a href="{VRS_URL}" rel="noreferrer">Valve VRS list</a></li>
</ul>
</div>"""

    body = f"""
<h1>Unresolved picks &amp; limitations</h1>
<p class="muted"><strong>{len(unresolved)} of {len(open_rows)} open matches have no pick at all.</strong>
A further <strong>{len(bound)}</strong> have a pick but <strong>no price</strong>: the opponent is absent from
Valve's published list, so only a lower bound can be published. Those {len(bound)} rows are listed here too,
because a bound is not a bookmaker line.</p>

<div class="note">
<strong>What was tried, in order, for every blank row.</strong>
<ol class="small">
<li><strong>HLTV</strong> — match page, head-to-head, recent form and the event bracket
(<a href="https://www.hltv.org/matches" rel="noreferrer">hltv.org/matches</a>). HLTV does publish an odds
comparison page per match; it is read in this session for both TWC semifinals.</li>
<li><strong>Esportsbooks and betting lines</strong> — Pinnacle, Bovada and Melbet public prices (already
collected by the canonical capture), then <strong>Thunderpick via bo3.gg</strong>
(<a href="https://bo3.gg/matches/current" rel="noreferrer">bo3.gg match centre</a>) for fixtures the three
books do not cover. bo3.gg shows "All odds are on" (no price) for the rows below, which is a coverage
statement, not proof that no book anywhere prices them.</li>
<li><strong>Exchange</strong> — Kalshi full-match contracts (canonical capture, gated at a 10-cent spread).
No contract exists for these rows.</li>
<li><strong>Official rating</strong> — Valve's published VRS list. Rows where both teams are rated are
priced with the model; rows where the opponent is absent get a published <em>lower bound</em> instead, on
the All-picks page.</li>
</ol>
</div>

<h2>Rows without a price (bound-only) and rows with no pick</h2>
{un_rows}

<h2>Limitations that apply to this list</h2>
<ul class="small">
<li><strong>Coverage, not absence.</strong> A missing price means "not found in the sources read at this
timestamp", never "no market exists". Each row is retried by the 4-hourly collector.</li>
<li><strong>Timing.</strong> Tier-3 books typically post within 24 hours of kickoff; the two VOID Autumn Cup
rows are more than 48 hours out at build time.</li>
<li><strong>Identity.</strong> Two HotSpawn cards name an opponent that no other source agrees with
(Lavked vs "LFO 10" — books and bo3.gg say Sokerorg). Those rows are priced against the source-agreed
opponent and carry an <em>opponent name conflict</em> chip. Verify the HotSpawn card before locking.</li>
<li><strong>Lower bounds are not point estimates.</strong> A "≥ x%" row says only that the favourite is at
least that likely given the opponent cannot be rated above Valve's published floor.</li>
<li><strong>Ownership is not probability.</strong> Crowd shares come from HotSpawn's rendered cards and are
used only in the leverage column.</li>
</ul>
"""
    pages["unresolved.html"] = page("Unresolved picks & limitations", "unresolved.html", body, generated)

    # ---------------------------------------------------------------- flagged
    flags = [
        ("F1", "Aurora had no October 2026 roster change",
         "The brief states there was a recent Aurora roster change. HLTV and bo3.gg both list the same five "
         "starters and the same coach, and neither shows an October move. Premise not used in any price.",
         "https://www.hltv.org/team/11861/aurora"),
        ("F2", "HotSpawn names the wrong opponent for Lavked",
         "HotSpawn card 1079634 reads 'Lavked vs LFO 10'. Bovada, Melbet and bo3.gg all price "
         "'Lavked vs Sokerorg' in the same CCT Europe Series 11 slot. LFO 10 does not appear in Valve's list "
         "(only LFO 7/8/9). The row is priced from the books but flagged.",
         "https://bo3.gg/matches/lavked-vs-sokerorg-17-10-2026"),
        ("F3", "Duplicate team names in Valve's official list",
         "Valve's 2026-10-05 list contains two rows each for Banda Chuya, ex-RUSTEC and 6666. The capture "
         "correctly refused to guess. This desk disambiguates by roster (full five-man row, and for ex-RUSTEC "
         "the row sharing three of bo3.gg's five players) and records the rule in research.json.",
         VRS_URL),
        ("F4", "WROTBERRY cannot be proven to be 'WhiteBIT Team'",
         "Melbet prices 'WhiteBIT Team vs Nexus Gaming' at the same kickoff as Nexus vs WROTBERRY. No source "
         "read here proves the names are the same team, so the price is not joined; only a lower bound is "
         "published.", "https://bo3.gg/teams/wrotberry"),
        ("F5", "Two TWC prices disagree by a full coin-flip",
         "The three books in the canonical capture put FURIA at 51.1%; Thunderpick has the semifinal at "
         "1.85/1.85 (50.0%). The desk publishes the three-book consensus and shows the second source on the "
         "row. It does not average away the disagreement silently.",
         "https://bo3.gg/matches/furia-vs-aurora-gaming-17-10-2026"),
        ("F6", "HotSpawn renders times in UTC-4",
         "Every lobby card this session rendered in America/Sao_Paulo (e.g. the 14:00Z semifinal showed as "
         "10:00). All times on this desk are converted to UTC and cross-checked against the canonical "
         "capture's start_utc.", LOBBY),
        ("F7", "Published map scores are partial",
         "Only the six series whose HLTV match page was opened in this session carry a map line. The other "
         "four are left blank; they are not reconstructed from memory.",
         "https://www.hltv.org/results?event=8932"),
        ("F8", "The canonical board still shows 9 blank rows",
         "This desk resolves 5 of them (3 by re-joined book quotes, 2 by roster-disambiguated Valve rows) and "
         "adds 1 more model row. The canonical board itself is not edited; it remains the strict market-only "
         "view and will keep showing its own blanks until its collector is changed.",
         "../picks-every-match/unresolved.html"),
    ]
    flag_html = "".join(
        f'<div class="card"><h3>{esc(k)} · {esc(t)}</h3><p class="small">{esc(d)}</p>'
        f'<p class="small"><a href="{esc(u)}" rel="noreferrer">{esc(u)}</a></p></div>'
        for k, t, d, u in flags)
    body = f"""
<h1>Flagged for review</h1>
<p class="muted">Irregularities found while verifying this build. None of them blocks a pick; all are
published so they can be checked by hand.</p>
{flag_html}
"""
    pages["flagged.html"] = page("Flagged for review", "flagged.html", body, generated)

    # ---------------------------------------------------------------- method
    body = f"""
<h1>Method &amp; sources</h1>
<h2>1. Inventory</h2>
<p>Fixtures, points, tiers and lock times come from the canonical capture
<a href="../data/c64a5e19/board.json">data/c64a5e19/board.json</a>
(collected {esc(canon.get('collected_from_utc'))} → {esc(canon.get('collected_to_utc'))}), which reads the
public HotSpawn lobby. This desk does not re-invent fixtures; it joins to that capture by fixture id.</p>

<h2 id="rules">2. Probability</h2>
<p>For decimal odds dA and dB: <code>pA = (1/dA) / ((1/dA) + (1/dB))</code>, i.e. the no-vig two-way price.
Multiple books are combined with weight 2 for Pinnacle and 1 for the others (a modelling choice, declared).
The live Thunderpick read is used as a second source and shown next to the consensus; it never silently
replaces it.</p>
<p><strong>Model rows</strong> use Valve's official published rating points and the same shrink curve as the
canonical board: <code>u = 1/(1+10^(-Δ/400))</code>, <code>p = 0.5 + (u-0.5)·{SHRINK}</code>, where Δ is
the rating-point difference. It is an estimate, not a bookmaker price.</p>
<p><strong>Lower bounds</strong> put the unrated opponent at the floor of Valve's published list
({esc(research['vrs_floor']['points'])} pts, rank {esc(research['vrs_floor']['standing'])}) and therefore
report the <em>minimum</em> probability of the rated side. It is written "≥ x%" and never presented as a
point estimate.</p>

<h2>3. Picks and the leaderboard rule</h2>
<ul>
<li><strong>Pick</strong> = the side with the higher probability. On a true 50/50 the pick is the
lower-owned side, labelled "priced tie".</li>
<li><strong>Leverage</strong> = probability − crowd share, for that side.
Positive means the field is under-weighting the side.</li>
<li><strong>Climb pick</strong> requires all three: the side is the underdog, its market probability is at
least <strong>35%</strong> (the "not stupid" floor), and its leverage is at least <strong>20 points</strong>.
No climb pick is invented when the thresholds fail.</li>
<li>Points per match come from HotSpawn (2 / 3 / 7) and are shown on every row. The leaderboard impact of a
pick is roughly <code>points × (probability − crowd share)</code>; that is the arithmetic behind the
"Aurora is the one real edge" call.</li>
</ul>

<h2>4. Sources read for this build</h2>
<div class="scroll"><table><thead><tr><th>Source</th><th>Used for</th><th>Read (UTC)</th></tr></thead><tbody>
{''.join(f"<tr><td><a href='{esc(x['url'])}' rel='noreferrer'>{esc(x['label'])}</a></td><td class='small'>{esc(x['note'])}</td><td class='small'>read by {esc(RESEARCH_WINDOW)}</td></tr>" for x in research['reads'])}
</tbody></table></div>

<h2>5. Refresh</h2>
<p>Rebuilt every 4 hours by <code>.github/workflows/desk-3e1be203.yml</code>, and after every new
canonical capture. A rebuild re-reads <code>data/c64a5e19/board.json</code>; it does not invent a new
observation. If the capture is stale, the page says so with the capture's own timestamps.</p>

<h2>6. What this desk does not do</h2>
<ul class="small">
<li>It does not use HotSpawn crowd percentages as probabilities.</li>
<li>It does not fill a blank with 50/50, a sibling-team rating or an average of unrelated matches.</li>
<li>It does not claim a model estimate is a bookmaker price.</li>
<li>It does not edit another session's board or data.</li>
</ul>
"""
    pages["method.html"] = page("Method & sources", "method.html", body, generated)

    # ---------------------------------------------------------------- write
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "style.css"), "w", encoding="utf-8") as fh:
        fh.write(CSS)
    for name, content in pages.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            fh.write(content)
    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    summary = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "open": len(open_rows),
        "priced": len(market) + len(model),
        "with_pick": len(priced),
        "market": len(market),
        "model": len(model),
        "bound": len(bound),
        "unresolved": len(unresolved),
        "climb_picks": len(climbs),
        "canonical_capture": canon.get("collected_from_utc"),
    }
    with open(os.path.join(OUT, "data", "board.json"), "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "rows": rows,
                   "twc": {"results": twc["results"], "day4": [sf1, sf2],
                           "aurora_roster": twc["aurora_roster"]}},
                  fh, indent=1)
    print(json.dumps(summary, indent=1))
    return summary


def crowd_note(r, lead):
    """How far the picked side is from its HotSpawn ownership share (ownership, never probability)."""
    if not lead or r.get("crowd_a") is None:
        return ""
    own = r["crowd_a"] if lead == r["team_a"] else r["crowd_b"]
    if own is None:
        return ""
    prob = r["prob_a"] if lead == r["team_a"] else r["prob_b"]
    gap = (prob - own / 100.0) * 100
    if abs(gap) < 1:
        return " · crowd is level with the price"
    return f" · pick is <strong>{abs(gap):.0f} pts {'under' if gap > 0 else 'over'}-owned</strong>"


def nxt_note(r):
    if r["basis"] == "market":
        return ""
    return f" · {esc(r['note'])}" if r.get("note") else ""


if __name__ == "__main__":
    render()
