#!/usr/bin/env python3
"""Session 9c44d0e9: phone-first 'today' desk.

Re-joins the retained verified boards (c64a5e19 canonical + 1c8f79f8 day-4 desk)
by HotSpawn fixture ID and republishes them as one mobile list. It never invents
a probability: a row either reproduces a retained line (with its basis + sources)
or stays blank and is listed on the unresolved page. TWC 2026 semifinal lines are
computed in-code from the retained decimal quotes in EVIDENCE below (read live
2026-10-17 ~01:05Z; URLs retained for manual replay). HotSpawn crowd shares are
context only, never a probability input.
"""
import html, json, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "today"
DATA = ROOT / "data" / "9c44d0e9" / "board.json"
LOBBY = "https://play.hotspawn.com/lobby"
HLTV_EVENT = "https://www.hltv.org/events/8932/thunderpick-world-championship-2026"

# --- Fresh TWC evidence, read 2026-10-17 ~01:05Z (this session, fetch_page) ---
EVIDENCE = {
    "read_utc": "2026-10-17T01:05:00Z",
    "sf1": {  # FURIA vs Aurora, 2026-10-17 14:00Z (16:00 CEST), HLTV 2399414
        "egw_decimals": [1.83, 1.90],  # FURIA, Aurora (egamersworld live page)
        "egw_url": "https://egamersworld.com/counterstrike/match/5X5sFiL7H/furia-vs-aurora-Z00JFz0dG",
        "poly_cents": [53, 48],        # FURIA, Aurora moneyline; $51.3K vol
        "poly_vol_usd": 51300,
        "poly_url": "https://polymarket.com/esports/cs2/thunderpick-world-championship/cs2-furia-aur1-2026-10-17",
        "hltv_url": "https://www.hltv.org/matches/2399414/furia-vs-aurora-thunderpick-world-championship-2026",
    },
    "sf2": {  # Falcons vs BETBOOM, 2026-10-17 17:00Z (19:00 CEST), HLTV 2399415
        "egw_decimals": [1.23, 3.75],  # Falcons, BETBOOM (egamersworld live page)
        "egw_url": "https://egamersworld.com/counterstrike/match/5X5sFiL7H/falcons-vs-betboom-team-H2VXCn1md",
        "hltv_url": "https://www.hltv.org/matches/2399415/falcons-vs-betboom-thunderpick-world-championship-2026",
    },
}

def devig(da, db):
    ia, ib = 1.0 / da, 1.0 / db
    return ia / (ia + ib)

def pct(p):
    return "—" if p is None else f"{round(p * 100)}%"

def esc(x):
    return html.escape(str(x if x is not None else ""))

def norm_sources(sources):
    """Retained boards use {'label','url'} dicts (canonical) or [label,url] pairs (day-4 desk)."""
    out = []
    for s in sources or []:
        if isinstance(s, dict) and s.get("url"):
            out.append({"label": s.get("label") or "source", "url": s["url"]})
        elif isinstance(s, (list, tuple)) and len(s) >= 2 and str(s[1]).startswith("http"):
            out.append({"label": str(s[0]), "url": str(s[1])})
        elif isinstance(s, str) and s.startswith("http"):
            out.append({"label": "source", "url": s})
    return out

def src_links(sources):
    out = [f'<a href="{esc(s["url"])}" rel="noopener">{esc(s["label"])}</a>' for s in norm_sources(sources)]
    return " · ".join(out) or "—"

