#!/usr/bin/env python3
"""Build the a666cd41 source-provenance audit for the HotSpawn CS2 lobby.

This is intentionally an independent, offline verifier of the f7279a54 snapshot.  It does
not fetch a bookmaker page, does not read HotSpawn crowd ownership and does not fill missing
prices.  Every published probability is re-derived from the captured two-way price in
``data/f7279a54/snapshot.json``.

Owned outputs:
  * data/a666cd41/report.json
  * audits/a666cd41/{index,picks,unresolved,evidence,method}.html

The source board is used only to define the lobby fixtures and its strict market eligibility.
A narrowly documented exception allows a source team name whose *complete token sequence* is
an exact reordering of the lobby team name, provided the opponent and start time also match.
That rule is designed for "Apogee Betclic" / "Betclic Apogee"; it never guesses aliases.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote as urlquote

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOARD = ROOT / "data/f7279a54/board.json"
DEFAULT_SNAPSHOT = ROOT / "data/f7279a54/snapshot.json"
DEFAULT_REPORT = ROOT / "data/a666cd41/report.json"
DEFAULT_SITE = ROOT / "audits/a666cd41"

SCHEMA = "a666cd41.provenance-audit.v1"
GENERATOR_VERSION = "2026-10-19.1"
REPO = "https://github.com/buffedlizard55-lab/MaltaProj2"
SOURCE_BRANCH = "main"
GENERIC_PREFIX = {"team", "the"}
GENERIC_SUFFIX = {"team", "esports", "esport", "gaming", "gg", "club"}
SOURCE_WEIGHTS = {"pinnacle": 2.0, "bovada": 1.0, "melbet": 1.0}
TIME_TOLERANCE = timedelta(minutes=5)
QUOTE_FRESHNESS = timedelta(hours=4)


class AuditError(ValueError):
    """The source inputs fail an evidence invariant and must not be published."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuditError(f"cannot read JSON evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"JSON evidence {path} is not an object")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def abs_time_difference(a: Any, b: Any) -> timedelta | None:
    aa, bb = parse_utc(a), parse_utc(b)
    if aa is None or bb is None:
        return None
    return abs(aa - bb)


def team_tokens(name: Any) -> tuple[str, ...]:
    """Conservative exact-name key: accents/case/punctuation + generic org suffixes only.

    This deliberately does *not* include an alias table, substring logic, or fuzzy matching.
    Names such as ``WBT`` and ``WROTBERRY`` therefore remain different and cannot be joined.
    """
    text = unicodedata.normalize("NFKD", str(name or "")).casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    parts = [part for part in re.split(r"[^a-z0-9]+", text) if part]
    while len(parts) > 1 and parts[0] in GENERIC_PREFIX:
        parts.pop(0)
    while len(parts) > 1 and parts[-1] in GENERIC_SUFFIX:
        parts.pop()
    return tuple(parts)


def ordered_orientation(fixture: dict[str, Any], quote: dict[str, Any]) -> bool | None:
    """Return False/True for same/reversed orientation under the ordinary strict rule."""
    fa, fb = team_tokens(fixture.get("team_a")), team_tokens(fixture.get("team_b"))
    qa, qb = team_tokens(quote.get("team_a")), team_tokens(quote.get("team_b"))
    if fa and fb and fa == qa and fb == qb:
        return False
    if fa and fb and fa == qb and fb == qa:
        return True
    return None


def reordered_orientation(fixture: dict[str, Any], quote: dict[str, Any]) -> bool | None:
    """Return orientation only for a genuine exact token-order reordering.

    Both competitors must independently have identical token multisets, one name must actually
    be out of order, and the ordinary ordered rule must have failed.  It is intentionally much
    stricter than a similar-name or partial-name comparison.
    """
    if ordered_orientation(fixture, quote) is not None:
        return None
    fa, fb = team_tokens(fixture.get("team_a")), team_tokens(fixture.get("team_b"))
    qa, qb = team_tokens(quote.get("team_a")), team_tokens(quote.get("team_b"))
    if not fa or not fb or not qa or not qb:
        return None
    if Counter(fa) == Counter(qa) and Counter(fb) == Counter(qb):
        return False
    if Counter(fa) == Counter(qb) and Counter(fb) == Counter(qa):
        return True
    return None


def american_to_decimal(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price):
        return None
    if price >= 100:
        return 1 + price / 100
    if price <= -100:
        return 1 + 100 / abs(price)
    return None


def rederive_two_way(quote: dict[str, Any]) -> dict[str, float] | None:
    """Independently calculate no-vig probabilities from captured raw odds."""
    try:
        raw_a, raw_b = float(quote["raw_a"]), float(quote["raw_b"])
    except (KeyError, TypeError, ValueError):
        return None
    fmt = quote.get("raw_format")
    if fmt == "american":
        decimal_a, decimal_b = american_to_decimal(raw_a), american_to_decimal(raw_b)
    elif fmt == "decimal":
        decimal_a, decimal_b = raw_a, raw_b
    elif fmt == "yes mid ($)" and 0 < raw_a < 1 and 0 < raw_b < 1:
        decimal_a, decimal_b = 1 / raw_a, 1 / raw_b
    else:
        return None
    if decimal_a is None or decimal_b is None:
        return None
    if not all(math.isfinite(number) and number > 1 for number in (decimal_a, decimal_b)):
        return None
    implied_a, implied_b = 1 / decimal_a, 1 / decimal_b
    overround = implied_a + implied_b
    # A pathological payload is not a usable two-way bookmaker market.
    if not 0.95 <= overround <= 1.30:
        return None
    return {
        "decimal_a": decimal_a,
        "decimal_b": decimal_b,
        "prob_a": implied_a / overround,
        "prob_b": implied_b / overround,
        "overround": overround,
    }


def source_time_is_strict(fixture: dict[str, Any], quote: dict[str, Any]) -> tuple[bool, float | None]:
    if quote.get("start_is_approx"):
        return False, None
    difference = abs_time_difference(fixture.get("start_utc"), quote.get("start_utc"))
    if difference is None:
        return False, None
    return difference <= TIME_TOLERANCE, difference.total_seconds() / 3600


def quote_is_fresh(quote: dict[str, Any], collected_to: datetime) -> bool:
    observed = parse_utc(quote.get("retrieved_utc"))
    return observed is not None and timedelta(0) <= collected_to - observed <= QUOTE_FRESHNESS


def fixture_quote_key(quote: dict[str, Any]) -> tuple[str, str]:
    return str(quote.get("source_key") or ""), str(quote.get("event_id") or "")


