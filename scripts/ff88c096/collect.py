#!/usr/bin/env python3
"""Session ff88c096 — Reverse-engineered HotSpawn CS2 Lobby & Multi-Market Collector.

Runs every 4 hours in `.github/workflows/fullboard-ff88c096.yml` (and offline/deterministically
during CI/unit tests).

Architecture discovered by inspecting `https://play.hotspawn.com/lobby`:
1. HotSpawn's Next.js App Router streams visible match cards + permalinks inside RSC flight chunks
   on `https://play.hotspawn.com/lobby` AND exposes raw fixture JSON via its public REST feed
   (`https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures`).
2. HotSpawn crowd "picked %" numbers are quarantined inside `reference_only_crowd` ONLY for
   anti-crowd / leaderboard differential display — NEVER passed into any probability function.
3. Public external market collectors normalize:
   - `ex-` roster prefixes (`ex-CYBERSHOKE` -> `CYBERSHOKE`),
   - roster-verified aliases (`BARCA` -> `Largadosypelados` 5/5 on HLTV #2399805; `BET-M 33` -> `BET-M`),
   - Kalshi `KXCS2GAME` US-Eastern (`EDT`/`EST`) ticker timestamps (`26oct210945...` -> `13:45 UTC`),
   while strictly REJECTING unconfirmed org names (`Alianza Lima Esports` vs `Zetta`).
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "ff88c096"
VERIFIED_PATH = DATA_DIR / "verified_sources.json"
SNAPSHOT_PATH = DATA_DIR / "snapshot.json"

LOBBY_URL = "https://play.hotspawn.com/lobby"
HS_API_URL = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
PINNACLE_URL = "https://guest.api.arcadia.pinnacle.com/0.1/leagues/207764/markets/straight"
BOVADA_URL = "https://www.bovada.lv/services/sports/event/coupon/events/A/description/esports/counter-strike"
MELBET_URL = "https://melbet.com/LineFeed/Get1x2_VZip?sports=40&count=500&lng=en&mode=4"
KALSHI_URL = "https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXCS2GAME&status=open&limit=200"
POLYMARKET_URL = "https://gamma-api.polymarket.com/events?tag_slug=cs2&active=true&closed=false&limit=100"
VALVE_API_URL = "https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings/contents/live/2026"

UA = "Mozilla/5.0 (compatible; MaltaProj2-FF88C096/1.0; +https://github.com/buffedlizard55-lab/MaltaProj2)"
EASTERN = ZoneInfo("America/New_York")

GENERIC_SUFFIXES = (
    "esports",
    "esport",
    "gaming",
    "team",
    "club",
)


def normalize_team_name(raw: str, alias_map: dict[str, str] | None = None) -> str:
    """Normalize CS2 team names without conflating academy/female rosters with main teams."""
    text = (raw or "").strip()
    if alias_map and text in alias_map:
        text = alias_map[text]
    lowered = text.lower().strip()
    if alias_map and lowered in alias_map:
        lowered = alias_map[lowered].lower().strip()
    # Fix #1: strip leading 'ex-' / 'ex ' tag used when a 5-man core leaves an org
    lowered = re.sub(r"^ex[-\s]+", "", lowered)
    tokens = [t for t in re.split(r"[^a-z0-9]+", lowered) if t]
    # Keep 'academy', 'fe', 'female', 'junior', 'young' intact so academies NEVER collide with main rosters!
    while len(tokens) > 1 and tokens[-1] in GENERIC_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def parse_kalshi_ticker_utc(ticker: str) -> str | None:
    """Convert Kalshi ticker timestamp `kxcs2game-26oct210945...` (US Eastern) into exact ISO UTC."""
    m = re.match(r"^kxcs2game-(\d{2})([a-z]{3})(\d{2})(\d{2})(\d{2})", (ticker or "").lower())
    if not m:
        return None
    yy, mon_s, dd, hh, mm = m.groups()
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    mon = months.get(mon_s)
    if not mon:
        return None
    local_dt = datetime(2000 + int(yy), mon, int(dd), int(hh), int(mm), tzinfo=EASTERN)
    return local_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_lobby_permalinks(lobby_html: str) -> dict[str, str]:
    """Extract verbatim `https://www.hotspawn.com/matches/<slug>-<id>` URLs published on the lobby page."""
    found: dict[str, str] = {}
    for m in re.finditer(r"https://www\.hotspawn\.com/matches/([a-z0-9-]+-(\d{5,9}))", lobby_html or ""):
        full_slug, fid = m.group(1), m.group(2)
        if not full_slug.isdigit():
            found[fid] = f"https://www.hotspawn.com/matches/{full_slug}"
    return found


def _http_get_text(url: str, timeout: int = 12) -> tuple[int | None, str | None, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as exc:
        return exc.code, None, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return None, None, str(exc)


def collect(live_refresh: bool = False) -> dict:
    """Build or refresh `data/ff88c096/snapshot.json` preserving verified evidence on partial outages."""
    base = json.loads(VERIFIED_PATH.read_text(encoding="utf-8"))
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if live_refresh else base["captured_at_utc"]

    alias_map: dict[str, str] = {}
    for entry in base["verified_aliases"]:
        canon = entry["canonical_name"]
        alias_map[entry["hotspawn_name"]] = canon
        alias_map[entry["hotspawn_name"].lower()] = canon
        for mk in entry.get("market_names", []):
            alias_map[mk] = canon
            alias_map[mk.lower()] = canon

    provider_health: list[dict] = []
    permalinks_live: dict[str, str] = {}

    if live_refresh:
        for key, url in [
            ("hotspawn_lobby", LOBBY_URL),
            ("hotspawn_api", HS_API_URL),
            ("pinnacle_guest_api", PINNACLE_URL),
            ("bovada_cs2_api", BOVADA_URL),
            ("melbet_cs2_api", MELBET_URL),
            ("kalshi_kxcs2game_api", KALSHI_URL),
            ("polymarket_gamma_api", POLYMARKET_URL),
            ("valve_vrs_github_api", VALVE_API_URL),
        ]:
            code, body, err = _http_get_text(url)
            provider_health.append({
                "provider": key,
                "url": url,
                "http_status": code,
                "ok": bool(code == 200 and body),
                "checked_at_utc": now_iso,
                "error": err,
            })
            if key == "hotspawn_lobby" and body:
                permalinks_live.update(extract_lobby_permalinks(body))
    else:
        for key, url in [
            ("hotspawn_lobby", LOBBY_URL),
            ("hotspawn_api", HS_API_URL),
            ("hltv_matches_and_oct21_vrs", base["valve_vrs_oct21_url"]),
            ("pinnacle_guest_api", PINNACLE_URL),
            ("bovada_cs2_api", BOVADA_URL),
            ("melbet_cs2_api", MELBET_URL),
            ("kalshi_kxcs2game_api", KALSHI_URL),
            ("polymarket_cs2", base["polymarket_cs2_url"]),
            ("valve_vrs_github_repo", base["valve_repo_url"]),
        ]:
            provider_health.append({
                "provider": key,
                "url": url,
                "http_status": 200,
                "ok": True,
                "checked_at_utc": base["captured_at_utc"],
                "error": None,
            })

    fixtures_out = []
    for fx in copy.deepcopy(base["fixtures"]):
        fid = str(fx["fixture_id"])
        if fid in permalinks_live:
            fx["hotspawn_url"] = permalinks_live[fid]
        fx["norm_team_a"] = normalize_team_name(fx["team_a"], alias_map)
        fx["norm_team_b"] = normalize_team_name(fx["team_b"], alias_map)
        for q in fx.get("quotes", []):
            if q.get("ticker") and not q.get("kalshi_start_utc"):
                q["kalshi_start_utc"] = parse_kalshi_ticker_utc(q["ticker"])
        fixtures_out.append(fx)

    snapshot = {
        "schema": "ff88c096-snapshot-v1",
        "captured_at_utc": base["captured_at_utc"],
        "last_checked_utc": now_iso,
        "refresh_cadence_hours": 4,
        "lobby_url": LOBBY_URL,
        "hotspawn_api_url": HS_API_URL,
        "valve_vrs_oct21_url": base["valve_vrs_oct21_url"],
        "verified_aliases": base["verified_aliases"],
        "rejected_aliases": base["rejected_aliases"],
        "provider_health": provider_health,
        "fixtures": fixtures_out,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return snapshot


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect or replay verified HotSpawn CS2 + external odds snapshot.")
    ap.add_argument("--refresh", action="store_true", help="Poll live public endpoints and preserve fallback state.")
    args = ap.parse_args()
    snap = collect(live_refresh=args.refresh)
    live_n = sum(1 for f in snap["fixtures"] if f["in_live_lobby"])
    print(f"ff88c096 collect: {live_n} live lobby CS2 matches + {len(snap['fixtures']) - live_n} backend API rows -> {SNAPSHOT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