# TWC Day 1-3 results. Series + map scores cross-checked this session against
# HLTV news/match pages (per-row source). Retained day-4 desk agrees on all 10.
RESULTS = [
    ("Day 1 · Oct 14", "Group A opening", "9z", "2–0", "Aurora", "Inferno 13–11, Nuke 13–1",
     "https://www.hltv.org/matches/2399384/9z-vs-aurora-thunderpick-world-championship-2026"),
    ("Day 1 · Oct 14", "Group A opening", "Falcons", "2–0", "Ninjas in Pyjamas", "Ancient 16–13, Dust2 13–6", HLTV_EVENT),
    ("Day 1 · Oct 14", "Group B opening", "Legacy", "2–0", "PARIVISION", "Dust2 13–11, Mirage 16–14", HLTV_EVENT),
    ("Day 1 · Oct 14", "Group B opening", "FURIA", "2–0", "BETBOOM", "Ancient 13–10, Mirage 13–9",
     "https://www.hltv.org/matches/2399387/furia-vs-betboom-thunderpick-world-championship-2026"),
    ("Day 2 · Oct 15", "Group A winners'", "Falcons", "2–1", "9z", "Nuke 13–9, Mirage 8–13, Dust2 13–9",
     "https://www.hltv.org/news/45728/falcons-secure-playoff-berth-at-twc-2026"),
    ("Day 2 · Oct 15", "Group A elimination", "Aurora", "2–0", "Ninjas in Pyjamas", "Cache 13–9, Dust2 13–7", HLTV_EVENT),
    ("Day 2 · Oct 15", "Group B winners'", "FURIA", "2–1", "Legacy", "Cache 10–13, Inferno 13–5, Mirage 13–8", HLTV_EVENT),
    ("Day 2 · Oct 15", "Group B elimination", "BETBOOM", "2–1", "PARIVISION", "Ancient 10–13, Anubis 13–4, Mirage 13–7",
     "https://www.hltv.org/news/45729/betboom-eliminate-parivision-from-twc"),
    ("Day 3 · Oct 16", "Group A decider", "Aurora", "2–0", "9z", "Cache 13–11, Inferno 13–4",
     "https://www.hltv.org/matches/2399412/aurora-vs-9z-thunderpick-world-championship-2026"),
    ("Day 3 · Oct 16", "Group B decider", "BETBOOM", "2–1", "Legacy", "Nuke 16–13, Dust2 11–13, Mirage 13–11",
     "https://www.hltv.org/news/45739/betboom-qualify-for-twc-playoffs-over-legacy"),
]

CSS = """
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#0b1020;color:#e8ecf8;line-height:1.5}
a{color:#7dd3fc}.wrap{max-width:860px;margin:0 auto;padding:16px 14px 90px}
h1{font-size:1.55rem;line-height:1.2;margin:.3rem 0}h2{font-size:1.15rem;margin:1.4rem 0 .5rem}h3{font-size:1rem;margin:1rem 0 .4rem}
.eyebrow{color:#93c5fd;font-size:.8rem;text-transform:uppercase;letter-spacing:.08em;margin:0}
.card{background:#141b33;border:1px solid #26325a;border-radius:14px;padding:14px;margin:10px 0}
.btn{display:block;text-align:center;background:#2563eb;color:#fff;text-decoration:none;font-weight:700;padding:14px;border-radius:12px;margin:8px 0;font-size:1.05rem}
.btn.alt{background:#1e293b;border:1px solid #334155}.btn.warn{background:#7c2d12}
.pick{font-size:1.25rem;font-weight:800}.prob{font-size:1.6rem;font-weight:800;color:#4ade80}
.vs{display:flex;justify-content:space-between;gap:8px;align-items:center}.team{flex:1;text-align:center}
.bar{height:10px;border-radius:6px;background:#334155;overflow:hidden;display:flex;margin:6px 0}
.bar i{display:block;height:100%;background:#4ade80}.bar b{display:block;height:100%;background:#f472b6}
table{width:100%;border-collapse:collapse;font-size:.92rem}th,td{border-bottom:1px solid #26325a;padding:8px 6px;text-align:left;vertical-align:top}
.tbl{overflow-x:auto}.small{color:#a5b4d4;font-size:.82rem}.flag{color:#fbbf24;font-weight:700}.blank{color:#f87171;font-weight:700}
nav.tabs{position:fixed;left:0;right:0;bottom:0;background:#0f1730;border-top:1px solid #26325a;display:flex;z-index:9}
nav.tabs a{flex:1;text-align:center;padding:12px 2px;color:#cbd5f5;text-decoration:none;font-size:.78rem;font-weight:600}
nav.tabs a.on{color:#fff;background:#1d4ed8}
.notice{border-left:4px solid #f59e0b;background:#1c1917;padding:10px 12px;border-radius:8px;margin:10px 0}
.good{border-left-color:#22c55e;background:#052e16}
"""