def consensus(entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not entries:
        raise AuditError("cannot calculate a consensus without independently re-derived quotes")
    weight_sum = sum(SOURCE_WEIGHTS.get(entry["source_key"], 1.0) for entry in entries)
    if weight_sum <= 0:
        raise AuditError("invalid zero consensus weight")
    prob_a = sum(SOURCE_WEIGHTS.get(entry["source_key"], 1.0) * entry["prob_a"] for entry in entries) / weight_sum
    return {
        "prob_a": prob_a,
        "prob_b": 1 - prob_a,
        "sources": sorted({str(entry["source_key"]) for entry in entries}),
        "n_sources": len(entries),
        "spread_a": max(entry["prob_a"] for entry in entries) - min(entry["prob_a"] for entry in entries)
        if len(entries) > 1 else None,
        "weights": {key: SOURCE_WEIGHTS[key] for key in sorted({entry["source_key"] for entry in entries})
                    if key in SOURCE_WEIGHTS},
    }


def source_file_url(path_from_root: str) -> str:
    return f"{REPO}/blob/{SOURCE_BRANCH}/{urlquote(path_from_root)}"


def clean_flags(flags: Iterable[Any]) -> list[str]:
    return sorted({str(flag) for flag in flags if isinstance(flag, (str, int, float)) and str(flag)})


def make_quote_evidence(
    fixture: dict[str, Any], raw: dict[str, Any], orientation_swapped: bool, join_rule: str,
    start_diff_hours: float,
) -> dict[str, Any]:
    calc = rederive_two_way(raw)
    if calc is None:
        raise AuditError(f"{fixture.get('fixture_id')}: unusable raw odds for {fixture_quote_key(raw)}")
    probability_for_fixture_a = calc["prob_b"] if orientation_swapped else calc["prob_a"]
    return {
        "source_key": raw.get("source_key"),
        "source_name": raw.get("source_name") or raw.get("source_key"),
        "source_url": raw.get("public_url") or raw.get("api_url"),
        "api_url": raw.get("api_url"),
        "event_id": str(raw.get("event_id") or ""),
        "retrieved_utc": raw.get("retrieved_utc"),
        "start_utc_at_source": raw.get("start_utc"),
        "start_diff_hours": start_diff_hours,
        "names_at_source": [raw.get("team_a"), raw.get("team_b")],
        "raw_format": raw.get("raw_format"),
        "raw_a": raw.get("raw_a"),
        "raw_b": raw.get("raw_b"),
        "decimal_a": calc["decimal_a"],
        "decimal_b": calc["decimal_b"],
        "overround": calc["overround"],
        "prob_a_at_source": calc["prob_a"],
        "prob_b_at_source": calc["prob_b"],
        "prob_fixture_a": probability_for_fixture_a,
        "swapped": orientation_swapped,
        "join_rule": join_rule,
        "fixture_team_tokens": [list(team_tokens(fixture.get("team_a"))), list(team_tokens(fixture.get("team_b")))],
        "source_team_tokens": [list(team_tokens(raw.get("team_a"))), list(team_tokens(raw.get("team_b")))],
    }


def report_source_note() -> dict[str, str]:
    return {
        "fixture_discovery": "HotSpawn fixture/lobby records determine the listed open matches only.",
        "probabilities": "Each published probability is a weighted no-vig consensus of independently re-derived external bookmaker odds. HotSpawn crowd ownership is never read or used.",
        "unresolved": "A blank probability means no eligible external price passed the documented join checks; it is not a 50/50 estimate.",
    }


def rejected_summary(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Preserve source-rejected candidates without promoting them to evidence for a pick."""
    output: list[dict[str, Any]] = []
    for candidate in row.get("rejected_joins") or []:
        if not isinstance(candidate, dict):
            continue
        output.append({
            "source_key": candidate.get("source_key"),
            "source_name": candidate.get("source_name") or candidate.get("source_key"),
            "source_url": candidate.get("public_url"),
            "event_id": candidate.get("event_id"),
            "names_at_source": candidate.get("names_at_source"),
            "start_utc_at_source": candidate.get("start_utc_at_source"),
            "start_diff_hours": candidate.get("start_diff_h"),
            "reason": "Rejected by the source board's strict time/start verification; not used.",
        })
    return output


def default_valid_until(entries: list[dict[str, Any]], board_row: dict[str, Any]) -> str | None:
    candidates: list[datetime] = []
    for entry in entries:
        retrieved = parse_utc(entry.get("retrieved_utc"))
        if retrieved:
            candidates.append(retrieved + QUOTE_FRESHNESS)
    upstream = parse_utc(board_row.get("valid_until_utc"))
    if upstream:
        candidates.append(upstream)
    return iso_utc(min(candidates)) if candidates else None


def build_direct_market(
    fixture: dict[str, Any], raw_index: dict[tuple[str, str], list[dict[str, Any]]],
    collected_to: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Recheck every quote accepted by f7279a54 under this audit's own strict rule."""
    quote_entries: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for listed in fixture.get("quotes") or []:
        if not isinstance(listed, dict):
            raise AuditError(f"{fixture.get('fixture_id')}: non-object listed quote")
        key = fixture_quote_key(listed)
        raw_matches = raw_index.get(key, [])
        if len(raw_matches) != 1:
            raise AuditError(f"{fixture.get('fixture_id')}: expected exactly one raw quote for {key}, got {len(raw_matches)}")
        raw = raw_matches[0]
        source_key = str(raw.get("source_key") or "")
        if source_key in seen_sources:
            raise AuditError(f"{fixture.get('fixture_id')}: duplicate accepted source {source_key}")
        seen_sources.add(source_key)
        if raw.get("live"):
            raise AuditError(f"{fixture.get('fixture_id')}: live quote was accepted: {key}")
        if not quote_is_fresh(raw, collected_to):
            raise AuditError(f"{fixture.get('fixture_id')}: stale or future quote accepted: {key}")
        orientation = ordered_orientation(fixture, raw)
        if orientation is None:
            raise AuditError(f"{fixture.get('fixture_id')}: accepted quote is not an exact ordered-name match: {key}")
        time_ok, start_diff = source_time_is_strict(fixture, raw)
        if not time_ok or start_diff is None:
            raise AuditError(f"{fixture.get('fixture_id')}: accepted quote lacks verified matching start time: {key}")
        entry = make_quote_evidence(fixture, raw, orientation, "ordered-token exact match", start_diff)
        recorded_probability = listed.get("no_vig_prob_team_a")
        if isinstance(recorded_probability, (float, int)) and abs(entry["prob_fixture_a"] - float(recorded_probability)) > 0.00011:
            raise AuditError(
                f"{fixture.get('fixture_id')}: independently re-derived quote differs from upstream by more than rounding: {key}"
            )
        quote_entries.append(entry)
    if not quote_entries:
        raise AuditError(f"{fixture.get('fixture_id')}: market line has no independently verified quote")
    market = consensus([
        {"source_key": entry["source_key"], "prob_a": entry["prob_fixture_a"]} for entry in quote_entries
    ])
    upstream_market = fixture.get("market") or {}
    upstream_probability = upstream_market.get("prob_a")
    if isinstance(upstream_probability, (float, int)) and abs(market["prob_a"] - float(upstream_probability)) > 0.00011:
        raise AuditError(f"{fixture.get('fixture_id')}: consensus differs from upstream source board beyond rounding")
    return quote_entries, market


def build_reordered_market(
    fixture: dict[str, Any], raw_quotes: list[dict[str, Any]], collected_to: datetime
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    """Find conservative exact-token-order-only joins for an otherwise blank row.

    A source is ignored if it contains more than one equally-close candidate. This avoids choosing
    a duplicate or a similarly named event merely because it sorts first.
    """
    candidates: dict[str, list[tuple[float, dict[str, Any], bool]]] = defaultdict(list)
    for raw in raw_quotes:
        source_key = str(raw.get("source_key") or "")
        if source_key not in SOURCE_WEIGHTS or raw.get("live") or not quote_is_fresh(raw, collected_to):
            continue
        orientation = reordered_orientation(fixture, raw)
        if orientation is None:
            continue
        time_ok, start_diff = source_time_is_strict(fixture, raw)
        if not time_ok or start_diff is None or rederive_two_way(raw) is None:
            continue
        candidates[source_key].append((start_diff, raw, orientation))

    accepted: list[dict[str, Any]] = []
    for source_key, options in sorted(candidates.items()):
        options.sort(key=lambda item: (item[0], str(item[1].get("event_id") or "")))
        best_diff = options[0][0]
        closest = [option for option in options if abs(option[0] - best_diff) < 1e-12]
        if len(closest) != 1:
            # Ambiguous names are a hard stop for this source.
            continue
        start_diff, raw, orientation = closest[0]
        accepted.append(make_quote_evidence(
            fixture, raw, orientation, "exact full-token multiset reordering + exact opponent/start", start_diff
        ))
    if not accepted:
        return None
    market = consensus([
        {"source_key": entry["source_key"], "prob_a": entry["prob_fixture_a"]} for entry in accepted
    ])
    return accepted, market


def make_fixture_record(
    row: dict[str, Any], raw_index: dict[tuple[str, str], list[dict[str, Any]]], raw_quotes: list[dict[str, Any]],
    collected_to: datetime,
) -> dict[str, Any]:
    fixture_id = str(row.get("fixture_id") or "")
    if not fixture_id or not row.get("team_a") or not row.get("team_b") or not row.get("hotspawn_url"):
        raise AuditError("source board contains an incomplete open fixture")
    record: dict[str, Any] = {
        "fixture_id": fixture_id,
        "competition": row.get("competition"),
        "tier": row.get("tier"),
        "stage": row.get("stage"),
        "best_of": row.get("best_of"),
        "points": row.get("points"),
        "start_utc": row.get("start_utc"),
        "lock_utc": row.get("lock_utc"),
        "team_a": row.get("team_a"),
        "team_b": row.get("team_b"),
        "fixture_source": {
            "name": "HotSpawn match record (fixture discovery only)",
            "url": row.get("hotspawn_url"),
            "url_kind": row.get("hotspawn_url_kind"),
        },
        "flags": clean_flags(row.get("flags") or []),
        "rejected_candidates": rejected_summary(row),
        "quotes": [],
        "prob_a": None,
        "prob_b": None,
        "pick_team": None,
        "pick_side": None,
        "pick_probability": None,
        "valid_until_utc": None,
        "market": None,
        "basis": None,
        "status": "unresolved",
        "unresolved_reason": None,
    }

    upstream_line = row.get("line")
    if isinstance(upstream_line, dict):
        if upstream_line.get("basis") != "market":
            record["flags"].append("upstream_non_market_line_not_published")
            record["unresolved_reason"] = "The source board did not present an external-market-only line accepted by this audit."
            return record
        entries, market = build_direct_market(row, raw_index, collected_to)
        record.update({
            "quotes": entries,
            "market": market,
            "prob_a": market["prob_a"],
            "prob_b": market["prob_b"],
            "basis": "External market consensus — exact ordered team-token and start-time match",
            "status": "published",
            "valid_until_utc": default_valid_until(entries, row),
        })
        record["flags"].append("external_market_rederived_from_raw_snapshot")
    else:
        reordered = build_reordered_market(row, raw_quotes, collected_to)
        if reordered:
            entries, market = reordered
            record.update({
                "quotes": entries,
                "market": market,
                "prob_a": market["prob_a"],
                "prob_b": market["prob_b"],
                "basis": "External market consensus — exact token-order reordering verified with opponent and start time",
                "status": "published",
                "valid_until_utc": default_valid_until(entries, row),
            })
            # The upstream strict board correctly left this blank because it accepts ordered
            # names only. Keep that provenance without displaying the contradictory impression
            # that this independently rechecked row still has no line.
            record["flags"] = [flag for flag in record["flags"] if flag != "no_line_unverified"]
            record["flags"].extend([
                "upstream_blank_before_token_order_review",
                "token_order_reordered_join_documented",
                "external_market_rederived_from_raw_snapshot",
            ])
        else:
            record["flags"].append("no_external_market_line_verified")
            record["unresolved_reason"] = (
                "No captured external market passed the exact-name/start checks. Probabilities and pick are deliberately blank."
            )

    if record["status"] == "published":
        if not isinstance(record["prob_a"], float) or not isinstance(record["prob_b"], float):
            raise AuditError(f"{fixture_id}: published record has missing probability")
        if abs(record["prob_a"] + record["prob_b"] - 1) > 1e-9:
            raise AuditError(f"{fixture_id}: published probabilities do not total 100%")
        side = "a" if record["prob_a"] >= record["prob_b"] else "b"
        record["pick_side"] = side
        record["pick_team"] = record["team_a"] if side == "a" else record["team_b"]
        record["pick_probability"] = max(record["prob_a"], record["prob_b"])
        record["flags"] = clean_flags(record["flags"])
    return record


def build_report(board: dict[str, Any], snapshot: dict[str, Any], board_path: Path, snapshot_path: Path) -> dict[str, Any]:
    if board.get("session") != "f7279a54":
        raise AuditError("audit accepts only the declared f7279a54 source board")
    generated = parse_utc(board.get("generated_utc"))
    collected_from = parse_utc(snapshot.get("collected_from_utc"))
    collected_to = parse_utc(snapshot.get("collected_to_utc"))
    if generated is None or collected_from is None or collected_to is None or collected_from > collected_to:
        raise AuditError("source snapshot lacks a valid collection window")
    if abs((generated - collected_to).total_seconds()) > 1:
        raise AuditError("source board generation time does not match its raw snapshot endpoint")
    source_open = board.get("open")
    raw_quotes = snapshot.get("quotes")
    if not isinstance(source_open, list) or not isinstance(raw_quotes, list):
        raise AuditError("source board/snapshot has no fixture or quote list")
    if any(not isinstance(item, dict) for item in source_open + raw_quotes):
        raise AuditError("source board/snapshot contains malformed row objects")
    expected_open = (board.get("summary") or {}).get("open")
    if expected_open != len(source_open):
        raise AuditError("source board's open summary does not equal its fixture rows")

    raw_index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in raw_quotes:
        key = fixture_quote_key(raw)
        if key == ("", ""):
            continue
        raw_index[key].append(raw)

    fixtures = [make_fixture_record(row, raw_index, raw_quotes, collected_to) for row in source_open]
    fixtures.sort(key=lambda item: (str(item.get("lock_utc") or item.get("start_utc") or ""), item["fixture_id"]))
    ids = [fixture["fixture_id"] for fixture in fixtures]
    if len(ids) != len(set(ids)):
        raise AuditError("duplicate fixture ID in audit output")
    if len(fixtures) != len(source_open):
        raise AuditError("audit output did not preserve every source-board open fixture")

    published = [fixture for fixture in fixtures if fixture["status"] == "published"]
    unresolved = [fixture for fixture in fixtures if fixture["status"] != "published"]
    direct = [fixture for fixture in published if not any(
        flag == "token_order_reordered_join_documented" for flag in fixture["flags"]
    )]
    reordered = [fixture for fixture in published if fixture not in direct]
    if len(published) + len(unresolved) != len(fixtures):
        raise AuditError("coverage accounting failed")

    access = board.get("access") or {}
    source_status = {
        name: {
            "url": metadata.get("url"), "status": metadata.get("status"), "ok": metadata.get("ok"),
            "error": metadata.get("error"), "at_utc": metadata.get("at_utc"), "quotes": metadata.get("quotes"),
        }
        for name, metadata in access.items() if isinstance(metadata, dict)
    }
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "audit_generated_utc": iso_utc(generated),
        "input": {
            "source_session": "f7279a54",
            "board_path": str(board_path.relative_to(ROOT)),
            "snapshot_path": str(snapshot_path.relative_to(ROOT)),
            "board_sha256": sha256_file(board_path),
            "snapshot_sha256": sha256_file(snapshot_path),
            "source_board_generated_utc": iso_utc(generated),
            "collected_from_utc": iso_utc(collected_from),
            "collected_to_utc": iso_utc(collected_to),
            "source_policy": board.get("policy"),
        },
        "policy": {
            **report_source_note(),
            "standard_join": "Both full normalized token sequences (case/diacritics/punctuation and generic organization suffix only) plus a source start within five minutes must match.",
            "token_reorder_exception": "Only if both entire team-token multisets match exactly, opponent and verified source start match, and ordinary ordered matching failed. No aliases, prefixes, substrings, or fuzzy name matching are permitted.",
            "market_math": "For each two-way quote, implied probabilities are normalized by their sum to remove the overround. Consensus weights: Pinnacle 2; Bovada 1; Melbet 1.",
            "fallback_ladder": "For blank rows: the captured HLTV probe is recorded as blocked (HTTP 403); external markets were checked; no originated/VRS estimate is published because the retained VRS snapshot is flagged stale or unverified for these fixtures.",
        },
        "source_access": source_status,
        "summary": {
            "open_fixtures": len(fixtures),
            "published_external_market_picks": len(published),
            "published_direct_market_picks": len(direct),
            "published_exact_token_reorder_picks": len(reordered),
            "unresolved_blank": len(unresolved),
            "source_board_market_picks": (board.get("summary") or {}).get("market_based"),
            "source_board_unresolved": (board.get("summary") or {}).get("no_line"),
            "raw_quotes_examined": len(raw_quotes),
        },
        "fixtures": fixtures,
        "repository_review": {
            "board": source_file_url("data/f7279a54/board.json"),
            "raw_snapshot": source_file_url("data/f7279a54/snapshot.json"),
            "upstream_method": source_file_url("scripts/f7279a54/core.py"),
            "audit_builder": source_file_url("scripts/a666cd41/build_audit.py"),
            "audit_workflow": source_file_url(".github/workflows/a666cd41-audit.yml"),
        },
    }
    return report


# -------------------------------------------------------------------------------------- HTML

def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fmt_pct(value: Any) -> str:
    return f"{float(value) * 100:.1f}%" if isinstance(value, (int, float)) else "—"


def fmt_num(value: Any, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}" if isinstance(value, (int, float)) else "—"


def fmt_time(value: Any) -> str:
    if not value:
        return "—"
    parsed = parse_utc(value)
    if parsed is None:
        return esc(value)
    return parsed.strftime("%a %d %b · %H:%M UTC")


def external_link(url: Any, label: str) -> str:
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        return esc(label)
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label)} <span aria-hidden="true">↗</span></a>'


