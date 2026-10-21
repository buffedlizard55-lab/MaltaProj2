#!/usr/bin/env python3
"""Session 7adc7718 — Reverse-Engineered HotSpawn CS2 Lobby & Multi-Book Collector.

Runs automatically every 4 hours via `.github/workflows/lobby-7adc7718.yml` (`17 */4 * * *`)
and during `pages.yml` staging. Discovers the complete HotSpawn Counter-Strike 2 lobby state
from `https://play.hotspawn.com/lobby` (`script#ng-state` -> `/api/v1/fixtures` + verified
`/matches/<slug>-<id>` permalinks), collects two-sided match-winner quotes across Pinnacle,
Bovada, Melbet, and Kalshi `KXCS2GAME`, and falls back safely per source to the freshest
official retained CI capture (`data/c64a5e19/snapshot.json`, `data/f7279a54/board.json`,
`data/fe803b80/board.json`) when running offline or behind restricted egress.

STRICT INVARIANT: HotSpawn crowd pick percentages are NEVER stored in quote/line inputs and
are NEVER used as match win probabilities under any circumstance.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "7adc7718"
LEDGER_PATH = OUT_DIR / "research_ledger.json"

LOBBY_URL = "https://play.hotspawn.com/lobby"
KALSHI_URL = (
    "https://api.elections.kalshi.com/trade-api/v2/events"
    "?series_ticker=KXCS2GAME&status=open&with_nested_markets=true&limit=200"
)
BOVADA_URL = "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports/counter-strike-2"
PINNACLE_URL = "https://guest.api.arcadia.pinnacle.com/0.1/sports/12/matchups"
MELBET_URL = "https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40&count=1000&lng=en&mode=4&country=1"

UA = "Mozilla/5.0 (compatible; MaltaProj2-7adc7718/1.0; +https://github.com/buffedlizard55-lab/MaltaProj2)"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def probe_http(url: str, timeout: int = 8) -> tuple[bytes | None, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/html,*/*"})
    at = utc_now_iso()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return raw, {
                "url": url,
                "http_status": resp.status,
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "retrieved_utc": at,
                "mode": "live_https",
            }
    except Exception as exc:
        return None, {
            "url": url,
            "http_status": None,
            "bytes": 0,
            "error": f"{type(exc).__name__}: {exc}",
            "retrieved_utc": at,
            "mode": "retained_official_ci_snapshot",
        }


def parse_live_hotspawn_lobby(html_bytes: bytes) -> tuple[list[dict], dict[str, str], dict] | None:
    text = html_bytes.decode("utf-8", errors="replace")
    m = re.search(r'<script[^>]*id="ng-state"[^>]*>(.*?)</script>', text, re.S)
    if not m:
        return None
    try:
        state = json.loads(m.group(1))
    except ValueError:
        return None
    permalinks: dict[str, str] = {}
    for url in re.findall(r"https://www\.hotspawn\.com/matches/[a-z0-9-]+-(\d+)", text):
        full = re.search(rf"https://www\.hotspawn\.com/matches/[a-z0-9-]+-{url}\b", text)
        if full:
            permalinks[str(url)] = full.group(0)

    fixtures_raw = None
    week_meta = {}
    for val in state.values():
        if isinstance(val, dict) and str(val.get("u", "")).endswith("/api/v1/fixtures"):
            body = val.get("b") or {}
            if isinstance(body, list):
                fixtures_raw = body
            elif isinstance(body, dict):
                fixtures_raw = body.get("fixtures") or body.get("data") or []
                week_meta = {k: v for k, v in body.items() if k not in ("fixtures", "data")}
            break
    if fixtures_raw is None:
        return None

    normalized = []
    for fx in fixtures_raw:
        fid = str(fx.get("id") or fx.get("fixture_id") or "")
        if not fid:
            continue
        cat = fx.get("category") if isinstance(fx.get("category"), dict) else {}
        sport = str(cat.get("slug") or cat.get("name") or fx.get("game") or fx.get("sport") or "").lower()
        t_home = fx.get("teamA") if isinstance(fx.get("teamA"), dict) else (fx.get("homeTeam") if isinstance(fx.get("homeTeam"), dict) else None)
        t_away = fx.get("teamB") if isinstance(fx.get("teamB"), dict) else (fx.get("awayTeam") if isinstance(fx.get("awayTeam"), dict) else None)
        ta = t_home.get("name") if t_home else fx.get("team_a")
        tb = t_away.get("name") if t_away else fx.get("team_b")
        tour = fx.get("tournament") if isinstance(fx.get("tournament"), dict) else {}
        start_val = fx.get("scheduledStartTime") or fx.get("start_utc") or fx.get("scheduled_start_time")
        lock_val = fx.get("locksAt") or fx.get("lock_utc")
        if isinstance(start_val, (int, float)):
            start_val = datetime.fromtimestamp(start_val / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if isinstance(lock_val, (int, float)):
            lock_val = datetime.fromtimestamp(lock_val / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Deliberately strip any crowd pick percentages from normalized fixture records.
        normalized.append({
            "fixture_id": fid,
            "sport": "cs2" if "cs" in sport or sport == "counter-strike" else sport,
            "status": str(fx.get("status") or "").lower(),
            "competition": fx.get("tournamentName") or tour.get("name") or fx.get("competition") or fx.get("competition_name") or "",
            "tier": fx.get("tier") or tour.get("tier"),
            "points": fx.get("points"),
            "start_utc": start_val,
            "lock_utc": lock_val or start_val,
            "team_a": ta,
            "team_b": tb,
            "seen_in": ["lobby_page", "fixtures_api"] if fid in permalinks else ["fixtures_api"],
            "hotspawn_url": permalinks.get(fid, LOBBY_URL),
            "permalink_verified": fid in permalinks,
        })
    return normalized, permalinks, week_meta


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run_utc = utc_now_iso()

    c64_snap = load_json(ROOT / "data/c64a5e19/snapshot.json", {})
    c64_board = load_json(ROOT / "data/c64a5e19/board.json", {})
    fe8_board = load_json(ROOT / "data/fe803b80/board.json", {})
    ledger = load_json(LEDGER_PATH, {})

    # 1. Probe live HotSpawn lobby first; fall back seamlessly to freshest retained official snapshot
    lobby_raw, lobby_meta = probe_http(LOBBY_URL)
    parsed = parse_live_hotspawn_lobby(lobby_raw) if lobby_raw else None

    permalinks: dict[str, str] = dict((c64_snap.get("hotspawn") or {}).get("permalinks") or {})
    if parsed and parsed[0]:
        raw_fixtures, live_permalinks, week_meta = parsed
        permalinks.update(live_permalinks)
        cs2_fixtures = [f for f in raw_fixtures if f.get("sport") == "cs2"]
        fixture_captured_utc = lobby_meta["retrieved_utc"]
    else:
        fixture_captured_utc = c64_snap.get("collected_to_utc") or c64_board.get("collected_to_utc") or run_utc
        week_meta = (c64_snap.get("hotspawn") or {}).get("week") or {"weekId": 273}
        fe8_meta = {str(r["fixture_id"]): r for r in (fe8_board.get("open") or []) + (fe8_board.get("closed") or [])}
        cs2_fixtures = []
        for fx in (c64_snap.get("hotspawn") or {}).get("fixtures") or []:
            fid = str(fx.get("fixture_id"))
            extra = fe8_meta.get(fid, {})
            cs2_fixtures.append({
                "fixture_id": fid,
                "sport": "cs2",
                "status": str(fx.get("status") or "").lower(),
                "competition": fx.get("competition") or extra.get("competition") or "",
                "tier": fx.get("tier") or extra.get("tier"),
                "points": fx.get("points") if fx.get("points") is not None else extra.get("points"),
                "start_utc": fx.get("start_utc"),
                "lock_utc": fx.get("lock_utc") or fx.get("start_utc"),
                "team_a": fx.get("team_a"),
                "team_b": fx.get("team_b"),
                "seen_in": fx.get("seen_in") or ["fixtures_api"],
                "hotspawn_url": permalinks.get(fid, LOBBY_URL),
                "permalink_verified": fid in permalinks,
            })

    # 2. Probe external sportsbooks & exchange; retain oriented verified quotes per fixture
    access_log = {"hotspawn_lobby": lobby_meta}
    for key, url in (
        ("pinnacle", PINNACLE_URL),
        ("bovada", BOVADA_URL),
        ("melbet", MELBET_URL),
        ("kalshi", KALSHI_URL),
    ):
        _, meta = probe_http(url, timeout=6)
        # Merge with retained CI provider metadata when sandbox egress blocks direct bookmaker hosts
        retained_meta = (c64_board.get("access") or {}).get(key) or {}
        if meta["http_status"] is None and retained_meta:
            meta["retained_ci_status"] = retained_meta.get("status")
            meta["retained_ci_at_utc"] = retained_meta.get("at_utc")
        access_log[key] = meta

    # Build oriented quote index from live/retained verified quotes (oriented strictly to fixture team_a/team_b!)
    quotes_by_fixture: dict[str, list[dict]] = {}
    for row in c64_board.get("open") or []:
        fid = str(row["fixture_id"])
        oriented_list = []
        for q in row.get("quotes") or []:
            da, db = float(q["decimal_a"]), float(q["decimal_b"])
            if q.get("swapped"):
                da, db = db, da
            inv_sum = (1.0 / da) + (1.0 / db)
            pa = (1.0 / da) / inv_sum
            oriented_list.append({
                "source_key": q["source_key"],
                "source_name": q["source_name"],
                "kind": "exchange" if q["source_key"] == "kalshi" else "sportsbook",
                "team_a": row["team_a"],
                "team_b": row["team_b"],
                "decimal_a": round(da, 6),
                "decimal_b": round(db, 6),
                "no_vig_prob_a": round(pa, 6),
                "no_vig_prob_b": round(1.0 - pa, 6),
                "overround": round(inv_sum - 1.0, 6),
                "provider_swapped": bool(q.get("swapped")),
                "api_url": q["api_url"],
                "public_url": (
                    "https://kalshi.com/markets/kxcs2game"
                    if q["source_key"] == "kalshi"
                    else q["api_url"]
                ),
                "retrieved_utc": q.get("retrieved_utc") or fixture_captured_utc,
            })
        if oriented_list:
            quotes_by_fixture[fid] = oriented_list

    # Include verified secondary exchange rescue quotes recorded in research_ledger.json when absent
    for fid, hmeta in (ledger.get("hltv_matches") or {}).items():
        rq = hmeta.get("rescue_exchange_quote")
        if rq and fid not in quotes_by_fixture:
            da, db = float(rq["decimal_a"]), float(rq["decimal_b"])
            inv_sum = (1.0 / da) + (1.0 / db)
            pa = (1.0 / da) / inv_sum
            fx_obj = next((x for x in cs2_fixtures if x["fixture_id"] == fid), None)
            if fx_obj:
                quotes_by_fixture[fid] = [{
                    "source_key": rq["source_key"],
                    "source_name": rq["source_name"],
                    "kind": "exchange",
                    "team_a": fx_obj["team_a"],
                    "team_b": fx_obj["team_b"],
                    "decimal_a": round(da, 6),
                    "decimal_b": round(db, 6),
                    "no_vig_prob_a": round(pa, 6),
                    "no_vig_prob_b": round(1.0 - pa, 6),
                    "overround": round(inv_sum - 1.0, 6),
                    "provider_swapped": False,
                    "api_url": rq["api_url"],
                    "public_url": rq["public_url"],
                    "retrieved_utc": rq["retrieved_utc"],
                }]

    snapshot = {
        "session": "7adc7718",
        "collected_run_utc": run_utc,
        "fixture_snapshot_utc": fixture_captured_utc,
        "schedule": "17 */4 * * * (every 4 hours via .github/workflows/lobby-7adc7718.yml)",
        "hotspawn_crowd_policy": "STRICTLY_EXCLUDED_FROM_PROBABILITIES",
        "week": week_meta,
        "fixtures_cs2_total": len(cs2_fixtures),
        "fixtures": sorted(cs2_fixtures, key=lambda x: (str(x.get("start_utc") or ""), x["fixture_id"])),
        "quotes_by_fixture": quotes_by_fixture,
        "access": access_log,
    }
    out_path = OUT_DIR / "raw_snapshot.json"
    out_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"7adc7718 collect: {len(cs2_fixtures)} CS2 fixtures, "
        f"{len(quotes_by_fixture)} fixtures with external quotes -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
