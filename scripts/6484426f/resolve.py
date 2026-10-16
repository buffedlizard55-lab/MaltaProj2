#!/usr/bin/env python3
"""Resolve one pick and one win probability for every open HotSpawn CS2 fixture (session 6484426f).

Inputs, all read-only:

  * ``data/c64a5e19/board.json``            - canonical fixture inventory + accepted external quotes
  * ``data/6484426f/sources/capture.json``  - this session's own source capture (optional, preferred)
  * ``data/6484426f/valve/*.md``            - official Valve regional standings, as committed
  * ``data/6484426f/research.json``         - dated manual reads (HLTV etc.) with their URLs
  * ``data/7c2622db/lobby_state.json``      - lobby ownership fallback when our own capture is absent

Outputs ``data/6484426f/board.json``. Nothing else is written; every published number keeps the
source link it came from. HotSpawn crowd percentages are ownership only and never enter a price.
"""
from __future__ import annotations

import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shared  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "6484426f"
CANON = ROOT / "data" / "c64a5e19" / "board.json"
CANON_OWNERSHIP = ROOT / "data" / "7c2622db" / "lobby_state.json"
CAPTURE = OUT / "sources" / "capture.json"
RESEARCH = OUT / "research.json"
VALVE_DIR = OUT / "valve"
HISTORY = OUT / "history.json"
BOARD = OUT / "board.json"

# Declared policy (published on desk/method.html) ------------------------------------------
CLIMB_MIN_PROB = 0.30          # "not stupid" floor: a climb pick below 30% is not taken
CLIMB_MIN_LEVERAGE = 2.0       # win probability / crowd ownership of that side
CLIMB_MAX_PER_DAY = 3          # ranked by leverage x offered points
QUOTE_MAX_AGE_H = 4.0          # an external price older than this cannot price a row
LOBBY = "https://play.hotspawn.com/lobby"
VALVE_REPO = "ValveSoftware/counter-strike_regional_standings"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def hours_between(a, b):
    if not a or not b:
        return None
    return abs((a - b).total_seconds()) / 3600.0


# --------------------------------------------------------------------------------- Valve
VRS_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|([^|]*)\|", re.M)


def parse_standings(text: str) -> list[dict]:
    out = []
    for m in VRS_ROW.finditer(text or ""):
        roster = [p.strip() for p in re.split(r",", m.group(4) or "") if p.strip()]
        roster = [r for r in roster if not r.startswith("[")]
        out.append({"standing": int(m.group(1)), "points": int(m.group(2)),
                    "team": m.group(3).strip(), "roster": roster})
    return out


def load_valve() -> dict:
    """Official ratings: this session's committed copy first, the canonical batch second."""
    files, source = {}, None
    if VALVE_DIR.exists():
        for path in sorted(VALVE_DIR.glob("standings_*.md")):
            files[path.stem] = path.read_text()
        source = "data/6484426f/valve (own fetch, see valve_commit.json)"
    inputs = load_json(ROOT / "data" / "c64a5e19" / "official_inputs.json")
    if not files and isinstance(inputs, dict):
        for key, value in inputs.items():
            if isinstance(value, str) and value.lstrip().startswith("|"):
                files[key] = value
        source = "data/c64a5e19/official_inputs.json"
    entries: dict[str, list[dict]] = {}
    for name, text in files.items():
        for row in parse_standings(text):
            key = shared.core().norm(row["team"])
            entries.setdefault(key, []).append({**row, "file": name})
    # Collapse the same team listed in both the global and a regional file.
    by_name: dict[str, list[dict]] = {}
    for key, rows in entries.items():
        seen = {}
        for row in rows:
            seen.setdefault((row["team"].casefold(), row["points"]), row)
        by_name[key] = sorted(seen.values(), key=lambda r: -r["points"])
    return {"entries": by_name, "source": source,
            "files": sorted(files), "repo": VALVE_REPO}


