#!/usr/bin/env python3
"""Build the session-797e94ea read-only source-integrity audit.

This audit intentionally consumes the repository's captured root snapshot rather
than collecting or changing markets.  It proves reproducible properties of that
snapshot (links, joins, arithmetic, timestamps and rendered coverage) and keeps
manual public-source observations in a separate ledger.  It must never turn a
missing quote into a probability.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import re
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LINES_PATH = ROOT / "data" / "lines.json"
CURRENT_PATH = ROOT / "data" / "current_probabilities.json"
ROOT_CS2_PATH = ROOT / "cs2.html"
REPORT_PATH = HERE / "report.json"
LEDGER_PATH = HERE / "source_check_ledger.json"
PAGE_PATH = HERE / "index.html"

AUDIT_OBSERVED_AT = "2026-10-14T01:40:24Z"
LOBBY_URL = "https://play.hotspawn.com/lobby"
FIXTURES_URL = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def is_https(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("https://")


def no_vig(decimal_a: float, decimal_b: float) -> tuple[float, float]:
    raw_a = 1.0 / decimal_a
    raw_b = 1.0 / decimal_b
    total = raw_a + raw_b
    return raw_a / total, raw_b / total


def rounded(value: float) -> float:
    return round(value, 4)


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def anchor(url: str, label: str) -> str:
    return f'<a href="{escape(url, quote=True)}" rel="noopener noreferrer">{escape(label)}</a>'


def source_url(quote: dict[str, Any]) -> str:
    # A direct public event page is most useful to a human where available.  The
    # API endpoint remains the exact source for the captured quote.
    return quote.get("source_public_url") or quote.get("source_api_url") or ""


def source_links(quote: dict[str, Any]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    public = quote.get("source_public_url")
    api = quote.get("source_api_url")
    name = quote.get("source_name", "external source")
    if is_https(public):
        links.append({"label": name, "url": public})
    if is_https(api):
        links.append({"label": "quote API" if public else name, "url": api})
    return links


def manual_ledger() -> dict[str, Any]:
    """A concise ledger of the source pages manually read during this audit.

    Values are observations, not a second live quote feed and not inputs to any
    published probability.  Exact public URLs are retained for manual review.
    """
    pinnacle_base = "https://guest.api.arcadia.pinnacle.com/0.1/matchups/"
    return {
        "audit_observed_at_utc": AUDIT_OBSERVED_AT,
        "collection_method": (
            "One read of the public pages/endpoints using the platform page reader. "
            "This is not a replacement price feed: a readable response is not a certification of the "
            "operator, a promise of availability, or a current line for a later reader."
        ),
        "checks": [
            {
                "id": "SRC-797-01",
                "status": "observed_price_moved",
                "fixture_id": "1080176",
                "fixture": "9z vs Aurora",
                "source_url": pinnacle_base + "1638111785",
                "market_url": pinnacle_base + "1638111785/markets/related/straight",
                "observed": {
                    "participants": ["9z", "Aurora"],
                    "start_time_utc": "2026-10-14T08:30:00Z",
                    "full_match_market_key": "s;0;m",
                    "market_status": "open",
                    "american_prices": [241, -307],
                },
                "snapshot_at_011557z": {"american_prices": [255, -326]},
                "note": (
                    "The same public Pinnacle market was readable and aligned on participants, kickoff, "
                    "full-match key and open status, but the price had moved. The root value is therefore a "
                    "dated snapshot, not a live price at this audit time."
                ),
            },
            {
                "id": "SRC-797-02",
                "status": "observed_snapshot_price_matches",
                "fixture_id": "1079439",
                "fixture": "HOTU vs Fnatic",
                "source_url": pinnacle_base + "1637867148",
                "market_url": pinnacle_base + "1637867148/markets/related/straight",
                "observed": {
                    "participants": ["HOTU", "fnatic"],
                    "start_time_utc": "2026-10-14T10:00:00Z",
                    "full_match_market_key": "s;0;m",
                    "market_status": "open",
                    "american_prices": [-101, -125],
                },
                "snapshot_at_011555z": {"american_prices": [-101, -125]},
                "note": "This single re-read matched the archived Pinnacle full-match price at the stated time.",
            },
            {
                "id": "SRC-797-03",
                "status": "observed_metadata_alignment_only",
                "fixture_id": "1080177",
                "fixture": "Falcons vs Ninjas in Pyjamas",
                "source_url": pinnacle_base + "1638111674",
                "market_url": pinnacle_base + "1638111674/markets/related/straight",
                "observed": {
                    "participants": ["Falcons", "Ninjas In Pyjamas"],
                    "start_time_utc": "2026-10-14T11:00:00Z",
                    "matchup_status": "pending",
                },
                "note": "Participants and kickoff aligned; this audit did not record a second full-match price.",
            },
            {
                "id": "SRC-797-04",
                "status": "observed_metadata_alignment_only",
                "fixture_id": "1079440",
                "fixture": "MIBR vs BC.Game",
                "source_url": pinnacle_base + "1637936745",
                "market_url": pinnacle_base + "1637936745/markets/related/straight",
                "observed": {
                    "participants": ["MIBR", "BC.Game"],
                    "start_time_utc": "2026-10-15T10:00:00Z",
                    "matchup_status": "pending",
                },
                "note": "Participants and kickoff aligned; this audit did not record a second full-match price.",
            },
            {
                "id": "SRC-797-05",
                "status": "observed_metadata_alignment_only",
                "fixture_id": "1079442",
                "fixture": "Heroic vs Envy",
                "source_url": pinnacle_base + "1637999450",
                "market_url": pinnacle_base + "1637999450/markets/related/straight",
                "observed": {
                    "participants": ["HEROIC", "Envy"],
                    "start_time_utc": "2026-10-15T10:00:00Z",
                    "matchup_status": "pending",
                },
                "note": "Participants and kickoff aligned (case-only team-name variation); no second full-match price recorded.",
            },
            {
                "id": "SRC-797-06",
                "status": "public_coupon_readable_direct_event_sample_blocked",
                "fixture_id": "1079438",
                "fixture": "Astralis vs Sashi",
                "source_url": "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports",
                "direct_event_url": "https://www.bovada.lv/esports/counter-strike-2/pulse-beat-iii/astralis-sashi-esport-202610140600",
                "observed": {
                    "coupon_endpoint": "returned JSON",
                    "direct_event_page": "Not Found / reCAPTCHA in the audit reader",
                },
                "note": (
                    "This is a read-access observation for one event page, not evidence that any archived Bovada "
                    "price is wrong. Exact current price re-validation from the direct event page is unresolved."
                ),
            },
            {
                "id": "SRC-797-07",
                "status": "lobby_counter_changed",
                "fixture_id": None,
                "fixture": "HotSpawn Pick'ems lobby",
                "source_url": LOBBY_URL,
                "observed": {
                    "matches_this_week": 68,
                    "all_tiers": 89,
                    "tier_counts": {"b": 25, "c": 60, "s": 4},
                },
                "snapshot_at_011608z": {
                    "root_fixture_total": 90,
                    "tier_counts": {"b": 25, "c": 61, "s": 4},
                },
                "note": (
                    "The rendered lobby counter differed from the root snapshot less than half an hour later. "
                    "This audit does not infer which fixture changed or alter the captured inventory."
                ),
            },
        ],
    }


def build_report() -> dict[str, Any]:
    lines = load_json(LINES_PATH)
    current = load_json(CURRENT_PATH)
    line_fixtures = lines["fixtures"]
    current_rows = current["rows"]
    generated_at = parse_utc(lines["generated_at_utc"])
    max_age = int(lines["method"]["max_age_seconds"])

    current_by_id = {str(row["fixture_id"]): row for row in current_rows}
    priced = [fixture for fixture in line_fixtures if fixture.get("bookmaker_lines")]
    result_rows: list[dict[str, Any]] = []
    errors: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    for fixture in priced:
        fixture_id = str(fixture["fixture_id"])
        quote_rows = fixture["bookmaker_lines"]
        current_row = current_by_id.get(fixture_id)
        require(current_row is not None, f"{fixture_id}: missing from current_probabilities")
        fixture_start = parse_utc(fixture["start_time_utc"])
        per_source: list[dict[str, Any]] = []
        source_probabilities: list[tuple[float, float]] = []
        fixture_pass = True
        fixture_issues: list[str] = []

        for quote in quote_rows:
            odds_a = float(quote["decimal_odds_a"])
            odds_b = float(quote["decimal_odds_b"])
            exp_a, exp_b = no_vig(odds_a, odds_b)
            stored_a = float(quote["derived_probability_a"])
            stored_b = float(quote["derived_probability_b"])
            retrieved = parse_utc(quote["retrieved_at_utc"])
            age_seconds = (generated_at - retrieved).total_seconds()
            links = source_links(quote)
            checks = {
                "https_source": bool(links) and all(is_https(item["url"]) for item in links),
                # Pinnacle calls the series market "full match".  Bovada exposes
                # the same match-winner market with period label "Game" but an
                # explicit full-match market type and its main 2W-12 key.  Do not
                # mislabel that schema difference as a map market.
                "full_match": quote.get("market_period") == "full match"
                or (
                    "full match" in str(quote.get("market_type", "")).lower()
                    and quote.get("source_market_key") == "2W-12"
                ),
                "prematch": quote.get("market_is_live") is False,
                "open": str(quote.get("market_status", "")).lower() in {"open", "o"},
                "team_alignment": quote.get("outcome_alignment_verified") is True,
                "kickoff_alignment": quote.get("start_time_agrees_with_fixture") is True,
                "fresh_at_capture": 0 <= age_seconds <= max_age,
                "before_fixture": retrieved < fixture_start,
                "math": abs(stored_a - rounded(exp_a)) <= 0.00011
                and abs(stored_b - rounded(exp_b)) <= 0.00011
                and abs((stored_a + stored_b) - 1.0) <= 0.00011,
            }
            failed = [name for name, passed in checks.items() if not passed]
            if failed:
                fixture_pass = False
                fixture_issues.extend(f"{quote.get('source_key')}: {name}" for name in failed)
            source_probabilities.append((stored_a, stored_b))
            per_source.append(
                {
                    "source_key": quote.get("source_key"),
                    "source_name": quote.get("source_name"),
                    "links": links,
                    "retrieved_at_utc": quote.get("retrieved_at_utc"),
                    "decimal_odds": [odds_a, odds_b],
                    "stored_probability": [stored_a, stored_b],
                    "recomputed_probability": [rounded(exp_a), rounded(exp_b)],
                    "overround": quote.get("overround"),
                    "checks": checks,
                }
            )

        consensus = fixture["derived"]["consensus"]
        expected_a = round(sum(pair[0] for pair in source_probabilities) / len(source_probabilities), 4)
        expected_b = round(sum(pair[1] for pair in source_probabilities) / len(source_probabilities), 4)
        consensus_checks = {
            "consensus_math": abs(float(consensus["derived_probability_a_mean"]) - expected_a) <= 0.00011
            and abs(float(consensus["derived_probability_b_mean"]) - expected_b) <= 0.00011,
            "current_mirror": current_row is not None
            and abs(float(current_row["probability_a"]) - float(consensus["derived_probability_a_mean"])) <= 0.00011
            and abs(float(current_row["probability_b"]) - float(consensus["derived_probability_b_mean"])) <= 0.00011,
            "external_source_count": int(consensus["n_sources"]) == len(quote_rows),
            "hotspawn_is_discovery_only": fixture.get("hotspawn_match_url") == FIXTURES_URL,
        }
        failed_consensus = [name for name, passed in consensus_checks.items() if not passed]
        if failed_consensus:
            fixture_pass = False
            fixture_issues.extend(failed_consensus)

        result_rows.append(
            {
                "fixture_id": fixture_id,
                "competition": fixture["competition"],
                "tier": fixture["tier"],
                "start_time_utc": fixture["start_time_utc"],
                "team_a": fixture["team_a"],
                "team_b": fixture["team_b"],
                "hotspawn_fixture_source": fixture["hotspawn_match_url"],
                "per_source": per_source,
                "consensus": {
                    "stored_probability_a": consensus["derived_probability_a_mean"],
                    "stored_probability_b": consensus["derived_probability_b_mean"],
                    "recomputed_probability_a": expected_a,
                    "recomputed_probability_b": expected_b,
                    "n_sources": consensus["n_sources"],
                },
                "checks": consensus_checks,
                "status": "pass" if fixture_pass else "fail",
                "issues": fixture_issues,
            }
        )

    # The source snapshots carrying probabilities must not carry a crowd-picked
    # input. The broader raw fixture dataset intentionally does retain it.
    analysis_text = json.dumps({"lines": lines, "current": current}, sort_keys=True).lower()
    crowd_terms = re.findall(r'"[^" ]*picked[^" ]*"', analysis_text)
    require(not crowd_terms, f"analysis snapshots contain crowd-pick keys: {sorted(set(crowd_terms))}")

    # Rendered root output has a table row for every priced fixture and links to
    # the captured source URL (the audit does not make a network request here).
    cs2_html = ROOT_CS2_PATH.read_text(encoding="utf-8")
    render_missing: list[str] = []
    for row in result_rows:
        if row["team_a"] not in cs2_html or row["team_b"] not in cs2_html:
            render_missing.append(f"{row['fixture_id']}: teams absent from cs2.html")
        for quote in row["per_source"]:
            for link in quote["links"]:
                if link["url"] not in cs2_html:
                    render_missing.append(f"{row['fixture_id']}: source link absent from cs2.html")
    require(not render_missing, "; ".join(render_missing))

    checks = [
        {
            "id": "A-797-01",
            "status": "pass" if not errors else "fail",
            "name": "Captured root arithmetic and consensus",
            "detail": f"Recomputed no-vig shares, consensus, and A+B=100% for {len(priced)} quoted fixtures / {sum(len(row['per_source']) for row in result_rows)} quote rows.",
            "sources": [FIXTURES_URL] + sorted({link["url"] for row in result_rows for quote in row["per_source"] for link in quote["links"]}),
        },
        {
            "id": "A-797-02",
            "status": "pass" if not errors else "fail",
            "name": "Capture-time eligibility fields",
            "detail": f"Checked HTTPS source links, full-match market, non-live/open state, verified alignment, capture age ≤ {max_age // 3600}h, and quote before kickoff.",
            "sources": [FIXTURES_URL],
        },
        {
            "id": "A-797-03",
            "status": "pass" if not crowd_terms else "fail",
            "name": "Crowd percentages excluded from root analysis inputs",
            "detail": "The audited analysis snapshots (`data/lines.json` and `data/current_probabilities.json`) contain no key with ‘picked’; raw fixture discovery is intentionally outside this check.",
            "sources": [LOBBY_URL, FIXTURES_URL],
        },
        {
            "id": "A-797-04",
            "status": "pass" if not render_missing else "fail",
            "name": "Rendered root CS2 source-link coverage",
            "detail": "Every audited quoted fixture and its captured external source link is present in `cs2.html`.",
            "sources": [FIXTURES_URL],
        },
    ]

    findings = [
        {
            "id": "F-797-01",
            "severity": "needs review",
            "title": "One direct Pinnacle re-read moved within the same hour",
            "detail": "9z vs Aurora was captured at +255 / −326 at 01:15:57Z; public re-read showed +241 / −307. Do not call the stored 26.9% / 73.1% a live line after its timestamp. The automatic collector, not this audit, must refresh it.",
            "sources": [
                pinnacle_url("1638111785"),
                pinnacle_market_url("1638111785"),
            ],
        },
        {
            "id": "F-797-02",
            "severity": "needs review",
            "title": "Rendered HotSpawn counter changed from 90 to 89",
            "detail": "The root snapshot at 01:16:08Z records 90 fixtures (B25/C61/S4). The public lobby read at 01:40:24Z rendered All tiers (89), B25/C60/S4. The changed fixture is not inferred here; count drift means snapshot coverage and live lobby coverage must remain time-stamped.",
            "sources": [LOBBY_URL, FIXTURES_URL],
        },
        {
            "id": "F-797-03",
            "severity": "needs review",
            "title": "Direct Bovada event-page review was blocked in this reader",
            "detail": "The public Bovada coupon endpoint returned JSON, but one direct Astralis–Sashi event page returned Not Found / reCAPTCHA. This is an access limitation, not a finding that the stored quote is wrong. The stored API/event identifiers and capture time should remain visible for review.",
            "sources": [
                "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports",
                "https://www.bovada.lv/esports/counter-strike-2/pulse-beat-iii/astralis-sashi-esport-202610140600",
            ],
        },
        {
            "id": "F-797-04",
            "severity": "scope boundary",
            "title": "This audit does not validate the other independently published boards",
            "detail": "The repository intentionally preserves dated research sections with different source policies. This report validates only the root 01:16Z primary-bookmaker snapshot and must not be read as certification of every probability elsewhere in the repository.",
            "sources": [FIXTURES_URL],
        },
    ]

    return {
        "audit_id": "797e94ea",
        "audit_observed_at_utc": AUDIT_OBSERVED_AT,
        "scope": {
            "included": ["data/lines.json", "data/current_probabilities.json", "cs2.html"],
            "excluded": "All other research boards and live/legacy snapshots; no source collection or mutation performed.",
        },
        "source_snapshot": {
            "lines_generated_at_utc": lines["generated_at_utc"],
            "odds_collected_at_utc": lines["odds_collected_at_utc"],
            "fixture_list_collected_at_utc": lines["fixture_list_collected_at_utc"],
            "fixture_total": len(line_fixtures),
            "quoted_fixture_total": len(priced),
            "unquoted_fixture_total": len(line_fixtures) - len(priced),
            "maximum_quote_age_seconds": max_age,
        },
        "summary": {
            "status": "pass" if not errors else "fail",
            "quoted_fixtures_checked": len(result_rows),
            "quote_rows_checked": sum(len(row["per_source"]) for row in result_rows),
            # current_probabilities also preserves rows outside this 90-fixture
            # root snapshot. Count blanks only after joining on the snapshot ids.
            "root_rows_with_blank_probability": sum(
                1
                for fixture in line_fixtures
                if current_by_id.get(str(fixture["fixture_id"]), {}).get("probability_a") is None
            ),
            "errors": errors,
        },
        "checks": checks,
        "rows": result_rows,
        "findings": findings,
    }


def pinnacle_url(matchup_id: str) -> str:
    return f"https://guest.api.arcadia.pinnacle.com/0.1/matchups/{matchup_id}"


def pinnacle_market_url(matchup_id: str) -> str:
    return f"{pinnacle_url(matchup_id)}/markets/related/straight"


def render_report(report: dict[str, Any], ledger: dict[str, Any]) -> str:
    rows_html: list[str] = []
    for row in report["rows"]:
        source_html: list[str] = []
        for quote in row["per_source"]:
            quote_links = " · ".join(anchor(item["url"], item["label"]) for item in quote["links"])
            source_html.append(
                f"<div class=\"source\"><strong>{escape(quote['source_name'])}</strong><br>{quote_links}<br>"
                f"<span class=\"muted\">captured {escape(quote['retrieved_at_utc'])} · "
                f"decimal {quote['decimal_odds'][0]:.6g}/{quote['decimal_odds'][1]:.6g}</span></div>"
            )
        source_checks = "; ".join(
            f"{escape(quote['source_name'])}: {pct(quote['stored_probability'][0])}/{pct(quote['stored_probability'][1])}"
            f" → {pct(quote['recomputed_probability'][0])}/{pct(quote['recomputed_probability'][1])}"
            for quote in row["per_source"]
        )
        status = "pass" if row["status"] == "pass" else "fail"
        rows_html.append(
            "<tr data-fixture=\"%s\">"
            "<td data-label=\"Fixture\"><strong>%s vs %s</strong><br><span class=\"muted\">%s · %s · %s</span><br>%s</td>"
            "<td data-label=\"Official discovery source\">%s</td>"
            "<td data-label=\"External quote source(s)\">%s</td>"
            "<td data-label=\"Stored / recomputed no-vig\">%s</td>"
            "<td data-label=\"Consensus A / B\"><strong>%s / %s</strong><br><span class=\"muted\">%d source(s)</span></td>"
            "<td data-label=\"Audit result\"><span class=\"%s\">%s</span>%s</td>"
            "</tr>"
            % (
                escape(row["fixture_id"]),
                escape(row["team_a"]),
                escape(row["team_b"]),
                escape(row["start_time_utc"]),
                escape(row["tier"].upper()),
                escape(row["competition"]),
                anchor(row["hotspawn_fixture_source"], "HotSpawn fixtures API"),
                anchor(row["hotspawn_fixture_source"], "fixture API"),
                "".join(source_html),
                source_checks,
                pct(row["consensus"]["stored_probability_a"]),
                pct(row["consensus"]["stored_probability_b"]),
                row["consensus"]["n_sources"],
                status,
                escape(row["status"].upper()),
                "" if not row["issues"] else "<br><span class=\"bad\">" + escape("; ".join(row["issues"])) + "</span>",
            )
        )

    checks_html = "".join(
        "<tr><td data-label=\"Check\"><strong>%s</strong><br>%s</td><td data-label=\"Result\"><span class=\"%s\">%s</span></td><td data-label=\"Manual-review sources\">%s</td></tr>"
        % (
            escape(check["id"]),
            escape(check["name"] + ": " + check["detail"]),
            "pass" if check["status"] == "pass" else "fail",
            escape(check["status"].upper()),
            " · ".join(anchor(url, "source") for url in check["sources"]),
        )
        for check in report["checks"]
    )
    findings_html = "".join(
        "<article class=\"finding %s\"><h3>%s — %s</h3><p>%s</p><p class=\"sources\">%s</p></article>"
        % (
            escape(finding["severity"].replace(" ", "-")),
            escape(finding["id"]),
            escape(finding["title"]),
            escape(finding["detail"]),
            " · ".join(anchor(url, "source") for url in finding["sources"]),
        )
        for finding in report["findings"]
    )
    ledger_html = "".join(
        "<tr><td data-label=\"ID\"><strong>%s</strong><br>%s</td><td data-label=\"Observation\">%s</td><td data-label=\"Source\">%s%s</td></tr>"
        % (
            escape(item["id"]),
            escape(item["status"]),
            escape(item["note"]),
            anchor(item["source_url"], "read source"),
            " · " + anchor(item["market_url"], "market") if item.get("market_url") else "",
        )
        for item in ledger["checks"]
    )
    summary = report["summary"]
    source = report["source_snapshot"]
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Read-only source-integrity audit of a dated HotSpawn CS2 probability snapshot.">
<title>Source-integrity audit · session 797e94ea</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header><div class="shell"><a class="back" href="../../index.html">← Root dashboard</a><span>Independent audit · 797e94ea</span></div></header>
<main class="shell">
  <p class="eyebrow">READ-ONLY QA · DATED SNAPSHOT</p>
  <h1>Primary-source integrity audit</h1>
  <p class="lead">A reproducible audit of the root CS2 probability snapshot captured at <strong>{escape(source['lines_generated_at_utc'])}</strong>. It checks data linkage and arithmetic; it does <strong>not</strong> create picks, fetch a replacement line, or certify every other board in this repository.</p>
  <section class="summary" aria-label="audit summary">
    <div><strong>{summary['quoted_fixtures_checked']}</strong><span>quoted fixtures checked</span></div>
    <div><strong>{summary['quote_rows_checked']}</strong><span>external quote rows checked</span></div>
    <div><strong>{source['unquoted_fixture_total']}</strong><span>root rows intentionally blank</span></div>
    <div><strong class="{('pass' if summary['status'] == 'pass' else 'fail')}">{escape(summary['status'].upper())}</strong><span>mechanical audit result</span></div>
  </section>
  <aside class="notice"><strong>Do not treat this as live pricing.</strong> The audit’s direct re-read found a moved Pinnacle line and a changed lobby counter. Use the capture timestamp and exact source link on every row; blank remains the correct result when a source cannot be confirmed.</aside>

  <h2>Audit checks</h2>
  <div class="tablewrap"><table class="cards"><thead><tr><th>Check</th><th>Result</th><th>Manual-review sources</th></tr></thead><tbody>{checks_html}</tbody></table></div>

  <h2>Quoted fixture rows — snapshot arithmetic</h2>
  <p class="muted">“Stored / recomputed” is a mechanical re-calculation from the captured decimal odds: <code>(1/A) / ((1/A)+(1/B))</code>. Every fixture row below links to the public HotSpawn discovery feed and the external quote page/API used by the snapshot.</p>
  <div class="tablewrap"><table class="cards"><thead><tr><th>Fixture</th><th>Official discovery source</th><th>External quote source(s)</th><th>Stored / recomputed no-vig</th><th>Consensus A / B</th><th>Audit result</th></tr></thead><tbody>{''.join(rows_html)}</tbody></table></div>

  <h2>Manual public-source read ledger</h2>
  <p class="muted">Observed {escape(ledger['audit_observed_at_utc'])}. This is a compact review ledger, not a replacement price feed. Values from the ledger are not used by any probability.</p>
  <div class="tablewrap"><table class="cards"><thead><tr><th>ID</th><th>Observation</th><th>Source</th></tr></thead><tbody>{ledger_html}</tbody></table></div>

  <h2>Flagged for review</h2>
  {findings_html}

  <h2>Scope and reproduction</h2>
  <p>This report reads only <a href="../../data/lines.json">data/lines.json</a>, <a href="../../data/current_probabilities.json">data/current_probabilities.json</a>, and the rendered <a href="../../cs2.html">root CS2 table</a>. Run <code>python3 audits/797e94ea/build_audit.py</code> and <code>python3 -m unittest tests.test_797e94ea</code> from the repository root. The machine-readable outputs are <a href="report.json">report.json</a> and <a href="source_check_ledger.json">source_check_ledger.json</a>.</p>
</main>
<footer class="shell">Audit observed {escape(AUDIT_OBSERVED_AT)} · No crowd-picked percentage is used by the audited inputs · Source availability and prices can change.</footer>
</body>
</html>
"""


def main() -> int:
    ledger = manual_ledger()
    report = build_report()
    dump_json(LEDGER_PATH, ledger)
    dump_json(REPORT_PATH, report)
    PAGE_PATH.write_text(render_report(report, ledger), encoding="utf-8")
    print(
        "audit built: "
        f"{report['summary']['quoted_fixtures_checked']} fixtures, "
        f"{report['summary']['quote_rows_checked']} quote rows, "
        f"status={report['summary']['status']}"
    )
    return 0 if report["summary"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
