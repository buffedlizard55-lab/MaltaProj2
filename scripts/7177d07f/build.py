#!/usr/bin/env python3
"""Session 7177d07f builder: a pick for every open HotSpawn CS2 fixture, with the basis labelled.

The featured resolution is the strict route the site already publishes: an eligible two-sided
primary-bookmaker quote joined by both team names and the exact UTC kickoff (data/lines.json).
This builder never duplicates or overrides that route. It applies the extra information sources
the brief names - in order - ONLY to fixtures the featured route leaves unresolved:

  1. HLTV ................. identity and ranking research (committed dated evidence)
  2. esportsbooks / lines .. Melbet LineFeed, Thunderpick coefficients via bo3.gg, Kalshi books
  3. official Valve VRS .... points from Valve's own standings file, using HLTV-confirmed identity

Basis labels published on every row:
  featured .......... eligible external bookmaker/exchange line (strict route)
  esportsbook ....... two-sided price from an esportsbook/exchange read this run
  originated_vrs .... line originated from official Valve VRS points for both teams
  originated_rank ... one side has only a published VRS rank; points substituted by standing
  unresolved ........ no defensible evidence - probability left blank and listed with its limitation

Nothing is invented: HLTV user-vote percentages are never used as probabilities, and a row without
evidence stays blank.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "7177d07f"
sys.path.insert(0, str(ROOT / "scripts" / "f7279a54"))  # read-only reuse of the published VRS math
import importlib.util as _iu, sys as _sys
from pathlib import Path as _Path
if 'core_7177d07f' in _sys.modules:
    core = _sys.modules['core_7177d07f']
else:
    _core_spec = _iu.spec_from_file_location('core_7177d07f', ROOT / "scripts" / "f7279a54" / "core.py")
    core = _iu.module_from_spec(_core_spec)
    _sys.modules['core_7177d07f'] = core
    _core_spec.loader.exec_module(core)

LOBBY = "https://play.hotspawn.com/lobby"
VALVE_PAGE = ("https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/"
              "live/2026/standings_global_2026_10_05.md")


def load(rel, default=None):
    try:
        return json.loads((ROOT / rel).read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def norm(name: str) -> str:
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def _parse_time(value):
    """Parse the ISO-8601 timestamps several public feeds use. Returns None when not parseable."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def now_utc_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ identity map
# Each alias maps a HotSpawn label onto the official Valve standings row that HLTV's roster
# evidence identifies. Every entry is published with its evidence on unresolved/flagged.html.
ALIAS = {
    "wrotberry": "wbt",
    "roundsgg": "rounds",
    "envy": "3dmax",
    "bandachuya": "bandachuya",
    "heroic": "heroic",
    "betboom": "betboom",
    "9z": "9z",
}


def valve_index(standings):
    """canonical name -> list of official rows (the file can list several rosters per org)."""
    idx = {}
    for row in standings or []:
        idx.setdefault(norm(row.get("team")), []).append(row)
    return idx


def pick_valve_row(idx, name):
    """Resolve one HotSpawn label to its official row; prefer the highest-rated roster."""
    key = norm(ALIAS.get(norm(name), name))
    rows = idx.get(key) or []
    if not rows:
        return None, None
    best = max(rows, key=lambda r: int(r.get("points") or 0))
    note = None
    if len(rows) > 1:
        note = (f"{len(rows)} official rows share the name '{best.get('team')}'; the highest-rated "
                f"({best.get('points')} points, standing {best.get('standing')}) was used.")
    return best, note


def points_from_rank(standings, rank):
    """Substitute points for a team known only by its published VRS standing.

    The official file is ordered by points, so standing N maps to the points of row N. This is a
    documented substitution, flagged on the row - not a measured rating.
    """
    if not standings or not rank:
        return None
    ordered = sorted(standings, key=lambda r: int(r.get("standing") or 0))
    if not ordered or rank < 1 or rank > len(ordered):
        return None
    return int(ordered[rank - 1].get("points") or 0)


def no_vig(dec_a, dec_b):
    qa, qb = 1.0 / float(dec_a), 1.0 / float(dec_b)
    total = qa + qb
    if total <= 0:
        return None, None
    return qa / total, qb / total


def confidence(prob):
    if prob >= 0.72:
        return "Strong"
    if prob >= 0.60:
        return "Solid"
    if prob >= 0.54:
        return "Lean"
    return "Toss-up"