def resolve_team(name: str, valve: dict, aliases: dict) -> dict:
    """Map a HotSpawn team label to official standings entries. Ambiguity is published."""
    core = shared.core()
    notes = []
    lookup = name
    alias = (aliases or {}).get(core.norm(name))
    if alias:
        lookup = alias["official_name"]
        notes.append({"type": "identity_alias", "hotspawn_label": name, "official_name": lookup,
                      "evidence": alias.get("evidence"), "sources": alias.get("sources") or []})
    key = core.norm(lookup)
    candidates = list(valve["entries"].get(key) or [])
    if not candidates:
        return {"resolved": None, "notes": notes, "candidates": [],
                "reason": f"no official Valve entry matches '{lookup}'"}
    if len(candidates) > 1:
        full = [c for c in candidates if len(c["roster"]) >= 4]
        chosen = full[0] if full else candidates[0]
        notes.append({"type": "ambiguous_official_name", "official_name": chosen["team"],
                      "rule": "highest-rated entry listing at least four players",
                      "candidates": [{"points": c["points"], "standing": c["standing"],
                                      "file": c["file"], "roster": c["roster"]} for c in candidates]})
    else:
        chosen = candidates[0]
    return {"resolved": chosen, "notes": notes, "candidates": candidates, "reason": None}


# ------------------------------------------------------------------------------ market
def hq(source_key, source_name, public_url, api_url, event_id, names, dec_a, dec_b, start_utc,
       raw_format, retrieved_utc, league=None, extra=None):
    nv = shared.core().no_vig(dec_a, dec_b)
    return {"source_key": source_key, "source_name": source_name, "public_url": public_url,
            "api_url": api_url, "event_id": str(event_id), "names_at_source": list(names),
            "raw_format": raw_format, "decimal_a": round(float(dec_a), 6),
            "decimal_b": round(float(dec_b), 6), "raw_a": dec_a, "raw_b": dec_b,
            "no_vig_prob_team_a": nv["prob_a"] if nv else None,
            "overround": nv["overround"] if nv else None, "swapped": False,
            "start_utc": start_utc, "league": league, "retrieved_utc": retrieved_utc,
            **(extra or {})}


def dedupe_quotes(quotes: list[dict]) -> list[dict]:
    """One price per source and event: the newest read wins, and any move between reads is published.

    Two captures of the same book can disagree (the line moved). Blending both would double-weight one
    book and hide the move, so the newer read prices the row, the older read time is kept in
    ``also_read_at``, and a differing earlier price is recorded in ``earlier_price`` with a
    ``price_moved_between_reads`` flag on the joined quote.
    """
    best: dict[tuple, dict] = {}
    for quote in quotes:
        key = (quote.get("source_key"), quote.get("event_id") or tuple(quote.get("names_at_source") or []))
        current = best.get(key)
        if current is None:
            best[key] = dict(quote)
            continue
        newer, older = ((quote, current) if str(quote.get("retrieved_utc") or "") >
                        str(current.get("retrieved_utc") or "") else (current, quote))
        merged = dict(newer)
        merged["also_read_at"] = sorted({str(older.get("retrieved_utc")),
                                         str(current.get("retrieved_utc"))} - {str(newer.get("retrieved_utc"))})
        for field in ("books", "rules_primary"):
            if not merged.get(field) and older.get(field):
                merged[field] = older[field]
        if (round(float(older.get("decimal_a") or 0), 4), round(float(older.get("decimal_b") or 0), 4)) != \
                (round(float(newer.get("decimal_a") or 0), 4), round(float(newer.get("decimal_b") or 0), 4)):
            merged["earlier_price"] = {"decimal_a": older.get("decimal_a"), "decimal_b": older.get("decimal_b"),
                                      "retrieved_utc": older.get("retrieved_utc")}
        best[key] = merged
    return list(best.values())


