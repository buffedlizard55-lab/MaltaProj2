#!/usr/bin/env python3
"""Session b1fb1465 probe round 2 — HLTV access paths, odds aggregators and exchange depth.

Round 1 established, with HTTP evidence, that:

* HLTV answers the sandbox/interactive reader but returns **403 + Cloudflare challenge** to every
  GitHub-runner request (matches, betting analytics, match page).
* Kalshi lists game markets for four of the six unpriced HotSpawn fixtures, two of which the
  inherited collector rejected as thin and two of which it could not join by name.
* bo3.gg publishes Thunderpick coefficients for RoundsGG fixtures under the name ``ROUNDS``.

Round 2 asks the follow-up questions that decide what can be automated and what must be published
as a limitation:

1. Is there a *documented, public* way to read the HLTV odds page from a datacenter address
   (text relays), or does the project have to treat HLTV as an interactive-only, dated cross-check?
2. Do public odds aggregators expose machine-readable CS2 odds (Oddsportal, Oddspedia)?
3. For the Kalshi events that cover the gap fixtures, what are the actual bid/ask and spread, i.e.
   is the rejection correct and what depth is available?
"""
from __future__ import annotations

import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote as urlquote

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "b1fb1465"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
HLTV_ANALYTICS = ("https://www.hltv.org/betting/analytics/2399463/pcific-vs-ryvex-"
                  "cct-2026-europe-series-12-closed-qualifier")
LOG: list[dict] = []

# Gap fixtures from round 1, with the exchange tickers that reference them.
GAP_TICKERS = {
    "1081113": "KXCS2GAME-26OCT141000RYVWRA",   # Ryvex vs WRAITH PCIFIC
    "1080286": "KXCS2GAME-26OCT160600RGGHAVU",  # RoundsGG vs HAVU
    "1080289": "KXCS2GAME-26OCT161200RGGVOC",   # RoundsGG vs Voca
    "1081120": "KXCS2GAME-26OCT161000PGMEL",    # Privateer Gaming vs mellren
}


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str, headers: dict | None = None, timeout: int = 45) -> tuple[str, dict]:
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
    h.update(headers or {})
    meta = {"url": url, "status": None, "bytes": 0, "error": None, "at_utc": iso(datetime.now(timezone.utc))}
    text = ""
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            raw = r.read()
            meta["status"] = r.status
            meta["content_type"] = r.headers.get("Content-Type")
            text = raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        meta["status"] = exc.code
        meta["error"] = f"HTTPError {exc.code}"
        try:
            text = exc.read(8192).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            text = ""
    except Exception as exc:  # noqa: BLE001
        meta["error"] = f"{type(exc).__name__}: {exc}"[:300]
    meta["bytes"] = len(text)
    meta["preview"] = text[:200].replace("\n", " ")
    LOG.append(meta)
    return text, meta


def json_of(text: str):
    try:
        return json.loads(text)
    except ValueError:
        return None


def probe_hltv_paths(report: dict) -> None:
    paths = {
        "direct_text_relay": f"https://r.jina.ai/{HLTV_ANALYTICS}",
        "codetabs_proxy": "https://api.codetabs.com/v1/proxy?quest=" + urlquote(HLTV_ANALYTICS, safe=""),
        "allorigins": "https://api.allorigins.win/raw?url=" + urlquote(HLTV_ANALYTICS, safe=""),
        "hltv_analytics_plain": "https://www.hltv.org/betting/analytics",
        "hltv_robots": "https://www.hltv.org/robots.txt",
    }
    out: dict = {}
    for key, url in paths.items():
        text, meta = fetch(url, {"Accept": "text/plain,text/html;q=0.9,*/*;q=0.8"})
        odds_samples = sorted({m.group(1) for m in re.finditer(r"\b(1\.\d\d|2\.\d\d)\b", text)})[:12]
        out[key] = {
            "status": meta.get("status"), "error": meta.get("error"), "bytes": meta.get("bytes"),
            "cloudflare_challenge": "Just a moment" in text or "cf_challenge" in text,
            "has_ryvex": bool(re.search(r"ryvex", text, re.I)),
            "has_odds_words": bool(re.search(r"odds|coefficient|bookmaker", text, re.I)),
            "decimal_numbers_sample": odds_samples,
            "preview": meta.get("preview", "")[:160],
        }
    report["hltv_paths"] = out