def main() -> int:
    inventory = load("data/hotspawn_matches.json", {})
    lines_doc = load("data/lines.json", {})
    snapshot = load("data/7177d07f/snapshot.json", {})
    research = load("data/7177d07f/hltv_research.json", {})

    standings = ((snapshot.get("valve") or {}).get("standings")) or []
    valve_snapshot = (snapshot.get("valve") or {}).get("snapshot")
    if not standings:
        # fall back to the copy other sessions archived from the same official repository
        standings = load("data/7177d07f/valve_standings_fallback.json", [])
    idx = valve_index(standings)

    quoted = {}
    for fx in (lines_doc.get("fixtures") or []):
        if fx.get("bookmaker_lines"):
            quoted[str(fx.get("fixture_id"))] = fx

    matches = [m for m in (inventory.get("matches") or []) if m.get("sport") == "cs2"]
    now = now_utc_iso()

    rows, open_rows = [], 0
    for m in matches:
        lock = m.get("lock_time") or m.get("scheduled_start_time")
        status = str(m.get("status") or "")
        is_open = bool(lock) and str(lock) > now and status == "scheduled"
        if not is_open:
            continue
        open_rows += 1

        fid = str(m.get("fixture_id"))
        team_a, team_b = m.get("team_a"), m.get("team_b")
        hotspawn_url = ((m.get("source") or {}).get("published_match_url")) or LOBBY
        row = {
            "fixture_id": fid,
            "team_a": team_a,
            "team_b": team_b,
            "competition": m.get("competition_name"),
            "tier": (m.get("tier") or "").upper(),
            "start_utc": m.get("scheduled_start_time"),
            "lock_utc": lock,
            "hotspawn_url": hotspawn_url,
            "hotspawn_url_kind": "published match page" if (m.get("source") or {}).get("published_match_url") else "official lobby",
            "evidence": [],
            "flags": [],
            "basis": "unresolved",
            "prob_a": None,
            "prob_b": None,
            "pick": None,
            "pick_prob": None,
            "confidence": None,
        }
        hltv = (research.get("matches") or {}).get(fid) or {}
        if hltv:
            url = hltv.get("hltv_match_url") or hltv.get("hltv_analytics_url")
            if url:
                row["evidence"].append({
                    "kind": "hltv_research",
                    "source": "HLTV",
                    "url": url,
                    "detail": "Identity and ranking evidence read from HLTV (see notes).",
                    "read_utc": research.get("read_window_utc"),
                    "notes": hltv.get("notes") or [],
                    "hltv_best_odds_present": hltv.get("hltv_best_odds_present"),
                    "hltv_bookmaker_favorite": hltv.get("hltv_bookmaker_favorite"),
                })
                if hltv.get("hltv_bookmaker_favorite"):
                    row["flags"].append(f"hltv_bookmaker_favorite:{hltv['hltv_bookmaker_favorite']}")
                if hltv.get("hltv_best_odds_present") is False:
                    row["flags"].append("hltv_best_odds_columns_empty")

        # ---------------------------------------------------------- 0. featured route
        featured = quoted.get(fid)
        if featured:
            consensus = (featured.get("derived") or {}).get("consensus") or {}
            if consensus:
                row["basis"] = "featured"
                row["prob_a"] = round(consensus["derived_probability_a_mean"], 4)
                row["prob_b"] = round(consensus["derived_probability_b_mean"], 4)
                for line in featured.get("bookmaker_lines") or []:
                    row["evidence"].append({
                        "kind": "featured_bookmaker_line",
                        "source": line.get("source_name") or line.get("source_key"),
                        "url": line.get("source_public_url") or line.get("source_api_url"),
                        "detail": f"quoted {line.get('decimal_odds_a')} / {line.get('decimal_odds_b')}; "
                                  f"no-vig {line.get('derived_probability_a')} / {line.get('derived_probability_b')}",
                        "read_utc": line.get("retrieved_at_utc"),
                    })
                rows.append(finalize(row))
                continue

        # ------------------------------------------- 1/2. esportsbook and exchange lines
        price = match_quote(snapshot, m)
        if price:
            pa, pb = no_vig(price["decimal_a"], price["decimal_b"])
            if pa is not None:
                row["basis"] = "esportsbook"
                row["prob_a"], row["prob_b"] = round(pa, 4), round(pb, 4)
                row["evidence"].append({
                    "kind": "esportsbook_price",
                    "source": price.get("source_name"),
                    "url": price.get("public_url"),
                    "detail": f"{price.get('team_a')} {price.get('decimal_a')} / "
                              f"{price.get('team_b')} {price.get('decimal_b')} -> no-vig {pa:.3f} / {pb:.3f}",
                    "read_utc": (snapshot.get("sources") or [{}])[0].get("retrieved_utc") or snapshot.get("collected_utc"),
                })
                if price.get("swapped"):
                    row["flags"].append("price_orientation_swapped_to_match_fixture")
                if price.get("from_exchange_midpoints"):
                    row["flags"].append("probability_from_exchange_bid_ask_midpoints")
                rows.append(finalize(row))
                continue

        # ---------------------------------------------- 3. official Valve VRS origination
        ra, note_a = pick_valve_row(idx, team_a)
        rb, note_b = pick_valve_row(idx, team_b)
        k, cal = calibration_k(lines_doc, idx)
        for note in (note_a, note_b):
            if note:
                row["flags"].append("multiple_official_rows_same_team")

        pa, pb = None, None
        if ra and rb:
            pa = core.vrs_prob(float(ra["points"]), float(rb["points"]), k)
            pb = 1.0 - pa
            row["basis"] = "originated_vrs"
            row["evidence"].append({
                "kind": "official_valve_vrs",
                "source": "Valve regional standings (official)",
                "url": VALVE_PAGE,
                "detail": f"{ra.get('team')} {ra.get('points')} pts (standing {ra.get('standing')}) vs "
                          f"{rb.get('team')} {rb.get('points')} pts (standing {rb.get('standing')}); "
                          f"Valve Glicko curve, calibrated slope k={k}",
                "read_utc": (snapshot.get("valve") or {}).get("retrieved_utc") or snapshot.get("collected_utc"),
            })
        else:
            # one or both sides known only by a published VRS standing (e.g. HLTV 'VRS #169')
            ranks = {}
            for side, name in (("a", team_a), ("b", team_b)):
                key = norm(name)
                entry = ((hltv.get("teams") or {}).get(name)) or {}
                for candidate, value in (hltv.get("teams") or {}).items():
                    if norm(candidate) == key:
                        entry = value or {}
                        break
                ranks[side] = entry.get("hltv_valve_vrs_rank")
            if (ra or ranks.get("a")) and (rb or ranks.get("b")):
                pts_a = float(ra["points"]) if ra else points_from_rank(standings, ranks.get("a"))
                pts_b = float(rb["points"]) if rb else points_from_rank(standings, ranks.get("b"))
                if pts_a and pts_b:
                    pa = core.vrs_prob(pts_a, pts_b, k)
                    pb = 1.0 - pa
                    row["basis"] = "originated_rank"
                    row["flags"].append("rating_from_published_standing_not_a_measured_rating")
                    row["evidence"].append({
                        "kind": "official_valve_vrs_rank_substitution",
                        "source": "HLTV republication of the Valve VRS rank + Valve standings file",
                        "url": ((hltv.get("teams") or {}).get(team_b if ra else team_a) or {}).get("hltv_team_url")
                               or hltv.get("hltv_match_url") or VALVE_PAGE,
                        "detail": f"points substituted from the published standing "
                                  f"(A={pts_a:.0f}, B={pts_b:.0f}); Valve Glicko curve, k={k}",
                        "read_utc": research.get("read_window_utc"),
                    })
        if pa is not None:
            row["prob_a"], row["prob_b"] = round(pa, 4), round(pb, 4)
        if row["basis"] in ("originated_vrs", "originated_rank"):
            row["evidence"].extend(slot_corroboration(snapshot, m))
        rows.append(finalize(row))

    # ------------------------------------------- cross-check against the other published boards
    others = load_other_boards()
    for row in rows:
        row["cross_check"] = []
        for board_name, entry in others.items():
            ref = entry.get(row["fixture_id"])
            if not ref or not ref.get("pick"):
                continue
            row["cross_check"].append({
                "board": board_name,
                "page": entry["_page"],
                "pick": ref["pick"],
                "prob": ref.get("prob"),
                "basis": ref.get("basis"),
                "agrees": bool(row["pick"]) and norm(ref["pick"]) == norm(row["pick"]),
            })
        if row["pick"] and row["cross_check"] and all(not c["agrees"] for c in row["cross_check"]):
            row["flags"].append("pick_disagrees_with_every_other_published_board")
        elif row["pick"] and any(not c["agrees"] for c in row["cross_check"]):
            row["flags"].append("pick_disagrees_with_at_least_one_other_board")
        # HLTV's own bookmaker-favourite statement vs the originated line
        fav = None
        for item in row["evidence"]:
            if item.get("kind") == "hltv_research":
                fav = item.get("hltv_bookmaker_favorite")
        if fav and row["pick"] and norm(fav) != norm(row["pick"]):
            row["flags"].append("hltv_bookmaker_favorite_disagrees_with_this_line")
        row["flags"] = sorted(set(row["flags"]))

    rows.sort(key=lambda r: (r["lock_utc"] or r["start_utc"] or "", r["fixture_id"]))
    summary = {
        "open": open_rows,
        "with_pick": sum(1 for r in rows if r["pick"]),
        "unresolved": sum(1 for r in rows if not r["pick"]),
        "by_basis": {},
        "calibration": cal,
        "valve_snapshot": valve_snapshot,
        "valve_rows": len(standings),
    }
    for row in rows:
        summary["by_basis"][row["basis"]] = summary["by_basis"].get(row["basis"], 0) + 1

    board = {
        "session": "7177d07f",
        "generated_utc": now,
        "inventory_source": {
            "file": "data/hotspawn_matches.json",
            "page": inventory.get("source_page") or LOBBY,
            "endpoint": inventory.get("source_endpoint"),
            "generated_at_utc": inventory.get("generated_at_utc"),
            "observed_at_utc": inventory.get("source_observed_at_utc"),
            "note": "HotSpawn is used for fixture discovery only; its crowd pick percentage is never read.",
        },
        "featured_source": {
            "file": "data/lines.json",
            "generated_at_utc": lines_doc.get("generated_at_utc"),
            "odds_collected_at_utc": lines_doc.get("odds_collected_at_utc"),
        },
        "snapshot_source": {
            "file": "data/7177d07f/snapshot.json",
            "collected_utc": snapshot.get("collected_utc"),
            "sources": snapshot.get("sources") or [],
        },
        "hltv_research": {
            "file": "data/7177d07f/hltv_research.json",
            "read_window_utc": research.get("read_window_utc"),
            "source_root": research.get("source_root"),
        },
        "summary": summary,
        "rows": rows,
        "unresolved_rows": [r for r in rows if not r["pick"]],
        "identity_findings": research.get("identity_findings") or [],
    }
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "board.json").write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