def capture_quotes(capture: dict) -> list[dict]:
    quotes = []
    for key in ("pinnacle", "bovada", "melbet", "bo3gg"):
        for row in ((capture.get(key) or {}).get("quotes") or []):
            try:
                dec_a, dec_b = float(row["decimal_a"]), float(row["decimal_b"])
            except (KeyError, TypeError, ValueError):
                continue
            quotes.append(hq(row.get("source_key"), row.get("source_name"), row.get("public_url"),
                             row.get("api_url"), row.get("event_id"), row.get("names_at_source") or [],
                             dec_a, dec_b, row.get("start_utc"), row.get("raw_format"),
                             row.get("retrieved_utc"), row.get("league")))
    for row in ((capture.get("kalshi") or {}).get("markets") or []):
        mids = row.get("yes_mid") or []
        if len(mids) != 2 or not all(mids):
            continue
        dec_a, dec_b = 1.0 / mids[0], 1.0 / mids[1]
        quotes.append(hq("kalshi", "Kalshi (exchange)", row.get("public_url"), row.get("api_url"),
                         row.get("event_id"), row.get("names_at_source") or [], dec_a, dec_b,
                         row.get("kickoff_utc"), "yes mid ($)", row.get("retrieved_utc"),
                         extra={"rules_primary": row.get("rules_primary"),
                                "books": row.get("books")}))
    return quotes


def canonical_quotes(canonical: dict) -> list[dict]:
    """Accepted quotes from the canonical batch, re-derived here from their raw prices.

    Their URLs, raw decimal/american prices and UTC read times travel with the row, so a
    reviewer can replay the same join and the same no-vig arithmetic this session publishes.
    """
    core = shared.core()
    out = []
    for row in canonical.get("open") or []:
        for quote in row.get("quotes") or []:
            try:
                dec_a = float(quote.get("decimal_a"))
                dec_b = float(quote.get("decimal_b"))
            except (TypeError, ValueError):
                continue
            nv = core.no_vig(dec_a, dec_b)
            if not nv:
                continue
            out.append(hq(quote.get("source_key"), quote.get("source_name"),
                          quote.get("public_url"), quote.get("api_url"), quote.get("event_id"),
                          quote.get("names_at_source") or [dec_a, dec_b], dec_a, dec_b,
                          quote.get("start_utc_at_source") or quote.get("start_utc"),
                          quote.get("raw_format"), quote.get("retrieved_utc"),
                          extra={"raw_a": quote.get("raw_a"), "raw_b": quote.get("raw_b"),
                                 "origin": "canonical batch data/c64a5e19/board.json",
                                 "canonical_fixture_id": row.get("fixture_id")}))
    return out


def alias_names(name: str, aliases: dict) -> list[str]:
    """All labels a source may use for this team: the HotSpawn label plus verified aliases."""
    core = shared.core()
    out = [name]
    alias = (aliases or {}).get(core.norm(name))
    if alias and alias.get("official_name"):
        out.append(alias["official_name"])
    return out


def join_quote(fixture: dict, quote: dict, aliases: dict | None = None) -> dict | None:
    core = shared.core()
    names = quote.get("names_at_source") or []
    if len(names) != 2:
        return None
    a_names = alias_names(fixture["team_a"], aliases or {})
    b_names = alias_names(fixture["team_b"], aliases or {})
    straight = (any(core.same_team(n, names[0])[0] for n in a_names)
                and any(core.same_team(n, names[1])[0] for n in b_names))
    swapped_names = (any(core.same_team(n, names[1])[0] for n in a_names)
                     and any(core.same_team(n, names[0])[0] for n in b_names))
    if straight:
        swapped = False
    elif swapped_names:
        swapped = True
    else:
        return None
    diff = hours_between(shared.core().parse_iso(fixture.get("start_utc")),
                         shared.core().parse_iso(quote.get("start_utc")))
    if diff is None:
        return {"rejected": "unverified_start_time", "swapped": swapped, "start_diff_h": None}
    if diff > 3.0:
        return {"rejected": "kickoff_mismatch", "swapped": swapped, "start_diff_h": diff}
    prob = quote.get("no_vig_prob_team_a")
    if prob is None:
        return None
    return {"swapped": swapped, "start_diff_h": diff,
            "prob_a": (1.0 - prob) if swapped else prob, "quote": quote}


