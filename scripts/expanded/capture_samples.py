#!/usr/bin/env python3
"""Capture raw payload samples from reachable external odds sources.

Stage 1 of T-EXPAND. The sandbox that writes this repo has no general internet egress, so
payload structure must be learned from a runner run and stored as evidence. Everything here
is a *raw* capture: no parsing, no interpretation, and no price is published from this step.

Round 2 additionally discovers the esports sport ids of the 1xBet-family LineFeed (the
mirrors that are reachable), because those feeds are the only reachable source that lists
small tier-C tournaments such as CCT Europe series and Elisa BreakOut.

Payloads under 700 KB are stored verbatim; larger ones are trimmed (top-level lists keep up
to 300 entries, deeper lists up to 8) and the original lengths are recorded.

Usage: python3 scripts/expanded/capture_samples.py [--outdir DIR] [--round 2]
"""
from __future__ import annotations

import argparse
import json
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
}
PIN_HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
               "Referer": "https://www.pinnacle.com/",
               "X-Device-UUID": "b9dc3e0e-2f6e-4a5f-9d5c-6a0a5e5b1a11"}
MAX_BYTES = 8_000_000
VERBATIM_LIMIT = 700_000
LINE_FEED_HOSTS = ["melbet.com", "22bet.com", "betwinner.com"]
ESPORTS_HINTS = ("esport", "counter", "cs2", "csgo", "cyber", "dota", "league of legends",
                 "valorant", "starcraft", "warcraft", "arena of valor", "mobile legends")


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get(url: str, headers: dict | None = None, timeout: int = 40):
    hdrs = dict(BASE_HEADERS)
    if headers:
        hdrs.update(headers)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdrs),
                                    timeout=timeout, context=ssl.create_default_context()) as r:
            return r.status, r.read(MAX_BYTES), None
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read(MAX_BYTES)
        except Exception:  # noqa: BLE001
            pass
        return exc.code, body, f"HTTPError {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return 0, b"", f"{type(exc).__name__}: {exc}"


def trim_json(obj, top_cap=300, nested_cap=8, dict_cap=60, depth=0):
    if depth > 7:
        return obj
    if isinstance(obj, list):
        cap = top_cap if depth == 0 else nested_cap
        out = [trim_json(x, top_cap, nested_cap, dict_cap, depth + 1) for x in obj[:cap]]
        if len(obj) > cap:
            return {"_trimmed_list": True, "_original_length": len(obj), "_items": out}
        return out
    if isinstance(obj, dict):
        return {k: trim_json(obj[k], top_cap, nested_cap, dict_cap, depth + 1)
                for k in list(obj.keys())[:dict_cap]}
    return obj


def save(outdir: Path, key: str, url: str, status: int, body: bytes, error, notes: str = ""):
    rec = {"key": key, "url": url, "http_status": status, "bytes": len(body),
           "error": error, "notes": notes, "captured_at_utc": now_iso()}
    path = outdir / f"{key}.json"
    if status == 200 and body:
        text = body.decode("utf-8", "replace")
        try:
            data = json.loads(text)
            rec["json"] = True
            rec["verbatim"] = len(text) <= VERBATIM_LIMIT
            payload = data if rec["verbatim"] else trim_json(data)
            path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001
            rec["json"] = False
            path = outdir / f"{key}.txt"
            path.write_text(text[:200_000], encoding="utf-8")
    else:
        rec["json"] = False
        path = outdir / f"{key}.txt"
        path.write_text((body[:4000].decode("utf-8", "replace") if body else ""), encoding="utf-8")
    rec["saved_as"] = path.name
    print(f"{status:>4} {key:<36} bytes={len(body):<9} -> {path.name} {notes}")
    return rec


