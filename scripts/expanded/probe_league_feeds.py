#!/usr/bin/env python3
"""Round-4 exploration: per-championship event feeds of the 1xBet-platform LineFeed.

The flat `Get1x2_VZip?sports=40` feed is capped at ~50 events, so full lobby coverage needs
the per-championship endpoints. This script first reads the platform's own championship list
(`GetChampsZip?`, which returns every league), selects the esports leagues that match the
tournaments in the HotSpawn lobby snapshot, then tries each candidate per-league endpoint for
a handful of those leagues and records exactly what comes back.

Writes data/expanded/league_feed_probe.json and saves any payload that carries odds to
data/expanded/samples/. No price is published from this probe.

Usage: python3 scripts/expanded/probe_league_feeds.py
"""
from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
           "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "identity"}
MIRROR = "https://melbet.com"
MAX = 4_000_000
GOAL_HINTS = ("cct", "elisa", "european pro league", "esl challenger", "pulse", "tp world",
              "thunderpick", "dracula", "urban riga", "svenska", "dach", "rainhas", "ultragear",
              "clutch", "stake")


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get(url: str):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=40,
                                    context=ssl.create_default_context()) as r:
            return r.status, r.read(MAX), None
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read(MAX)
        except Exception:  # noqa: BLE001
            pass
        return exc.code, body, f"HTTPError {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return 0, b"", f"{type(exc).__name__}: {str(exc)[:160]}"


def value_items(body: bytes) -> list[dict]:
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return []
    value = data.get("Value") if isinstance(data, dict) else None
    items = value.get("_items") if isinstance(value, dict) else value
    if isinstance(value, dict) and isinstance(value.get("Value"), list):
        items = value["Value"]
    return [x for x in (items or []) if isinstance(x, dict)]


def main() -> int:
    outdir = ROOT / "data" / "expanded"
    samples = outdir / "samples"
    samples.mkdir(parents=True, exist_ok=True)
    report: dict = {"generated_at_utc": now_iso(), "mirror": MIRROR, "steps": []}

    # 1. championship list
    champs_url = f"{MIRROR}/service-api/LineFeed/GetChampsZip?"
    st, body, err = get(champs_url)
    champs = value_items(body)
    esports = [c for c in champs if str(c.get("SN") or c.get("SE") or "").casefold() == "esports"]
    report["steps"].append({
        "step": "champs_list", "url": champs_url, "status": st, "error": err,
        "records": len(champs), "esports_records": len(esports),
        "sample_keys": sorted(champs[0].keys())[:30] if champs else None,
    })
    print(f"champs: {st} records={len(champs)} esports={len(esports)}")
    if champs:
        (samples / "linefeed_champs_all.json").write_text(
            json.dumps(champs[:1500], indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    # 2. pick esports leagues that match lobby tournaments
    targets = []
    for c in esports:
        name = str(c.get("LE") or c.get("L") or "")
        if any(h in name.casefold() for h in GOAL_HINTS):
            targets.append({"li": c.get("LI"), "name": name, "games": c.get("GC")})
    seen = set()
    uniq = []
    for t in targets:
        if t["li"] in seen:
            continue
        seen.add(t["li"])
        uniq.append(t)
    report["target_leagues"] = uniq[:40]
    print(f"target esports leagues: {len(uniq)}")

    # 3. per-league feed variants
    variants = [
        ("GetChampZip", f"{MIRROR}/service-api/LineFeed/GetChampZip?id={{li}}&lng=en&country=1"),
        ("GetChampZip_gr", f"{MIRROR}/service-api/LineFeed/GetChampZip?id={{li}}&lng=en&country=1&groupChamps=true&virtualSports=true"),
        ("GetGameZip", f"{MIRROR}/service-api/LineFeed/GetGameZip?id={{li}}&lng=en&country=1"),
    ]
    for t in uniq[:6]:
        for label, tmpl in variants:
            url = tmpl.format(li=t["li"])
            st, body, err = get(url)
            items = value_items(body)
            rec = {"step": label, "league": t, "url": url, "status": st, "error": err,
                   "records": len(items),
                   "item_keys": sorted(items[0].keys())[:30] if items else None,
                   "has_odds": bool(items and any(isinstance(i.get("E"), list) and i.get("E") for i in items))}
            if rec["records"] and st == 200:
                safe = re.sub(r"[^a-z0-9]+", "_", t["name"].casefold())[:40]
                fname = f"linefeed_{label}_{t['li']}_{safe}.json"
                (samples / fname).write_text(json.dumps(items[:200], indent=1, ensure_ascii=False) + "\n",
                                             encoding="utf-8")
                rec["saved_as"] = fname
            report["steps"].append(rec)
            print(f"{st:>4} {label:<14} li={t['li']:<8} recs={rec['records']:<5} odds={rec['has_odds']} "
                  f"{str(t['name'])[:34]} {str(err)[:40]}")

    (outdir / "league_feed_probe.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(f"\nWROTE {outdir / 'league_feed_probe.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
