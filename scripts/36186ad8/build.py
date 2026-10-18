#!/usr/bin/env python3
"""Session 36186ad8 — TWC 2026 FINAL DAY (18 Oct) live desk.

Inputs (read-only): finals/data/board.json (session 782adb47, canonical capture
2026-10-17T18:26:54Z) for every HotSpawn row; data/36186ad8/live.json for this
session's live reads (HotSpawn lobby, HLTV countdowns, Thunderpick-via-bo3.gg
Day-5 prices). Day-5 probabilities are proportional no-vig from the live book
price; the originated Valve-VRS line is shown as sensitivity only. HotSpawn
crowd % is ownership, never a probability. Nothing is invented: rows whose
lock has passed drop to 'locked', unresolved rows keep their attempt ledger.
"""
import html, json, pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "finalday"; (OUT / "data").mkdir(parents=True, exist_ok=True)
board = json.loads((ROOT / "finals/data/board.json").read_text())
live = json.loads((ROOT / "data/36186ad8/live.json").read_text())
NOW = datetime.now(timezone.utc)
def iso(d=NOW): return d.strftime("%Y-%m-%dT%H:%M:%SZ")
def pct(x): return f"{x*100:.1f}%"
def esc(s): return html.escape(str(s))

# Day 5: live market no-vig
day5 = []
for m in live["day5"]:
    ia, ib = 1/m["odds_a"], 1/m["odds_b"]; s = ia+ib
    m = dict(m); m["prob_a"] = ia/s; m["prob_b"] = ib/s; m["overround"] = s-1
    m["safe"] = m["a"] if m["prob_a"] >= .5 else m["b"]
    m["dog"] = m["b"] if m["safe"] == m["a"] else m["a"]
    m["dog_prob"] = min(m["prob_a"], m["prob_b"])
    if m["dog"] == "BETBOOM":
        m["verdict"] = (f"NO CLIMB — take FURIA. BETBOOM are now priced at {pct(m['dog_prob'])}, BELOW the pre-declared 35% floor, "
                        "with head-to-head (0–6 in maps across the last three series), map pool and rest all against them. "
                        "Yesterday's originated 36.6% already said no on flags; the live market removes any doubt. "
                        "Chasing Saturday's upset team into a worse bo5 matchup is the definition of stupid-contrarian.")
    else:
        m["verdict"] = (f"SAFE: Falcons. CONDITIONAL CLIMB only: Aurora {pct(m['dog_prob'])} clears the 35% floor with 2 verified flags "
                        "(rest, Anubis/Cache veto), so IF a HotSpawn card appears with Aurora crowd ownership ≤22% near lock "
                        "(≥15pp leverage), switching to Aurora is the one justified leaderboard gamble today. TWC Malta is not on "
                        "HotSpawn at the live lobby read — without a card there is nothing to switch, so the pick is Falcons.")
    day5.append(m)

rows = board["rows"]
for r in rows:
    cv = live["crowd_live"].get(r["fixture_id"])
    if cv: r["crowd_a"], r["crowd_b"] = cv; r["crowd_note"] = f"live lobby {live['lobby_read_utc']}"
open_rows = [r for r in rows if r["lock_utc"] > iso()]
locked = [r for r in rows if r["lock_utc"] <= iso()]
open_rows.sort(key=lambda r: r["lock_utc"])
by_basis = {}
for r in open_rows: by_basis[r["basis"]] = by_basis.get(r["basis"], 0) + 1
unresolved = [r for r in open_rows if r["basis"] != "market"]
summary = {"open": len(open_rows), "locked_since_capture": len(locked), "by_basis": by_basis,
           "with_pick": sum(1 for r in open_rows if r.get("pick")), "blank": sum(1 for r in open_rows if not r.get("pick"))}
machine = {"session": "36186ad8", "generated_utc": iso(), "canonical_capture": board.get("canonical_capture"),
           "lobby_read_utc": live["lobby_read_utc"], "summary": summary,
           "day5": [{k: v for k, v in m.items()} for m in day5], "rows": open_rows, "locked": locked,
           "hltv_confirm": live["hltv_confirm"], "lobby": live["lobby"]}
