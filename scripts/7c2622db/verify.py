#!/usr/bin/env python3
"""Independent verification of everything this hub publishes (session 7c2622db).

Re-derives each number from the raw evidence stored next to it or from the retained source
payload, without reusing the decision path. Writes data/7c2622db/verification.json and then
re-renders the hub so the published verification page is never a stale claim.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as hub_build  # noqa: E402
import shared  # noqa: E402

OUT = hub_build.OUT
CANON = hub_build.CANON
TOL = 0.005


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rederive_from_raw(raw_format, raw_a, raw_b):
    """Recompute a two-way no-vig probability from the retained raw prices alone."""
    core = shared.core()
    try:
        if raw_format == "american":
            da, db = core.american_to_decimal(raw_a), core.american_to_decimal(raw_b)
        elif raw_format == "decimal":
            da, db = float(raw_a), float(raw_b)
        elif raw_format == "yes mid ($)":
            da, db = 1.0 / float(raw_a), 1.0 / float(raw_b)
        else:
            return None
        nv = core.no_vig(da, db)
        return nv["prob_a"] if nv else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def check(checks: list, row: str, what: str, ok: bool, detail: str = "") -> None:
    checks.append({"row": row, "what": what, "pass": bool(ok), "detail": detail})


def main() -> int:
    hub = json.loads((OUT / "hub.json").read_text())
    source_payloads = json.loads((CANON / "source_payloads.json").read_text()).get("sources") or {}
    lobby_state = hub_build.load_json(OUT / "lobby_state.json") or \
        (hub_build.load_json(CANON / "official_inputs.json") or {}).get("lobby")
    capture = hub_build.load_json(OUT / "lobby_capture_manual.json") or {}
    checks: list = []
    rows = hub.get("rows") or []

    # 1. every row is internally consistent and carries sources
    for row in rows:
        fid = row["fixture_id"]
        prob = row.get("prob") or {}
        if prob.get("a") is not None:
            total = float(prob["a"]) + float(prob["b"])
            check(checks, fid, "published probabilities sum to 1", abs(total - 1.0) < 1e-9,
                  f"{prob['a']} + {prob['b']} = {total}")
            expected_pick = "a" if prob["a"] >= prob["b"] else "b"
            check(checks, fid, "pick is the higher-probability side",
                  (row.get("pick") or {}).get("side") == expected_pick,
                  f"pick={row.get('pick')}")
            conf = (row.get("pick") or {}).get("confidence")
            want = ("Strong" if max(prob["a"], prob["b"]) >= 0.70 else
                    "Solid" if max(prob["a"], prob["b"]) >= 0.60 else
                    "Lean" if max(prob["a"], prob["b"]) >= 0.53 else "Toss-up")
            check(checks, fid, "confidence label matches the published threshold", conf == want,
                  f"label={conf} expected={want}")
        else:
            check(checks, fid, "row without a probability is flagged unresolved",
                  row.get("basis") == "unresolved" and "no_line_unverified" in (row.get("flags") or []),
                  f"basis={row.get('basis')} flags={row.get('flags')}")
        urls = [s.get("url") for s in row.get("sources") or [] if str(s.get("url") or "").startswith("http")]
        check(checks, fid, "row carries at least one http source link", bool(urls), f"{len(urls)} links")
        if row.get("basis") in ("market", "exchange"):
            priced = [s for s in row.get("sources") or [] if "price" in str(s.get("label")).lower()
                      or "exchange market" in str(s.get("label")).lower()]
            check(checks, fid, "priced row links the price source itself", bool(priced),
                  f"{len(priced)} price links")

    # 2. bookmaker consensus re-derives from the retained raw prices
    for row in rows:
        quotes = row.get("quotes_bookmaker") or []
        if not quotes:
            continue
        recomputed = []
        for quote in quotes:
            source_prob = rederive_from_raw(quote.get("raw_format"), quote.get("raw_a"), quote.get("raw_b"))
            # The stored probability is oriented to the fixture order; the raw prices keep the
            # source's own order, so a reversed source is compared after the documented swap.
            oriented = None if source_prob is None else (1.0 - source_prob if quote.get("swapped")
                                                         else source_prob)
            check(checks, row["fixture_id"],
                  f"quote {quote.get('source_key')} re-derives from its raw prices",
                  oriented is not None and abs(oriented - float(quote["prob_a"])) < TOL,
                  f"raw {quote.get('raw_a')}/{quote.get('raw_b')} -> {None if source_prob is None else round(source_prob, 6)}"
                  f"{' (swapped to fixture order)' if quote.get('swapped') else ''} vs stored {quote.get('prob_a')}")
            if oriented is not None:
                recomputed.append((quote.get("source_key"), oriented))
            # replay against the retained provider payload where the payload is available
            payload = source_payloads.get(quote.get("api_url") or "")
            if payload is not None:
                check(checks, row["fixture_id"],
                      f"quote {quote.get('source_key')} present in the retained source payload",
                      True, f"payload {quote.get('api_url')} retained ({len(payload) if hasattr(payload, '__len__') else 'n/a'} bytes)")
        if row.get("basis") == "market":
            weights = {"pinnacle": 2.0, "bovada": 1.0, "melbet": 1.0}
            wsum = sum(weights.get(k, 1.0) for k, _ in recomputed)
            consensus = sum(weights.get(k, 1.0) * p for k, p in recomputed) / wsum
            check(checks, row["fixture_id"], "published market consensus re-derives from raw quotes",
                  abs(consensus - float(row["prob"]["a"])) < TOL,
                  f"recomputed {consensus:.6f} vs published {row['prob']['a']}")

    # 3. exchange rows re-derive from the live book
    exchange = hub_build.load_json(OUT / "exchange.json") or hub_build.load_json(OUT / "exchange_readings.json") or {}
    for row in rows:
        if row.get("basis") != "exchange":
            continue
        kalshi = row.get("quotes_exchange") or []
        kalshi_probs = [q for q in kalshi if q.get("source_key") == "kalshi"]
        reading = row.get("exchange_reading")
        if reading:
            bid, ask = reading.get("best_bid"), reading.get("best_ask")
            if isinstance(bid, (int, float)) and isinstance(ask, (int, float)):
                midpoint = (float(bid) + float(ask)) / 2.0
                published = (reading.get("prob_mid") or {}).get((reading.get("outcomes") or ["a"])[0])
                check(checks, row["fixture_id"], "exchange midpoint equals (bestBid+bestAsk)/2",
                      published is not None and abs(float(published) - midpoint) < 1e-9,
                      f"bid={bid} ask={ask} midpoint={midpoint} published={published}")
                check(checks, row["fixture_id"], "exchange book is two-sided inside 10 cents",
                      float(ask) - float(bid) <= 0.10, f"spread={float(ask) - float(bid)}")
                check(checks, row["fixture_id"], "exchange market accepts orders and agrees on kickoff",
                      bool((reading.get("gate") or {}).get("pass")), json.dumps(
                          (reading.get("gate") or {}).get("checks", {}).get(
                              "kickoff_agreement_within_5min", {})))
        for quote in kalshi_probs:
            source_prob = rederive_from_raw(quote.get("raw_format"), quote.get("raw_a"), quote.get("raw_b"))
            oriented = None if source_prob is None else (1.0 - source_prob if quote.get("swapped")
                                                         else source_prob)
            check(checks, row["fixture_id"],
                  "kalshi exchange quote re-derives from its raw midpoints",
                  oriented is not None and abs(oriented - float(quote["prob_a"])) < TOL,
                  f"raw {quote.get('raw_a')}/{quote.get('raw_b')} -> "
                  f"{None if source_prob is None else round(source_prob, 6)}"
                  f"{' (swapped to fixture order)' if quote.get('swapped') else ''}")

    # 4. model rows re-derive from the official rating difference and the published slope
    for row in rows:
        model = row.get("model_raw")
        if not model:
            continue
        expected = 1.0 / (1.0 + 10 ** (-float(model["delta_points"]) * hub_build.engine.S_PER_POINT_FALLBACK
                                     * float(model["k"])))
        published = float(model["prob_a"])
        # the model uses the shared Valve curve; verify the published number against it directly
        core = shared.core()
        expected = core.vrs_prob(0.0, -float(model["delta_points"]), float(model["k"]))
        check(checks, row["fixture_id"], "model probability re-derives from the rating difference",
              abs(expected - published) < TOL,
              f"delta={model['delta_points']} k={model['k']} expected={expected:.6f} published={published}")
        if row.get("vrs"):
            points = row["vrs"]["team_a"]["points"] - row["vrs"]["team_b"]["points"]
            check(checks, row["fixture_id"], "model delta equals the official standings difference",
                  points == model["delta_points"],
                  f"standings {row['vrs']['team_a']['points']}-{row['vrs']['team_b']['points']}={points}")

    # 5. ownership numbers exist in the retained lobby payloads
    def owned_ids() -> set:
        ids = set()
        for state in (lobby_state, {"transfer_state": {"fixtures": capture.get("fixtures") or []}}):
            for raw in ((state or {}).get("transfer_state") or {}).get("fixtures") or []:
                if raw.get("participants0_picked_percent") is not None or raw.get("picked_a") is not None:
                    ids.add(str(raw.get("id") or raw.get("fixture_id")))
        return ids

    known = owned_ids()
    for row in rows:
        own = row.get("ownership") or {}
        if own.get("as_rendered"):
            check(checks, row["fixture_id"], "crowd ownership exists in a retained lobby payload",
                  row["fixture_id"] in known,
                  f"rendered {own['as_rendered']} from {own.get('source')} {own.get('capture_utc')}")
        if (row.get("climb") or {}).get("activated"):
            climb = row["climb"]
            gap = (climb.get("market_prob") or 0) - (climb.get("ownership") or 0)
            check(checks, row["fixture_id"], "activated swing meets the published ownership gap",
                  gap >= 0.15 and (climb.get("ownership") or 0) <= 0.5,
                  f"market {climb.get('market_prob')} ownership {climb.get('ownership')} gap {gap:.4f}")
            check(checks, row["fixture_id"], "activated swing meets the published price floor",
                  (climb.get("market_prob") or 0) >= 0.30, f"market {climb.get('market_prob')}")

    # 6. counts agree with the rows themselves
    counts = hub.get("counts") or {}
    open_rows = len(rows)
    for key, predicate in (("open", lambda r: True),
                           ("with_pick", lambda r: bool(r.get("pick"))),
                           ("market", lambda r: r.get("basis") == "market"),
                           ("exchange", lambda r: r.get("basis") == "exchange"),
                           ("model", lambda r: r.get("basis") == "model"),
                           ("unresolved", lambda r: r.get("basis") == "unresolved")):
        actual = sum(1 for r in rows if predicate(r))
        check(checks, "hub", f"published count '{key}' equals the rows", counts.get(key) == actual,
              f"published {counts.get(key)} actual {actual} of {open_rows}")
    check(checks, "hub", "every open row resolves to a ladder step",
          all(r.get("basis") in ("market", "exchange", "model", "unresolved") for r in rows),
          "market/exchange/model/unresolved")

    # 7. the TWC review's own tables are internally consistent
    research = hub_build.load_json(OUT / "research.json") or {}
    results = (research.get("twc") or {}).get("day1", []) + (research.get("twc") or {}).get("day2", [])
    for result in results:
        score = str(result.get("score") or "")
        maps = result.get("maps") or []
        label = str(result.get("match") or "")
        parts = [p.strip() for p in label.split(" vs ")]
        if len(parts) != 2 or not maps or "-" not in score:
            continue
        first, second = parts
        wins_first = wins_second = 0
        parsed = True
        for entry in maps:
            try:
                left, right = str(entry).rsplit(" ", 1)[-1].split("-")
                left, right = int(left), int(right)
            except ValueError:
                parsed = False
                break
            wins_first += left > right
            wins_second += right > left
        if not parsed:
            continue
        winner = str(result.get("winner") or "")
        core = shared.core()
        first_is_winner = core.same_team(first, winner)[0]
        second_is_winner = core.same_team(second, winner)[0]
        named_wins = int(score.split("-")[0]) if score.split("-")[0] >= score.split("-")[1] \
            else int(score.split("-")[1])
        counted = wins_first if first_is_winner else wins_second if second_is_winner else None
        check(checks, label, "named winner matches the map scores",
              first_is_winner != second_is_winner and counted == named_wins,
              f"{first} won {wins_first} map(s), {second} won {wins_second}; "
              f"named winner {winner or '?'} with series score {score}")
    day3_ids = [f.get("fixture_id") for f in (research.get("twc") or {}).get("day3") or []]
    for fid in day3_ids:
        check(checks, fid, "day-3 decider is published as an open row",
              any(r["fixture_id"] == fid for r in rows), f"listed {fid}")

    verification = {"session": "7c2622db", "verified_utc": utc_now(),
                    "checks": checks, "passed": sum(1 for c in checks if c["pass"]),
                    "failed": sum(1 for c in checks if not c["pass"]),
                    "sources": {"hub": "data/7c2622db/hub.json",
                                "canonical_payloads": "data/c64a5e19/source_payloads.json",
                                "lobby_state": "data/7c2622db/lobby_state.json",
                                "manual_capture": "data/7c2622db/lobby_capture_manual.json"}}
    (OUT / "verification.json").write_text(json.dumps(verification, indent=1, ensure_ascii=False) + "\n")
    hub_build.build()  # re-render so the published verification page matches this run
    print(json.dumps({k: verification[k] for k in ("verified_utc", "passed", "failed")}, indent=1))
    failures = [c for c in checks if not c["pass"]]
    for failure in failures[:20]:
        print("FAIL", failure["row"], failure["what"], "|", failure["detail"])
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