def sports_list(body: bytes) -> list[dict]:
    try:
        value = json.loads(body.decode("utf-8", "replace")).get("Value")
    except Exception:  # noqa: BLE001
        return []
    items = value.get("_items") if isinstance(value, dict) else value
    return [x for x in (items or []) if isinstance(x, dict)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=str(ROOT / "data" / "expanded" / "samples"))
    ap.add_argument("--round", default="2")
    args = ap.parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []

    # ------------------------------------------------------------ Pinnacle
    pin_urls = [
        ("pinnacle_sports", "https://guest.api.arcadia.pinnacle.com/0.1/sports"),
        ("pinnacle_esports_leagues", "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/leagues"),
        ("pinnacle_esports_matchups", "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/matchups"),
    ]
    for key, url in pin_urls:
        records.append(save(outdir, key, url, *get(url, PIN_HEADERS)))

    # ------------------------------------------------------------ Bovada
    for key, path in (("bovada_cs2", "counter-strike-2"), ("bovada_lol", "league-of-legends")):
        url = ("https://www.bovada.lv/services/sports/event/v2/events/A/description/esports"
               + (f"/{path}" if path else ""))
        records.append(save(outdir, key, url, *get(url)))
    # Full esports coupon: kept only for the two games this project covers, because the whole
    # coupon exceeds the committable sample size. The filter and original size are recorded.
    url = "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports"
    st, body, err = get(url)
    if st == 200 and body:
        try:
            groups = json.loads(body.decode("utf-8", "replace"))
            keep = []
            for g in groups:
                link = " ".join(str(p.get("link") or "") for p in (g.get("path") or []))
                if "counter-strike" in link or "league-of-legends" in link:
                    keep.append(g)
            p = outdir / "bovada_pickem_games.json"
            p.write_text(json.dumps(keep, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            rec = {"key": "bovada_pickem_games", "url": url, "http_status": st, "bytes": len(body),
                   "error": err, "json": True, "verbatim": True,
                   "notes": (f"filtered to counter-strike-2 / league-of-legends groups: {len(keep)} of "
                             f"{len(groups)} groups kept"),
                   "captured_at_utc": now_iso(), "saved_as": p.name}
            print(f"{st:>4} bovada_pickem_games                 bytes={len(body):<9} -> {p.name} "
                  f"({len(keep)}/{len(groups)} groups)")
            records.append(rec)
        except Exception as exc:  # noqa: BLE001
            print(f"bovada full-coupon filter failed: {exc}")

    # ------------------------------------------------------------ 1xBet family: discover esports sports
    discovered: dict[str, list[int]] = {}
    for host in LINE_FEED_HOSTS:
        url = (f"https://{host}/service-api/LineFeed/GetSportsShortZip"
               "?sports=1&lng=en&country=1&virtualSports=true&groupChamps=true")
        st, body, err = get(url)
        records.append(save(outdir, f"linefeed_{host.split('.')[0]}_sports_full", url, st, body, err))
        ids = []
        for it in sports_list(body):
            name = " ".join(str(it.get(k) or "") for k in ("N", "SE", "SN", "E")).casefold()
            if any(h in name for h in ESPORTS_HINTS) and isinstance(it.get("I"), int):
                ids.append(it["I"])
        discovered[host] = sorted(set(ids))
        print(f"     {host}: esports-like sport ids {discovered[host]}")

    # The feed mirror bodies are identical (same platform); fetch the feeds for the union.
    all_ids = sorted({i for ids in discovered.values() for i in ids}) or [12]
    for hid in all_ids:
        url = (f"https://melbet.com/service-api/LineFeed/Get1x2_VZip"
               f"?sports={hid}&count=1000&lng=en&mode=4&country=1")
        records.append(save(outdir, f"linefeed_melbet_sport{hid}_1x2", url, *get(url),
                            notes=f"sport id {hid}"))

    # ------------------------------------------------------------ bo3.gg (fixtures, tiers, ratings)
    for key, url in (
        ("bo3gg_cs2_upcoming",
         "https://bo3.gg/api/v1/matches?filter%5Bmatches.status%5D%5Bin%5D=upcoming&sort=start_date&page=1&limit=50"),
        ("bo3gg_teams_ranking",
         "https://bo3.gg/api/v1/teams/ranking?discipline=counter-strike&limit=100"),
        ("bo3gg_teams_rankings_alt",
         "https://bo3.gg/api/v1/ranking/teams?discipline=counter-strike"),
        ("bo3gg_cs2_tournaments",
         "https://bo3.gg/api/v1/tournaments?filter%5Btournaments.status%5D%5Bin%5D=ongoing&limit=50"),
    ):
        records.append(save(outdir, key, url, *get(url)))

    manifest = {"generated_at_utc": now_iso(), "round": args.round,
                "purpose": ("Raw payload samples from reachable external odds sources, captured on a "
                            "runner with full internet. Used to build and test parsers; no odds value is "
                            "published from these samples."),
                "linefeed_esports_sport_ids": discovered,
                "captures": records}
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"\nWROTE {outdir}/manifest.json  ({len(records)} captures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