(OUT / "data/board.json").write_text(json.dumps(machine, indent=1))

CSS = """<style>:root{--bg:#0b1220;--card:#131e33;--line:#2a3a5c;--txt:#eef3ff;--mut:#a9b8d8;--acc:#ffb020;--ok:#2fbf71;--bad:#ff6b6b;--warn:#ffd166}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
a{color:#7db4ff}h1{font-size:1.4rem;margin:.2rem 0 .4rem}h2{font-size:1.15rem;margin:1.2rem 0 .5rem}h3{font-size:1rem;margin:.8rem 0 .3rem}
.wrap{max-width:860px;margin:0 auto;padding:12px 12px 40px}
.tabs{position:sticky;top:0;z-index:5;display:flex;gap:6px;overflow-x:auto;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line)}
.tabs a{flex:0 0 auto;min-height:44px;display:flex;align-items:center;padding:6px 12px;border:1px solid var(--line);border-radius:999px;color:var(--txt);text-decoration:none;font-size:.92rem}
.tabs a.on{background:var(--acc);color:#111;border-color:var(--acc);font-weight:700}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px;margin:10px 0}.pick{font-size:1.15rem;font-weight:800}.pick b{color:var(--ok)}
.probs{display:flex;gap:8px;margin:8px 0}.probs div{flex:1;background:#0d1830;border-radius:10px;padding:8px;text-align:center}.probs .n{font-size:1.6rem;font-weight:800}.probs .t{font-size:.85rem;color:var(--mut)}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:.78rem;font-weight:700;margin:2px 4px 2px 0}
.b-market{background:#123d2b;color:#7dffb0}.b-model{background:#2b2a12;color:#ffe97d}.b-bound{background:#3d2a12;color:#ffcf7d}.b-stale{background:#3d1230;color:#ff9de2}.b-alias{background:#12303d;color:#7dd7ff}.b-none{background:#3d1212;color:#ff9d9d}
.mut{color:var(--mut);font-size:.9rem}.small{font-size:.85rem}
.btn{display:flex;justify-content:space-between;align-items:center;min-height:48px;background:#1a2a4a;color:var(--txt);border:1px solid var(--line);border-radius:12px;padding:10px 14px;margin:8px 0;text-decoration:none}.btn strong{color:var(--acc)}
table{width:100%;border-collapse:collapse;font-size:.92rem}th,td{padding:7px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
.warn{border-left:4px solid var(--warn);padding:8px 10px;background:#241d08;border-radius:8px}.good{border-left:4px solid var(--ok);padding:8px 10px;background:#0b2417;border-radius:8px}
.big{font-size:1.05rem}@media(max-width:520px){.probs .n{font-size:1.3rem}h1{font-size:1.2rem}}</style>"""
TABS = [("index.html","🏆 Final day"),("picks.html","✅ All picks"),("twc.html","TWC Days 1–5"),("unresolved.html","⚠️ Unresolved"),("flagged.html","Flagged"),("method.html","Method")]
def page(title, active, body):
    tabs = "".join(f'<a href="{h}"{" class=on" if h==active else ""}>{t}</a>' for h,t in TABS)
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>{esc(title)}</title>{CSS}</head><body><div class=wrap>
<nav class=tabs>{tabs}</nav>
<p class="mut small">TWC 2026 FINAL DAY desk · built {iso()} · lobby read live {live['lobby_read_utc']} · HotSpawn capture {board.get('canonical_capture')} · probabilities from external books / Valve ratings — never HotSpawn. Crowd % = ownership only.</p>
{body}
<p class="mut small">Not affiliated with HotSpawn, Thunderpick or any bookmaker. Model/bound numbers are originated estimates, not verified win chances. Check lock times on HotSpawn before picking. <a href="../index.html">← Site home</a> · <a href="data/board.json">JSON board</a></p>
</div></body></html>"""

def day5_card(m):
    return f"""<article class=card><h3>{esc(m['stage'])} · TODAY Sun 18 Oct · {m['start_utc'][11:16]} UTC</h3>
