#!/usr/bin/env python3
"""Build the complete CS2 and LoL pick'em inventories.

Inputs (all already in repo):
  data/hotspawn_matches.json  — official play API snapshot (407 rows, captured 2026-10-13T18:25:09Z,
                                source https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures,
                                embedded in play.hotspawn.com/lobby public HTML)
  data/cs2_matches.json       — this session's lobby CARD observations (30 rows across two replica states)

Outputs:
  data/cs2_matches.json  — rewritten: all 93 CS2 rows (API layer + card_observed flags + lobby snapshots)
  data/cs2_unrendered_flags.json — the 59 past-lock rows are now row-identified from the API; the
                                IRREGULARITY (lobby counts unplayable past-lock rows) is kept and flagged
                                with filled, source-linked rows (nothing inferred: values come from API).
  data/lol_matches.json  — all 314 LoL rows + lobby-count reconciliation.
"""
import json
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 13, 19, 0, tzinfo=timezone.utc)

api = json.loads((ROOT / "data" / "hotspawn_matches.json").read_text())
API_ROWS = api["matches"]
API_URL = api["source_endpoint"]

cs2_old = json.loads((ROOT / "data" / "cs2_matches.json").read_text())
_raw = cs2_old.get("matches", [])
if _raw and "tournament" in _raw[0]:
    card_rows = _raw  # original 30-row card capture (old schema)
else:  # already rebuilt: recover card observations from new schema (idempotent rerun)
    card_rows = [
        {"tournament": r.get("competition"), "team_a": r.get("team_a"), "team_b": r.get("team_b"),
         "time_display": r.get("card_time_display"), "match_url": r.get("match_url"),
         "match_id": r.get("fixture_id")}
        for r in _raw if r.get("card_observed")
    ]
card_keys = {(r["tournament"], r["team_a"], r["team_b"]) for r in card_rows}
card_by_id = {str(r["match_id"]): r for r in card_rows if r.get("match_id")}

API_SOURCE_NOTE = (
    "Official play.hotspawn.com backend JSON, embedded in the lobby's public HTML "
    "(ng-state). Reference captured 2026-10-13T18:25:09Z."
)