def local_link(url: str, label: str) -> str:
    return f'<a href="{esc(url)}">{esc(label)}</a>'


def nav(active: str) -> str:
    items = [
        ("index.html", "Summary"),
        ("picks.html", "Current picks"),
        ("unresolved.html", "Unresolved"),
        ("evidence.html", "Evidence"),
        ("method.html", "Method"),
        ("../../index.html", "Main site"),
    ]
    links = []
    for href, label in items:
        current = ' aria-current="page"' if href == active else ""
        links.append(f'<a href="{href}"{current}>{label}</a>')
    return "".join(links)


def source_summary_links(fixture: dict[str, Any], include_books: bool = True) -> str:
    links = [external_link(fixture["fixture_source"].get("url"), "HotSpawn fixture")]
    if include_books:
        for quote_data in fixture.get("quotes") or []:
            name = quote_data.get("source_name") or quote_data.get("source_key") or "market"
            links.append(external_link(quote_data.get("source_url"), str(name)))
    links.append(local_link(f"evidence.html#fixture-{fixture['fixture_id']}", "audit trail"))
    return '<span class="source-links">' + " · ".join(links) + "</span>"


def flag_pills(flags: list[str], limit: int | None = None) -> str:
    values = flags if limit is None else flags[:limit]
    pills = "".join(f'<span class="flag">{esc(flag.replace("_", " "))}</span>' for flag in values)
    extra = f' <span class="muted">+{len(flags) - len(values)} more</span>' if limit is not None and len(flags) > len(values) else ""
    return pills + extra if pills else '<span class="muted">None</span>'