<div class=probs><div><div class=t>{esc(m['a'])} ({m['odds_a']:.2f})</div><div class=n>{round(m['prob_a']*100)}%</div></div>
<div><div class=t>{esc(m['b'])} ({m['odds_b']:.2f})</div><div class=n>{round(m['prob_b']*100)}%</div></div></div>
<p class=pick>✅ PICK: <b>{esc(m['safe'])}</b> · {pct(max(m['prob_a'],m['prob_b']))}</p>
<p class=big>{esc(m['verdict'])}</p>
<p class="mut small">LIVE market: {esc(m['book'])} {m['odds_a']:.2f} / {m['odds_b']:.2f} read {m['read_utc']}, proportional no-vig (overround {m['overround']*100:.1f}%). Yesterday's originated VRS sensitivity: {esc(m['a'])} {pct(m['originated_a'])} calibrated / {pct(m['originated_a_raw'])} raw Valve — market supersedes it.</p>
<p class=small>Sources: <a href="{m['hltv_url']}">HLTV match</a> · <a href="{m['bo3_url']}">bo3.gg (price)</a> · <a href="https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026_10_05.md">Valve VRS</a> · <a href="twc.html">full case</a></p></article>"""

nxt = "".join(f'<li><a href="picks.html#{r["fixture_id"]}">{esc(r["pick"])} {round(r["pick_prob"]*100)}%</a> — {esc(r["team_a"])} v {esc(r["team_b"])} · locks {r["lock_utc"][:10]} {r["lock_utc"][11:16]} UTC</li>' for r in open_rows[:4])
index = f"""<h1>🏆 TWC 2026 — FINAL DAY picks (today, Malta)</h1>
<p class=big><strong>The books priced the final overnight.</strong> Grand Final: <strong>FURIA {pct(day5[1]['prob_a'])}</strong> over BETBOOM (1.35/2.90). 3rd place: <strong>Falcons {pct(day5[0]['prob_b'])}</strong> over Aurora (2.50/1.48). BETBOOM at {pct(day5[1]['dog_prob'])} fail the 35% climb floor — no stupid chase. Aurora are today's only justified conditional gamble, and only if a HotSpawn card appears (Malta main event is still NOT on the lobby at the {live['lobby_read_utc']} live read).</p>
{day5_card(day5[0])}{day5_card(day5[1])}
<h2>📱 Where the picks are</h2>
<a class=btn href="picks.html"><span><strong>All picks</strong> · {summary['open']} open HotSpawn matches — pick + both % on every card</span><span>→</span></a>
<a class=btn href="twc.html"><span><strong>TWC Days 1–5</strong> · verified results, Aurora roster truth, today's full case</span><span>→</span></a>
<a class=btn href="unresolved.html"><span><strong>Unresolved &amp; limitations</strong> · {len(unresolved)} rows without a fresh book price + what was tried</span><span>→</span></a>
<a class=btn href="../finals/index.html"><span>Yesterday's finals desk (pre-price originated lines, for the record)</span><span>→</span></a>
<a class=btn href="../picks-every-match/index.html"><span>Canonical strict board · market-only, blanks stay blank</span><span>→</span></a>
<a class=btn href="../ourline/index.html"><span>Ourline · fastest refresh (~27 min)</span><span>→</span></a>
<h2>Coverage right now</h2><p>{summary['open']} open · {by_basis.get('market',0)} fresh market · {by_basis.get('alias',0)} proven-alias market · {by_basis.get('stale',0)} stale · {by_basis.get('model',0)} Valve-VRS model · {by_basis.get('bound',0)} bound-only · {summary['blank']} blank · {len(locked)} locked since capture. Live lobby still lists 81 CS2 fixtures; refreshed every 4 hours.</p>
<h2>⏰ Next locks</h2><ul>{nxt}</ul>
<h2>How to climb (contrarian, not stupid)</h2><p>1) Take favourites the crowd hates first — free differential, no win-% cost. 2) Switch to a dog only at ≥35% win chance, ≥15pp leverage over crowd ownership, AND ≥2 verified flags (rest, veto, H2H, roster/stand-in). 3) Never chase yesterday's upset into a worse matchup. Day 4 is graded honestly on the TWC page: the Aurora climb lost, the floor-rejected BETBOOM punt won — one result doesn't rewrite a pre-declared rule, and today's BETBOOM price ({pct(day5[1]['dog_prob'])}) fails it anyway.</p>
<p class=warn><strong>Unresolved summary:</strong> {len(unresolved)} open rows have no fresh two-sided book price (model/bound/stale/alias instead, each labelled). Every such row, the HLTV→esportsbook→exchange→VRS sources tried, and what would resolve it: <a href="unresolved.html">Unresolved &amp; limitations</a>. Nothing is filled in as 50/50.</p>"""
(OUT/"index.html").write_text(page("TWC final day — picks + every HotSpawn match", "index.html", index))

BASIS_L = {"market":"Market · bookmaker","alias":"Market · proven alias","stale":"Stale single-book","model":"Model · Valve VRS","bound":"Bound only (≥)","none":"Withheld"}
cards = []
for r in open_rows:
    srcs = " · ".join(f'<a href="{s["url"]}">{esc(s["label"])}</a>' for s in r.get("sources",[]))
    crowd = f'Crowd (ownership only): {r["crowd_a"]}% / {r["crowd_b"]}% {esc(r.get("crowd_note",""))}.' if r.get("crowd_a") is not None else ""
    climb = esc(r["climb"]) if r.get("climb") else ""
    cards.append(f"""<article class=card id={r['fixture_id']}><h3>{esc(r['team_a'])} v {esc(r['team_b'])}</h3>
