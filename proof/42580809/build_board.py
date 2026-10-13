#!/usr/bin/env python3
"""
Session 42580809 — join external quotes to HotSpawn pick'em fixtures and derive probabilities.

Inputs (all evidence, none of it hand-typed):
  proof/42580809/evidence/fixtures.json  - the pick'em window read from the lobby's public API
  proof/42580809/evidence/lines.json     - raw quotes collected by run/collect_lines.py

Matching rules (strict; every decision and rejection is written to evidence/matching.json):
  1. Both participants must match after normalisation, in either order (a reversed fixture
     gets its prices reversed). Aliases are explicit and documented, never fuzzy.
  2. Kalshi teams come from the exchange's own event title; its settlement rule supplies the
     tournament and the original schedule (occurrence_datetime is padded and is not used).
  3. If the source publishes a start time, it must agree with the fixture within 90 minutes.
  4. One quote is assigned to at most one fixture; ambiguous candidates are rejected.

Derivation (clearly labelled, never presented as a source quote):
  bookmaker decimal odds:  q_i = 1/odds_i ; p_i = q_i/(q_a+q_b)      [proportional no-vig]
  Kalshi two-sided book:   p_i = mid_i/(mid_a+mid_b), mid_i = (yes_bid+yes_ask)/2
  consensus:               arithmetic mean of the per-source p_i over all matched sources

Outputs:
  evidence/board.json           - per-fixture board rows (site input)
  evidence/board.csv            - same rows, CSV
  evidence/matched_quotes.json  - every matched market observation incl. non-pick'em matches
                                  (this is the input graph for originate.py)
  evidence/matching.json        - every accept/reject decision with raw rows
  evidence/coverage.json        - per-source and per-tournament coverage
"""

from __future__ import annotations

import csv
import json
import os
import re
import statistics
import unicodedata
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "evidence")
TIME_TOLERANCE_MIN = 90

# Documented aliases: source spelling (already normalised) -> canonical HotSpawn spelling.
ALIASES = {
    "9z globant": "9z",
    "nip": "ninjas in pyjamas",
    "n i p": "ninjas in pyjamas",
    "bb": "betboom",
    "bb team": "betboom",
    "pvision": "parivision",
    "keyd stars": "keyd",
    "overtake": "overtake sector",
    "aurora gaming": "aurora",
    "sashi esport": "sashi",
    "team falcons": "falcons",
    "team aurora": "aurora",
    "gremio esports": "gremio",
}

# Conditional aliases: applied ONLY when the same tournament name and the same scheduled
# start time also match, and every use is recorded in matching.json with both raw spellings.
CONDITIONAL_ALIASES = {
    "wbt academy": "wrotberry",
}

SUFFIXES = (" esports", " esport", " e sports", " gaming", " club", " team", " csgo", " cs2")
PREFIXES = ("team ",)


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " and ")
    for ch in ".,'’`´:;!?()[]{}*+-_/\\\"":
        s = s.replace(ch, " ")
    s = " ".join(s.split())
    for p in PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
    for suf in SUFFIXES:
        if s.endswith(suf):
            s = s[: -len(suf)]
    s = " ".join(s.split())
    return ALIASES.get(s, s)


KALSHI_SCHED_RE = re.compile(
    r"originally scheduled for (?P<date>[A-Z][a-z]{2} \d{1,2}, \d{4}) "
    r"at (?P<time>\d{1,2}:\d{2}\s?[AP]M) (?P<tz>[A-Z]{2,4})", re.I)
KALSHI_TOUR_RE = re.compile(r"wins the (?P<tournament>.+?):\s+.+? vs\.? .+? CS2 match", re.I)
TZ_OFFSETS = {"EDT": -4, "EST": -5, "CDT": -5, "CST": -6, "MDT": -6, "MST": -7,
              "PDT": -7, "PST": -8, "UTC": 0, "GMT": 0}


