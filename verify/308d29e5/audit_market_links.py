#!/usr/bin/env python3
"""Audit market-board HotSpawn links against recorded source-published permalinks.

This is a read-only audit. It does not generate, alter, or certify any betting line.
It consumes two snapshots that already exist in the repository:
  * data/expanded/lines.json (the board under review)
  * data/picks_fixtures.json (a separate lobby-link capture with link-kind metadata)

The external route behavior in manual_checks is a recorded browser-reader observation,
not a claim that CI has re-fetched every one of the market board's links.
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
MARKET_PATH = ROOT / "data" / "expanded" / "lines.json"
PICKS_PATH = ROOT / "data" / "picks_fixtures.json"
FIXTURES_PATH = ROOT / "data" / "expanded" / "fixtures.json"
LOBBY_URL = "https://play.hotspawn.com/lobby"
NUMERIC_MATCH_ROUTE = re.compile(r"^https://www\.hotspawn\.com/matches/\d+/?$")

# Browser-reader source checks performed during this audit. The scope is deliberately
# limited to one fixture route and its source-published counterpart.
MANUAL_CHECKS = [
    {
        "checked_utc_precision": "minute",
        "checked_at_utc": "2026-10-13T22:54Z",
        "fixture_id": "1079546",
        "requested_numeric_route": "https://www.hotspawn.com/matches/1079546",
        "observed_final_url": "https://www.hotspawn.com/matches",
        "observed_page_title": "Matches - Hotspawn",
        "observation": "The numeric-ID path loaded the generic Matches listing, not the Zomblers vs Overtake Sector fixture page.",
        "source_published_permalink": "https://www.hotspawn.com/matches/zomblers-vs-overtake-sector-esl-challenger-league-season-52-north-america-cup-3-1079546",
        "observed_permalink_page_title": "Zomblers Vs Overtake Sector Counter-Strike 2 Match At ESL Challenger League Season 52: North America - Cup #3 - 1079546 - Hotspawn",
        "source_listing": "https://play.hotspawn.com/lobby",
        "scope_note": "One live fixture was checked at each route. This does not establish live reachability for every other fixture permalink.",
    }
]


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


def _is_cs2(row: dict[str, Any]) -> bool:
    return str(row.get("game", "")).strip().casefold() in {"cs2", "counter-strike 2", "counter strike 2"}


def _reference_for(fixture_id: str, picks_by_id: dict[str, dict[str, Any]]) -> tuple[str, str, str]:
    """Return a source-recorded URL, its classification, and its evidence note."""
    source_row = picks_by_id.get(fixture_id)
    if not source_row:
        return LOBBY_URL, "lobby_listing_fallback", "No matching fixture row exists in the separate link capture; use the official lobby, not a guessed URL."
    kind = str(source_row.get("hotspawn_match_url_kind") or "")
    url = str(source_row.get("hotspawn_match_url") or "")
    verified = source_row.get("hotspawn_match_url_verified") is True
    if kind == "lobby_published_permalink" and verified and url.startswith("https://www.hotspawn.com/matches/"):
        return url, "lobby_published_permalink", "Separate picks capture records a source-published permalink; this audit did not re-fetch this individual URL."
    if kind == "lobby_listing_fallback" and url == LOBBY_URL:
        return LOBBY_URL, "lobby_listing_fallback", "Separate picks capture used the official lobby listing because no per-match permalink was recorded."
    return LOBBY_URL, "lobby_listing_fallback", "Link capture has no validated per-match permalink; conservative official lobby fallback."


def build_report() -> dict[str, Any]:
    market = _load(MARKET_PATH)
    picks = _load(PICKS_PATH)
    raw_fixtures = _load(FIXTURES_PATH)
    market_rows = market.get("fixtures")
    picks_rows = picks.get("fixtures")
    fixtures_rows = raw_fixtures.get("fixtures")
    if not all(isinstance(x, list) for x in (market_rows, picks_rows, fixtures_rows)):
        raise ValueError("Expected fixtures arrays in all three captured datasets")

    picks_by_id = {str(row.get("fixture_id")): row for row in picks_rows if isinstance(row, dict)}
    fixture_source_by_id = {str(row.get("fixture_id")): row.get("source", {}) for row in fixtures_rows if isinstance(row, dict)}
    selected = [
        row for row in market_rows
        if isinstance(row, dict) and _is_cs2(row) and row.get("is_future") is True
    ]
    report_rows: list[dict[str, Any]] = []
    for row in sorted(selected, key=lambda x: (str(x.get("start_time_utc") or ""), str(x.get("fixture_id") or ""))):
        fixture_id = str(row.get("fixture_id") or "")
        market_url = str(row.get("hotspawn_match_url") or "")
        numeric_route = bool(NUMERIC_MATCH_ROUTE.fullmatch(market_url))
        reference_url, reference_kind, evidence_note = _reference_for(fixture_id, picks_by_id)
        raw_source = fixture_source_by_id.get(fixture_id) or {}
        reported_source_permalink = str(raw_source.get("hotspawn_match_url") or "")
        # The fixture capture commonly contains the same numeric route. It is not accepted
        # as a match-detail permalink because the live route check showed it lands on /matches.
        report_rows.append({
            "fixture_id": fixture_id,
            "game": "CS2",
            "scheduled_utc": row.get("start_time_utc"),
            "team_a": row.get("team_a"),
            "team_b": row.get("team_b"),
            "competition": row.get("competition"),
            "market_board_url": market_url,
            "numeric_id_route": numeric_route,
            "issue": "numeric_id_route_not_a_match_permalink" if numeric_route else None,
            "official_reference_url": reference_url,
            "official_reference_kind": reference_kind,
            "link_capture_note": evidence_note,
            "fixture_capture_url": reported_source_permalink,
        })

    numeric_count = sum(row["numeric_id_route"] for row in report_rows)
    reference_counts: dict[str, int] = {}
    for row in report_rows:
        key = row["official_reference_kind"]
        reference_counts[key] = reference_counts.get(key, 0) + 1
    return {
        "audit_id": "308d29e5-hotspawn-market-link-audit",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "scope": "Future CS2 fixtures in data/expanded/lines.json only. Betting quote values and odds eligibility are out of scope.",
        "inputs": {
            "market_lines_file": "data/expanded/lines.json",
            "market_snapshot_generated_at_utc": market.get("generated_at_utc"),
            "picks_link_capture_file": "data/picks_fixtures.json",
            "picks_link_capture_generated_at_utc": picks.get("generated_at_utc"),
            "hotspawn_fixture_capture_file": "data/expanded/fixtures.json",
            "hotspawn_fixture_capture_generated_at_utc": raw_fixtures.get("generated_at_utc"),
            "official_lobby": LOBBY_URL,
        },
        "summary": {
            "future_cs2_fixtures_reviewed": len(report_rows),
            "numeric_id_routes_in_market_board": numeric_count,
            "other_market_route_shapes": len(report_rows) - numeric_count,
            "reference_link_kinds_from_separate_capture": reference_counts,
            "status": "needs_review" if numeric_count else "no_numeric_id_route_issue_detected",
        },
        "manual_live_checks": MANUAL_CHECKS,
        "limitations": [
            "Only the fixture 1079546 numeric-ID route and its source-published counterpart were live-checked in this audit.",
            "The source-published link inventory is from a separate, older snapshot; it is shown as prior captured evidence, not a fresh check of all links.",
            "The numeric-ID URL is not treated as a valid match link solely because it contains a HotSpawn fixture ID.",
            "No probabilities, odds, picks, or team identities were recalculated or changed.",
        ],
        "rows": report_rows,
    }


def render(report: dict[str, Any]) -> str:
    summary = report["summary"]
    checked = report["manual_live_checks"][0]
    counts = summary["reference_link_kinds_from_separate_capture"]
    html_rows = []
    for row in report["rows"]:
        bad = row["numeric_id_route"]
        status = "Needs correction" if bad else "No numeric-ID pattern"
        market_link = html.escape(row["market_board_url"] or "(blank)")
        market_href = html.escape(row["market_board_url"], quote=True)
        reference_href = html.escape(row["official_reference_url"], quote=True)
        reference_text = "Open source-published match page" if row["official_reference_kind"] == "lobby_published_permalink" else "Open official lobby"
        issue = "Market link is `/matches/<id>`; a live example returned the general Matches listing." if bad else "No numeric-only route was detected in this row."
        when = html.escape(str(row.get("scheduled_utc") or ""))
        html_rows.append(
            '<tr><td data-label="Fixture">' + html.escape(row["fixture_id"]) + '</td>'
            '<td data-label="Scheduled UTC">' + when + '</td>'
            '<td data-label="Match"><strong>' + html.escape(str(row.get("team_a") or "")) + '</strong> vs <strong>' + html.escape(str(row.get("team_b") or "")) + '</strong><div class="small">' + html.escape(str(row.get("competition") or "")) + '</div></td>'
            '<td data-label="Current market URL"><a href="' + market_href + '" rel="noopener">' + market_link + '</a></td>'
            '<td data-label="Official reference"><a href="' + reference_href + '" rel="noopener">' + reference_text + '</a><div class="small">' + html.escape(row["official_reference_kind"]) + '</div><div class="small">' + html.escape(row["link_capture_note"]) + '</div></td>'
            '<td data-label="Finding"><span class="badge ' + ('bad' if bad else 'ok') + '">' + status + '</span><div class="small">' + html.escape(issue) + '</div></td></tr>'
        )
    if not html_rows:
        html_rows.append('<tr><td colspan="6">No future CS2 fixtures in the input snapshot.</td></tr>')
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>HotSpawn link audit · MaltaProj2</title>
<style>
:root{{--bg:#f5f7fb;--card:#fff;--ink:#142033;--muted:#607086;--line:#dce4ef;--blue:#174ea6;--red:#9a3412;--redbg:#fff1e8;--green:#166534;--greenbg:#e9f8ef}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}}main{{max-width:1180px;margin:auto;padding:24px 16px 56px}}header,.panel{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;margin:0 0 16px;box-shadow:0 8px 24px #1023450a}}h1{{font-size:clamp(1.7rem,4vw,2.5rem);line-height:1.15;margin:.15em 0 .4em}}h2{{font-size:1.22rem;margin:.2em 0 .75em}}p{{margin:.45em 0}}a{{color:var(--blue);overflow-wrap:anywhere}}.lede,.small,.muted{{color:var(--muted)}}.small{{font-size:.82rem}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px;margin:16px 0}}.card{{border:1px solid var(--line);border-radius:12px;padding:12px}}.num{{font-size:1.7rem;font-weight:750}}.pill{{display:inline-block;border-radius:99px;padding:2px 10px;font-size:.8rem;font-weight:700;background:var(--redbg);color:var(--red)}}.notice{{border-left:4px solid #ca6a12;padding:10px 12px;background:#fff8ee;border-radius:8px}}.scroll{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:900px}}th,td{{border-bottom:1px solid var(--line);padding:10px 9px;text-align:left;vertical-align:top}}th{{font-size:.82rem;color:var(--muted);background:#f8fafc;position:sticky;top:0}}.badge{{display:inline-block;padding:2px 8px;border-radius:20px;font-weight:700;font-size:.78rem}}.bad{{background:var(--redbg);color:var(--red)}}.ok{{background:var(--greenbg);color:var(--green)}}ul{{padding-left:20px}}footer{{color:var(--muted);font-size:.82rem;padding:10px 2px}}@media(max-width:700px){{main{{padding:12px 10px 32px}}header,.panel{{padding:16px;border-radius:12px}}.scroll{{overflow:visible}}table{{min-width:0}}thead{{display:none}}tbody,tr,td{{display:block;width:100%}}tr{{border:1px solid var(--line);border-radius:12px;margin:10px 0;padding:6px;background:#fff}}td{{border:0;padding:7px 8px}}td::before{{content:attr(data-label);display:block;font-size:.72rem;font-weight:750;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:2px}}}}
</style></head><body><main>
<header><div class="pill">Flagged for review · link integrity only</div><h1>HotSpawn match-link audit</h1>
<p class="lede">Independent check of HotSpawn navigation links on the published market CS2 board. This report does not change or recalculate any betting odds or probabilities.</p>
<div class="cards"><div class="card"><div class="num">{summary['future_cs2_fixtures_reviewed']}</div><div class="small">future CS2 rows in the audited snapshot</div></div><div class="card"><div class="num">{summary['numeric_id_routes_in_market_board']}</div><div class="small">numeric-ID match URLs detected</div></div><div class="card"><div class="num">{counts.get('lobby_published_permalink', 0)}</div><div class="small">recorded match permalinks in separate prior capture</div></div><div class="card"><div class="num">{counts.get('lobby_listing_fallback', 0)}</div><div class="small">official lobby fallbacks in separate prior capture</div></div></div>
<p><strong>Finding:</strong> {html.escape(str(summary['status']))}. A HotSpawn fixture ID embedded in a URL is not proof that the URL opens that fixture.</p></header>
<section class="panel"><h2>Live source check</h2><div class="notice"><strong>Fixture {html.escape(checked['fixture_id'])}.</strong> The numeric route <a href="{html.escape(checked['requested_numeric_route'], quote=True)}">{html.escape(checked['requested_numeric_route'])}</a> was served as <a href="{html.escape(checked['observed_final_url'], quote=True)}">{html.escape(checked['observed_final_url'])}</a> with page title <em>{html.escape(checked['observed_page_title'])}</em>, a general listing. The separate HotSpawn lobby capture recorded this source-published match permalink <a href="{html.escape(checked['source_published_permalink'], quote=True)}">{html.escape(checked['source_published_permalink'])}</a>; when opened in this one manual check, its page title identified {html.escape(checked['fixture_id'])} and the matching teams. Read at {html.escape(checked['checked_at_utc'])} (minute precision).</div>
<p class="small">The live check proves the behavior for this one fixture only; no claim is made that every other slug was re-fetched. Source listing: <a href="{LOBBY_URL}">HotSpawn Pick'ems lobby</a>.</p></section>
<section class="panel"><h2>Fixture-by-fixture review</h2>
<p class="muted">The market board URL is shown as published. The official reference column uses a permalink or lobby fallback recorded in the separate picks capture. Snapshot times: market <code>{html.escape(str(report['inputs']['market_snapshot_generated_at_utc']))}</code>; link inventory <code>{html.escape(str(report['inputs']['picks_link_capture_generated_at_utc']))}</code>. The link inventory is older and is not represented as freshly re-verified.</p>
<div class="scroll"><table><thead><tr><th>Fixture</th><th>Scheduled UTC</th><th>Match</th><th>Market URL</th><th>Official reference</th><th>Finding</th></tr></thead><tbody>{''.join(html_rows)}</tbody></table></div></section>
<section class="panel"><h2>Method and limits</h2><ul>{''.join('<li>'+html.escape(x)+'</li>' for x in report['limitations'])}</ul><p>Primary manual sources: <a href="{LOBBY_URL}">HotSpawn Pick'ems lobby</a>; <a href="{html.escape(checked['requested_numeric_route'], quote=True)}">numeric route tested</a>; <a href="{html.escape(checked['source_published_permalink'], quote=True)}">source-published match permalink tested</a>.</p></section>
<footer>Generated by <code>verify/308d29e5/audit_market_links.py</code>. Data snapshot timestamps and per-row source references are retained in <a href="link_audit.json">link_audit.json</a>. This audit is not betting advice.</footer>
</main></body></html>'''
    return page


def main() -> int:
    report = build_report()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "link_audit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "index.html").write_text(render(report), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Wrote {OUT / 'index.html'} and {OUT / 'link_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
