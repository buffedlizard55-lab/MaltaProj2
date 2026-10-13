#!/usr/bin/env python3
"""
Session 42580809 — originate our own lines for fixtures the market does not price.

Two documented methods, both built only from outside sources:

  A. Market graph (Bradley-Terry). Every collected moneyline is one observation of
     logit(p) = strength_A - strength_B. Strengths are fitted by maximum likelihood over the whole
     graph (including markets for matches outside the pick'em), so a fixture between two teams the
     market does price, but which no book prices directly, gets a line that is implied by those
     prices. Teams the market never prices are absent from the graph by construction.

  B. Valve Regional Standings (official Valve ranking). p = sigmoid((points_A - points_B)/scale),
     with `scale` fitted by least squares against the market-derived rows where both teams carry a
     VRS standing — i.e. the model is calibrated on real prices and reports its own fit error.
     Source: https://github.com/ValveSoftware/counter-strike_regional_standings (mirrored in
     evidence/vrs_*.md).

Neither method is a bookmaker quote. Every originated row on the site is labelled as originated and
carries the inputs that produced it (team strengths / standings, source URLs, fit diagnostics).

Output: data/originated_42580809.json
"""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
EV = os.path.join(HERE, "evidence")
DATA = os.path.join(REPO, "data")

ITERATIONS = 600
LR = 0.25
REG = 0.02
VRS_SNAPSHOT = "2026_10_05"

ALIASES = {
    "9z globant": "9z", "nip": "ninjas in pyjamas", "bb": "betboom", "bb team": "betboom",
    "pvision": "parivision", "keyd stars": "keyd", "ex keyd stars": "keyd",
    "overtake": "overtake sector", "aurora gaming": "aurora", "team aurora": "aurora",
    "sashi esport": "sashi", "team falcons": "falcons", "gremio esports": "gremio",
    "team spirit": "spirit", "los ninos": "los ninos", "wbt academy": "wrotberry",
    "esport academy copenhagen": "eac", "pcific espor": "pcific", "privateer gaming": "privateer",
}
SUFFIXES = (" esports", " esport", " e sports", " gaming", " club", " team", " csgo", " cs2")


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " and ")
    for ch in ".,'’`´:;!?()[]{}*+-_/\\\"":
        s = s.replace(ch, " ")
    s = " ".join(s.split())
    for p in ("team ",):
        if s.startswith(p) and len(s) > len(p) + 2:
            s = s[len(p):]
    changed = True
    while changed:
        changed = False
        for suf in SUFFIXES:
            if s.endswith(suf) and len(s) > len(suf) + 2:
                s = s[: -len(suf)].strip()
                changed = True
    return ALIASES.get(s, s)


def sigmoid(x):
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


# ------------------------------------------------------------------ method A: market graph
MIN_OBS = 3          # a team needs this many market observations to carry a usable strength
MIN_OPPONENTS = 2    # ... against at least this many different opponents


def fit_bradley_terry(observations, iterations=300):
    """Bradley-Terry by the MM (Zermelo) algorithm: each observation is one match with the
    quoted probability split between the two teams as fractional wins."""
    teams = sorted({t for o in observations for t in (o["team_a_norm"], o["team_b_norm"])})
    wins, played = {t: 0.0 for t in teams}, {t: {} for t in teams}
    for o in observations:
        a, b = o["team_a_norm"], o["team_b_norm"]
        wins[a] += o["p_a"]
        wins[b] += o["p_b"]
        played[a][b] = played[a].get(b, 0) + 1
        played[b][a] = played[b].get(a, 0) + 1
    s = {t: 1.0 for t in teams}
    for _ in range(iterations):
        new = {}
        for t in teams:
            den = sum(played[t][j] / (s[t] + s[j]) for j in played[t])
            new[t] = wins[t] / den if den > 0 else s[t]
        z = math.exp(sum(math.log(max(v, 1e-12)) for v in new.values()) / max(1, len(new)))
        s = {t: max(v, 1e-12) / z for t, v in new.items()}
    return {t: math.log(v) for t, v in s.items()}


def obs_stats(observations):
    counts, opponents = {}, {}
    for o in observations:
        for team, other in ((o["team_a_norm"], o["team_b_norm"]), (o["team_b_norm"], o["team_a_norm"])):
            counts[team] = counts.get(team, 0) + 1
            opponents.setdefault(team, set()).add(other)
    return counts, opponents


def usable(team, counts, opponents):
    return counts.get(team, 0) >= MIN_OBS and len(opponents.get(team, ())) >= MIN_OPPONENTS