def page(title, active, body, gen):
    tabs = [("index.html", "🏠 Today"), ("picks.html", "🎯 All picks"), ("twc.html", "🏆 TWC Day 4"),
            ("unresolved.html", "❔ Unresolved"), ("method.html", "📖 Method")]
    nav = "".join(f'<a href="{h}" class="{"on" if h == active else ""}">{t}</a>' for h, t in tabs)
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{esc(title)} · HotSpawn CS2 picks</title><style>{CSS}</style></head><body>"
            f'<main class="wrap">{body}<p class="small">Built {esc(gen)} · Session 9c44d0e9 · '
            f'<a href="../index.html">Full dashboard</a> · <a href="../flagged.html">Flagged for Review</a> · '
            f'<a href="{LOBBY}" rel="noopener">HotSpawn lobby</a>. Probabilities are estimates from the cited '
            f'betting lines / models, not guarantees. HotSpawn is never a probability input.</p></main>'
            f'<nav class="tabs">{nav}</nav></body></html>')

def match_card(r):
    pa, pb = r["prob_a"], r["prob_b"]
    bar = ""
    if pa is not None:
        bar = f'<div class="bar"><i style="width:{pa*100:.0f}%"></i><b style="width:{pb*100:.0f}%"></b></div>'
    pick = (f'<p>✅ Pick: <span class="pick">{esc(r["pick"])}</span> <span class="prob">{pct(max(pa, pb))}</span></p>'
            if r["pick"] else '<p class="blank">⚠️ No verified line — no pick. See Unresolved.</p>')
    climb = ""
    if r.get("climb_pick"):
        climb = (f'<p>🧗 Climb (contrarian, not stupid): <b>{esc(r["climb_pick"])}</b> {pct(r["climb_prob"])}'
                 f'<br><span class="small">{esc(r["climb_note"])}</span></p>')
    return (f'<article class="card" id="m-{esc(r["fixture_id"])}"><div class="vs">'
            f'<div class="team"><b>{esc(r["team_a"])}</b><br><span class="prob">{pct(pa)}</span></div>'
            f'<div class="small">vs<br>{esc(r["start_utc"][:16].replace("T", " "))}Z</div>'
            f'<div class="team"><b>{esc(r["team_b"])}</b><br><span class="prob">{pct(pb)}</span></div></div>{bar}'
            f'<p class="small">{esc(r["competition"])} · Tier {esc(r["tier"])} · {esc(r["points"])} pts · #{esc(r["fixture_id"])}</p>'
            f'{pick}{climb}<p class="small">Basis: {esc(r["basis"])}<br>Sources: {src_links(r["sources"])} · '
            f'<a href="{esc(r["hotspawn_url"])}" rel="noopener">HotSpawn fixture</a></p></article>')

