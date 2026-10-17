#!/usr/bin/env python3
"""Session 17866d06 — fresh evidence collector (runs where source access exists).

Writes raw and normalised evidence under ``data/17866d06/``. Nothing is derived
here beyond parsing and a strict, documented join: every probability is computed
later by ``model.py`` from the quotes this file retains, so a published number can
always be replayed from stored evidence.

Sources (all external to HotSpawn for prices):
  fixtures ...... HotSpawn fixtures API  (fixture spine, points, ownership, settlement)
  thunderpick ... bo3.gg public API      (publishes Thunderpick's coefficients per fixture)
  melbet ........ Melbet public LineFeed (bookmaker decimal odds, esports sport id 40)
  polymarket .... Polymarket gamma API   (CFTC-regulated exchange prices, volume, liquidity)
  vrs ........... Valve's official regional standings repository (model input)

Usage:
    python scripts/17866d06/collect.py            # capture, normalise, join, verify
    python scripts/17866d06/collect.py --check    # verify the committed capture only
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "17866d06"
EVIDENCE = DATA / "evidence"

HOTSPAWN_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
TWC_COMPETITION_ID = "35859"          # Thunderpick World Championship 2026 (Malta), verified this session
BO3_API = "https://api.bo3.gg/api/v1/matches/"
MELBET_FEED = ("https://melbet.com/service-api/LineFeed/Get1x2_VZip"
               "?sports=40&count=1000&lng=en&mode=4&country=1")
POLY_EVENTS = ("https://gamma-api.polymarket.com/events"
               "?closed=false&limit=200&tag_slug=cs2&order=startDate&ascending=false")
POLY_TWC_SLUGS = ["cs2-furia-aur1-2026-10-17", "cs2-fal2-bb3-2026-10-17"]
VRS_REGIONS = ("global", "americas", "asia", "europe")
VRS_API = ("https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings"
           "/contents/live/2026/standings_{region}_{snapshot}.md")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36 malta-proj2-research/17866d06")
JOIN_WINDOW_SEC = 5400          # a quote must start within 90 minutes of the fixture
LOCK_OFFSET_SEC = 360           # verified against HotSpawn rows: lock = start - 360 s


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ms_to_utc(ms) -> str:
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_to_epoch(value: str):
    """Parse an ISO-8601 instant into unix seconds. Naive stamps are read as UTC."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00").replace(" ", "T")
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.timestamp()