def load_other_boards():
    """Read-only cross-check inputs: the pick each other published board shows for a fixture."""
    out = {}

    def add(name, page, rows, pick_key, prob_key, basis_key):
        bucket = {"_page": page}
        for row in rows:
            fid = str(row.get("fixture_id") or "")
            if not fid or fid in bucket:
                continue
            bucket[fid] = {
                "pick": row.get(pick_key),
                "prob": row.get(prob_key),
                "basis": row.get(basis_key),
            }
        out[name] = bucket

    every = load("data/c64a5e19/board.json", {})
    add("picks-every-match (c64a5e19)", "picks-every-match/index.html",
        [{"fixture_id": r.get("fixture_id"),
          "pick": (r.get("line") or {}).get("pick_team"),
          "prob": (r.get("line") or {}).get("pick_prob"),
          "basis": (r.get("line") or {}).get("basis")} for r in every.get("open") or []],
        "pick", "prob", "basis")

    full = load("data/fe803b80/board.json", {})
    add("board (fe803b80)", "board/picks.html",
        [{"fixture_id": r.get("fixture_id"),
          "pick": (r.get("line") or {}).get("pick"),
          "prob": (r.get("line") or {}).get("pick_probability"),
          "basis": (r.get("line") or {}).get("basis")} for r in full.get("open") or []],
        "pick", "prob", "basis")

    ourline = load("data/f7279a54/board.json", {})
    add("ourline (f7279a54)", "ourline/index.html",
        [{"fixture_id": r.get("fixture_id"),
          "pick": (r.get("line") or {}).get("pick_team"),
          "prob": (r.get("line") or {}).get("pick_prob"),
          "basis": (r.get("line") or {}).get("basis")} for r in ourline.get("open") or []],
        "pick", "prob", "basis")

    coverage = load("data/coverage/board.json", {})
    add("coverage (6ddde224)", "coverage/index.html",
        [{"fixture_id": r.get("fixture_id"),
          "pick": (r.get("published") or {}).get("pick_team"),
          "prob": (r.get("published") or {}).get("pick_probability")
                  or (r.get("published") or {}).get("prob_a"),
          "basis": (r.get("published") or {}).get("basis")} for r in coverage.get("rows") or []],
        "pick", "prob", "basis")
    return out


