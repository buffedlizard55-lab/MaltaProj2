#!/usr/bin/env python3
"""
HotSpawn Pick'ems — fixture collector (reverse-engineered public API).

Source of truth
---------------
play.hotspawn.com is an Angular SSR app that loads its data from a public JSON API:

    https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/

Endpoints observed in the SSR payload of https://play.hotspawn.com/lobby
(see evidence/api.md for the raw capture and the exact HTML/JS bytes they came from):

    /api/v1/fixtures                              -> list of every fixture ever offered
    /api/v1/tenants/slug/hotspawn                 -> tenant + feature flags
    /api/v1/week-prizes/widget                    -> weekly prizes
    /api/v1/admin/gamification/fixtures/permalinks -> match permalink slugs

The lobby HTML only server-renders the next ~27 fixtures, so the API dump (not the
HTML) is the only complete source for the weekly pick'em list.

This script writes:
    data/hotspawn_matches.json  - normalised current pick'em window fixtures
    evidence/hotspawn_probe.json - diagnostics/evidence (endpoint probes, raw field list)

It performs no inference: every value comes straight from the API response.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1"
LOBBY_PAGE = "https://play.hotspawn.com/lobby"
UA = "MaltaProj2-research/1.0 (+https://github.com/buffedlizard55-lab/MaltaProj2)"
# HotSpawn publishes per-match permalinks as /matches/<team-a>-vs-<team-b>-<tournament>-<fixture id>.
# A bare /matches/<numeric id> is NOT published by HotSpawn: it resolves to the general matches
# index (verified 2026-10-14 ~01:50 UTC), so it must never be used as a per-row source link.
PERMALINK_PATH_RE = re.compile(
    r"https?://(?:www\.)?hotspawn\.com/matches/([A-Za-z0-9][A-Za-z0-9\-\.\+']*)")
PERMALINK_TAIL_RE = re.compile(r"^(.+)-(\d{4,})$")


def extract_published_permalinks(html: str) -> dict:
    """Map fixture id -> the per-match permalink HotSawn itself publishes on the lobby page.

    Only URLs found verbatim in the served page are returned. A fixture without a published
    permalink is absent from the map, so the caller falls back to the official lobby URL instead
    of constructing a slug. The id is the trailing `-<digits>` of the published slug, which keeps
    tournaments containing digits intact (`...-cct-europe-2026-series-11-1079621`).
    """
    out = {}
    for segment in PERMALINK_PATH_RE.findall(html or ""):
        tail = PERMALINK_TAIL_RE.match(segment)
        if tail:
            out.setdefault(tail.group(2), "https://www.hotspawn.com/matches/" + segment)
    return out
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE_STATUSES = {"upcoming", "live", "open", "pending", "scheduled"}


def get_json(path: str, timeout: int = 120):
    """GET an API path; return (status, parsed_json_or_text)."""
    url = path if path.startswith("http") else API + path
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:  # keep the body for evidence
        body = exc.read()
        status = exc.code
    try:
        return status, json.loads(body.decode("utf-8", "replace")), url
    except Exception:
        return status, body.decode("utf-8", "replace")[:2000], url


def ms_to_iso(value):
    """Convert epoch-milliseconds (str/int) to an ISO-8601 UTC string. No inference."""
    if value in (None, "", "0"):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None


def main() -> int:
    status, fixtures, url = get_json("/fixtures")
    probe = {
        "api_base": API,
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endpoint_status": {"GET " + url: status},
    }
    if not isinstance(fixtures, list):
        probe["error"] = "fixtures endpoint did not return a list"
        probe["body_preview"] = fixtures
        _write(os.path.join(ROOT, "evidence", "hotspawn_probe.json"), probe)
        return 1

    probe["fixtures_total"] = len(fixtures)
    keys = sorted({k for f in fixtures for k in f})
    probe["fixture_fields"] = keys

    # ---- ancillary endpoints (evidence only) ----
    for path in ("/tenants/slug/hotspawn", "/week-prizes/widget",
                 "/admin/gamification/fixtures/permalinks"):
        st, body, u = get_json(path, timeout=60)
        probe.setdefault("endpoint_status", {})["GET " + u] = st
        if st == 200:
            if isinstance(body, list):
                probe["endpoint_sample_" + path.strip("/").replace("/", "_")] = body[:3]
                probe["endpoint_length_" + path.strip("/").replace("/", "_")] = len(body)
            else:
                probe["endpoint_sample_" + path.strip("/").replace("/", "_")] = body

    # ---- current pick'em window = every fixture the lobby can still offer ----
    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    window = []
    for f in fixtures:
        status_l = str(f.get("status", "")).lower()
        sched = f.get("scheduled_start_time")
        try:
            sched_ms = int(sched)
        except (TypeError, ValueError):
            sched_ms = None
        if status_l == "ended":
            continue
        # keep everything not finished, plus recently finished (last 24h) for auditing
        if sched_ms is not None and sched_ms < now_ms - 24 * 3600 * 1000 and status_l not in LIVE_STATUSES:
            continue
        window.append(f)

    window.sort(key=lambda f: int(f.get("scheduled_start_time") or 0))

    # Per-row source links come only from permalinks HotSpawn itself publishes on the lobby page.
    status, page_body, page_url = get_json(LOBBY_PAGE, timeout=60)
    page_html = page_body if isinstance(page_body, str) else ""
    permalinks = extract_published_permalinks(page_html)
    probe["lobby_page"] = {"url": page_url, "status": status,
                           "permalinks_published": len(permalinks),
                           "permalinks_sample": dict(list(sorted(permalinks.items()))[:5])}

    matches = []
    for f in window:
        cid = f.get("competition_id")
        matches.append({
            "fixture_id": str(f.get("id")),
            "competition_id": str(cid) if cid is not None else None,
            "competition_name": f.get("competition_name"),
            "sport": f.get("sport_alias"),
            "sport_name": f.get("sport_name"),
            "status": f.get("status"),
            "tier": (f.get("tier") or None),
            "stage": f.get("stage"),
            "best_of": f.get("best_of"),
            "series_format": f.get("series_format"),
            "scheduled_start_time": ms_to_iso(f.get("scheduled_start_time")),
            "lock_time": ms_to_iso(f.get("lock_time")),
            "lock_offset_sec": f.get("lock_offset_sec"),
            "offered_points": f.get("offered_points"),
            "base_points": f.get("base_points"),
            "total_picks": f.get("total_picks"),
            "team_a_id": str(f.get("participants0_id")) if f.get("participants0_id") is not None else None,
            "team_a": f.get("participants0_name"),
            "team_a_pick_pct": f.get("participants0_picked_percent"),
            "team_b_id": str(f.get("participants1_id")) if f.get("participants1_id") is not None else None,
            "team_b": f.get("participants1_name"),
            "team_b_pick_pct": f.get("participants1_picked_percent"),
            "source": {
                "api": f"{API}/fixtures",
                "page": LOBBY_PAGE,
                "hotspawn_match_url": permalinks.get(str(f.get("id")), LOBBY_PAGE),
                "hotspawn_match_url_kind": ("lobby_published_permalink"
                                            if str(f.get("id")) in permalinks
                                            else "official_lobby_fallback"),
            },
        })

    out = {
        "generated_at_utc": probe["generated_at_utc"],
        "source_api": API,
        "source_endpoint": f"{API}/fixtures",
        "source_page": "https://play.hotspawn.com/lobby",
        "note": ("Reverse-engineered public JSON API of play.hotspawn.com. "
                 "team_a_pick_pct / team_b_pick_pct are HotSpawn player PICK percentages "
                 "and are NOT betting probabilities; they are recorded for reference only."),
        "match_count": len(matches),
        "permalinks": permalinks,
        "permalinks_note": ("fixture id -> the official HotSpawn match URL the lobby page itself "
                            "publishes; /matches/<id> on its own redirects to the matches index and "
                            "is never published, so the official lobby page is used instead"),
        "matches": matches,
    }
    _write(os.path.join(ROOT, "data", "hotspawn_matches.json"), out, indent=1)
    _write(os.path.join(ROOT, "evidence", "hotspawn_probe.json"), probe, indent=1)

    probe["window_count"] = len(matches)
    probe["window_first"] = matches[0]["scheduled_start_time"] if matches else None
    probe["window_last"] = matches[-1]["scheduled_start_time"] if matches else None
    _write(os.path.join(ROOT, "evidence", "hotspawn_probe.json"), probe, indent=1)
    print(f"matches written: {len(matches)}")
    return 0


def _write(path, obj, indent=2):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=indent, ensure_ascii=False, sort_keys=False)


if __name__ == "__main__":
    sys.exit(main())
