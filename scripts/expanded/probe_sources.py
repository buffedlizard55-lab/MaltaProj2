#!/usr/bin/env python3
"""Probe external (non-HotSpawn) esports odds sources for reachability.

Runs on a GitHub Actions runner (full internet). Records, for every candidate
endpoint, the raw HTTP result so that source coverage claims are evidence-backed:

  * http status, content type, byte length
  * whether the body parses as JSON and how many records it carries
  * a short, size-limited preview (kept in the JSON evidence file)
  * for HTML, whether odds-like tokens are present

Nothing is guessed: an endpoint that fails is reported as failed with its exact
error, and never counted as a source of prices.

Usage:  python3 scripts/expanded/probe_sources.py [--out PATH] [--playwright]
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}
ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------- candidates
# key: (label, kind, url, extra_headers)
CANDIDATES: list[tuple[str, str, str, dict]] = [
    # ---------------------------------------------------------- bookmakers (JSON APIs)
    ("pinnacle_sports", "bookmaker", "https://guest.api.arcadia.pinnacle.com/0.1/sports",
     {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/"}),
    ("pinnacle_esports_matchups", "bookmaker", "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/matchups",
     {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/"}),
    ("pinnacle_esports_leagues", "bookmaker", "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/leagues",
     {"X-API-Key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R", "Referer": "https://www.pinnacle.com/"}),
    ("bovada_esports", "bookmaker",
     "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports", {}),
    ("bovada_cs2", "bookmaker",
     "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports/counter-strike-2", {}),
    ("bovada_lol", "bookmaker",
     "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports/league-of-legends", {}),
    ("1xbet_linefeed", "bookmaker",
     "https://1xbet.com/service-api/LineFeed/Get1x2_VZip?sports=3&count=300&lng=en&mode=4&country=1", {}),
    ("1xbet_champs", "bookmaker",
     "https://1xbet.com/service-api/LineFeed/GetChampsZip?sports=3&lng=en&country=1", {}),
    ("melbet_linefeed", "bookmaker",
     "https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=3&count=300&lng=en&mode=4&country=1", {}),
    ("22bet_linefeed", "bookmaker",
     "https://22bet.com/service-api/LineFeed/Get1x2_VZip?sports=3&count=300&lng=en&mode=4&country=1", {}),
    ("betwinner_linefeed", "bookmaker",
     "https://betwinner.com/service-api/LineFeed/Get1x2_VZip?sports=3&count=300&lng=en&mode=4&country=1", {}),
    ("thunderpick_api_matches", "bookmaker", "https://api.thunderpick.io/api/v1/matches", {}),
    ("thunderpick_api_esports", "bookmaker", "https://api.thunderpick.io/api/v1/esports/matches", {}),
    ("ggbet_api_line", "bookmaker", "https://gg.bet/api/line/esports", {}),
    ("ggbet_api_v2", "bookmaker", "https://gg.bet/api/v2/line/esports", {}),
    ("unibet_kambic_listview", "bookmaker",
     "https://eu-offering-api.kambicdn.com/offering/v2018/ubse/listView/esports/all/all/matches.json"
     "?lang=en_GB&market=GB&client_id=2&channel_id=1&ncid=1", {}),
    ("betano_esports_api", "bookmaker", "https://www.betano.pt/api/sport/esports/competicoes/", {}),
    ("draftkings_esports_lobby", "bookmaker",
     "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusnj/v1/leagues/82402", {}),
    ("fanduel_esports", "bookmaker",
     "https://sportsbook.fanduel.com/api/content-managed-page?page=CUSTOM&customPageId=esports"
     "&_ak=FhMFpcPWXMeyZxOx", {}),
    ("pinnacle_public_page", "bookmaker", "https://www.pinnacle.com/en/esports/", {}),
    ("betway_esports", "bookmaker", "https://sports.betway.com/en/sports/grp/esports", {}),
    ("betonline_esports", "bookmaker", "https://www.betonline.ag/sportsbook/esports", {}),
    # ---------------------------------------------------------- prediction markets
    ("polymarket_esports", "prediction-market",
     "https://gamma-api.polymarket.com/events?closed=false&limit=200&tag_slug=esports", {}),
    ("polymarket_cs2", "prediction-market",
     "https://gamma-api.polymarket.com/events?closed=false&limit=100&tag_slug=counter-strike", {}),
    ("polymarket_lol", "prediction-market",
     "https://gamma-api.polymarket.com/events?closed=false&limit=100&tag_slug=league-of-legends", {}),
    ("kalshi_markets", "prediction-market",
     "https://api.elections.kalshi.com/trade-api/v2/markets?limit=200&status=open", {}),
    # ---------------------------------------------------------- odds aggregators
    ("oddspedia_esports", "aggregator", "https://oddspedia.com/esports", {}),
    ("oddspedia_api", "aggregator", "https://oddspedia.com/api/v1/getMatchList?language=en&sport=counter-strike", {}),
    ("betexplorer_esports", "aggregator", "https://www.betexplorer.com/esports/", {}),
    ("betexplorer_cs", "aggregator", "https://www.betexplorer.com/counter-strike/", {}),
    ("egamersworld_cs_matches", "aggregator", "https://egamersworld.com/counterstrike/matches", {}),
    ("egamersworld_lol_matches", "aggregator", "https://egamersworld.com/leagueoflegends/matches", {}),
    ("strafe_cs2", "aggregator", "https://strafe.com/matches/counter-strike", {}),
    ("hltv_matches", "reference", "https://www.hltv.org/matches", {}),
    ("hltv_ranking", "reference", "https://www.hltv.org/ranking/teams/2026/october/5", {}),
    ("hltv_betting_analytics", "reference", "https://www.hltv.org/betting/analytics", {}),
    ("bo3gg_matches", "aggregator", "https://bo3.gg/api/v1/matches?filter%5Bmatches.status%5D%5Bin%5D=upcoming", {}),
    ("liquipedia_cs_api", "reference",
     "https://liquipedia.net/counterstrike/api.php?action=query&list=categorymembers"
     "&cmtitle=Category:Tournaments&cmlimit=20&format=json", {}),
    ("valve_vrs_raw", "reference",
     "https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/main/"
     "invitation/2026/standings_global_2026_10_05.md", {}),
    ("hotspawn_lobby", "fixtures", "https://play.hotspawn.com/lobby", {}),
    ("hotspawn_api_fixtures", "fixtures",
     "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures", {}),
]

PLAYWRIGHT_TARGETS = [
    ("egamersworld_cs_matches_pw", "https://egamersworld.com/counterstrike/matches"),
    ("hltv_matches_pw", "https://www.hltv.org/matches"),
    ("thunderpick_cs2_pw", "https://thunderpick.io/esports/cs2-betting"),
    ("oddspedia_esports_pw", "https://oddspedia.com/esports"),
    ("ggbet_esports_pw", "https://gg.bet/en/esports"),
]

ODDS_TOKEN_RE = re.compile(r"(?<![\d.])(\d\.\d{2})(?![\d.])")
JSON_LIMIT = 400_000


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str, extra: dict | None = None, timeout: int = 25):
    headers = dict(HEADERS)
    if extra:
        headers.update(extra)
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            body = r.read(JSON_LIMIT)
            return {
                "http_status": r.status,
                "content_type": r.headers.get("Content-Type"),
                "bytes": len(body),
                "server": r.headers.get("Server"),
                "cf_ray": r.headers.get("CF-RAY"),
                "cloudflare_mitigated": r.headers.get("cf-mitigated"),
                "final_url": r.geturl(),
                "body": body,
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read(JSON_LIMIT)
        except Exception:  # noqa: BLE001
            pass
        return {
            "http_status": exc.code,
            "content_type": exc.headers.get("Content-Type") if exc.headers else None,
            "bytes": len(body),
            "server": exc.headers.get("Server") if exc.headers else None,
            "cf_ray": exc.headers.get("CF-RAY") if exc.headers else None,
            "cloudflare_mitigated": exc.headers.get("cf-mitigated") if exc.headers else None,
            "final_url": None,
            "body": body,
            "error": f"HTTPError {exc.code}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "http_status": 0,
            "content_type": None,
            "bytes": 0,
            "server": None,
            "cf_ray": None,
            "cloudflare_mitigated": None,
            "final_url": None,
            "body": b"",
            "error": f"{type(exc).__name__}: {exc}",
        }


def summarise_body(body: bytes, content_type: str | None):
    """Return (json_ok, json_records, markets_like, preview, odds_tokens)."""
    info = {"json_ok": False, "json_records": None, "markets_like": None,
            "preview": "", "odds_tokens": 0}
    text = ""
    try:
        text = body.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return info
    info["preview"] = text[:600]
    stripped = text.lstrip()
    if stripped[:1] in "[{" and (content_type is None or "json" in (content_type or "")
                                 or stripped[:1] in "[{"):
        try:
            data = json.loads(text)
            info["json_ok"] = True
            if isinstance(data, list):
                info["json_records"] = len(data)
            elif isinstance(data, dict):
                for key in ("data", "events", "matches", "markets", "results", "Value", "Value2"):
                    if isinstance(data.get(key), list):
                        info["json_records"] = len(data[key])
                        break
            info["markets_like"] = 1 if re.search(
                r'"(price|odds|homePrice|awayPrice|decimal|american|moneyline|probability)"', text,
                re.I) else 0
            return info
        except Exception:  # noqa: BLE001
            pass
    info["odds_tokens"] = len(ODDS_TOKEN_RE.findall(text[:200_000]))
    info["markets_like"] = 1 if re.search(r"(moneyline|match winner|1x2|odds)", text, re.I) else 0
    return info


def probe_playwright(targets, results):
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        results.append({"key": "playwright", "kind": "probe-availability", "http_status": 0,
                        "error": f"playwright not installed: {exc}"})
        return results
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900},
                                  locale="en-US")
        page = ctx.new_page()
        for key, url in targets:
            rec = {"key": key, "kind": "playwright-navigation", "url": url}
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                rec["http_status"] = resp.status if resp else 0
                page.wait_for_timeout(6000)
                html = page.content()
                text = page.inner_text("body")
                rec["final_url"] = page.url
                rec["title"] = page.title()
                rec["bytes_html"] = len(html)
                rec["bytes_text"] = len(text)
                rec["odds_tokens"] = len(ODDS_TOKEN_RE.findall(text[:200_000]))
                rec["markets_like"] = 1 if re.search(r"(moneyline|match winner|1x2|odds|vs)", text, re.I) else 0
                rec["preview"] = text[:600]
                rec["error"] = None
            except Exception as exc:  # noqa: BLE001
                rec.update({"http_status": 0, "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            results.append(rec)
        browser.close()
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "expanded" / "source_probe.json"))
    ap.add_argument("--playwright", action="store_true")
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = []
    for key, kind, url, extra in CANDIDATES:
        r = fetch(url, extra)
        body = r.pop("body")
        summary = summarise_body(body, r.get("content_type"))
        rec = {"key": key, "kind": kind, "url": url, **r, **summary}
        results.append(rec)
        print(f"{rec['http_status']:>4}  {key:<32} json={str(summary['json_ok']):<5} "
              f"recs={str(summary['json_records']):<6} bytes={rec['bytes']:<8} "
              f"err={str(rec['error'])[:60]}")
        sys.stdout.flush()

    if args.playwright:
        print("--- playwright navigations ---")
        probe_playwright(PLAYWRIGHT_TARGETS, results)
        for rec in results[-len(PLAYWRIGHT_TARGETS):]:
            if rec.get("kind") != "playwright-navigation":
                continue
            print(f"{rec.get('http_status', 0):>4}  {rec['key']:<32} "
                  f"tokens={rec.get('odds_tokens')} title={str(rec.get('title'))[:60]} "
                  f"err={str(rec.get('error'))[:60]}")
            sys.stdout.flush()

    doc = {
        "generated_at_utc": now_iso(),
        "purpose": ("Reachability evidence for external (non-HotSpawn) esports odds sources. "
                    "A non-200 row is recorded as unavailable and never used for prices."),
        "runner": {"github_actions": bool(__import__("os").environ.get("GITHUB_ACTIONS"))},
        "results": results,
    }
    out_path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    ok = [r for r in results if r.get("http_status") == 200]
    print(f"\nWROTE {out_path} — reachable 200: {len(ok)}/{len(results)}")
    print("reachable keys: " + ", ".join(sorted(r["key"] for r in ok)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