def fixture_row(fixture: dict[str, Any], kind: str) -> str:
    searchable = " ".join(str(fixture.get(key) or "") for key in ("team_a", "team_b", "competition", "fixture_id", "tier")).casefold()
    status = fixture["status"]
    attrs = (
        f'data-row data-status="{esc(status)}" data-search="{esc(searchable)}" '
        f'data-valid-until="{esc(fixture.get("valid_until_utc") or "")}" '
        f'data-lock="{esc(fixture.get("lock_utc") or "")}"'
    )
    matchup = (
        f'<a class="fixture-title" href="evidence.html#fixture-{esc(fixture["fixture_id"])}">'
        f'{esc(fixture["team_a"])} <span aria-hidden="true">vs</span> {esc(fixture["team_b"])}</a>'
        f'<div class="sub">{esc(fixture.get("competition") or "Unknown competition")} · {esc(fixture.get("tier") or "—")} tier</div>'
    )
    timing = (
        f'<time datetime="{esc(fixture.get("start_utc") or "")}">{fmt_time(fixture.get("start_utc"))}</time>'
        f'<div class="sub">Locks {fmt_time(fixture.get("lock_utc"))}</div>'
    )
    if status == "published":
        probabilities = (
            f'<span class="probability" data-probability>{esc(fixture["team_a"])} <b>{fmt_pct(fixture["prob_a"])}</b></span><br>'
            f'<span class="probability" data-probability>{esc(fixture["team_b"])} <b>{fmt_pct(fixture["prob_b"])}</b></span>'
        )
        pick = (
            f'<span class="pick" data-pick><strong>{esc(fixture["pick_team"])} · {fmt_pct(fixture["pick_probability"])}</strong>'
            f'<br><span class="sub">{esc(fixture["basis"])}</span></span>'
        )
        valid = f'<time class="sub" datetime="{esc(fixture.get("valid_until_utc") or "")}">Valid through {fmt_time(fixture.get("valid_until_utc"))}</time>'
    else:
        probabilities = '<span class="blank" data-probability>Blank — unverified</span>'
        pick = f'<span class="blank" data-pick>No pick</span><br><span class="sub">{esc(fixture.get("unresolved_reason") or "Unverified")}</span>'
        valid = '<span class="sub">No current externally verified price</span>'
    return f"""<tr {attrs}>
  <td data-label="Match">{matchup}</td>
  <td data-label="Start / lock">{timing}</td>
  <td data-label="Win probabilities">{probabilities}</td>
  <td data-label="Pick / basis">{pick}</td>
  <td data-label="Sources">{source_summary_links(fixture, include_books=status == 'published')}<br>{valid}</td>
  <td data-label="Flags">{flag_pills(fixture.get('flags') or [], limit=2)}</td>
</tr>"""


def page(title: str, active: str, body: str, report: dict[str, Any]) -> str:
    observed = report["input"]["collected_to_utc"]
    # Renderers use readable triple-quoted fragments. Strip their framing newline so generated
    # HTML never contains whitespace-only lines (and remains clean under `git diff --check`).
    body = body.strip()
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Source-linked, mobile-friendly audit of every open HotSpawn CS2 Pick'em fixture.">
  <title>{esc(title)} · HotSpawn CS2 provenance audit</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
<a class="skip" href="#content">Skip to content</a>
<header>
  <div class="bar">
    <a class="brand" href="index.html">CS2 Pick'em <span>provenance audit</span></a>
    <nav aria-label="Audit navigation">{nav(active)}</nav>
  </div>
</header>
<main id="content" data-observed="{esc(observed)}">
{body}
  <footer>
    <p>Snapshot collected <time datetime="{esc(observed)}">{fmt_time(observed)}</time>. This is an evidence audit, not betting advice. External pages may change after capture.</p>
    <p>HotSpawn is used for match discovery only; its crowd-pick ownership is not read or used as a probability signal.</p>
  </footer>
</main>
<script src="app.js"></script>
</body>
</html>
"""


def controls(default: str = "all") -> str:
    return f"""<div class="controls" aria-label="Filter fixtures">
  <label for="filter">Find a team or event <input id="filter" type="search" autocomplete="off" placeholder="Search teams, event, or ID"></label>
  <div class="buttons" role="group" aria-label="Fixture status">
    <button type="button" data-filter="all" class="{'active' if default == 'all' else ''}">All</button>
    <button type="button" data-filter="published" class="{'active' if default == 'published' else ''}">Current picks</button>
    <button type="button" data-filter="unresolved" class="{'active' if default == 'unresolved' else ''}">Unresolved</button>
  </div>
  <p class="sub" id="filter-count" aria-live="polite"></p>
</div>"""


def render_index(report: dict[str, Any]) -> str:
    summary = report["summary"]
    published = [fixture for fixture in report["fixtures"] if fixture["status"] == "published"]
    unresolved = [fixture for fixture in report["fixtures"] if fixture["status"] != "published"]
    strongest = sorted(published, key=lambda item: (-float(item["pick_probability"]), item["start_utc"]))[:5]
    featured = "".join(
        f"""<li><a href="evidence.html#fixture-{esc(item['fixture_id'])}">{esc(item['team_a'])} vs {esc(item['team_b'])}</a>
        <strong>{esc(item['pick_team'])} {fmt_pct(item['pick_probability'])}</strong>
        <span>{esc(item['basis'])}</span></li>""" for item in strongest
    ) or "<li>No current externally verified picks.</li>"
    hltv = (report.get("source_access") or {}).get("hltv_probe") or {}
    hltv_note = "HLTV capture status was not recorded."
    if hltv:
        hltv_note = f"HLTV fallback probe: HTTP {esc(hltv.get('status'))} ({esc(hltv.get('error') or 'no error text')})."
    return f"""
