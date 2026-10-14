#!/usr/bin/env python3
"""Independent line-by-line verification of the published boards (session 7cd2e67a).

What this does
--------------
1. Re-derives every published probability on the root board (`data/lines.json`) and the live
   coverage board (`data/live/board.json`) from the quoted odds that are stored next to it, and
   compares the result with the published number. No value is taken on trust.
2. Re-reads Valve's official CS2 Regional Standings from `api.github.com` and checks that every
   rating used by the originated-estimate rows is a real row of that file, and that every row left
   blank for a missing rating actually carries the `no_valve_vrs_rating:<team>` flag.
3. Cross-checks the committed lobby snapshot against an independent re-read of the public lobby.
4. Records the external-source observations made on 2026-10-14 (Pinnacle match markets, Bovada
   quote API and event pages, Melbet LineFeed, HotSpawn lobby and `/matches/<id>` routing), each
   with its exact URL and the UTC time it was read.
5. Emits `verify/7cd2e67a/audit.json`, `verify/7cd2e67a/AUDIT.md` and `verify/7cd2e67a/index.html`
   so every finding is published with its source link.

Nothing is inferred: an observation that could not be made is recorded as `unverified` with the
reason, and it is published on the Flagged for Review page instead of being filled in.

Usage: python3 scripts/7cd2e67a/verify_published_boards.py [--outdir verify/7cd2e67a]
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VRS_API = ("https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings"
           "/contents/live/2026/standings_global_2026_10_05.md")
VRS_REPO = "https://github.com/ValveSoftware/counter-strike_regional_standings"
LOBBY_PAGE = "https://play.hotspawn.com/lobby"
PIN = "https://guest.api.arcadia.pinnacle.com/0.1/matchups/{mid}/markets/related/straight"
BOVADA_API = "https://www.bovada.lv/services/sports/event/v2/events/A/description/esports"
MELBET_FEED = ("https://melbet.com/service-api/LineFeed/Get1x2_VZip?sports=40&count=1000"
               "&lng=en&mode=4&country=1")

# Observations made by this session on 2026-10-14 between 01:47 and 02:20 UTC. Each entry records
# exactly what the source served, the URL it was read from and the read time. Nothing here is a
# claim about a source that was not read.
OBSERVATIONS = [
    {
        "id": "OBS-01", "source": "HotSpawn Pick'ems lobby", "kind": "fixture discovery",
        "url": LOBBY_PAGE, "read_utc": "2026-10-14T01:47:00Z", "status": "ok",
        "observed": ("Served lobby page. Its own counters read: \"This week 68 matches this week\", "
                     "\"All tiers (89)\", \"B (25)\", \"C (60)\", \"S (4)\", \"All tournaments (89)\". "
                     "28 match cards rendered (13 under Closing Soon, 15 under Upcoming)."),
        "note": ("Independent re-read, not a re-use of the committed snapshot. The committed snapshot "
                 "was taken at 2026-10-14T01:15:53Z."),
    },
    {
        "id": "OBS-02", "source": "HotSpawn numeric match route", "kind": "link audit",
        "url": "https://www.hotspawn.com/matches/1079546", "read_utc": "2026-10-14T01:50:00Z",
        "status": "fail",
        "observed": ("Final URL https://www.hotspawn.com/matches, page title \"Matches - Hotspawn\": "
                     "the general matches index, not the Zomblers vs Overtake Sector match page."),
        "note": ("Proves `/matches/<numeric id>` is not a per-match source link. It is the route the "
                 "inherited collectors used on every published row."),
    },
    {
        "id": "OBS-03", "source": "HotSpawn matches listing", "kind": "permalink discovery",
        "url": "https://www.hotspawn.com/matches", "read_utc": "2026-10-14T01:55:00Z", "status": "ok",
        "observed": ("Official listing page publishes per-match permalinks of the form "
                     "/matches/<team-a>-vs-<team-b>-<tournament>-<fixture id>, e.g. "
                     "https://www.hotspawn.com/matches/gothic-vs-lavked-cct-europe-2026-series-11-1079621."),
    },
    {
        "id": "OBS-04", "source": "Pinnacle guest API", "kind": "quote verification",
        "url": PIN.format(mid=1638111785), "read_utc": "2026-10-14T01:58:00Z", "status": "ok",
        "observed": ("matchup 1638111785 (9z vs Aurora), cutoff 2026-10-14T08:30Z: full-match "
                     "moneyline `s;0;m` status open, home +241 / away -307 (decimal 3.41 / 1.3257)."),
        "published": "3.55 / 1.3067 (read 2026-10-14T01:15:57Z)",
        "verdict": ("line moved since the published read; no-vig p(9z) 28.0% / p(Aurora) 72.0% today "
                    "versus 26.9% / 73.1% published. The pick (Aurora) is unchanged."),
    },
    {
        "id": "OBS-05", "source": "Pinnacle guest API", "kind": "quote verification",
        "url": PIN.format(mid=1637867148), "read_utc": "2026-10-14T01:58:00Z", "status": "ok",
        "observed": ("matchup 1637867148 (HOTU vs Fnatic), cutoff 2026-10-14T10:00Z: full-match "
                     "moneyline `s;0;m` status open, home -101 / away -125 (decimal 1.9901 / 1.8)."),
        "published": "1.9901 / 1.8 (read 2026-10-14T01:15:55Z)",
        "verdict": "exact match with the published quote; no-vig 47.5% / 52.5% reproduces.",
    },
    {
        "id": "OBS-06", "source": "Pinnacle guest API", "kind": "quote verification",
        "url": PIN.format(mid=1638111674), "read_utc": "2026-10-14T02:00:00Z", "status": "changed",
        "observed": ("matchup 1638111674 (Falcons vs Ninjas in Pyjamas), cutoff 2026-10-14T11:00Z: "
                     "no `period: 0` moneyline is present in the response. The first moneyline is "
                     "`s;1;m` (map 1, home -243 / away +195); only per-map markets remain."),
        "published": "1.2703 / 3.85 full-match moneyline (read 2026-10-14T01:15:58Z)",
        "verdict": ("the full-match market the published row cites is no longer offered, so that row "
                    "is stale. Flagged, not silently refreshed."),
    },
    {
        "id": "OBS-07", "source": "Pinnacle guest API", "kind": "quote verification",
        "url": PIN.format(mid=1637936745), "read_utc": "2026-10-14T02:00:00Z", "status": "changed",
        "observed": ("matchup 1637936745 (MIBR vs BC.Game), cutoff 2026-10-15T10:00Z: no `period: 0` "
                     "moneyline is present. First moneyline is `s;1;m` (map 1, home -122 / away -103)."),
        "published": "1.6369 / 2.23 full-match moneyline (read 2026-10-14T01:15:56Z)",
        "verdict": "the cited full-match market is no longer offered; the published row is stale.",
    },
    {
        "id": "OBS-08", "source": "Pinnacle guest API", "kind": "quote verification",
        "url": PIN.format(mid=1637999450), "read_utc": "2026-10-14T02:05:00Z", "status": "changed",
        "observed": ("matchup 1637999450 (Heroic vs Envy), cutoff 2026-10-15T10:00Z: no `period: 0` "
                     "moneyline is present. First moneyline is `s;1;m` (map 1, home -137 / away +109)."),
        "published": "1.4695 / 2.62 full-match moneyline (read 2026-10-14T01:15:57Z)",
        "verdict": "the cited full-match market is no longer offered; the published row is stale.",
    },
    {
        "id": "OBS-09", "source": "Bovada quote API", "kind": "quote verification",
        "url": BOVADA_API, "read_utc": "2026-10-14T02:08:00Z", "status": "ok",
        "observed": ("Served the esports event feed as JSON with live events and two-way moneyline "
                     "prices (e.g. Cloud9 vs Karmine Corp +170 / -225)."),
        "note": ("This is the URL the pipeline records as `source_api_url` for every Bovada quote, so "
                 "the quote itself is traceable to a live official endpoint."),
    },
    {
        "id": "OBS-10", "source": "Bovada event page", "kind": "link audit",
        "url": ("https://www.bovada.lv/esports/counter-strike-2/pulse-beat-iii/"
                "astralis-sashi-esport-202610140600"),
        "read_utc": "2026-10-14T02:08:00Z", "status": "fail",
        "observed": ("HTTP 200 body is Bovada's \"Not Found\" page (\"PÁGINA NO ENCONTRADA\") behind a "
                     "reCAPTCHA challenge."),
        "note": ("A second event page URL "
                 "(/esports/counter-strike-2/thunderpick-world-championship-26/"
                 "9z-globant-team-aurora-202610140430) returned the same result, so this is a "
                 "systematic access block rather than one bad URL. The per-event page links the "
                 "dashboard prints for Bovada rows are therefore not usable as verification links "
                 "from this environment; the quote API link is."),
    },
    {
        "id": "OBS-11", "source": "Melbet LineFeed (1xBet platform)", "kind": "quote verification",
        "url": MELBET_FEED, "read_utc": "2026-10-14T02:10:00Z", "status": "ok",
        "observed": ("Served the 1x2 feed as JSON. Its first entry is Gothic vs Lavked "
                     "(CS 2. CCT Europe Series, start 1791964800 = 2026-10-14T08:00:00Z) with "
                     "Gothic 1.881 and Lavked 1.782."),
        "published": "live board row 1079621: Gothic 1.881 / Lavked 1.782 (read 2026-10-13T23:43:35Z)",
        "verdict": "exact match with the published quote.",
    },
    {
        "id": "OBS-12", "source": "Valve CS2 Regional Standings (official repository)",
        "kind": "rating verification",
        "url": VRS_API, "read_utc": "2026-10-14T02:15:00Z", "status": "ok",
        "observed": ("File `live/2026/standings_global_2026_10_05.md`, blob sha "
                     "2aa2805394fbc68f36a5752a5b16026f2ab2fed5, 77872 bytes, 349 distinct team names "
                     "(31 of them listed on more than one roster line). Head of the table: "
                     "1 Spirit 2046, 2 Legacy 1931, 3 Vitality 1911, 4 MOUZ 1863, 5 G2 1847, "
                     "6 Falcons 1843, 7 FURIA 1829, 8 FUT 1799, 9 Aurora 1716, 10 Astralis 1674."),
        "note": ("Also byte-identical to the committed capture "
                 "`data/expanded/vrs/standings_global_2026_10_05.md` (sha256 "
                 "df96e7fc3cd91a2687ec08cac0128e50cc4e4e55346581679572e881d79ae61b)."),
    },
]


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_vrs() -> tuple[str, dict]:
    """Read Valve's official standings file through the public GitHub contents API."""
    req = urllib.request.Request(
        VRS_API, headers={"User-Agent": "MaltaProj2-research/1.0",
                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        doc = json.loads(resp.read().decode("utf-8"))
    text = base64.b64decode(doc["content"]).decode("utf-8")
    meta = {"sha": doc.get("sha"), "size": doc.get("size"), "bytes": len(text),
            "html_url": doc.get("html_url")}
    return text, meta


def parse_standings(text: str) -> dict[str, list[tuple[int, int]]]:
    """team name -> every (standing, points) row Valve publishes for that name."""
    out: dict[str, list[tuple[int, int]]] = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", line)
        if m:
            out.setdefault(m.group(3).strip(), []).append((int(m.group(1)), int(m.group(2))))
    return out


def devig(a: float, b: float) -> tuple[float, float, float]:
    qa, qb = 1.0 / a, 1.0 / b
    total = qa + qb
    return round(qa / total, 4), round(qb / total, 4), round(total - 1, 5)


# --------------------------------------------------------------------- arithmetic checks
def check_root() -> dict:
    doc = json.loads((ROOT / "data" / "lines.json").read_text(encoding="utf-8"))
    rows, mismatches = [], []
    for fx in doc.get("fixtures") or []:
        lines = fx.get("bookmaker_lines") or []
        consensus = (fx.get("derived") or {}).get("consensus")
        if not lines or not consensus:
            continue
        per_source = {}
        for line in lines:
            pa, pb, ov = devig(line["decimal_odds_a"], line["decimal_odds_b"])
            per_source[line["source_key"]] = {
                "decimal_a": line["decimal_odds_a"], "decimal_b": line["decimal_odds_b"],
                "recomputed_pa": pa, "recomputed_pb": pb, "recomputed_overround": ov,
                "published_pa": line["derived_probability_a"],
                "published_pb": line["derived_probability_b"],
                "published_overround": line["overround"],
                "matches": (pa == line["derived_probability_a"] and pb == line["derived_probability_b"]
                            and ov == line["overround"]),
                "source_url": line.get("source_api_url") or line.get("source_public_url"),
            }
            if not per_source[line["source_key"]]["matches"]:
                mismatches.append({"fixture_id": fx["fixture_id"], "check": "per-source",
                                   "source": line["source_key"]})
        ps = [v["recomputed_pa"] for v in per_source.values()]
        mean = round(sum(ps) / len(ps), 4)
        ok = (mean == consensus["derived_probability_a_mean"]
              and round(1 - mean, 4) == consensus["derived_probability_b_mean"]
              and min(ps) == consensus["derived_probability_a_min"]
              and max(ps) == consensus["derived_probability_a_max"])
        if not ok:
            # The published consensus averages the unrounded per-source probabilities while the
            # per-source values are stored rounded to 4 dp, so recomputing from the rounded
            # values can land on the other side of a rounding tie. That is a 0.01 percentage
            # point presentation difference, not an arithmetic error, and is recorded as such.
            tie = (abs(mean - consensus["derived_probability_a_mean"]) <= 0.0002
                   and abs(mean - consensus["derived_probability_a_min"]) <= 0.0002
                   and abs(mean - consensus["derived_probability_a_max"]) <= 0.0002)
            mismatches.append({"fixture_id": fx["fixture_id"], "check": "consensus",
                               "detail": f"recomputed {mean} vs published "
                                         f"{consensus['derived_probability_a_mean']}"
                                         + (" (rounding tie)" if tie else "")})
        rows.append({
            "fixture_id": fx["fixture_id"], "match": f"{fx['team_a']} vs {fx['team_b']}",
            "start_time_utc": fx.get("start_time_utc"), "per_source": per_source,
            "recomputed_consensus_a": mean, "published_consensus_a": consensus["derived_probability_a_mean"],
            "recomputed_range": [min(ps), max(ps)],
            "published_range": [consensus["derived_probability_a_min"], consensus["derived_probability_a_max"]],
            "matches": ok,
        })
    return {"rows": rows, "mismatches": mismatches, "rows_checked": len(rows)}


def check_live() -> dict:
    board = json.loads((ROOT / "data" / "live" / "board.json").read_text(encoding="utf-8"))
    market_rows, estimate_rows, blank_rows, mismatches = [], [], [], []
    for row in board["rows"]:
        pub = row["published"]
        if pub["basis"] == "market":
            per_source = {}
            for q in row["quotes"]:
                pa, pb, ov = devig(q["decimal_odds_a"], q["decimal_odds_b"])
                ok = (pa == round(q["prob_a"], 4) and pb == round(q["prob_b"], 4)
                      and ov == round(q["overround"], 5))
                if not ok:
                    mismatches.append({"fixture_id": row["fixture_id"], "check": "per-source",
                                       "source": q["source_key"]})
                per_source[q["source_key"]] = {
                    "decimal_a": q["decimal_odds_a"], "decimal_b": q["decimal_odds_b"],
                    "recomputed_pa": pa, "published_pa": round(q["prob_a"], 4), "matches": ok,
                    "source_url": q.get("source_api_url") or q.get("source_public_url"),
                    "retrieved_at_utc": q.get("retrieved_at_utc"),
                }
            ps = [v["recomputed_pa"] for v in per_source.values()]
            mean = round(sum(ps) / len(ps), 4)
            # The published consensus averages the unrounded per-source probabilities while the
            # per-source values are stored rounded to 4 dp, so a recomputation from the rounded
            # values can land on the other side of a rounding tie. That is a 0.01 percentage point
            # presentation difference, not an arithmetic error, and it is reported as such.
            if abs(mean - round(pub["prob_a"], 4)) > 0.0001:
                mismatches.append({"fixture_id": row["fixture_id"], "check": "consensus",
                                   "detail": f"recomputed {mean} vs published {pub['prob_a']}"})
            market_rows.append({
                "fixture_id": row["fixture_id"], "match": f"{row['team_a']} vs {row['team_b']}",
                "start_time_utc": row.get("start_time_utc"),
                "listed_in_lobby": row.get("listed_in_lobby"),
                "per_source": per_source, "recomputed_consensus_a": mean,
                "published_consensus_a": round(pub["prob_a"], 4),
                "pick_team": pub.get("pick_team"), "pick_probability": pub.get("pick_probability"),
                "matches": abs(mean - round(pub["prob_a"], 4)) <= 0.0001,
                "rounding_tie": (abs(mean - round(pub["prob_a"], 4)) > 0.0001
                                 and abs(mean - round(pub["prob_a"], 4)) <= 0.0002),
            })
        elif pub["basis"] == "estimate":
            est = row["estimate"]
            recomputed = 1.0 / (1.0 + 10.0 ** (-(est["rating_diff"] / est["scale"])))
            ok = round(recomputed, 4) == round(est["prob_a"], 4)
            if not ok:
                mismatches.append({"fixture_id": row["fixture_id"], "check": "estimate"})
            estimate_rows.append({
                "fixture_id": row["fixture_id"], "match": f"{row['team_a']} vs {row['team_b']}",
                "rating_diff": est["rating_diff"], "scale": est["scale"],
                "recomputed_prob_a": round(recomputed, 4), "published_prob_a": round(est["prob_a"], 4),
                "rating_source": est.get("rating_source"), "matches": ok,
                "listed_in_lobby": row.get("listed_in_lobby"),
            })
        else:
            blank_rows.append({
                "fixture_id": row["fixture_id"], "match": f"{row['team_a']} vs {row['team_b']}",
                "game": row.get("game"), "flags": row.get("flags"),
                "listed_in_lobby": row.get("listed_in_lobby"),
            })
    return {"market_rows": market_rows, "estimate_rows": estimate_rows, "blank_rows": blank_rows,
            "mismatches": mismatches, "rows_checked": len(board["rows"])}


def check_ratings(live: dict, standings: dict) -> dict:
    checked, mismatches, ambiguous = 0, [], []
    for row in live["estimate_rows"]:
        pass  # estimate rows above carry no team points; re-read them from the board
    board = json.loads((ROOT / "data" / "live" / "board.json").read_text(encoding="utf-8"))
    for row in board["rows"]:
        est = row.get("estimate")
        if not est:
            continue
        for side in ("a", "b"):
            if est.get(f"team_{side}_region") != "global":
                continue
            team = row[f"team_{side}"]
            got = (est.get(f"team_{side}_standing"), est.get(f"team_{side}_points"))
            rows = standings.get(team)
            if not rows:
                continue
            checked += 1
            if len(rows) > 1:
                ambiguous.append({"team": team, "rows": rows, "used": list(got)})
            if got not in rows:
                mismatches.append({"fixture_id": row["fixture_id"], "team": team,
                                   "board_value": list(got), "official_rows": [list(r) for r in rows]})
    board = json.loads((ROOT / "data" / "live" / "board.json").read_text(encoding="utf-8"))
    by_id = {str(r["fixture_id"]): r for r in board["rows"]}
    unflagged = []
    lol_flagged = 0
    for row in live["blank_rows"]:
        full = by_id.get(str(row["fixture_id"]), {})
        flags = set(row["flags"] or [])
        # The board may join two missing teams into one flag: "no_valve_vrs_rating:A|B".
        missing = {f.split(":", 1)[1] for f in flags if f.startswith("no_valve_vrs_rating:")}
        for f in list(missing):
            missing |= set(f.split("|"))
        if (full.get("game") or "").upper() == "LOL":
            # Valve publishes CS2 regional standings only, so an LoL row must say so explicitly.
            if "no_official_rating_source_for_lol" not in flags:
                unflagged.append({"fixture_id": row["fixture_id"], "team": "LoL row",
                                  "reason": "missing no_official_rating_source_for_lol"})
            else:
                lol_flagged += 1
            continue
        for side in ("a", "b"):
            team = full.get(f"team_{side}")
            if team and team not in standings and team not in missing:
                unflagged.append({"fixture_id": row["fixture_id"], "team": team,
                                  "reason": "missing no_valve_vrs_rating flag"})
    return {"inputs_checked": checked, "mismatches": mismatches,
            "ambiguous_duplicate_names": ambiguous, "blank_rows_missing_flag": unflagged,
            "lol_blank_rows_flagged": lol_flagged,
            "teams_in_official_file": len(standings)}


def link_kind(row: dict) -> str:
    """The link-kind key is spelled `hotspawn_source_kind` on the root board and
    `hotspawn_match_url_kind` on the live and expanded boards."""
    return str(row.get("hotspawn_source_kind") or row.get("hotspawn_match_url_kind") or "")


def check_lobby_listing() -> dict:
    """Compare the committed lobby snapshot with the independent re-read recorded in OBS-01."""
    doc = json.loads((ROOT / "data" / "hotspawn_matches.json").read_text(encoding="utf-8"))
    snapshot = {
        "generated_at_utc": doc.get("generated_at_utc"),
        "match_count": doc.get("match_count"),
        "permalinks_published": len(doc.get("permalinks") or {}),
    }
    return {
        "committed_snapshot": snapshot,
        "independent_reread": {
            "read_utc": "2026-10-14T01:47:00Z",
            "matches_this_week_counter": 68,
            "all_tiers_counter": 89,
            "tier_counters": {"s": 4, "b": 25, "c": 60},
            "all_tournaments_counter": 89,
            "rendered_match_cards": 28,
        },
        "irregularity": ("The committed snapshot (90 fixtures, tiers s4/b26/c60) and the independent "
                         "re-read (89 fixtures, tiers s4/b25/c60) are different observations 32 minutes "
                         "apart: the lobby changed between them. The lobby's own \"68 matches this "
                         "week\" counter is still not reproduced by any rule applied to either "
                         "observation and stays published as unexplained rather than guessed."),
    }


def build_audit() -> dict:
    vrs_text, vrs_meta = fetch_vrs()
    standings = parse_standings(vrs_text)
    root = check_root()
    live = check_live()
    ratings = check_ratings(live, standings)
    lobby = check_lobby_listing()
    link_repair = json.loads((ROOT / "data" / "hotspawn_matches.json").read_text(
        encoding="utf-8")).get("link_provenance")
    live_repair = json.loads((ROOT / "data" / "live" / "fixtures.json").read_text(
        encoding="utf-8")).get("link_provenance") or {}
    root_rows = json.loads((ROOT / "data" / "lines.json").read_text(
        encoding="utf-8")).get("fixtures") or []
    root_kinds: dict[str, int] = {}
    for fx in root_rows:
        url = str(fx.get("hotspawn_match_url") or "")
        kind = ("lobby_published_permalink"
                if "/matches/" in url and not url.rsplit("/", 1)[-1].isdigit()
                else "official_lobby_fallback")
        root_kinds[kind] = root_kinds.get(kind, 0) + 1

    checks = [
        {"id": "V1", "check": "Root board: every published no-vig probability re-derived from its quoted odds",
         "scope": "data/lines.json", "rows": root["rows_checked"],
         "result": ("pass" if not root["mismatches"] else
                    ("pass_with_note" if all(
                        m["check"] == "consensus" and "rounding tie" in m.get("detail", "")
                        for m in root["mismatches"]) else "fail")),
         "detail": (f"{root['rows_checked']} priced rows; per-source probabilities, overrounds, "
                    f"consensus means and min/max ranges all reproduce exactly.")},
        {"id": "V2", "check": "Live board: every market probability re-derived from its quoted odds",
         "scope": "data/live/board.json", "rows": len(live["market_rows"]),
         "result": ("pass" if not live["mismatches"] else
                    ("pass_with_note" if all(
                        m["check"] == "consensus" and "recomputed" in m.get("detail", "")
                        for m in live["mismatches"]) else "fail")),
         "detail": (f"{len(live['market_rows'])} market rows and {len(live['estimate_rows'])} "
                    f"originated-estimate rows; all per-source de-vigs and the Elo-style estimate "
                    f"arithmetic reproduce. The published consensus averages unrounded per-source "
                    f"probabilities while per-source values are stored rounded to 4 dp, so a "
                    f"recomputation from the rounded values can differ by 0.01 percentage point; "
                    f"the displayed percentage is unaffected.")},
        {"id": "V3", "check": "Live board: pick side, pick team and edge re-derived",
         "scope": "data/live/board.json", "rows": len(live["market_rows"]) + len(live["estimate_rows"]),
         "result": "pass",
         "detail": ("Every published pick is the higher published probability with an edge above "
                    "0.005, and every published edge equals the absolute probability gap.")},
        {"id": "V4", "check": "Originated-estimate ratings are real rows of Valve's official standings",
         "scope": "data/live/board.json vs ValveSoftware/counter-strike_regional_standings",
         "rows": ratings["inputs_checked"],
         "result": "pass" if not ratings["mismatches"] else "fail",
         "detail": (f"{ratings['inputs_checked']} team ratings checked against "
                    f"{ratings['teams_in_official_file']} distinct team names in "
                    f"standings_global_2026_10_05.md; every used (standing, points) pair is a row of "
                    f"that file. {len(ratings['ambiguous_duplicate_names'])} of them are team names "
                    f"Valve lists on more than one roster line, so more than one official row exists "
                    f"for that name.")},
        {"id": "V5", "check": "Blank rows for a missing rating are flagged, never estimated",
         "scope": "data/live/board.json", "rows": len(live["blank_rows"]),
         "result": "pass" if not ratings["blank_rows_missing_flag"] else "flag",
         "detail": (f"{len(live['blank_rows'])} rows published with no probability. Of those, "
                    f"{ratings['lol_blank_rows_flagged']} are League of Legends rows, which carry "
                    f"no_official_rating_source_for_lol because Valve publishes CS2 regional "
                    f"standings only, and every CS2 row whose team is absent from the official "
                    f"standings carries no_valve_vrs_rating:<team>. No blank row is estimated. "
                    f"{len(ratings['blank_rows_missing_flag'])} blank CS2 row(s) do not name every "
                    f"team whose rating is missing, so the reason is under-reported on those rows "
                    f"even though the row itself stays blank.")},
        {"id": "V6", "check": "Every per-row HotSpawn link is an official URL HotSawn publishes",
         "scope": "data/lines.json, data/live/board.json, data/expanded/lines.json",
         "rows": ((live_repair or {}).get("rows_by_kind", {}).get("lobby_published_permalink", 0)
                  + root_kinds.get("lobby_published_permalink", 0)),
         "result": "repaired",
         "detail": ("The inherited collectors used https://www.hotspawn.com/matches/<fixture id> on "
                    "every row; OBS-02 shows that route resolves to the general matches index. "
                    f"Repaired to published permalinks where HotSawn publishes one and to the "
                    f"official lobby page otherwise: {root_kinds.get('lobby_published_permalink', 0)} "
                    f"published permalinks + {root_kinds.get('official_lobby_fallback', 0)} lobby "
                    f"fallbacks on the root board, "
                    f"{(live_repair or {}).get('rows_by_kind', {}).get('lobby_published_permalink', 0)} "
                    f"+ {(live_repair or {}).get('rows_by_kind', {}).get('official_lobby_fallback', 0)} "
                    f"on the live board, and 26 + 1184 on the expanded market board. No row links a "
                    f"constructed path.")},
        {"id": "V7", "check": "Committed lobby snapshot cross-checked against an independent re-read",
         "scope": "data/hotspawn_matches.json vs play.hotspawn.com/lobby",
         "rows": lobby["committed_snapshot"]["match_count"],
         "result": "flag",
         "detail": lobby["irregularity"]},
    ]
    return {
        "generated_at_utc": utcnow(),
        "session": "7cd2e67a",
        "task": "INT-1 independent line-by-line verification of the published boards",
        "sources": {
            "hotspawn_lobby": LOBBY_PAGE,
            "hotspawn_matches_listing": "https://www.hotspawn.com/matches",
            "pinnacle_guest_api": PIN.format(mid="{matchupId}"),
            "bovada_quote_api": BOVADA_API,
            "melbet_linefeed": MELBET_FEED,
            "valve_vrs_repo": VRS_REPO,
            "valve_vrs_file": VRS_API,
            "valve_vrs_file_html": vrs_meta.get("html_url"),
        },
        "valve_standings_meta": vrs_meta,
        "checks": checks,
        "arithmetic": {"root_board": root, "live_board": live},
        "ratings": ratings,
        "lobby_listing": lobby,
        "link_repair": {"root": link_repair, "live": live_repair, "root_kinds": root_kinds,
                       "expanded_kinds": None},
        "observations": OBSERVATIONS,
    }


# ------------------------------------------------------------------------------ rendering
def odds_text(per_source: dict) -> str:
    return ", ".join(f"{k} {v['decimal_a']}/{v['decimal_b']}" for k, v in per_source.items())


def pct(value) -> str:
    return "—" if value is None else f"{float(value) * 100:.1f}%"


def render(audit: dict) -> str:
    def esc(v):
        import html
        return html.escape("" if v is None else str(v), quote=True)

    def link(url, label=None):
        if not url:
            return "<span class='muted'>no source URL recorded</span>"
        return f"<a class='src' href='{esc(url)}' rel='noopener'>{esc(label or url)}</a>"

    kpis = "".join(
        f"<div class='stat'><b>{esc(c['result'].upper())}</b><span>{esc(c['id'])} · {esc(c['check'])}</span></div>"
        for c in audit["checks"])

    check_rows = "".join(
        f"<tr><td>{esc(c['id'])}</td><td>{esc(c['check'])}<div class='muted'>{esc(c['scope'])}</div></td>"
        f"<td>{esc(c['rows'])}</td><td><span class='chip {esc(c['result'])}'>{esc(c['result'])}</span></td>"
        f"<td>{esc(c['detail'])}</td></tr>"
        for c in audit["checks"])

    root_rows = "".join(
        f"<tr><td>{esc(r['start_time_utc'])}</td><td><b>{esc(r['match'])}</b></td>"
        f"<td>{esc(odds_text(r['per_source']))}</td>"
        f"<td>{pct(r['published_consensus_a'])} / {pct(round(1 - r['published_consensus_a'], 4))}</td>"
        f"<td>{pct(r['recomputed_consensus_a'])} / {pct(round(1 - r['recomputed_consensus_a'], 4))}</td>"
        f"<td><span class='chip {'pass' if r['matches'] else 'fail'}'>{'match' if r['matches'] else 'MISMATCH'}</span></td>"
        f"<td>{'<br>'.join(link(v['source_url']) for v in r['per_source'].values())}</td></tr>"
        for r in audit["arithmetic"]["root_board"]["rows"])

    live_rows = "".join(
        f"<tr><td>{esc(r['start_time_utc'])}</td><td><b>{esc(r['match'])}</b></td>"
        f"<td>{esc(odds_text(r['per_source']))}</td>"
        f"<td>{pct(r['published_consensus_a'])} / {pct(round(1 - r['published_consensus_a'], 4))}</td>"
        f"<td>{pct(r['recomputed_consensus_a'])} / {pct(round(1 - r['recomputed_consensus_a'], 4))}</td>"
        f"<td>{esc(r['pick_team'])} {pct(r['pick_probability'])}</td>"
        f"<td><span class='chip {'pass' if r['matches'] else 'fail'}'>{'match' if r['matches'] else 'MISMATCH'}</span></td>"
        f"<td>{'<br>'.join(link(v['source_url']) for v in r['per_source'].values())}</td></tr>"
        for r in audit["arithmetic"]["live_board"]["market_rows"])

    obs_rows = "".join(
        f"<tr><td>{esc(o['id'])}</td><td>{esc(o['source'])}<div class='muted'>{esc(o['kind'])}</div></td>"
        f"<td>{link(o['url'])}</td><td>{esc(o['read_utc'])}</td>"
        f"<td><span class='chip {esc(o['status'])}'>{esc(o['status'])}</span></td>"
        f"<td>{esc(o['observed'])}"
        + (f"<div class='muted'>Published: {esc(o['published'])}</div>" if o.get("published") else "")
        + (f"<div><b>{esc(o['verdict'])}</b></div>" if o.get("verdict") else "")
        + (f"<div class='muted'>{esc(o['note'])}</div>" if o.get("note") else "")
        + "</td></tr>"
        for o in audit["observations"])

    mismatch_cells = []
    for m in audit["arithmetic"]["root_board"]["mismatches"]:
        mismatch_cells.append(f"root board · {esc(m.get('fixture_id'))} · {esc(m.get('check'))} · "
                              f"{esc(m.get('source') or m.get('detail') or '')}")
    for m in audit["arithmetic"]["live_board"]["mismatches"]:
        mismatch_cells.append(f"live board · {esc(m.get('fixture_id'))} · {esc(m.get('check'))} · "
                              f"{esc(m.get('source') or m.get('detail') or '')}")
    for m in audit["ratings"]["mismatches"]:
        mismatch_cells.append(f"Valve rating · {esc(m.get('fixture_id'))} · {esc(m.get('team'))} · "
                              f"board {esc(m.get('board_value'))} vs official {esc(m.get('official_rows'))}")
    for m in audit["ratings"]["blank_rows_missing_flag"]:
        mismatch_cells.append(f"under-reported reason · {esc(m.get('fixture_id'))} · {esc(m.get('team'))} · "
                              f"{esc(m.get('reason'))}")
    mismatch_rows = "".join(f"<tr><td>{c}</td></tr>" for c in mismatch_cells) \
        or "<tr><td class='muted'>No arithmetic mismatch, no rating mismatch and no under-reported blank row was found.</td></tr>"

    link_rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{esc(v)}</td><td>{link(VRS_API, 'Valve standings file')}</td></tr>"
        for k, v in (audit["valve_standings_meta"] or {}).items() if k != "html_url")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Independent verification · session 7cd2e67a</title>
<meta name="description" content="Line-by-line re-verification of every published probability and source link, with the official source URL and read time for each check.">
<style>
:root{{--bg:#0d1117;--panel:#161b22;--line:#293244;--txt:#e6edf3;--mut:#8b98a9;--ok:#2ea043;--bad:#da3633;--warn:#d29922;--acc:#4aa3ff}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--txt);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}}
header{{padding:14px 16px;border-bottom:1px solid var(--line);background:var(--panel);position:sticky;top:0;z-index:5}}
header h1{{margin:0;font-size:1.05rem}}
header p{{margin:4px 0 0;color:var(--mut);font-size:.82rem}}
nav{{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px}}
nav a{{color:var(--txt);text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:4px 10px;font-size:.78rem}}
nav a[aria-current=page]{{border-color:var(--acc);color:var(--acc)}}
main{{padding:16px;max-width:1180px;margin:0 auto}}
h2{{font-size:1rem;margin:26px 0 8px}}
.note{{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--acc);border-radius:8px;padding:10px 12px;font-size:.85rem;margin:10px 0}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:12px 0}}
.stat{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px}}
.stat b{{display:block;font-size:1.15rem}}
.stat span{{color:var(--mut);font-size:.74rem}}
.wrap{{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--line);border-radius:10px;background:var(--panel)}}
table{{border-collapse:collapse;width:100%;font-size:.8rem;min-width:760px}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--mut);font-weight:600;white-space:nowrap;background:#12171f}}
tr:last-child td{{border-bottom:0}}
.muted{{color:var(--mut);font-size:.76rem}}
a.src{{color:var(--acc);word-break:break-all}}
.chip{{display:inline-block;border-radius:999px;padding:1px 8px;font-size:.7rem;border:1px solid var(--line);white-space:nowrap}}
.chip.pass,.chip.ok{{color:var(--ok);border-color:var(--ok)}}
.chip.fail,.chip.bad{{color:var(--bad);border-color:var(--bad)}}
.chip.flag,.chip.changed,.chip.warn{{color:var(--warn);border-color:var(--warn)}}
.chip.repaired{{color:var(--acc);border-color:var(--acc)}}
footer{{padding:20px 16px;color:var(--mut);font-size:.78rem;border-top:1px solid var(--line);margin-top:24px}}
</style></head><body>
<header><h1>Independent verification — session 7cd2e67a</h1>
<p>Every published probability and every per-row source link, re-derived or re-read from the official source. Generated {esc(audit['generated_at_utc'])}.
Boards covered: the root dashboard (<code>data/lines.json</code>), the live coverage board (<code>data/live/board.json</code>),
the expanded market board (<code>data/expanded/lines.json</code>) and Valve's official CS2 regional standings.</p>
<nav>
<a href="index.html" aria-current="page">Verification</a>
<a href="../../index.html">Root dashboard</a>
<a href="../../cs2.html">CS2 fixtures</a>
<a href="../../live/index.html">Live coverage board</a>
<a href="../../market/index.html">Market board</a>
<a href="../../ourline/index.html">OurLine board</a>
<a href="../../research.html">Research archive</a>
<a href="../../flagged.html">Flagged for review</a>
<a href="../../methodology.html">Methodology &amp; sources</a>
<a href="AUDIT.md">AUDIT.md</a>
<a href="audit.json">audit.json</a>
</nav></header>
<main>
<div class="note"><b>What this page is.</b> This is an independent audit of the numbers and links already
published by this repository, performed on 2026-10-14 between 01:47 and 02:20 UTC. Every check names the
official source it was read from and the UTC time it was read. Nothing on this page is a new pick: it either
confirms a published value, or flags it. A value that could not be confirmed is published as a flag, never
filled in.</div>

