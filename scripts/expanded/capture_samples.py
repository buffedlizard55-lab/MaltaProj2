#!/usr/bin/env python3
"""Capture raw payload samples from reachable external odds sources.

Stage 1 of T-EXPAND. The sandbox that writes this repo has no general internet egress,
so payload structure must be learned from a runner run and stored as evidence. Everything
here is a *raw* capture: no parsing, no interpretation, no prices committed to the
deliverable from this step.

Saved to data/expanded/samples/<key>.json with a manifest. Lists are trimmed for repo
size; every trim records the original length so nothing looks smaller than it is.

Usage: python3 scripts/expanded/capture_samples.py [--outdir DIR]
"""
from __future__ import annotations

import argparse
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
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
}
PIN_HEADERS = {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
               "Referer": "https://www.pinnacle.com/", "X-Device-UUID": "b9dc3e0e-2f6e-4a5f-9d5c-6a0a5e5b1a11"}
MAX_BYTES = 6_000_000

LINE_FEED_HOSTS = ["melbet.com", "22bet.com", "betwinner.com"]


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
    """Trim big lists so a sample stays committable; record original sizes.

    Top-level lists keep up to `top_cap` entries (so every event of a coupon is present);
    nested lists keep `nested_cap` (enough to learn the market/outcome structure).
    """
    if depth > 7:
        return obj
    if isinstance(obj, list):
        cap = top_cap if depth == 0 else nested_cap
        out = [trim_json(x, top_cap, nested_cap, dict_cap, depth + 1) for x in obj[:cap]]
        if len(obj) > cap:
            return {"_trimmed_list": True, "_original_length": len(obj), "_items": out}
        return out
    if isinstance(obj, dict):
        keys = list(obj.keys())
        return {k: trim_json(obj[k], top_cap, nested_cap, dict_cap, depth + 1) for k in keys[:dict_cap]}
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
            trimmed = trim_json(data)
            path.write_text(json.dumps(trimmed, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001
            rec["json"] = False
            path = outdir / f"{key}.txt"
            path.write_text(text[:200_000], encoding="utf-8")
    else:
        rec["json"] = False
        path = outdir / f"{key}.txt"
        path.write_text((body[:4000].decode("utf-8", "replace") if body else ""), encoding="utf-8")
    rec["saved_as"] = path.name
    print(f"{status:>4} {key:<34} bytes={len(body):<9} -> {path.name} {notes}")
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=str(ROOT / "data" / "expanded" / "samples"))
    args = ap.parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []

    # ---------------------------------------------------------------- Pinnacle
    records.append(save(outdir, "pinnacle_sports",
                        "https://guest.api.arcadia.pinnacle.com/0.1/sports", *get(
                            "https://guest.api.arcadia.pinnacle.com/0.1/sports", PIN_HEADERS)))
    records.append(save(outdir, "pinnacle_esports_leagues",
                        "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/leagues", *get(
                            "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/leagues", PIN_HEADERS)))
    st, body, err = get("https://guest.api.arcadia.pinnacle.com/0.1/sports/12/matchups", PIN_HEADERS)
    records.append(save(outdir, "pinnacle_esports_matchups",
                        "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/matchups", st, body, err))
    matchup_ids: list[int] = []
    if st == 200:
        try:
            for m in json.loads(body.decode("utf-8", "replace")):
                if m.get("type") == "matchup" and m.get("id"):
                    matchup_ids.append(m["id"])
        except Exception:  # noqa: BLE001
            pass
    for mid in matchup_ids[:6]:
        url = f"https://guest.api.arcadia.pinnacle.com/0.1/matchups/{mid}/markets/related/straight"
        records.append(save(outdir, f"pinnacle_markets_{mid}", url, *get(url, PIN_HEADERS),
                            notes="straight markets for sample matchup"))

    # ---------------------------------------------------------------- Bovada
    for key, path in (("bovada_cs2", "counter-strike-2"), ("bovada_lol", "league-of-legends"),
                      ("bovada_esports_all", "")):
        url = ("https://www.bovada.lv/services/sports/event/v2/events/A/description/esports"
               + (f"/{path}" if path else ""))
        records.append(save(outdir, key, url, *get(url)))

    # ---------------------------------------------------------------- 1xBet family (LineFeed)
    for host in LINE_FEED_HOSTS:
        for key, tmpl in (
            ("sports_short", "https://{h}/service-api/LineFeed/GetSportsShortZip?sports=1&lng=en&country=1"),
            ("esports_champs", "https://{h}/service-api/LineFeed/GetChampsZip?sports=12&lng=en&country=1"),
            ("esports_1x2", "https://{h}/service-api/LineFeed/Get1x2_VZip?sports=12&count=1000&lng=en&mode=4&country=1"),
            ("all_1x2", "https://{h}/service-api/LineFeed/Get1x2_VZip?sports=3&count=50&lng=en&mode=4&country=1"),
        ):
            url = tmpl.format(h=host)
            records.append(save(outdir, f"linefeed_{host.split('.')[0]}_{key}", url, *get(url)))

    # ---------------------------------------------------------------- bo3.gg (esports fixture/tier data)
    for key, url in (
        ("bo3gg_cs2_upcoming",
         "https://bo3.gg/api/v1/matches?filter%5Bmatches.status%5D%5Bin%5D=upcoming&sort=start_date&page=1&limit=50"),
        ("bo3gg_lol_upcoming",
         "https://bo3.gg/api/v1/matches?filter%5Bmatches.status%5D%5Bin%5D=upcoming&filter%5Btournament.discipline%5D%5Bin%5D=2&sort=start_date&page=1&limit=50"),
    ):
        records.append(save(outdir, key, url, *get(url)))

    # ---------------------------------------------------------------- Polymarket
    records.append(save(outdir, "polymarket_esports",
                        "https://gamma-api.polymarket.com/events?closed=false&limit=200&tag_slug=esports",
                        *get("https://gamma-api.polymarket.com/events?closed=false&limit=200&tag_slug=esports")))

    manifest = {"generated_at_utc": now_iso(), "purpose": (
        "Raw payload samples from reachable external odds sources, captured on a runner "
        "with full internet. Used to build and test parsers; no odds value is published "
        "from these samples."), "captures": records}
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"\nWROTE {outdir}/manifest.json  ({len(records)} captures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