<section class="hero">
  <p class="eyebrow">Every page-listed open fixture · source snapshot {esc(report['input']['source_board_generated_utc'])}</p>
  <h1>CS2 Pick'em evidence, without crowd ownership</h1>
  <p class="lede">A phone-first audit of all {summary['open_fixtures']} open HotSpawn lobby fixtures. {summary['published_external_market_picks']} have externally re-derived bookmaker probabilities; {summary['unresolved_blank']} remain deliberately blank because no source passed verification.</p>
  <div class="cta-row">
    <a class="button primary" href="picks.html">View {summary['published_external_market_picks']} current picks</a>
    <a class="button warning" href="unresolved.html">Review {summary['unresolved_blank']} unresolved</a>
    <a class="button" href="evidence.html">Open line-by-line evidence</a>
  </div>
</section>
<section class="metrics" aria-label="Coverage summary">
  <article><b>{summary['open_fixtures']}</b><span>open fixtures audited</span></article>
  <article><b>{summary['published_external_market_picks']}</b><span>external-market picks</span></article>
  <article><b>{summary['published_direct_market_picks']}</b><span>direct strict-name joins</span></article>
  <article><b>{summary['published_exact_token_reorder_picks']}</b><span>exact token-order joins</span></article>
  <article><b>{summary['unresolved_blank']}</b><span>blank &amp; flagged</span></article>
</section>
<section class="notice" id="freshness-notice">
  <h2>Read this before using a pick</h2>
  <p>Each probability is valid only through its shown expiry and match lock. Your browser hides expired probabilities and picks automatically; the audit trail remains visible. The update workflow rebuilds from the f7279a54 source board at a four-hour cadence, with a schedule fallback.</p>
</section>
<section class="split">
  <div>
    <h2>Highest snapshot probabilities</h2>
    <ol class="feature-list">{featured}</ol>
    <p><a href="picks.html">All updated picks and both-team probabilities →</a></p>
  </div>
  <div>
    <h2>Unresolved Picks &amp; Limitations</h2>
    <p>{len(unresolved)} fixtures have no published probability or pick. Blank is intentional: it means no qualifying external line, not an inferred coin flip.</p>
    <p>{hltv_note} The retained Valve VRS input is flagged stale/unverified for fallback use, so this audit does not manufacture model-only values.</p>
    <p><a href="unresolved.html">See every blank row, flag, and rejected candidate →</a></p>
  </div>
</section>
<section>
  <h2>What the sources mean</h2>
  <div class="method-grid">
    <article><h3>Fixture discovery</h3><p>Each row links to its official HotSpawn match record. That verifies the listing and start/lock context only.</p></article>
    <article><h3>Probability evidence</h3><p>Bookmaker two-way prices are re-derived to no-vig probabilities. Captured raw odds, source team names, timestamps, and calculations are shown line by line.</p></article>
    <article><h3>Conservative gaps</h3><p>Aliases, fuzzy names, approximate starts, in-play prices, stale data, and unverified VRS fallbacks do not produce a number.</p></article>
  </div>
  <p><a href="method.html">Full method, source statuses, and reproducibility details →</a></p>
</section>
"""


def render_picks(report: dict[str, Any]) -> str:
    fixtures = [fixture for fixture in report["fixtures"] if fixture["status"] == "published"]
    rows = "\n".join(fixture_row(fixture, "published") for fixture in fixtures)
    return f"""
<section>
  <p class="eyebrow">Externally priced rows only</p>
  <h1>Updated picks</h1>
  <p class="lede">{len(fixtures)} of {report['summary']['open_fixtures']} open fixtures have a source-verified external market. Both team probabilities, the deterministic higher-probability pick, source links, and basis are shown below.</p>
  <p class="notice compact">A green pick is not a recommendation. It is simply the higher side of the documented no-vig consensus. If a row expires or locks, browser-side protection replaces its probabilities with blanks.</p>
  {controls('published')}
  <div class="table-wrap"><table class="cards">
    <thead><tr><th>Match</th><th>Start / lock</th><th>Win probabilities</th><th>Pick / basis</th><th>Sources</th><th>Flags</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
</section>
<section class="notice">
  <h2>Coverage note</h2>
  <p>{report['summary']['published_direct_market_picks']} rows reproduce a direct exact-name market join from the source board. {report['summary']['published_exact_token_reorder_picks']} additional rows use only a complete, exact team-token reordering, plus exact opponent/start validation. See their individual audit trails for the raw line and token comparison.</p>
  <p><a href="unresolved.html">Open the remaining blank rows →</a></p>
</section>
"""


def render_unresolved(report: dict[str, Any]) -> str:
    fixtures = [fixture for fixture in report["fixtures"] if fixture["status"] != "published"]
    rows = "\n".join(fixture_row(fixture, "unresolved") for fixture in fixtures)
    return f"""
<section>
  <p class="eyebrow">No inference permitted</p>
  <h1>Unresolved Picks &amp; Limitations</h1>
  <p class="lede">{len(fixtures)} open fixtures have blank probabilities and no pick. These values are intentionally absent rather than substituted with crowd ownership, a name guess, or a stale model.</p>
  {controls('unresolved')}
  <div class="table-wrap"><table class="cards">
    <thead><tr><th>Match</th><th>Start / lock</th><th>Win probabilities</th><th>Pick / basis</th><th>Sources</th><th>Flags</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
</section>
<section class="notice">
  <h2>Fallback research ladder — result for this snapshot</h2>
  <ol>
    <li><strong>HLTV first:</strong> the captured <a href="https://www.hltv.org/matches" target="_blank" rel="noopener noreferrer">HLTV matches probe ↗</a> returned HTTP 403, recorded in the source-access log. It supplied no input.</li>
    <li><strong>External markets:</strong> eligible sportsbook lines were used only where both names and a verified start time passed. Name-similar candidates are retained as rejected evidence, not converted into a pick.</li>
    <li><strong>Originated line:</strong> none was published. The retained Valve VRS snapshot is explicitly flagged stale/unverified for these fallbacks; originating a number from it would violate the blank-until-confirmed rule.</li>
  </ol>
  <p>Each row's <a href="evidence.html">audit trail</a> preserves the fixture link, flags, and any rejected candidate recorded by the source board.</p>
</section>
"""


def raw_odds_line(entry: dict[str, Any]) -> str:
    names = entry.get("names_at_source") or ["?", "?"]
    first, second = (list(names) + ["?"])[:2]
    source = external_link(entry.get("source_url"), str(entry.get("source_name") or entry.get("source_key") or "market"))
    token_info = (
        f"fixture tokens {esc(' / '.join(' '.join(group) or '∅' for group in entry.get('fixture_team_tokens') or []))}; "
        f"source tokens {esc(' / '.join(' '.join(group) or '∅' for group in entry.get('source_team_tokens') or []))}"
    )
    raw_label = (
        f"{esc(first)} {esc(entry.get('raw_a'))} · {esc(second)} {esc(entry.get('raw_b'))} "
        f"({esc(entry.get('raw_format'))})"
    )
    return f"""<li class="quote">
  <div><strong>{source}</strong> <span class="code">{esc(entry.get('source_key'))}:{esc(entry.get('event_id'))}</span></div>
  <div>{raw_label}</div>
  <div class="sub">Source start {fmt_time(entry.get('start_utc_at_source'))}; retrieved {fmt_time(entry.get('retrieved_utc'))}; start difference {fmt_num(entry.get('start_diff_hours'), 3)}h.</div>
  <div class="math">Decimals {fmt_num(entry.get('decimal_a'))} / {fmt_num(entry.get('decimal_b'))} → implied-normalized {fmt_pct(entry.get('prob_a_at_source'))} / {fmt_pct(entry.get('prob_b_at_source'))}; overround {fmt_pct(entry.get('overround') - 1)}. Oriented fixture Team A probability: <strong>{fmt_pct(entry.get('prob_fixture_a'))}</strong>.</div>
  <div class="sub">Join rule: {esc(entry.get('join_rule'))}. {token_info}.</div>
