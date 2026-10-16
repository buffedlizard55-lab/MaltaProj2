#!/usr/bin/env python3
"""Collect the hub's own source capture (session 7c2622db).

Runs on a GitHub-hosted runner, where the public sources are reachable. Three outputs,
all inside this session's own data directory (no other session's file is read or written):

  * ``snapshot.json``        - the shared collector's capture: lobby inventory, bookmaker
                               prices, the CFTC-regulated exchange series, the official
                               Valve ratings, and a per-source access log.
  * ``lobby_state.json``     - the exact public lobby transfer state as published, which is
                               the only place the crowd pick shares appear. Crowd shares are
                               ownership, never a probability input.
  * ``exchange.json``        - this hub's own exchange markets (see exchange_markets.json),
                               re-fetched live with both sides of the book and the gate result.

No authenticated API, no access-control bypass, no price is ever inferred.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shared  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "7c2622db"
UA = ("MaltaProj2-picks-hub/1.0 (+https://github.com/buffedlizard55-lab/MaltaProj2)")
MAX_BYTES = 2_000_000


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_raw(url: str, headers: dict | None = None, timeout: int = 45):
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json",
                                                  **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                return None, {"status": response.status, "error": "payload over safety limit",
                              "at_utc": iso_now()}
            return body, {"status": response.status, "bytes": len(body),
                          "date": response.headers.get("Date"), "age": response.headers.get("Age"),
                          "at_utc": iso_now()}
    except urllib.error.HTTPError as exc:
        return None, {"status": exc.code, "error": f"HTTP {exc.code}", "at_utc": iso_now()}
    except Exception as exc:  # noqa: BLE001
        return None, {"status": None, "error": f"{type(exc).__name__}: {exc}"[:200],
                      "at_utc": iso_now()}


# ------------------------------------------------------------------ shared collector pass
def run_shared_collector() -> dict:
    """Collect lobby inventory, bookmaker prices and official ratings with the shared engine."""
    try:
        collector = shared.collector()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    collector.OUT = OUT
    lobby_page = collector.LOBBY_PAGE
    evidence = {"lobby": None}
    original_fetch = collector.fetch

    def retaining_fetch(url, headers=None, timeout=45):
        body, meta = original_fetch(url, headers, timeout)
        if url == lobby_page and body:
            state = shared.core().lobby_state(body.decode("utf-8", "replace"))
            if state.get("fixtures"):
                evidence["lobby"] = {"url": url, "metadata": meta, "transfer_state": state}
        return body, meta

    collector.fetch = retaining_fetch
    try:
        collector.main()
        ok = True
        error = None
    except Exception as exc:  # noqa: BLE001
        ok, error = False, f"{type(exc).__name__}: {exc}"[:300]
    if evidence["lobby"]:
        (OUT / "lobby_state.json").write_text(json.dumps(evidence["lobby"], indent=1,
                                                         ensure_ascii=False) + "\n")
    return {"ok": ok, "error": error, "lobby_state_retained": bool(evidence["lobby"])}


# ------------------------------------------------------------------------- exchange pass
def normalise_exchange(seed: dict, payload: dict, fixture: dict | None, retrieved_utc: str) -> dict:
    """One seeded exchange market -> publishable reading with the gate result spelled out."""
    outcomes = payload.get("outcomes")
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except ValueError:
            outcomes = None
    if not isinstance(outcomes, list):
        outcomes = list(seed.get("outcomes") or [])
    row = {
        "fixture_id": seed.get("fixture_id"),
        "market_slug": payload.get("slug") or seed.get("market_slug"),
        "question": payload.get("question"),
        "outcomes": outcomes,
        "market_url": seed.get("market_url"),
        "api_url": seed.get("api_url") or
        f"https://gamma-api.polymarket.com/markets?slug={seed.get('market_slug')}",
        "resolution_source": seed.get("resolution_source"),
        "retrieved_utc": retrieved_utc,
        "updated_at": payload.get("updatedAt"),
        "game_start_time": payload.get("gameStartTime"),
        "closed": payload.get("closed"),
        "accepting_orders": payload.get("acceptingOrders"),
        "best_bid": payload.get("bestBid"),
        "best_ask": payload.get("bestAsk"),
        "spread": payload.get("spread"),
        "last_trade": payload.get("lastTradePrice"),
        "volume": payload.get("volumeNum") if payload.get("volumeNum") is not None else payload.get("volume"),
        "liquidity": payload.get("liquidityNum") if payload.get("liquidityNum") is not None else payload.get("liquidity"),
        "tick_size": payload.get("orderPriceMinTickSize"),
        "min_order_size": payload.get("orderMinSize"),
        "outcome_prices": payload.get("outcomePrices"),
    }
    checks: dict[str, dict] = {}

    def check(name, ok, detail):
        checks[name] = {"pass": bool(ok), "detail": detail}

    bid, ask = row["best_bid"], row["best_ask"]
    spread_ok = (isinstance(bid, (int, float)) and isinstance(ask, (int, float))
                 and 0.0 < float(bid) <= float(ask) < 1.0 and (float(ask) - float(bid)) <= 0.10)
    check("two_sided_book_within_10c", spread_ok, f"bestBid={bid} bestAsk={ask}")
    check("accepting_orders", bool(row["accepting_orders"]) and not bool(row["closed"]),
          f"acceptingOrders={row['accepting_orders']} closed={row['closed']}")
    start_ok = False
    if fixture and row["game_start_time"]:
        try:
            market_start = datetime.fromisoformat(str(row["game_start_time"]).replace(" ", "T")
                                                  .replace("+00", "+00:00"))
            if market_start.tzinfo is None:
                market_start = market_start.replace(tzinfo=timezone.utc)
            fixture_start = datetime.strptime(fixture["start_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc)
            start_ok = abs((market_start - fixture_start).total_seconds()) <= 300
            detail = f"market {market_start.isoformat()} vs fixture {fixture['start_utc']}"
        except Exception:  # noqa: BLE001
            detail = "unparseable start"
    else:
        detail = "no fixture start or no market start"
    check("kickoff_agreement_within_5min", start_ok, detail)
    identity_ok = (fixture is not None and len(outcomes) == 2
                   and {shared.core().norm(o) for o in outcomes}
                   == {shared.core().norm(fixture["team_a"]), shared.core().norm(fixture["team_b"])})
    check("outcome_identity_matches_fixture", identity_ok,
          f"outcomes={outcomes} fixture={(fixture or {}).get('team_a')}/{(fixture or {}).get('team_b')}")
    if spread_ok:
        mid = (float(bid) + float(ask)) / 2.0
        row["prob_mid"] = {outcomes[0] if outcomes else "a": mid,
                           outcomes[1] if len(outcomes) > 1 else "b": 1.0 - mid}
        row["prob_mid_note"] = ("midpoint of the live bid/ask book on outcome 1; outcome 2 is its "
                               "complement. An estimate, not an executable price.")
    else:
        row["prob_mid"] = None
        row["prob_mid_note"] = "book missing, one-sided, crossed or wider than 10 cents"
    row["gate"] = {"pass": all(c["pass"] for c in checks.values()), "checks": checks}
    return row


def run_exchange_fetch(seeds: dict, fixtures: dict[str, dict]) -> dict:
    rows, payloads, log = [], {}, {}
    for seed in seeds.get("markets") or []:
        fixture = fixtures.get(seed.get("fixture_id"))
        body, meta = fetch_raw(seed.get("api_url") or
                               f"https://gamma-api.polymarket.com/markets?slug={seed.get('market_slug')}")
        log[str(seed.get("market_slug"))] = meta
        if not body:
            continue
        try:
            parsed = json.loads(body)
        except ValueError:
            continue
        payload = parsed[0] if isinstance(parsed, list) and parsed else parsed
        if not isinstance(payload, dict):
            continue
        payloads[str(seed.get("market_slug"))] = payload
        rows.append(normalise_exchange(seed, payload, fixture, meta.get("at_utc") or iso_now()))
        time.sleep(0.2)
    (OUT / "exchange_payloads.json").write_text(json.dumps(
        {"collected_to_utc": iso_now(), "markets": payloads}, indent=1, ensure_ascii=False) + "\n")
    result = {"collected_to_utc": iso_now(), "access": log,
              "markets": rows, "seed_file": "data/7c2622db/exchange_markets.json"}
    (OUT / "exchange.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    return result


def fixtures_from_capture() -> dict[str, dict]:
    """The committed manual capture, used only to resolve a seeded market's fixture early."""
    path = OUT / "lobby_capture_manual.json"
    if not path.exists():
        return {}
    rows = json.loads(path.read_text()).get("fixtures") or []
    return {r["fixture_id"]: r for r in rows}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    shared_result = run_shared_collector()
    fixtures = fixtures_from_capture()
    snapshot_path = OUT / "snapshot.json"
    if snapshot_path.exists():
        try:
            snapshot = json.loads(snapshot_path.read_text())
            for row in (snapshot.get("hotspawn") or {}).get("fixtures") or []:
                fixtures[row["fixture_id"]] = row
        except ValueError:
            pass
    seeds = json.loads((OUT / "exchange_markets.json").read_text())
    exchange = run_exchange_fetch(seeds, fixtures)
    print(json.dumps({"shared_collector": shared_result,
                      "exchange_markets": len(exchange.get("markets") or []),
                      "exchange_gate_passed": sum(1 for m in exchange.get("markets") or []
                                                  if (m.get("gate") or {}).get("pass"))}, indent=1))
    return 0 if shared_result.get("ok") or exchange.get("markets") else 1


if __name__ == "__main__":
    sys.exit(main())