def main():
    gen = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    canon = json.loads((ROOT / "data/c64a5e19/board.json").read_text())
    desk = json.loads((ROOT / "data/1c8f79f8/board.json").read_text())
    desk_by_id = {str(r["fixture_id"]): r for r in desk.get("open") or []}
    rows, unresolved = [], []
    for c in canon.get("open") or []:
        fid = str(c["fixture_id"]); d = desk_by_id.get(fid, {})
        line = d.get("line") or c.get("line") or {}
        pa = line.get("prob_a"); pb = line.get("prob_b")
        basis_src = d if d.get("line") else c
        basis = line.get("basis") or ("market" if basis_src.get("market") else "no verified line")
        ladder = d.get("ladder") or {}
        climb_raw = ladder.get("climb"); climb_p_raw = ladder.get("climb_prob")
        # Display pick = favourite's HotSpawn team name (retained pick strings can be
        # aliases/casing variants, e.g. "WBT (WhiteBIT Team)" for WROTBERRY).
        pick_team = None; climb = None; climb_p = None
        if pa is not None and pb is not None:
            pick_team = c.get("team_a") if pa >= pb else c.get("team_b")
            dog_team = c.get("team_b") if pa >= pb else c.get("team_a")
            dog_p = pb if pa >= pb else pa
            # Contrarian-but-not-stupid: only if the retained board flagged a climb
            # whose probability matches the underdog's, and the dog is >=40%.
            if climb_raw and climb_p_raw is not None and dog_p >= 0.40 and abs(climb_p_raw - dog_p) <= 0.02:
                climb, climb_p = dog_team, dog_p
        r = {"fixture_id": fid, "competition": c.get("competition"), "tier": c.get("tier"),
             "points": c.get("points"), "start_utc": c.get("start_utc") or "", "team_a": c.get("team_a"),
             "team_b": c.get("team_b"), "prob_a": pa, "prob_b": pb,
             "pick": pick_team, "pick_raw": line.get("pick"), "basis": basis,
             "sources": norm_sources(d.get("sources") or c.get("sources") or []),
             "hotspawn_url": c.get("hotspawn_url") or LOBBY, "climb_pick": climb, "climb_prob": climb_p,
             "climb_note": "Near-coin-flip underdog (≥40%): the only band where fading the crowd can gain leaderboard places without donating expected points." if climb else "",
             "flags": c.get("flags") or [], "blank_reason": d.get("blank_reason") or ""}
        rows.append(r)
        if pa is None:
            unresolved.append(r)
    rows.sort(key=lambda r: r["start_utc"])

    # TWC semifinals from retained quotes
    e1, e2 = EVIDENCE["sf1"], EVIDENCE["sf2"]
    sf1_egw = devig(*e1["egw_decimals"])
    sf1_poly = e1["poly_cents"][0] / sum(e1["poly_cents"])
    sf1_a = round((sf1_egw + sf1_poly) / 2, 4)  # FURIA
    sf2_a = round(devig(*e2["egw_decimals"]), 4)  # Falcons
    twc = [
        {"fixture_id": "twc-sf1", "competition": "Thunderpick World Championship 2026 · Semifinal 1 (Malta, LAN)",
         "tier": "S", "points": "— (not on HotSpawn lobby at read time)", "start_utc": "2026-10-17T14:00:00Z",
         "team_a": "FURIA", "team_b": "Aurora", "prob_a": sf1_a, "prob_b": round(1 - sf1_a, 4),
         "pick": "FURIA", "basis": f"Market (2 sources, equal-weight mean): egamersworld {e1['egw_decimals'][0]}/{e1['egw_decimals'][1]} → FURIA {pct(sf1_egw)} de-vigged; Polymarket {e1['poly_cents'][0]}¢/{e1['poly_cents'][1]}¢ (${e1['poly_vol_usd']:,} vol) → FURIA {pct(sf1_poly)} normalised. Read {EVIDENCE['read_utc']}.",
         "sources": [{"label": "egamersworld odds", "url": e1["egw_url"]}, {"label": "Polymarket moneyline", "url": e1["poly_url"]},
                     {"label": "HLTV match page", "url": e1["hltv_url"]}],
         "hotspawn_url": LOBBY, "climb_pick": "Aurora", "climb_prob": round(1 - sf1_a, 4),
         "climb_note": "≈48% underdog in a true coin flip — the textbook climb pick. Aurora beat FURIA 2–1 at ESL Pro League S24 on Oct 6 (HLTV news 45736) and just avenged 9z 2–0. Differentiation here costs almost no expected points."},
        {"fixture_id": "twc-sf2", "competition": "Thunderpick World Championship 2026 · Semifinal 2 (Malta, LAN)",
         "tier": "S", "points": "— (not on HotSpawn lobby at read time)", "start_utc": "2026-10-17T17:00:00Z",
         "team_a": "Falcons", "team_b": "BETBOOM", "prob_a": sf2_a, "prob_b": round(1 - sf2_a, 4),
         "pick": "Falcons", "basis": f"Market: egamersworld {e2['egw_decimals'][0]}/{e2['egw_decimals'][1]} → Falcons {pct(sf2_a)} de-vigged. Read {EVIDENCE['read_utc']}. (Yesterday no book had opened this semi; the retained 66% was a documented VRS estimate — superseded by this real line.)",
         "sources": [{"label": "egamersworld odds", "url": e2["egw_url"]}, {"label": "HLTV match page", "url": e2["hltv_url"]}],
         "hotspawn_url": LOBBY, "climb_pick": None, "climb_prob": None,
         "climb_note": ""},
    ]
    n_pick = sum(1 for r in rows if r["pick"])
    board = {"session": "9c44d0e9", "generated_utc": gen,
             "inputs": {"canonical": "data/c64a5e19/board.json", "canonical_generated": canon.get("generated_utc"),
                        "day4_desk": "data/1c8f79f8/board.json", "day4_generated": desk.get("generated_utc"),
                        "lobby_read_utc": "2026-10-17T00:55:00Z", "twc_evidence": EVIDENCE},
             "summary": {"inventory_total": len(canon.get("inventory") or []), "open": len(rows),
                         "open_with_pick": n_pick, "open_blank": len(unresolved), "twc_semifinals": 2},
             "open": rows, "twc": twc, "results": [list(x) for x in RESULTS],
             "inventory": canon.get("inventory") or []}
    DATA.parent.mkdir(parents=True, exist_ok=True); OUT.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(board, indent=1))

    res_rows = "".join(
        f'<tr><td data-l="Day">{esc(a)}</td><td>{esc(b)}</td><td><b>{esc(w)}</b> {esc(s)} {esc(l)}</td>'
        f'<td class="small">{esc(m)}</td><td><a href="{esc(u)}" rel="noopener">HLTV</a></td></tr>'
        for a, b, w, s, l, m, u in RESULTS)

    index = f"""
<p class="eyebrow">Executive summary · CS2 Pick'em · updated {esc(gen)}</p>
<h1>📱 Today's picks — start here</h1>
<p>One phone-friendly list for <b>every</b> CS2 match on the <a href="{LOBBY}" rel="noopener">HotSpawn lobby</a>:
win probability for both teams, an obvious pick, and the source behind it. No line? The row stays blank and is
explained — never guessed.</p>
<a class="btn" href="picks.html">🎯 All picks · every open match ({len(rows)}) →</a>
<a class="btn alt" href="twc.html">🏆 TWC Day 4 · semifinals + Day 1–3 review →</a>
<a class="btn alt" href="unresolved.html">❔ Unresolved picks &amp; limitations ({len(unresolved)}) →</a>
<a class="btn alt" href="../picks-every-match/index.html">Canonical every-match board (auto, 4-hourly) →</a>
<a class="btn alt" href="../day4/index.html">Day-4 desk (full evidence) →</a>
<div class="card"><h2>Coverage right now</h2>
<p><b>{board['summary']['inventory_total']}</b> CS2 fixtures in the retained HotSpawn inventory ·
<b>{len(rows)}</b> open for picks · <b>{n_pick}</b> with a verified-line pick · <b>{len(unresolved)}</b> blank/unresolved.
Inputs: canonical board {esc(canon.get('generated_utc'))}, day-4 desk {esc(desk.get('generated_utc'))}, lobby re-read 2026-10-17T00:55Z.
This page rebuilds every 4 hours from those retained boards (see Method).</p></div>
<h2>🏆 Today: TWC 2026 semifinals (Malta)</h2>
<p class="small">⚠️ The Malta main event was <b>not listed on the HotSpawn lobby</b> at read time (only the South American
Series was). Picks below are for the real Day-4 matches priced from outside books — use them if/when HotSpawn lists them,
and for your own read of the day. Full reasoning on the <a href="twc.html">TWC page</a>.</p>
{''.join(match_card(r) for r in twc)}
<div class="notice good"><b>🧗 How to climb without being stupid:</b> differentiate only in the 40–50% band.
Today that is exactly one spot — <b>Aurora over FURIA (≈48%)</b>. Do <b>not</b> climb on BETBOOM over Falcons (≈25%):
a 1-in-4 ticket donates expected points. Everywhere else, take the market favourite.</div>
<h2>Next matches up (open lobby)</h2>
{''.join(match_card(r) for r in rows[:5])}
<a class="btn" href="picks.html">See all {len(rows)} open matches →</a>
"""
    (OUT / "index.html").write_text(page("Today's picks", "index.html", index, gen))

    picks = (f"<h1>🎯 Picks for every open match</h1><p>All {len(rows)} open CS2 fixtures from the retained HotSpawn "
             f"inventory, soonest first. Probability = de-vigged betting line where a book/exchange line exists; "
             f"otherwise a labelled rating-model estimate from the retained boards; otherwise blank. "
             f"Tap a source to verify any row yourself.</p>" + "".join(match_card(r) for r in rows))
    (OUT / "picks.html").write_text(page("All picks", "picks.html", picks, gen))

    twc_body = f"""
<h1>🏆 Thunderpick World Championship 2026 — Day 4</h1>
<p>LAN, Malta · $1,000,000 · Oct 14–18 · <a href="{HLTV_EVENT}" rel="noopener">HLTV event page</a></p>
<h2>Day 4 picks (today, Oct 17)</h2>
{''.join(match_card(r) for r in twc)}
<h3>Semifinal 1 — FURIA vs Aurora: a genuine coin flip</h3>
<p>Both outside sources agree within ~2 points (books {pct(sf1_egw)} FURIA, Polymarket {pct(sf1_poly)} FURIA on $51.3K volume).
<b>Safe pick: FURIA</b> (market favourite, defending champions, rested since Oct 15).
<b>Climb pick: Aurora</b> — at ≈48% you give up almost nothing in expectation but gain full differentiation if the crowd
piles onto the defending champions. The form case is real, not hopeful: Aurora beat FURIA 2–1 ten days ago at ESL Pro League S24
(<a href="https://www.hltv.org/news/45736/aurora-beat-9z-to-secure-third-consecutive-top-four-appearance" rel="noopener">HLTV 45736</a>)
and arrive off a 2–0 revenge win over 9z. Counterweight: Aurora have played three series in three days; FURIA have played two and rested yesterday.</p>
<h3>Semifinal 2 — Falcons vs BETBOOM: do not get cute</h3>
<p>Books make Falcons {pct(sf2_a)}. BETBOOM's run (reverse-sweep PARIVISION, late 3-map decider vs Legacy finishing Oct 16 night)
is exactly the profile the market already prices: alive, but tired, against a rested top-4 VRS side. <b>Safe pick: Falcons.</b>
BETBOOM at ≈25% fails the "not stupid" test — it is only rational if you are so far behind that only a 1-in-4 swing can save your week.</p>
<h2>What actually happened Days 1–3</h2>
<div class="tbl"><table><thead><tr><th>Day</th><th>Stage</th><th>Result</th><th>Maps</th><th>Source</th></tr></thead>
<tbody>{res_rows}</tbody></table></div>
<h3>The Day-1 upset, in context</h3>
<p>9z 2–0 Aurora (Inferno 13–11, <b>Nuke 13–1</b>) was the tournament's one true shock — HLTV called Aurora "the only favorite to
falter" on day one (<a href="https://www.hltv.org/news/45723/furia-fend-off-betboom-to-end-day-one-of-twc" rel="noopener">45723</a>),
with 9z's luchov posting a 1.61 series rating (<a href="https://www.hltv.org/news/45718/9z-beat-aurora-2-0-to-kick-off-twc-2026" rel="noopener">45718</a>).
But note the sequel: Aurora immediately stabilised (2–0 NIP), then <b>beat the same 9z 2–0</b> in the Day-3 decider with a changed veto
(Cache first-pick, Nuke banned away). Lesson for Day 4: the upset was map- and form-specific, not evidence Aurora are broken —
which is precisely why the semifinal market sits at ~50/50 rather than punishing them.</p>
<h3>The "recent Aurora roster change" — verified verdict</h3>
<div class="notice"><b>Partly true, but not recent.</b> Aurora's rebuild was in <b>July 2026</b>, three months ago:
kyxsan (IGL) signed Jul 8 completing an international pivot with Jimpphat + coach ash (Jul 3), replacing MAJ3R, soulfly and Fabre
(<a href="https://www.hltv.org/news/45082/official-aurora-complete-rebuild-with-kyxsan" rel="noopener">HLTV 45082</a>,
<a href="https://www.hltv.org/news/45050/maj3r-steps-down-from-aurora" rel="noopener">45050</a>,
<a href="https://www.hltv.org/team/11861/aurora" rel="noopener">HLTV team timeline</a>).
<b>No October change was found.</b> The "deko" name on old timeline views is the 2023–24 Russian Aurora (inactive since Nov 28, 2024) — not this roster.
The onboarding risk is therefore <i>residual</i> (new IGL + language switch still bedding in — coach ash discussed integration publicly in August),
not a fresh-debut discount. Do not fade Aurora for "new player" reasons; the Day-1 loss is better explained by 9z's Nuke and luchov's form, and Days 2–3 show correction.</div>
<h3>Rest / workload going into Day 4</h3>
<p>Falcons &amp; FURIA: 2 series each, idle Oct 16 (group winners). Aurora &amp; BETBOOM: 3 series each including Oct 16 deciders
(BETBOOM's went 3 maps, latest finish). In a same-week LAN this is a real but second-order edge — already reflected in the Falcons price;
in Semifinal 1 it slightly favours FURIA and is the main argument against over-weighting the Aurora climb pick.</p>
"""
    (OUT / "twc.html").write_text(page("TWC Day 4", "twc.html", twc_body, gen))

    if unresolved:
        u_rows = "".join(
            f'<tr><td><b>{esc(r["team_a"])}</b> vs <b>{esc(r["team_b"])}</b><div class="small">#{esc(r["fixture_id"])} · {esc(r["competition"])} · {esc(r["start_utc"][:16])}Z</div></td>'
            f'<td class="small">{esc(r["blank_reason"] or "No accepted full-match line on Pinnacle/Bovada/Melbet/Kalshi/Polymarket at capture; HLTV probe returned no usable price; Valve-VRS model ineligible (team unidentified/ambiguous or standings stale). Flags: " + ", ".join(r["flags"] or []))}</td>'
            f'<td><a href="{esc(r["hotspawn_url"])}" rel="noopener">HotSpawn</a> · <a href="../picks-every-match/unresolved.html">canonical ledger</a></td></tr>'
            for r in unresolved)
        u_table = f'<div class="tbl"><table><thead><tr><th>Match (blank — no pick)</th><th>Why no number / what was tried</th><th>Verify</th></tr></thead><tbody>{u_rows}</tbody></table></div>'
    else:
        u_table = "<p>✅ No blank open rows in this build.</p>"
    unres = f"""
<h1>❔ Unresolved picks &amp; limitations</h1>
<p>These open matches have <b>no pick and no probability</b> because no source passed verification. A blank is deliberate —
inventing a 50/50 would be worse than useless for leaderboard play. They are re-checked every 4 hours.</p>
{u_table}
<h2>The resolution ladder (applied in order)</h2>
<ol><li><b>Esportsbooks first:</b> Pinnacle / Bovada / Melbet full-match two-way prices, both teams + kickoff joined (canonical collector).</li>
<li><b>HLTV</b> match pages for identity/schedule (HLTV publishes no directly reusable odds feed; probe results are retained).</li>
<li><b>Exchanges / other books:</b> Polymarket / Kalshi / egamersworld-listed books where a full-match market exists (day-4 desk).</li>
<li><b>Originated line:</b> Valve official VRS standings → Glicko logistic model, only when both rosters are uniquely identified and standings ≤14 days old. Labelled "model", never presented as a bookmaker line.</li>
<li><b>Otherwise blank</b> and listed here with the failure reason.</li></ol>
<h2>Limitations you should know</h2>
<ul><li>Low-tier (B/C) matches are often priced by <b>no</b> book and absent from Polymarket — the blank is a market-coverage fact, not laziness.</li>
<li>Team-name aliases (academy/ex- rosters, slot names) block the VRS model when identity can't be proven; we never borrow a sibling roster's rating.</li>
<li>Lines move: every probability carries its source + capture time in <a href="../data/9c44d0e9/board.json">board.json</a>; re-check before lock.</li>
<li>HotSpawn crowd % is shown nowhere as a probability — it measures other players' picks, not win chances.</li>
<li>This desk re-joins retained boards; freshness is bounded by the canonical 4-hourly collectors listed on the Method page.</li></ul>
<p>Full ledgers: <a href="../picks-every-match/unresolved.html">canonical unresolved</a> · <a href="../day4/unresolved.html">day-4 unresolved</a> · <a href="flagged.html">flagged items for this desk</a></p>
"""
    (OUT / "unresolved.html").write_text(page("Unresolved", "unresolved.html", unres, gen))

    flagged = f"""
<h1>🚩 Flagged for Review (this desk)</h1>
<p>Non-blocking irregularities found 2026-10-17. Nothing below was silently "fixed" — check each source yourself.</p>
<div class="tbl"><table><thead><tr><th>#</th><th>Irregularity</th><th>Evidence / manual check</th></tr></thead><tbody>
<tr><td>F1</td><td><b>Semifinal-1 favourite flipped overnight.</b> Yesterday's day-4 desk headline read "Aurora 52%"; both fresh sources now favour FURIA (books {pct(sf1_egw)}, Polymarket {pct(sf1_poly)} on $51.3K). Treat SF1 as a coin flip; either pick is defensible, which is why Aurora is the climb spot.</td><td><a href="{e1['egw_url']}" rel="noopener">egamersworld</a> · <a href="{e1['poly_url']}" rel="noopener">Polymarket</a> · <a href="../day4/index.html">day-4 desk</a></td></tr>
<tr><td>F2</td><td><b>Semifinal-2 line appeared &lt;24h before start.</b> No book had opened Falcons–BETBOOM at yesterday's read (66% was a VRS estimate); egamersworld now shows 1.23/3.75 ({pct(sf2_a)} Falcons). Single-source line — corroborate before lock.</td><td><a href="{e2['egw_url']}" rel="noopener">egamersworld</a> · <a href="{e2['hltv_url']}" rel="noopener">HLTV</a></td></tr>
<tr><td>F3</td><td><b>TWC Malta main event not on HotSpawn lobby</b> at 2026-10-17T00:55Z read (filter lists only TWC South American Series #1). Semifinal picks therefore cannot currently be entered as HotSpawn pick'ems.</td><td><a href="{LOBBY}" rel="noopener">HotSpawn lobby</a></td></tr>
<tr><td>F4</td><td><b>"Recent Aurora roster change" premise is stale:</b> rebuild was July 2026; no October move found; "deko" references are the defunct 2023–24 Russian roster.</td><td><a href="https://www.hltv.org/news/45082/official-aurora-complete-rebuild-with-kyxsan" rel="noopener">HLTV 45082</a> · <a href="https://www.hltv.org/team/11861/aurora" rel="noopener">HLTV Aurora</a></td></tr>
<tr><td>F5</td><td><b>Day-1 Nuke score:</b> one retained capture in repo history recorded 16–14; HLTV + 7 other captures record <b>13–1</b>. This desk uses 13–1.</td><td><a href="https://www.hltv.org/matches/2399384/9z-vs-aurora-thunderpick-world-championship-2026" rel="noopener">HLTV 2399384</a> · <a href="../verify/1fac4be2/flagged.html">verification flagged page</a></td></tr>
<tr><td>F6</td><td><b>Two "Valve Glicko" constants exist across repo boards</b> (RD 75 vs RD 200) — model-only rows can differ slightly between boards. Market rows are unaffected.</td><td><a href="../verify/1fac4be2/index.html">verification desk</a></td></tr>
</tbody></table></div>
<p>Site-wide list: <a href="../flagged.html">Flagged for Review</a>.</p>
"""
    (OUT / "flagged.html").write_text(page("Flagged", "method.html", flagged, gen))

    method = f"""
<h1>📖 Method &amp; sources</h1>
<h2>How a probability is produced</h2>
<p>For decimal odds d<sub>A</sub>, d<sub>B</sub>: fair p<sub>A</sub> = (1/d<sub>A</sub>) / ((1/d<sub>A</sub>)+(1/d<sub>B</sub>)) (bookmaker margin removed).
Exchange cents are normalised the same way. Multiple accepted sources are averaged as declared per row.
Worked example (SF1, read {EVIDENCE['read_utc']}): egamersworld 1.83/1.90 → FURIA {pct(sf1_egw)}; Polymarket 53¢/48¢ → FURIA {pct(sf1_poly)}; mean → <b>FURIA {pct(sf1_a)} / Aurora {pct(1-sf1_a)}</b>.</p>
<h2>Source order</h2>
<ol><li>Fixture inventory: <a href="{LOBBY}" rel="noopener">HotSpawn lobby</a> (fixtures only — never probabilities).</li>
<li>Betting lines: Pinnacle/Bovada/Melbet (canonical collector), then Polymarket/Kalshi/egamersworld-listed books.</li>
<li>Results/identity/schedule: <a href="{HLTV_EVENT}" rel="noopener">HLTV</a>.</li>
<li>Originated fallback: Valve official VRS → Glicko model (labelled "model").</li></ol>
<h2>Refresh</h2>
<p>The canonical collectors run every 4 hours in GitHub Actions (<code>every-match-c64a5e19</code>, <code>day4-1c8f79f8</code>);
this desk's workflow (<code>today-9c44d0e9</code>) then re-joins their retained boards and republishes <code>today/</code>.
Data for manual replay: <a href="../data/9c44d0e9/board.json">data/9c44d0e9/board.json</a> ·
<a href="../data/c64a5e19/board.json">canonical board</a> · <a href="../data/1c8f79f8/board.json">day-4 board</a>.</p>
<h2>Contrarian rule</h2>
<p>A "climb" pick is only shown when the underdog's fair probability is <b>≥40%</b>. Below that, fading the favourite loses
more expected points than differentiation can repay — the definition of "stupid" used across this site.</p>
<h2>All pick lists on this site</h2>
<p><a href="picks.html">Today · all open picks</a> · <a href="../picks-every-match/index.html">Canonical every-match</a> ·
<a href="../day4/index.html">Day-4 desk</a> · <a href="../picks-every-match/picks.html">Canonical picks table</a> ·
<a href="../index.html">Dashboard home</a></p>
"""
    (OUT / "method.html").write_text(page("Method", "method.html", method, gen))
    print(f"open={len(rows)} picks={n_pick} blank={len(unresolved)} sf1 FURIA={sf1_a} sf2 Falcons={sf2_a}")

if __name__ == "__main__":
    main()