def finalize(row):
    if row["prob_a"] is None or row["prob_b"] is None:
        row["pick"] = None
        row["pick_prob"] = None
        row["confidence"] = None
        row["basis"] = "unresolved"
        row["flags"].append("no_defensible_evidence_probability_left_blank")
    else:
        if row["prob_a"] >= row["prob_b"]:
            row["pick"], row["pick_prob"] = row["team_a"], row["prob_a"]
        else:
            row["pick"], row["pick_prob"] = row["team_b"], row["prob_b"]
        row["confidence"] = confidence(row["pick_prob"])
        if row["basis"] in ("originated_vrs", "originated_rank"):
            row["confidence"] = f"{row['confidence']} (originated)"
        elif "probability_from_exchange_bid_ask_midpoints" in row["flags"]:
            row["confidence"] = f"{row['confidence']} (exchange)"
    row["flags"] = sorted(set(row["flags"]))
    return row


def match_quote(snapshot, fixture):
    """Two-sided esportsbook/exchange price whose team names match this fixture (either order)."""
    a, b = norm(fixture.get("team_a")), norm(fixture.get("team_b"))
    if not a or not b:
        return None
    best = None
    for q in snapshot.get("quotes") or []:
        qa, qb = norm(q.get("team_a")), norm(q.get("team_b"))
        if qa == a and qb == b:
            cand = dict(q, swapped=False)
        elif qa == b and qb == a:
            cand = dict(q, swapped=True)
            cand["decimal_a"], cand["decimal_b"] = q["decimal_b"], q["decimal_a"]
        else:
            continue
        if best is None:
            best = cand
    if best is None:
        best = match_exchange_book(snapshot, fixture)
    return best