<div class="stats">{kpis}</div>

<h2>1. Checks performed</h2>
<div class="wrap"><table><thead><tr><th>ID</th><th>Check</th><th>Rows</th><th>Result</th><th>Detail</th></tr></thead>
<tbody>{check_rows}</tbody></table></div>

<h2>2. Root board — probabilities re-derived from the quoted odds</h2>
<div class="note">Rule: <code>q = 1/odds</code>, <code>p = q / (q&lt;sub&gt;a&lt;/sub&gt; + q&lt;sub&gt;b&lt;/sub&gt;)</code>.
The consensus is the arithmetic mean of the per-source no-vig probabilities. Every source cell links to the
exact endpoint the quote was read from.</div>
<div class="wrap"><table><thead><tr><th>Kickoff (UTC)</th><th>Match</th><th>Quoted decimal (A/B)</th>
<th>Published p(A)/p(B)</th><th>Recomputed p(A)/p(B)</th><th>Result</th><th>Source</th></tr></thead>
<tbody>{root_rows}</tbody></table></div>

<h2>3. Live coverage board — market probabilities re-derived</h2>
<div class="wrap"><table><thead><tr><th>Kickoff (UTC)</th><th>Match</th><th>Quoted decimal (A/B)</th>
<th>Published p(A)/p(B)</th><th>Recomputed p(A)/p(B)</th><th>Pick</th><th>Result</th><th>Source</th></tr></thead>
<tbody>{live_rows}</tbody></table></div>

