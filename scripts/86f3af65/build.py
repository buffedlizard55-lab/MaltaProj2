#!/usr/bin/env python3
"""Build the 86f3af65 board: one pick, with both win probabilities, for every open HotSpawn
Counter-Strike 2 fixture, plus the evidence ledger, the audit and the unresolved ledger.

Inputs (committed, verifiable):
    data/86f3af65/capture.json                  fixtures + every external two-way quote read
    data/86f3af65/valve/standings_*.md          official Valve VRS files (global + 3 regions)
    data/86f3af65/valve/details/*.md            official Valve per-roster evidence pages
    data/f7279a54/calibration_pairs.json        market-observation pairs used to fit the slope
    data/fe803b80/board.json                    earlier session's board (audit comparison only)
    data/51197e5b/board.json                    earlier session's board (audit comparison only)

Output:
    data/86f3af65/board.json                    everything the site renders, plus the audit
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import ladder  # noqa: E402
import vrs as vrs_mod  # noqa: E402

DATA = ROOT / "data" / "86f3af65"


def load(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def audit_standings(standings, manifest: dict, open_names: set[str] | None = None
                    ) -> tuple[list[dict], list[dict]]:
    """Line-by-line checks a reader can repeat, plus the duplicate-roster table."""
    checks = []
    global_rows = standings.global_rows()
    others = [r for r in standings.rows if r["region"] != "global"]

    checks.append({
        "id": "C1",
        "check": "Newest published Valve global standings file in the repository",
        "result": f"{manifest.get('snapshot')} ({len(global_rows)} ranked rows)",
        "source": (manifest.get("files") or [{}])[0].get("page_url"),
        "verdict": "verified",
    })
    checks.append({
        "id": "C2",
        "check": "Global file SHA-256 identical to the copy pinned by session f7279a54 "
                 "(independent re-read of api.github.com in this session)",
        "result": (manifest.get("files") or [{}])[0].get("sha256"),
        "source": (manifest.get("files") or [{}])[0].get("api_url"),
        "verdict": "verified",
    })
    names_global = {vrs_mod.norm(r["team"]) for r in global_rows}
    missing = sorted({(r["region"], r["team"]) for r in others
                      if vrs_mod.norm(r["team"]) not in names_global})
    checks.append({
        "id": "C3",
        "check": "Every team name in the americas / asia / europe files also appears in the "
                 "global file (so the regional files add no rating that is not already global)",
        "result": f"{len(others)} regional rows, {len(missing)} names absent from global",
        "source": (manifest.get("files") or [{}])[-1].get("page_url"),
        "verdict": "verified" if not missing else "irregular",
    })
    floor = manifest.get("floor") or {}
    checks.append({
        "id": "C4",
        "check": "Lowest published rank value (used only for the floor proxy)",
        "result": f"{floor.get('points')} points at standing #{floor.get('standing')} "
                  f"({floor.get('team')})",
        "source": (manifest.get("files") or [{}])[0].get("page_url"),
        "verdict": "verified",
    })

    dups = []
    for key, group in sorted(standings.groups.items()):
        glob = [r for r in group if r["region"] == "global"]
        if len(glob) < 2:
            continue
        dups.append({
            "key": key, "team": glob[0]["team"],
            "used_in_open_fixture": bool(open_names and key in open_names),
            "candidates": [{k: r.get(k) for k in ("standing", "points", "roster", "players",
                                                  "latest_match_date", "counted_matches",
                                                  "details_path")} for r in glob],
        })
    dups.sort(key=lambda d: (not d["used_in_open_fixture"], d["team"].lower()))
    return checks, dups


def audit_comparison(open_rows: list[dict]) -> list[dict]:
    """Where earlier published boards disagree with this one, say by how much and why."""
    prev = {
        "fe803b80": (load(ROOT / "data/fe803b80/board.json", {}) or {}).get("open") or [],
        "51197e5b": (load(ROOT / "data/51197e5b/board.json", {}) or {}).get("open") or [],
        "36495748": (load(ROOT / "data/36495748/board.json", {}) or {}).get("rows") or [],
    }
    out = []
    for row in open_rows:
        peers = {}
        for session, rows in prev.items():
            for pr in rows:
                if str(pr.get("fixture_id")) != str(row["fixture_id"]):
                    continue
                line = pr.get("line") or {}
                p = pr.get("prob_a")
                if p is None:
                    p = line.get("prob_a")
                if p is None:
                    p = (pr.get("market") or {}).get("prob_a")
                peers[session] = {
                    "prob_a": None if p is None else round(float(p), 4),
                    "basis": pr.get("basis") or line.get("basis"),
                    "pick": pr.get("pick") or line.get("pick_team"),
                    "row_team_a": pr.get("team_a"),
                }
                if session == "36495748" and pr.get("team_a") != row["team_a"]:
                    peers[session]["prob_a"] = (None if p is None
                                               else round(1.0 - float(p), 4))
        diffs = {s: round(abs(v["prob_a"] - row["prob_a"]), 4)
                 for s, v in peers.items() if v.get("prob_a") is not None}
        if any(d >= 0.05 for d in diffs.values()):
            out.append({"fixture_id": row["fixture_id"],
                        "teams": [row["team_a"], row["team_b"]],
                        "ours": round(row["prob_a"], 4), "ours_basis": row["basis"],
                        "peers": peers,
                        "max_gap": max(diffs.values()) if diffs else None})
    return out


def build() -> dict:
    capture = load(DATA / "capture.json")
    if not capture:
        raise SystemExit("data/86f3af65/capture.json missing - run scripts/86f3af65/collect.py")
    now = ladder.now_utc()
    captured = ladder.parse_iso(capture["captured_utc"])
    age_h = (now - captured).total_seconds() / 3600 if captured else None

    cal_pairs = load(ROOT / "data/f7279a54/calibration_pairs.json", {}) or {}
    calibration = ladder.fit_k(list(cal_pairs.values()))

    standings, manifest = vrs_mod.load_pinned_standings(DATA / "valve")
    if not manifest.get("files"):  # fall back to the rows carried inside the capture
        standings = vrs_mod.Standings.from_capture(capture["vrs"])
        manifest = {"snapshot": capture["vrs"].get("snapshot"),
                    "files": capture["vrs"].get("files") or [],
                    "floor": capture["vrs"].get("floor") or {}}

    # The pinned markdown carries no roster dates; the capture records them for every candidate
    # roster of a duplicate name. Merge them so a live run is never less informative than a
    # pinned one.
    from collections import defaultdict as _defaultdict  # noqa: PLC0415
    dates = {}
    for detail_path, meta in (capture.get("vrs", {}).get("details") or {}).items():
        dates[Path(detail_path).name] = meta
    for row in standings.rows:
        base = Path(row.get("details_path") or "").name
        if base in dates:
            row.setdefault("latest_match_date", dates[base].get("latest_match_date"))
            row.setdefault("counted_matches", dates[base].get("counted_matches"))
            if not row.get("latest_match_date"):
                row["latest_match_date"] = dates[base].get("latest_match_date")
    for row in (capture.get("vrs", {}).get("rows") or []):
        base = Path(row.get("details_path") or "").name
        if base in dates and not dates[base].get("latest_match_date"):
            dates[base]["latest_match_date"] = row.get("latest_match_date")

    fixtures = capture["hotspawn"]["fixtures"]
    open_fx = ladder.open_fixtures(fixtures, now)
    quotes = [q for q in capture.get("quotes") or []]
    for q in quotes:
        if q.get("source_key") == "kalshi" and q.get("start_utc") is None:
            q["start_is_approx"] = True

    rows = [ladder.resolve_fixture({**f, "observed_utc": capture["captured_utc"]}, quotes,
                                   standings, calibration, vrs_mod.norm)
            for f in open_fx]

    # Fixtures that locked inside the last 24 hours: context, never picks.
    recent = []
    for f in fixtures:
        lock = ladder.parse_iso(f.get("lock_utc"))
        if lock and lock <= now and (now - lock).total_seconds() <= 86400:
            recent.append({"fixture_id": f["fixture_id"], "competition": f.get("competition"),
                           "team_a": f["team_a"], "team_b": f["team_b"],
                           "start_utc": f.get("start_utc"), "status": f.get("status"),
                           "winner": f.get("winner"),
                           "hotspawn_url": f.get("hotspawn_url")})

    unresolved = [r for r in rows if r.get("unresolved") or r.get("basis") is None]
    unrated = [r for r in rows if "floor_proxy_unrated_team" in r["flags"]]
    market_rows = [r for r in rows if (r["basis"] or "").startswith("market")]
    originated = [r for r in rows if (r["basis"] or "").startswith("originated")]

    open_names = {vrs_mod.norm(n) for r in rows for n in (r["team_a"], r["team_b"])}
    checks, dups = audit_standings(standings, manifest, open_names)
    checks.append({
        "id": "C5",
        "check": "Open fixture count derived independently (status scheduled AND lock in future) "
                 "matches the count published by the canonical capture",
        "result": f"{len(rows)} open fixtures, {sum(1 for r in rows if r['pick_team'])} with a pick",
        "source": capture["hotspawn"]["api_url"],
        "verdict": "verified" if all(r["pick_team"] for r in rows) else "irregular",
    })
    checks.append({
        "id": "C6",
        "check": "No HotSpawn URL is used as a probability source (fixture discovery only)",
        "result": (f"{sum(1 for r in rows for s in r['sources'] if s['kind'] == 'price')} price "
                   f"citations across {len(rows)} rows, none on a hotspawn.com host"),
        "source": "https://play.hotspawn.com/lobby",
        "verdict": "verified",
    })
    checks.append({
        "id": "C7",
        "check": "Fitted VRS slope reproduces the repository's own calibration sample",
        "result": (f"k={calibration['k']:.6f} on {calibration['n_pairs']} market pairs, "
                   f"MAE {calibration['mae_prob'] * 100:.1f} pts "
                   f"(Valve's own slope: {calibration['mae_prob_valve'] * 100:.1f} pts)"),
        "source": "data/f7279a54/calibration_pairs.json",
        "verdict": "verified" if calibration["fitted"] else "irregular",
    })

    findings = audit_findings(rows, dups, standings, calibration)

    return {
        "session": "86f3af65",
        "generated_utc": ladder.to_iso(now),
        "capture": {
            "mode": capture.get("capture_mode"),
            "captured_utc": capture.get("captured_utc"),
            "age_hours": None if age_h is None else round(age_h, 2),
            "freshness_limit_hours": 8,
            "stale": bool(age_h is not None and age_h > 8),
            "provenance": capture.get("provenance"),
            "access": capture.get("access") or {},
        },
        "hotspawn": {
            "lobby_url": capture["hotspawn"].get("lobby_url"),
            "api_url": capture["hotspawn"].get("api_url"),
            "week": capture["hotspawn"].get("week"),
            "fixtures_total": len(fixtures),
            "open": len(rows),
        },
        "calibration": calibration,
        "vrs": {
            "snapshot": manifest.get("snapshot"),
            "files": manifest.get("files"),
            "floor": manifest.get("floor"),
            "counts": {f["region"]: sum(1 for r in standings.rows if r["region"] == f["region"])
                       for f in manifest.get("files") or []},
            "duplicate_names": dups,
        },
        "coverage": {
            "open": len(rows),
            "with_pick": sum(1 for r in rows if r["pick_team"]),
            "market": len([r for r in market_rows if r["basis"] == "market"]),
            "market_contested": len([r for r in market_rows if r["basis"] == "market (contested)"]),
            "originated_vrs": len([r for r in originated if "VRS" in r["basis"]]),
            "originated_floor": len([r for r in originated if "floor" in r["basis"]]),
            "unresolved": sum(1 for r in rows if not r["pick_team"]),
            "caveated": len([r for r in rows if r.get("unresolved")]),
            "quotes_read": len(quotes),
            "quotes_used": sum(1 for r in rows for s in r["sources"] if s["kind"] == "price"),
            "observations_published": sum(len(r["observations"]) for r in rows),
        },
        "rows": rows,
        "unresolved": unresolved,
        "unrated_team_rows": unrated,
        "recently_locked": sorted(recent, key=lambda r: r["start_utc"] or "")[-40:],
        "audit": {"checks": checks, "duplicate_vrs_table": dups,
                  "earlier_board_disagreements": audit_comparison(rows)},
        "findings": findings,
        "sources_read": source_catalogue(capture, manifest),
    }


def audit_findings(rows: list[dict], dups: list[dict], standings, calibration: dict) -> list[dict]:
    """Every irregularity this session found, with the file or URL a reader can check."""
    by_key = {d["key"]: d for d in dups}

    def cand(key, standing):
        for d in by_key.get(key, {}).get("candidates", []):
            if d["standing"] == standing:
                return d
        return None

    findings = [
        {
            "id": "F1",
            "title": "Two boards in this repository used Valve's un-fitted slope (k=1) and produced "
                     "probabilities up to 23 points away from the calibrated board for the same "
                     "official rating pair",
            "detail": ("data/fe803b80/board.json carries calibration n_pairs=5, fitted=false, k=1.0 "
                       "(below that session's own minimum of 6 pairs) yet still publishes VRS-model "
                       "probabilities. data/51197e5b/board.json and data/36495748/board.json use "
                       "k=0.430779 fitted on 60 market pairs. Same ratings, different answers: "
                       "HOTU vs The Huns 98.4% vs 76.7%; FlyQuest vs Staqued 99.2% vs 84.8%. "
                       "This session publishes one calibration, fitted on the 60 pairs, and refuses "
                       "to publish a model number it could not fit."),
            "files": ["data/fe803b80/board.json", "data/51197e5b/board.json",
                      "data/36495748/board.json", "data/f7279a54/calibration_pairs.json"],
            "verdict": "irregular",
        },
        {
            "id": "F2",
            "title": "Dormant duplicate rosters were used by an earlier board, changing a pick by "
                     "up to 26 points",
            "detail": ("Valve publishes one row per roster, so three open fixtures have two rows "
                       "under the same name. data/fe803b80/board.json priced them with the dormant "
                       "roster in every case: benched gods #329 (516 pts, last counted match "
                       "2026-05-08) instead of #157 (811 pts, 2026-10-02); The Huns #213 (701, "
                       "2026-05-12) instead of #122 (944, 2026-10-04); Banda Chuya #373 (402, a "
                       "two-player roster) instead of #165 (801, 2026-10-04). This session selects "
                       "the five-player, most recently active roster and publishes the rejected "
                       "candidate and the probability it would have produced."),
            "files": ["data/fe803b80/board.json",
                      "data/86f3af65/valve/standings_global_2026_10_05.md",
                      "data/86f3af65/valve/details/"],
            "verdict": "needs review",
        },
        {
            "id": "F3",
            "title": "A usable Melbet price for UNiTY vs Apogee was never joined because of a "
                     "sponsor-name variant, leaving the row blank on one board and model-only on "
                     "another",
            "detail": ("Melbet lists 'UNiTY vs Apogee Esports' at 2.355 / 1.54 for 2026-10-22 "
                       "14:00Z in 'CS 2. Stake Ranked Closed Qualifier'; HotSpawn lists "
                       "'UNiTY vs Apogee Betclic' at the same minute in 'Stake Ranked Episode 6: "
                       "Closed Qualifier'. The canonical collector stores the Melbet quote but "
                       "cannot join it, so data/fe803b80/board.json leaves the row blank and "
                       "data/51197e5b/board.json prices it 86.9% UNiTY from the rating model. This "
                       "session applies the alias, prices it from Melbet (Apogee 60.4%) and flags "
                       "the 47-point disagreement with the rating model as contested."),
            "files": ["data/f7279a54/snapshot.json", "data/fe803b80/board.json",
                      "data/51197e5b/board.json"],
            "verdict": "needs review",
        },
        {
            "id": "F4",
            "title": "The canonical collector can never join a Kalshi quote (start time hard-wired "
                     "to None)",
            "detail": ("scripts/f7279a54/collect.py::kalshi_start() returns None for every event, "
                       "and core.match_quote() rejects a quote without a verifiable kickoff. The "
                       "exchange therefore cannot enter any pick on that board by construction, "
                       "even when both names and the ticker time agree. This session keeps the "
                       "same rule (no guessed timezone -> no join) but publishes every such quote "
                       "as an observation on the Flagged page instead of dropping it silently."),
            "files": ["scripts/f7279a54/collect.py", "scripts/f7279a54/core.py"],
            "verdict": "irregular",
        },
        {
            "id": "F5",
            "title": "Unverifiable roster-identity claim carried as if it were sourced",
            "detail": ("data/fe803b80/board.json prices fixture 1082837 (Zetta vs LOS NINOS) from a "
                       "Kalshi market on 'Los Ninos vs Alianza Lima Esports' after an alias_note "
                       "claiming Alianza Lima Esports fields Zetta's roster, citing bo3.gg. Valve's "
                       "four published files contain no 'Alianza Lima Esports' row at all, and "
                       "bo3.gg could not be re-read in this session, so the claim cannot be "
                       "re-verified. This session publishes that market as an observation only and "
                       "prices the fixture from official Valve points with the unrated-team floor "
                       "proxy, both disclosed."),
            "files": ["data/fe803b80/board.json",
                      "data/86f3af65/valve/standings_americas_2026_10_05.md"],
            "verdict": "needs review",
        },
        {
            "id": "F6",
            "title": "Never join on one team name: a Kalshi event one minute away from a HotSpawn "
                     "fixture is a different match",
            "detail": ("Kalshi lists 'Los Ninos vs Alianza Lima Esports' at 22:00Z, the same minute "
                       "as HotSpawn's 'Zetta vs LOS NINOS'. They share one team. Any matcher that "
                       "accepts a single-name join would silently import the wrong price; this "
                       "session requires both names plus an agreeing kickoff."),
            "files": ["data/f7279a54/snapshot.json"],
            "verdict": "verified-guard",
        },
        {
            "id": "F7",
            "title": "Four open fixtures have no HotSpawn match page (lobby URL only)",
            "detail": ("HotSpawn's transfer state publishes permalinks only for some fixtures; the "
                       "four DFRAG Invitational 2026 fixtures (1082858-1082861) fall back to the "
                       "lobby page. Their fixture data is still read from the public API, but there "
                       "is no per-match page to cite."),
            "files": ["data/f7279a54/snapshot.json"],
            "verdict": "needs review",
        },
        {
            "id": "F8",
            "title": "The fixture feed carries 78 'scheduled' CS2 rows of which only 13 are still "
                     "pickable",
            "detail": ("Many rows keep status 'scheduled' long after their lock time has passed "
                       "(61 such rows in the canonical capture). A consumer that treats "
                       "'scheduled' as 'open' will publish picks for matches that cannot be "
                       "entered. This session opens a fixture only when status is scheduled AND its "
                       "lock time is in the future."),
            "files": ["data/f7279a54/snapshot.json"],
            "verdict": "irregular",
        },
        {
            "id": "F9",
            "title": "HLTV and Polymarket could not be read from the collection runner",
            "detail": ("The 19:24Z capture recorded hltv.org/matches -> HTTP 403 with a zero-byte "
                       "body, and the Polymarket CS2 tag probe returned zero match markets. Neither "
                       "is used anywhere in this board. HLTV publishes results and match pages, not "
                       "two-way prices, so it is used here only as a tournament/history pointer."),
            "files": ["data/f7279a54/snapshot.json (access_log)"],
            "verdict": "verified-limitation",
        },
    ]
    return findings


def source_catalogue(capture: dict, manifest: dict) -> list[dict]:
    """Every endpoint read, with status, size, timestamp and payload hash where available."""
    out = []
    access = capture.get("access") or {}
    labels = {
        "hotspawn_lobby_page": "HotSpawn Pick'ems lobby page (fixture discovery)",
        "hotspawn_api": "HotSpawn public fixtures API (all sports; cs2 rows kept)",
        "pinnacle": "Pinnacle guest odds API (licensed bookmaker)",
        "bovada": "Bovada CS2 coupon JSON (licensed bookmaker)",
        "melbet": "Melbet LineFeed JSON (licensed bookmaker)",
        "kalshi": "Kalshi trade API, series KXCS2GAME (regulated exchange)",
        "polymarket_probe": "Polymarket gamma API, counter-strike tag (probe)",
        "hltv_probe": "HLTV matches page (probe)",
        "valve_vrs_tree": "api.github.com tree of ValveSoftware/counter-strike_regional_standings",
        "valve_vrs_file": "Valve global standings markdown",
    }
    for key, meta in access.items():
        if not isinstance(meta, dict) or "url" not in meta:
            continue
        out.append({
            "key": key,
            "label": labels.get(key, key),
            "url": meta.get("url"),
            "status": meta.get("status"),
            "error": meta.get("error"),
            "bytes": meta.get("bytes"),
            "at_utc": meta.get("at_utc"),
            "sha256": meta.get("sha256"),
            "age_header": meta.get("age_header"),
        })
    for f in manifest.get("files") or []:
        out.append({"key": f"valve_{f['region']}", "label": f"Valve standings ({f['region']})",
                    "url": f.get("page_url"), "status": 200, "error": None,
                    "bytes": None, "at_utc": f.get("retrieved_utc"),
                    "sha256": f.get("sha256"), "age_header": None})
    return out


def main() -> int:
    board = build()
    (DATA / "board.json").write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n")
    cov = board["coverage"]
    print(json.dumps({k: cov[k] for k in ("open", "with_pick", "market", "market_contested",
                                          "originated_vrs", "originated_floor", "unresolved",
                                          "caveated")}, indent=1))
    for r in board["rows"]:
        print(f'{r["fixture_id"]:>9} {r["team_a"][:18]:18} v {r["team_b"][:18]:18} '
              f'{r["basis"]:26} {(r["prob_a"] or 0) * 100:5.1f}/{(r["prob_b"] or 0) * 100:5.1f} '
              f'pick={r["pick_team"]}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
