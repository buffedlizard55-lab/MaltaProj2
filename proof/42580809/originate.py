#!/usr/bin/env python3
"""
Session 42580809 — originate our own line for pick'em fixtures the books do not price.

Method (fully documented, no invented inputs):

  1. Every external quote we collected and matched — including matches that are *not* in the
     pick'em — becomes one observation  logit(p) = s_A - s_B  where p is the market's own
     no-vig probability (bookmaker proportional de-vig, or Kalshi two-sided mid).
  2. A Bradley-Terry model (equivalently, logistic regression on team strengths) is fitted to
     that observation graph by maximum likelihood with gradient ascent. The only data entering
     the fit are real prices published by Pinnacle, Bovada and Kalshi.
  3. The fitted strengths give a probability for any pairing whose two teams are connected to
     the priced graph. Fixtures whose teams the market never prices are left untouched: they
     stay "unverified" on the board rather than being given a made-up number.
  4. Honesty check: leave-one-fixture-out cross-validation over the priced pick'em fixtures.
     For every priced pick'em fixture the model is refit *without* that fixture and its
     prediction error is recorded. The aggregate error is published next to the originated
     probabilities so a reader can judge them.

Outputs:
  proof/42580809/evidence/originated.json - fitted strengths, per-fixture originated
                                            probabilities and the cross-validation report
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "evidence")

ITERATIONS = 400
LEARNING_RATE = 0.35
REGULARISATION = 0.02          # keeps unconnected teams near zero instead of exploding


def load(name):
    with open(os.path.join(EV, name), encoding="utf-8") as fh:
        return json.load(fh)


def fit(obs, exclude_fixture=None):
    """Maximum-likelihood Bradley-Terry fit over the observation graph.

    Each observation contributes p (market probability for team_a). We maximise
    sum log-likelihood with a small L2 pull to zero (identifiability + damping).
    """
    teams = sorted({t for o in obs for t in (o["team_a"], o["team_b"])})
    idx = {t: i for i, t in enumerate(teams)}
    s = [0.0] * len(teams)
    rows = [o for o in obs if o.get("fixture_id") != exclude_fixture]
    for _ in range(ITERATIONS):
        grad = [0.0] * len(teams)
        for o in rows:
            i, j = idx[o["team_a"]], idx[o["team_b"]]
            x = s[i] - s[j]
            p = 1.0 / (1.0 + math.exp(-x))
            # d/ds_i of log-lik ~ (y - p); weights = 1 for each market observation
            g = (o["p_a"] - p) * o.get("weight", 1.0)
            grad[i] += g
            grad[j] -= g
        for k in range(len(teams)):
            s[k] += LEARNING_RATE * (grad[k] / max(1, len(rows)) * 10 - REGULARISATION * s[k])
    return teams, idx, s


def predict(s, idx, a, b):
    if a not in idx or b not in idx:
        return None
    return 1.0 / (1.0 + math.exp(-(s[idx[a]] - s[idx[b]])))


def main() -> int:
    matched = load("matched_quotes.json")["observations"]   # produced by build_board.py
    board = load("board.json")
    obs = []
    for m in matched:
        obs.append({"team_a": m["team_a_norm"], "team_b": m["team_b_norm"], "p_a": m["p_a"],
                    "source": m["source_key"], "fixture_id": m.get("fixture_id"),
                    "weight": m.get("weight", 1.0)})

    teams, idx, s = fit(obs)

    # ---- leave-one-out cross-validation on the priced pick'em fixtures
    priced = [r for r in board["rows"] if r["n_sources"]]
    cv = []
    for r in priced:
        a, b = r["team_a_norm"], r["team_b_norm"]
        if a not in idx or b not in idx:
            continue
        _, _, s_lo = fit(obs, exclude_fixture=r["fixture_id"])
        p = predict(s_lo, idx, a, b)
        if p is None:
            continue
        cv.append({"fixture_id": r["fixture_id"], "match": f"{r['team_a']} vs {r['team_b']}",
                   "market_p": r["p_a"], "model_p": round(p, 4),
                   "abs_error": round(abs(p - r["p_a"]), 4)})
    mae = round(sum(c["abs_error"] for c in cv) / len(cv), 4) if cv else None
    brier = round(sum((c["model_p"] - c["market_p"]) ** 2 for c in cv) / len(cv), 4) if cv else None

    # ---- originated probabilities for fixtures without any external quote
    rows = []
    for r in board["rows"]:
        if r["n_sources"]:
            continue
        a, b = r["team_a_norm"], r["team_b_norm"]
        p = predict(s, idx, a, b)
        if p is None:
            rows.append({"fixture_id": r["fixture_id"], "match": f"{r['team_a']} vs {r['team_b']}",
                         "originated_p_a": None, "basis": "not in the priced market graph",
                         "team_a_observations": 0, "team_b_observations": 0})
            continue
        na = sum(1 for o in obs if a in (o["team_a"], o["team_b"]))
        nb = sum(1 for o in obs if b in (o["team_a"], o["team_b"]))
        rows.append({
            "fixture_id": r["fixture_id"], "match": f"{r['team_a']} vs {r['team_b']}",
            "originated_p_a": round(p, 4),
            "basis": "Bradley-Terry fit to external market prices (see methodology)",
            "team_a_strength": round(s[idx[a]], 4), "team_b_strength": round(s[idx[b]], 4),
            "team_a_observations": na, "team_b_observations": nb,
            "sources_behind_team_a": sorted({o["source"] for o in obs if a in (o["team_a"], o["team_b"])}),
            "sources_behind_team_b": sorted({o["source"] for o in obs if b in (o["team_a"], o["team_b"])}),
        })

    out = {
        "generated_at_utc": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": ("Bradley-Terry / logistic strength model fitted to no-vig probabilities of "
                   "external market quotes (Pinnacle, Bovada, Kalshi) across every priced CS2 "
                   "match we can see; predictions only for teams connected to that market graph"),
        "graph": {"observations": len(obs),
                  "teams": len(teams),
                  "pickem_fixtures_with_model_input": sum(1 for r in board["rows"] if r["team_a_norm"] in idx and r["team_b_norm"] in idx)},
        "cross_validation": {"held_out_fixtures": len(cv), "mean_absolute_error": mae,
                             "brier": brier, "rows": cv},
        "originated": rows,
        "strengths": [{"team": t, "strength": round(s[idx[t]], 4),
                       "market_observations": sum(1 for o in obs if t in (o["team_a"], o["team_b"]))}
                      for t in teams],
    }
    with open(os.path.join(EV, "originated.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(json.dumps({"graph": out["graph"], "cv": {k: v for k, v in out["cross_validation"].items() if k != "rows"}},
                     indent=1))
    print("originated rows:", sum(1 for r in rows if r["originated_p_a"] is not None),
          "of", len(rows), "unpriced fixtures")
    print("still unverified (not in market graph):",
          sum(1 for r in rows if r["originated_p_a"] is None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