# ------------------------------------------------------------------------ ownership
def load_ownership(capture: dict | None) -> dict:
    rows = ((capture or {}).get("hotspawn") or {}).get("ownership") or {}
    out = {}
    for fid, row in rows.items():
        pa, pb = row.get("picked_percent_a"), row.get("picked_percent_b")
        try:
            pa, pb = float(pa), float(pb)
        except (TypeError, ValueError):
            continue
        total = pa + pb
        if total <= 0:
            continue
        out[str(fid)] = {"a": pa / total, "b": pb / total, "pct_a": pa, "pct_b": pb,
                         "total_picks": row.get("total_picks"), "team_a": row.get("team_a"),
                         "team_b": row.get("team_b")}
    if out:
        return out
    state = load_json(CANON_OWNERSHIP) or {}
    for raw in ((state.get("transfer_state") or {}).get("fixtures") or []):
        try:
            fid = str(raw["id"])
            pa = float(raw["participants0_picked_percent"])
            pb = float(raw["participants1_picked_percent"])
        except (KeyError, TypeError, ValueError):
            continue
        total = pa + pb
        if total <= 0:
            continue
        out[fid] = {"a": pa / total, "b": pb / total, "pct_a": pa, "pct_b": pb,
                    "total_picks": raw.get("total_picks"),
                    "team_a": raw.get("participants0_name"), "team_b": raw.get("participants1_name")}
    return out


# -------------------------------------------------------------------------- the ladder
def evaluate_row(row: dict, quotes: list[dict], valve: dict, aliases: dict, k_fit: float,
                 ownership: dict) -> dict:
    core = shared.core()
    fixture = {k: row.get(k) for k in ("fixture_id", "team_a", "team_b", "start_utc", "lock_utc",
                                       "competition", "tier", "points", "hotspawn_url")}
    joined, rejected = [], []
    for quote in dedupe_quotes(quotes):
        info = join_quote(fixture, quote, aliases)
        if info is None:
            continue
        if info.get("rejected"):
            rejected.append({"source_key": quote.get("source_key"), "reason": info["rejected"],
                             "start_diff_h": info.get("start_diff_h"), "url": quote.get("api_url")})
            continue
        age = hours_between(now_utc(), shared.core().parse_iso(quote.get("retrieved_utc")))
        q = {"source_key": quote["source_key"], "source_name": quote["source_name"],
             "public_url": quote["public_url"], "api_url": quote["api_url"],
             "event_id": quote["event_id"], "names_at_source": quote["names_at_source"],
             "decimal_a": quote["decimal_a"], "decimal_b": quote["decimal_b"],
             "raw_format": quote["raw_format"], "raw_a": quote.get("raw_a"),
             "raw_b": quote.get("raw_b"), "no_vig_prob_team_a": round(info["prob_a"], 6),
             "swapped": info["swapped"], "start_utc": quote.get("start_utc"),
             "start_diff_h": round(info["start_diff_h"] or 0.0, 4),
             "retrieved_utc": quote.get("retrieved_utc"),
             "age_hours": round(age, 2) if age is not None else None,
             "fresh": (age is not None and age <= QUOTE_MAX_AGE_H),
             "origin": quote.get("origin") or "own capture"}
        if quote.get("books"):
            q["books"] = quote["books"]
            q["rules_primary"] = quote.get("rules_primary")
        source_order = shared.core().no_vig(quote["decimal_a"], quote["decimal_b"])
        q["raw_no_vig_team1"] = round(source_order["prob_a"], 6) if source_order else None
        joined.append(q)

    # 1. bookmaker market line
    books = [q for q in joined
             if q["source_key"] in ("pinnacle", "bovada", "melbet", "thunderpick_via_bo3gg")]
    exchange = [q for q in joined if q["source_key"] == "kalshi"]
    vrs_a = resolve_team(fixture["team_a"], valve, aliases)
    vrs_b = resolve_team(fixture["team_b"], valve, aliases)
    model = None
    if vrs_a.get("resolved") and vrs_b.get("resolved"):
        pa = core.vrs_prob(vrs_a["resolved"]["points"], vrs_b["resolved"]["points"], k_fit)
        model = {"prob_a": pa, "prob_b": 1.0 - pa, "delta_points":
                 vrs_a["resolved"]["points"] - vrs_b["resolved"]["points"], "k": k_fit}

    out = {**fixture, "crowd": ownership.get(str(fixture["fixture_id"])), "quotes": joined,
           "rejected_quotes": rejected, "vrs": {"team_a": vrs_a, "team_b": vrs_b, "model": model}}
    if books:
        usable = books
        wsum = sum(core.SOURCE_WEIGHTS.get(q["source_key"], 1.0) for q in usable)
        pa = sum(core.SOURCE_WEIGHTS.get(q["source_key"], 1.0) * q["no_vig_prob_team_a"]
                 for q in usable) / wsum
        stale = not any(q["fresh"] for q in usable)
        out.update({"basis": "market", "prob_a": pa, "prob_b": 1.0 - pa,
                    "n_sources": len({q["source_key"] for q in usable}),
                    "source_keys": sorted({q["source_key"] for q in usable}),
                    "quote_stale": stale,
                    "quote_age_hours": min((q["age_hours"] for q in usable
                                            if q["age_hours"] is not None), default=None)})
    elif exchange:
        q = exchange[0]
        out.update({"basis": "exchange", "prob_a": q["no_vig_prob_team_a"],
                    "prob_b": 1.0 - q["no_vig_prob_team_a"], "n_sources": 1,
                    "source_keys": ["kalshi"], "quote_stale": not q["fresh"],
                    "quote_age_hours": q["age_hours"]})
    elif model:
        out.update({"basis": "model", "prob_a": model["prob_a"], "prob_b": model["prob_b"],
                    "n_sources": 0, "source_keys": [], "quote_stale": False,
                    "quote_age_hours": None})
    else:
        out.update({"basis": "unresolved", "prob_a": None, "prob_b": None, "n_sources": 0,
                    "source_keys": [], "quote_stale": False, "quote_age_hours": None})
    flags = []
    if out.get("quote_stale"):
        flags.append("quote_older_than_4h")
    if out["basis"] == "market" and out.get("n_sources") == 1:
        flags.append("single_book_price")
    if out["basis"] == "market" and all(q["source_key"] == "thunderpick_via_bo3gg" for q in books):
        flags.append("single_esportsbook_price_no_sharp_book")
    if any((q.get("start_diff_h") or 0.0) > shared.core().TIME_TOLERANCE_H for q in joined):
        flags.append("kickoff_differs_between_sources")
    if any(q.get("price_moved") for q in joined):
        flags.append("price_moved_between_reads")
    if out["basis"] == "model":
        for side, res in (("a", vrs_a), ("b", vrs_b)):
            for note in res.get("notes") or []:
                flags.append(f"{note['type']}:{note.get('official_name') or fixture['team_' + side]}")
    if out["basis"] == "unresolved":
        flags.append("no_line_unverified")
    out["flags"] = sorted(set(flags))
    out["prob_age_hours"] = out.get("quote_age_hours")
    return out


