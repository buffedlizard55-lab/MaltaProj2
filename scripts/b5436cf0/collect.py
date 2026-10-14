#!/usr/bin/env python3
"""Best-effort live probes for the picks-all section (session b5436cf0).

Refreshes every 4 hours by .github/workflows/allpicks-b5436cf0.yml. Records reachability
of every source this section cites so staleness is visible. NEVER blocks the build:
a failed probe is recorded as evidence, not as a fabricated value. HotSpawn is read for
fixture discovery only.
"""
from __future__ import annotations

import json
import ssl
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "b5436cf0" / "live_checks.json"

PROBES = [
    ("hotspawn_lobby", "https://play.hotspawn.com/lobby", "fixture discovery (never a probability input)"),
    ("egamersworld_matches", "https://egamersworld.com/counterstrike/matches", "esports betting lines aggregator"),
    ("hltv_elisa_event", "https://www.hltv.org/events/9332/elisa-breakout-series-2", "HLTV (runner access often 403)"),
    ("kalshi_cs2", "https://kalshi.com/markets/kxcs2game", "prediction market (exchange)"),
    ("bo3gg_matches", "https://bo3.gg/matches/current", "Thunderpick coefficient feed / analytics"),
]

CTX = ssl.create_default_context()


def probe(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; MaltaProj2-research-bot)"})
    try:
        with urllib.request.urlopen(req, timeout=15, context=CTX) as resp:
            body = resp.read(200000)
            return {"status": int(resp.status), "bytes": len(body)}
    except Exception as exc:  # recorded, never raised
        return {"status": None, "error": f"{type(exc).__name__}: {exc}"[:300]}


def main() -> int:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    checks = []
    for key, url, kind in PROBES:
        result = probe(url)
        checks.append({"key": key, "url": url, "kind": kind, "checked_utc": now, **result})
        print(f"{key}: {result.get('status') or 'ERR'}")
    prior = {}
    if OUT.exists():
        try:
            prior = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            prior = {}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "session": "b5436cf0",
        "checked_utc": now,
        "checks": checks,
        "previous_checked_utc": prior.get("checked_utc"),
        "note": "Probes are reachability evidence only. A 403 (e.g. HLTV on runners) is expected "
                "and is never converted into a value; research facts stay dated session reads.",
    }, indent=1), encoding="utf-8")
    return 0  # probes never fail the pipeline


if __name__ == "__main__":
    raise SystemExit(main())