def cross_validate(observations, rows_with_market):
    """Leave-one-fixture-out: refit without that fixture's own quotes, predict it, compare with
    the market consensus. Only fixtures whose teams stay usable after removal are scored."""
    counts, opponents = obs_stats(observations)
    scored, errors, briers = [], [], []
    pairs_seen = {}
    for o in observations:
        pairs_seen.setdefault(frozenset((o["team_a_norm"], o["team_b_norm"])), set()).add(o["fixture_id"])
    for r in rows_with_market:
        a, b = norm(r["team_a"]), norm(r["team_b"])
        held = {o["fixture_id"] for o in observations if o["fixture_id"] == r["fixture_id"]}
        # also drop observations of the same pairing collected from another batch (fixture_id None):
        # otherwise the fixture's own prices would leak back into the training set.
        pair = frozenset((a, b))
        train = [o for o in observations
                 if o["fixture_id"] not in held
                 and frozenset((o["team_a_norm"], o["team_b_norm"])) != pair]
        c2, o2 = obs_stats(train)
        if not (usable(a, c2, o2) and usable(b, c2, o2)):
            continue
        strengths = fit_bradley_terry(train)
        model_p = sigmoid(strengths[a] - strengths[b])
        err = abs(model_p - r["p_a"])
        errors.append(err)
        briers.append((model_p - r["p_a"]) ** 2)
        scored.append({"fixture_id": r["fixture_id"], "match": f'{r["team_a"]} vs {r["team_b"]}',
                       "market_p": round(r["p_a"], 4), "model_p": round(model_p, 4),
                       "abs_error": round(err, 4)})
    out = {"held_out_fixtures": len(scored), "rows": scored}
    if errors:
        out["mean_absolute_error"] = round(sum(errors) / len(errors), 4)
        out["brier"] = round(sum(briers) / len(briers), 4)
    return out


# ------------------------------------------------------------------ method B: Valve VRS
VRS_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", re.M)
CLAMP = (0.10, 0.90)


def load_vrs():
    """Parse Valve's standings table. A name that appears more than once (Valve lists separate
    entries with the same team name, usually different rosters) is recorded as ambiguous and is
    never used for an originated line, because the fixture cannot be tied to one entry."""
    path = os.path.join(EV, f"vrs_global_{VRS_SNAPSHOT}.md")
    if not os.path.exists(path):
        return {}, {}, None
    text = open(path, encoding="utf-8").read()
    table, ambiguous = {}, {}
    for standing, points, name in VRS_ROW.findall(text):
        key = norm(name)
        entry = {"standing": int(standing), "points": int(points), "name": name.strip()}
        if key in table:
            ambiguous.setdefault(key, [table[key]]).append(entry)
        else:
            table[key] = entry
    return table, ambiguous, (f"https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/"
                             f"live/2026/standings_global_{VRS_SNAPSHOT}.md")


def fit_vrs_scale(table, rows_with_market):
    """Fit the points->probability scale against real prices; report the fit error."""
    pairs = []
    deep = []
    for r in rows_with_market:
        a, b = norm(r["team_a"]), norm(r["team_b"])
        if a in table and b in table:
            pairs.append((table[a]["points"] - table[b]["points"], r["p_a"], r))
    if len(pairs) < 3:
        return None, {"note": "fewer than three priced fixtures have both teams in Valve's standings",
                      "calibration_fixtures": len(pairs)}
    scale = 120.0
    for _ in range(400):
        grad = 0.0
        for diff, p_market, _r in pairs:
            p = sigmoid(diff / scale)
            grad += 2 * (p - p_market) * p * (1 - p) * (-diff / (scale ** 2))
        step = 0.5 * grad / len(pairs)
        if abs(step) < 1e-9:
            break
        scale = min(4000.0, max(5.0, scale - step))
    rows, errors, briers = [], [], []
    for diff, p_market, r in pairs:
        p = sigmoid(diff / scale)
        err = abs(p - p_market)
        errors.append(err)
        briers.append((p - p_market) ** 2)
        rows.append({"fixture_id": r["fixture_id"], "match": f'{r["team_a"]} vs {r["team_b"]}',
                     "points_difference": diff, "market_p": round(p_market, 4),
                     "model_p": round(p, 4), "abs_error": round(err, 4)})
    if scale:
        deep = [(diff, p_market) for diff, p_market, r in pairs
                if any(q["source_key"] in ("pinnacle", "bovada") for q in r["sources"])]
        if deep:
            derr = [abs(sigmoid(diff / scale) - p) for diff, p in deep]
            dbri = [(sigmoid(diff / scale) - p) ** 2 for diff, p in deep]
            fit_deep = {"n": len(deep), "mean_absolute_error": round(sum(derr) / len(derr), 4),
                        "brier": round(sum(dbri) / len(dbri), 4)}
        else:
            fit_deep = {"n": 0}
    return scale, {"calibration_fixtures": len(pairs), "scale_points": round(scale, 1),
                   "calibration_on_deeper_books": fit_deep,
                   "mean_absolute_error": round(sum(errors) / len(errors), 4),
                   "brier": round(sum(briers) / len(briers), 4),
                   "clamp": list(CLAMP), "rows": rows}


def vrs_probability(table, scale, ambiguous, team_a, team_b):
    a, b = norm(team_a), norm(team_b)
    if not scale or a not in table or b not in table or a in ambiguous or b in ambiguous:
        return None
    p = sigmoid((table[a]["points"] - table[b]["points"]) / scale)
    return min(CLAMP[1], max(CLAMP[0], p))