def choose_picks(row: dict) -> dict:
    """Safe pick, tie handling, and the declared climb rule, with every gate result published."""
    core = shared.core()
    out = {"safe_pick": None, "climb_pick": None, "climb_active": False, "tie_break": None,
           "leverage": None, "gates": {}}
    if row.get("prob_a") is None:
        return out
    pa, pb = row["prob_a"], row["prob_b"]
    crowd = row.get("crowd") or {}
    own = {"a": crowd.get("a"), "b": crowd.get("b")}
    if abs(pa - pb) < 1e-9:
        # Declared tiebreak policy (published on desk/method.html): the market says the sides are
        # equal, so the SAFE pick uses the independent official rating model when one exists and
        # the CLIMB pick takes the less-owned side (equal expected points, positive separation).
        model = (row.get("vrs") or {}).get("model")
        less_owned = None
        if own["a"] is not None and own["b"] is not None:
            less_owned = "a" if own["a"] < own["b"] else ("b" if own["b"] < own["a"] else None)
        if model:
            picked = "a" if model["prob_a"] >= 0.5 else "b"
            out["tie_break"] = ("equal probabilities; SAFE pick = official Valve rating side, "
                               "CLIMB pick = less-owned side")
        elif less_owned:
            picked = less_owned
            out["tie_break"] = "equal probabilities; no model -> less-owned side for both picks"
        else:
            picked = "a"
            out["tie_break"] = "equal probabilities; no model and no ownership -> team A"
        out["safe_pick"] = row["team_a"] if picked == "a" else row["team_b"]
        out["climb_pick"] = ((row["team_a"] if less_owned == "a" else row["team_b"])
                             if less_owned else out["safe_pick"])
        out["underdog"] = {"side": less_owned, "team": out["climb_pick"],
                           "prob": 0.5, "ownership": own.get(less_owned) if less_owned else None}
        return out
    side = "a" if pa > pb else "b"
    dog = "b" if side == "a" else "a"
    out["safe_pick"] = row["team_a"] if side == "a" else row["team_b"]
    out["climb_pick"] = out["safe_pick"]
    p_dog = row["prob_b"] if dog == "b" else row["prob_a"]
    dog_own = own[dog]
    leverage = (p_dog / dog_own) if dog_own else None
    out["leverage"] = leverage
    out["underdog"] = {"side": dog, "team": row["team_b"] if dog == "b" else row["team_a"],
                       "prob": p_dog, "ownership": dog_own}
    out["gates"] = {"prob_floor_30pct": p_dog >= CLIMB_MIN_PROB,
                    "leverage_2x": (leverage is not None and leverage >= CLIMB_MIN_LEVERAGE),
                    "ownership_published": dog_own is not None}
    out["climb_candidate"] = bool(out["gates"]["prob_floor_30pct"] and out["gates"]["leverage_2x"])
    return out