def parse(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00")) if t else None


def permalink_from_card(fid):
    r = card_by_id.get(str(fid))
    return r.get("match_url") if r else None


# ---------------- CS2 full ----------------
cs2_api = [r for r in API_ROWS if r["sport"] == "cs2"]
cs2_out = []
for r in cs2_api:
    start = parse(r["scheduled_start_time"])
    past = bool(start and start < NOW and r["status"] == "scheduled")
    started = r["status"] == "started"
    row = OrderedDict()
    row["fixture_id"] = r["fixture_id"]
    row["game"] = "CS2"
    row["competition"] = r["competition_name"]
    row["team_a"] = r["team_a"]
    row["team_b"] = r["team_b"]
    row["scheduled_start_time_utc"] = r["scheduled_start_time"]
    row["lock_time_utc"] = r["lock_time"]
    row["status"] = r["status"]
    row["tier"] = r["tier"]
    row["stage"] = r["stage"]
    row["base_points"] = r["base_points"]
    row["offered_points"] = r["offered_points"]
    row["past_lock_not_pickable"] = past
    card = card_keys and next(
        (c for c in card_rows if (c["tournament"], c["team_a"], c["team_b"]) == (r["competition_name"], r["team_a"], r["team_b"])),
        None,
    )
    row["card_observed"] = bool(card)
    row["card_time_display"] = card["time_display"] if card else None
    row["match_url"] = permalink_from_card(r["fixture_id"]) or (card.get("match_url") if card else None)
    row["source_url"] = API_URL
    row["pick_pct_note"] = "Hotspawn crowd pick % (if shown on card) is FORBIDDEN as a probability; excluded."
    cs2_out.append(row)

cs2_out.sort(key=lambda x: (x["scheduled_start_time_utc"] or ""))
past_rows = [r for r in cs2_out if r["past_lock_not_pickable"]]
future_rows = [r for r in cs2_out if not r["past_lock_not_pickable"] and r["status"] == "scheduled"]

cs2_doc = {
    "game": "CS2",
    "generated_at_utc": "2026-10-13T19:00:00Z",
    "api_snapshot_at_utc": api["generated_at_utc"],
    "source_api": API_URL,
    "source_page": "https://play.hotspawn.com/cs2-pickems",
    "note": (
        "Complete CS2 pick'em inventory from the official play API, cross-checked row-by-row against "
        "this session's lobby card renders (30 cards across two replica states: 85-count and 91-count). "
        "7/7 spot checks matched exactly on teams, UTC time, tier, status. "
        "past_lock_not_pickable=true rows are counted by the lobby tournament filters but never rendered "
        "as cards (their locks are in the past and www.hotspawn.com shows those tournaments finished)."
    ),
    "counts": {
        "api_rows": len(cs2_out),
        "scheduled_future_pickable": len(future_rows),
        "scheduled_past_lock_flagged": len(past_rows),
        "started": sum(1 for r in cs2_out if r["status"] == "started"),
        "cards_observed": sum(1 for r in cs2_out if r["card_observed"]),
    },
    "lobby_snapshots": (cs2_old.get("meta") or {}).get("replica_snapshots") or cs2_old.get("lobby_snapshots"),
    "matches": cs2_out,
}
(ROOT / "data" / "cs2_matches.json").write_text(json.dumps(cs2_doc, indent=2, ensure_ascii=False) + "\n")
print(f"CS2: {len(cs2_out)} rows | future {len(future_rows)} | past-lock {len(past_rows)} | cards {cs2_doc['counts']['cards_observed']}")

# ---------------- flags rewrite ----------------
comp_past = Counter(r["competition"] for r in past_rows)
# dates/status evidence per tournament (observed this session on www pages)
evidence = {
    "CCT Europe 2026 Challengers #4": ("2026-06-27 – 2026-07-05", "Finished; Live & Upcoming empty", "https://www.hotspawn.com/counter-strike/tournament/cct-europe-2026-challengers-4"),
    "CCT South America 2026 Series #3": ("2026-07 (ended 2026-07-09)", "Finished; sample fixture 186091 Ended Jul 9", "https://www.hotspawn.com/counter-strike/tournament/cct-south-america-2026-series-3"),
    "DACH CS Masters Season 5": (None, "No www tournament page/fixtures exist (WP search: seasons 1-4 only)", "https://www.hotspawn.com/wp-json/wp/v2/tournament?search=DACH"),
    "DraculaN Season 7": ("2026-06-23 – 2026-06-28", "Finished (Bucharest); Live & Upcoming empty", "https://www.hotspawn.com/counter-strike/tournament/draculan-season-7"),
    "European Pro League Series 8": ("2026-07-06 – 2026-07-24", "Past dates; rows still status=scheduled with July times", "https://www.hotspawn.com/counter-strike/tournament/european-pro-league-series-8"),
    "European Pro League Series 8 Play-In": ("2026-07", "24 play-in fixtures in WP (1052743-1052764), all past", "https://www.hotspawn.com/counter-strike/tournament/european-pro-league-series-8-play-in"),
    "LG UltraGear Tournament 2026": ("2026-06-25 – 2026-06-26", "Finished (Almaty); Live & Upcoming empty", "https://www.hotspawn.com/counter-strike/tournament/lg-ultragear-tournament-2026"),
    "Rainhas do Clutch 2026": ("2026-06-23 – 2026-06-26", "Finished (Rio); Live & Upcoming empty", "https://www.hotspawn.com/counter-strike/tournament/rainhas-do-clutch-2026"),
    "Svenska CS-Ligan 2026": ("finished 2026-06-27", "Finished; sample fixture 183709 Ended Jun 27", "https://www.hotspawn.com/counter-strike/tournament/svenska-cs-ligan-2026"),
    "Thunderpick World Championship 2026: South American Series #1": ("2026-06-24 – 2026-06-28", "Finished; Live & Upcoming empty", "https://www.hotspawn.com/counter-strike/tournament/thunderpick-world-championship-2026-south-american-series-1"),
    "Urban Riga Open #5": ("2026-06-28 – 2026-06-29", "Finished; 18 June fixtures; lobby team counts diverge from June set", "https://www.hotspawn.com/counter-strike/tournament/urban-riga-open-5"),
}
flags_doc = {
    "generated_at_utc": "2026-10-13T19:00:00Z",
    "game": "CS2",
    "status": "ROWS RESOLVED from official API snapshot; irregularity REMAINS FLAGGED",
    "rule": "Values below come from the official play API (source_url per row); nothing inferred. Hotspawn crowd pick % excluded from any probability use.",
    "irregularity": (
        "The lobby tournament filters COUNT these 59 matches (lock times in June/July 2026), but they "
        "are never rendered as pickable cards, and www.hotspawn.com shows the corresponding tournaments "
        "finished. They are status=scheduled rows with past start times — counted, unplayable. "
        "Live count changes observed this session (86->85 when a match started; 85->91->85 replica "
        "divergence) show the feed is dynamic while these rows never resolve."
    ),
    "entries": [],
    "totals": {"past_lock_rows": len(past_rows), "tournaments": len(comp_past)},
}
for comp, n in sorted(comp_past.items(), key=lambda x: -x[1]):
    dates, state, url = evidence.get(comp, (None, None, None))
    rows = [r for r in past_rows if r["competition"] == comp]
    flags_doc["entries"].append(OrderedDict([
        ("tournament", comp),
        ("lobby_count", n),
        ("www_dates", dates),
        ("www_state", state),
        ("www_source_url", url),
        ("rows", [OrderedDict([
            ("fixture_id", r["fixture_id"]),
            ("team_a", r["team_a"]),
            ("team_b", r["team_b"]),
            ("scheduled_start_time_utc", r["scheduled_start_time_utc"]),
            ("status", r["status"]),
            ("pickable", False),
            ("source_url", API_URL),
            ("match_url", r["match_url"]),
        ]) for r in rows]),
    ]))
(ROOT / "data" / "cs2_unrendered_flags.json").write_text(json.dumps(flags_doc, indent=2, ensure_ascii=False) + "\n")
print(f"flags: {len(flags_doc['entries'])} tournaments, {sum(e['lobby_count'] for e in flags_doc['entries'])} rows")

# ---------------- LoL full ----------------
lol_api = [r for r in API_ROWS if r["sport"] == "lol"]
LOBBY_COUNTS = {  # exact filter labels from /lol-pickems render 2026-10-13T18:48Z (25 comps, sums to 294)
    "total_reported": 294, "this_week_first_seen": 126, "this_week_at_1848z": 131,
    "tiers": {"A": 4, "C": 76, "S": 4, "WAITING FOR INFORMATION": 210},
    "tournaments": {
        "Arabian League 2nd Division 2026 Summer": 18,
        "Benelux Ascend Series 2026 Summer Playoffs": 1,
        "Benelux Ascend Series 2026 Summer Split": 2,
        "Benelux Ascend Series 2027 Winter Promotion": 6,
        "Benelux Ascend Series Rising 2026 Summer Playoffs": 5,
        "Demacia Cup Global Invitational 2026": 2,
        "EM 2026 Summer Main Event": 2,
        "FPL 2026 Summer Playoffs": 1,
        "Hitpoint 2nd Div Challengers 2026 Summer Playoffs": 1,
        "Icelandic Esports League 2026 Autumn": 12,
        "Komplettligaen 2026 Autumn": 22,
        "LCP Wildcard 2026 Playoffs": 1,
        "Legends Academy powered by Żabka Season 3 Playoffs": 1,
        "LGC Rising 2026 Playoffs": 2,
        "LigaGG CELOL A 2026 Split 2": 13,
        "LigaGG CELOL B 2026 Split 2": 2,
        "LIT 2027 Winter Promotion": 1,
        "MängudeÖÖ 2026": 1,
        "POP Esports Masters Season 7": 1,
        "PRM 2nd Division 26-27 Fall": 52,
        "PRM 3rd Division 26-27 Fall": 69,
        "RIVALS LEAGUE Season 2": 32,
        "Superstrike League 2026": 10,
        "Tunisian Super League 2026": 35,
        "Worlds 2026 Play-In": 2,
    },
    "note": "Exact labels transcribed from the lobby filter bar; sum = 294.",
}
LOL_OBSERVED_CARDS = {  # fixture ids seen on /lol-pickems cards (chunk0 renders, 18:02Z + 18:48Z)
    "1076650", "1079335", "1080902", "1075725", "1076570", "1071203", "1075708",
}
lol_out = []
for r in lol_api:
    start = parse(r["scheduled_start_time"])
    row = OrderedDict()
    row["fixture_id"] = r["fixture_id"]
    row["game"] = "LoL"
    row["competition"] = r["competition_name"]
    row["team_a"] = r["team_a"]
    row["team_b"] = r["team_b"]
    row["scheduled_start_time_utc"] = r["scheduled_start_time"]
    row["lock_time_utc"] = r["lock_time"]
    row["status"] = r["status"]
    row["tier"] = r["tier"]
    row["stage"] = r["stage"]
    row["base_points"] = r["base_points"]
    row["offered_points"] = r["offered_points"]
    row["past_lock_not_pickable"] = bool(start and start < NOW and r["status"] == "scheduled")
    row["card_observed"] = r["fixture_id"] in LOL_OBSERVED_CARDS
    row["source_url"] = API_URL
    lol_out.append(row)
lol_out.sort(key=lambda x: (x["scheduled_start_time_utc"] or ""))
sched = [r for r in lol_out if r["status"] == "scheduled"]
canc = [r for r in lol_out if r["status"] == "cancelled"]
fut = [r for r in sched if not r["past_lock_not_pickable"]]
past = [r for r in sched if r["past_lock_not_pickable"]]
api_by_comp_total = Counter(r["competition"] for r in sched)
recon = []
for t, c in LOBBY_COUNTS["tournaments"].items():
    a = api_by_comp_total_total = api_by_comp_total.get(t, 0)
    recon.append({"tournament": t, "lobby_count": c, "api_scheduled": a, "delta": a - c})
unlisted = {k: v for k, v in sorted(api_by_comp_total.items()) if k not in LOBBY_COUNTS["tournaments"]}
lol_doc = {
    "game": "LoL",
    "generated_at_utc": "2026-10-13T19:00:00Z",
    "api_snapshot_at_utc": api["generated_at_utc"],
    "source_api": API_URL,
    "source_page": "https://play.hotspawn.com/lol-pickems",
    "note": "Complete LoL pick'em inventory from the official play API. Lobby filters reported 294 at 2026-10-13 ~18:0x UTC; API snapshot (18:25Z) has 298 scheduled + 16 cancelled — snapshot skew and cancelled rows documented, not silently merged.",
    "lobby_reported": LOBBY_COUNTS,
    "counts": {"api_rows": len(lol_out), "scheduled": len(sched), "scheduled_future": len(fut),
               "scheduled_past_lock": len(past), "cancelled": len(canc),
               "cards_observed": sum(1 for r in lol_out if r["card_observed"])},
    "reconciliation": {"per_tournament": recon, "api_comps_not_in_lobby_counts": unlisted},
    "matches": lol_out,
}
(ROOT / "data" / "lol_matches.json").write_text(json.dumps(lol_doc, indent=2, ensure_ascii=False) + "\n")
print(f"LoL: {len(lol_out)} rows | sched {len(sched)} (future {len(fut)}, past {len(past)}) | cancelled {len(canc)}")
print("LoL reconciliation deltas:", [(r['tournament'], r['delta']) for r in recon if r['delta']])
print("API comps not in lobby counts:", unlisted)
