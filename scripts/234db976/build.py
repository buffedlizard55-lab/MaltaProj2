#!/usr/bin/env python3
"""Render the source-linked, static TWC Day-5 research pages."""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "234db976" / "research.json"
PAGE_PATHS = {
    "twc-2026/day-5.html": "day5",
    "twc-2026/day-5-unresolved.html": "unresolved",
}


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def link(label: str, url: str, *, css: str | None = None) -> str:
    if not url.startswith("https://"):
        raise ValueError(f"External evidence URLs must use https://, got {url!r}")
    class_attr = f' class="{esc(css)}"' if css else ""
    return f'<a{class_attr} href="{esc(url)}" rel="noopener">{esc(label)}</a>'


def american_to_decimal(price: str | int | float) -> float:
    value = float(str(price).replace("+", ""))
    if value >= 100:
        return 1.0 + value / 100.0
    if value <= -100:
        return 1.0 + 100.0 / abs(value)
    raise ValueError(f"Invalid American odds: {price!r}")


def market_probabilities(match: dict[str, Any]) -> dict[str, Any]:
    odds = match["american_odds"]
    teams = (match["team_a"], match["team_b"])
    decimal = {team: american_to_decimal(odds[team]) for team in teams}
    raw = {team: 1.0 / decimal[team] for team in teams}
    total = sum(raw.values())
    if not 0.95 <= total <= 1.30:
        raise ValueError(f"Implausible two-way book for {match['id']}: {total:.4f}")
    no_vig = {team: raw[team] / total for team in teams}
    return {
        "decimal": decimal,
        "raw": raw,
        "total_raw": total,
        "overround_pct_points": (total - 1.0) * 100.0,
        "no_vig": no_vig,
    }


def vrs_probability(points_a: int | float, points_b: int | float, k: float) -> float:
    """Valve's documented 400-point logistic curve with the board's fitted slope."""
    q = math.log(10.0) / 400.0
    g = 1.0 / math.sqrt(1.0 + 3.0 * q**2 * 75.0**2 / math.pi**2)
    c = g * math.log(10.0) / 400.0
    x = k * c * (float(points_a) - float(points_b))
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


def load_data() -> dict[str, Any]:
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    validate_data(data)
    return data


def validate_data(data: dict[str, Any]) -> None:
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported research.json schema version")
    if len(data.get("matches", [])) != 2:
        raise ValueError("Exactly two Day-5 fixtures are expected")
    if len(data.get("history_days_1_to_4", [])) != 12:
        raise ValueError("The Days 1–4 ledger must contain all 12 completed matches")
    if any(match.get("kickoff_utc") is not None for match in data["matches"]):
        raise ValueError("Unconfirmed UTC kickoff must remain blank")
    expected_days = {1: 4, 2: 4, 3: 2, 4: 2}
    counts = {day: 0 for day in expected_days}
    for row in data["history_days_1_to_4"]:
        counts[row["day"]] = counts.get(row["day"], 0) + 1
        for key in ("blast_url", "hotspawn_url", "hltv_url"):
            if not row.get(key, "").startswith("https://"):
                raise ValueError(f"Historical row {row.get('result')} lacks {key}")
    if counts != expected_days:
        raise ValueError(f"Unexpected Days 1–4 match counts: {counts}")
    for match in data["matches"]:
        probs = market_probabilities(match)
        ordered = sorted(probs["no_vig"], key=probs["no_vig"].get, reverse=True)
        if match["primary_pick"] != ordered[0]:
            raise ValueError(f"Primary pick is not the market favorite in {match['id']}")
        if match["underdog_option"] != ordered[1]:
            raise ValueError(f"Underdog option is not the market underdog in {match['id']}")
        if not match.get("market_url", "").startswith("https://"):
            raise ValueError(f"Market source missing for {match['id']}")
        if not match.get("sources"):
            raise ValueError(f"No evidence links for {match['id']}")
        if any(not source["url"].startswith("https://") for source in match["sources"]):
            raise ValueError(f"Non-HTTPS evidence URL for {match['id']}")