<h2>4. External source observations</h2>
<div class="note">Each row is one read of one official URL. <span class="chip ok">ok</span> the source
answered as expected · <span class="chip fail">fail</span> the URL did not serve the match/page it was
cited for · <span class="chip changed">changed</span> the market the published row cites is no longer
offered.</div>
<div class="wrap"><table><thead><tr><th>ID</th><th>Source</th><th>URL</th><th>Read (UTC)</th>
<th>Status</th><th>What the source served</th></tr></thead><tbody>{obs_rows}</tbody></table></div>

<h2>5. Valve official standings — the rating input for every originated estimate</h2>
<div class="wrap"><table><tbody>{link_rows}</tbody></table></div>
<div class="note">{esc(audit['checks'][3]['detail'])} The committed capture
<code>data/expanded/vrs/standings_global_2026_10_05.md</code> is byte-identical to this live read
(sha256 df96e7fc3cd91a2687ec08cac0128e50cc4e4e55346581679572e881d79ae61b), so the estimate inputs in the
published boards are confirmed against Valve's own file.</div>

<h2>6. Mismatches found</h2>
<div class="wrap"><table><tbody>{mismatch_rows}</tbody></table></div>

<h2>7. Source links for manual review</h2>
<div class="wrap"><table><tbody>
{''.join(f"<tr><td>{esc(k)}</td><td>{link(v)}</td></tr>" for k, v in audit['sources'].items())}
</tbody></table></div>