def kalshi_rule_parts(rules, event_title=None):
    """Teams from the event title, tournament + original schedule from the settlement rule."""
    text = str(rules or "")
    tour = KALSHI_TOUR_RE.search(text)
    sched = KALSHI_SCHED_RE.search(text)
    out = {"tournament": tour.group("tournament").strip() if tour else None,
           "start_utc": None, "teams": None}
    if event_title and " vs" in event_title:
        left, right = re.split(r"\s+vs\.?\s+", event_title, maxsplit=1)
        out["teams"] = (left.strip(), right.strip())
    if sched:
        tz = TZ_OFFSETS.get(sched.group("tz").upper())
        if tz is not None:
            try:
                dt = datetime.strptime(f"{sched.group('date')} {sched.group('time').upper()}",
                                       "%b %d, %Y %I:%M %p")
                out["start_utc"] = (dt - timedelta(hours=tz)).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return out


def tournament_overlap(a, b):
    """Crude but explicit check that two tournament names refer to the same event."""
    ta = {t for t in re.split(r"[^a-z0-9]+", str(a or "").lower()) if len(t) > 2}
    tb = {t for t in re.split(r"[^a-z0-9]+", str(b or "").lower()) if len(t) > 2}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def parse_iso(value):
    if not value:
        return None
    txt = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load(name):
    with open(os.path.join(EV, name), encoding="utf-8") as fh:
        return json.load(fh)


def bookmaker_probabilities(line):
    da, db = line.get("decimal_odds_a"), line.get("decimal_odds_b")
    if not da or not db or da <= 1 or db <= 1:
        return None
    qa, qb = 1 / da, 1 / db
    s = qa + qb
    return qa / s, qb / s, s - 1, {"decimal_odds_a": da, "decimal_odds_b": db,
                                   "implied_a": round(qa, 6), "implied_b": round(qb, 6)}


def kalshi_pair_probabilities(sides):
    """Mid-price probabilities for a two-outcome Kalshi event, normalised over the book."""
    mids, detail = {}, {}
    for s in sides:
        yb, ya, nb, na = s.get("yes_bid"), s.get("yes_ask"), s.get("no_bid"), s.get("no_ask")
        mid = (yb + ya) / 2 if (yb and ya) else None
        mids[s.get("outcome_name")] = mid
        detail[s.get("outcome_name")] = {
            "ticker": s.get("source_market_id"), "yes_bid": yb, "yes_ask": ya,
            "no_bid": nb, "no_ask": na, "mid": mid, "volume": s.get("volume"),
            "api": s.get("source_api_url")}
    return mids, detail


