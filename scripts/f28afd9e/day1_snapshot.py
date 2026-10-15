#!/usr/bin/env python3
"""Freeze the day-1 (14-15 Oct 2026) review: pre-lock line, pre-lock crowd ownership, result.

Inputs, all already committed by the repository's own collectors (provenance kept per row):
  * data/fe803b80/board.json `history`  - the last pick + probability published BEFORE kick-off
    (built from bookmaker/exchange prices; basis recorded) and the settled winner;
  * data/fe803b80/board.json `closed`   - HotSpawn points and settlement status per fixture;
  * git history of data/live/board.json - the last HotSpawn crowd split captured BEFORE the pick
    lock (ownership only; never a probability input). The commit hash is stored per row.

Run once with full git history available (`git fetch --unshallow`). Output:
data/f28afd9e/day1_review.json. Re-running reproduces the same file from the same commits.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import strategy  # noqa: E402

WINDOW = ("2026-10-14T00:00:00Z", "2026-10-15T09:00:00Z")
OUT = ROOT / "data" / "f28afd9e" / "day1_review.json"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def main(ref="origin/main"):
    board = json.loads((ROOT / "data/fe803b80/board.json").read_text(encoding="utf-8"))
    context = json.loads((ROOT / "data/f28afd9e/context.json").read_text(encoding="utf-8"))["teams"]
    closed = {r["fixture_id"]: r for r in board["closed"]}
    last = {}
    for h in board["history"]:
        if WINDOW[0] <= h["start_utc"] < WINDOW[1] and h["published_utc"] < h["start_utc"]:
            k = h["fixture_id"]
            if k not in last or h["published_utc"] > last[k]["published_utc"]:
                last[k] = h
    crowd = {}
    commits = git("log", "--format=%H", "--since=2026-10-13T12:00", "--until=2026-10-15T09:00",
                  ref, "--", "data/live/board.json").split()
    for sha in reversed(commits):                       # oldest -> newest, keep latest pre-lock
        try:
            live = json.loads(git("show", f"{sha}:data/live/board.json"))
        except Exception:
            continue
        gen = live.get("generated_at_utc")
        for r in live.get("rows", []):
            fid = str(r["fixture_id"])
            c = r.get("hotspawn_pick_pct_reference_only") or {}
            if fid in last and gen and gen < r["lock_time_utc"] and c.get("team_a") is not None \
                    and r.get("listed_in_lobby"):
                crowd[fid] = {"captured_utc": gen, "commit": sha, "pct_a": c["team_a"], "pct_b": c["team_b"],
                              "team_a": r["team_a"], "team_b": r["team_b"]}
    rows = []
    for fid, h in sorted(last.items(), key=lambda kv: (kv[1]["start_utc"], kv[0])):
        c = closed.get(fid, {})
        cr = crowd.get(fid)
        prob_a = h["pick_probability"] if h["pick"] == h["team_a"] else 1 - h["pick_probability"]
        own = strategy.ownership(cr["pct_a"], cr["pct_b"]) if cr else None
        s = strategy.evaluate(h["team_a"], h["team_b"], prob_a, own, c.get("points"), context,
                              h["start_utc"])
        winner = h.get("winner") if h.get("settled") else None
        rows.append({
            "fixture_id": fid, "start_utc": h["start_utc"], "competition": c.get("competition"),
            "tier": c.get("tier"), "points": c.get("points"),
            "team_a": h["team_a"], "team_b": h["team_b"],
            "prelock_prob_a": round(prob_a, 4), "prelock_basis": h["basis"],
            "prelock_published_utc": h["published_utc"],
            "crowd": cr, "winner": winner, "settled": h.get("settled"),
            "hotspawn_url": c.get("hotspawn_url") or "https://play.hotspawn.com/lobby",
            "strategy": s,
        })
    strategy.apply_daily_cap(rows)
    for r in rows:
        s = r["strategy"]
        r["safe_correct"] = None if not r["winner"] else (s["safe_pick"] == r["winner"])
        r["leaderboard_correct"] = None if not r["winner"] else (s["leaderboard_pick"] == r["winner"])
        if r["winner"] and r["crowd"]:
            own = strategy.ownership(r["crowd"]["pct_a"], r["crowd"]["pct_b"])
            r["crowd_share_on_winner"] = round(own[0] if r["winner"] == r["team_a"] else own[1], 4)
    settled = [r for r in rows if r["winner"]]

    def pts(r, key):
        return float(r["points"] or 0) if r[key] else 0.0
    summary = {
        "fixtures": len(rows), "settled": len(settled),
        "safe_correct": sum(1 for r in settled if r["safe_correct"]),
        "leaderboard_correct": sum(1 for r in settled if r["leaderboard_correct"]),
        "safe_points": sum(pts(r, "safe_correct") for r in settled),
        "leaderboard_points": sum(pts(r, "leaderboard_correct") for r in settled),
        "upsets_vs_market": [r["fixture_id"] for r in settled if not r["safe_correct"]],
        "contrarian_rows": [r["fixture_id"] for r in rows
                            if r["strategy"]["leaderboard_pick"] != r["strategy"]["safe_pick"]],
    }
    doc = {"session": "f28afd9e", "window_utc": WINDOW,
           "sources": {
               "lines_and_results": "data/fe803b80/board.json (history: last pre-kick-off publication; "
                                    "closed: HotSpawn settlement + points)",
               "crowd_ownership": "git history of data/live/board.json (commit per row; HotSpawn crowd "
                                  "split captured before the pick lock; ownership only)",
               "official_results": "https://www.hltv.org/results?event=8932",
               "hotspawn_lobby": "https://play.hotspawn.com/lobby"},
           "summary": summary, "rows": rows}
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(*(sys.argv[1:2]))