def document(title: str, description: str, active: str, main: str) -> str:
    nav_items = [
        ("index.html", "Days 1–3", ""),
        ("day-4.html", "Day 4 recap", ""),
        ("day-5.html", "Day 5 picks", "day5"),
        ("day-5-unresolved.html", "Unresolved / source audit", "unresolved"),
        ("../picks-every-match/index.html", "All HotSpawn CS2 fixtures", ""),
        ("../picks-every-match/unresolved.html", "All-match limitations", ""),
    ]
    nav = "".join(
        '<a href="' + esc(href) + '"'
        + (' aria-current="page"' if key == active else '')
        + '>' + esc(label) + '</a>'
        for href, label, key in nav_items
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{esc(description)}">
<title>{esc(title)}</title>
<link rel="stylesheet" href="assets.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header>
  <div class="wrap">
    <div class="brand">TWC 2026 <span class="small">Independent Day-5 research</span></div>
    <nav aria-label="Main navigation">{nav}</nav>
  </div>
</header>
<main id="main" class="wrap">
{main}
<footer class="small">
  <p>Research record: <a href="../data/234db976/research.json">machine-readable sources and inputs</a>. Odds are dated observations, not a live feed or a promise of outcome. Check the direct market before any match lock.</p>
  <p>Not affiliated with Thunderpick, BLAST, HLTV or HotSpawn. HotSpawn crowd / ownership values are not used as probabilities. No automated bets or account actions; gamble responsibly and follow local age and legal rules.</p>
  <p><a href="index.html">TWC research home</a> · <a href="day-5.html">Day-5 picks</a> · <a href="day-5-unresolved.html">Unresolved details</a> · <a href="../picks-every-match/index.html">Read-only full HotSpawn CS2 board</a></p>
</footer>
</main>
</body>
</html>
"""


def render_market_card(match: dict[str, Any], capture: str, vrs: dict[str, Any]) -> str:
    p = market_probabilities(match)
    model_p = vrs_probability(
        match["vrs_points"][match["team_a"]],
        match["vrs_points"][match["team_b"]],
        vrs["used_k"],
    )
    team_a, team_b = match["team_a"], match["team_b"]
    odds_a, odds_b = match["american_odds"][team_a], match["american_odds"][team_b]
    dec_a, dec_b = p["decimal"][team_a], p["decimal"][team_b]
    sources = " · ".join(link(s["label"], s["url"]) for s in match["sources"])
    market_label_note = (
        f'  <p class="small"><strong>Market label note:</strong> {esc(match["market_label_note"])}</p>\n'
        if match.get("market_label_note")
        else ""
    )
    source_label_b = match.get("market_source_labels", {}).get(team_b)
    source_team_b = f"{team_b} (Thunderpick: {source_label_b})" if source_label_b else team_b
    return f"""<article class="panel" data-match="{esc(match['id'])}">
  <p class="eyebrow">{esc(match['round'])} · {esc(match['format'])}</p>
  <h3>{esc(team_a)} vs {esc(team_b)}</h3>
  <p><strong>Sunday 18 October 2026.</strong> Kickoff (UTC): <span class="blank">— unconfirmed</span>. {esc(match['raw_time_display'])}.</p>
  <div class="teams" role="group" aria-label="One-book de-vigged win probabilities">
    <span>{esc(team_a)}</span><span class="prob">{p['no_vig'][team_a] * 100:.1f}%</span>
    <span>{esc(team_b)}</span><span class="prob">{p['no_vig'][team_b] * 100:.1f}%</span>
  </div>
  <p><span class="pick">Primary pick: {esc(match['primary_pick'])}</span></p>
  <p><span class="risk">Reasonable underdog alternative: {esc(match['underdog_option'])}</span><br>{esc(match['underdog_note'])}</p>
  <p><strong>Market snapshot:</strong> {esc(team_a)} {esc(odds_a)} (decimal return {dec_a:.2f}); {esc(source_team_b)} {esc(odds_b)} (decimal return {dec_b:.2f}).</p>
{market_label_note}  <p class="small">Proportional overround removal; raw implied total {p['total_raw'] * 100:.2f}% (overround {p['overround_pct_points']:.2f} percentage points). Capture: {esc(capture)}. One verified book only.</p>
  <p class="small"><strong>VRS cross-check only:</strong> {esc(team_a)} {model_p * 100:.1f}% / {esc(team_b)} {(1.0 - model_p) * 100:.1f}%. This is a cross-check, not the primary estimate; no format-specific fit is available.</p>
  <p class="sources"><strong>Sources:</strong> {sources}</p>
</article>"""


def render_market_table(data: dict[str, Any]) -> str:
    rows: list[str] = []
    for match in data["matches"]:
        p = market_probabilities(match)
        for team in (match["team_a"], match["team_b"]):
            source_label = match.get("market_source_labels", {}).get(team)
            team_display = f"{team} (Thunderpick: {source_label})" if source_label else team
            rows.append(
                "<tr data-evidence-row=\"market\">"
                f"<td data-label=\"Match\">{esc(match['team_a'])}–{esc(match['team_b'])}</td>"
                f"<td data-label=\"Team\">{esc(team_display)}</td>"
                f"<td data-label=\"American quote\">{esc(match['american_odds'][team])}</td>"
                f"<td data-label=\"Decimal return\">{p['decimal'][team]:.2f}</td>"
                f"<td data-label=\"Raw implied\">{p['raw'][team] * 100:.2f}%</td>"
                f"<td data-label=\"De-vigged\"><strong>{p['no_vig'][team] * 100:.2f}%</strong></td>"
                f"<td data-label=\"Book overround\">{p['overround_pct_points']:.2f} pp</td>"
                f"<td data-label=\"Official source\">{link('Direct Thunderpick match page', match['market_url'])}</td>"
                "</tr>"
            )
    return "\n".join(rows)


def render_vrs_table(data: dict[str, Any]) -> str:
    vrs = data["vrs_crosscheck"]
    rows = []
    for match in data["matches"]:
        team_a, team_b = match["team_a"], match["team_b"]
        points_a = match["vrs_points"][team_a]
        points_b = match["vrs_points"][team_b]
        p_a = vrs_probability(points_a, points_b, vrs["used_k"])
        rows.append(
            "<tr data-evidence-row=\"vrs\">"
            f"<td data-label=\"Match\">{esc(team_a)}–{esc(team_b)}</td>"
            f"<td data-label=\"Valve points\">{esc(team_a)} {points_a}; {esc(team_b)} {points_b}</td>"
            f"<td data-label=\"Model cross-check\">{p_a * 100:.1f}% / {(1-p_a) * 100:.1f}%</td>"
            f"<td data-label=\"Calibration\">10 pairs; raw k={vrs['raw_k']:.5f}, clamped to {vrs['used_k']:.2f}</td>"
            f"<td data-label=\"Official source\">{link('Valve global standings, 5 Oct 2026', vrs['official_standings_url'])} · {link('Valve model implementation', vrs['official_model_url'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_history(data: dict[str, Any]) -> str:
    rows = []
    for row in data["history_days_1_to_4"]:
        day_label = f"Day {row['day']} · {row['date']}"
        sources = (
            link("Official BLAST result record", row["blast_url"])
            + " · "
            + link("HotSpawn match record", row["hotspawn_url"])
            + " · "
            + link("HLTV match / map record", row["hltv_url"])
        )
        context = f'<p class="small">{esc(row["context"])}</p>' if row.get("context") else ""
        rows.append(
            "<tr data-evidence-row=\"history\">"
            f"<td data-label=\"Day\">{esc(day_label)}</td>"
            f"<td data-label=\"Series\"><strong>{esc(row['result'])}</strong></td>"
            f"<td data-label=\"Map scores\">{esc(row['maps'])}{context}</td>"
            f"<td data-label=\"Sources\">{sources}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_roster(data: dict[str, Any]) -> str:
    review = data["aurora_roster_review"]
    rows = []
    for entry in review["announcements"]:
        rows.append(
            "<tr data-evidence-row=\"roster\">"
            f"<td data-label=\"Date\">{esc(entry['date'])}</td>"
            f"<td data-label=\"Change\">{esc(entry['change'])}</td>"
            f"<td data-label=\"Evidence\">{link('Official Aurora post', entry['primary_url'])} · "
            f"{link('HLTV rebuild report', review['corroborating_report_url'])}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_day5(data: dict[str, Any]) -> str:
    capture = data["market_capture"]["checked_utc"]
    cards = "\n".join(render_market_card(m, capture, data["vrs_crosscheck"]) for m in data["matches"])
    body = f"""<p class="eyebrow">Thunderpick World Championship 2026 · Sunday 18 October</p>
<h1>Day 5: two picks, one timestamped market</h1>
<p class="muted">Falcons meet Aurora in the third-place BO3; FURIA meet BETBOOM in the BO5 Grand Final. Prices below come from direct Thunderpick match pages and were checked around {esc(capture)}. These are dated observations, not a live feed.</p>
<div class="actions">
  <a class="button primary" href="#day5-picks">Jump to Day-5 picks</a>
  <a class="button" href="#days-1-to-4">Review Days 1–4</a>
  <a class="button" href="day-5-unresolved.html">Open unresolved schedule / model notes</a>
  <a class="button" href="../picks-every-match/index.html">Full HotSpawn CS2 coverage (read-only)</a>
</div>
<div class="notice" role="note"><strong>Source age and schedule warning.</strong> The exact UTC kickoff is unconfirmed for both fixtures: Thunderpick, HLTV and BLAST show 07:30 / 11:00 without a timezone, while HotSpawn's Day-5 slots remain placeholders at 11:30 / 15:00 UTC. Do not convert an unstated timezone or use a HotSpawn crowd share as probability. Prices can move before lock.</div>

<h2 id="day5-picks">Day-5 picks &amp; market-implied win probabilities</h2>
<div class="grid">{cards}</div>

<h2>Odds conversion and probability method</h2>
<p>For American odds <code>+x</code>, decimal return is <code>1 + x/100</code> and raw implied probability is <code>100/(x+100)</code>. For <code>−x</code>, decimal return is <code>1 + 100/|x|</code> and raw implied probability is <code>|x|/(|x|+100)</code>. Decimal return includes the stake. For each two-way market, de-vig by dividing each raw implied probability by the sum of both sides. This simple proportional (multiplicative) method produces one-book market estimates; it does not create a market consensus.</p>
<table>
  <caption>Every price row links to the direct Thunderpick match page from which that quote was read. Capture: {esc(capture)} UTC (approximate minute).</caption>
  <thead><tr><th scope="col">Match</th><th scope="col">Team</th><th scope="col">American odds</th><th scope="col">Decimal return</th><th scope="col">Raw implied</th><th scope="col">De-vigged probability</th><th scope="col">Overround</th><th scope="col">Source</th></tr></thead>
  <tbody>{render_market_table(data)}</tbody>
</table>

<h2>Valve VRS cross-check (secondary; not the pick probability)</h2>
<p>The official 5 October standings provide team ratings. The cross-check follows Valve's logistic rating-difference model (fixed RD 75), with a locally calibrated slope <code>k</code>. The linked board calibration has 10 pairs; its raw fitted <code>k</code> is below the configured minimum, so the calculation clamps to <code>0.25</code>. This small, older fit is not format-adjusted and has no BO5-specific fit for the final. It is shown only as a sanity-check beside the primary bookmaker snapshot. See the <a href="{esc(data['vrs_crosscheck']['official_model_url'])}">official model implementation</a>.</p>
<table>
  <caption>Both rows link to Valve's official global standings snapshot used for the points.</caption>
  <thead><tr><th scope="col">Match</th><th scope="col">Valve points</th><th scope="col">VRS model cross-check</th><th scope="col">Calibration</th><th scope="col">Official source</th></tr></thead>
  <tbody>{render_vrs_table(data)}</tbody>
</table>
<p class="small">The current external prices are not derived from VRS. The VRS cross-check uses Valve's 400-point logistic scale with fixed RD 75 and a local market-fit slope; methodology and limits are described on the <a href="day-5-unresolved.html#model-limits">unresolved / source audit page</a>.</p>

<h2>Qualitative matchup notes (not extra probability inputs)</h2>
<div class="grid">
{''.join(f'''<article class="panel"><p class="eyebrow">{esc(m['round'])} · {esc(m['format'])}</p><h3>{esc(m['team_a'])} vs {esc(m['team_b'])}</h3><p>{esc(m['hltv_analytics_summary'])}</p><p class="small">HLTV analytics is qualitative here; community poll percentages were excluded from all probability estimates.</p><p class="sources">{link('HLTV analytics', m['hltv_analytics_url'])} · {link('HLTV match page', m['hltv_match_url'])}</p></article>''' for m in data['matches'])}
</div>

<h2>Aurora's roster rebuild: July, not a Day-5 surprise</h2>
<p>{esc(data['aurora_roster_review']['finding'])} The opener upset against 9z is a real result, but not proof of future probability; Aurora later beat 9z in the Day-3 rematch and lost to FURIA in the semifinal. The roster timeline is descriptive context, not a made-up percentage penalty.</p>
<table>
  <caption>Primary Aurora announcements, cross-checked against the reported completed rebuild.</caption>
  <thead><tr><th scope="col">Date</th><th scope="col">Roster change</th><th scope="col">Evidence</th></tr></thead>
  <tbody>{render_roster(data)}</tbody>
</table>
<p class="small">The 8 July captain announcement was {data['aurora_roster_review']['days_from_kyxsan_announcement_to_day_one']} days before the 14 October opener. The official tournament roster / standings page is <a href="{esc(data['aurora_roster_review']['current_tournament_lineup_url'])}">linked here</a>.</p>

<h2 id="days-1-to-4">Days 1–4: results and context</h2>
<p>Review all 12 completed series, including 9z's Day-1 opening upset over Aurora. Every row links to the official BLAST historical match record; HLTV is linked for map-level details, with HotSpawn's official media-partner match record as an additional cross-check. Results are descriptive evidence, not a shortcut to future win probabilities.</p>
<table>
  <caption>Official BLAST result, HotSpawn match record and HLTV map-detail links appear on every row.</caption>
  <thead><tr><th scope="col">Day</th><th scope="col">Series result</th><th scope="col">Map scores</th><th scope="col">Sources</th></tr></thead>
  <tbody>{render_history(data)}</tbody>
</table>

<div class="notice"><strong>Coverage boundary.</strong> The complete HotSpawn open-fixture inventory lives on the existing <a href="../picks-every-match/index.html">full-coverage board</a>; this Day-5 route links to it read-only. That board's crowd / ownership fields are not used here as probabilities. The TWC Day-5 research is a separate two-match section.</div>
<p class="sources">More evidence: {link('Official Thunderpick event format', data['event']['official_event_url'])} · {link('Thunderpick event article / media partner', data['event']['official_event_article_url'])} · {link('HotSpawn TWC event page', data['event']['hotspawn_event_url'])} · {link('Official BLAST Day 1–4 results', data['event']['official_blast_results_url'])} · {link('Official BLAST event page', 'https://blast.tv/cs/tournaments/thunderpick-world-championship-2026')} · <a href="day-5-unresolved.html">All unresolved issues and source conflicts →</a></p>
"""
    return document(
        "TWC 2026 Day 5: picks, odds and evidence",
        "Mobile-friendly CS2 Day-5 research with direct Thunderpick odds, de-vigged probabilities, verified Days 1–4 results and a separate limitations page.",
        "day5",
        body,
    )


def render_schedule_rows(data: dict[str, Any]) -> str:
    rows = []
    for item in data["schedule_sources"]:
        urls = [item["url"], *item.get("additional_urls", [])]
        labels = [item["source"], *item.get("additional_labels", [])]
        sources = " · ".join(link(f"Open {labels[i]} source", url) for i, url in enumerate(urls))
        rows.append(
            "<tr data-evidence-row=\"schedule\">"
            f"<td data-label=\"Source\">{esc(item['source'])}</td>"
            f"<td data-label=\"What it displays\">{esc(item['display'])}</td>"
            f"<td data-label=\"Evidence\">{sources}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_limitation_rows(data: dict[str, Any]) -> str:
    event = data["event"]
    market = data["market_capture"]
    vrs = data["vrs_crosscheck"]
    matches = data["matches"]
    coverage = data["hotspawn_coverage"]
    rows = [
        {
            "item": "Kickoff time and timezone",
            "finding": "No agreed UTC kickoff is published. Raw source displays disagree; HotSpawn's cards do not name the teams. Leave the UTC field blank.",
            "urls": [matches[0]["market_url"], matches[1]["market_url"], event["official_event_url"], data["schedule_sources"][3]["url"], event["hotspawn_event_url"], data["schedule_sources"][6]["url"]],
        },
        {
            "item": "Observed Aurora quote difference",
            "finding": market["earlier_overview_quote"],
            "urls": [market["earlier_overview_url"], matches[0]["market_url"]],
        },
        {
            "item": "One-book snapshot, not consensus",
            "finding": market["source_scope"],
            "urls": [matches[0]["market_url"], matches[1]["market_url"], data["other_market_checks"][0]["url"]],
        },
        {
            "item": "Thunderpick final team label",
            "finding": matches[1]["market_label_note"],
            "urls": [matches[1]["market_url"], event["official_event_url"], matches[1]["hltv_match_url"]],
        },
        {
            "item": "VRS age and small clamped fit",
            "finding": f"Valve's latest checked snapshot is {vrs['snapshot_date']} ({vrs['age_days_at_capture']} days old at capture). Calibration has {vrs['calibration_market_pairs']} pairs; raw k={vrs['raw_k']:.5f} was clamped to {vrs['used_k']:.2f}.",
            "urls": [vrs["official_standings_url"], vrs["checked_latest_snapshot_url"]],
        },
        {
            "item": "No BO5-specific calibration",
            "finding": "The FURIA–BETBOOM final is BO5. The VRS calibration is not format-adjusted; the direct match-specific bookmaker price is primary.",
            "urls": [event["official_event_url"], matches[1]["market_url"], vrs["official_standings_url"]],
        },
        {
            "item": "Final format metadata conflict",
            "finding": "The organizer, Thunderpick's direct market page and HotSpawn list a BO5 final. BLAST's final match detail page labels it BO3. This is flagged, not silently normalized.",
            "urls": [event["official_event_url"], matches[1]["market_url"], data["schedule_sources"][4]["url"], event["hotspawn_event_url"]],
        },
        {
            "item": "HotSpawn Day-5 fixture state and probabilities",
            "finding": f"The TWC page's Day-5 slots remain {coverage['day5_fixture_cards']}; no final contest points, fixture IDs or ownership share were verified. HotSpawn crowd share is not a probability input.",
            "urls": [event["hotspawn_event_url"], coverage["lobby_url"]],
        },
        {
            "item": "HotSpawn map-score rendering for FURIA series",
            "finding": "The HotSpawn match pages for FURIA–Legacy and FURIA–Aurora show series headers consistent with official results, but their rendered map-side scores appear reversed relative to the BLAST match records and HLTV map details. Use BLAST for the series results and HLTV for map scores; do not read the HotSpawn map-side fields as a probability signal.",
            "urls": [
                data["history_days_1_to_4"][7]["hotspawn_url"],
                data["history_days_1_to_4"][7]["blast_url"],
                data["history_days_1_to_4"][7]["hltv_url"],
                data["history_days_1_to_4"][10]["hotspawn_url"],
                data["history_days_1_to_4"][10]["blast_url"],
                data["history_days_1_to_4"][10]["hltv_url"],
            ],
        },
        {
            "item": "No verified four-hour Day-5 odds feed",
            "finding": coverage["refresh_note"],
            "urls": [matches[0]["market_url"], matches[1]["market_url"], coverage["lobby_url"]],
        },
    ]
    out = []
    for row in rows:
        sources = " · ".join(link(f"Source {i + 1}", url) for i, url in enumerate(row["urls"]))
        out.append(
            "<tr data-evidence-row=\"limitation\">"
            f"<td data-label=\"Unresolved item\"><strong>{esc(row['item'])}</strong></td>"
            f"<td data-label=\"Confirmed / limitation\">{esc(row['finding'])}</td>"
            f"<td data-label=\"Sources\">{sources}</td>"
            "</tr>"
        )
    return "\n".join(out)


def render_unresolved(data: dict[str, Any]) -> str:
    capture = data["market_capture"]["checked_utc"]
    body = f"""<p class="eyebrow">TWC 2026 · Day 5 source audit</p>
<h1>Unresolved times, market limits and model caveats</h1>
<p class="muted">This is the separate review page for information that is conflicting, stale, or not independently confirmed. Unconfirmed values remain blank; this page does not invent a kickoff time, a second market, or a HotSpawn probability.</p>
<div class="actions">
  <a class="button primary" href="day-5.html">Back to Day-5 picks</a>
  <a class="button" href="index.html">TWC research home</a>
  <a class="button" href="../picks-every-match/index.html">Full HotSpawn CS2 board (read-only)</a>
  <a class="button" href="../picks-every-match/unresolved.html">All-match unresolved board</a>
</div>
<div class="notice"><strong>UTC kickoff remains unconfirmed.</strong> Both match records deliberately show <span class="blank">—</span> for UTC start. The raw source values are kept below with their timezone labels (or missing labels) intact.</div>

<h2>Schedule and format cross-check</h2>
<table>
  <caption>One row per checked source; every row links directly to the page used. A schedule display is not silently converted to UTC.</caption>
  <thead><tr><th scope="col">Source</th><th scope="col">What it displays</th><th scope="col">Evidence</th></tr></thead>
  <tbody>{render_schedule_rows(data)}</tbody>
</table>

<h2>Market capture and quote movement</h2>
<p>Direct match pages were re-read at approximately <strong>{esc(capture)} UTC</strong>. The line values below are the latest verified direct quotes in this research capture, not a promise that the same price will remain available at publication or match lock.</p>
<table>
  <caption>Price / provenance exceptions. Every row links to the source(s) behind the note.</caption>
  <thead><tr><th scope="col">Item</th><th scope="col">What was observed</th><th scope="col">Sources</th></tr></thead>
  <tbody>
    <tr data-evidence-row="limitation"><td data-label="Item">Aurora–Falcons quote</td><td data-label="Observation">An earlier event overview displayed Aurora +150 / Falcons −208; the later direct match page displayed +170 / −238. The latter is used in the Day-5 card. Movement or caching could explain the difference; no line-history archive was captured.</td><td data-label="Sources">{link('Earlier Thunderpick event overview', data['market_capture']['earlier_overview_url'])} · {link('Later direct Aurora–Falcons market', data['matches'][0]['market_url'])}</td></tr>
    <tr data-evidence-row="limitation"><td data-label="Item">FURIA–BETBOOM quote</td><td data-label="Observation">The direct Thunderpick page displayed FURIA −286 / BB Team +190. The event fixture and HLTV use BETBOOM; the price is mapped to that final by its date, BO5 format, and 11:00 listing, with the label discrepancy flagged below. The de-vigged figures are based on that one bookmaker.</td><td data-label="Sources">{link('Direct Thunderpick final market', data['matches'][1]['market_url'])} · {link('Official event format / final', data['event']['official_event_url'])} · {link('HLTV final listing', data['matches'][1]['hltv_match_url'])}</td></tr>
    <tr data-evidence-row="limitation"><td data-label="Item">Independent price confirmation</td><td data-label="Observation">No second current bookmaker or exchange price was verified for either Day-5 match. Do not describe this as a multi-book consensus. If these direct prices disappear before publication, replace them only with a clearly labelled VRS baseline or leave probability blank.</td><td data-label="Sources">{link('Aurora–Falcons direct market', data['matches'][0]['market_url'])} · {link('FURIA–BETBOOM direct market', data['matches'][1]['market_url'])} · {link('Polymarket event search checked', data['other_market_checks'][0]['url'])}</td></tr>
  </tbody>
</table>

<h2 id="model-limits">Model limits and reported discrepancies</h2>
<table>
  <caption>Limits that materially affect interpretation. Every row links to an official or direct source.</caption>
  <thead><tr><th scope="col">Item</th><th scope="col">Confirmed finding / remaining issue</th><th scope="col">Sources</th></tr></thead>
  <tbody>{render_limitation_rows(data)}</tbody>
</table>

<h2>Aurora opening upset: context, not a probability rule</h2>
<p>9z beat Aurora 2–0 on the opening day, then Falcons beat 9z 2–1, and Aurora beat 9z 2–0 in the Day-3 rematch. Aurora later lost 0–2 to FURIA in the semifinal. These are verified results, not proof that an upset changes the base rate for the next fixture. The roster rebuild was announced in July, around 98 days before the opener; no arbitrary last-minute penalty was added.</p>
<p class="sources">{link('9z–Aurora Day-1 match', data['history_days_1_to_4'][0]['hltv_url'])} · {link('Aurora–9z Day-3 rematch', data['history_days_1_to_4'][8]['hltv_url'])} · {link('FURIA–Aurora semifinal', data['history_days_1_to_4'][10]['hltv_url'])} · {link('Official Aurora roster post: kyxsan', data['aurora_roster_review']['announcements'][2]['primary_url'])}</p>

<h2>Complete HotSpawn fixture coverage remains elsewhere</h2>
<p>The full all-CS2 HotSpawn fixture board is an existing, separately maintained section. It is linked read-only below; this Day-5 TWC page does not reproduce or modify that board. Crowd picks / ownership, where present there, remain ownership context and never become these market probabilities.</p>
<div class="actions">
  <a class="button primary" href="{esc(data['hotspawn_coverage']['canonical_full_coverage_board_path'])}">Open complete HotSpawn CS2 board</a>
  <a class="button" href="{esc(data['hotspawn_coverage']['canonical_unresolved_board_path'])}">Open full-board unresolved limitations</a>
  {link('HotSpawn lobby source', data['hotspawn_coverage']['lobby_url'], css='button')}
</div>
<p class="small">Refresh note: {esc(data['hotspawn_coverage']['refresh_note'])} The dedicated workflow validates arithmetic, generated routes and source-link presence only; it does not refresh the bookmaker feed or guarantee future price availability.</p>
"""
    return document(
        "TWC 2026 Day 5: unresolved schedule and source limitations",
        "Separate review page for Day-5 kickoff disagreement, one-book odds limitations, VRS age, BO5 calibration and HotSpawn fixture coverage.",
        "unresolved",
        body,
    )


def render_pages(data: dict[str, Any] | None = None) -> dict[Path, str]:
    data = data or load_data()
    renderers = {"day5": render_day5, "unresolved": render_unresolved}
    return {
        ROOT / relative: renderers[renderer](data)
        for relative, renderer in PAGE_PATHS.items()
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if generated pages differ from committed files")
    args = parser.parse_args(argv)
    pages = render_pages()
    errors = []
    for path, content in pages.items():
        if args.check:
            if not path.exists():
                errors.append(f"Missing generated page: {path.relative_to(ROOT)}")
            elif path.read_text(encoding="utf-8") != content:
                errors.append(f"Generated page is stale: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"Wrote {path.relative_to(ROOT)}")
    if errors:
        raise SystemExit("\n".join(errors))
    if args.check:
        print("PASS: committed Day-5 pages match the research data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