def main() -> int:
    fixtures = load("fixtures.json")
    lines = load("lines.json")["lines"]
    cs2 = [f for f in fixtures["fixtures"] if f["sport"] == "cs2"]
    fx_index = {(norm(f["team_a"]), norm(f["team_b"])): f for f in cs2}
    fx_teams = {t for f in cs2 for t in (norm(f["team_a"]), norm(f["team_b"]))}

    now = datetime.now(tz=timezone.utc)
    decisions, matched = [], []

    # ---------------------------------------------------------------- bookmaker quotes
    for line in lines:
        sk = line["source_key"]
        if sk == "kalshi":
            continue
        a, b = norm(line.get("team_a_name")), norm(line.get("team_b_name"))
        probs = bookmaker_probabilities(line)
        if not a or not b or a == b or not probs:
            decisions.append({"source": sk, "event_id": line.get("source_event_id"),
                              "teams": [line.get("team_a_name"), line.get("team_b_name")],
                              "reason": "unusable quote (missing participants or prices)",
                              "accepted": None})
            continue
        p_a, p_b, over, detail = probs
        if a == norm(line.get("team_a_name")) and (a, b) in fx_index:
            fx, order = fx_index[(a, b)], "same"
        elif (b, a) in fx_index:
            fx, order = fx_index[(b, a)], "reversed"
            p_a, p_b = p_b, p_a
            detail["order"] = "prices reversed: the source lists the fixture the other way round"
        else:
            fx, order = None, None
        delta = None
        if fx:
            lstart, fstart = parse_iso(line.get("start_time_utc")), parse_iso(fx["scheduled_start_time_utc"])
            if lstart and fstart:
                delta = abs((lstart - fstart).total_seconds()) / 60
                if delta > TIME_TOLERANCE_MIN:
                    decisions.append({"source": sk, "event_id": line.get("source_event_id"),
                                      "teams": [line.get("team_a_name"), line.get("team_b_name")],
                                      "fixture_id": fx["fixture_id"],
                                      "reason": f"start time differs by {delta:.0f} min",
                                      "accepted": None})
                    fx = None
        matched.append({
            "fixture_id": fx["fixture_id"] if fx else None,
            "team_a_norm": a, "team_b_norm": b, "p_a": p_a, "p_b": p_b,
            "overround": over, "source_key": sk, "source_name": line.get("source_name"), "weight": 1.0,
            "source_public_url": line.get("source_public_url"), "retrieved_at_utc": line.get("retrieved_at_utc"),
            "market_type": line.get("market_type"), "source_market_id": line.get("source_market_id"),
            "quoted_a": line.get("team_a_name"), "quoted_b": line.get("team_b_name"),
            "start_time_utc": line.get("start_time_utc"), "api": line.get("source_api_url"),
            "detail": detail,
        })
        if fx:
            decisions.append({"source": sk, "event_id": line.get("source_event_id"),
                              "teams": [line.get("team_a_name"), line.get("team_b_name")],
                              "fixture_id": fx["fixture_id"], "order": order,
                              "start_time_delta_min": None if delta is None else round(delta, 1),
                              "accepted": fx["fixture_id"]})

    # ---------------------------------------------------------------- Kalshi quotes
    events: dict[str, list] = {}
    for line in lines:
        if line["source_key"] == "kalshi":
            events.setdefault(line["source_event_id"], []).append(line)
    for ev, sides in sorted(events.items()):
        if len(sides) != 2:
            decisions.append({"source": "kalshi", "event_id": ev, "accepted": None,
                              "reason": f"{len(sides)} outcome markets (expected 2)"})
            continue
        listing = sides[0]
        parts = kalshi_rule_parts(listing.get("source_rules_primary"), listing.get("event_title"))
        teams = [norm(t) for t in (parts["teams"] or [])]
        if len(teams) != 2:
            decisions.append({"source": "kalshi", "event_id": ev, "accepted": None,
                              "reason": "could not read both team names"})
            continue
        a, b = teams
        alias_used = None
        cands = [f for f in cs2 if {norm(f["team_a"]), norm(f["team_b"])} == {a, b}]
        if not cands:
            alt = tuple(CONDITIONAL_ALIASES.get(t, t) for t in (a, b))
            if alt != (a, b):
                cands = [f for f in cs2 if {norm(f["team_a"]), norm(f["team_b"])} == set(alt)]
                if cands and parts["start_utc"]:
                    f0 = cands[0]
                    fstart0 = parse_iso(f0["scheduled_start_time_utc"])
                    same_time = abs((parts["start_utc"] - fstart0).total_seconds()) / 60 <= TIME_TOLERANCE_MIN
                    same_event = tournament_overlap(parts["tournament"], f0["competition_name"]) >= 0.6
                    if not (same_time and same_event):
                        decisions.append({"source": "kalshi", "event_id": ev, "accepted": None,
                                          "reason": ("conditional alias rejected: tournament/time "
                                                     f"confirmation failed (time_ok={same_time}, "
                                                     f"event_ok={same_event})"),
                                          "raw_names": teams,
                                          "rule_tournament": parts["tournament"],
                                          "fixture": f0["fixture_id"]})
                        cands = []
                    else:
                        alias_used = {"raw": list(teams), "mapped_to": list(norm(t) for t in
                                       (f0["team_a"], f0["team_b"])),
                                      "evidence": ("same tournament name and identical scheduled "
                                                   "start time; source spelling differs from HotSpawn"),
                                      "rule_tournament": parts["tournament"],
                                      "fixture": f0["fixture_id"]}
                        decisions.append({"source": "kalshi", "event_id": ev,
                                          "accepted": f0["fixture_id"], "conditional_alias": alias_used})
                        fx_direct = f0
                if not cands:
                    decisions.append({"source": "kalshi", "event_id": ev, "accepted": None,
                                      "reason": "0 fixture candidates",
                                      "raw_names": teams,
                                      "rule_tournament": parts["tournament"]})
                    continue
            else:
                decisions.append({"source": "kalshi", "event_id": ev, "accepted": None,
                                  "reason": "0 fixture candidates", "raw_names": teams,
                                  "rule_tournament": parts["tournament"]})
                continue
        mids, detail = kalshi_pair_probabilities(sides)
        names_by_norm = {norm(s.get("outcome_name")): s.get("outcome_name") for s in sides}
        if any(names_by_norm.get(t) is None or mids.get(names_by_norm[t]) is None for t in (a, b)):
            decisions.append({"source": "kalshi", "event_id": ev, "accepted": None,
                              "reason": "no two-sided mid on one outcome"})
            continue
        ma, mb = mids[names_by_norm[a]], mids[names_by_norm[b]]
        total = ma + mb
        if alias_used:
            fx = fx_direct
            if {norm(fx["team_a"]), norm(fx["team_b"])} != {a, b}:
                ma, mb = mb, ma
            a, b = norm(fx["team_a"]), norm(fx["team_b"])
        else:
            fx = fx_index.get((a, b)) or fx_index.get((b, a))
            if fx and fx_index.get((b, a)) and (a, b) not in fx_index:
                ma, mb = mb, ma
                a, b = b, a
        lstart = parts["start_utc"]
        delta = None
        if fx and lstart:
            fstart = parse_iso(fx["scheduled_start_time_utc"])
            delta = abs((lstart - fstart).total_seconds()) / 60
            if delta > TIME_TOLERANCE_MIN:
                decisions.append({"source": "kalshi", "event_id": ev, "fixture_id": fx["fixture_id"],
                                  "reason": f"rule-scheduled start differs by {delta:.0f} min",
                                  "accepted": None})
                fx = None
        if fx and lstart is None:
            decisions.append({"source": "kalshi", "event_id": ev, "fixture_id": fx["fixture_id"],
                              "reason": "settlement rule gave no parseable start time",
                              "accepted": None})
            fx = None
        matched.append({
            "fixture_id": fx["fixture_id"] if fx else None,
            "team_a_norm": a, "team_b_norm": b, "p_a": ma / total, "p_b": mb / total,
            "overround": total - 1, "source_key": "kalshi", "source_name": "Kalshi", "weight": 1.0,
            "source_public_url": listing.get("source_public_url"),
            "retrieved_at_utc": listing.get("retrieved_at_utc"),
            "market_type": "match winner (Kalshi two-sided book, both outcomes)",
            "quoted_a": parts["teams"][0], "quoted_b": parts["teams"][1],
            "start_time_utc": lstart.strftime("%Y-%m-%dT%H:%M:%SZ") if lstart else None,
            "api": listing.get("source_api_url"), "detail": detail,
            "rule_tournament": parts["tournament"], "conditional_alias": alias_used,
        })
        if fx and not alias_used:
            decisions.append({"source": "kalshi", "event_id": ev, "fixture_id": fx["fixture_id"],
                              "order": "same", "rule_tournament": parts["tournament"],
                              "start_time_delta_min": None if delta is None else round(delta, 1),
                              "accepted": fx["fixture_id"]})

    # ---------------------------------------------------------------- consensus rows
    by_fixture: dict[str, list] = {}
    for m in matched:
        if m["fixture_id"]:
            by_fixture.setdefault(m["fixture_id"], []).append(m)

    rows = []
    for fx in sorted(cs2, key=lambda f: f["scheduled_start_time_utc"] or ""):
        qs = by_fixture.get(fx["fixture_id"], [])
        pa = [q["p_a"] for q in qs]
        row = {
            "fixture_id": fx["fixture_id"], "sport": fx["sport"], "tournament": fx["competition_name"],
            "tier": fx["tier"], "status": fx["status"], "best_of": fx["best_of"],
            "scheduled_start_time_utc": fx["scheduled_start_time_utc"], "lock_time_utc": fx["lock_time_utc"],
            "hotspawn_url": fx["source_url"],
            "hotspawn_pick_pct_reference_only": [fx["team_a_pick_pct"], fx["team_b_pick_pct"]],
            "team_a": fx["team_a"], "team_b": fx["team_b"],
            "team_a_norm": norm(fx["team_a"]), "team_b_norm": norm(fx["team_b"]),
            "offered_points": fx["offered_points"], "tier_points": fx["base_points"],
            "n_sources": len({q["source_key"] for q in qs}),
        }
        if qs:
            row.update({
                "p_a": round(statistics.fmean(pa), 4), "p_a_min": round(min(pa), 4),
                "p_a_max": round(max(pa), 4), "basis": "market-derived",
                "quotes": qs,
            })
            row["p_b"] = round(1 - row["p_a"], 4)
            row["pick_team"] = fx["team_a"] if row["p_a"] >= row["p_b"] else fx["team_b"]
            row["pick_probability"] = round(max(row["p_a"], row["p_b"]), 4)
        else:
            row.update({"p_a": None, "p_b": None, "p_a_min": None, "p_a_max": None,
                        "pick_team": None, "pick_probability": None, "basis": "unverified",
                        "quotes": []})
        rows.append(row)

    # ---------------------------------------------------------------- coverage
    coverage = {
        "generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fixtures_total": len(cs2),
        "fixtures_with_market_line": sum(1 for r in rows if r["n_sources"]),
        "fixtures_without_market_line": sum(1 for r in rows if not r["n_sources"]),
        "market_observations_total": len(matched),
        "observations_matched_to_pickem": sum(1 for m in matched if m["fixture_id"]),
        "distinct_teams_in_market_graph": len({t for m in matched for t in (m["team_a_norm"], m["team_b_norm"])}),
        "pickem_teams_absent_from_market_graph": sorted(fx_teams - {t for m in matched for t in (m["team_a_norm"], m["team_b_norm"])}),
        "by_source": {}, "by_tournament": {},
    }
    for m in matched:
        d = coverage["by_source"].setdefault(m["source_key"], {"quotes": 0, "fixtures": set()})
        d["quotes"] += 1
        if m["fixture_id"]:
            d["fixtures"].add(m["fixture_id"])
    for k, d in coverage["by_source"].items():
        d["fixtures"] = len(d["fixtures"])
    for r in rows:
        d = coverage["by_tournament"].setdefault(r["tournament"], {"total": 0, "priced": 0, "sources": {}})
        d["total"] += 1
        if r["n_sources"]:
            d["priced"] += 1
        for q in r["quotes"]:
            d["sources"][q["source_key"]] = d["sources"].get(q["source_key"], 0) + 1

    with open(os.path.join(EV, "board.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at_utc": coverage["generated_at_utc"],
                   "rules": {
                       "fixtures": "HotSpawn lobby public API; HotSpawn pick percentages are shown for reference only and are never a probability input",
                       "match": "both participants equal after documented normalisation, either order",
                       "time": f"source start time within {TIME_TOLERANCE_MIN} min of the fixture start",
                       "probability": "proportional no-vig on bookmaker odds; mid of the two-sided book on Kalshi",
                       "consensus": "arithmetic mean over matched sources",
                   },
                   "coverage": coverage, "rows": rows}, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(EV, "matched_quotes.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at_utc": coverage["generated_at_utc"],
                   "note": "every external market observation, matched to a pick'em fixture or not",
                   "count": len(matched), "observations": matched}, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(EV, "matching.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated_at_utc": coverage["generated_at_utc"],
                   "accepted": [d for d in decisions if d.get("accepted")],
                   "rejected": [d for d in decisions if not d.get("accepted")]}, fh, indent=1,
                  ensure_ascii=False)
    with open(os.path.join(EV, "coverage.json"), "w", encoding="utf-8") as fh:
        json.dump(coverage, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(EV, "board.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["kickoff_utc", "tournament", "tier", "team_a", "team_b", "pick",
                    "pick_probability", "p_a", "p_b", "n_sources", "source_keys", "basis",
                    "hotspawn_url"])
        for r in rows:
            w.writerow([r["scheduled_start_time_utc"], r["tournament"], r["tier"], r["team_a"],
                        r["team_b"], r["pick_team"], r["pick_probability"], r["p_a"], r["p_b"],
                        r["n_sources"], "|".join(sorted({q["source_key"] for q in r["quotes"]})),
                        r["basis"], r["hotspawn_url"]])

    print(json.dumps({k: v for k, v in coverage.items() if k != "by_tournament"}, indent=1)[:1400])
    print("tournaments:")
    for t, d in sorted(coverage["by_tournament"].items(), key=lambda kv: -kv[1]["total"]):
        print(f"  {t[:44]:46s} {d['priced']}/{d['total']} priced  {d['sources']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