def get(url: str, timeout: int = 90, headers=None, retries: int = 3):
    hdrs = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    if headers:
        hdrs.update(headers)
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                return {"status": resp.status, "body": body, "url": url,
                        "read_utc": now_utc(), "attempt": attempt,
                        "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        except Exception as exc:                          # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(2 * attempt)
    return {"status": 0, "body": b"", "url": url, "read_utc": now_utc(),
            "attempt": retries, "bytes": 0, "sha256": None, "error": last}


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# --------------------------------------------------------------------- HotSpawn
def collect_hotspawn(log: dict):
    meta = {"url_all": f"{HOTSPAWN_API}?sport_alias=cs2&status=scheduled",
            "url_twc": f"{HOTSPAWN_API}?sport_alias=cs2&competition_id={TWC_COMPETITION_ID}",
            "url_twc_scheduled": f"{HOTSPAWN_API}?sport_alias=cs2&status=scheduled&competition_id={TWC_COMPETITION_ID}"}
    raw_all = get(meta["url_all"])
    raw_twc = get(meta["url_twc"])
    raw_twc_sched = get(meta["url_twc_scheduled"])
    for key, res in (("all_scheduled", raw_all), ("twc_all_statuses", raw_twc), ("twc_scheduled", raw_twc_sched)):
        meta[key] = {k: v for k, v in res.items() if k != "body"}
        if res["status"] == 200 and res["body"]:
            (EVIDENCE / f"hotspawn_{key}.json").write_bytes(res["body"])
            try:
                meta[key]["rows"] = len(json.loads(res["body"].decode("utf-8", "replace")))
            except ValueError as exc:
                meta[key]["parse_error"] = str(exc)
    log["hotspawn"] = meta
    if raw_all["status"] != 200:
        raise SystemExit(f"HotSpawn fixtures API unreachable: {raw_all.get('error')}")
    rows = json.loads(raw_all["body"].decode("utf-8", "replace"))
    twc_rows = []
    if raw_twc["status"] == 200 and raw_twc["body"]:
        twc_rows = json.loads(raw_twc["body"].decode("utf-8", "replace"))
    return rows, twc_rows


def open_fixtures(rows, captured_epoch: float):
    """Keep only fixtures that have not started yet (HotSpawn's scheduled filter is
    known to retain past-dated rows; verified by earlier sessions and re-checked here)."""
    kept, dropped = [], []
    for row in rows:
        start = row.get("scheduled_start_time")
        if start is None:
            dropped.append({"id": row.get("id"), "reason": "no scheduled_start_time"})
            continue
        start_epoch = int(start) / 1000
        if start_epoch < captured_epoch - 3600:
            dropped.append({"id": row.get("id"), "start_utc": ms_to_utc(start),
                            "competition": row.get("competition_name"),
                            "reason": "past_start_still_marked_scheduled"})
            continue
        kept.append({
            "fixture_id": str(row.get("id")),
            "competition": row.get("competition_name"),
            "competition_id": str(row.get("competition_id")),
            "sport": row.get("sport_alias"),
            "status": row.get("status"),
            "tier": (row.get("tier") or "").upper(),
            "stage": row.get("stage"),
            "offered_points": row.get("offered_points"),
            "base_points": row.get("base_points"),
            "points_breakdown": row.get("points_breakdown"),
            "best_of": row.get("best_of"),
            "start_utc": ms_to_utc(start),
            "start_epoch": start_epoch,
            "lock_utc": ms_to_utc(row["lock_time"]) if row.get("lock_time") else None,
            "lock_offset_sec": row.get("lock_offset_sec", LOCK_OFFSET_SEC),
            "team_a": row.get("participants0_name"),
            "team_b": row.get("participants1_name"),
            "participant_a_id": row.get("participants0_id"),
            "participant_b_id": row.get("participants1_id"),
            "crowd_a": row.get("participants0_picked_percent"),
            "crowd_b": row.get("participants1_picked_percent"),
            "total_picks": row.get("total_picks"),
            "hotspawn_public_url": "https://play.hotspawn.com/lobby",
            "hotspawn_api_url": (f"{HOTSPAWN_API}?sport_alias=cs2&status=scheduled"
                                 f"&competition_id={row.get('competition_id')}"),
        })
    kept.sort(key=lambda r: (r["start_epoch"], r["fixture_id"]))
    return kept, dropped


def twc_settlement(rows):
    out = []
    for row in rows:
        out.append({
            "fixture_id": str(row.get("id")),
            "status": row.get("status"),
            "start_utc": ms_to_utc(row["scheduled_start_time"]) if row.get("scheduled_start_time") else None,
            "tier": (row.get("tier") or "").upper(),
            "offered_points": row.get("offered_points"),
            "base_points": row.get("base_points"),
            "points_breakdown": row.get("points_breakdown"),
            "team_a": row.get("participants0_name"),
            "team_b": row.get("participants1_name"),
            "score_a": row.get("participants0_score"),
            "score_b": row.get("participants1_score"),
            "crowd_a": row.get("participants0_picked_percent"),
            "crowd_b": row.get("participants1_picked_percent"),
            "total_picks": row.get("total_picks"),
        })
    return out


# ----------------------------------------------------------------------- bo3.gg
def collect_bo3(log: dict):
    quotes, meta = [], {"pages": [], "matches_seen": 0, "thunderpick_rows": 0}
    for offset in (0, 100, 200, 300):
        url = (BO3_API + "?filter%5Bmatches.discipline_id%5D%5Beq%5D=1"
               "&filter%5Bmatches.status%5D%5Bin%5D=upcoming&sort=start_date"
               f"&page%5Blimit%5D=100&page%5Boffset%5D={offset}")
        res = get(url)
        entry = {k: v for k, v in res.items() if k != "body"}
        if res["status"] == 200 and res["body"]:
            try:
                payload = json.loads(res["body"].decode("utf-8", "replace"))
            except ValueError as exc:
                entry["parse_error"] = str(exc)
                meta["pages"].append(entry)
                continue
            results = payload.get("results") or []
            entry["rows"] = len(results)
            entry["total_count"] = (payload.get("total") or {}).get("count")
            meta["matches_seen"] += len(results)
            # Retain the fields this desk actually uses, plus the digest of the full body, so the
            # capture stays auditable without committing megabytes of unrelated match metadata.
            trimmed = [{"id": m.get("id"), "slug": m.get("slug"), "discipline_id": m.get("discipline_id"),
                        "start_date": m.get("start_date"), "tier": m.get("tier"),
                        "tournament_id": m.get("tournament_id"), "status": m.get("status"),
                        "team1_id": m.get("team1_id"), "team2_id": m.get("team2_id"),
                        "bet_updates": m.get("bet_updates")} for m in results]
            write_json(EVIDENCE / f"bo3gg_upcoming_offset{offset}.json",
                       {"source_url": url, "retrieved_utc": res["read_utc"], "raw_bytes": res["bytes"],
                        "raw_sha256": res["sha256"], "results": trimmed})
            for match in results:
                bet = match.get("bet_updates") or {}
                if bet.get("provider") != "thunderpick":
                    continue
                t1, t2 = bet.get("team_1") or {}, bet.get("team_2") or {}
                if not t1.get("coeff") or not t2.get("coeff"):
                    continue
                start = iso_to_epoch((match.get("start_date") or "").replace("+00:00", "Z"))
                meta["thunderpick_rows"] += 1
                quotes.append({
                    "source_key": "thunderpick",
                    "book": "Thunderpick (coefficients as published by bo3.gg)",
                    "team_a": t1.get("name"),
                    "team_b": t2.get("name"),
                    "decimal_a": float(t1["coeff"]),
                    "decimal_b": float(t2["coeff"]),
                    "start_epoch": start,
                    "start_utc": (match.get("start_date") or "")[:19] + "Z" if match.get("start_date") else None,
                    "public_url": bet.get("path"),
                    "evidence_url": url,
                    "tier": match.get("tier"),
                    "bo3_match_id": match.get("id"),
                    "bo3_slug": match.get("slug"),
                    "retrieved_utc": res["read_utc"],
                })
        meta["pages"].append(entry)
        if offset and res["status"] != 200:
            break
    log["bo3gg"] = meta
    return quotes


# ------------------------------------------------------------------------ Melbet
def collect_melbet(log: dict):
    res = get(MELBET_FEED, timeout=120)
    meta = {k: v for k, v in res.items() if k != "body"}
    quotes = []
    if res["status"] == 200 and res["body"]:
        try:
            payload = json.loads(res["body"].decode("utf-8", "replace"))
        except ValueError as exc:
            meta["parse_error"] = str(exc)
            log["melbet"] = meta
            return quotes
        values = payload.get("Value") or []
        meta["rows_total"] = len(values)
        kept = []
        for row in values:
            league = str(row.get("L") or "") + "|" + str(row.get("SSN") or "") + "|" + str(row.get("SN") or "")
            if "CS 2" not in league and row.get("SI") != 40:
                continue
            if "CS 2" not in league:
                continue
            odds = {}
            for entry in row.get("E") or []:
                if entry.get("T") in (1, 2, 3) and entry.get("C"):
                    odds[int(entry["T"])] = float(entry["C"])
            if 1 not in odds or 3 not in odds:
                continue
            kept.append({"id": row.get("I"), "league": row.get("LE") or row.get("L"),
                         "o1": row.get("O1E") or row.get("O1"), "o2": row.get("O2E") or row.get("O2"),
                         "start_epoch": row.get("S"), "w1": odds[1], "draw": odds.get(2), "w2": odds[3],
                         "stage": (row.get("MIO") or {}).get("TSt")})
            quotes.append({
                "source_key": "melbet",
                "book": "Melbet (public LineFeed, esports)",
                "team_a": row.get("O1E") or row.get("O1"),
                "team_b": row.get("O2E") or row.get("O2"),
                "decimal_a": odds[1],
                "decimal_b": odds[3],
                "draw_decimal": odds.get(2),
                "start_epoch": row.get("S"),
                "start_utc": ms_to_utc(int(row["S"]) * 1000) if row.get("S") else None,
                "league": row.get("LE") or row.get("L"),
                "stage": (row.get("MIO") or {}).get("TSt"),
                "public_url": "https://melbet.com/en/line/esports",
                "evidence_url": MELBET_FEED,
                "feed_row_id": row.get("I"),
                "retrieved_utc": res["read_utc"],
            })
        meta["cs2_rows"] = len(kept)
        meta["raw_bytes"] = res["bytes"]
        meta["raw_sha256"] = res["sha256"]
        write_json(EVIDENCE / "melbet_cs2_rows.json", kept)
    log["melbet"] = meta
    return quotes


# -------------------------------------------------------------------- Polymarket
def _poly_market(event, market, url, read_utc):
    try:
        outcomes = json.loads(market.get("outcomes") or "[]")
        prices = [float(p) for p in json.loads(market.get("outcomePrices") or "[]")]
    except (ValueError, TypeError):
        return None
    if len(outcomes) != 2 or len(prices) != 2:
        return None
    start = market.get("gameStartTime") or market.get("eventStartTime") or event.get("startDate")
    start_epoch = iso_to_epoch(start)
    slug = event.get("slug") or market.get("slug")
    return {
        "source_key": "polymarket",
        "book": "Polymarket (CFTC-regulated prediction exchange)",
        "team_a": outcomes[0],
        "team_b": outcomes[1],
        "price_a": prices[0],
        "price_b": prices[1],
        "decimal_a": round(1 / prices[0], 4) if prices[0] else None,
        "decimal_b": round(1 / prices[1], 4) if prices[1] else None,
        "start_epoch": start_epoch,
        "start_utc": start,
        "market_slug": market.get("slug"),
        "event_slug": slug,
        "group_item": market.get("groupItemTitle"),
        "volume_usd": market.get("volumeNum") or market.get("volume"),
        "liquidity_usd": market.get("liquidityNum") or market.get("liquidity"),
        "best_bid": market.get("bestBid"),
        "best_ask": market.get("bestAsk"),
        "spread": market.get("spread"),
        "market_updated_utc": (market.get("updatedAt") or "").replace("T", " ").split(".")[0] + "Z" if market.get("updatedAt") else None,
        "public_url": f"https://polymarket.com/event/{slug}",
        "evidence_url": url,
        "retrieved_utc": read_utc,
    }


def collect_polymarket(log: dict):
    quotes, meta = [], {"pages": [], "markets_kept": 0}
    urls = [POLY_EVENTS] + [f"https://gamma-api.polymarket.com/markets?slug={s}" for s in POLY_TWC_SLUGS]
    for url in urls:
        res = get(url, timeout=120)
        entry = {k: v for k, v in res.items() if k != "body"}
        if res["status"] == 200 and res["body"]:
            try:
                payload = json.loads(res["body"].decode("utf-8", "replace"))
            except ValueError as exc:
                entry["parse_error"] = str(exc)
                meta["pages"].append(entry)
                continue
            name = "polymarket_twc_slugs.json" if "slug=" in url else "polymarket_cs2_events.json"
            events = payload if isinstance(payload, list) and payload and "markets" in (payload[0] or {}) else []
            if isinstance(payload, list) and payload and "question" in (payload[0] or {}):
                # /markets response: wrap each market as a pseudo-event
                events = [{"slug": m.get("slug"), "title": m.get("question"), "markets": [m]} for m in payload]
            retained = []
            for event in events or []:
                kept_markets = []
                for market in event.get("markets") or []:
                    group = (market.get("groupItemTitle") or "").lower()
                    slug = market.get("slug") or ""
                    is_series = group in ("", "match winner", "winner") or slug == (event.get("slug") or "")
                    if not is_series or "-game" in slug:
                        continue
                    row = _poly_market(event, market, url, res["read_utc"])
                    if row:
                        quotes.append(row)
                        meta["markets_kept"] += 1
                        kept_markets.append({k: market.get(k) for k in
                                             ("id", "question", "slug", "groupItemTitle", "outcomes",
                                              "outcomePrices", "volumeNum", "liquidityNum", "bestBid",
                                              "bestAsk", "spread", "updatedAt", "gameStartTime",
                                              "eventStartTime", "resolutionSource", "closed")})
                if kept_markets:
                    retained.append({"slug": event.get("slug"), "title": event.get("title"),
                                     "startDate": event.get("startDate"), "closed": event.get("closed"),
                                     "markets": kept_markets})
            write_json(EVIDENCE / name, {"source_url": url, "retrieved_utc": res["read_utc"],
                                         "raw_bytes": res["bytes"], "raw_sha256": res["sha256"],
                                         "events_with_series_markets": retained})
            entry["events"] = len(events or [])
        meta["pages"].append(entry)
    log["polymarket"] = meta
    return quotes


# --------------------------------------------------------------------- Valve VRS
def collect_vrs(log: dict):
    standings, meta = {}, {"regions": {}}
    listing = get("https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings/contents/live/2026")
    snapshot = None
    if listing["status"] == 200 and listing["body"]:
        names = [r["name"] for r in json.loads(listing["body"].decode("utf-8", "replace"))
                 if isinstance(r, dict) and str(r.get("name", "")).startswith("standings_global_")]
        if names:
            snapshot = sorted(names)[-1].replace("standings_global_", "").replace(".md", "")
    meta["snapshot"] = snapshot
    meta["listing_read_utc"] = listing["read_utc"]
    if not snapshot:
        meta["error"] = listing.get("error") or "no standings_global_*.md found"
        log["vrs"] = meta
        return standings, meta
    for region in VRS_REGIONS:
        url = VRS_API.format(region=region, snapshot=snapshot)
        res = get(url, headers={"Accept": "application/vnd.github.raw"})
        entry = {k: v for k, v in res.items() if k != "body"}
        rows = {}
        if res["status"] == 200 and res["body"]:
            text = res["body"].decode("utf-8", "replace")
            (EVIDENCE / f"vrs_{region}_{snapshot}.md").write_text(text, encoding="utf-8")
            for line in text.splitlines():
                if not line.startswith("|"):
                    continue
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) < 4 or not cells[0].isdigit():
                    continue
                try:
                    rows[cells[2]] = {"standing": int(cells[0]), "points": int(cells[1]), "roster": cells[3]}
                except ValueError:
                    continue
            entry["teams"] = len(rows)
            entry["header"] = text.splitlines()[0][:80] if text else None
        standings[region] = rows
        meta["regions"][region] = entry
    log["vrs"] = meta
    return standings, meta


