#!/usr/bin/env python3
"""Verify the independent extraction against its exact official-page archive.

Uses a local archived HTML file, or the pinned git object already fetched in this
checkout. No network calls, live-data assumptions, or bookmaker normalization.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent
PINNED_OBJECT = (
    "c48b28e8e16f9a33b473ff1dba22fc4add305acd:"
    "docs/evidence/probe/lobby.html"
)
FIELD_MAP = {
    "fixture_id": "id",
    "competition_name": "competition_name",
    "sport_alias": "sport_alias",
    "participant_0": "participants0_name",
    "participant_1": "participants1_name",
    "scheduled_start_raw_ms": "scheduled_start_time",
    "source_reported_status": "status",
    "best_of": "best_of",
    "series_format": "series_format",
}
EMPTY_FIELDS = (
    "bookmaker_source_url", "decimal_odds_0", "decimal_odds_1",
    "derived_probability_0", "derived_probability_1",
)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def verify(raw, audit):
    check(hashlib.sha256(raw).hexdigest() == audit["snapshot_sha256"],
          "Archive SHA-256 does not match; this audit concerns a pinned snapshot.")
    match = re.search(
        rb'<script id="ng-state" type="application/json">(.*?)</script>',
        raw, re.DOTALL,
    )
    check(match is not None, "Expected published ng-state script missing.")
    state = json.loads(match.group(1))
    entries = [v for v in state.values() if isinstance(v, dict)]
    fixtures = [v for v in entries
                if v.get("u", "").endswith("/api/v1/fixtures")]
    permalink_entries = [v for v in entries
                         if v.get("u", "").endswith("/fixtures/permalinks")]
    check(len(fixtures) == 1, "Ambiguous or missing fixtures payload.")
    check(len(permalink_entries) == 1, "Ambiguous or missing permalink payload.")
    originals = fixtures[0]["b"]
    permalinks = permalink_entries[0]["b"]["permalinks"]
    rows = audit["rows"]
    check(len(rows) == len(originals) == audit["fixture_count"],
          "Fixture count mismatch.")
    check(len({r["fixture_id"] for r in rows}) == len(rows),
          "Duplicate extracted fixture IDs.")
    response_time = dt.datetime.fromisoformat(audit["http_response_date_utc"])
    past_count = 0
    for row, original in zip(rows, originals):
        identifier = row["fixture_id"]
        for extracted, source in FIELD_MAP.items():
            check(row[extracted] == original[source],
                  f"{identifier}: {extracted} differs from source.")
        check(row["official_source_url"] == "https://play.hotspawn.com/lobby",
              f"{identifier}: wrong official lobby URL.")
        check(row["snapshot_evidence_url"] == audit["snapshot_evidence_url"],
              f"{identifier}: wrong snapshot link.")
        check(row["official_match_url"] == permalinks.get(identifier),
              f"{identifier}: inferred or incorrect match permalink.")
        for field in EMPTY_FIELDS:
            check(row[field] is None, f"{identifier}: unverified {field} filled.")
        start = dt.datetime.fromtimestamp(
            int(original["scheduled_start_time"]) / 1000, dt.timezone.utc,
        )
        check(row["scheduled_start_utc_derived"] == start.isoformat(),
              f"{identifier}: incorrect derived timestamp.")
        flags = ["external_odds_unverified", "series_format_unverified"]
        if start < response_time:
            flags.append("source_scheduled_start_precedes_response_date")
            past_count += 1
        check(row["review_flags"] == flags,
              f"{identifier}: flags differ from explicit evidence.")
        check(not any("picked_percent" in k or "points" in k for k in row),
              f"{identifier}: gamification input leaked into extraction.")
    check(past_count == audit["past_scheduled_start_count"],
          "Past timestamp count mismatch.")
    check(len(rows) - past_count == audit["future_scheduled_start_count"],
          "Non-past timestamp count mismatch.")
    for source_key, count_key in (("best_of", "missing_best_of_count"),
                                  ("series_format", "missing_series_format_count")):
        check(sum(r[source_key] is None for r in rows) == audit[count_key],
              f"{source_key}: missing-value count mismatch.")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, help="Exact archived lobby HTML")
    args = parser.parse_args()
    raw = (args.html.read_bytes() if args.html else subprocess.check_output(
        ["git", "show", PINNED_OBJECT], cwd=ROOT,
    ))
    audit = json.loads((ROOT / "lobby-snapshot-audit.json").read_text())
    count = verify(raw, audit)
    print(f"PASS: {count} fixture rows exactly match pinned official-page snapshot;")
    print("permalinks, missing values, derived flags and blank odds verified.")
    print("This validates an archived extraction, NOT fresh match odds or outcomes.")


if __name__ == "__main__":
    main()
