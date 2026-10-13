#!/usr/bin/env python3
"""
External betting-line collector for the HotSpawn pick'em match list.

Rules enforced everywhere in this file (they come from the project requirements):
  * HotSpawn is never used as a probability source. Only its fixture list is used.
  * Every number written to data/odds.json must come from a named external bookmaker /
    exchange / odds aggregator, together with the exact public URL it was read from.
  * Nothing is inferred, interpolated or invented. A match with no external line stays
    empty and is flagged unverified by the site builder.

Sources probed (see SOURCES). Each probe records HTTP status + a response fingerprint in
evidence/odds_probe.json so the reachability claim itself is auditable.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36 MaltaProj2-research/1.0")

SOURCES = [
    {
        "key": "pinnacle",
        "name": "Pinnacle (guest API)",
        "kind": "bookmaker",
        "url": "https://guest.api.arcadia.pinnacle.com/0.1/sports",
        "public_page": "https://www.pinnacle.com/en/esports/",
    },
    {
        "key": "polymarket",
        "name": "Polymarket (prediction market, public API)",
        "kind": "exchange",
        "url": "https://gamma-api.polymarket.com/events?closed=false&limit=20&tag_slug=counter-strike",
        "public_page": "https://polymarket.com/markets/esports",
    },
    {
        "key": "betexplorer",
        "name": "BetExplorer (odds aggregator)",
        "kind": "aggregator",
        "url": "https://www.betexplorer.com/counter-strike/",
        "public_page": "https://www.betexplorer.com/counter-strike/",
    },
    {
        "key": "oddspedia",
        "name": "Oddspedia (odds aggregator)",
        "kind": "aggregator",
        "url": "https://oddspedia.com/esports/counter-strike",
        "public_page": "https://oddspedia.com/esports/counter-strike",
    },
    {
        "key": "egamersworld",
        "name": "EGamersWorld (esports portal with bookmaker odds)",
        "kind": "portal",
        "url": "https://egamersworld.com/counterstrike/matches",
        "public_page": "https://egamersworld.com/counterstrike/matches",
    },
    {
        "key": "hltv",
        "name": "HLTV (match metadata / verification)",
        "kind": "reference",
        "url": "https://www.hltv.org/matches",
        "public_page": "https://www.hltv.org/matches",
    },
    {
        "key": "thunderpick",
        "name": "Thunderpick (title sponsor bookmaker)",
        "kind": "bookmaker",
        "url": "https://thunderpick.io/en/sports",
        "public_page": "https://thunderpick.io/en/sports/esports/counter-strike",
    },
    {
        "key": "ggbet",
        "name": "GG.BET (esports bookmaker)",
        "kind": "bookmaker",
        "url": "https://gg.bet/en/esports",
        "public_page": "https://gg.bet/en/esports",
    },
    {
        "key": "bo3gg",
        "name": "bo3.gg (esports portal with bookmaker odds)",
        "kind": "portal",
        "url": "https://bo3.gg/matches/",
        "public_page": "https://bo3.gg/matches/",
    },
]


def fetch(url, timeout=45, headers=None, accept="text/html,application/json,*/*"):
    hdrs = {
        "User-Agent": UA,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
    }
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, dict(resp.headers), body
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()
    except Exception as exc:  # noqa: BLE001 - network failure is evidence too
        return 0, {}, str(exc).encode()


def probe_sources():
    probe = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "probes": [],
    }
    for src in SOURCES:
        status, headers, body = fetch(src["url"])
        text = body.decode("utf-8", "replace")
        probe["probes"].append({
            "key": src["key"],
            "name": src["name"],
            "kind": src["kind"],
            "url": src["url"],
            "http_status": status,
            "content_type": headers.get("Content-Type"),
            "cloudflare_mitigated": headers.get("cf-mitigated"),
            "bytes": len(body),
            "looks_like_json": text.lstrip()[:1] in "[{",
            "body_preview": text[:600],
        })
        time.sleep(1)
    out = os.path.join(ROOT, "evidence", "odds_probe.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(probe, fh, indent=1, ensure_ascii=False)
    return probe


def main() -> int:
    probe = probe_sources()
    ok = [p for p in probe["probes"] if p["http_status"] == 200]
    print(f"reachable sources: {len(ok)}/{len(probe['probes'])}")
    # data/odds.json is produced by the per-source extractors (added once a source is
    # confirmed reachable). Until then the file records an explicit empty result set.
    out = os.path.join(ROOT, "data", "odds.json")
    if not os.path.exists(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({
                "generated_at_utc": probe["generated_at_utc"],
                "lines": [],
                "note": "no external source has been extracted yet; see evidence/odds_probe.json",
            }, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