# ------------------------------------------------------------------ normalising
def norm(name) -> str:
    if not name:
        return ""
    text = "".join(ch if ch.isalnum() else " " for ch in str(name).lower())
    return "".join(text.split())


_ALIASES = None


def aliases() -> dict:
    """Verified team-name aliases, loaded from research.py (single source of truth)."""
    global _ALIASES
    if _ALIASES is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("research_17866d06_collect",
                                                      Path(__file__).resolve().parent / "research.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _ALIASES = getattr(module, "ALIASES", {})
    return _ALIASES


def _side_match(fixture_name, quote_name) -> str:
    """Compare two team names as published by different sources.

    'exact' and 'substring' are the same tests the standings lookup uses; 'alias' means the
    two strings differ but research.py carries evidence that they are the same team.
    """
    fn, qn = norm(fixture_name), norm(quote_name)
    if not fn or not qn:
        return "missing"
    if fn == qn:
        return "exact"
    table = aliases()
    if table.get(fn, (fn,))[0] and norm(table.get(fn, (fn,))[0]) == norm(table.get(qn, (qn,))[0]):
        return "alias"
    if fn in qn or qn in fn:
        return "substring"
    return "none"


def join_quotes(fixtures, quotes, captured_utc):
    """Strict join: start within JOIN_WINDOW_SEC and at least one side matching, with
    the other side not contradicting. Every rejection is retained for the ledger."""
    joined, rejected = [], []
    for quote in quotes:
        if not quote.get("start_epoch"):
            rejected.append({**{k: quote.get(k) for k in ("source_key", "team_a", "team_b", "public_url")},
                             "reason": "quote has no usable start time"})
            continue
        best, best_delta = None, None
        for fix in fixtures:
            delta = abs(quote["start_epoch"] - fix["start_epoch"])
            if delta > JOIN_WINDOW_SEC:
                continue
            a = _side_match(fix["team_a"], quote["team_a"])
            b = _side_match(fix["team_b"], quote["team_b"])
            swapped = a == "none" and b == "none"
            if swapped:
                a2 = _side_match(fix["team_a"], quote["team_b"])
                b2 = _side_match(fix["team_b"], quote["team_a"])
                if a2 != "none" and b2 != "none":
                    a, b, swapped = a2, b2, True
            if a == "none" or b == "none":
                continue
            score = (0 if a == "exact" else 1) + (0 if b == "exact" else 1)
            if best is None or (delta, score) < (best_delta, best["_score"]):
                best = {"fixture_id": fix["fixture_id"], "_score": score,
                        "side_a_match": a, "side_b_match": b, "swapped": swapped,
                        "start_delta_sec": int(delta)}
                best_delta = delta
        if best is None:
            rejected.append({**{k: quote.get(k) for k in ("source_key", "team_a", "team_b", "start_utc", "public_url")},
                             "reason": f"no HotSpawn fixture within {JOIN_WINDOW_SEC}s matched both sides"})
            continue
        literal = {"exact", "substring"}
        if best["side_a_match"] in literal and best["side_b_match"] in literal and best["start_delta_sec"] <= 900:
            confidence = "exact"
        elif best["side_a_match"] != "none" and best["side_b_match"] != "none" and "alias" in (
                best["side_a_match"], best["side_b_match"]) and best["start_delta_sec"] <= 900:
            # the two sources spell the team differently and research.py carries the evidence that
            # they are the same team; labelled separately so a reader can see the name was mapped
            confidence = "alias"
        else:
            confidence = "partial"
        joined.append({**quote, "fixture_id": best["fixture_id"], "join": {
            "side_a_match": best["side_a_match"], "side_b_match": best["side_b_match"],
            "swapped": best["swapped"], "start_delta_sec": best["start_delta_sec"],
            "confidence": confidence}})
    return joined, rejected


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    DATA.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    captured_utc = now_utc()
    captured_epoch = datetime.now(timezone.utc).timestamp()
    log = {"session": "17866d06", "captured_utc": captured_utc, "join_window_sec": JOIN_WINDOW_SEC}

    if "--check" in argv:
        fixtures = json.loads((DATA / "fixtures.json").read_text())["open"]
        quotes = json.loads((DATA / "quotes.json").read_text())["joined"]
        print(f"check: {len(fixtures)} open fixtures, {len(quotes)} joined quotes")
        return 0

    only = next((a.split("=", 1)[1] for a in argv if a.startswith("--only=")), None)
    if only == "vrs":
        # Standalone Valve-standings capture: reachable from any environment that can read
        # api.github.com, so the model input can be refreshed even if the book feeds are blocked.
        vrs, vrs_meta = collect_vrs(log)
        existing = json.loads((DATA / "collect_log.json").read_text()) if (DATA / "collect_log.json").exists() else {}
        prior_capture = existing.get("captured_utc")
        existing.update(log)
        if prior_capture:
            existing["captured_utc"] = prior_capture   # fixtures were captured then, not now
        existing["vrs_only_refresh_utc"] = captured_utc
        write_json(DATA / "vrs.json", {"snapshot": vrs_meta.get("snapshot"), "captured_utc": captured_utc,
                                       "source": "https://github.com/ValveSoftware/counter-strike_regional_standings",
                                       "standings": vrs})
        write_json(DATA / "collect_log.json", existing)
        print(f"vrs snapshot {vrs_meta.get('snapshot')}: "
              + ", ".join(f"{r}={len(v)}" for r, v in sorted(vrs.items())))
        return 0

    hs_rows, twc_rows = collect_hotspawn(log)
    fixtures, dropped = open_fixtures(hs_rows, captured_epoch)
    bo3 = collect_bo3(log)
    melbet = collect_melbet(log)
    poly = collect_polymarket(log)
    vrs, vrs_meta = collect_vrs(log)

    all_quotes = bo3 + melbet + poly
    joined, rejected = join_quotes(fixtures, all_quotes, captured_utc)
    joined_ids = {id(q) for q in joined}
    # Quotes that did not join still carry two team names and a market price: they are the
    # calibration sample for the originated VRS scale (fitted on markets, not on HotSpawn).
    unjoined = [{k: q.get(k) for k in ("source_key", "team_a", "team_b", "decimal_a", "decimal_b",
                                      "price_a", "price_b", "volume_usd", "start_utc", "public_url")}
                for q in all_quotes if id(q) not in joined_ids]

    write_json(DATA / "fixtures.json", {"captured_utc": captured_utc, "source": log["hotspawn"]["url_all"],
                                        "open": fixtures, "dropped_stale": dropped,
                                        "twc_competition_id": TWC_COMPETITION_ID,
                                        "twc_settlement": twc_settlement(twc_rows)})
    write_json(DATA / "quotes.json", {"captured_utc": captured_utc, "joined": joined, "rejected": rejected,
                                      "unjoined_for_calibration": unjoined,
                                      "counts": {"thunderpick": len(bo3), "melbet": len(melbet),
                                                 "polymarket": len(poly),
                                                 "joined": len(joined), "unjoined": len(unjoined)}})
    write_json(DATA / "vrs.json", {"snapshot": vrs_meta.get("snapshot"), "captured_utc": captured_utc,
                                   "source": "https://github.com/ValveSoftware/counter-strike_regional_standings",
                                   "standings": vrs})
    write_json(DATA / "collect_log.json", log)
    print(f"captured {captured_utc}: {len(fixtures)} open CS2 fixtures, {len(joined)} joined quotes "
          f"({len(rejected)} rejected), VRS snapshot {vrs_meta.get('snapshot')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