def main() -> int:
    graph_doc = json.load(open(os.path.join(EV, "matched_quotes.json"), encoding="utf-8"))
    observations = graph_doc["observations"]
    board = json.load(open(os.path.join(DATA, "board_42580809.json"), encoding="utf-8"))
    rows = board["rows"]
    with_market = [r for r in rows if r["basis"] == "market-derived"]

    strengths = fit_bradley_terry(observations)
    cv = cross_validate(observations, with_market)
    table, ambiguous, vrs_url = load_vrs()
    scale, vrs_fit = fit_vrs_scale(table, with_market)

    counts, opponents = obs_stats(observations)

    out_rows = []
    for r in rows:
        if r["basis"] != "unverified" or r["stale"]:
            continue
        a, b = norm(r["team_a"]), norm(r["team_b"])
        rec = {"fixture_id": r["fixture_id"], "team_a": r["team_a"], "team_b": r["team_b"],
               "tournament": r["tournament"], "scheduled_start_time_utc": r["scheduled_start_time_utc"],
               "method": None, "originated_p_a": None, "originated_p_b": None,
               "hotspawn_url": r["hotspawn_url"], "inputs": {}, "source_urls": []}
        bt_ok = usable(a, counts, opponents) and usable(b, counts, opponents)
        vrs_p = vrs_probability(table, scale, ambiguous, r["team_a"], r["team_b"])
        if bt_ok:
            p = sigmoid(strengths[a] - strengths[b])
            rec.update(method="market-graph (Bradley-Terry on collected prices)",
                       originated_p_a=round(p, 4), originated_p_b=round(1 - p, 4))
            rec["inputs"] = {"team_a_market_observations": counts[a], "team_b_market_observations": counts[b],
                             "team_a_distinct_opponents": len(opponents[a]),
                             "team_b_distinct_opponents": len(opponents[b]),
                             "graph_observations": len(observations), "min_observations_rule": MIN_OBS,
                             "cross_validated_mae": cv.get("mean_absolute_error"),
                             "cross_validated_brier": cv.get("brier")}
            if vrs_p is not None:
                rec["cross_check_vrs_probability_a"] = round(vrs_p, 4)
        elif vrs_p is not None:
            rec.update(method="Valve Regional Standings (official ranking, calibrated)",
                       originated_p_a=round(vrs_p, 4), originated_p_b=round(1 - vrs_p, 4))
            rec["inputs"] = {"team_a_vrs": table[a], "team_b_vrs": table[b],
                             "scale_points": round(scale, 1),
                             "calibration_fixtures": vrs_fit.get("calibration_fixtures"),
                             "calibration_mae": vrs_fit.get("mean_absolute_error"),
                             "calibration_brier": vrs_fit.get("brier"),
                             "clamp": list(CLAMP)}
            if vrs_url:
                rec["source_urls"].append(vrs_url)
        else:
            reasons = []
            for team, normed in ((r["team_a"], a), (r["team_b"], b)):
                if counts.get(normed, 0) < MIN_OBS:
                    reasons.append(f"{team}: only {counts.get(normed, 0)} collected market observation(s)")
                elif len(opponents.get(normed, ())) < MIN_OPPONENTS:
                    reasons.append(f"{team}: observations against a single opponent only")
                if normed not in table:
                    reasons.append(f"{team}: not in Valve Regional Standings {VRS_SNAPSHOT.replace('_', '-')}")
                elif normed in ambiguous:
                    entries = ", ".join(f'#{e["standing"]} ({e["points"]} pts)' for e in ambiguous[normed])
                    reasons.append(f"{team}: ambiguous in Valve's standings — the name is listed more than once "
                                   f"({entries}); not used rather than guessed")
            rec["unoriginated_because"] = reasons
        out_rows.append(rec)

    doc = {"generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "session": "42580809",
           "note": ("Originated lines are this project's own model output, not bookmaker quotes. "
                    "Method A is fitted to collected market prices; method B is calibrated against "
                    "those prices using Valve's official Regional Standings."),
           "graph": {"observations": len(observations),
                     "matched_to_pickem": graph_doc.get("matched"),
                     "outside_pickem": graph_doc.get("extra"),
                     "teams": len(strengths)},
           "method_a_cross_validation": cv,
           "method_b": {"vrs_snapshot": VRS_SNAPSHOT, "vrs_source_url": vrs_url,
                        "teams_in_table": len(table),
                        "ambiguous_names_not_used": {k: v for k, v in sorted(ambiguous.items())},
                        "fit": vrs_fit},
           "rows": out_rows}
    with open(os.path.join(DATA, "originated_42580809.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, ensure_ascii=False)
    print(f"graph: {len(observations)} observations / {len(strengths)} teams; "
          f"CV mae={cv.get('mean_absolute_error')} brier={cv.get('brier')}")
    print(f"VRS: {len(table)} teams; scale={None if not scale else round(scale,1)} "
          f"fit={json.dumps({k: v for k, v in (vrs_fit or {}).items() if k != 'rows'})}")
    for rec in out_rows:
        print(f"  {rec['fixture_id']} {rec['team_a']} vs {rec['team_b']}: "
              f"{rec['method']} p_a={rec['originated_p_a']} {rec.get('unoriginated_because') or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