def match_exchange_book(snapshot, fixture):
    """Kalshi market whose title names both fixture teams, priced from the two order books.

    Kalshi lists each side as its own market, so the pair is found by matching both team names
    across the two market titles of the same event, then normalising the two bid/ask midpoints.
    A market is only used when both sides quote a bid and an ask and the spread is <= 10c, the same
    gate the coverage board uses; otherwise the book is too thin to price the fixture.
    """
    a, b = norm(fixture.get("team_a")), norm(fixture.get("team_b"))
    if not a or not b:
        return None
    books = snapshot.get("exchange_books") or []
    by_event = {}
    for book in books:
        text = norm(f"{book.get('title') or ''} {book.get('subtitle') or ''}")
        if not text:
            continue
        by_event.setdefault(str(book.get("event_id") or ""), []).append((text, book))

    for event_id, entries in by_event.items():
        if len(entries) < 2:
            continue
        side_a = next((bk for txt, bk in entries if a and a in txt), None)
        side_b = next((bk for txt, bk in entries if b and b in txt), None)
        if not side_a or not side_b or side_a is side_b:
            continue
        mids = []
        for book in (side_a, side_b):
            try:
                bid = float(book.get("yes_bid_dollars"))
                ask = float(book.get("yes_ask_dollars"))
            except (TypeError, ValueError):
                mids = []
                break
            if bid <= 0 or ask <= 0 or ask < bid or (ask - bid) > 0.10:
                mids = []
                break
            mids.append((bid + ask) / 2.0)
        if len(mids) != 2 or sum(mids) <= 0:
            continue
        # The two sides are complements in a genuine two-outcome market, so the raw midpoints must
        # add up to about 1.0. A book where they do not is quoting stale or placeholder prices on
        # an untraded market, and normalising it would manufacture a confident-looking number.
        if not (0.85 <= (mids[0] + mids[1]) <= 1.15):
            continue
        pa = mids[0] / (mids[0] + mids[1])
        if pa <= 0 or pa >= 1:
            continue
        return {
            "source_key": "kalshi",
            "source_name": "Kalshi (regulated exchange)",
            "public_url": side_a.get("public_url"),
            "api_url": side_a.get("api_url"),
            "event_id": event_id,
            "team_a": fixture.get("team_a"),
            "team_b": fixture.get("team_b"),
            # implied decimal prices: 1/p, kept so the row shows a real two-sided number
            "decimal_a": round(1.0 / pa, 4),
            "decimal_b": round(1.0 / (1.0 - pa), 4),
            "start_utc": None,
            "swapped": False,
            "from_exchange_midpoints": True,
        }
    return None


