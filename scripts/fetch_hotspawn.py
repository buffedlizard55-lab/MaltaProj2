#!/usr/bin/env python3
"""Collect the exact CS2 fixture inventory embedded by the public HotSpawn lobby.

HotSpawn's Angular server-rendered page stores HTTP responses in ``script#ng-state``.
The response whose URL ends in ``/api/v1/fixtures`` is the fixture inventory used by
that lobby render; a separate response contains HotSpawn-published match permalinks.
This collector reads those public responses without signing in or calling an admin
endpoint.

Fail-closed rules:
* a missing, malformed, duplicate, or ambiguous embedded fixture response returns 1;
* the previous committed inventory is not overwritten on failure;
* only source fields are copied (missing values stay ``null`` and are flagged);
* HotSpawn crowd-pick percentages are deliberately not copied;
* a match permalink is used only when it was present in the page state and has the
  expected official host/path/id. Otherwise the official lobby is the fallback and
  the row is flagged.

Outputs:
* ``data/hotspawn_matches.json`` — exact embedded fixture rows, normalized;
* ``evidence/hotspawn_probe.json`` — response metadata, counters, field names,
  listing ids, permalink coverage, and validation findings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

LOBBY = "https://play.hotspawn.com/lobby"
API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1"
UA = "MaltaProj2-source-audit/2.0 (+https://github.com/buffedlizard55-lab/MaltaProj2)"
ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TEXT_FIELDS = ("participants0_name", "participants1_name", "competition_name", "sport_alias")


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ms_to_iso(value):
    """Convert source epoch milliseconds to UTC; invalid/missing fields remain blank."""
    if value in (None, "", "0") or isinstance(value, bool):
        return None
    try:
        return iso(datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc))
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def fetch_page(url: str = LOBBY, timeout: int = 90):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Encoding": "identity",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read(5_000_001)
            if len(body) > 5_000_000:
                raise ValueError("lobby response exceeded the 5 MB safety limit")
            headers = {key: response.headers.get(key) for key in ("Date", "Age", "ETag", "Last-Modified")}
            return response.status, body.decode("utf-8", "replace"), headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(2000).decode("utf-8", "replace"), {
            key: exc.headers.get(key) for key in ("Date", "Age", "ETag", "Last-Modified")
        }


def published_permalink(value, fixture_id: str):
    """Accept only a permalink literally published in state for this fixture id."""
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != "www.hotspawn.com":
        return None
    if not parsed.path.startswith("/matches/") or not parsed.path.rstrip("/").endswith("-" + fixture_id):
        return None
    return value


def parse_lobby(page_html: str) -> dict:
    """Parse one public lobby response. No network calls and no inferred fixture values."""
    soup = BeautifulSoup(page_html, "html.parser")
    state_node = soup.select_one("script#ng-state")
    raw_state = state_node.string if state_node is not None else None
    if not raw_state:
        raise ValueError("public Angular transfer-state is missing")
    try:
        state = json.loads(raw_state)
    except json.JSONDecodeError as exc:
        raise ValueError(f"public Angular transfer-state is invalid JSON: {exc}") from exc
    if not isinstance(state, dict):
        raise ValueError("public Angular transfer-state is not an object")

    fixture_responses = []
    permalink_maps = []
    for entry in state.values():
        if not isinstance(entry, dict):
            continue
        url, body = str(entry.get("u") or ""), entry.get("b")
        if url.rstrip("/").endswith("/api/v1/fixtures") and isinstance(body, list):
            fixture_responses.append({"url": url, "body": body})
        if isinstance(body, dict) and isinstance(body.get("permalinks"), dict):
            permalink_maps.append(body["permalinks"])
    if len(fixture_responses) != 1:
        raise ValueError(f"expected exactly one embedded fixture response, found {len(fixture_responses)}")
    if len(permalink_maps) > 1:
        raise ValueError(f"ambiguous embedded permalink responses: {len(permalink_maps)}")

    fixtures = fixture_responses[0]["body"]
    if not fixtures:
        raise ValueError("embedded fixture response is empty")
    permalinks = permalink_maps[0] if permalink_maps else {}
    seen = set()
    normalized = []
    for source in fixtures:
        if not isinstance(source, dict):
            raise ValueError("embedded fixture response contains a non-object row")
        fixture_id = str(source.get("id") or "")
        if not fixture_id or fixture_id in seen:
            raise ValueError("embedded fixture id is missing or duplicated")
        seen.add(fixture_id)
        missing = [key for key in REQUIRED_TEXT_FIELDS
                   if not isinstance(source.get(key), str) or not source[key].strip()]
        start = ms_to_iso(source.get("scheduled_start_time"))
        lock = ms_to_iso(source.get("lock_time"))
        if start is None:
            missing.append("scheduled_start_time")
        if lock is None:
            missing.append("lock_time")
        permalink = published_permalink(permalinks.get(fixture_id), fixture_id)
        flags = [f"source_field_missing:{key}" for key in missing]
        if permalink is None:
            flags.append("official_match_permalink_unavailable")
        competition_id = source.get("competition_id")
        normalized.append({
            "fixture_id": fixture_id,
            "competition_id": str(competition_id) if competition_id is not None else None,
            "competition_name": source.get("competition_name"),
            "sport": source.get("sport_alias"),
            "sport_name": source.get("sport_name"),
            "status": source.get("status"),
            "tier": source.get("tier") or None,
            "stage": source.get("stage"),
            "best_of": source.get("best_of"),
            "series_format": source.get("series_format"),
            "scheduled_start_time": start,
            "lock_time": lock,
            "lock_offset_sec": source.get("lock_offset_sec"),
            "offered_points": source.get("offered_points"),
            "base_points": source.get("base_points"),
            "total_picks": source.get("total_picks"),
            "team_a_id": str(source.get("participants0_id")) if source.get("participants0_id") is not None else None,
            "team_a": source.get("participants0_name"),
            "team_b_id": str(source.get("participants1_id")) if source.get("participants1_id") is not None else None,
            "team_b": source.get("participants1_name"),
            "source_flags": sorted(set(flags)),
            "source": {
                "page": LOBBY,
                "api": fixture_responses[0]["url"],
                "published_match_url": permalink,
                "published_match_url_verified": permalink is not None,
            },
        })

    normalized.sort(key=lambda row: (row.get("scheduled_start_time") or "", row["fixture_id"]))
    rendered_links = sorted({a.get("href") for a in soup.select('a[href*="hotspawn.com/matches/"]') if a.get("href")})
    text = soup.get_text(" ", strip=True)

    def count(pattern):
        match = re.search(pattern, text, re.I)
        return int(match.group(1).replace(",", "")) if match else None

    counters = {
        "matches_this_week": count(r"(\d[\d,]*)\s*matches this week"),
        "all_tiers": count(r"All tiers\s*\((\d[\d,]*)\)"),
        "tier_s": count(r"(?<![A-Za-z])S\s*\((\d[\d,]*)\)"),
        "tier_b": count(r"(?<![A-Za-z])B\s*\((\d[\d,]*)\)"),
        "tier_c": count(r"(?<![A-Za-z])C\s*\((\d[\d,]*)\)"),
    }
    return {
        "fixtures": normalized,
        "fixture_response_url": fixture_responses[0]["url"],
        "fixture_fields": sorted({key for row in fixtures for key in row}),
        "permalink_map_found": bool(permalink_maps),
        "published_permalink_count": sum(1 for row in normalized if row["source"]["published_match_url"]),
        "rendered_match_link_count": len(rendered_links),
        "counters": counters,
    }


def observed_time(retrieved_at: datetime, headers: dict) -> tuple[datetime, int | None]:
    """Account for a standard HTTP Age header; missing/invalid Age is not invented."""
    raw_age = headers.get("Age")
    try:
        age = int(raw_age) if raw_age is not None else None
        if age is not None and age < 0:
            age = None
    except (TypeError, ValueError):
        age = None
    return (retrieved_at - timedelta(seconds=age) if age is not None else retrieved_at), age


def build_documents(page_html: str, retrieved_at: datetime, headers: dict):
    parsed = parse_lobby(page_html)
    source_time, age = observed_time(retrieved_at, headers)
    fixtures = parsed["fixtures"]
    document = {
        "generated_at_utc": iso(retrieved_at),
        "source_observed_at_utc": iso(source_time),
        "source_cache_age_seconds": age,
        "source_page": LOBBY,
        "source_endpoint": parsed["fixture_response_url"],
        "scope": "Exact fixture response embedded in the public HotSpawn lobby render; CS2 is the observed lobby game in this response.",
        "note": "HotSpawn is fixture discovery only. Crowd-picked percentages are deliberately omitted and never enter a probability.",
        "match_count": len(fixtures),
        "matches": fixtures,
    }
    probe = {
        "generated_at_utc": iso(retrieved_at),
        "source_observed_at_utc": iso(source_time),
        "source_cache_age_seconds": age,
        "source_page": LOBBY,
        "source_endpoint": parsed["fixture_response_url"],
        "response_headers": headers,
        "response_sha256": hashlib.sha256(page_html.encode("utf-8")).hexdigest(),
        "fixture_count": len(fixtures),
        "fixture_ids": [row["fixture_id"] for row in fixtures],
        "fixture_fields": parsed["fixture_fields"],
        "sport_counts": {sport: sum(1 for row in fixtures if row.get("sport") == sport)
                         for sport in sorted({row.get("sport") for row in fixtures}, key=lambda x: str(x))},
        "status_counts": {status: sum(1 for row in fixtures if row.get("status") == status)
                          for status in sorted({row.get("status") for row in fixtures}, key=lambda x: str(x))},
        "counters": parsed["counters"],
        "permalink_map_found": parsed["permalink_map_found"],
        "published_permalink_count": parsed["published_permalink_count"],
        "rendered_match_link_count": parsed["rendered_match_link_count"],
        "validation": {
            "fixture_ids_unique": len({row["fixture_id"] for row in fixtures}) == len(fixtures),
            "normalized_crowd_percentage_fields_present": False,
            "source_rows_with_flags": sum(1 for row in fixtures if row["source_flags"]),
        },
    }
    return document, probe


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", help="Parse a saved lobby HTML fixture instead of making a request")
    parser.add_argument("--retrieved-at", help="UTC ISO timestamp for --fixture evidence")
    args = parser.parse_args()
    retrieved_at = now_utc()
    headers = {"Date": None, "Age": None, "ETag": None, "Last-Modified": None}
    probe_path = ROOT / "evidence" / "hotspawn_probe.json"
    try:
        if args.fixture:
            page_html = Path(args.fixture).read_text(encoding="utf-8")
            if args.retrieved_at:
                parsed_time = datetime.fromisoformat(args.retrieved_at.replace("Z", "+00:00"))
                if parsed_time.tzinfo is None:
                    raise ValueError("--retrieved-at must include a UTC offset")
                retrieved_at = parsed_time.astimezone(timezone.utc)
        else:
            status, page_html, headers = fetch_page()
            if status != 200:
                raise ValueError(f"official lobby returned HTTP {status}")
        document, probe = build_documents(page_html, retrieved_at, headers)
    except Exception as exc:  # retain prior inventory, but publish the failed attempt
        write_json(probe_path, {
            "generated_at_utc": iso(retrieved_at),
            "source_page": LOBBY,
            "response_headers": headers,
            "error": str(exc),
            "result": "failed; previous fixture inventory retained",
        })
        print(f"fixture collection failed: {exc}", file=sys.stderr)
        return 1

    write_json(ROOT / "data" / "hotspawn_matches.json", document)
    write_json(probe_path, probe)
    print(f"exact lobby fixtures written: {document['match_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
