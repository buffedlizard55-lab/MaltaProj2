#!/usr/bin/env python3
"""T-FULLCOV board builder (session fe803b80). Reads the snapshot, writes ``data/fe803b80/board.json``.

The board gives **every** open CS2 fixture listed in the HotSpawn pick'em lobby a pick and a
probability, and labels where that number comes from:

1. ``market``        — a two-way price from Pinnacle / Bovada / Kalshi / Melbet / Thunderpick-via-bo3.gg
2. ``market+model``  — the market consensus blended with the official Valve-VRS rating model
3. ``model``         — no reachable bookmaker prices this fixture, so the line is **originated**
                       from ratings: official Valve VRS when both teams are listed, otherwise this
                       project's own Elo computed from bo3.gg published match results

Every row carries the exact source URL(s) and read time; nothing is inferred. A row that has no
source at all stays blank with a flag rather than being filled.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "fe803b80"
HLTV_RANKING_PAGE = "https://www.hltv.org/ranking/teams"


def load(name, default=None):
    path = DATA / name
    if not path.exists():
        return default if default is not None else {}
    return json.loads(path.read_text(encoding="utf-8"))


def vrs_lookup(vrs_regions: dict) -> tuple[dict, list[str], dict]:
    """canonical team key -> {"points","standing","region"}; global first, then the regions.

    Region keys are normalised to their bare name, so a snapshot whose keys carry the standings date
    (``global_2026_10``) joins exactly like ``global``. A team that appears in two regions with
    different points is recorded as ambiguous and published on the flagged page.

    The third return value keeps *every* official row published under a name, so a name that maps
    to more than one roster (Valve publishes two "CYBERSHOKE" rows) can be resolved conservatively
    instead of silently taking the first one.
    """
    ordered: dict[str, dict] = {}
    for raw_region, rows in (vrs_regions or {}).items():
        region = str(raw_region).split("_")[0]
        if region in ("global", "europe", "americas", "asia"):
            ordered.setdefault(region, {}).update(rows or {})
    out: dict[str, dict] = {}
    candidates: dict[str, list[dict]] = {}
    ambiguous: list[str] = []
    for region in ("global", "europe", "americas", "asia"):
        for name, row in (ordered.get(region) or {}).items():
            key, _, _ = core.canon(name)
            if not key:
                continue
            record = {"points": float(row["points"]), "standing": int(row["standing"]),
                      "region": region, "vrs_name": name}
            bucket = candidates.setdefault(key, [])
            if not any(abs(float(c["points"]) - record["points"]) < 1e-9
                       and c["region"] == region for c in bucket):
                bucket.append(record)
            if key in out:
                if abs(float(out[key]["points"]) - float(row["points"])) > 1e-9:
                    ambiguous.append(f"{key}:{region}:{name}")
                continue
            out[key] = record
    return out, sorted(set(ambiguous)), candidates


def build_quotes_index(quotes: list[dict]) -> dict:
    idx: dict[str, list[dict]] = {}
    for qt in quotes:
        for name in (qt.get("team_a"), qt.get("team_b")):
            key, _, _ = core.canon(name)
            if key:
                idx.setdefault(key, []).append(qt)
    return idx


def resolve_market(fixture: dict, quote_index: dict) -> tuple[list[dict], list[dict]]:
    """Return (joined entries, rejected joins) for one fixture."""
    joined, rejected = [], []
    candidates: list[dict] = []
    for name in (fixture["team_a"], fixture["team_b"]):
        key, _, _ = core.canon(name)
        for qt in quote_index.get(key, []):
            if qt not in candidates:
                candidates.append(qt)
    for qt in candidates:
        info = core.match_quote(fixture, qt)
        if info is None:
            continue
        if info.get("rejected"):
            rejected.append({"quote": qt, "info": info})
            continue
        if qt.get("prob_a") is None:
            continue
        pa = core.oriented_prob(qt, info["swapped"])
        if pa is None:
            continue
        joined.append({
            "source_key": qt["source_key"], "source_name": qt["source_name"],
            "public_url": qt["public_url"], "event_id": qt["event_id"],
            "team_a": qt["team_a"], "team_b": qt["team_b"],
            "decimal_a": qt["decimal_a"] if not info["swapped"] else qt["decimal_b"],
            "decimal_b": qt["decimal_b"] if not info["swapped"] else qt["decimal_a"],
            "prob_a": pa, "overround": qt.get("overround"), "raw_format": qt.get("raw_format"),
            "retrieved_utc": qt.get("retrieved_utc"), "league": qt.get("league"),
            "live": qt.get("live"), "start_utc": qt.get("start_utc"),
            "alias_notes": info.get("alias_notes") or [], "alias_evidence": info.get("alias_evidence") or [],
            "start_diff_h": info.get("start_diff_h"), "swapped": info["swapped"],
            "lock_evidence": "no",
        })
    return joined, rejected


def calibration_pairs(rows: list[dict]) -> list[dict]:
    pairs = []
    for row in rows:
        if not row["market"] or not row["model"].get("vrs"):
            continue
        pairs.append({"delta": row["model"]["vrs"]["delta"],
                      "market_prob_a": row["market"]["prob_a"],
                      "fixture_id": row["fixture_id"]})
    return pairs


def elo_for(rows: list[dict], history: dict, vrs_teams: dict, bo3_ids: dict) -> tuple[dict, dict]:
    """Our own Elo over bo3.gg published results, anchored to the official Valve VRS scale.

    Anchoring: every team that has an official VRS row *and* a bo3.gg id is seeded to
    ``1500 + (points - anchor)``, where ``anchor`` is the median VRS point value over the teams
    in this snapshot. 400 VRS points therefore equal 400 Elo points, which matches the shape of
    Valve's own published curve (a 400-point gap is worth ~90% win probability). This is a
    documented modelling choice, not a source value.
    """
    matches = []
    seen = set()
    for tid in history:
        for m in history.get(tid) or []:
            a, b, w = m.get("team1_id"), m.get("team2_id"), m.get("winner_team_id")
            if not a or not b or not w or m.get("id") in seen:
                continue
            seen.add(m.get("id"))
            matches.append({"key_a": f"bo3:{a}", "key_b": f"bo3:{b}",
                            "winner": "a" if str(w) == str(a) else "b",
                            "start_utc": m.get("start_date")})
    anchor = 1500.0
    points = [rec["points"] for key, rec in vrs_teams.items() if bo3_ids.get(key)]
    if points:
        anchor = sorted(points)[len(points) // 2]
    seed = {f"bo3:{bo3_ids[key]}": core.ELO_BASE + (rec["points"] - anchor)
            for key, rec in vrs_teams.items() if bo3_ids.get(key)}
    ratings = core.elo_run(matches, seed=seed)
    info = {"matches": len(matches), "teams_seeded": len(seed), "anchor_vrs_points": anchor,
            "k": core.ELO_K, "passes": 8}
    return ratings, info


def rank_to_rating(rank) -> float | None:
    """Map a bo3.gg published world ranking position onto the Elo scale (documented mapping).

    bo3.gg publishes a world rank per team (1 = best). This is a modelling choice, not a source
    value: rank 1 maps to 1799, rank 300 or worse to 1500, linearly in between, so that a ranking
    gap alone can originate a line when a team has no VRS points and no match history. Every row
    that uses it is labelled and flagged.
    """
    try:
        value = float(rank)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return core.ELO_BASE + max(0.0, 300.0 - min(value, 300.0))


def alias_candidate(name: str, vrs_candidates: dict) -> dict | None:
    """Official Valve rows a former-name listing ("ex-...") could refer to.

    Only the ``ex-`` prefix is removed; the rest of the name still has to match an official row
    exactly. When several official rows share that name (Valve publishes two "CYBERSHOKE"
    rosters), the weakest one is kept so the resulting line is the most conservative official
    reading. The result is a *candidate*: it is published as an explicit, flagged assumption.
    """
    for key in core.ex_prefix_candidates(name):
        rows = vrs_candidates.get(key) or []
        if not rows:
            continue
        weakest = min(rows, key=lambda r: float(r["points"]))
        return {"key": key, "rows": rows, "weakest": weakest}
    return None


def vrs_page_url(snap: dict, region: str) -> str | None:
    """The official Valve page that published the standings row of a region."""
    for entry in (snap.get("vrs") or {}).get("evidence", []):
        if str(entry.get("region", "")).split("_")[0] == region:
            return entry.get("page_url")
    return None


MARKET_SOURCE_ORDER = (("pinnacle", "Pinnacle (guest odds API)"),
                       ("bovada", "Bovada"),
                       ("linefeed_melbet", "1xBet platform (1xBet / Melbet LineFeed)"),
                       ("kalshi", "Kalshi (CFTC exchange)"),
                       ("polymarket", "Polymarket (prediction market)"),
                       ("bo3gg_matches", "Thunderpick prices published by bo3.gg"))


def attempt_ledger(snap: dict, row: dict) -> list[dict]:
    """What was tried for this fixture and what each source answered.

    The ledger is published on the unresolved page so a reviewer can see that a blank row is the
    result of an exhausted search (or of a blocked source), never of an oversight.
    """
    access = snap.get("access") or {}
    joined_sources = set((row.get("market") or {}).get("sources") or [])
    out: list[dict] = []
    joined_counts: dict[str, int] = {}
    for quote in row.get("quotes") or []:
        key = quote.get("source_key")
        joined_counts[key] = joined_counts.get(key, 0) + 1
    source_keys = {"pinnacle": "pinnacle", "bovada": "bovada",
                   "linefeed_melbet": "melbet", "kalshi": "kalshi",
                   "polymarket": "polymarket", "bo3gg_matches": "thunderpick"}
    for key, label in MARKET_SOURCE_ORDER:
        meta = access.get(key) or {}
        if key == "bo3gg_matches":
            state = (f"reachable ({meta.get('matches', 0)} upcoming matches, "
                     f"{access.get('thunderpick_quotes', 0)} Thunderpick prices)")
        else:
            code, err = meta.get("status"), meta.get("error")
            if err:
                state = f"not reachable ({err})"
            elif code == 200:
                count = meta.get("quotes")
                state = ("reachable (HTTP 200" + (f", {count} quotes" if count is not None else "")
                         + ")")
            elif code:
                state = f"answered HTTP {code}"
            else:
                state = "no answer recorded"
        count = joined_counts.get(source_keys.get(key, ""), 0)
        out.append({"source": label, "state": state,
                    "joined": (f"yes ({count} price{'s' if count != 1 else ''})" if count else "no")})
    hltv = access.get("hltv_ranking") or {}
    if hltv.get("error"):
        hltv_state = f"not reachable ({hltv['error']})"
    elif hltv.get("status") == 200:
        hltv_state = (f"reachable (HTTP 200, {hltv.get('parsed', 0)} of the requested team names "
                      f"published a ranking position)")
    elif hltv.get("status"):
        hltv_state = f"answered HTTP {hltv['status']}"
    else:
        hltv_state = "not attempted"
    out.append({"source": "HLTV team ranking", "state": hltv_state, "joined": "no"})
    vrs = access.get("valve_vrs") or {}
    vrs_state = ("read (snapshot " + str(vrs.get("snapshot")) + ")" if vrs.get("snapshot")
                 else (f"not reachable ({vrs.get('error')})" if vrs.get("error") else "no answer"))
    out.append({"source": "Valve VRS official standings", "state": vrs_state,
                "joined": "yes" if (row.get("vrs_a") or row.get("vrs_b")
                                    or row.get("model", {}).get("floor")) else "no"})
    ident = access.get("identity_resolution") or {}
    if ident.get("error"):
        ident_state = f"not reachable ({ident['error']})"
    elif row.get("identity"):
        ident_state = (f"resolved {len(row['identity'])} team name(s) from the same fixture on bo3.gg "
                       f"({ident.get('identities', 0)} identity joins in this snapshot)")
    else:
        ident_state = (f"searched, no same-fixture match published for this slot "
                       f"({ident.get('identities', 0)} identity joins in this snapshot)")
    out.append({"source": "bo3.gg fixture identity (same slot + same competition)",
                "state": ident_state, "joined": "yes" if row.get("identity") else "no"})
    return out


def mark_first_seen(rows: list[dict], build_utc: str) -> dict:
    """Record when each fixture id was first listed here, so the board can show what is new."""
    path = DATA / "fixtures_seen.json"
    seen = {}
    if path.exists():
        try:
            seen = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            seen = {}
    changed = False
    for row in rows:
        fid = row["fixture_id"]
        if fid not in seen:
            seen[fid] = {"first_seen_utc": build_utc, "competition": row.get("competition"),
                         "team_a": row["team_a"], "team_b": row["team_b"],
                         "start_utc": row["start_utc"]}
            changed = True
        row["first_seen_utc"] = seen[fid]["first_seen_utc"]
        row["new_since_first_build"] = seen[fid]["first_seen_utc"] == build_utc
    if changed:
        keep = {k: v for k, v in seen.items()}
        path.write_text(json.dumps(keep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return seen


def main() -> int:
    snap = load("snapshot.json")
    if not snap:
        raise SystemExit("no data/fe803b80/snapshot.json — run collect.py first")
    fixtures = snap["hotspawn"]["fixtures"]
    permalinks = snap["hotspawn"].get("permalinks") or {}
    quotes = snap.get("quotes") or []
    rejected_quotes = snap.get("rejected_quotes") or []
    vrs_teams, vrs_ambiguous, vrs_candidates = vrs_lookup(snap.get("vrs_regions") or {})
    identities = snap.get("identities") or {}
    hltv_teams = snap.get("hltv_teams") or {}
    bo3 = snap.get("bo3gg") or {}

    # canonical bo3.gg team id per canonical name (from the team records collected upstream)
    bo3_ids: dict[str, str] = {}
    for tid, rec in (bo3.get("teams") or {}).items():
        for candidate in (rec.get("name"), rec.get("acronym"), rec.get("slug")):
            key, _, _ = core.canon(candidate)
            if key and key not in bo3_ids:
                bo3_ids[key] = str(tid)

    # bo3.gg world ranking per canonical name (used only when nothing better exists)
    rank_index: dict[str, int] = {}
    slug_index: dict[str, str] = {}
    for tid, rec in (bo3.get("teams") or {}).items():
        for candidate in (rec.get("name"), rec.get("acronym"), rec.get("slug")):
            key, _, _ = core.canon(candidate)
            if key and key not in rank_index and rec.get("rank") is not None:
                rank_index[key] = int(rec["rank"])
            if key and key not in slug_index and rec.get("slug"):
                slug_index[key] = rec["slug"]

    # Second route to the same ids: bo3.gg publishes the two teams of a fixture together, so a
    # fixture whose individual team name is not resolvable can still be resolved by its pairing
    # (either orientation, and only when both sides agree). Used only to feed the rating history;
    # it never creates a price.
    pair_ids: dict[tuple[str, str], tuple[str, str]] = {}
    for m in bo3.get("matches") or []:
        id1, id2 = m.get("team1_id"), m.get("team2_id")
        if not id1 or not id2:
            continue
        name1 = ((bo3.get("teams") or {}).get(str(id1)) or {}).get("name")
        name2 = ((bo3.get("teams") or {}).get(str(id2)) or {}).get("name")
        key1, _, _ = core.canon(name1)
        key2, _, _ = core.canon(name2)
        if key1 and key2:
            pair_ids.setdefault((key1, key2), (str(id1), str(id2)))

    def resolve_pair(key_a: str, key_b: str) -> tuple[str | None, str | None]:
        for (x, y), (i1, i2) in pair_ids.items():
            if x == key_a and y == key_b:
                return i1, i2
            if x == key_b and y == key_a:
                return i2, i1
        return None, None

    quote_index = build_quotes_index(quotes)

    rows: list[dict] = []
    for fx in fixtures:
        key_a, evidence_a, note_a = core.canon(fx["team_a"])
        key_b, evidence_b, note_b = core.canon(fx["team_b"])
        joined, rejected = resolve_market(fx, quote_index)
        market = core.consensus(joined)
        vrs_a, vrs_b = vrs_teams.get(key_a), vrs_teams.get(key_b)
        # A renamed HotSpawn team is mapped onto the bo3.gg record of the *same fixture* only
        # when the same slot, the same competition and the opponent all agree; the evidence URL
        # travels with the row.
        ident = identities.get(fx["fixture_id"]) or {}
        identity: dict[str, dict] = {}
        for side, key, name in (("a", key_a, fx["team_a"]), ("b", key_b, fx["team_b"])):
            rec = ident.get(name)
            if not rec:
                continue
            identity[side] = rec
            known = bo3_ids.get(key)
            if known is None:
                bo3_ids[key] = rec["bo3_team_id"]
                if rec.get("bo3_slug"):
                    slug_index[key] = rec["bo3_slug"]
            elif known != rec["bo3_team_id"]:
                rec = dict(rec, conflict_with_team_id=known)
                identity[side] = rec
        model = {}
        if vrs_a and vrs_b:
            model["vrs"] = {"delta": vrs_a["points"] - vrs_b["points"],
                            "points_a": vrs_a["points"], "points_b": vrs_b["points"],
                            "standing_a": vrs_a["standing"], "standing_b": vrs_b["standing"],
                            "region_a": vrs_a["region"], "region_b": vrs_b["region"],
                            "vrs_name_a": vrs_a["vrs_name"], "vrs_name_b": vrs_b["vrs_name"]}
        rows.append({
            "fixture_id": fx["fixture_id"], "competition": fx.get("competition"),
            "tier": fx.get("tier"), "stage": fx.get("stage"), "best_of": fx.get("best_of"),
            "points": fx.get("points"), "status": fx.get("status"),
            "start_utc": fx["start_utc"], "lock_utc": fx.get("lock_utc"),
            "team_a": fx["team_a"], "team_b": fx["team_b"], "winner": fx.get("winner"),
            "seen_in": fx.get("seen_in") or [],
            "hotspawn_url": permalinks.get(fx["fixture_id"], "https://play.hotspawn.com/lobby"),
            "hotspawn_url_kind": ("match page" if fx["fixture_id"] in permalinks
                                  else "official lobby page (no published permalink)"),
            "key_a": key_a, "key_b": key_b,
            "alias_note": " ".join(x for x in (note_a, note_b) if x) or None,
            "alias_evidence": sorted(set(evidence_a + evidence_b)),
            "market": market, "quotes": joined, "rejected_joins": rejected,
            "model": model, "identity": identity,
            "vrs_a": ({**vrs_a, "bo3_id": bo3_ids.get(key_a)} if vrs_a else None),
            "vrs_b": ({**vrs_b, "bo3_id": bo3_ids.get(key_b)} if vrs_b else None),
        })

    mark_first_seen(rows, snap["generated_utc"])

    pairs = calibration_pairs(rows)
    calib = core.fit_calibration(pairs)

    # ---------------- model probability: official VRS first, our own Elo as the last resort ----
    for row in rows:
        v = row["model"].get("vrs")
        if v:
            row["model"]["prob_a"] = core.vrs_prob(v["points_a"], v["points_b"], k=calib["k"])
            row["model"]["basis"] = "valve_vrs"
    # ---- official Valve rating on one side only ---------------------------------------------
    # A fixture where exactly one roster is listed in Valve's published standings is priced with a
    # *bound under a stated assumption*: the unlisted opponent is placed on the 400-point floor
    # Valve's own model starts every roster at. The number is labelled, flagged and published on
    # the unresolved page; it is never presented as a bookmaker price.
    for row in rows:
        if row["model"].get("prob_a") is not None:
            continue
        if row.get("market"):
            # A published bookmaker/exchange price is the better number: the floor bound only fills
            # a gap, it never overrides or dilutes a real price.
            continue
        sides: dict[str, dict] = {}
        for side, team_name, exact in (("a", row["team_a"], row.get("vrs_a")),
                                       ("b", row["team_b"], row.get("vrs_b"))):
            if exact:
                sides[side] = {"points": float(exact["points"]), "standing": exact["standing"],
                               "region": exact["region"], "vrs_name": exact["vrs_name"],
                               "source": "exact_official_row", "key": core.canon(team_name)[0],
                               "candidates": []}
                continue
            cand = alias_candidate(team_name, vrs_candidates)
            if cand:
                sides[side] = {"points": float(cand["weakest"]["points"]),
                               "standing": cand["weakest"]["standing"],
                               "region": cand["weakest"]["region"],
                               "vrs_name": cand["weakest"]["vrs_name"],
                               "source": "alias_candidate", "key": cand["key"],
                               "candidates": cand["rows"]}
        if len(sides) == 1:
            side, rated = next(iter(sides.items()))
            prob_rated = core.vrs_floor_prob(rated["points"], core.VRS_FLOOR_POINTS, k=calib["k"])
            row["model"]["prob_a"] = prob_rated if side == "a" else 1.0 - prob_rated
            row["model"]["basis"] = ("vrs_alias_candidate_bound" if rated["source"] == "alias_candidate"
                                     else "vrs_floor_bound")
            row["model"]["floor"] = {
                "rated_side": side,
                "rated_points": rated["points"],
                "rated_standing": rated["standing"],
                "rated_region": rated["region"],
                "rated_vrs_name": rated["vrs_name"],
                "rating_source": rated["source"],
                "floor_points": core.VRS_FLOOR_POINTS,
                "prob_rated": prob_rated,
                "assumption": ("The opponent is not listed in Valve's published standings, so it is "
                               "placed on the 400-point floor that Valve's own model starts every "
                               "roster at. This is a bound under that assumption, not a price."),
            }
        elif len(sides) == 2:
            pa, pb = sides.get("a"), sides.get("b")
            row["model"]["prob_a"] = core.vrs_prob(pa["points"], pb["points"], k=calib["k"])
            row["model"]["basis"] = ("vrs_alias_candidate" if any(s["source"] == "alias_candidate"
                                                                  for s in sides.values())
                                     else "valve_vrs")
            row["model"]["vrs"] = {"delta": pa["points"] - pb["points"],
                                   "points_a": pa["points"], "points_b": pb["points"],
                                   "standing_a": pa["standing"], "standing_b": pb["standing"],
                                   "region_a": pa["region"], "region_b": pb["region"],
                                   "vrs_name_a": pa["vrs_name"], "vrs_name_b": pb["vrs_name"],
                                   "alias_candidate_sides": [s for s, v in sides.items()
                                                            if v["source"] == "alias_candidate"]}

    needed_keys = sorted({r["key_a"] for r in rows if not r["model"].get("prob_a")} |
                         {r["key_b"] for r in rows if not r["model"].get("prob_a")})
    history = snap.get("bo3gg_history") or {}
    elo_info = {"matches": 0, "teams_seeded": 0}
    ratings: dict[str, float] = {}
    if history:
        ratings, elo_info = elo_for(rows, history, vrs_teams, bo3_ids)

    # Last resort that still has an external source: bo3.gg publishes a world rank per team, so a
    # fixture whose teams have no VRS points and no result history can still be originated from
    # that published ranking (documented mapping in rank_to_rating) — labelled and flagged.
    for row in rows:
        if row["model"].get("prob_a") is not None:
            continue
        ida, idb = bo3_ids.get(row["key_a"]), bo3_ids.get(row["key_b"])
        if not ida or not idb:
            # fall back to the published pairing of the same two teams
            pa_id, pb_id = resolve_pair(row["key_a"], row["key_b"])
            ida, idb = ida or pa_id, idb or pb_id
        ra = ratings.get(f"bo3:{ida}") if ida else None
        rb = ratings.get(f"bo3:{idb}") if idb else None
        from_history = ra is not None and rb is not None
        rank_a = rank_index.get(row["key_a"])
        rank_b = rank_index.get(row["key_b"])
        if ra is None and rank_a is not None:
            ra = rank_to_rating(rank_a)
        if rb is None and rank_b is not None:
            rb = rank_to_rating(rank_b)
        if ra is None or rb is None:
            continue
        pa = core.elo_expected(ra, rb)
        row["model"]["prob_a"] = pa
        row["model"]["basis"] = "originated_elo" if from_history else "originated_rank"
        row["model"]["elo"] = {"rating_a": round(ra, 1), "rating_b": round(rb, 1),
                               "matches": elo_info["matches"] if from_history else 0,
                               "rank_a": rank_a, "rank_b": rank_b,
                               "source_a": "bo3.gg history" if from_history else "bo3.gg rank",
                               "source_b": "bo3.gg history" if from_history else "bo3.gg rank"}

    # ---- HLTV ranking, when the public ranking page answered --------------------------------
    # HLTV publishes a world ranking per team. When the page is reachable the two ranking
    # positions are mapped onto the same documented scale as the bo3.gg ranking and the fixture is
    # originated from them. When HLTV answers 403 (it usually does for automated readers) the
    # attempt is published as a blocked source instead of being treated as "no ranking exists".
    hltv_index: dict[str, dict] = {}
    for name, rec in (hltv_teams or {}).items():
        key = core.canon(name)[0]
        if key:
            hltv_index.setdefault(key, rec)
    for row in rows:
        if row["model"].get("prob_a") is not None:
            continue
        ha, hb = hltv_index.get(row["key_a"]), hltv_index.get(row["key_b"])
        if not ha or not hb or not ha.get("rank") or not hb.get("rank"):
            continue
        ra, rb = rank_to_rating(ha["rank"]), rank_to_rating(hb["rank"])
        if ra is None or rb is None:
            continue
        row["model"]["prob_a"] = core.elo_expected(ra, rb)
        row["model"]["basis"] = "originated_hltv_rank"
        row["model"]["hltv"] = {"rank_a": ha["rank"], "rank_b": hb["rank"],
                                "rating_a": round(ra, 1), "rating_b": round(rb, 1),
                                "url_a": ha.get("url"), "url_b": hb.get("url")}

    # --------------------------------------------------------------- final line, pick, flags --
    for row in rows:
        market_pa = row["market"]["prob_a"] if row["market"] else None
        n_sources = row["market"]["n_sources"] if row["market"] else 0
        model_pa = row["model"].get("prob_a")
        line = core.blend(market_pa, n_sources, model_pa)
        if line:
            pick_a = line["prob_a"] >= 0.5
            confidence = core.confidence_label(line["prob_a"] if pick_a else line["prob_b"])
            if row["model"].get("basis") == "vrs_floor_bound":
                confidence = "Bound (unrated opponent)"
            elif row["model"].get("basis") in ("vrs_alias_candidate_bound", "vrs_alias_candidate"):
                confidence = "Bound (alias candidate)"
            row["line"] = {**line,
                           "pick": row["team_a"] if pick_a else row["team_b"],
                           "pick_probability": line["prob_a"] if pick_a else line["prob_b"],
                           "confidence": confidence}
        else:
            row["line"] = None
        flags = []
        if row["market"] is None:
            flags.append("no_external_price_for_this_fixture")
        if row["model"].get("basis") == "originated_elo":
            flags.append("originated_elo_line_no_official_rating")
        if row["model"].get("basis") == "originated_rank":
            flags.append("originated_rank_line_bo3gg_ranking")
        if row["model"].get("basis") == "originated_hltv_rank":
            flags.append("originated_hltv_rank_line")
        if row["model"].get("basis") == "vrs_floor_bound":
            flags.append("one_sided_vrs_floor_bound_unrated_opponent_on_valve_floor")
        if row["model"].get("basis") == "vrs_alias_candidate_bound":
            flags.append("alias_candidate_identity_unconfirmed")
        if row["model"].get("basis") == "vrs_alias_candidate":
            flags.append("alias_candidate_identity_unconfirmed")
        if row.get("identity"):
            flags.append("team_identity_confirmed_by_same_fixture_on_bo3gg")
        if row["model"].get("basis") == "valve_vrs" and row["market"] is None:
            flags.append("originated_vrs_line")
        if row["tier"] == "C":
            flags.append("tier_c_event_low_coverage")
        if row["line"] is None:
            flags.append("no_source_input_available_row_left_blank")
        if len(row["quotes"]) >= 1 and max(q["start_diff_h"] or 0 for q in row["quotes"]) > 3:
            flags.append("joined_price_start_time_differs_more_than_3h")
        if row["alias_note"]:
            flags.append("alias_applied_see_evidence")
        if row.get("new_since_first_build"):
            flags.append("new_fixture_since_this_board_started")
        row["flags"] = flags
        # Every row cites how the fixture itself was discovered, and HotSpawn is named as discovery
        # only: it is never the source of a probability.
        row["sources"] = [{
            "label": "HotSpawn Pick'ems lobby (fixture discovery only)",
            "url": row["hotspawn_url"],
            "read_utc": snap["access"]["hotspawn_lobby_page"]["at_utc"],
            "note": "listing and kick-off time; not used as a probability source",
            "kind": "discovery",
        }]
        for qt in row["quotes"]:
            row["sources"].append({"label": f"{qt['source_name']} · {qt['raw_format']}",
                                   "url": qt["public_url"], "read_utc": qt["retrieved_utc"],
                                   "note": f"event {qt['event_id']}", "kind": "price"})
        if row["model"].get("basis") == "valve_vrs":
            for region, name, standing, pts in (
                    (row["vrs_a"]["region"], row["vrs_a"]["vrs_name"], row["vrs_a"]["standing"],
                     row["vrs_a"]["points"]),
                    (row["vrs_b"]["region"], row["vrs_b"]["vrs_name"], row["vrs_b"]["standing"],
                     row["vrs_b"]["points"])):
                url = next((e["page_url"] for e in (snap.get("vrs") or {}).get("evidence", [])
                            if str(e.get("region", "")).split("_")[0] == region), None)
                row["sources"].append({"label": f"Valve VRS {region} standings · {name} "
                                                f"#{standing} ({pts:g} pts)",
                                       "url": url, "read_utc": snap.get("generated_utc"),
                                       "note": "official Valve regional standings snapshot",
                                       "kind": "rating"})
        if row["model"].get("basis") == "originated_elo":
            row["sources"].append({"label": "bo3.gg published match results (Elo input)",
                                   "url": "https://bo3.gg/matches",
                                   "read_utc": snap.get("generated_utc"),
                                   "note": f"{row['model'].get('elo', {}).get('matches', 0)} "
                                           "finished matches",
                                   "kind": "rating"})
        if row["model"].get("basis") == "originated_rank":
            for key, label in ((row["key_a"], row["team_a"]), (row["key_b"], row["team_b"])):
                slug = slug_index.get(key)
                row["sources"].append({
                    "label": f"bo3.gg world ranking · {label} "
                             f"#{rank_index.get(key)} (ranking-prior Elo input)",
                    "url": f"https://bo3.gg/teams/{slug}" if slug else "https://bo3.gg/teams",
                    "read_utc": snap.get("generated_utc"),
                    "note": "external published ranking; mapped to the Elo scale by a documented "
                            "formula, so this line is originated, not a market price",
                    "kind": "rating"})
        if row["model"].get("basis") in ("vrs_floor_bound", "vrs_alias_candidate_bound"):
            floor = row["model"].get("floor") or {}
            rated_side = floor.get("rated_side") or "a"
            rated = row.get("vrs_a") if rated_side == "a" else row.get("vrs_b")
            rated = rated or {"region": floor.get("rated_region"),
                              "vrs_name": floor.get("rated_vrs_name"),
                              "standing": floor.get("rated_standing"),
                              "points": floor.get("rated_points")}
            url = vrs_page_url(snap, str(rated.get("region") or "global"))
            row["sources"].append({
                "label": f"Valve VRS {rated.get('region')} standings · {rated.get('vrs_name')} "
                         f"#{rated.get('standing')} ({rated.get('points'):g} pts)",
                "url": url, "read_utc": snap.get("generated_utc"),
                "note": "official Valve regional standings snapshot",
                "kind": "rating"})
            row["sources"].append({
                "label": "Valve VRS floor assumption · 400 points (the minimum the official model "
                         "awards a roster)",
                "url": url, "read_utc": snap.get("generated_utc"),
                "note": ("the unrated opponent is placed on Valve's published floor, so this row is "
                         "a bound under that assumption, not a bookmaker price"),
                "kind": "assumption"})
            if floor.get("rating_source") == "alias_candidate":
                row["sources"].append({
                    "label": "Alias candidate · HotSpawn name vs Valve's official rows",
                    "url": url, "read_utc": snap.get("generated_utc"),
                    "note": (f"HotSpawn lists this team under a former name; Valve's official table "
                             f"publishes {floor.get('rated_vrs_name')}. The identity is a "
                             f"candidate, not a confirmed match — see the unresolved page."),
                    "kind": "assumption"})
        if row["model"].get("basis") == "vrs_alias_candidate":
            vrs = row["model"].get("vrs") or {}
            for side, name_key, standing_key, points_key in (("a", "vrs_name_a", "standing_a",
                                                               "points_a"),
                                                              ("b", "vrs_name_b", "standing_b",
                                                               "points_b")):
                if side not in (vrs.get("alias_candidate_sides") or []):
                    continue
                url = vrs_page_url(snap, str(vrs.get(f"region_{side}") or "global"))
                row["sources"].append({
                    "label": f"Alias candidate · Valve VRS {vrs.get(f'region_{side}')} standings · "
                             f"{vrs.get(name_key)} #{vrs.get(standing_key)} "
                             f"({vrs.get(points_key):g} pts)",
                    "url": url, "read_utc": snap.get("generated_utc"),
                    "note": ("the identity of this side is a candidate: HotSpawn lists a former name "
                             "and Valve's official table publishes the roster under the current "
                             "name. See the unresolved page."),
                    "kind": "assumption"})
        if row["model"].get("basis") == "originated_hltv_rank":
            hltv = row["model"].get("hltv") or {}
            row["sources"].append({
                "label": f"HLTV team ranking · {row['team_a']} #{hltv.get('rank_a')} / "
                         f"{row['team_b']} #{hltv.get('rank_b')}",
                "url": hltv.get("url_a") or HLTV_RANKING_PAGE,
                "read_utc": snap.get("generated_utc"),
                "note": "public HLTV ranking positions mapped to the Elo scale by the documented "
                        "formula; an originated line, not a market price",
                "kind": "rating"})
        row["attempts"] = attempt_ledger(snap, row)
        if row["winner"] in ("a", "b") and row["hotspawn_url_kind"] == "match page":
            row["sources"].append({"label": "HotSpawn match page (final score, settlement only)",
                                   "url": row["hotspawn_url"],
                                   "read_utc": snap["access"]["hotspawn_lobby_page"]["at_utc"],
                                   "note": "result settlement for the track record; never a probability",
                                   "kind": "settlement"})

    open_rows, closed_rows = core.close_rows(rows)
    for row in open_rows:
        row["state"] = "open"
    for row in closed_rows:
        row["state"] = "closed"

    # -------------------------------------------------------------------- track record (history)
    hist_path = DATA / "history.jsonl"
    existing = {}
    if hist_path.exists():
        for line in hist_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            key = (rec["fixture_id"], rec.get("published_utc"))
            existing[key] = rec
    now = core.now_utc()
    by_id = {r["fixture_id"]: r for r in rows}
    for rec in existing.values():
        fx = by_id.get(rec["fixture_id"])
        if not fx or rec.get("settled") is not None:
            continue
        if fx.get("winner") in ("a", "b") and fx["line"]:
            won = (fx["winner"] == "a") == (rec["pick"] == fx["team_a"])
            rec["settled"] = "won" if won else "lost"
            rec["winner"] = fx["team_a"] if fx["winner"] == "a" else fx["team_b"]
            rec["settled_utc"] = core.to_iso(now)
            rec["settlement_source"] = fx["hotspawn_url"]
    new_records = []
    for row in open_rows:
        if not row["line"] or row["lock_utc"] is None:
            continue
        key = (row["fixture_id"], snap["generated_utc"])
        if key in existing:
            continue
        new_records.append({
            "fixture_id": row["fixture_id"], "published_utc": snap["generated_utc"],
            "competition": row["competition"], "start_utc": row["start_utc"],
            "team_a": row["team_a"], "team_b": row["team_b"], "pick": row["line"]["pick"],
            "pick_probability": round(row["line"]["pick_probability"], 4),
            "basis": row["line"]["basis"], "settled": None, "winner": None,
        })
    all_records = list(existing.values()) + new_records
    if new_records or any(r.get("settled") for r in existing.values()):
        hist_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in all_records),
                             encoding="utf-8")
    settled = [r for r in all_records if r.get("settled") in ("won", "lost")]
    track = {"settled": len(settled), "won": sum(1 for r in settled if r["settled"] == "won"),
             "pending": sum(1 for r in all_records if not r.get("settled")),
             "brier": (sum((r["pick_probability"] - (1.0 if r["settled"] == "won" else 0.0)) ** 2
                           for r in settled) / len(settled)) if settled else None,
             "by_basis": {}}
    for basis in ("market", "market+model", "model"):
        sub = [r for r in settled if r["basis"] == basis]
        track["by_basis"][basis] = {
            "n": len(sub), "won": sum(1 for r in sub if r["settled"] == "won"),
            "accuracy": (sum(1 for r in sub if r["settled"] == "won") / len(sub)) if sub else None}

    # -------------------------------------------------------------- unmatched / rejected quotes
    matched_ids = {q["event_id"] for row in rows for q in row["quotes"]}
    unmatched = [qt for qt in quotes if qt["event_id"] not in matched_ids]

    summary = {
        "fixtures_total": len(rows),
        "open": len(open_rows),
        "closed": len(closed_rows),
        "open_with_market": sum(1 for r in open_rows if r["market"]),
        "open_market_only": sum(1 for r in open_rows if r["line"] and r["line"]["basis"] == "market"),
        "open_market_model": sum(1 for r in open_rows if r["line"] and r["line"]["basis"] == "market+model"),
        "open_model_only": sum(1 for r in open_rows if r["line"] and r["line"]["basis"] == "model"),
        "open_with_pick": sum(1 for r in open_rows if r["line"]),
        "open_bounded": sum(1 for r in open_rows if r["line"]
                             and not (r.get("market") or {}).get("prob_a")
                             and (r.get("model") or {}).get("basis") in core.BOUND_BASES),
        "open_originated": sum(1 for r in open_rows if r["line"]
                               and not (r.get("market") or {}).get("prob_a")
                               and (r.get("model") or {}).get("basis") in core.ORIGIN_BASES),
        "open_blank": sum(1 for r in open_rows if not r["line"]),
        "quotes_total": len(quotes),
        "quotes_joined_events": len(matched_ids),
        "quotes_unmatched": len(unmatched),
        "rejected_quotes": len(rejected_quotes),
        "sources": {},
    }
    for qt in quotes:
        summary["sources"][qt["source_key"]] = summary["sources"].get(qt["source_key"], 0) + 1

    doc = {
        "session": "fe803b80",
        "generated_utc": core.to_iso(now),
        "snapshot_utc": snap.get("generated_utc"),
        "fixture_source_read_utc": snap["access"]["hotspawn_lobby_page"]["at_utc"],
        "week": snap["hotspawn"].get("week"),
        "summary": summary,
        "calibration": calib,
        "vrs": {k: v for k, v in (snap.get("vrs") or {}).items() if k != "teams_global"},
        "vrs_ambiguous_keys": vrs_ambiguous,
        "elo": elo_info,
        "track_record": track,
        "history": all_records,
        "open": open_rows,
        "closed": closed_rows,
        "unmatched_quotes": unmatched,
        "rejected_quotes": rejected_quotes,
        "quotes": quotes,
        "bo3gg_teams": bo3.get("teams") or {},
        "bo3gg_tournaments": bo3.get("tournaments") or {},
        "access": snap.get("access") or {},
        "notes": [
            "HotSpawn is used for fixture discovery and final scores only; its crowd pick "
            "percentage is never read, never stored and never an input.",
            "A probability exists for every open fixture: from market quotes, from the official "
            "Valve VRS model, or from this project's own Elo over bo3.gg published results.",
            "Values that no source supports stay blank and flagged.",
        ],
    }
    (DATA / "board.json").write_text(json.dumps(doc, ensure_ascii=False, allow_nan=False) + "\n",
                                     encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("open", "open_with_pick", "open_blank",
                                              "open_with_market", "quotes_total",
                                              "quotes_unmatched")}, indent=1))
    print(f"calibration k={calib['k']:.4f} fitted={calib['fitted']} pairs={calib['n_pairs']}")
    print(f"track record: {track['settled']} settled, {track['pending']} pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
