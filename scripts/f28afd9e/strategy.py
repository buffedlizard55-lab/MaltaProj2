"""Leaderboard (contrarian-but-not-stupid) pick rules for the HotSpawn CS2 pick'em.

Two picks are published for every match:

* SAFE pick  - the side with the higher win probability from our line (bookmaker/exchange
  prices first, originated rating model only where no price exists). Maximises expected points.
* LEADERBOARD pick - identical to the safe pick unless one of three explicit rules fires.
  The rules only ever take an underdog that the betting market itself rates as live, and only
  when the HotSpawn crowd has piled onto the favourite. HotSpawn crowd numbers are used here as
  OWNERSHIP (how many rivals share a pick), never as a probability.

Why: in expectation the favourite always scores more points, so a pure-chalk card can only keep
pace with the ~90% of players who pick the same way. Climbing a top-10-prize leaderboard needs
points the field does not get. The rules below buy that separation where it is cheapest in
expected points (near coin flips) or where the payoff on a live underdog is largest.

Rules (thresholds are declared policy, not source facts):
  R1 coinflip fade   gap between the two win probabilities <= 12 points and the underdog is
                     owned by <= 40% of the crowd -> take the less-owned underdog.
  R2 upset swing     underdog win probability >= 35%, owned by <= 20%, and
                     leverage (win prob / ownership) >= 2.0.
  R3 context swing   underdog win probability >= 25%, owned by <= 10%, and at least one verified
                     context factor (favourite roster change/onboarding within 120 days, stand-in,
                     rest disadvantage, or an underdog head-to-head win within 12 months).
At most MAX_SWINGS_PER_DAY R2/R3 swings per UTC day, ranked by leverage x points; R1 fades are
not capped because they cost almost nothing in expected points.
"""
from __future__ import annotations

COINFLIP_MAX_GAP = 0.12
COINFLIP_MAX_OWN = 0.40
SWING_MIN_P = 0.35
SWING_MAX_OWN = 0.20
SWING_MIN_LEVERAGE = 2.0
CONTEXT_MIN_P = 0.25
CONTEXT_MAX_OWN = 0.10
MAX_SWINGS_PER_DAY = 3
CONTEXT_TYPES = ("roster_change", "stand_in", "rest_disadvantage", "h2h_underdog_win")


def ownership(pct_a, pct_b):
    """Normalise HotSpawn crowd percentages (they can sum to 99-101) to shares. None if absent."""
    if pct_a is None or pct_b is None:
        return None
    total = float(pct_a) + float(pct_b)
    if total <= 0:
        return None
    return float(pct_a) / total, float(pct_b) / total


def context_factors(team_fav, team_dog, context, fixture_date=None):
    """Verified context entries that weaken the favourite or back the underdog."""
    out = []
    for entry in (context.get(team_fav) or []):
        if entry.get("type") in ("roster_change", "stand_in", "rest_disadvantage") and not entry.get("secondary"):
            out.append({"team": team_fav, **entry})
    for entry in (context.get(team_dog) or []):
        if entry.get("type") == "h2h_underdog_win" and entry.get("against") == team_fav and not entry.get("secondary"):
            out.append({"team": team_dog, **entry})
    if fixture_date:
        kept = []
        for e in out:
            d = str(e.get("date") or "")
            if e["type"] == "roster_change" and len(d) == 10:
                from datetime import date
                try:
                    age = (date.fromisoformat(fixture_date[:10]) - date.fromisoformat(d)).days
                except ValueError:
                    age = None
                if age is None or age > 120:
                    continue
                e = {**e, "age_days": age}
            kept.append(e)
        out = kept
    return out


def evaluate(team_a, team_b, prob_a, own=None, points=None, context=None, fixture_date=None):
    """Return the safe pick and the candidate leaderboard pick for one match.

    prob_a: our win probability for team_a (None -> no pick possible).
    own: (share_a, share_b) crowd ownership or None.
    """
    res = {"safe_pick": None, "safe_prob": None, "leaderboard_pick": None, "leaderboard_prob": None,
           "rule": None, "leverage": None, "ep_cost": None, "context": [], "notes": []}
    if prob_a is None:
        res["rule"] = "no_probability"
        return res
    prob_b = 1.0 - prob_a
    fav, dog = (team_a, team_b) if prob_a >= prob_b else (team_b, team_a)
    p_fav, p_dog = max(prob_a, prob_b), min(prob_a, prob_b)
    res.update(safe_pick=fav, safe_prob=p_fav, leaderboard_pick=fav, leaderboard_prob=p_fav, rule="chalk")
    if own is None:
        res["notes"].append("no crowd ownership available: leaderboard pick = safe pick")
        return res
    own_fav, own_dog = (own[0], own[1]) if fav == team_a else (own[1], own[0])
    res["own_fav"], res["own_dog"] = own_fav, own_dog
    leverage = (p_dog / own_dog) if own_dog > 0 else float("inf")
    res["leverage"] = leverage
    pts = float(points) if points else 1.0
    res["ep_cost"] = (p_fav - p_dog) * pts
    ctx = context_factors(fav, dog, context or {}, fixture_date)
    res["context"] = ctx
    if own_dog >= own_fav:
        res["notes"].append("the market favourite is already the less-owned side: safe pick is also contrarian")
        res["rule"] = "chalk_contrarian"
        return res
    if (p_fav - p_dog) <= COINFLIP_MAX_GAP and own_dog <= COINFLIP_MAX_OWN:
        res.update(leaderboard_pick=dog, leaderboard_prob=p_dog, rule="R1_coinflip_fade")
    elif p_dog >= SWING_MIN_P and own_dog <= SWING_MAX_OWN and leverage >= SWING_MIN_LEVERAGE:
        res.update(leaderboard_pick=dog, leaderboard_prob=p_dog, rule="R2_upset_swing")
    elif p_dog >= CONTEXT_MIN_P and own_dog <= CONTEXT_MAX_OWN and ctx:
        res.update(leaderboard_pick=dog, leaderboard_prob=p_dog, rule="R3_context_swing")
    return res


def apply_daily_cap(rows, key_day=lambda r: (r.get("start_utc") or "")[:10]):
    """Keep at most MAX_SWINGS_PER_DAY R2/R3 swings per UTC day (highest leverage x points)."""
    by_day = {}
    for r in rows:
        s = r.get("strategy") or {}
        if s.get("rule") in ("R2_upset_swing", "R3_context_swing"):
            by_day.setdefault(key_day(r), []).append(r)
    for day, items in by_day.items():
        items.sort(key=lambda r: -((r["strategy"].get("leverage") or 0) * float(r.get("points") or 1)))
        for r in items[MAX_SWINGS_PER_DAY:]:
            s = r["strategy"]
            s["notes"].append(f"{s['rule']} qualified but the daily cap of {MAX_SWINGS_PER_DAY} swings was reached")
            s.update(leaderboard_pick=s["safe_pick"], leaderboard_prob=s["safe_prob"], rule="chalk_capped")
    return rows