def slot_corroboration(snapshot, fixture):
    """Esportsbook prices for the same slot under a different team label - shown, never joined.

    Several low-tier events are priced by esportsbooks under a label that differs from HotSpawn's
    (for example Melbet lists 'WhiteBIT Team' where HotSpawn says 'WROTBERRY'). Those prices are
    published next to the originated line as direction corroboration only: they are not joined and
    never enter the arithmetic, because the identity is exactly what is in dispute.
    """
    a, b = norm(fixture.get("team_a")), norm(fixture.get("team_b"))
    if not a or not b:
        return []
    start = _parse_time(fixture.get("scheduled_start_time"))
    if start is None:
        return []
    out = []
    seen = set()
    for q in snapshot.get("quotes") or []:
        qa, qb = norm(q.get("team_a")), norm(q.get("team_b"))
        key = (q.get("source_key"), q.get("event_id"))
        if key in seen:
            continue
        matches_a, matches_b = (qa == a or qb == a), (qa == b or qb == b)
        if matches_a == matches_b:  # need exactly one side to line up
            continue
        q_start = _parse_time(q.get("start_utc"))
        # Fail closed: without a published start time on both sides this cannot be shown to be the
        # same slot, and a neighbouring fixture that merely shares one team must never be attached.
        if q_start is None or abs((q_start - start).total_seconds()) > 1800:
            continue
        seen.add(key)
        pa, pb = no_vig(q["decimal_a"], q["decimal_b"])
        if pa is None:
            continue
        # orient the probability onto the fixture's team A
        prob_a = pa if qa == a else pb
        out.append({
            "kind": "esportsbook_same_slot_not_joined",
            "source": q.get("source_name"),
            "url": q.get("public_url"),
            "detail": (f"{q.get('team_a')} {q.get('decimal_a')} / {q.get('team_b')} "
                       f"{q.get('decimal_b')} -> {prob_a:.3f} for {fixture.get('team_a')} "
                       f"if the label is the same team. NOT joined: the identity is what is in "
                       f"dispute on this event."),
            "read_utc": (snapshot.get("sources") or [{}])[0].get("retrieved_utc")
                        or snapshot.get("collected_utc"),
        })
    if out:
        out.append({
            "kind": "note",
            "source": "7177d07f rule",
            "url": "https://play.hotspawn.com/lobby",
            "detail": ("Slot prices above are published for comparison only. They are excluded from "
                       "the probability because joining them would assume the identity they are "
                       "meant to test."),
            "read_utc": None,
        })
    return out


def calibration_k(lines_doc, idx):
    """Fit the Valve-curve slope against the market-priced fixtures of the same snapshot."""
    pairs = []
    for fx in (lines_doc.get("fixtures") or []):
        consensus = (fx.get("derived") or {}).get("consensus")
        if not consensus:
            continue
        ra, _ = pick_valve_row(idx, fx.get("team_a"))
        rb, _ = pick_valve_row(idx, fx.get("team_b"))
        if ra and rb:
            pairs.append({
                "delta": float(ra["points"]) - float(rb["points"]),
                "market_prob_a": consensus["derived_probability_a_mean"],
            })
    cal = core.fit_calibration(pairs) if hasattr(core, "fit_calibration") else {}
    k = cal.get("k") if cal else None
    if not cal.get("fitted"):
        fallback = None
        for rel in ("data/c64a5e19/board.json", "data/f7279a54/board.json"):
            doc = load(rel, {})
            value = ((doc.get("calibration") or {}).get("k"))
            if isinstance(value, (int, float)) and (doc.get("calibration") or {}).get("fitted"):
                fallback = float(value)
                break
        if fallback:
            k = fallback
            cal = dict(cal or {}, k=k, borrowed_from=rel, fitted=True)
    out = {
        "k": round(float(k or 1.0), 4),
        "fitted": bool(cal.get("fitted")),
        "pairs_used": len(pairs),
        "min_pairs": (cal or {}).get("min_pairs"),
        "mae_prob": (cal or {}).get("mae_prob"),
        "borrowed_from": (cal or {}).get("borrowed_from"),
    }
    return float(k or 1.0), out


if __name__ == "__main__":
    sys.exit(main())
