#!/usr/bin/env python3
"""Build twc/ (TWC 2026 Day 1-3 review + Day 3 picks) from data/869a5375/twc.json.

Deterministic, no network. Every table row / card carries its source links;
unverified probabilities render blank, never invented. HotSpawn crowd % is
rendered as ownership only.
"""
import html, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/869a5375/twc.json"
OUT = ROOT / "twc"

CSS = """
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--text:#e6edf3;--mut:#9aa7b4;--ok:#3fb950;--warn:#d29922;--bad:#f85149;--acc:#58a6ff}
*{box-sizing:border-box}body{margin:0;font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--text)}
a{color:var(--acc)}main{max-width:860px;margin:0 auto;padding:12px}
nav{display:flex;flex-wrap:wrap;gap:8px;padding:10px 12px;background:#010409;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:2}
nav a{min-height:44px;display:inline-flex;align-items:center;padding:0 12px;border:1px solid var(--line);border-radius:8px;text-decoration:none;color:var(--text);font-size:15px}
nav a.on{background:#1f6feb;border-color:#1f6feb}
h1{font-size:1.45rem;margin:14px 0 6px}h2{font-size:1.15rem;margin:24px 0 8px}
.mut{color:var(--mut);font-size:.9rem}
.btns{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.btn{min-height:48px;display:inline-flex;align-items:center;padding:0 16px;border-radius:10px;background:#1f6feb;color:#fff;text-decoration:none;font-weight:600}
.btn.alt{background:var(--card);border:1px solid var(--line);color:var(--text)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin:12px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px}.tile b{display:block;font-size:1.4rem}
.m{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:10px 0}
.m.contra{border-left:5px solid var(--warn)}
.top{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;font-size:.85rem;color:var(--mut)}
.teams{display:grid;grid-template-columns:1fr auto;gap:4px 10px;margin:8px 0;font-size:1.05rem}
.teams .p{font-weight:700;text-align:right}.fav{color:var(--ok)}
.bar{height:8px;border-radius:4px;background:#30363d;overflow:hidden;margin:4px 0 8px}.bar i{display:block;height:100%;background:var(--ok)}
.picks{display:grid;grid-template-columns:1fr 1fr;gap:8px}.pk{background:#0d1117;border:1px solid var(--line);border-radius:8px;padding:8px}
.pk small{display:block;color:var(--mut);font-size:.78rem}.pk b{font-size:1.05rem}.pk.lb b{color:var(--warn)}
.why{font-size:.9rem;color:var(--mut)}details{margin-top:8px}summary{cursor:pointer;min-height:36px;color:var(--acc)}
.src{font-size:.85rem;word-break:break-word}.tag{display:inline-block;font-size:.75rem;padding:2px 7px;border-radius:999px;border:1px solid var(--line);margin:2px 4px 0 0;color:var(--mut)}
.tag.w{border-color:var(--warn);color:var(--warn)}.tag.b{border-color:var(--bad);color:var(--bad)}.tag.g{border-color:var(--ok);color:var(--ok)}
table{width:100%;border-collapse:collapse;font-size:.92rem}th,td{border-bottom:1px solid var(--line);padding:7px 5px;text-align:left;vertical-align:top}
.tw{overflow-x:auto}.blank{color:var(--bad);font-weight:700}
footer{color:var(--mut);font-size:.8rem;margin:30px 0 20px}
@media(max-width:480px){.picks{grid-template-columns:1fr}h1{font-size:1.3rem}}
"""

def e(x): return html.escape(str(x)) if x is not None else ""
def src_links(sources): return " · ".join(f'<a href="{e(s["url"])}">{e(s["label"])}</a>' for s in sources)
def pct(v): return "—" if v is None else f"{v:g}%"

def page(title, current, body, gen):
    nav = [("../index.html", "← Home / all picks"), ("index.html", "TWC Day 1–3"), ("unresolved.html", "Unresolved & limits"), ("method.html", "Method")]
    links = "".join(f'<a href="{u}"{" class=on" if u == current else ""}>{e(t)}</a>' for u, t in nav)
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(title)}</title><style>{CSS}</style></head><body><nav>{links}</nav>'
            f'<main>{body}<footer>Built {e(gen)} UTC by scripts/869a5375/build.py from data/869a5375/twc.json · '
            f'HotSpawn crowd % is ownership only, never a probability · Probabilities are external market estimates, not guarantees · '
            f'Not affiliated with HotSpawn · 18+, gamble responsibly.</footer></main></body></html>')

