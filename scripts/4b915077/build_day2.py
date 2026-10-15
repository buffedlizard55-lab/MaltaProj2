#!/usr/bin/env python3
"""Build the source-linked TWC day-two review from its recorded evidence JSON."""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/4b915077/day2-review.json"
OUT = ROOT / "strategy/day2.html"


def e(value):
    return html.escape("" if value is None else str(value), quote=True)


def link(url, label):
    return f'<a href="{e(url)}">{e(label)}</a>'


def render():
    d = json.loads(DATA.read_text(encoding="utf-8"))
    result_cards = []
    for row in d["day2_results"]:
        details = ""
        if row.get("map_scores"):
            details = " · Maps: " + ", ".join(row["map_scores"])
        source = link(row["match_source"], "HLTV match")
        if row.get("detail_source"):
            source += " · " + link(row["detail_source"], "HLTV report")
        result_cards.append(
            f'<article class="card"><div class="meta">{e(row["date"])} · Day 2</div>'
            f'<h3>{e(row["team_a"])} <strong>{e(row["score"])}</strong> {e(row["team_b"])}</h3>'
            f'<p>{e(row["reading"])}{e(details)}</p><p class="source">{source} · '
            f'{link(row["official_results_source"], "Official event results list")}</p></article>'
        )

    aurora = d["day3_fixtures"][0]
    bblegacy = d["day3_fixtures"][1]
    rows = []
    for row in d["day3_fixtures"]:
        if row.get("hotspawn_fixture_id"):
            probability = f'{e(row["safe_probability_pct"])}% {e(row["safe_pick"])}'
            pick = f'{e(row["safe_pick"])} for both safe + leaderboard'
            basis = f'Market-led board estimate (market-only consensus {e(row["market_consensus_probability_pct"])}%); '
            basis += f'HotSpawn ownership {e(row["hotspawn_crowd_ownership_pct"]["Aurora"])}% / '
            basis += f'{e(row["hotspawn_crowd_ownership_pct"]["9z"])}% (ownership only).'
            why = d["interpretation"]["aurora_9z"]
            source_links = " · ".join([
                link(row["match_source"], "HLTV match / schedule"),
                link(row["hotspawn_source"], "HotSpawn fixture (listing only)"),
                link(row["day1_head_to_head_source"], "9z–Aurora day-one match"),
                link(row["aurora_roster_source"], "HLTV Aurora roster page"),
                link("../board/picks.html#m-1080205", "Price and evidence board"),
                link("../strategy/index.html#m-1080205", "Current pick card")
            ])
            flagged = f'<div class="limit"><b>Contrarian screen:</b> underdog leverage {e(row["contrarian_rules"]["underdog_leverage"])}×; '
            flagged += f'{e(row["contrarian_rules"]["R1_coinflip_fade"])}; '
            flagged += f'{e(row["contrarian_rules"]["R2_upset_swing"])}; '
            flagged += f'{e(row["contrarian_rules"]["R3_context_swing"])}.</div>'
            limitation = "Prices and crowd split were read before this review; recheck the live board because quotes expire at lock."
        else:
            probability = f'{e(row["model_probability_pct"])}% {e(row["model_pick"])} (model only)'
            pick = "No HotSpawn pick published yet; provisional model lean only"
            basis = e(row["method"])
            why = d["interpretation"]["betboom_legacy"]
            source_links = " · ".join([
                link(row["match_source"], "HLTV schedule / match"),
                link(row["rating_source"], "Valve VRS source"),
                link("../data/fe803b80/board.json", "Model calibration record"),
                link(row["hotspawn_inventory_source"], f'HotSpawn lobby snapshot {row["hotspawn_inventory_stamp_utc"]} (not listed)'),
                link("https://www.egamersworld.com/counterstrike/match/5X5sFiL7H/betboom-team-vs-legacy-a0-2p2fTz", "EGW listing (not trusted as a directional line)")
            ])
            flagged = '<div class="limit"><b>Flagged / unresolved:</b> no validated two-sided market odds or HotSpawn crowd ownership in the captured snapshot. '
            flagged += f'{e(row["review_flag"])}</div>'
            limitation = e(row["limitation"])
        rows.append(
            f'<article class="fixture"><div class="meta">{e(row["date"])} · Thunderpick World Championship 2026</div>'
            f'<h3>{e(row["team_a"])} vs {e(row["team_b"])}</h3>'
            f'<div class="pick"><span>Probability / lean</span><b>{probability}</b></div>'
            f'<div class="pick"><span>Leaderboard action</span><b>{pick}</b></div>'
            f'<p><b>Basis:</b> {basis}</p><p>{e(why)}</p>{flagged}'
            f'<details><summary>Sources and limits</summary><p class="source">{source_links}</p>'
            f'<p class="muted">{limitation}</p></details></article>'
        )

    source_result = link(d["results_source"], "HLTV official event results")
    source_schedule = link(d["schedule_source"], "HLTV event schedule")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TWC day 2 results → day 3 picks</title>