def probe_aggregators(report: dict) -> None:
    targets = {
        "oddsportal_cs2": "https://www.oddsportal.com/esports/counter-strike/",
        "oddsportal_root": "https://www.oddsportal.com/esports/",
        "oddspedia_root": "https://oddspedia.com/esports",
        "oddspedia_cs2_json": "https://oddspedia.com/api/v1/getMatchList?category=counter-strike",
        "flashscore_cs2": "https://www.flashscore.com/esports/counter-strike/",
        "sofascore_cs2": "https://www.sofascore.com/api/v1/sport/esports/scheduled-events/2026-10-14",
        "bo3gg_api_matches": "https://api.bo3.gg/api/v1/matches/?page%5Blimit%5D=5",
        "liquipedia_cs2_api": ("https://liquipedia.net/counterstrike/api.php?action=query&format=json"
                               "&list=search&srsearch=CCT%20Europe%202026%20Series%2012"),
    }
    out: dict = {}
    for key, url in targets.items():
        text, meta = fetch(url, {"Accept": "application/json, text/html;q=0.9"})
        data = json_of(text)
        out[key] = {
            "status": meta.get("status"), "error": meta.get("error"), "bytes": meta.get("bytes"),
            "json": data is not None,
            "has_odds_pattern": bool(re.search(r"\"odds\"|oddCell|bookmaker", text, re.I)),
            "gap_team_hits": sorted({k for k, rx in (
                ("ryvex", r"ryvex"), ("pcific", r"pcific"), ("roundsgg", r"rounds\s?gg|rounds"),
                ("havu", r"\bhavu\b"), ("mellren", r"mellren"), ("privateer", r"privateer"),
                ("banda", r"banda"), ("dendele", r"dendele"), ("wildcard", r"wildcard"),
            ) if re.search(rx, text, re.I)}),
            "preview": meta.get("preview", "")[:160],
        }
    report["aggregators"] = out


def probe_kalshi_depth(report: dict) -> None:
    """Bid/ask and spread for the exchange events that reference the unpriced fixtures."""
    out: dict = {}
    for fixture_id, ticker in GAP_TICKERS.items():
        url = (f"https://api.elections.kalshi.com/trade-api/v2/events/{ticker}"
               "?with_nested_markets=true")
        text, meta = fetch(url, {"Accept": "application/json"})
        data = json_of(text) or {}
        ev = data.get("event") or {}
        rows = []
        for mk in ev.get("markets") or []:
            def num(*keys):
                for k in keys:
                    v = mk.get(k)
                    if v not in (None, ""):
                        try:
                            return float(v)
                        except (TypeError, ValueError):
                            continue
                return None
            bid = num("yes_bid_dollars", "yes_bid")
            ask = num("yes_ask_dollars", "yes_ask")
            if bid is not None and bid > 1:
                bid, ask = bid / 100.0, ask / 100.0
            rows.append({"ticker": mk.get("ticker"), "sub_title": mk.get("yes_sub_title"),
                         "status": mk.get("status"), "bid": bid, "ask": ask,
                         "spread": None if None in (bid, ask) else round(ask - bid, 3),
                         "volume": mk.get("volume"), "open_interest": mk.get("open_interest"),
                         "liquidity": mk.get("liquidity_dollars") or mk.get("liquidity")})
        out[fixture_id] = {"event_ticker": ticker, "title": ev.get("title"),
                           "status": meta.get("status"), "error": meta.get("error"),
                           "markets": rows,
                           "public_url": f"https://kalshi.com/markets/kxcs2game/{ticker.lower()}"}
    report["kalshi_depth"] = out


def main() -> int:
    report: dict = {"session": "b1fb1465", "round": 2,
                    "generated_utc": iso(datetime.now(timezone.utc))}
    for name, fn in (("hltv_paths", probe_hltv_paths), ("aggregators", probe_aggregators),
                     ("kalshi_depth", probe_kalshi_depth)):
        try:
            fn(report)
        except Exception as exc:  # noqa: BLE001
            report[f"{name}_error"] = f"{type(exc).__name__}: {exc}"[:300]
        print(f"[probe2] {name} done")
    report["requests"] = LOG
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "probe_round2.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                           encoding="utf-8")
    print("== round 2 summary ==")
    print("hltv_paths:", json.dumps(report.get("hltv_paths"))[:2000])
    print("aggregators:", json.dumps(report.get("aggregators"))[:2000])
    print("kalshi_depth:", json.dumps(report.get("kalshi_depth"))[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