def results_table(day):
    rows = ""
    for r in day["rows"]:
        maps = f'<br><span class="mut">{e(r["maps"])}</span>' if r.get("maps") else ""
        kind = f'<br><span class="mut">{e(r["kind"])}</span>' if r.get("kind") else ""
        rows += (f'<tr><td>{e(r["match"])}{kind}<br><span class="mut">Group {e(r["group"])}</span></td>'
                 f'<td><b>{e(r["score"])}</b>{maps}</td><td>{e(r["note"])}</td>'
                 f'<td>{src_links(r["sources"])}</td></tr>')
    return (f'<h2>{e(day["label"])}</h2><div class="tw"><table><tr><th>Match</th><th>Result (HLTV)</th>'
            f'<th>What it means for Day 3</th><th>Source</th></tr>{rows}</table></div>')

def pick_card(r):
    contra = r["leaderboard_pick"] != r["safe_pick"]
    bar = f'<div class="bar"><i style="width:{r["prob_a"]:g}%"></i></div>' if r["prob_a"] is not None else ""
    crowd = ""
    if r["crowd_a"] is not None:
        crowd = f'<span class="mut"> · crowd {r["crowd_a"]:g}%</span>'
        crowd_b = f'<span class="mut"> · crowd {r["crowd_b"]:g}%</span>'
    else:
        crowd_b = ""
    team_a, team_b = r["match"].split(" vs ")
    basis = e(r["prob_basis"]) if r["prob_basis"] else '<span class="blank">Probability unverified — left blank (see Unresolved U-TWC1).</span>'
    forlist = "".join(f"<li>{e(x)}</li>" for x in r["for_pick"])
    against = "".join(f"<li>{e(x)}</li>" for x in r["against_pick"])
    cardtag = ('<span class="tag g">HotSpawn card · %s pts</span>' % r["points"]) if r["hotspawn_card"] else '<span class="tag b">No HotSpawn card in captured lobby — U-TWC2</span>'
    return f'''<article class="m{' contra' if contra else ''}" id="{e(r['id'])}">
<div class="top"><span>Group {e(r['group'])} decider · both 1–1</span><span>{e(r['start_hotspawn_utc'] or '16 Oct 2026 (HLTV)')}{' · locks ' + e(r['lock_hotspawn_utc']) if r['lock_hotspawn_utc'] else ''}</span></div>
<div class="teams"><span class="{'fav' if r['safe_pick']==team_a else ''}">{e(team_a)}{crowd}</span><span class="p">{pct(r['prob_a'])}</span>
<span class="{'fav' if r['safe_pick']==team_b else ''}">{e(team_b)}{crowd_b}</span><span class="p">{pct(r['prob_b'])}</span></div>{bar}
<div class="picks"><div class="pk"><small>Safe pick (most likely)</small><b>{e(r['safe_pick'])}</b> {pct(r['safe_prob'])}</div>
<div class="pk lb"><small>Leaderboard pick (contrarian-but-not-stupid)</small><b>{e(r['leaderboard_pick'])}</b> {pct(r['leaderboard_prob'])}</div></div>
<p class="why"><b>Why:</b> {e(r['leaderboard_rule'])}</p>
<p class="why"><b>Probability basis:</b> {basis}</p>
<p class="why"><b>Rest / roster:</b> {e(r['rest_context'])}</p>
<div>{cardtag}<span class="tag">crowd = ownership only</span></div>
<details><summary>For / against the leaderboard pick</summary>
<p><b>For {e(r['leaderboard_pick'])}:</b></p><ul>{forlist}</ul>
<p><b>Against (counterevidence):</b></p><ul>{against}</ul></details>
<details><summary>Sources</summary><ul class="src">{''.join(f'<li>{src_links([s])}</li>' for s in r['sources'])}</ul>
<p class="mut">{e(r['crowd_note'])}</p></details></article>'''