def fit_k(rows: list[dict]) -> dict:
    """Fit the VRS slope against this capture's own bookmaker lines (through the origin)."""
    core = shared.core()
    pairs = []
    for row in rows:
        model = (row.get("vrs") or {}).get("model")
        if row.get("basis") == "market" and model:
            pairs.append({"delta": model["delta_points"], "market_prob_a": row["prob_a"]})
    return core.fit_calibration(pairs)


def grade_history(board_rows: list[dict], inventory: list[dict], generated_utc: str) -> dict:
    """Keep the first published pick per fixture and grade it when HotSpawn reports the result."""
    history = load_json(HISTORY) or {"picks": []}
    known = {p["fixture_id"] for p in history["picks"]}
    for row in board_rows:
        if row["fixture_id"] in known or not row.get("safe_pick"):
            continue
        history["picks"].append({"fixture_id": row["fixture_id"], "team_a": row["team_a"],
                                 "team_b": row["team_b"], "start_utc": row["start_utc"],
                                 "safe_pick": row["safe_pick"], "climb_pick": row["climb_pick"],
                                 "prob_a": row["prob_a"], "prob_b": row["prob_b"],
                                 "basis": row["basis"],
                                 "first_published_utc": generated_utc})
    winners = {str(f["fixture_id"]): f for f in inventory}
    graded = []
    for pick in history["picks"]:
        fx = winners.get(pick["fixture_id"])
        if not fx or not fx.get("winner"):
            continue
        winner_name = fx["team_a"] if fx["winner"] == "a" else fx["team_b"]
        graded.append({**pick, "winner": winner_name,
                       "safe_correct": pick["safe_pick"] == winner_name,
                       "climb_correct": pick["climb_pick"] == winner_name})
    return {"history": history, "graded": graded}