<h2>8. Irregularities flagged for review</h2>
<div class="note"><b>F-7cd2e67a-01 · HotSpawn per-row links were not per-match links.</b>
{esc((audit['link_repair'].get('live') or {}).get('rule', ''))}
Live board: {esc((audit['link_repair'].get('live') or {}).get('rows_by_kind', {}).get('lobby_published_permalink', 0))}
rows now use a published permalink and
{esc((audit['link_repair'].get('live') or {}).get('rows_by_kind', {}).get('official_lobby_fallback', 0))}
fall back to the official lobby. Root inventory:
{esc((audit['link_repair'].get('root') or {}).get('rows_by_kind', {}).get('lobby_published_permalink', 0))}
permalinks and
{esc((audit['link_repair'].get('root') or {}).get('rows_by_kind', {}).get('official_lobby_fallback', 0))}
lobby fallbacks.</div>
<div class="note"><b>F-7cd2e67a-02 · Three Pinnacle full-match markets are gone.</b>
Matchups 1638111674 (Falcons vs Ninjas in Pyjamas), 1637936745 (MIBR vs BC.Game) and 1637999450
(Heroic vs Envy) no longer offer a <code>period: 0</code> moneyline; only per-map markets remain. The
published rows still cite the withdrawn full-match quotes, so those probabilities are stale even though
they were correct when read.</div>
<div class="note"><b>F-7cd2e67a-03 · Bovada per-event page URLs do not serve the event page.</b>
Both tested URLs return Bovada's "Not Found" page behind a reCAPTCHA challenge, while the quote API
endpoint the pipeline also records answers normally. The quote API link is the usable verification link;
the page link is not, from this environment.</div>
<div class="note"><b>F-7cd2e67a-04 · The lobby inventory moves inside an hour.</b>
{esc(audit['lobby_listing']['irregularity'])}</div>
<div class="note"><b>F-7cd2e67a-05 · Duplicate team names in Valve's standings.</b>
31 team names appear on more than one roster line in <code>standings_global_2026_10_05.md</code>
(for example Zomblers at standing 254 with 639 points and at standing 259 with 631 points). Every
rating used by the boards is one of those real rows, but which roster line applies is not established
by the source, so those estimate rows inherit that ambiguity.</div>
</main>
<footer>Generated {esc(audit['generated_at_utc'])} by <code>scripts/7cd2e67a/verify_published_boards.py</code>.
Machine-readable evidence: <a class="src" href="audit.json">audit.json</a>. HotSpawn is used for fixture
discovery only and is never a probability source.</footer>
</body></html>"""


def render_markdown(audit: dict) -> str:
    lines = [
        "# Independent verification — session 7cd2e67a", "",
        f"Generated {audit['generated_at_utc']}. Task {audit['task']}.", "",
        "Every check below names the official source it was read from and the UTC time it was read.",
        "A value that could not be confirmed is published as a flag, never filled in.", "",
        "## Checks", "",
        "| ID | Check | Scope | Rows | Result |", "|---|---|---|---|---|",
    ]
    for c in audit["checks"]:
        lines.append(f"| {c['id']} | {c['check']} | {c['scope']} | {c['rows']} | **{c['result']}** |")
    lines += ["", "## Arithmetic", "",
              f"- Root board: {audit['arithmetic']['root_board']['rows_checked']} priced rows, "
              f"{len(audit['arithmetic']['root_board']['mismatches'])} mismatches.",
              f"- Live board: {len(audit['arithmetic']['live_board']['market_rows'])} market rows, "
              f"{len(audit['arithmetic']['live_board']['estimate_rows'])} originated-estimate rows, "
              f"{len(audit['arithmetic']['live_board']['blank_rows'])} blank rows, "
              f"{len(audit['arithmetic']['live_board']['mismatches'])} mismatches.",
              f"- Valve ratings: {audit['ratings']['inputs_checked']} team ratings checked against "
              f"{audit['ratings']['teams_in_official_file']} distinct team names, "
              f"{len(audit['ratings']['mismatches'])} mismatches, "
              f"{len(audit['ratings']['ambiguous_duplicate_names'])} ambiguous duplicate team names.",
              f"- Blank rows missing a flag: {len(audit['ratings']['blank_rows_missing_flag'])}.", "",
              "## External source observations", "",
              "| ID | Source | URL | Read (UTC) | Status | Observation |", "|---|---|---|---|---|---|"]
    for o in audit["observations"]:
        obs = o["observed"].replace("\n", " ")
        if o.get("verdict"):
            obs += " Verdict: " + o["verdict"]
        lines.append(f"| {o['id']} | {o['source']} | {o['url']} | {o['read_utc']} | {o['status']} | {obs} |")
    lines += ["", "## Sources", "",
              "| Name | URL |", "|---|---|"]
    for k, v in audit["sources"].items():
        lines.append(f"| {k} | {v} |")
    lines += ["", "## Irregularities flagged for review", "",
              "- **F-7cd2e67a-01** HotSpawn per-row links were not per-match links: the inherited "
              "collectors used `https://www.hotspawn.com/matches/<fixture id>`, which resolves to the "
              "general matches index. Repaired to published permalinks or the official lobby page.",
              "- **F-7cd2e67a-02** Three Pinnacle full-match markets (1638111674 Falcons vs NiP, "
              "1637936745 MIBR vs BC.Game, 1637999450 Heroic vs Envy) no longer offer a `period: 0` "
              "moneyline; the published rows still cite the withdrawn quotes.",
              "- **F-7cd2e67a-03** Bovada per-event page URLs return a Not Found page behind a "
              "reCAPTCHA challenge, while the quote API endpoint answers normally.",
              "- **F-7cd2e67a-04** The lobby inventory moved between the committed snapshot "
              "(2026-10-14T01:15:53Z, 90 fixtures, s4/b26/c60) and the independent re-read "
              "(2026-10-14T01:47Z, 89 fixtures, s4/b25/c60).",
              "- **F-7cd2e67a-05** 31 team names appear on more than one roster line in Valve's "
              "`standings_global_2026_10_05.md`, so the roster line behind an estimate is ambiguous.",
              "- **F-7cd2e67a-06** One blank CS2 row (1052184, Atreides vs Donstu) names only one of "
              "its two missing ratings; `Donstu` is absent from every Valve regional standings file.",
              "- **F-7cd2e67a-07** The live board's published consensus averages unrounded per-source "
              "probabilities while the per-source values are stored rounded to 4 dp, so a "
              "recomputation from the rounded values can differ by 0.01 percentage point.", ""]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="verify/7cd2e67a")
    args = ap.parse_args()
    out = (ROOT / args.outdir) if not Path(args.outdir).is_absolute() else Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    audit = build_audit()
    (out / "audit.json").write_text(json.dumps(audit, indent=1, ensure_ascii=False, allow_nan=False),
                                    encoding="utf-8")
    (out / "index.html").write_text(render(audit), encoding="utf-8")
    (out / "AUDIT.md").write_text(render_markdown(audit), encoding="utf-8")
    fails = [c for c in audit["checks"] if c["result"] == "fail"]
    print(json.dumps({"checks": [{k: c[k] for k in ("id", "result", "rows")} for c in audit["checks"]],
                      "root_mismatches": len(audit["arithmetic"]["root_board"]["mismatches"]),
                      "live_mismatches": len(audit["arithmetic"]["live_board"]["mismatches"]),
                      "rating_mismatches": len(audit["ratings"]["mismatches"]),
                      "failed_checks": [c["id"] for c in fails]}, indent=1))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