<style>
:root{{--bg:#0d1117;--card:#161b22;--line:#30363d;--text:#e6edf3;--mut:#9aa7b4;--blue:#58a6ff;--yellow:#d29922;--green:#3fb950}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
a{{color:var(--blue)}}nav{{position:sticky;top:0;background:#010409;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:8px;padding:10px;z-index:2}}
nav a,.button{{min-height:44px;display:inline-flex;align-items:center;padding:0 12px;border:1px solid var(--line);border-radius:8px;text-decoration:none;color:var(--text)}}
main{{max-width:900px;margin:auto;padding:14px}}h1{{font-size:1.55rem;margin:14px 0 5px}}h2{{font-size:1.2rem;margin:24px 0 8px}}h3{{font-size:1.1rem;margin:6px 0}}
.muted,.meta{{color:var(--mut);font-size:.9rem}}.meta{{margin-bottom:5px}}.callout,.card,.fixture{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:10px 0}}
.callout{{border-left:5px solid var(--yellow)}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:8px}}
.pick{{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid var(--line)}}.pick span{{color:var(--mut)}}.limit{{padding:10px;margin:10px 0;background:#211b0e;border-left:4px solid var(--yellow);border-radius:6px}}
.source{{font-size:.9rem;overflow-wrap:anywhere}}details summary{{cursor:pointer;min-height:40px;color:var(--blue);padding-top:8px}}
.buttons{{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}}.button.primary{{background:#1f6feb;color:white;border-color:#1f6feb}}
footer{{border-top:1px solid var(--line);margin-top:28px;padding:14px 0;color:var(--mut);font-size:.85rem}}
@media(max-width:480px){{main{{padding:10px}}h1{{font-size:1.32rem}}.pick{{align-items:flex-start;flex-direction:column;gap:1px}}}}
</style></head><body>
<nav><a href="../index.html">← Dashboard</a><a href="index.html">All picks</a><a href="unresolved.html">Unresolved &amp; limits</a><a href="day1.html">Day 1 review</a><a href="day2.html" aria-current="page">Day 2 → day 3</a></nav>
<main><h1>Thunderpick World Championship 2026: day 2 → day 3</h1>
<p class="muted">Evidence checked {e(d["reviewed_utc"])} UTC. Results and schedule verified against {source_result} and {source_schedule}. Probabilities below are not HotSpawn predictions.</p>
<div class="buttons"><a class="button primary" href="index.html#m-1080205">Open Aurora–9z pick</a><a class="button" href="index.html#picks">All open picks</a><a class="button" href="unresolved.html">Unresolved / limitations</a></div>
<div class="callout"><b>Executive take:</b> For the listed day-three rematch, keep <b>Aurora</b> on both the safe and leaderboard cards. The market still gives Aurora about 65–66%; 9z is live, but 20% ownership yields only 1.75× leverage and misses the published contrarian gates. Day two strengthens neither a blind 9z chase nor an assumption that day one was meaningless: Aurora recovered 2-0, while 9z took a map from Falcons but lost 1-2. The other official decider, BetBoom–Legacy, was not in the captured HotSpawn inventory; keep its model-only lean separate and flagged.</div>
<h2>Verified day-two results</h2><div class="cards">{''.join(result_cards)}</div>
<h2>Day-three picks and unresolved fixture</h2>{''.join(rows)}
<h2>What changed after day 2?</h2><ul><li>Aurora's elimination win over NIP is current evidence that the roster is competitive after the 9z loss. It does not erase the day-one 9z head-to-head upset.</li><li>9z's map win against Falcons shows a real path to an upset, but the full-series loss is also relevant. A single BO3 is not enough to recalculate market odds by hand.</li><li>Legacy's loss and BetBoom's win point in opposite directions for their next match. We do not treat narrative recency as a substitute for a current two-sided market.</li><li>Keep HotSpawn crowd percentages strictly as opponent ownership, never as a match-probability source.</li></ul>
<h2>Separate unresolved item and limitations</h2><p>The official schedule confirms BetBoom–Legacy, but the saved HotSpawn lobby snapshot did not list it. Its 63% Legacy figure is a reproducible, calibrated VRS model estimate from a 10 October-old standings snapshot—not betting odds. The page therefore does not present this as a confirmed HotSpawn pick. The EGamersWorld 1.8/1.8 display is noted but not used to choose a side. Recheck the lobby and independent odds on the next refresh.</p>
<p>All source-linked result rows above link to HLTV match pages, with the official event results page as a cross-check. The original day's HotSpawn record is cited only to confirm listing and crowd ownership; HotSpawn is never used to estimate match probability.</p>
<footer>Generated from <a href="../data/4b915077/day2-review.json">the dated evidence record</a>. This is a dated analytical note; markets, schedules and pick-lock status change. Source/method detail: <a href="method.html">strategy method</a>.</footer></main></body></html>'''


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(f"Built {OUT.relative_to(ROOT)} from {DATA.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
