#!/usr/bin/env python3
"""Session 961e163a — build the verified pick board from raw external quotes.

Reads (never writes) the raw evidence produced by ``scripts/961/collect_961.py`` plus the
previously published egamersworld evidence, joins each external quote to the exact Hotspawn
fixture it prices, removes the bookmaker margin per source, and averages the sources.

Rules (published on every generated page):
  1. Only full-match (series) winner markets from the named external source are used.
  2. Per source: q = 1/decimal; p_a = q_a / (q_a + q_b)  -> the source's no-vig share.
  3. Consensus: arithmetic mean of the per-source no-vig shares.
  4. Hotspawn's own crowd pick percentage is NEVER an input (it is not read by this script).
  5. A fixture with no verified external quote is published blank with the flag
     ``no_external_line`` — nothing is estimated, filled in or inferred.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "961")
LOBBY = os.path.join(OUT, "lobby.json")
QUOTES = os.path.join(OUT, "quotes.json")
BOARD = os.path.join(OUT, "board.json")

SUFFIXES = [" esports", " esport", " gaming", " team", " club", " academy"]
PREFIXES = ["team "]


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).strip().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    for suf in SUFFIXES:
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
    for pre in PREFIXES:
        if s.startswith(pre):
            s = s[len(pre):].strip()
    return re.sub(r"\s+", " ", s)


def tokens(name: str) -> set:
    return {t for t in norm(name).split() if len(t) > 1}


def teams_match(a: str, b: str) -> bool:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    inter = ta & tb
    if not inter:
        return False
    return len(inter) / min(len(ta), len(tb)) >= 0.5 or na in nb or nb in na


def parse_iso(v):
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.strptime(str(v)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def hours_between(a, b):
    if not a or not b:
        return None
    return abs((a - b).total_seconds()) / 3600.0


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def extra_quotes_from_existing_evidence():
    """egamersworld evidence already in the repo (read-only), re-stamped as its own source."""
    out = []
    for path, game in ((os.path.join(DATA, "cs2_odds_egamersworld.json"), "cs2"),
                       (os.path.join(DATA, "lol_odds_egamersworld.json"), "lol")):
        doc = load_json(path)
        if not doc:
            continue
        for row in doc.get("rows") or []:
            a, b = row.get("decimal_odds_a"), row.get("decimal_odds_b")
            if not a or not b:
                continue
            out.append({
                "source_key": "egamersworld",
                "source_name": "egamersworld.com odds widget",
                "source_kind": "esports odds aggregator (external to Hotspawn)",
                "game": game,
                "source_url": row.get("source_url"),
                "source_event_id": row.get("fixture_id"),
                "source_league": row.get("competition"),
                "market_type": "match winner (moneyline)",
                "market_is_live": False,
                "source_reported_start_utc": row.get("official_start_utc"),
                "retrieved_at_utc": row.get("retrieved_at_utc") or doc.get("generated_at_utc"),
                "team_a_name": row.get("team_a"),
                "team_b_name": row.get("team_b"),
                "raw_price_format": "decimal",
                "raw_price_a": a,
                "raw_price_b": b,
                "decimal_odds_a": a,
                "decimal_odds_b": b,
                "decimal_odds_derived": False,
                "evidence_file": os.path.relpath(path, ROOT),
                "join_note": row.get("join_note"),
            })
    return out


def fallback_book_quotes():
    """Previously captured Pinnacle/Bovada quotes, used only if a fresh capture is empty."""
    doc = load_json(os.path.join(DATA, "odds.json"))
    if not doc:
        return []
    out = []
    for line in doc.get("lines") or []:
        if line.get("source_key") not in ("pinnacle", "bovada"):
            continue
        if not line.get("decimal_odds_a") or not line.get("decimal_odds_b"):
            continue
        low = str(line.get("source_league") or "").lower()
        link = str(line.get("source_public_url") or "").lower()
        game = "cs2" if ("cs2" in low or "counter" in low or "counter-strike" in link) else (
            "lol" if ("lol" in low or "league-of-legends" in link) else None)
        if game is None:
            continue
        out.append({
            "source_key": line["source_key"],
            "source_name": line.get("source_name"),
            "source_kind": line.get("source_kind"),
            "game": game,
            "source_url": line.get("source_public_url") or line.get("source_api_url"),
            "source_event_id": line.get("source_event_id"),
            "source_league": line.get("source_league"),
            "market_type": line.get("market_type"),
            "market_is_live": bool(line.get("market_is_live")),
            "source_reported_start_utc": line.get("start_time_utc"),
            "retrieved_at_utc": line.get("retrieved_at_utc"),
            "team_a_name": line.get("team_a_name"),
            "team_b_name": line.get("team_b_name"),
            "raw_price_format": line.get("raw_price_format"),
            "raw_price_a": line.get("raw_price_a"),
            "raw_price_b": line.get("raw_price_b"),
            "decimal_odds_a": line.get("decimal_odds_a"),
            "decimal_odds_b": line.get("decimal_odds_b"),
            "decimal_odds_derived": line.get("decimal_odds_derived"),
            "evidence_file": "data/odds.json (fallback capture)",
        })
    return out


def main() -> int:
    lobby = load_json(LOBBY)
    if not lobby:
        raise SystemExit("data/961/lobby.json missing — run scripts/961/collect_961.py first")
    quotes_doc = load_json(QUOTES) or {"quotes": []}
    quotes = list(quotes_doc.get("quotes") or [])

    fresh_sources = {q["source_key"] for q in quotes}
    used_fallback = False
    notes = []
    if not (fresh_sources & {"pinnacle", "bovada"}):
        try:
            fb = fallback_book_quotes()
        except Exception as exc:  # noqa: BLE001
            fb, _ = [], notes.append(f"fallback read failed: {exc}")
        if fb:
            quotes.extend(fb)
            used_fallback = True
    try:
        quotes.extend(extra_quotes_from_existing_evidence())
    except Exception as exc:  # noqa: BLE001
        notes.append(f"egamersworld evidence read failed: {exc}")

    now = datetime.now(tz=timezone.utc)
    fixtures = lobby.get("fixtures") or []
    rows = []
    for fx in fixtures:
        fx_start = parse_iso(fx.get("scheduled_start_time_utc"))
        matches = []
        for q in quotes:
            if q.get("game") and fx.get("sport") and q["game"] != fx["sport"]:
                continue
            if teams_match(q.get("team_a_name") or "", fx.get("team_a") or "") and \
               teams_match(q.get("team_b_name") or "", fx.get("team_b") or ""):
                orientation = "direct"
            elif teams_match(q.get("team_a_name") or "", fx.get("team_b") or "") and \
                    teams_match(q.get("team_b_name") or "", fx.get("team_a") or ""):
                orientation = "reversed"
            else:
                continue
            q_start = parse_iso(q.get("source_reported_start_utc"))
            delta_h = hours_between(q_start, fx_start) if (q_start and fx_start) else None
            matches.append((q, orientation, delta_h))

        per_source = {}
        for q, orientation, delta_h in matches:
            oa, ob = q.get("decimal_odds_a"), q.get("decimal_odds_b")
            if not oa or not ob or oa <= 1 or ob <= 1:
                continue
            if orientation == "reversed":
                oa, ob = ob, oa
            qa, qb = 1.0 / oa, 1.0 / ob
            p_a = qa / (qa + qb)
            src = q["source_key"]
            entry = {
                "source_key": src,
                "source_name": q.get("source_name"),
                "source_kind": q.get("source_kind"),
                "source_url": q.get("source_url") or q.get("source_api_url"),
                "event_id": q.get("source_event_id"),
                "league": q.get("source_league"),
                "market_type": q.get("market_type"),
                "market_is_live": bool(q.get("market_is_live")),
                "retrieved_at_utc": q.get("retrieved_at_utc"),
                "decimal_odds_a": round(oa, 4),
                "decimal_odds_b": round(ob, 4),
                "overround": round(qa + qb - 1.0, 5),
                "no_vig_probability_a": round(p_a, 5),
                "no_vig_probability_b": round(1 - p_a, 5),
                "orientation_vs_fixture": orientation,
                "start_time_delta_hours": None if delta_h is None else round(delta_h, 2),
                "evidence_file": q.get("evidence_file"),
                "join_note": q.get("join_note"),
            }
            # keep the oldest quote per source (most conservative freshness) unless identical price
            prev = per_source.get(src)
            if prev is None or (prev.get("retrieved_at_utc") or "") > (entry.get("retrieved_at_utc") or ""):
                per_source[src] = entry

        sources = sorted(per_source.values(), key=lambda s: s["source_key"])
        probs = [s["no_vig_probability_a"] for s in sources]
        prob_a = round(sum(probs) / len(probs), 5) if probs else None
        status_l = str(fx.get("status") or "").lower()
        flags = []
        if not sources:
            flags.append("no_external_line")
        if len(sources) == 1:
            flags.append("single_source")
        if fx_start and fx_start < now:
            flags.append("scheduled_start_in_the_past_or_started")
        if status_l and status_l != "scheduled":
            flags.append(f"hotspawn_status_{status_l}")
        if status_l == "cancelled":
            flags.append("fixture_cancelled")
        if status_l == "started" and fx_start and fx_start > now:
            flags.append("source_status_inconsistent_with_future_start")
        for s in sources:
            if s.get("market_is_live"):
                flags.append("live_market_quote")
            age_h = hours_between(parse_iso(s.get("retrieved_at_utc")), now)
            if age_h is not None and age_h > 6:
                flags.append("quote_older_than_6h")
        if used_fallback:
            flags.append("uses_fallback_stored_quote")
        for q, orientation, delta_h in matches:
            if delta_h is not None and delta_h > 6:
                flags.append("start_time_mismatch_over_6h")

        pick = None
        pick_probability = None
        if prob_a is not None:
            pick = fx.get("team_a") if prob_a >= 0.5 else fx.get("team_b")
            pick_probability = round(max(prob_a, 1 - prob_a), 4)
        rows.append({
            "fixture_id": fx.get("fixture_id"),
            "game": fx.get("sport"),
            "competition": fx.get("competition"),
            "tier": fx.get("tier"),
            "stage": fx.get("stage"),
            "scheduled_start_time_utc": fx.get("scheduled_start_time_utc"),
            "lock_time_utc": fx.get("lock_time_utc"),
            "status": fx.get("status"),
            "team_a": fx.get("team_a"),
            "team_b": fx.get("team_b"),
            "probability_a": prob_a,
            "probability_b": None if prob_a is None else round(1 - prob_a, 5),
            "pick": pick,
            "pick_probability": pick_probability,
            "n_sources": len(sources),
            "sources": sources,
            "flags": sorted(set(flags)),
            "verified": bool(sources),
            "cancelled": status_l == "cancelled",
            "official_source_url_hotspawn": fx.get("source_url"),
            "hotspawn_match_url": fx.get("match_url"),
            "hotspawn_pick_pct_used": False,
        })

    rows.sort(key=lambda r: (r.get("scheduled_start_time_utc") or "", r.get("game") or ""))

    open_rows = [r for r in rows
                 if (parse_iso(r.get("lock_time_utc")) or parse_iso(r.get("scheduled_start_time_utc")) or now) >= now
                 and "fixture_cancelled" not in r["flags"]]
    with_line = [r for r in rows if r["verified"]]
    open_with_line = [r for r in open_rows if r["verified"]]

    doc = {
        "generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session": "961e163a",
        "build_notes": notes,
        "source_of_fixtures": "https://play.hotspawn.com/lobby (public fixtures API)",
        "rules": [
            "External betting lines only (Pinnacle, Bovada, HLTV-published bookmaker odds, egamersworld).",
            "Per source: q = 1/decimal; p_a = q_a/(q_a+q_b) removes that source's margin.",
            "Consensus = arithmetic mean of per-source no-vig shares.",
            "Hotspawn crowd pick % is never an input (see data/961/hotspawn_reference.json).",
            "No verified external line => probabilities blank and flagged no_external_line.",
        ],
        "summary": {
            "fixtures_total": len(rows),
            "open_for_picks": len(open_rows),
            "fixtures_with_external_line": len(with_line),
            "open_fixtures_with_external_line": len(open_with_line),
            "fixtures_without_external_line": len(rows) - len(with_line),
            "cancelled_fixtures": sum(1 for r in rows if r["cancelled"]),
            "unverified_open": sum(1 for r in open_rows if not r["verified"]),
            "by_game": {g: {
                "total": sum(1 for r in rows if r.get("game") == g),
                "with_line": sum(1 for r in rows if r.get("game") == g and r["verified"]),
                "open": sum(1 for r in open_rows if r.get("game") == g),
                "open_with_line": sum(1 for r in open_with_line if r.get("game") == g),
            } for g in sorted({r.get("game") for r in rows if r.get("game")})},
            "by_source": {k: sum(1 for r in rows for s in r["sources"] if s["source_key"] == k)
                          for k in sorted({s["source_key"] for r in rows for s in r["sources"]})},
            "quote_freshness_utc": sorted({s["retrieved_at_utc"] for r in rows for s in r["sources"]
                                           if s.get("retrieved_at_utc")}),
        },
        "rows": rows,
    }
    os.makedirs(OUT, exist_ok=True)
    with open(BOARD, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    print(json.dumps(doc["summary"], indent=1)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