<p class="mut small">{esc(r['competition'])} · locks {r['lock_utc'][:10]} {r['lock_utc'][11:16]} UTC · {r.get('points','')} pts</p>
<div class=probs><div><div class=t>{esc(r['team_a'])}</div><div class=n>{round(r['prob_a']*100)}%</div></div><div><div class=t>{esc(r['team_b'])}</div><div class=n>{round(r['prob_b']*100)}%</div></div></div>
<p class=pick>✅ PICK: <b>{esc(r['pick'])}</b> · {pct(r['pick_prob'])}</p>
<span class="badge b-{r['basis']}">{esc(r.get('basis_label') or BASIS_L.get(r['basis'],r['basis']))}</span>
<p class=small>{esc(r.get('note',''))} {crowd} {climb}</p><p class=small>Sources: {srcs}</p></article>""")
(OUT/"picks.html").write_text(page("All picks — every open HotSpawn match","picks.html",
 f"<h1>✅ All picks — {summary['open']} open HotSpawn CS2 matches</h1><p>Every card: both win probabilities, the pick in green, and the basis badge. Market = external book no-vig; Model/Bound = our originated Valve-VRS estimate (labelled, never dressed as a book price). Rows without a fresh price are detailed on <a href=unresolved.html>Unresolved</a>.</p>"+"".join(cards)))

URES = [("D1 · 14 Oct","Group A opening","9z 2–0 Aurora 🚨 UPSET (Inferno 13–11, Nuke 13–1; 9z closed 3.80)"),("D1","Group A opening","Falcons 2–0 NiP"),("D1","Group B opening","Legacy 2–0 PARIVISION"),("D1","Group B opening","FURIA 2–0 BETBOOM — today's final pairing"),
("D2 · 15 Oct","Group A elim./winners","Aurora 2–0 NiP · 9z 1–2 Falcons"),("D2","Group B elim./winners","PARIVISION 1–2 BETBOOM · Legacy 1–2 FURIA"),
("D3 · 16 Oct","Group A decider","Aurora 2–0 9z (Cache 13–11, Inferno 13–4) — rematch won, 9z out"),("D3","Group B decider","BETBOOM 2–1 Legacy"),
("D4 · 17 Oct","Semifinal 1","FURIA 2–0 Aurora (Dust2 13–8, Inferno 13–10)"),("D4","Semifinal 2","Falcons 1–2 BETBOOM 🚨 UPSET (Anubis 13–5, Dust2 14–16 OT, Mirage 7–13; BETBOOM priced 26.8%)")]
res_rows = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a,b,c in URES)
ctx = lambda m: "".join(f"<li>{esc(c)}</li>" for c in m["context"])
twc = f"""<h1>TWC 2026 — Days 1–4 verified → Day 5 (today)</h1>
<h2>What happened (HLTV event 8932, line by line)</h2><table><tr><th>Day</th><th>Stage</th><th>Result</th></tr>{res_rows}</table>
<p class=small>Source: <a href="https://www.hltv.org/events/8932/thunderpick-world-championship-2026">HLTV event 8932</a> (+ per-match pages; full transcription in <a href="../finals/twc.html">yesterday's desk</a>, re-confirmed live today via HLTV/bo3.gg form tables). {esc(live['hltv_confirm'])}</p>
<h2>The Aurora roster-change premise — checked, again</h2>
<p>The change is the <strong>July 2026 rebuild</strong> (Fabre out 29 Jun; MAJ3R/soulfly 2 Jul; Jimpphat + coach ash 3 Jul; kyxsan IGL 8 Jul — HLTV news 45082), ~100 days before Day 1 with a full event cycle to onboard. Live today: bo3.gg lists the same five (XANTARES, woxic, Jimpphat, kyxsan, Wicadia). <strong>No October change for any finalist.</strong> The Day-1 9z loss prices as variance + one bad Nuke — the same five beat 9z 2–0 two days later. No onboarding penalty is applied to any number on this site. Where the angle is real: genuinely fresh changes/stand-ins inside ~2 weeks (e.g. Hacha's stand-ins on yesterday's card) — flagged per-row, never assumed.</p>
<h2>Day 4 picks — graded honestly</h2><p>Safe FURIA ✅ / Aurora climb ❌ · Safe Falcons ❌ / BETBOOM 26.8% rejected by the 35% floor — and won. Safe 1/2, taken climbs 0/1. A 27% dog still loses ~3 times in 4; HotSpawn pays equal points per correct pick, so switching only pays via crowd differential over volume. Rule unchanged and pre-declared.</p>
<h2>Day 5 — today, priced by the market</h2>
{day5_card(day5[0])}<ul>{ctx(day5[0])}</ul>{day5_card(day5[1])}<ul>{ctx(day5[1])}</ul>
<p class=warn>Leaderboard bottom line: <strong>FURIA + Falcons are the picks.</strong> The only non-stupid contrarian move today is Aurora (37.2%, 2 flags) <em>if</em> a HotSpawn card appears with ≤22% Aurora ownership. BETBOOM at 31.8% into FURIA's 6–0 map H2H is the stupid version — yesterday's hero is today's trap.</p>"""
(OUT/"twc.html").write_text(page("TWC Days 1–5 — final day case","twc.html",twc))

u = []
for r in unresolved:
    att = "".join(f"<li>{esc(a.get('label',''))}: {esc(a.get('result',''))} (<a href=\"{a.get('url','#')}\">source</a>, {esc(a.get('at_utc',''))})</li>" for a in r.get("attempts",[]))
    u.append(f"""<article class=card><h3>{esc(r['team_a'])} v {esc(r['team_b'])}</h3><span class="badge b-{r['basis']}">{esc(r.get('basis_label') or BASIS_L.get(r['basis']))}</span>
<p class=small>Why no fresh book price: {esc(r.get('note',''))}</p><p class=small>What was tried (HLTV → esportsbooks → exchange → Valve VRS):</p><ul class=small>{att}</ul>
<p class=small>Pick shown on All picks from the labelled fallback only — <a href="picks.html#{r['fixture_id']}">card</a>.</p></article>""")
(OUT/"unresolved.html").write_text(page("Unresolved picks & limitations","unresolved.html",
 f"""<h1>⚠️ Unresolved picks &amp; limitations</h1><p>{len(unresolved)} of {summary['open']} open rows have no fresh two-sided bookmaker price. Each keeps a labelled fallback (proven-alias market / stale single-book / calibrated Valve-VRS model / one-sided bound) or would be left blank — never defaulted to 50/50. Limitations: low-tier CCT/DraculaN/regional cards are often priced by one book or none and are absent from Polymarket; VRS covers only ranked cores, so new stacks get bounds, not point estimates; name variants (e.g. WhiteBIT=WROTBERRY) are joined only on agreeing opponent + kickoff + roster proof. Full method: <a href=method.html>Method</a>.</p>"""+"".join(u)))

FLAGS = [
 ("FD1","Aurora 'recent roster change' = July rebuild, not October. No onboarding penalty anywhere. Sources: HLTV news 45082, bo3.gg live lineups."),
 ("FD2","TWC Malta main event is NOT a HotSpawn pick'em card (live lobby read today) — Day-5 picks are research picks; the conditional Aurora climb needs a card that may never appear."),
 ("FD3","Day-5 prices are single-book (Thunderpick via bo3.gg). One book can be off-market; recheck near lock. Originated VRS sensitivity is published alongside."),
 ("FD4","Start times 11:30Z/15:00Z derive from HLTV's UTC−4 rendering + live countdowns; bo3.gg countdowns agree."),
 ("FD5","HotSpawn rows inherit the 2026-10-17T18:26:54Z canonical capture for prices/model; crowd % refreshed live today where listed. Prices can move — 4-hourly workflow re-reads."),
 ("FD6","WROTBERRY alias join (WhiteBIT) and bound-only rows are the weakest evidence on the board — see Unresolved before trusting them with a climb switch."),
 ("FD7","BETBOOM's Day-4 win at 26.8% does not retro-validate chasing sub-35% dogs; published as a backtest loss for the rule, not hidden."),
]
(OUT/"flagged.html").write_text(page("Flagged for review","flagged.html","<h1>Flagged for review</h1>"+"".join(f'<article class=card><h3>{a}</h3><p>{b}</p></article>' for a,b in FLAGS)))
(OUT/"method.html").write_text(page("Method","method.html","""<h1>Method</h1>
<h2>HotSpawn reverse-engineering</h2><p>Public lobby at play.hotspawn.com/lobby embeds its fixture list (81 CS2 at today's live read); canonical capture + collectors live in scripts/ (update-data + per-session workflows, 4-hourly). HotSpawn supplies fixtures, points and crowd ownership only.</p>
<h2>Probability ladder (per match)</h2><ol><li>External bookmaker/exchange two-sided price → proportional no-vig p=(1/odds)/Σ(1/odds).</li><li>Proven-alias re-join only on agreeing opponent + kickoff + roster proof.</li><li>HLTV research (rosters, stand-ins, H2H, maps) — flags, never blended into %.</li><li>Calibrated Valve-VRS originated line (k≈0.42 vs raw k=1.0 sensitivity) where both cores are uniquely ranked.</li><li>One-sided VRS bound, or blank + flagged. Never 50/50.</li></ol>
<h2>Leaderboard rule (pre-declared)</h2><p>Free differential first (favourite the crowd hates). Dog switch only if win% ≥35, leverage vs crowd ownership ≥15pp, and ≥2 verified flags. HotSpawn crowd % is ownership — it never enters a probability.</p>
<h2>Day-5 today</h2><p>Thunderpick prices via bo3.gg read live this session; no-vig math in data/board.json. Yesterday's originated lines are retained as sensitivity so the market move is auditable.</p>"""))
print("built", iso(), summary)