def build() -> dict:
    generated = iso(now_utc())
    canonical = load_json(CANON) or {}
    capture = load_json(CAPTURE)
    research = load_json(RESEARCH) or {}
    aliases = research.get("identity_aliases") or {}
    valve = load_valve()

    fixtures: dict[str, dict] = {}
    for row in canonical.get("open") or []:
        fixtures[str(row["fixture_id"])] = dict(row)
    cap_fx = ((capture or {}).get("hotspawn") or {}).get("fixtures") or []
    for fx in cap_fx:
        if "lobby_page" not in (fx.get("seen_in") or []):
            continue
        fid = str(fx["fixture_id"])
        base = fixtures.setdefault(fid, {})
        fixtures[fid] = {**base, **{k: v for k, v in fx.items() if k != "seen_in"},
                         "seen_in": fx.get("seen_in"), "membership": "own_capture"}
    inventory = canonical.get("inventory") or []
    ownership = load_ownership(capture)
    now_iso = iso(now_utc())
    locked: list[dict] = []
    for fid, fx in list(fixtures.items()):
        lock = fx.get("lock_utc") or fx.get("start_utc")
        if lock and lock <= now_iso:
            locked.append({"fixture_id": fid, "team_a": fx.get("team_a"), "team_b": fx.get("team_b"),
                           "start_utc": fx.get("start_utc"), "lock_utc": fx.get("lock_utc"),
                           "status": fx.get("status"), "why": "lock time already passed in this capture"})
            fixtures.pop(fid)
        elif not lock:
            locked.append({"fixture_id": fid, "team_a": fx.get("team_a"), "team_b": fx.get("team_b"),
                           "start_utc": fx.get("start_utc"), "lock_utc": None, "status": fx.get("status"),
                           "why": "no lock time published by the lobby source"})
            fixtures.pop(fid)
    quotes = capture_quotes(capture or {}) + canonical_quotes(canonical)
    unresolved_notes = research.get("unresolved_notes") or {}

    rows = [evaluate_row(fx, quotes, valve, aliases, 1.0, ownership) for fx in fixtures.values()]
    calibration = fit_k(rows)
    k_fit = calibration["k"]
    rows = [evaluate_row(fx, quotes, valve, aliases, k_fit, ownership) for fx in fixtures.values()]
    for row in rows:
        row.update(choose_picks(row))
        row["limitation"] = (unresolved_notes.get(row["fixture_id"])
                             if row["basis"] == "unresolved" else None)
        row["sources"] = []
        if row.get("hotspawn_url"):
            row["sources"].append({"label": "HotSpawn fixture card", "url": row["hotspawn_url"]})
        for quote in row["quotes"]:
            row["sources"].append({"label": f"{quote['source_name']} price ({quote['origin']})",
                                   "url": quote["public_url"],
                                   "retrieved_utc": quote.get("retrieved_utc"),
                                   "age_hours": quote.get("age_hours")})
        for side in ("team_a", "team_b"):
            res = (row.get("vrs") or {}).get(side) or {}
            if res.get("resolved"):
                row["sources"].append({
                    "label": f"Valve official rating: {res['resolved']['team']} "
                             f"#{res['resolved']['standing']} ({res['resolved']['points']} pts)",
                    "url": "https://github.com/" + VALVE_REPO + "/blob/main/live/2026/"
                           "standings_global_2026_10_05.md"})
        if row.get("crowd"):
            row["sources"].append({"label": "HotSpawn crowd share (ownership only, never a price)",
                                   "url": LOBBY})
        if not row["sources"]:
            row["sources"].append({"label": "HotSpawn lobby listing for this fixture", "url": LOBBY})

    # Climb budget: at most CLIMB_MAX_PER_DAY activations, ranked by leverage x offered points.
    today = date.fromisoformat(generated[:10])
    candidates = [r for r in rows if r.get("climb_candidate") and r.get("start_utc")
                  and date.fromisoformat(r["start_utc"][:10]) == today]
    candidates.sort(key=lambda r: -(r["leverage"] * (r.get("points") or 1)))
    for rank, row in enumerate(candidates):
        if rank < CLIMB_MAX_PER_DAY:
            row["climb_pick"] = row["underdog"]["team"]
            row["climb_active"] = True
            row["climb_rank"] = rank + 1
    clusters: dict[tuple, set] = {}
    for row in rows:
        for quote in row["quotes"]:
            key = (quote["source_key"], round(float(quote["decimal_a"]), 3),
                   round(float(quote["decimal_b"]), 3))
            clusters.setdefault(key, set()).add(row["fixture_id"])
    for row in rows:
        repeated = sorted({fid for quote in row["quotes"]
                           for fid in clusters.get((quote["source_key"],
                                                    round(float(quote["decimal_a"]), 3),
                                                    round(float(quote["decimal_b"]), 3)), set())
                           if fid != row["fixture_id"]})
        if repeated:
            row["flags"] = sorted(set(row["flags"]) | {f"repeated_price_pair_with:{','.join(repeated)}"})
            row["repeated_price_pair"] = repeated
    rows.sort(key=lambda r: (r.get("start_utc") or "", r["fixture_id"]))

    grading = grade_history(rows, inventory, generated)
    twc = {r["fixture_id"]: r for r in rows if r["fixture_id"] in ("1080205", "1081775")}
    summary = {
        "open": len(rows),
        "with_pick": sum(1 for r in rows if r.get("safe_pick")),
        "market": sum(1 for r in rows if r["basis"] == "market"),
        "exchange": sum(1 for r in rows if r["basis"] == "exchange"),
        "model": sum(1 for r in rows if r["basis"] == "model"),
        "unresolved": sum(1 for r in rows if r["basis"] == "unresolved"),
        "climb_active": sum(1 for r in rows if r.get("climb_active")),
        "listed_fixtures": len(inventory),
        "ended_fixtures": sum(1 for f in inventory if f.get("winner")),
        "graded": len(grading["graded"]),
        "safe_correct": sum(1 for g in grading["graded"] if g["safe_correct"]),
    }
    coverage = {"capture_fixtures": len(fixtures) + len(locked),
                "open": len(fixtures), "listed_locked": len(locked),
                "locked_ids": sorted(f["fixture_id"] for f in locked),
                "locked_sample": sorted(locked, key=lambda f: (f.get("start_utc") or ""))[:12],
                "lobby_source": LOBBY}
    out = {
        "session": "6484426f",
        "coverage": coverage,
        "generated_utc": generated,
        "policy": {"climb_min_prob": CLIMB_MIN_PROB, "climb_min_leverage": CLIMB_MIN_LEVERAGE,
                   "climb_max_per_day": CLIMB_MAX_PER_DAY, "quote_max_age_hours": QUOTE_MAX_AGE_H,
                   "ladder": ["market", "exchange", "model", "unresolved"]},
        "inventory_source": "data/c64a5e19/board.json (canonical, read-only)"
                            + (" + data/6484426f/sources/capture.json (own capture)" if capture else ""),
        "capture_present": bool(capture),
        "capture_utc": ((capture or {}).get("finished_utc")),
        "ownership_source": ("own capture (data/6484426f/sources/capture.json)" if capture
                             else "data/7c2622db/lobby_state.json (read-only fallback)"),
        "calibration": calibration,
        "valve": {"source": valve["source"], "files": valve["files"], "repo": valve["repo"],
                  "entries": sum(len(v) for v in valve["entries"].values())},
        "rows": rows,
        "summary": summary,
        "twc": {"rows": twc, "research": research.get("twc_2026") or {}},
        "grading": grading,
        "sources": research.get("sources") or [],
        "research_read_utc": {"lobby": "2026-10-16T07:26Z", "hltv_event": "2026-10-16T07:35Z",
                              "hltv_results": "2026-10-16T07:38Z", "hltv_analytics": "2026-10-16T07:41Z",
                              "valve": "2026-10-16T07:32Z"},
    }
    BOARD.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    HISTORY.write_text(json.dumps(grading["history"], indent=1, ensure_ascii=False) + "\n")
    return out


if __name__ == "__main__":
    board = build()
    print(json.dumps(board["summary"], indent=1))
    print("calibration", {k: board["calibration"][k] for k in ("n_pairs", "k", "fitted", "mae_prob")})
    for row in board["rows"]:
        probs = ("" if row.get("prob_a") is None
                 else "{:.1f}/{:.1f}".format(100 * row["prob_a"], 100 * row["prob_b"]))
        print(f"{row['fixture_id']} {str(row.get('start_utc'))[:16]} {row['team_a'][:20]:20} vs "
              f"{row['team_b'][:20]:20} {row['basis']:11} {probs:13} "
              f"pick={row.get('safe_pick') or '-':20} climb={row.get('climb_pick')}")