</li>"""


def render_evidence(report: dict[str, Any]) -> str:
    articles: list[str] = []
    for fixture in report["fixtures"]:
        quotes = fixture.get("quotes") or []
        quote_block = "".join(raw_odds_line(entry) for entry in quotes)
        if not quote_block:
            quote_block = '<li class="blank">No eligible external quote. This row remains blank.</li>'
        rejected = fixture.get("rejected_candidates") or []
        rejected_block = ""
        if rejected:
            rejected_items = "".join(
                f"<li>{external_link(item.get('source_url'), str(item.get('source_name') or item.get('source_key') or 'source'))} "
                f"<span class=\"code\">{esc(item.get('event_id'))}</span>: {esc(' vs '.join(str(name) for name in (item.get('names_at_source') or [])))}; "
                f"source start {fmt_time(item.get('start_utc_at_source'))}; difference {esc(item.get('start_diff_hours'))}h. {esc(item.get('reason'))}</li>"
                for item in rejected
            )
            rejected_block = f'<details><summary>Rejected source candidates ({len(rejected)})</summary><ul>{rejected_items}</ul></details>'
        result = (
            f"<strong>Published:</strong> {esc(fixture['pick_team'])} {fmt_pct(fixture['pick_probability'])}; "
            f"{esc(fixture['team_a'])} {fmt_pct(fixture['prob_a'])} / {esc(fixture['team_b'])} {fmt_pct(fixture['prob_b'])}."
            if fixture["status"] == "published" else
            f"<strong class=\"blank\">Unresolved — probabilities and pick blank.</strong> {esc(fixture.get('unresolved_reason') or '')}"
        )
        articles.append(f"""<article class="evidence" id="fixture-{esc(fixture['fixture_id'])}">
  <header><p class="eyebrow">Fixture {esc(fixture['fixture_id'])} · {esc(fixture.get('tier') or '—')} tier</p>
  <h2>{esc(fixture['team_a'])} <span aria-hidden="true">vs</span> {esc(fixture['team_b'])}</h2>
  <p>{esc(fixture.get('competition') or 'Unknown competition')} · starts {fmt_time(fixture.get('start_utc'))} · {external_link(fixture['fixture_source'].get('url'), 'HotSpawn fixture record')}</p></header>
  <p class="outcome">{result}</p>
  <p><strong>Basis:</strong> {esc(fixture.get('basis') or 'No verified external market line')}</p>
  <h3>Captured market inputs</h3><ol class="quotes">{quote_block}</ol>
  <p><strong>Flags:</strong> {flag_pills(fixture.get('flags') or [])}</p>
{rejected_block}
  <p class="back"><a href="#content">Back to evidence index</a> · <a href="{('picks.html' if fixture['status'] == 'published' else 'unresolved.html')}">Back to {'picks' if fixture['status'] == 'published' else 'unresolved'}</a></p>
</article>""")
    return f"""
<section>
  <p class="eyebrow">Repository-reviewable source ledger</p>
  <h1>Line-by-line evidence</h1>
  <p class="lede">Every listed fixture appears below. Published values show the captured raw odds, conversion, no-vig calculation, matching rule, external source link, and fixture link. A blank row documents why no value was published.</p>
  <p class="notice compact">Raw source snapshot: {external_link(report['repository_review']['raw_snapshot'], 'data/f7279a54/snapshot.json')} · Source board: {external_link(report['repository_review']['board'], 'data/f7279a54/board.json')} · This audit report: <a href="../../data/a666cd41/report.json">data/a666cd41/report.json</a>.</p>
</section>
<section class="evidence-index">
  {''.join(articles)}
</section>
"""


def access_rows(report: dict[str, Any]) -> str:
    rows = []
    for name, info in sorted((report.get("source_access") or {}).items()):
        status = info.get("status")
        outcome = "available" if info.get("ok") else "failed / unavailable"
        rows.append(
            f"<tr><td>{esc(name)}</td><td>{external_link(info.get('url'), 'recorded endpoint')}</td>"
            f"<td>{esc(status)}</td><td>{esc(outcome)}</td><td>{esc(info.get('error') or '—')}</td>"
            f"<td>{fmt_time(info.get('at_utc'))}</td></tr>"
        )
    return "".join(rows)


def render_method(report: dict[str, Any]) -> str:
    return f"""
<section>
  <p class="eyebrow">Reproducible policy</p>
  <h1>Method &amp; provenance</h1>
  <p class="lede">This section audits, rather than replaces, the f7279a54 strict board. It publishes an external-market estimate only after independently recomputing it from the preserved raw snapshot.</p>
</section>
<section class="method-grid">
  <article><h2>1. Discover fixtures</h2><p>Use page-listed open HotSpawn CS2 fixtures from the board. HotSpawn links are retained per row. No crowd ownership or HotSpawn pick percentage is read, stored, or used.</p></article>
  <article><h2>2. Re-derive odds</h2><p>Raw two-way bookmaker prices are converted to decimal odds when needed. Each implied probability is divided by the two implied probabilities' sum, removing the quoted overround.</p></article>
  <article><h2>3. Match conservatively</h2><p>Both teams and a verified start must match. Normalization is limited to case, diacritics, punctuation, and generic organization suffixes. No fuzzy or substring matching is allowed.</p></article>
  <article><h2>4. Exact reorder exception</h2><p>When only full team-token order differs (for example, “Apogee Betclic” / “Betclic Apogee”), both teams' complete token multisets, opponent, and source start must match. Such rows are visibly flagged.</p></article>
  <article><h2>5. Consensus and pick</h2><p>Source no-vig probabilities are weighted Pinnacle 2, Bovada 1, Melbet 1. The displayed pick is the higher resulting probability; it is a deterministic label, not advice.</p></article>
  <article><h2>6. Stop on uncertainty</h2><p>In-play, approximate-time, stale, ambiguous, alias-only, or unverified data cannot create a probability. The row is blank and linked into the unresolved review.</p></article>
</section>
<section>
  <h2>Fallback ladder &amp; limitations</h2>
  <ol>
    <li>Try HLTV as a match/research check. For this input it was blocked; it is recorded below, not treated as a source.</li>
    <li>Use externally captured sportsbook/exchange odds only when exact join rules pass.</li>
    <li>Do not originate a VRS/model-only line here: the retained VRS snapshot is flagged stale or unverified for every current fallback context. Blank is safer and required by the audit policy.</li>
  </ol>
</section>
<section>
  <h2>Captured source access</h2>
  <p>The following is a status log from the raw snapshot collection window, not a claim that a public page still displays the same price now.</p>
  <div class="table-wrap"><table><thead><tr><th>Source</th><th>Recorded endpoint</th><th>HTTP</th><th>Result</th><th>Error</th><th>Observed</th></tr></thead><tbody>{access_rows(report)}</tbody></table></div>
</section>
<section>
  <h2>Repository review &amp; refresh</h2>
  <ul>
    <li>{external_link(report['repository_review']['board'], 'Source board JSON')} and {external_link(report['repository_review']['raw_snapshot'], 'raw snapshot JSON')} are preserved inputs.</li>
    <li>{external_link(report['repository_review']['upstream_method'], 'Upstream strict join method')} and {external_link(report['repository_review']['audit_builder'], 'this independent audit builder')} are reviewable source code.</li>
    <li>{external_link(report['repository_review']['audit_workflow'], 'Audit refresh workflow')} rebuilds on a four-hour schedule and can be manually dispatched. It writes only this audit’s directory/data scope.</li>
    <li>{external_link(source_file_url('data/a666cd41/external-observations.json'), 'Supplemental GitHub/Valve metadata observation')} records the independent official GitHub API metadata check made with this audit; it is explicitly not substituted for raw odds evidence.</li>
    <li>Input SHA-256: board <code>{esc(report['input']['board_sha256'])}</code>; snapshot <code>{esc(report['input']['snapshot_sha256'])}</code>.</li>
  </ul>