def main():
    d = json.loads(DATA.read_text())
    gen = d["generated_utc"]
    OUT.mkdir(exist_ok=True)
    d1, d2, d3 = d["day1"], d["day2"], d["day3"]
    standings = "".join(
        f'<tr><td>{e(s["group"])}</td><td>{e(s["team"])}</td><td>{e(s["record"])}</td><td>{e(s["status"])}</td></tr>'
        for s in d2["standings_derived"])
    cards = "".join(pick_card(r) for r in d3["rows"])
    index = f"""<h1>Thunderpick World Championship 2026 — Day 1–3 review &amp; Day 3 picks</h1>
<p class="mut">Read on your phone: what happened on Day 1 (the 9z upset) and Day 2, the group standings, and a safe + a
contrarian-but-not-stupid leaderboard pick for <b>every Day 3 match</b> (Friday 16 October 2026). Research read {e(gen)} UTC.
For every other HotSpawn CS2 match, use the <a href="../strategy/index.html">every-match picks board</a> or the
<a href="../picks-every-match/index.html">strict probabilities board</a>.</p>
<div class="btns"><a class="btn" href="#day3">Day 3 picks ↓</a><a class="btn alt" href="unresolved.html">Unresolved picks &amp; limitations</a>
<a class="btn alt" href="../strategy/index.html">All CS2 matches: safe + leaderboard picks</a><a class="btn alt" href="../picks-every-match/unresolved.html">All unresolved matches</a></div>
<h2>Executive summary</h2><ul>
<li><b>Day 1:</b> 9z beat Aurora 2–0 (Inferno 13–11, Nuke 13–1) — the market gave 9z ~30%, only 4% of players picked them. The lesson is not "pick every underdog": it is that the crowd over-owns favourites (80–96%) relative to the market (65–75%), so a <i>live</i> underdog at low ownership is the cheapest way to climb. <a href="#day1">Day 1 table</a></li>
<li><b>Aurora's roster change is real but old:</b> the verified change is the <b>July 2026</b> rebuild (kyxsan as IGL, Jimpphat, coach ash; the Turkish core became an international lineup). No October change was found on HLTV — flagged as U-TWC6. By October the market has priced the rebuild, and Aurora's Day 2 form is counterevidence to fading them blindly.</li>
<li><b>Day 2:</b> Falcons and FURIA won their groups (2–0); NiP and PARIVISION are out (0–2). Aurora bounced back 2–0 over NiP; 9z took a map off Falcons; Legacy took a map off FURIA; BetBoom came from behind against PARIVISION. <a href="#day2">Day 2 table</a></li>
<li><b>Day 3 (16 Oct) — Group A decider:</b> Safe pick <b>Aurora (65%)</b>; leaderboard pick <b>9z (35%, owned by only 20%)</b> — they already beat Aurora 2–0 at this event. <a href="#twc-d3-1">Card</a></li>
<li><b>Day 3 — Group B decider:</b> Research pick <b>Legacy</b> (better HLTV rank/form, took a map off FURIA), but the win probability is <span class="blank">blank — unverified</span> and <b>no HotSpawn card existed</b> for this match in the captured lobby, so there is no contrarian pick and possibly no HotSpawn pick to make yet. <a href="#twc-d3-2">Card</a> · <a href="unresolved.html">U-TWC1/U-TWC2</a></li>
<li><b>Playoffs:</b> semi-finals (17 Oct) and the final day (18 Oct) have no teams yet — no picks can be generated (U-TWC5).</li>
</ul>
<div class="tiles"><div class="tile"><b>8</b>Day 1+2 results verified on HLTV</div><div class="tile"><b>2</b>Day 3 deciders</div>
<div class="tile"><b>1</b>with a verified market %</div><div class="tile"><b>1</b>probability blank (flagged)</div><div class="tile"><b>1</b>contrarian pick (9z)</div></div>
<section id="day1">{results_table(d1)}</section>
<h2>9z–Aurora: what it teaches (and what it doesn't)</h2>
<p>{e(d['aurora_roster']['summary'])}</p><p>{e(d['aurora_roster']['how_to_use'])}</p>
<p class="mut">Sources: {src_links(d['aurora_roster']['sources'])}</p>
<section id="day2">{results_table(d2)}</section>
<h2>Group standings after Day 2 (derived from the results above)</h2>
<div class="tw"><table><tr><th>Group</th><th>Team</th><th>Record</th><th>Status</th></tr>{standings}</table></div>
<p class="mut">{e(d2['standings_note'])} Source for all results: {src_links([{'label':'HLTV event results','url':d['event']['hltv_results_url']}])}.</p>
<h2 id="day3">Day 3 picks — Friday 16 October 2026</h2>
<p class="mut">Two deciders; the winners take the last two playoff spots (<a href="{e(d['event']['hotspawn_day3_preview_url'])}">HotSpawn Day 3 preview</a>).
Safe = most likely winner. Leaderboard = the contrarian-but-not-stupid card for climbing; it is a variance choice, not a claim the underdog is more likely.</p>
{cards}
<p class="mut">Full rules: <a href="method.html">Method &amp; contrarian rules</a> · Limitations and blank rows: <a href="unresolved.html">Unresolved picks &amp; limitations</a>.</p>"""
    (OUT / "index.html").write_text(page("TWC 2026 Day 1–3 review & Day 3 picks", "index.html", index, gen))

    urows = "".join(
        f'<tr><td>{e(u["id"])}</td><td>{e(u["item"])}</td><td><span class="blank">— blank / unverified</span></td>'
        f'<td>{e(u["limitation"])}</td><td>{src_links(u["sources"])}</td></tr>' for u in d["unresolved"])
    also = "".join(
        f'<tr><td>{e(a["match"])}</td><td><span class="blank">— no pick yet</span></td><td>{e(a["reason"])}</td><td>{src_links(a["sources"])}</td></tr>'
        for a in d3["also_unresolved"])
    unresolved = f"""<h1>Unresolved picks &amp; limitations — TWC 2026</h1>
<p>Every TWC row that could <b>not</b> be resolved the same way as the featured market picks, what was tried
(HLTV first, then esportsbooks/exchanges, then an originated rating estimate), and why the value stays blank.
Nothing here is filled in by guessing, by HotSpawn popularity, or by an invented 50/50. This section is linked from the
<a href="index.html">executive summary</a> and from the site home page.</p>
<div class="tw"><table><tr><th>ID</th><th>Item</th><th>Published value</th><th>Limitation &amp; source attempts</th><th>Sources for manual review</th></tr>{urows}</table></div>
<h2>Matches with no pick yet (teams not decided)</h2>
<div class="tw"><table><tr><th>Match</th><th>Pick</th><th>Why</th><th>Source</th></tr>{also}</table></div>
<p class="mut">For unresolved matches across <b>all</b> HotSpawn CS2 tournaments (not just TWC), see
<a href="../picks-every-match/unresolved.html">the canonical unresolved page</a> and
<a href="../strategy/unresolved.html">the strategy board's unresolved &amp; limits page</a>.</p>"""
    (OUT / "unresolved.html").write_text(page("Unresolved picks & limitations · TWC 2026", "unresolved.html", unresolved, gen))

    rules = "".join(f"<li>{e(r)}</li>" for r in d["contrarian_rules"])
    policy = "".join(f"<li>{e(r)}</li>" for r in d["policy"])
    method = f"""<h1>Method, probability rules &amp; contrarian rules</h1>
<h2>Where the numbers come from</h2><ul>{policy}</ul>
<h2>Resolution ladder for a match with no featured market pick</h2>
<ol><li><b>HLTV first</b> — event/match/analytics pages for fixtures, results, rankings and form.</li>
<li><b>Then esportsbooks and exchanges</b> — the repo market boards' captured two-sided lines (Pinnacle, Bovada, Melbet, Kalshi, Thunderpick via bo3.gg); a second published line is used as a cross-check, and suspected placeholder quotes (e.g. uniform 1.80/1.80) are rejected.</li>
<li><b>Then an originated estimate</b> — only from uniquely identified official Valve VRS ratings, clearly labelled as our model, never presented as a bookmaker price.</li>
<li><b>Otherwise blank</b> — published on the <a href="unresolved.html">Unresolved</a> page with the attempts and the limitation.</li></ol>
<h2>Contrarian-but-not-stupid rules (leaderboard picks)</h2><ol>{rules}</ol>
<h2>Updates</h2>
<p>This section is rebuilt automatically every 4 hours by <code>.github/workflows/twc-869a5375.yml</code> from
<code>data/869a5375/twc.json</code> (fail-closed internal-link check). Live fixture/line refresh for all CS2 matches is handled by the
repo's 4-hourly collectors behind the <a href="../strategy/index.html">every-match board</a> and the
<a href="../picks-every-match/index.html">strict board</a>; a rebuild never makes an old quote fresh — every card shows its read time.</p>
<h2>Sources used for this section</h2>
<ul class="src"><li>{src_links([{'label':'HLTV TWC 2026 event','url':d['event']['hltv_event_url']},{'label':'HLTV results','url':d['event']['hltv_results_url']},{'label':'HLTV matches','url':d['event']['hltv_matches_url']},{'label':'HotSpawn lobby (discovery only)','url':d['event']['hotspawn_lobby_url']},{'label':'HotSpawn Day 3 preview (editorial)','url':d['event']['hotspawn_day3_preview_url']}])}</li></ul>"""
    (OUT / "method.html").write_text(page("Method · TWC 2026 picks", "method.html", method, gen))
    print(f"built twc/ (3 pages) from {DATA.name} generated_utc={gen}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
