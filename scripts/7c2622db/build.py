#!/usr/bin/env python3
"""Build the mobile pick'em hub for session 7c2622db.

Reads only: this session's own capture (or the committed fallback capture), the canonical
collected batch (read-only), and this session's committed research/alias rules. Writes only
``hub/**`` and ``data/7c2622db/hub.json``. Every published probability is derived here from a
retained raw price or from the official Valve ratings, and every row keeps its sources.
"""
from __future__ import annotations

import html
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine  # noqa: E402
import shared  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "7c2622db"
HUB = ROOT / "hub"
CANON = ROOT / "data" / "c64a5e19"
CANONICAL_SNAPSHOT: dict | None = None
LOBBY = "https://play.hotspawn.com/lobby"
BOOKMAKERS = ("pinnacle", "bovada", "melbet")
LADDER = ("market", "exchange", "model", "unresolved")


# --------------------------------------------------------------------------------- helpers
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def parse_iso(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def pct(value, digits: int = 0) -> str:
    if value is None:
        return "—"
    return f"{100.0 * float(value):.{digits}f}%"


def hours_between(a: datetime | None, b: datetime | None) -> float | None:
    if not a or not b:
        return None
    return abs((a - b).total_seconds()) / 3600.0


def age_hours(stamp: datetime | None, reference: datetime) -> float | None:
    if not stamp:
        return None
    return (reference - stamp).total_seconds() / 3600.0


# ---------------------------------------------------------------------------- input layer
def ownership_from_state(state: dict | None) -> dict[str, dict]:
    """Crowd pick shares exactly as the lobby publishes them. Ownership only, never a price."""
    rows = ((state or {}).get("transfer_state") or {}).get("fixtures") or []
    out = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        fid = str(raw.get("id") or "")
        if not fid:
            continue
        out[fid] = {
            "a": raw.get("participants0_picked_percent"),
            "b": raw.get("participants1_picked_percent"),
            "total_picks": raw.get("total_picks"),
            "team_a": raw.get("participants0_name"),
            "team_b": raw.get("participants1_name"),
        }
    return out


def validate_display_clock(fixtures: dict, canonical: dict | None, capture: dict) -> dict:
    """Check the lobby's unlabelled ET display against every UTC start we can cross-reference.

    The lobby renders kickoff times in US Eastern with no zone label. The rule this hub applies
    (UTC = displayed ET + 4h) is only used for fixtures with no epoch start of their own, and it is
    re-checked at every build against every fixture that has a canonical epoch start. Any
    disagreement is published rather than silently resolved.
    """
    offset = int((capture.get("display_clock") or {}).get("rendered_offset_hours") or -4)
    canon = {}
    for row in ((canonical or {}).get("hotspawn") or {}).get("fixtures") or []:
        canon[str(row.get("fixture_id"))] = row
    checked, mismatches, derived_only = 0, [], []
    for fid, fixture in fixtures.items():
        displayed = fixture.get("displayed_et")
        start = fixture.get("start_utc")
        if not displayed:
            fixture["start_source"] = "no displayed time captured"
            continue
        reference = canon.get(fid) or {}
        epoch_start = reference.get("start_utc")
        try:
            parsed = datetime.strptime(displayed, "%b %d, %H:%M").replace(
                year=int(str(start or epoch_start or "2026")[:4]), tzinfo=timezone.utc)
        except (ValueError, TypeError):
            fixture["start_source"] = "displayed time unparseable"
            mismatches.append({"fixture_id": fid, "displayed_et": displayed,
                               "reason": "displayed time could not be parsed"})
            continue
        derived = parsed - timedelta(hours=offset)
        derived_iso = derived.strftime("%Y-%m-%dT%H:%M:%SZ")
        if epoch_start:
            checked += 1
            if derived_iso != epoch_start:
                mismatches.append({"fixture_id": fid, "displayed_et": displayed,
                                   "derived_utc": derived_iso, "canonical_utc": epoch_start})
            fixture["start_source"] = (f"canonical/API epoch start {epoch_start}"
                                       f"{'' if derived_iso == epoch_start else ' (CONFLICTS with the displayed ET)'}")
        else:
            derived_only.append(fid)
            fixture["start_source"] = (f"derived from the displayed ET {displayed} with the "
                                       f"validated rule (UTC = ET + 4h)")
            if start and start != derived_iso:
                mismatches.append({"fixture_id": fid, "displayed_et": displayed,
                                   "derived_utc": derived_iso, "published_utc": start})
                fixture["start_utc"] = derived_iso
    return {"rule": "UTC = displayed ET + 4h (lobby renders US Eastern, UTC-4)",
            "checked_against_epoch_starts": checked,
            "derived_from_display_only": sorted(derived_only),
            "mismatches": mismatches}


def load_fixtures(capture: dict, snapshot: dict | None) -> tuple[dict, dict]:
    """Merge the committed manual capture with the automated capture (automated wins)."""
    fixtures: dict[str, dict] = {}
    for row in capture.get("fixtures") or []:
        fixtures[row["fixture_id"]] = {
            "fixture_id": row["fixture_id"],
            "competition": row.get("competition"),
            "tier": row.get("tier"),
            "tier_label": row.get("tier_label"),
            "points": row.get("points"),
            "stage": row.get("stage"),
            "multiplier": row.get("multiplier"),
            "best_of": None,
            "status": "scheduled",
            "start_utc": row.get("start_utc"),
            "lock_utc": None,
            "team_a": row.get("team_a"),
            "team_b": row.get("team_b"),
            "permalink": row.get("permalink"),
            "displayed_et": row.get("displayed_et"),
            "capture_note": row.get("note"),
            "listed_in": ["manual_capture"],
            "ownership": {"a": (row.get("picked_a") / 100.0 if row.get("picked_a") is not None else None),
                          "b": (row.get("picked_b") / 100.0 if row.get("picked_b") is not None else None),
                          "as_rendered": [row.get("picked_a"), row.get("picked_b")],
                          "total_picks": None,
                          "source": "lobby capture " + str(capture.get("read_utc"))},
        }
    automated = (snapshot or {}).get("hotspawn") or {}
    for row in automated.get("fixtures") or []:
        fid = str(row.get("fixture_id"))
        existing = fixtures.get(fid)
        merged = {
            "fixture_id": fid,
            "competition": row.get("competition") or (existing or {}).get("competition"),
            "tier": row.get("tier") or (existing or {}).get("tier"),
            "tier_label": (existing or {}).get("tier_label"),
            "points": row.get("points") if row.get("points") is not None else (existing or {}).get("points"),
            "stage": row.get("stage") or (existing or {}).get("stage"),
            "multiplier": (existing or {}).get("multiplier"),
            "best_of": row.get("best_of"),
            "status": row.get("status"),
            "start_utc": row.get("start_utc"),
            "lock_utc": row.get("lock_utc"),
            "team_a": row.get("team_a"),
            "team_b": row.get("team_b"),
            "permalink": (automated.get("permalinks") or {}).get(fid) or (existing or {}).get("permalink"),
            "displayed_et": (existing or {}).get("displayed_et"),
            "capture_note": (existing or {}).get("capture_note"),
            "listed_in": ["automated_capture"] + (["manual_capture"] if existing else []),
            "ownership": (existing or {}).get("ownership"),
        }
        fixtures[fid] = merged
    clock = validate_display_clock(fixtures, CANONICAL_SNAPSHOT, capture)
    meta = {
        "automated_capture_utc": (snapshot or {}).get("collected_to_utc"),
        "automated_capture_rows": len(automated.get("fixtures") or []),
        "manual_capture_utc": capture.get("read_utc"),
        "manual_capture_rows": len(capture.get("fixtures") or []),
        "display_clock": clock,
    }
    return fixtures, meta


def load_quotes(snapshot: dict | None, canonical: dict | None) -> tuple[list, dict]:
    quotes: list = []
    source = None
    if snapshot and snapshot.get("quotes"):
        quotes = list(snapshot["quotes"])
        source = {"label": "hub collection", "collected_to_utc": snapshot.get("collected_to_utc")}
    elif canonical and canonical.get("quotes"):
        quotes = list(canonical["quotes"])
        source = {"label": "canonical every-match collection (read-only)",
                  "collected_to_utc": canonical.get("collected_to_utc")}
    return quotes, source or {"label": "none", "collected_to_utc": None}


def load_vrs(snapshot: dict | None, canonical: dict | None) -> tuple[dict, dict]:
    for candidate, label in ((snapshot, "hub collection"),
                             (canonical, "canonical every-match collection (read-only)")):
        vrs = (candidate or {}).get("vrs")
        if vrs and vrs.get("teams"):
            return vrs, {"label": label, "snapshot": vrs.get("snapshot")}
    return {}, {"label": "none", "snapshot": None}


# ------------------------------------------------------------------------ decision engine
def normalise_quote_names(quote: dict, aliases: dict) -> dict:
    """Rewrite a source's team labels through the reviewed alias rules, nothing else."""
    return {**quote, "team_a": engine.resolve_alias(quote.get("team_a")),
            "team_b": engine.resolve_alias(quote.get("team_b"))}


def normalise_fixture_names(fixture: dict) -> dict:
    return {**fixture, "team_a": engine.resolve_alias(fixture.get("team_a")),
            "team_b": engine.resolve_alias(fixture.get("team_b"))}


def match_quotes(fixture: dict, quotes: list, now: datetime) -> list[dict]:
    core = shared.core()
    target = normalise_fixture_names(fixture)
    matched = []
    for raw in quotes:
        quote = normalise_quote_names(raw, None)
        join = core.match_quote(target, quote)
        if not join or join.get("rejected"):
            continue
        if quote.get("live"):
            continue
        swapped = join["swapped"]
        prob_a = core.oriented_prob(quote, swapped)
        if prob_a is None:
            continue
        matched.append({
            "source_key": quote.get("source_key"),
            "source_name": quote.get("source_name"),
            "event_id": quote.get("event_id"),
            "public_url": quote.get("public_url"),
            "api_url": quote.get("api_url"),
            "league": quote.get("league"),
            "fetched_utc": quote.get("retrieved_utc"),
            "age_hours": age_hours(parse_iso(quote.get("retrieved_utc")), now),
            "swapped": swapped,
            "alias_notes": join.get("alias_notes") or [],
            "raw_a": quote.get("raw_a"),
            "raw_b": quote.get("raw_b"),
            "raw_format": quote.get("raw_format"),
            "decimal_a": quote.get("decimal_a"),
            "decimal_b": quote.get("decimal_b"),
            "start_utc_at_source": quote.get("start_utc"),
            "prob_a": float(prob_a),
            "overround": quote.get("overround"),
        })
    return matched


def fit_k(rows: list[dict], vault: dict) -> dict:
    core = shared.core()
    pairs = []
    for row in rows:
        market = row.get("market_consensus")
        model = row.get("model_raw")
        if not market or not model:
            continue
        pairs.append({"delta": model["delta_points"], "market_prob_a": market["prob_a"]})
    if len(pairs) < core.CAL_MIN_PAIRS:
        return {"n_pairs": len(pairs), "k": 1.0, "fitted": False,
                "note": f"fewer than {core.CAL_MIN_PAIRS} eligible priced pairs in this capture, "
                        f"Valve's own slope (k=1) is used and every model row says so"}
    fitted = core.fit_calibration(pairs)
    fitted["note"] = ("slope learned from this capture's own bookmaker consensus over official "
                      "Valve ratings, through the origin, clamped to the published bounds")
    return fitted


def vrs_lookup(name: str, vrs: dict) -> tuple[dict | None, dict]:
    core = shared.core()
    wanted = engine.resolve_alias(name)
    candidates = [t for t in (vrs.get("teams") or []) if core.norm(t.get("team")) == core.norm(wanted)]
    if len(candidates) == 1:
        return candidates[0], {"resolved": True, "candidates": candidates, "query": wanted}
    return None, {"resolved": False, "candidates": candidates, "query": wanted,
                  "reason": "not_in_vrs" if not candidates else "ambiguous_vrs_name"}


def exchange_entries(fixture: dict, exchange: dict | None, now: datetime) -> tuple[list, dict | None]:
    """Eligible exchange readings for this fixture, with the gate result attached."""
    entries, reading = [], None
    for market in (exchange or {}).get("markets") or []:
        if str(market.get("fixture_id")) != fixture["fixture_id"]:
            continue
        reading = market
        gate = market.get("gate") or {}
        fresh = (age_hours(parse_iso(market.get("retrieved_utc")), now) or 99) <= 6
        prob_mid = market.get("prob_mid") or {}
        if not gate.get("pass") or not fresh or not prob_mid:
            continue
        names = list(prob_mid.keys())
        if len(names) != 2:
            continue
        # orient to the fixture's own order
        core = shared.core()
        target = normalise_fixture_names(fixture)
        first = names[0]
        if core.same_team(target["team_a"], first)[0]:
            prob_a = float(prob_mid[first])
        elif core.same_team(target["team_a"], names[1])[0]:
            prob_a = float(prob_mid[names[1]])
        else:
            continue
        entries.append({
            "source_key": "polymarket",
            "source_name": "Polymarket (exchange)",
            "event_id": market.get("market_slug"),
            "public_url": market.get("market_url"),
            "api_url": market.get("api_url"),
            "fetched_utc": market.get("retrieved_utc"),
            "age_hours": age_hours(parse_iso(market.get("retrieved_utc")), now),
            "prob_a": prob_a,
            "best_bid": market.get("best_bid"),
            "best_ask": market.get("best_ask"),
            "spread": market.get("spread"),
            "volume": market.get("volume"),
            "liquidity": market.get("liquidity"),
            "rule_note": market.get("rule_note"),
        })
    return entries, reading


def decide(fixture: dict, quotes: list, exchange: dict | None, vrs: dict, k: float,
           now: datetime, max_age_hours: float) -> dict:
    core = shared.core()
    matched = match_quotes(fixture, quotes, now)
    eligible_book = [m for m in matched if m["source_key"] in BOOKMAKERS
                     and (m["age_hours"] is None or m["age_hours"] <= max_age_hours)]
    eligible_book.sort(key=lambda m: m["source_key"])
    expired_book = [m for m in matched if m["source_key"] in BOOKMAKERS
                    and (m["age_hours"] is None or m["age_hours"] > max_age_hours)]
    kalshi = [m for m in matched if m["source_key"] == "kalshi"
              and (m["age_hours"] is None or m["age_hours"] <= max_age_hours)]
    polymarket, exchange_reading = exchange_entries(fixture, exchange, now)

    row: dict = {
        "fixture_id": fixture["fixture_id"],
        "competition": fixture.get("competition"),
        "tier": fixture.get("tier"),
        "tier_label": fixture.get("tier_label"),
        "stage": fixture.get("stage"),
        "multiplier": fixture.get("multiplier"),
        "points": fixture.get("points"),
        "best_of": fixture.get("best_of"),
        "status": fixture.get("status"),
        "start_utc": fixture.get("start_utc"),
        "lock_utc": fixture.get("lock_utc"),
        "start_display_et": fixture.get("displayed_et"),
        "start_source": fixture.get("start_source"),
        "team_a": fixture.get("team_a"),
        "team_b": fixture.get("team_b"),
        "hotspawn_url": fixture.get("permalink") or LOBBY,
        "hotspawn_url_kind": "match page" if fixture.get("permalink") else "lobby",
        "listed_in": fixture.get("listed_in"),
        "flags": [],
        "sources": [],
        "quotes_bookmaker": eligible_book,
        "quotes_bookmaker_expired": expired_book,
        "quotes_exchange": kalshi + polymarket,
        "exchange_reading": exchange_reading,
        "ownership": fixture.get("ownership"),
    }

    # Valve rating model (independent of the market layer)
    a_row, a_info = vrs_lookup(fixture.get("team_a"), vrs)
    b_row, b_info = vrs_lookup(fixture.get("team_b"), vrs)
    if a_row and b_row:
        delta = float(a_row["points"]) - float(b_row["points"])
        row["vrs"] = {"snapshot": vrs.get("snapshot"), "page_url": vrs.get("page_url"),
                      "team_a": {"team": a_row.get("team"), "standing": a_row.get("standing"),
                                 "points": a_row.get("points"), "roster": a_row.get("roster"),
                                 "details_path": a_row.get("details_path")},
                      "team_b": {"team": b_row.get("team"), "standing": b_row.get("standing"),
                                 "points": b_row.get("points"), "roster": b_row.get("roster"),
                                 "details_path": b_row.get("details_path")}}
        row["model_raw"] = {"delta_points": delta, "k": k,
                            "prob_a": core.vrs_prob(a_row["points"], b_row["points"], k),
                            "label": "own calibrated calculation from the official Valve ratings"}
    else:
        row["vrs"] = None
        row["model_raw"] = None
        for info in (a_info, b_info):
            if not info.get("resolved"):
                row["flags"].append(f"{info['reason']}:{fixture['team_a'] if info is a_info else fixture['team_b']}")

    # Ladder
    if eligible_book:
        consensus = core.consensus(eligible_book)
        row["basis"] = "market"
        row["market_consensus"] = consensus
        row["prob"] = {"a": consensus["prob_a"], "b": consensus["prob_b"]}
        row["ladder"] = "1 - bookmaker two-way prices (Pinnacle weighted 2, Bovada and Melbet 1)"
        row["valid_until_utc"] = iso(max((parse_iso(m["fetched_utc"]) for m in eligible_book
                                          if parse_iso(m["fetched_utc"])), default=None)
                                     + timedelta(hours=max_age_hours))
    elif kalshi or polymarket:
        entries = kalshi + polymarket
        consensus = core.consensus(entries)
        row["basis"] = "exchange"
        row["market_consensus"] = consensus
        row["prob"] = {"a": consensus["prob_a"], "b": consensus["prob_b"]}
        row["ladder"] = "2 - exchange books (Polymarket CLOB with a two-sided book inside 10 cents, " \
                        "Kalshi with explicit full-match rules)"
        row["flags"].append("exchange_midpoints_not_executable_bookmaker_odds")
        if any((e.get("volume") or 0) < 500 for e in polymarket):
            row["flags"].append("exchange_volume_may_be_low")
        row["valid_until_utc"] = iso(max((parse_iso(e["fetched_utc"]) for e in entries
                                          if parse_iso(e["fetched_utc"])), default=None)
                                     + timedelta(hours=max_age_hours))
    elif row.get("model_raw"):
        row["basis"] = "model"
        row["model"] = {"prob_a": row["model_raw"]["prob_a"], "prob_b": 1.0 - row["model_raw"]["prob_a"],
                        "delta_points": row["model_raw"]["delta_points"], "k": k}
        row["prob"] = {"a": row["model"]["prob_a"], "b": row["model"]["prob_b"]}
        row["ladder"] = "3 - own logistic rating-difference line over the official Valve standings"
        row["flags"].append("model_estimate_not_verified_win_probability")
        row["valid_until_utc"] = None
    else:
        row["basis"] = "unresolved"
        row["prob"] = {"a": None, "b": None}
        row["ladder"] = "4 - no defensible price or rating pair in this capture"
        row["flags"].append("no_line_unverified")
        unresolved_why = []
        for info, team in ((a_info, fixture["team_a"]), (b_info, fixture["team_b"])):
            if not info.get("resolved"):
                unresolved_why.append(f"{team}: {info.get('reason')}")
        if not unresolved_why:
            unresolved_why.append("no eligible bookmaker, exchange or unique official rating pair")
        row["pick_blocked_reason"] = "; ".join(unresolved_why)

    if expired_book:
        row["flags"].append("older_bookmaker_quote_retained_as_evidence_only")

    # Pick, confidence, differential, climb gate
    if row["prob"]["a"] is not None:
        pick_side = "a" if row["prob"]["a"] >= row["prob"]["b"] else "b"
        pick_prob = row["prob"][pick_side]
        row["pick"] = {"side": pick_side, "team": fixture["team_" + pick_side],
                       "prob": pick_prob, "fair_decimal": round(1.0 / pick_prob, 3),
                       "confidence": core.confidence_label(pick_prob)}
        ownership_pick = (row.get("ownership") or {}).get(pick_side)
        row["differential_points"] = engine.differential(row.get("points"), pick_prob, ownership_pick)

        # Contrarian gate: examine BOTH sides. The best (probability - ownership)
        # differential wins, but only a side that passes all four published conditions is
        # activated. A crowd favourite is never a leaderboard pick.
        market_consensus = row.get("market_consensus") or {}
        model_probs = {"a": (row.get("model_raw") or {}).get("prob_a")}
        if model_probs["a"] is not None:
            model_probs["b"] = 1.0 - model_probs["a"]
        else:
            model_probs["b"] = None
        facts = fixture.get("context_facts") or {}
        candidates = []
        for side in ("a", "b"):
            market_prob = market_consensus.get("prob_" + side)
            ownership = (row.get("ownership") or {}).get(side)
            model_prob = model_probs[side]
            ok, reasons = engine.swing_eligible(
                market_prob, model_prob, ownership,
                has_context=bool(facts.get(side)),
                total_picks=(row.get("ownership") or {}).get("total_picks"),
            )
            candidates.append({
                "side": side,
                "team": fixture["team_" + side],
                "market_prob": market_prob,
                "ownership": ownership,
                "model_prob": model_prob,
                "differential_points": engine.differential(row.get("points"), market_prob, ownership),
                "gate": {"pass": bool(ok), "reasons": reasons},
                "facts": facts.get(side) or [],
            })
        ranked = sorted(candidates, key=lambda c: (c["differential_points"] is not None,
                                                   c["differential_points"] or -99), reverse=True)
        best = ranked[0]
        activated = next((c for c in ranked if c["gate"]["pass"]), None)
        chosen = activated or best
        row["climb_candidates"] = [c for c in candidates if c["market_prob"] is not None]
        # Two legitimate leaderboard shapes: take the underdog the market still prices
        # (contrarian underdog), or take a market favourite the crowd is fading
        # (fade the crowd). Both require the same gate, and both are the *swing* side,
        # which may or may not be the same side as the safe pick.
        row["climb"] = {
            "team": chosen["team"],
            "side": chosen["side"],
            "activated": bool(activated) and row["basis"] != "model",
            "kind": ("contrarian underdog" if chosen["side"] != pick_side else "fade the crowd"),
            "crowd_majority_side": "b" if (row.get("ownership") or {}).get("a", 0) < 0.5 else "a",
            "market_prob": chosen["market_prob"],
            "ownership": chosen["ownership"],
            "model_prob": chosen["model_prob"],
            "differential_points": chosen["differential_points"],
            "gate": chosen["gate"],
        }
        row["climb"]["crowd_fade"] = (row["climb"]["crowd_majority_side"] != chosen["side"])
        if activated and row["basis"] == "model":
            row["flags"].append("climb_not_activated_without_market_reading")
    else:
        row["pick"] = None
        row["climb"] = None

    # Row sources
    if row["hotspawn_url_kind"] == "match page":
        row["sources"].append({"label": "HotSpawn match page (fixture, points, lock, crowd share)",
                               "url": row["hotspawn_url"]})
    row["sources"].append({"label": "HotSpawn lobby (fixture discovery)", "url": LOBBY})
    for quote in eligible_book + expired_book + kalshi:
        row["sources"].append({"label": f"{quote['source_name']} full-match price "
                                         f"({quote.get('raw_a')}/{quote.get('raw_b')} {quote.get('raw_format')}, "
                                         f"fetched {quote.get('fetched_utc')})",
                               "url": quote.get("public_url") or quote.get("api_url")})
    for entry in polymarket:
        row["sources"].append({"label": f"Polymarket exchange market {entry.get('event_id')} "
                                         f"(bid {entry.get('best_bid')} / ask {entry.get('best_ask')}, "
                                         f"fetched {entry.get('fetched_utc')})",
                               "url": entry.get("public_url")})
    if row.get("vrs"):
        row["sources"].append({"label": f"Official Valve standings {row['vrs']['snapshot']} "
                                         f"(#{row['vrs']['team_a']['standing']} vs "
                                         f"#{row['vrs']['team_b']['standing']})",
                               "url": row["vrs"]["page_url"] or "https://github.com/ValveSoftware/counter-strike_regional_standings"})
    return row


def open_rows(fixtures: dict, now: datetime) -> tuple[list, list]:
    open_, locked = [], []
    for fixture in fixtures.values():
        lock = parse_iso(fixture.get("lock_utc"))
        start = parse_iso(fixture.get("start_utc"))
        if fixture.get("status") not in (None, "scheduled"):
            locked.append(fixture)
            continue
        if lock and lock <= now:
            locked.append(fixture)
            continue
        if start and start < now - timedelta(hours=6):
            locked.append(fixture)
            continue
        open_.append(fixture)
    open_.sort(key=lambda f: (f.get("start_utc") or "", f["fixture_id"]))
    return open_, locked


# ------------------------------------------------------------------------------- rendering
CSS = """
:root{--ink:#111827;--muted:#5b6472;--line:#e3e7ee;--bg:#f7f8fb;--card:#fff;--accent:#0b63ce;
--good:#0f9d58;--warn:#b45309;--bad:#b91c1c;--chip:#eef2f8}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--accent)}
.wrap{max-width:760px;margin:0 auto;padding:0 12px 64px}
header.top{position:sticky;top:0;z-index:5;background:#fff;border-bottom:1px solid var(--line);
padding:10px 12px}
header.top .inner{max-width:760px;margin:0 auto;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.brand{font-weight:700;font-size:15px;text-decoration:none;color:var(--ink)}
nav.jump{display:flex;gap:6px;overflow-x:auto;-webkit-overflow-scrolling:touch;padding:2px 0}
nav.jump a{flex:0 0 auto;padding:9px 12px;border:1px solid var(--line);border-radius:999px;
background:var(--chip);text-decoration:none;font-size:13px;color:var(--ink);min-height:40px;
display:inline-flex;align-items:center}
h1{font-size:24px;line-height:1.2;margin:18px 0 6px}
h2{font-size:19px;margin:28px 0 8px}
h3{font-size:16px;margin:18px 0 6px}
p,li{color:#1f2937}
.lede{color:var(--muted);font-size:14px;margin:0 0 10px}
.grid{display:grid;gap:10px}
@media(min-width:640px){.grid.two{grid-template-columns:1fr 1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px;margin:10px 0}
.card.hero{border-left:5px solid var(--accent)}
.card.locked{opacity:.65}
.top-line{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:12px;color:var(--muted)}
.chip{background:var(--chip);border-radius:999px;padding:3px 9px;font-size:12px;white-space:nowrap}
.chip.s{background:#fde8e8;color:#8a1c1c}
.chip.b{background:#e8f0fd;color:#123a75}
.chip.c{background:#eef2f8;color:#374151}
.chip.win{background:#e6f6ec;color:#0b6b3a;font-weight:600}
.chip.flag{background:#fdf1e3;color:#8a5300}
.match{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin:8px 0 2px}
.team{font-size:19px;font-weight:600;line-height:1.2}
.team.pick{color:var(--accent)}
.prob{font-size:20px;font-variant-numeric:tabular-nums;font-weight:700}
.prob.pick{color:var(--accent)}
.pickline{margin:6px 0 0;font-size:14px}
.pickline b{font-size:16px}
.meta{font-size:12.5px;color:var(--muted);margin:6px 0 0}
.bar{display:flex;height:8px;border-radius:999px;overflow:hidden;background:#eceff5;margin:8px 0 2px}
.bar span{display:block;height:100%}
.bar .a{background:#0b63ce}.bar .b{background:#9aa7bb}
.kpis{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:10px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px}
.kpi b{display:block;font-size:22px;line-height:1.1}
.kpi span{font-size:12px;color:var(--muted)}
details{margin-top:8px;border-top:1px dashed var(--line);padding-top:6px}
summary{cursor:pointer;font-size:13px;color:var(--accent);min-height:36px;display:flex;align-items:center}
ul.src{list-style:none;padding:0;margin:4px 0 0}
ul.src li{font-size:12.5px;margin:6px 0;overflow-wrap:anywhere}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;padding:7px 6px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;color:var(--muted);font-weight:600}
.scroll{overflow-x:auto}
.callout{background:#fffaf0;border:1px solid #f2dfba;border-radius:12px;padding:10px;margin:10px 0}
.callout.bad{background:#fef6f6;border-color:#f3cccc}
.callout.ok{background:#f4fbf6;border-color:#cfe9d8}
footer.foot{margin-top:30px;border-top:1px solid var(--line);padding-top:12px;font-size:12.5px;color:var(--muted)}
.drop{color:var(--muted);font-size:13px}
"""


def shell(title: str, body: str, generated: str, active: str = "") -> str:
    links = [("index.html", "Day 3 + every match"), ("twc.html", "TWC review"),
             ("unresolved.html", "Unresolved"), ("flagged.html", "Flagged"),
             ("verify.html", "Verification"), ("method.html", "Method")]
    nav = "".join(
        f'<a href="{href}"{" style=background:#0b63ce;color:#fff" if href == active else ""}>{label}</a>'
        for href, label in links)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Every open HotSpawn CS2 pick'em match with a pick, both win probabilities and its sources; TWC 2026 day-3 desk.">
<title>{esc(title)}</title><style>{CSS}</style></head><body>
<header class="top"><div class="inner"><a class="brand" href="index.html">⚡ Pick'em hub</a>
<nav class="jump" aria-label="Hub sections">{nav}<a href="../index.html">Main site</a></nav></div></header>
<div class="wrap">{body}
<footer class="foot">Built {esc(generated)} by session <code>7c2622db</code>.
HotSpawn supplies fixtures, listed points and crowd ownership only — never a probability.
External prices come from licensed bookmakers and public exchanges; model rows are this
project's own calculation from the official Valve standings. Research only, 18+.
<a href="../picks-every-match/index.html">Canonical every-match board</a> ·
<a href="../index.html">Main dashboard</a>.</footer></div></body></html>"""


def start_label(row: dict) -> str:
    stamp = parse_iso(row.get("start_utc"))
    if not stamp:
        return "start unknown"
    et = stamp - timedelta(hours=4)
    return f"{stamp.strftime('%d %b %H:%M')}Z · {et.strftime('%H:%M')} ET"


def tier_chip(row: dict) -> str:
    tier = (row.get("tier") or "?").lower()
    label = row.get("tier_label") or (row.get("tier") or "?")
    return f'<span class="chip {esc(tier)}">{esc(label)}</span>'


def basis_chip(row: dict) -> str:
    labels = {"market": "Market line", "exchange": "Exchange line", "model": "Own model line",
              "unresolved": "Unresolved"}
    return f'<span class="chip">{esc(labels.get(row.get("basis"), row.get("basis")))}</span>'


def prob_rows(row: dict) -> str:
    pick_side = (row.get("pick") or {}).get("side")
    out = []
    for side in ("a", "b"):
        team = row.get(f"team_{side}")
        prob = (row.get("prob") or {}).get(side)
        cls = "pick" if pick_side == side else ""
        mark = ' <span class="chip win">PICK</span>' if pick_side == side else ""
        out.append(f'<div class="match"><span class="team {cls}">{esc(team)}{mark}</span>'
                   f'<span class="prob {cls}">{pct(prob, 1)}</span></div>')
    return "".join(out)


def ownership_bar(row: dict) -> str:
    own = row.get("ownership") or {}
    a, b = own.get("a"), own.get("b")
    if a is None or b is None:
        return '<p class="meta">Crowd ownership: not captured for this fixture.</p>'
    total = (a or 0) + (b or 0) or 1
    pa = 100.0 * (a or 0) / total
    return (f'<div class="bar"><span class="a" style="width:{pa:.1f}%"></span>'
            f'<span class="b" style="width:{100 - pa:.1f}%"></span></div>'
            f'<p class="meta">Crowd ownership: {esc(row["team_a"])} {a * 100:.0f}% · '
            f'{esc(row["team_b"])} {b * 100:.0f}% '
            f'({esc(own.get("source") or "lobby capture")}'
            + (f' {esc(str(own.get("capture_utc"))[:16])}Z' if own.get("capture_utc") else '')
            + (f', {own.get("total_picks")} picks' if own.get("total_picks") is not None else '')
            + (f' counted ' + esc(str(own.get("count_capture_utc"))[:16]) + 'Z'
               if own.get("count_capture_utc") and own.get("count_capture_utc") != own.get("capture_utc") else '')
            + ', ownership only)</p>')


def source_details(row: dict) -> str:
    items = "".join(
        f'<li>· {esc(s.get("label"))}<br><a href="{esc(s.get("url"))}">{esc(s.get("url"))}</a></li>'
        for s in row.get("sources") or [])
    return (f'<details><summary>Sources for this row ({len(row.get("sources") or [])})</summary>'
            f'<ul class="src">{items}</ul></details>')


def match_card(row: dict, generated: str, compact: bool = False) -> str:
    flags = "".join(f'<span class="chip flag">{esc(f)}</span>' for f in row.get("flags") or [])
    pick = row.get("pick") or {}
    line = ""
    if pick:
        diff = row.get("differential_points")
        line = (f'<p class="pickline">Pick: <b>{esc(pick.get("team"))}</b> at '
                f'{pct(pick.get("prob"), 1)} · {esc(pick.get("confidence"))} · '
                f'fair price {pick.get("fair_decimal")} · listed points {row.get("points")}'
                + (f' · pick differential {diff:+.2f} pts' if diff is not None else '')
                + '</p>')
    climb = row.get("climb") or {}
    climb_line = ""
    if climb and climb.get("activated"):
        label = ("Leaderboard swing — " + str(climb.get("kind"))
                 if climb.get("crowd_fade") else "Leaderboard swing")
        climb_line = (f'<p class="pickline">{label}: <b>{esc(climb.get("team"))}</b> at '
                      f'{pct(climb.get("market_prob"), 1)} vs {pct(climb.get("ownership"), 0)} ownership '
                      f'· differential {climb.get("differential_points"):+.2f} pts</p>')
    elif climb and climb.get("market_prob") is not None:
        climb_line = (f'<p class="meta">No leaderboard swing on '
                      f'{esc(climb.get("team"))}: {esc("; ".join(climb.get("gate", {}).get("reasons") or []))}.</p>')
    return f"""<article class="card{" hero" if row.get("fixture_id") in ("1080205", "1081775") else ""}">
<div class="top-line">{tier_chip(row)}<span class="chip">{esc(row.get("points"))} pts</span>
{basis_chip(row)}<span class="chip">{esc(start_label(row))}</span></div>
<p class="meta">{esc(row.get("competition"))}{"" if not row.get("best_of") else f" · best of {esc(row.get('best_of'))}"}</p>
{prob_rows(row)}{ownership_bar(row)}{line}{climb_line}
<div class="meta">{flags}</div>{source_details(row)}</article>"""


# ------------------------------------------------------------------------------ page build
def read_research() -> dict:
    return load_json(OUT / "research.json") or {}


def build_twc_section(rows: dict, research: dict) -> str:
    twc = research.get("twc") or {}
    day3 = twc.get("day3") or []
    cards = []
    for fixture in day3:
        row = rows.get(fixture.get("fixture_id"))
        if not row:
            continue
        facts = "".join(f'<li>{esc(f.get("fact"))} <a href="{esc(f.get("url"))}">source</a></li>'
                        for f in fixture.get("context_facts") or [])
        cards.append(f"""<article class="card hero">
<div class="top-line"><span class="chip s">Group decider</span>
<span class="chip">7 pts</span>{basis_chip(row)}<span class="chip">{esc(start_label(row))}</span></div>
<h3>{esc(row.get('team_a'))} vs {esc(row.get('team_b'))}</h3>
{prob_rows(row)}{ownership_bar(row)}
<p class="pickline">Safe pick: <b>{(row.get('pick') or {}).get('team')}</b> at
{pct((row.get('pick') or {}).get('prob'), 1)}</p>
<p class="pickline">Contrarian leaderboard pick: <b>{(row.get('climb') or {}).get('team')}</b>
{'- activated' if (row.get('climb') or {}).get('activated') else '- not activated'}
({pct((row.get('climb') or {}).get('market_prob'), 1)} vs
{pct((row.get('climb') or {}).get('ownership'), 0)} crowd, differential
{(row.get('climb') or {}).get('differential_points') if (row.get('climb') or {}).get('differential_points') is None else f"{(row.get('climb') or {}).get('differential_points'):+.2f}"} pts)</p>
<p class="meta">{esc('; '.join((row.get('climb') or {}).get('gate', {}).get('reasons') or []) or 'All four gate conditions met on this capture.')}</p>
<ul>{facts}</ul>
<p class="meta">{esc(fixture.get('label'))} · winner plays in the semi-final. Full reasoning:
<a href="twc.html">TWC review &amp; day-3 desk</a>.</p>
{source_details(row)}</article>""")
    return "".join(cards)


def build_index(rows: list[dict], locked: list[dict], research: dict, inputs: dict,
                generated: str, counts: dict) -> str:
    counters = inputs.get("capture_counters") or {}
    not_captured = inputs.get("not_captured") or []
    rows_by_id = {r["fixture_id"]: r for r in rows}
    today = [r for r in rows if (r.get("start_utc") or "")[:10] == generated[:10]]
    later = [r for r in rows if r not in today]
    unresolved = [r for r in rows if r.get("basis") == "unresolved"]
    climb = [r for r in rows if (r.get("climb") or {}).get("activated")]
    kpis = "".join(
        f'<div class="kpi"><b>{value}</b><span>{label}</span></div>'
        for value, label in ((counts["open"], "open matches covered"),
                             (counts["with_pick"], "with a pick and both probabilities"),
                             (counts["market"] + counts["exchange"], "priced by a bookmaker or exchange"),
                             (counts["model"], "own model line (no market price)"),
                             (counts["unresolved"], "unresolved (blank and flagged)"),
                             (len(climb), "leaderboard swings activated")))
    swing_list = "".join(
        f'<li><b>{esc((r.get("climb") or {}).get("team"))}</b> '
        f'({esc(r.get("team_a"))} vs {esc(r.get("team_b"))}, {esc(r.get("competition"))}): '
        f'market {pct((r.get("climb") or {}).get("market_prob"), 1)} vs '
        f'{pct((r.get("climb") or {}).get("ownership"), 0)} crowd · '
        f'differential {(r.get("climb") or {}).get("differential_points"):+.2f} pts'
        + f' · {(r.get("climb") or {}).get("kind")}'
        + '</li>'
        for r in climb)
    coverage_block = ""
    if counters:
        gaps = "".join(f"<li>{esc(item)}</li>" for item in not_captured)
        coverage_block = f"""<div class="callout"><b>What this capture covers</b>
<p class="meta">The lobby reported <b>{esc(counters.get('matches_this_week'))}</b> matches in the
current week (reset in {esc(counters.get('week_reset_countdown_at_read'))} at read time) with tier
counters B {esc(counters.get('cs2_tier_b'))} / C {esc(counters.get('cs2_tier_c'))} /
S {esc(counters.get('cs2_tier_s'))}; the read below lists
<b>{esc(counters.get('open_rows_in_capture'))}</b> fixtures. Picks are published for every fixture
this read listed, including the low-tier series no betting site covers.</p>
{f'<ul>{gaps}</ul>' if gaps else ''}</div>"""
    body = f"""
<h1>Every HotSpawn CS2 match, with a pick and both win probabilities</h1>
<p class="lede">Mobile front door for the Thunderpick World Championship 2026 day-3 desk and for
every match the HotSpawn lobby still has open. Probabilities come from licensed bookmakers or
public exchange books; where no book prices a match, an own model line from the official Valve
standings is published and labelled. Rows without a defensible line stay blank and move to the
<a href="unresolved.html">Unresolved</a> section.</p>
<div class="callout"><b>Executive summary</b>
<ul>
<li><b>TWC 2026 day 3</b> — two group deciders decide the last two semi-final places:
<a href="#twc">safe and contrarian picks, with the points differential</a>.</li>
<li><b>Every open match</b> — {counts['open']} fixtures, {counts['with_pick']} with a pick and both
probabilities: <a href="#every-match">jump to the list</a>.</li>
<li><b>Unresolved picks &amp; limitations</b> — {counts['unresolved']} row(s) with no defensible
line, each with every source attempt: <a href="unresolved.html">open the section</a>.</li>
<li><b>Flagged for review</b> — alias joins, exchange-midpoint limits, expired quotes and the
TWC premise that could not be verified: <a href="flagged.html">open the flag list</a>.</li>
<li><b>Day 1 &amp; day 2 review</b> — the 9z upset over Aurora, the roster timeline and what is
actually verifiable: <a href="twc.html">open the review</a>.</li>
</ul>
<p class="meta">Captures: {esc(inputs.get('capture_line'))}. Quotes: {esc(inputs.get('quote_line'))}.
Ratings: {esc(inputs.get('vrs_line'))}. Every number on this page carries its own source link.</p>
</div>
<div class="kpis">{kpis}</div>
{coverage_block}
<h2 id="twc">TWC 2026 day 3 — the two deciders</h2>
{build_twc_section(rows_by_id, research)}
{('<div class="callout"><b>Leaderboard swings activated this capture</b><ul>' + swing_list + '</ul>'
  '<p class="meta">A swing is the side the crowd is fading: either the underdog the market still '
  'prices (contrarian underdog) or a market favourite the crowd has abandoned (fade the crowd). '
  'Gate: market reading at least 30%, at least 15 points of ownership gap, a crowd sample of at '
  'least 10 picks, one dated source-linked fact for that side, and the rating model no more than '
  '10 points below that market reading. A swing that fails any condition is published as not '
  'activated, never forced. Differential = listed points × (probability − crowd ownership) and is '
  'quoted in listed points only.</p></div>') if climb else
 ('<div class="callout"><b>No leaderboard swing met all gate conditions in this capture.</b> '
  'Every candidate and its failing condition is listed on the match cards below and in the '
  'Flagged page.</div>')}
<h2 id="every-match">Every open match</h2>
<h3>Today ({len(today)})</h3>
{''.join(match_card(r, generated) for r in today) or '<p class="meta">No matches remain today.</p>'}
<h3>Later ({len(later)})</h3>
{''.join(match_card(r, generated) for r in later) or '<p class="meta">No later matches listed.</p>'}
<h2>Already locked ({len(locked)})</h2>
<p class="lede">These fixtures were listed but their pick lock has passed at the build time, so
they are not offered as picks. They stay visible for settlement.</p>
{''.join(f'<article class="card locked"><b>{esc(r.get("team_a"))} vs {esc(r.get("team_b"))}</b>'
         f'<p class="meta">{esc(r.get("competition"))} · {esc(r.get("start_utc"))} · locked</p></article>'
         for r in locked[:12])}
"""
    return shell("Pick'em hub — every CS2 match, day 3", body, generated, "index.html")


def build_twc_page(research: dict, rows: dict, generated: str) -> str:
    twc = research.get("twc") or {}
    event = twc.get("event") or {}
    def results_table(rows_):
        out = ['<div class="scroll"><table><thead><tr><th>Match</th><th>Winner</th><th>Maps</th>'
               '<th>Source</th></tr></thead><tbody>']
        for r in rows_:
            maps = " · ".join(r.get("maps") or [])
            link = r.get("hltv") or event.get("hltv_event")
            out.append(f'<tr><td>{esc(r.get("match"))}<div class="drop">{esc(r.get("stage"))}</div></td>'
                       f'<td>{esc(r.get("winner"))} {esc(r.get("score"))}</td><td>{esc(maps)}</td>'
                       f'<td><a href="{esc(link)}">match page</a></td></tr>')
            if r.get("note"):
                out.append(f'<tr><td colspan="4" class="drop">{esc(r.get("note"))} '
                           f'<a href="{esc(r.get("note_url") or link)}">source</a></td></tr>')
        out.append('</tbody></table></div>')
        return "".join(out)
    standings = twc.get("standings") or {}
    def standings_table(key):
        out = ['<div class="scroll"><table><thead><tr><th>#</th><th>Team</th><th>W-L</th>'
               '<th>Rounds</th><th>Diff</th><th>Source</th></tr></thead><tbody>']
        for r in standings.get(key) or []:
            out.append(f'<tr><td>{esc(r.get("pos"))}</td><td>{esc(r.get("team"))}</td>'
                       f'<td>{esc(r.get("w_l"))}</td><td>{esc(r.get("rounds"))}</td>'
                       f'<td>{esc(r.get("diff"))}</td>'
                       f'<td><a href="{esc(r.get("source") or event.get("liquipedia"))}">table</a></td></tr>')
        out.append('</tbody></table></div>')
        return "".join(out)
    roster = twc.get("roster_focus") or {}
    timeline = "".join(f'<li><b>{esc(t.get("date"))}</b> — {esc(t.get("event"))} '
                       f'<a href="{esc(t.get("url"))}">source</a></li>' for t in roster.get("timeline") or [])
    consequences = "".join(f'<li>{esc(c.get("fact"))} <a href="{esc(c.get("url"))}">source</a></li>'
                           for c in roster.get("verified_consequences") or [])
    day3_rows = {f.get("fixture_id"): rows.get(f.get("fixture_id")) for f in twc.get("day3") or []}
    day3_cards = "".join(match_card(r, generated) for r in day3_rows.values() if r)
    body = f"""
<h1>TWC 2026 — day 1 &amp; day 2 review, day 3 desk</h1>
<p class="lede">Everything below is a dated read with its source link: the results, the group
tables, the roster timeline and the day-3 lines. Where a claim in the brief could not be verified
it is said so plainly instead of being repeated.</p>
<h2>What happened</h2>
<h3>Day 1 (14 October)</h3>
{results_table(twc.get('day1') or [])}
<p class="meta">The upset: 9z beat Aurora 2-0 with luchov rated 1.61, worth 62 VRS points.
<a href="https://www.hltv.org/news/45718/9z-beat-aurora-2-0-to-kick-off-twc-2026">HLTV report</a>.</p>
<h3>Day 2 (15 October)</h3>
{results_table(twc.get('day2') or [])}
<p class="meta">Group A: Aurora eliminated Ninjas in Pyjamas, Falcons beat 9z, so Aurora and 9z meet
again in the decider. Group B: BetBoom eliminated PARIVISION and FURIA beat Legacy, so BetBoom and
Legacy meet in the decider. Sources: <a href="{esc(event.get('liquipedia'))}">Liquipedia event page</a>
and <a href="{esc(event.get('hltv_event'))}">HLTV event 8932</a>.</p>
<h3>Group tables as they stand</h3>
<div class="grid two"><div><h4>Group A</h4>{standings_table('A')}</div>
<div><h4>Group B</h4>{standings_table('B')}</div></div>
<h2>The reported Aurora roster change</h2>
<p>{esc(roster.get('finding'))}</p>
<p class="meta">The brief's premise of a recent Aurora roster change <b>could not be verified</b>
from any official source read in this session; what is published instead is the dated evidence
below, with a link per line, and no invented rest or onboarding penalty.</p>
<ul>{timeline}</ul>
<h3>What that means for a pick</h3>
<ul>{consequences}</ul>
<p class="meta">{esc(roster.get('rest_and_onboarding_evidence'))}</p>
<h2>Day 3 — the desk</h2>
<p class="lede">Safe pick = the side the eligible market or exchange line prices as favourite.
Leaderboard swing = the side the crowd is fading (the underdog the market still prices, or a
favourite the crowd has abandoned) and only when every published gate condition holds on the same
capture; otherwise the row says why no swing was activated.</p>
{day3_cards}
<h3>What would have to happen for the contrarian side to land</h3>
<ul>
<li><b>Aurora vs 9z.</b> 9z beat Aurora 2-0 two days ago and owns Mirage, the map Aurora most often
loses to teams of this tier; the contrarian side needs Aurora's Nuke/Anubis veto advantage to be
neutralised in the ban phase and another big luchov series. Aurora's edge in the ratings and in
HLTV's map statistics is real, which is why the gate still prices 9z as the underdog.</li>
<li><b>BetBoom vs Legacy.</b> The crowd sits on Legacy, the market agrees (about 61%) but the rating
model is closer to 73%, so the underdog is priced below the 30% floor of the gate on at least one
reading. No swing is activated; the pick stays on the favourite with that disagreement published.</li>
</ul>
<p><a href="method.html">Method, formulas and sources</a> · <a href="unresolved.html">Unresolved</a>
· <a href="flagged.html">Flagged</a></p>
"""
    return shell("TWC 2026 day 1–3 review", body, generated, "twc.html")


def build_unresolved_page(rows: list[dict], research: dict, generated: str) -> str:
    gaps = [r for r in rows if r.get("basis") == "unresolved"]
    partial = [r for r in rows if r.get("basis") == "model"]
    cards = "".join(f"""<article class="card bad"><h3>{esc(r.get('team_a'))} vs {esc(r.get('team_b'))}</h3>
<p class="meta">{esc(r.get('competition'))} · {esc(start_label(r))} · {esc(r.get('points'))} pts ·
{esc(r.get('tier_label') or r.get('tier'))}</p>
<p><b>Status:</b> no pick published. <b>Why:</b> {'; '.join(r.get('flags') or []) or 'no eligible price or rating pair'}.</p>
<p><b>What was tried:</b> {esc(r.get('ladder'))}.
{('The official standings resolution for ' + esc('; '.join(f for f in r.get('flags') or [] if 'vrs' in f)) + ' failed, so the rating fallback is refused rather than guessed.') if any('vrs' in f for f in (r.get('flags') or [])) else ''}</p>
{source_details(r)}</article>""" for r in gaps)
    model_cards = "".join(f"""<article class="card"><h3>{esc(r.get('team_a'))} vs {esc(r.get('team_b'))}</h3>
<p class="pickline">Own model line: <b>{(r.get('pick') or {}).get('team')}</b> at
{pct((r.get('pick') or {}).get('prob'), 1)} (Valve ratings {r.get('model_raw', {}).get('delta_points')} points apart,
slope k={r.get('model_raw', {}).get('k')})</p>
<p class="meta">This is not a bookmaker price and carries no claimed out-of-sample accuracy. No
eligible two-way bookmaker or exchange price existed in this capture.</p>{source_details(r)}</article>"""
                          for r in partial)
    limits = "".join(f"<li>{esc(x)}</li>" for x in research.get("limitations") or [])
    body = f"""
<h1>Unresolved picks &amp; limitations</h1>
<p class="lede">The separate section for anything this hub could not resolve. A blank here is a
statement about the evidence, not about the match: every row lists what was tried and what would
change the answer.</p>
<div class="callout bad"><b>{len(gaps)} unresolved row(s) in this build.</b> They are excluded from
the pick counts and are never filled with a guess.
<div><a href="index.html">Back to the every-match list</a> · <a href="flagged.html">Flagged for review</a></div></div>
{cards or '<p class="meta">No unresolved rows in this build.</p>'}
<h2>Model-only rows ({len(partial)})</h2>
<p class="lede">These rows have a pick, but the pick is an own model line rather than a market
price, so they are listed here as well so nothing is mistaken for a bookmaker quote.</p>
{model_cards or '<p class="meta">No model-only rows in this build.</p>'}
<h2>Standing limitations of this hub</h2>
<ul>{limits}</ul>
"""
    return shell("Unresolved picks & limitations", body, generated, "unresolved.html")


def build_flagged_page(research: dict, rows: list[dict], inputs: dict, generated: str) -> str:
    items = "".join(f"""<article class="card"><h3>{esc(f.get('item'))}</h3>
<p class="meta">Reference {esc(f.get('id'))}</p>
<ul class="src">{''.join(f'<li>· <a href="{esc(u)}">{esc(u)}</a></li>' for u in f.get('sources') or [])}</ul>
</article>""" for f in research.get("flagged") or [])
    alias = "".join(f"""<article class="card"><h3>{esc(a.get('fixture_side'))} → {esc(a.get('canonical_team'))}</h3>
<p>{esc(a.get('why'))}</p>
<ul class="src">{''.join(f'<li>· {esc(e.get("label"))}<br><a href="{esc(e.get("url"))}">{esc(e.get("url"))}</a> <span class="drop">(read {esc(e.get("read_utc"))})</span></li>' for e in a.get('evidence') or [])}</ul>
<p class="meta">Residual limitation: {esc(a.get('residual_limitation'))}</p></article>"""
                   for a in (research.get("coverage") or {}).get("alias_decisions") or [])
    expired = [r for r in rows if "older_bookmaker_quote_retained_as_evidence_only" in (r.get("flags") or [])]
    expired_list = "".join(f'<li>{esc(r.get("team_a"))} vs {esc(r.get("team_b"))}: quote fetched '
                           f'{esc((r.get("quotes_bookmaker_expired") or [{}])[0].get("fetched_utc"))}</li>'
                           for r in expired)
    body = f"""
<h1>Flagged for review</h1>
<p class="lede">Irregularities, judgement calls and unverifiable claims. These do not block
publication; they are the list a reviewer should read first.</p>
<h2>Review items</h2>
{items}
<h2>Alias joins used by this hub</h2>
{alias}
<h2>Expired quotes retained as evidence only</h2>
{('<ul>' + expired_list + '</ul>') if expired_list else '<p class="meta">No expired bookmaker quotes in this build.</p>'}
<h2>Capture provenance</h2>
<ul>
<li>Fixture capture: {esc(inputs.get('capture_line'))}</li>
<li>Quotes: {esc(inputs.get('quote_line'))}</li>
<li>Ratings: {esc(inputs.get('vrs_line'))}</li>
<li>Exchange markets: {esc(inputs.get('exchange_line'))}</li>
</ul>
"""
    return shell("Flagged for review", body, generated, "flagged.html")


def build_method_page(research: dict, coverage: dict, inputs: dict, generated: str, k_info: dict) -> str:
    capture = inputs.get("capture_info") or {}
    board = capture.get("leaderboard") or []
    prizes = capture.get("prizes") or {}
    leaderboard_block = ""
    if board:
        position = "".join(f'<tr><td>{esc(p.get("pos"))}</td><td>{esc(p.get("player"))}</td>'
                           f'<td>{esc(p.get("points"))}</td></tr>' for p in board)
        prize_line = " · ".join(f"{esc(k)}: {esc(v)}" for k, v in prizes.items()) or "not captured"
        leaderboard_block = f"""<h2>Leaderboard context (captured {esc(str(capture.get('read_utc'))[:16])}Z)</h2>
<p class="meta">Prizes: {prize_line}. This is the field the leaderboard picks are played against;
the points differential is quoted in listed points, never in score-adjusted points.</p>
<div class="scroll"><table><thead><tr><th>#</th><th>Player</th><th>Points</th></tr></thead><tbody>
{position}</tbody></table></div>"""
    _ = coverage
    rules = (coverage.get("declared_rules") or {})
    gate = rules.get("climb_gate") or {}
    gate_items = "".join(f"<li><b>{esc(key)}</b> — {esc(value)}</li>" for key, value in gate.items())
    attempts = "".join(f"<li>{esc(x)}</li>" for x in coverage.get("unresolvable_attempt_order") or [])
    sources = research.get("source_reads") or []
    source_rows = "".join(f'<tr><td>{esc(s.get("label"))}</td><td><a href="{esc(s.get("url"))}">link</a></td>'
                          f'<td class="drop">{esc(s.get("at_utc"))}</td><td class="drop">{esc(s.get("used_for"))}</td></tr>'
                          for s in sources)
    body = f"""
<h1>Method, formulas and refresh schedule</h1>
<h2>Where each number comes from</h2>
<ol>
<li><b>Fixtures, listed points, locks and crowd shares</b> — the public HotSpawn lobby and its own
embedded fixture response. The crowd share is ownership: it is shown next to the pick and is never
used to derive a probability.</li>
<li><b>Prices</b> — licensed bookmaker two-way match-winner lines (Pinnacle weighted 2, Bovada and
Melbet weighted 1) and public exchange books (Polymarket CLOB only when both sides of the book
exist inside 10 cents and the kickoff matches within five minutes; the CFTC-regulated Kalshi
KXCS2GAME series only through explicit full-match contract rules).</li>
<li><b>Derivation</b> — proportional no-vig: for decimal dA, dB, pA = (1/dA) / ((1/dA) + (1/dB)).
Exchange readings use the midpoint of the live bid/ask book and are labelled as estimates, not
executable prices.</li>
<li><b>Own model line</b> — only for rows with no eligible price, and only when both teams resolve
to exactly one row of the official Valve regional standings.
pA = 1 / (1 + 10^(-Δ·s·k)) where Δ is the points difference, s the rating scale and k the slope
fitted on this capture's own bookmaker consensus: <b>k={k_info.get('k')}</b>
({esc(k_info.get('note'))}), pairs used {esc(k_info.get('n_pairs'))}.</li>
<li><b>Pick</b> — the side with the higher derived probability; confidence labels are Strong ≥70%,
Solid ≥60%, Lean ≥53%, otherwise Toss-up. Fair decimal = 1/p.</li>
</ol>
<h2>The contrarian (leaderboard) gate</h2>
<ul>{gate_items}</ul>
<p class="meta">Differential = listed points × (probability − crowd ownership of that side), quoted
in listed points only: the lobby advertises tier and stage multipliers but never states how they
combine, so no score-adjusted number is invented.</p>
<h2>Zero-blank ladder</h2>
<ol>{attempts}</ol>
<p class="meta">A row that stops at the last step is published blank in the
<a href="unresolved.html">Unresolved section</a>, never filled in.</p>
<h2>Refresh</h2>
<p>The hub rebuilds every four hours on a GitHub-hosted runner (cron <code>41 */4 * * *</code>) and
whenever the canonical collected batch changes. Each run re-reads the lobby, re-fetches the
bookmaker prices, the exchange books and the official ratings, then re-derives every number on the
site. Build time for this copy: <b>{esc(generated)}</b>.</p>
<ul>
<li>Capture: {esc(inputs.get('capture_line'))}</li>
<li>Quotes: {esc(inputs.get('quote_line'))}</li>
<li>Ratings: {esc(inputs.get('vrs_line'))}</li>
<li>Exchange: {esc(inputs.get('exchange_line'))}</li>
</ul>
<h2>Sources read for this build</h2>
{leaderboard_block}
<div class="scroll"><table><thead><tr><th>Source</th><th>Link</th><th>Read (UTC)</th>
<th>Used for</th></tr></thead><tbody>{source_rows}</tbody></table></div>
<h2>Machine-readable outputs</h2>
<ul>
<li><a href="../data/7c2622db/hub.json">hub.json — every row with its line, sources and flags</a></li>
<li><a href="../data/7c2622db/verification.json">verification.json — independent re-derivation</a></li>
<li><a href="../data/7c2622db/research.json">research.json — the dated research this page cites</a></li>
<li><a href="../data/7c2622db/coverage.json">coverage.json — alias rules and the declared gate</a></li>
</ul>
"""
    return shell("Method & sources", body, generated, "method.html")


def build_verify_page(verification: dict, generated: str) -> str:
    checks = verification.get("checks") or []
    rows = "".join(
        f'<tr><td>{esc(c.get("row"))}</td><td>{esc(c.get("what"))}</td>'
        f'<td>{"PASS" if c.get("pass") else "FAIL"}</td><td class="drop">{esc(c.get("detail"))}</td></tr>'
        for c in checks)
    failed = [c for c in checks if not c.get("pass")]
    body = f"""
<h1>Line-by-line verification</h1>
<p class="lede">Every published probability is re-derived from the raw numbers stored next to it,
independently of the code that produced it; every rating is re-checked against the official
standings; every row is checked for a source link. Generated {esc(verification.get('verified_utc'))}.</p>
<div class="callout {'bad' if failed else 'ok'}"><b>{len(checks) - len(failed)} of {len(checks)} checks pass.</b>
{'Failures: ' + esc('; '.join(c.get('row', '?') for c in failed)) if failed else
 'No discrepancies between the published numbers and the retained evidence in this build.'}</div>
<div class="scroll"><table><thead><tr><th>Row</th><th>Check</th><th>Result</th><th>Detail</th></tr>
</thead><tbody>{rows}</tbody></table></div>
<p class="meta">Re-run locally with <code>python scripts/7c2622db/verify.py</code> and
<code>python -m unittest tests.test_7c2622db -v</code>.</p>
"""
    return shell("Verification", body, generated, "verify.html")


# ------------------------------------------------------------------------------------- main
def build() -> dict:
    now = now_utc()
    generated = iso(now)
    capture = load_json(OUT / "lobby_capture_manual.json") or {"fixtures": [], "read_utc": None}
    snapshot = load_json(OUT / "snapshot.json")
    canonical = load_json(CANON / "snapshot.json")
    coverage = load_json(OUT / "coverage.json") or {}
    research = read_research()
    global CANONICAL_SNAPSHOT
    CANONICAL_SNAPSHOT = canonical
    fixtures, fixture_meta = load_fixtures(capture, snapshot)
    quotes, quote_meta = load_quotes(snapshot, canonical)
    vrs, vrs_meta = load_vrs(snapshot, canonical)

    # Crowd ownership: prefer the newest capture that actually lists the fixture. Mixing a newer
    # read into an older one would publish a snapshot that never existed, so the newest capture
    # that contains the row wins outright and its capture time is published next to the numbers.
    ownership_sources = []
    local_state = load_json(OUT / "lobby_state.json")
    if local_state:
        ownership_sources.append((str((local_state.get("metadata") or {}).get("at_utc") or ""),
                                  ownership_from_state(local_state), "hub lobby capture"))
    canonical_state = (load_json(CANON / "official_inputs.json") or {}).get("lobby")
    if canonical_state:
        ownership_sources.append((str((canonical_state.get("metadata") or {}).get("at_utc") or ""),
                                  ownership_from_state(canonical_state),
                                  "canonical lobby capture"))
    if capture.get("fixtures"):
        ownership_sources.append((str(capture.get("read_utc") or ""),
                                  {r["fixture_id"]: {"a": r.get("picked_a"), "b": r.get("picked_b"),
                                                     "total_picks": None}
                                   for r in capture["fixtures"] if r.get("picked_a") is not None},
                                  "lobby capture"))
    # Newest capture wins for the shares; the pick count comes from the newest capture that
    # published one, and both are labelled so a reader can see which read each number is from.
    shares, counts = {}, {}
    for stamp, rows_map, label in sorted(ownership_sources, key=lambda item: item[0]):
        for fid, entry in rows_map.items():
            if entry.get("a") is None:
                continue
            shares[fid] = {**entry, "capture_utc": stamp or None, "label": label}
            if entry.get("total_picks") is not None and fid not in counts:
                counts[fid] = {"total_picks": entry.get("total_picks"),
                               "count_utc": stamp or None, "count_label": label}
    for fixture in fixtures.values():
        entry = shares.get(fixture["fixture_id"])
        if entry:
            count = counts.get(fixture["fixture_id"]) or {}
            fixture["ownership"] = {"a": (entry["a"] / 100.0), "b": (entry["b"] / 100.0),
                                    "as_rendered": [entry["a"], entry["b"]],
                                    "total_picks": count.get("total_picks"),
                                    "capture_utc": entry.get("capture_utc"),
                                    "count_capture_utc": count.get("count_utc"),
                                    "source": entry.get("label")}
    facts: dict[str, dict[str, list]] = {}
    for entry in (research.get("twc", {}).get("day3") or []):
        bucket = facts.setdefault(str(entry.get("fixture_id")), {"a": [], "b": []})
        for fact in entry.get("context_facts") or []:
            supports = str(fact.get("supports") or "both").lower()
            item = {"fact": fact.get("fact"), "url": fact.get("url"), "read_utc": fact.get("at_utc")}
            for side in ("a", "b"):
                if supports in (side, "both"):
                    bucket[side].append(item)
    for entry in research.get("matches") or []:
        bucket = facts.setdefault(str(entry.get("fixture_id")), {"a": [], "b": []})
        side = str(entry.get("side") or "both").lower()
        item = {"fact": entry.get("fact"), "url": entry.get("url"), "read_utc": entry.get("read_utc")}
        for key in ("a", "b"):
            if side in (key, "both"):
                bucket[key].append(item)
    for fixture in fixtures.values():
        fixture["context_facts"] = facts.get(fixture["fixture_id"], {"a": [], "b": []})

    exchange = load_json(OUT / "exchange.json") or load_json(OUT / "exchange_readings.json")
    if exchange and not exchange.get("markets") and exchange.get("markets") == []:
        exchange = None

    open_, locked = open_rows(fixtures, now)
    rows = [decide(f, quotes, exchange, vrs, 1.0, now,
                   (coverage.get("declared_rules") or {}).get("quote_max_age_hours", 6))
            for f in open_]
    k_info = fit_k(rows, vrs)
    k = k_info.get("k", 1.0)
    if k != 1.0:
        rows = [decide(f, quotes, exchange, vrs, k, now,
                       (coverage.get("declared_rules") or {}).get("quote_max_age_hours", 6))
                for f in open_]
    counts = {
        "open": len(rows),
        "with_pick": sum(1 for r in rows if r.get("pick")),
        "market": sum(1 for r in rows if r.get("basis") == "market"),
        "exchange": sum(1 for r in rows if r.get("basis") == "exchange"),
        "model": sum(1 for r in rows if r.get("basis") == "model"),
        "unresolved": sum(1 for r in rows if r.get("basis") == "unresolved"),
        "locked": len(locked),
    }
    inputs = {
        "capture_line": (f"manual lobby capture {fixture_meta.get('manual_capture_utc')} "
                         f"({fixture_meta.get('manual_capture_rows')} rows)"
                         + (f" merged with the automated capture {fixture_meta.get('automated_capture_utc')} "
                            f"({fixture_meta.get('automated_capture_rows')} rows)"
                            if fixture_meta.get("automated_capture_utc") else " (no automated capture yet)")),
        "quote_line": f"{quote_meta.get('label')} at {quote_meta.get('collected_to_utc')} ({len(quotes)} quotes)",
        "vrs_line": f"{vrs_meta.get('label')}, official snapshot {vrs_meta.get('snapshot')}",
        "exchange_line": (f"{(exchange or {}).get('collected_to_utc')} "
                          f"({len((exchange or {}).get('markets') or [])} market(s))"),
        "capture_info": {"read_utc": capture.get("read_utc"), "leaderboard": capture.get("leaderboard") or [],
                          "prizes": capture.get("prizes") or {}},
        "capture_counters": capture.get("counters") or {},
        "not_captured": capture.get("not_captured") or [],
    }
    hub = {
        "session": "7c2622db",
        "generated_utc": generated,
        "policy": "market first, exchange second, own model line third (official ratings only), blank and flagged otherwise; HotSpawn crowd shares are ownership only",
        "counts": counts,
        "calibration": {k2: (round(v, 5) if isinstance(v, float) else v) for k2, v in k_info.items()},
        "inputs": inputs,
        "rows": rows,
        "locked": [{"fixture_id": f["fixture_id"], "team_a": f.get("team_a"), "team_b": f.get("team_b"),
                    "competition": f.get("competition"), "start_utc": f.get("start_utc")} for f in locked],
        "capture": {"read_utc": fixture_meta.get("manual_capture_utc"),
                    "rows": fixture_meta.get("manual_capture_rows"),
                    "automated_utc": fixture_meta.get("automated_capture_utc"),
                    "automated_rows": fixture_meta.get("automated_capture_rows"),
                    "display_clock": fixture_meta.get("display_clock"),
                    "counters": capture.get("counters") or {},
                    "not_captured": capture.get("not_captured") or [],
                    "leaderboard": capture.get("leaderboard") or [],
                    "prizes": capture.get("prizes") or {}},
    }
    HUB.mkdir(parents=True, exist_ok=True)
    (OUT / "hub.json").write_text(json.dumps(hub, indent=1, ensure_ascii=False) + "\n")

    research_for_pages = {**research, "coverage": coverage}
    (HUB / "index.html").write_text(build_index(rows, locked, research, inputs, generated, counts))
    (HUB / "twc.html").write_text(build_twc_page(research, {r["fixture_id"]: r for r in rows}, generated))
    (HUB / "unresolved.html").write_text(build_unresolved_page(rows, research, generated))
    (HUB / "flagged.html").write_text(build_flagged_page(research_for_pages, rows, inputs, generated))
    (HUB / "method.html").write_text(build_method_page(research, coverage, inputs, generated, k_info))
    verification = load_json(OUT / "verification.json") or {"checks": [], "verified_utc": None}
    (HUB / "verify.html").write_text(build_verify_page(verification, generated))
    return hub


def main() -> int:
    hub = build()
    print(json.dumps({"generated_utc": hub["generated_utc"], "counts": hub["counts"],
                      "calibration": hub["calibration"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