</section>
"""


CSS = r""":root{--bg:#08111d;--panel:#101f31;--panel2:#142841;--line:#29435e;--text:#edf6ff;--muted:#aac0d5;--brand:#6ee7b7;--link:#91caff;--warn:#ffcd70;--bad:#ffc0bf;--focus:#f8e16c}*{box-sizing:border-box}html{color-scheme:dark}body{margin:0;background:linear-gradient(135deg,#08111d,#0b1726 58%,#0e1b2e);color:var(--text);font:16px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;min-height:100vh}a{color:var(--link);text-underline-offset:3px}a:hover{color:#c1e2ff}.skip{position:absolute;left:-9999px;top:8px;background:#fff;color:#000;padding:9px;z-index:10}.skip:focus{left:8px}a:focus-visible,button:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid var(--focus);outline-offset:3px}.bar{max-width:1240px;margin:auto;padding:11px 18px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}.bar:before{content:"";position:absolute;inset:0 0 auto;height:1px;background:var(--line)}header{position:sticky;top:0;z-index:5;background:rgba(8,17,29,.96);backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}.brand{color:#fff;text-decoration:none;font-weight:800;letter-spacing:.01em;margin-right:auto}.brand span{display:block;color:var(--brand);font-size:12px;font-weight:650;text-transform:uppercase;letter-spacing:.09em}nav{display:flex;flex-wrap:wrap;gap:5px}nav a{padding:7px 10px;min-height:38px;border-radius:8px;text-decoration:none;color:var(--text);font-size:14px}nav a[aria-current=page]{background:var(--brand);color:#062218;font-weight:800}main{max-width:1240px;margin:auto;padding:24px 18px 48px}.hero{max-width:880px;padding:10px 0 22px}.eyebrow{margin:0 0 4px;color:var(--brand);font-weight:750;font-size:12px;letter-spacing:.09em;text-transform:uppercase}.lede{max-width:920px;color:var(--muted);font-size:18px}h1{font-size:clamp(29px,5vw,48px);line-height:1.08;margin:5px 0 12px;letter-spacing:-.035em}h2{font-size:clamp(20px,3vw,28px);line-height:1.18;margin:30px 0 8px}h3{font-size:17px;margin:0 0 6px}.cta-row{display:flex;flex-wrap:wrap;gap:9px;margin:20px 0 0}.button{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:10px 14px;border:1px solid var(--line);border-radius:9px;background:var(--panel);color:#fff;font-weight:750;text-decoration:none}.button.primary{background:var(--brand);border-color:var(--brand);color:#062218}.button.warning{background:#4f3612;border-color:#9c6c25;color:#ffe7b5}.metrics{display:grid;grid-template-columns:repeat(5,minmax(130px,1fr));gap:9px;margin:5px 0 20px}.metrics article,.method-grid article{border:1px solid var(--line);border-radius:12px;padding:14px;background:linear-gradient(145deg,var(--panel),#0d1a2a)}.metrics b{display:block;font-size:30px;line-height:1.1;color:var(--brand);font-variant-numeric:tabular-nums}.metrics span{display:block;color:var(--muted);font-size:13px;margin-top:4px}.notice{border:1px solid #44658a;border-left:4px solid var(--link);border-radius:10px;background:#0d1d30;padding:12px 15px;margin:20px 0}.notice.compact{font-size:14px;margin:12px 0}.notice h2{margin:0 0 4px;font-size:18px}.split,.method-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.split>div{border-top:1px solid var(--line);padding-top:2px}.feature-list{padding:0;margin:10px 0;list-style:none}.feature-list li{display:grid;grid-template-columns:1fr auto;gap:3px 12px;padding:11px 0;border-bottom:1px solid var(--line)}.feature-list strong{color:var(--brand);white-space:nowrap}.feature-list span{grid-column:1/-1;color:var(--muted);font-size:13px}.method-grid{grid-template-columns:repeat(3,minmax(0,1fr));margin:10px 0}.method-grid p{margin:0;color:var(--muted);font-size:14px}.controls{display:flex;align-items:end;gap:12px;flex-wrap:wrap;margin:20px 0 10px;padding:10px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.controls label{display:flex;align-items:center;gap:8px;flex:1 1 290px;font-weight:700;font-size:14px}.controls input{width:100%;min-height:43px;padding:8px 10px;border-radius:8px;border:1px solid var(--line);background:#081422;color:var(--text);font:inherit}.buttons{display:flex;gap:5px;flex-wrap:wrap}.buttons button{cursor:pointer;min-height:41px;padding:8px 11px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--text);font:inherit;font-weight:700}.buttons button.active{color:#062218;background:var(--brand);border-color:var(--brand)}#filter-count{width:100%;margin:0}.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel)}table{width:100%;border-collapse:collapse;min-width:990px}th,td{padding:12px 11px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}th{color:var(--muted);background:#0b1828;font-size:12px;letter-spacing:.065em;text-transform:uppercase;white-space:nowrap}tbody tr:last-child td{border-bottom:0}tbody tr:hover{background:#162a42}.fixture-title{font-weight:800;color:#fff;text-decoration:none}.sub{display:block;margin-top:3px;color:var(--muted);font-size:12px;line-height:1.42}.probability b{color:#fff;font-variant-numeric:tabular-nums}.pick strong{color:var(--brand);font-size:16px}.blank{color:var(--warn);font-weight:750}.flag{display:inline-block;margin:0 3px 4px 0;padding:2px 6px;border:1px solid #895f27;border-radius:999px;background:#38260f;color:#ffe0a5;font-size:11px;line-height:1.35}.source-links{font-size:13px}.source-links a{white-space:nowrap}.muted{color:var(--muted)}.code,code{overflow-wrap:anywhere;padding:2px 5px;border-radius:4px;background:#07121e;color:#d2e6f6;font:12px ui-monospace,SFMono-Regular,Menlo,monospace}.evidence{scroll-margin-top:85px;margin:25px 0;padding:18px;border:1px solid var(--line);border-radius:12px;background:linear-gradient(145deg,var(--panel),#0e1a2a)}.evidence header{position:static;background:none;border:0;backdrop-filter:none}.evidence h2{font-size:24px;margin:4px 0}.evidence h3{margin:18px 0 6px}.evidence .outcome{padding:10px 12px;border-radius:8px;background:#0a1726}.quotes{padding-left:22px}.quote{margin:8px 0;padding:10px;border-left:3px solid var(--brand);border-radius:0 8px 8px 0;background:#0b1828}.math{margin-top:5px;color:#d3e6f6;font-variant-numeric:tabular-nums}.back{font-size:13px}.evidence details{padding:9px 0;color:var(--muted)}.evidence details li{margin:5px 0}footer{margin-top:42px;padding-top:15px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}footer p{margin:5px 0}@media(max-width:920px){.metrics{grid-template-columns:repeat(3,minmax(120px,1fr))}.method-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:720px){body{font-size:15px}.bar{padding:9px 12px;gap:8px}.brand{width:100%}nav{width:100%;overflow-x:auto;flex-wrap:nowrap;padding-bottom:2px}nav a{white-space:nowrap;padding:7px 9px;font-size:13px}main{padding:18px 12px 36px}.lede{font-size:16px}.metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.metrics article{padding:10px}.metrics b{font-size:25px}.split,.method-grid{grid-template-columns:1fr}.cta-row .button{width:100%}.controls{align-items:stretch}.controls label{display:block}.controls input{margin-top:5px}.table-wrap{overflow:visible;border:0;background:none}.cards{min-width:0;background:none}.cards thead{display:none}.cards,.cards tbody,.cards tr,.cards td{display:block;width:100%}.cards tr{margin:0 0 10px;padding:4px 0;border:1px solid var(--line);border-radius:11px;background:var(--panel)}.cards td{padding:7px 10px;border:0}.cards td:before{content:attr(data-label);display:block;margin-bottom:2px;color:var(--muted);font-size:10px;font-weight:800;letter-spacing:.07em;text-transform:uppercase}.cards td[data-label=Match]:before{display:none}.feature-list li{grid-template-columns:1fr}.feature-list strong{white-space:normal}.evidence{padding:13px}.quote{margin-left:-3px;padding:8px}.source-links a{display:inline-block;margin:2px 0}}"""


JS = r"""(function(){
  'use strict';
  var rows = Array.prototype.slice.call(document.querySelectorAll('[data-row]'));
  var filter = document.getElementById('filter');
  var buttons = Array.prototype.slice.call(document.querySelectorAll('[data-filter]'));
  var count = document.getElementById('filter-count');
  var mode = document.querySelector('[data-filter].active'); mode = mode ? mode.dataset.filter : 'all';
  function expired(row){
    if(row.dataset.status !== 'published') return false;
    var now = Date.now(), valid = Date.parse(row.dataset.validUntil || ''), lock = Date.parse(row.dataset.lock || '');
    return (isFinite(valid) && now >= valid) || (isFinite(lock) && now >= lock);
  }
  function protect(row){
    if(!expired(row) || row.dataset.expired) return;
    row.dataset.expired = 'true';
    Array.prototype.forEach.call(row.querySelectorAll('[data-probability]'), function(el){el.textContent='— expired'; el.classList.add('blank');});
    Array.prototype.forEach.call(row.querySelectorAll('[data-pick]'), function(el){el.textContent='Expired / locked — awaiting source refresh'; el.classList.add('blank');});
    var notice = document.getElementById('freshness-notice');
    if(notice){notice.hidden=false; notice.innerHTML='<h2>Snapshot values have expired</h2><p>Expired or locked probabilities and picks are hidden in this browser. The evidence trail remains for review; reload after the next automated refresh.</p>';}
  }
  function apply(){
    var needle = (filter && filter.value || '').toLowerCase(), visible = 0;
    rows.forEach(function(row){
      protect(row);
      var actual = row.dataset.status === 'published' && !row.dataset.expired ? 'published' : (row.dataset.status === 'published' ? 'expired' : 'unresolved');
      var match = (!needle || (row.dataset.search || '').indexOf(needle) !== -1) && (mode === 'all' || actual === mode);
      row.hidden = !match; if(match) visible++;
    });
    if(count) count.textContent = visible + ' fixture' + (visible === 1 ? '' : 's') + ' shown';
  }
  if(filter) filter.addEventListener('input', apply);
  buttons.forEach(function(button){button.addEventListener('click', function(){mode=button.dataset.filter;buttons.forEach(function(b){b.classList.toggle('active',b===button);});apply();});});
  apply(); setInterval(apply, 60000);
}());"""


def render_csv(report: dict[str, Any], path: Path) -> None:
    fields = [
        "fixture_id", "start_utc", "lock_utc", "competition", "tier", "team_a", "team_b", "status",
        "prob_a", "prob_b", "pick_team", "pick_probability", "basis", "valid_until_utc", "fixture_url", "flags",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for fixture in report["fixtures"]:
            writer.writerow({
                "fixture_id": fixture["fixture_id"], "start_utc": fixture.get("start_utc"), "lock_utc": fixture.get("lock_utc"),
                "competition": fixture.get("competition"), "tier": fixture.get("tier"), "team_a": fixture.get("team_a"),
                "team_b": fixture.get("team_b"), "status": fixture.get("status"), "prob_a": fixture.get("prob_a"),
                "prob_b": fixture.get("prob_b"), "pick_team": fixture.get("pick_team"),
                "pick_probability": fixture.get("pick_probability"), "basis": fixture.get("basis"),
                "valid_until_utc": fixture.get("valid_until_utc"), "fixture_url": (fixture.get("fixture_source") or {}).get("url"),
                "flags": ";".join(fixture.get("flags") or []),
            })


def render_site(report: dict[str, Any], out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "style.css").write_text(CSS + "\n", encoding="utf-8")
    (out_dir / "app.js").write_text(JS + "\n", encoding="utf-8")
    pages = {
        "index.html": ("Summary", "index.html", render_index(report)),
        "picks.html": ("Updated picks", "picks.html", render_picks(report)),
        "unresolved.html": ("Unresolved picks & limitations", "unresolved.html", render_unresolved(report)),
        "evidence.html": ("Line-by-line evidence", "evidence.html", render_evidence(report)),
        "method.html": ("Method & provenance", "method.html", render_method(report)),
    }
    for filename, (title, active, body) in pages.items():
        (out_dir / filename).write_text(page(title, active, body, report), encoding="utf-8")
    (out_dir / "README.md").write_text(
        "# a666cd41 provenance audit\n\n"
        "Generated by `scripts/a666cd41/build_audit.py` from `data/f7279a54/board.json` and "
        "`data/f7279a54/snapshot.json`. Do not hand-edit generated HTML; rebuild it.\n\n"
        "The audit is a conservative source-coverage review: it re-derives raw two-way odds and leaves "
        "any fixture without a documented external line blank.\n",
        encoding="utf-8",
    )


def previous_is_too_recent(report_path: Path, source_generated: str, min_hours: float) -> bool:
    if min_hours <= 0 or not report_path.is_file():
        return False
    try:
        previous = load_json(report_path)
    except AuditError:
        return False
    if previous.get("generator_version") != GENERATOR_VERSION:
        return False
    prior = parse_utc((previous.get("input") or {}).get("source_board_generated_utc"))
    incoming = parse_utc(source_generated)
    return prior is not None and incoming is not None and timedelta(0) <= incoming - prior < timedelta(hours=min_hours)


def validate_max_age(source_generated: str, hours: float | None) -> None:
    if hours is None:
        return
    generated = parse_utc(source_generated)
    if generated is None:
        raise AuditError("cannot freshness-check an invalid source timestamp")
    age = datetime.now(timezone.utc) - generated
    if age < -timedelta(minutes=5) or age > timedelta(hours=hours):
        raise AuditError(f"source board is outside the allowed freshness window ({age.total_seconds() / 3600:.2f} hours; max {hours})")


def run(args: argparse.Namespace) -> int:
    board_path = Path(args.source_board).resolve()
    snapshot_path = Path(args.snapshot).resolve()
    report_path = Path(args.report).resolve()
    site_dir = Path(args.site_dir).resolve()
    board = load_json(board_path)
    if not args.force and previous_is_too_recent(report_path, str(board.get("generated_utc") or ""), args.min_refresh_hours):
        print("SKIP: source board is newer than previous audit by less than the configured cadence")
        return 0
    validate_max_age(str(board.get("generated_utc") or ""), args.max_input_age_hours)
    snapshot = load_json(snapshot_path)
    report = build_report(board, snapshot, board_path, snapshot_path)
    write_json(report_path, report)
    render_csv(report, report_path.parent / "coverage.csv")
    render_site(report, site_dir)
    print(
        "PASS: built a666cd41 audit: "
        f"{report['summary']['open_fixtures']} fixtures, "
        f"{report['summary']['published_external_market_picks']} published, "
        f"{report['summary']['unresolved_blank']} blank"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-board", default=str(DEFAULT_BOARD))
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--site-dir", default=str(DEFAULT_SITE))
    parser.add_argument("--force", action="store_true", help="rebuild even if the latest source input is inside the cadence window")
    parser.add_argument("--min-refresh-hours", type=float, default=0, help="skip same-policy rebuilds closer than this source-input interval")
    parser.add_argument("--max-input-age-hours", type=float, default=None, help="refuse to publish a stale source board")
    args = parser.parse_args()
    try:
        return run(args)
    except AuditError as exc:
        print(f"FAIL: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
