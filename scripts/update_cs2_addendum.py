#!/usr/bin/env python3
"""Addendum for data/cs2_matches.json.

- Adds 4 card rows observed only in the '91-count' replica snapshot of
  play.hotspawn.com/cs2-pickems (2026-10-13T18:31Z) but absent from the
  '85-count' snapshot: CCT South America 2026 Series #7 (2) and
  CCT Europe 2026 Series #12 Play-In (2 of its 4 matches).
- Records both replica snapshots in meta.
- Writes data/cs2_unrendered_flags.json: tournament-level records for the
  59 lobby-counted matches whose cards are never rendered (lock times in
  the past on www) plus the 2 unobserved EU #12 Play-In rows. No row-level
  values are inferred: teams/times stay blank and are flagged unverified
  per project verification rules.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "cs2_matches.json"
FLAGS = ROOT / "data" / "cs2_unrendered_flags.json"

d = json.loads(DATA.read_text())
existing = {m["match_id"] for m in d["matches"]}

new_rows = [
    # Observed only in the 91-count replica render of play.hotspawn.com/cs2-pickems
    # at 2026-10-13T18:31Z. Times are lobby-displayed America/New_York converted
    # to UTC. No www match permalink was shown on the card; source link points
    # at the official tournament page instead.
    dict(match_id=None, game="CS2", team_a="Grêmio", team_b="LOS NINOS",
         tournament="CCT South America 2026 Series #7",
         time_display="2026-10-13 15:00 (America/New_York)",
         time_utc="2026-10-13 19:00", tier="C", points=2,
         source_url="https://play.hotspawn.com/cs2-pickems",
         match_url="https://www.hotspawn.com/counter-strike/tournament/cct-south-america-2026-series-7",
         note="Observed only in 91-count replica snapshot 2026-10-13T18:31Z; card showed no www match permalink."),
    dict(match_id=None, game="CS2", team_a="SUKEBAN", team_b="your end",
         tournament="CCT South America 2026 Series #7",
         time_display="2026-10-13 18:00 (America/New_York)",
         time_utc="2026-10-13 22:00", tier="C", points=2,
         source_url="https://play.hotspawn.com/cs2-pickems",
         match_url="https://www.hotspawn.com/counter-strike/tournament/cct-south-america-2026-series-7",
         note="Observed only in 91-count replica snapshot 2026-10-13T18:31Z; card showed no www match permalink."),
    dict(match_id=None, game="CS2", team_a="Enjoy", team_b="B8 Academy",
         tournament="CCT Europe 2026 Series #12 Play-In",
         time_display="2026-10-14 04:00 (America/New_York)",
         time_utc="2026-10-14 08:00", tier="C", points=2,
         source_url="https://play.hotspawn.com/cs2-pickems",
         match_url="https://www.hotspawn.com/counter-strike/tournament/cct-europe-2026-series-12-play-in",
         note="Observed only in 91-count replica snapshot 2026-10-13T18:31Z; card showed no www match permalink."),
    dict(match_id=None, game="CS2", team_a="Banda chuya", team_b="6666",
         tournament="CCT Europe 2026 Series #12 Play-In",
         time_display="2026-10-14 07:00 (America/New_York)",
         time_utc="2026-10-14 11:00", tier="C", points=2,
         source_url="https://play.hotspawn.com/cs2-pickems",
         match_url="https://www.hotspawn.com/counter-strike/tournament/cct-europe-2026-series-12-play-in",
         note="Observed only in 91-count replica snapshot 2026-10-13T18:31Z; card showed no www match permalink."),
]

added = 0
for r in new_rows:
    if r["team_a"] not in {m["team_a"] for m in d["matches"]} or \
       r["team_b"] not in {m["team_b"] for m in d["matches"]} or True:
        key = (r["tournament"], r["team_a"], r["team_b"])
        if not any((m["tournament"], m["team_a"], m["team_b"]) == key for m in d["matches"]):
            d["matches"].append(r)
            added += 1

d["matches"].sort(key=lambda m: m["time_utc"])

d["meta"]["replica_snapshots"] = [
    {"at_utc": "2026-10-13T17:51:00Z", "total_count": 86, "this_week": "60",
     "note": "First observation on /lobby; count decremented to 85 within the session (dynamic ingest)."},
    {"at_utc": "2026-10-13T18:00:00Z", "total_count": 85, "this_week": "60",
     "tiers": {"S": 4, "B": 26, "C": 55}},
    {"at_utc": "2026-10-13T18:31:00Z", "total_count": 91, "this_week": "68",
     "tiers": {"S": 4, "B": 26, "C": 61},
     "note": "Second replica state seen within one minute: +CCT South America 2026 Series #7 (2), +CCT Europe 2026 Series #12 Play-In (4). Front-end replicas serve divergent ingest states."},
    {"at_utc": "2026-10-13T18:34:00Z", "total_count": 85, "this_week": "68",
     "note": "85-count replica again; cards identical to the 26-row base set."},
]
d["meta"]["card_render_window"] = "Cards render only for locks up to ~Oct 16 14:00 America/New_York (≈72h). Beyond-window and past-lock matches are counted in filters but never rendered."
d["meta"]["accounting_85_state"] = {
    "future_rendered": 26,
    "past_lock_counted_not_rendered": 59,
    "sum_check": "26 + 59 = 85",
}
d["meta"]["accounting_91_state"] = {
    "future_observed": 30,
    "future_counted_not_rendered": 2,
    "past_lock_counted_not_rendered": 59,
    "sum_check": "30 + 2 + 59 = 91",
}
d["meta"]["updated_at_utc"] = "2026-10-13T18:40:00Z"

DATA.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
print(f"matches now: {len(d['matches'])} (+{added} added)")

flags = {
    "generated_at_utc": "2026-10-13T18:40:00Z",
    "game": "CS2",
    "rule": "Unconfirmable match-level values are left blank and flagged; nothing is inferred or filled.",
    "explanation": (
        "play.hotspawn.com counts these matches in the lobby filters (85-count state) but never renders "
        "their cards, because their lock times are in the past. www.hotspawn.com shows the corresponding "
        "tournaments as finished (Live & Upcoming: no matches) or with past dates only. The exact per-match "
        "subset held by the pick'em DB cannot be observed from any public endpoint (card render window, "
        "play API probing, permalink endpoint all failed), so row-level teams/times are left BLANK."
    ),
    "entries": [
        {"tournament": "CCT Europe 2026 Challengers #4", "lobby_count": 8,
         "www_dates": "2026-06-27 – 2026-07-05", "www_state": "Finished; Live & Upcoming shows no matches",
         "source_url": "https://www.hotspawn.com/counter-strike/tournament/cct-europe-2026-challengers-4",
         "sample_evidence": "Fixture 185489 (external 1079766 range) status Ended, Jul 5 2026; page lists 9 days of finished matches only.",
         "rows": [{"match": None, "time_utc": None, "source_url": None} for _ in range(8)]},
        {"tournament": "CCT South America 2026 Series #3", "lobby_count": 8,
         "www_dates": "finished July 2026", "www_state": "Finished; sample fixture 186091 Ended 2026-07-09",
         "source_url": "https://www.hotspawn.com/counter-strike/tournament/cct-south-america-2026-series-3",
         "rows": [{"match": None, "time_utc": None, "source_url": None} for _ in range(8)]},
        {"tournament": "DACH CS Masters Season 5", "lobby_count": 1,
         "www_dates": None, "www_state": "No tournament page or fixtures found under this name (WP search returns DACH seasons 1–4 only)",
         "source_url": "https://www.hotspawn.com/wp-json/wp/v2/tournament?search=DACH",
         "rows": [{"match": None, "time_utc": None, "source_url": None}]},
        {"tournament": "DraculaN Season 7", "lobby_count": 6,
         "www_dates": "2026-06-23 – 2026-06-28", "www_state": "Finished (Bucharest); Live & Upcoming shows no matches",
         "source_url": "https://www.hotspawn.com/counter-strike/tournament/draculan-season-7",
         "rows": [{"match": None, "time_utc": None, "source_url": None} for _ in range(6)]},
        {"tournament": "European Pro League Series 8", "lobby_count": 1,
         "www_dates": "2026-07-06 – 2026-07-24", "www_state": "Past dates; remaining rows still show status UPCOMING with July times",
         "source_url": "https://www.hotspawn.com/counter-strike/tournament/european-pro-league-series-8",
         "rows": [{"match": None, "time_utc": None, "source_url": None}]},
        {"tournament": "European Pro League Series 8 Play-In", "lobby_count": 6,
         "www_dates": "July 2026", "www_state": "24 play-in fixtures found in WP (external ids 1052743–1052764), all past; exact pick'em subset unobservable",
         "source_url": "https://www.hotspawn.com/wp-json/wp/v2/fixtures?search=European%20Pro%20League%20Series%208",
         "rows": [{"match": None, "time_utc": None, "source_url": None} for _ in range(6)]},
        {"tournament": "LG UltraGear Tournament 2026", "lobby_count": 1,
         "www_dates": "2026-06-25 – 2026-06-26", "www_state": "Finished (Almaty); Live & Upcoming shows no matches",
         "source_url": "https://www.hotspawn.com/counter-strike/tournament/lg-ultragear-tournament-2026",
         "rows": [{"match": None, "time_utc": None, "source_url": None}]},
        {"tournament": "Rainhas do Clutch 2026", "lobby_count": 2,
         "www_dates": "2026-06-23 – 2026-06-26", "www_state": "Finished (Rio de Janeiro); 4 finished fixtures exist (1053146, 1052686, 1051505, 1051504) — pick'em subset of 2 unobservable",
         "source_url": "https://www.hotspawn.com/counter-strike/tournament/rainhas-do-clutch-2026",
         "rows": [{"match": None, "time_utc": None, "source_url": None} for _ in range(2)]},
        {"tournament": "Svenska CS-Ligan 2026", "lobby_count": 6,
         "www_dates": "finished 2026-06-27", "www_state": "Finished; sample fixture 183709 Ended Jun 27; 16+ season fixtures in WP",
         "source_url": "https://www.hotspawn.com/counter-strike/tournament/svenska-cs-ligan-2026",
         "rows": [{"match": None, "time_utc": None, "source_url": None} for _ in range(6)]},
        {"tournament": "Thunderpick World Championship 2026: South American Series #1", "lobby_count": 8,
         "www_dates": "2026-06-24 – 2026-06-28", "www_state": "Finished; Live & Upcoming shows no matches; ~15 finished fixtures on www",
         "source_url": "https://www.hotspawn.com/counter-strike/tournament/thunderpick-world-championship-2026-south-american-series-1",
         "rows": [{"match": None, "time_utc": None, "source_url": None} for _ in range(8)]},
        {"tournament": "Urban Riga Open #5", "lobby_count": 12,
         "www_dates": "2026-06-28 – 2026-06-29", "www_state": "Finished; 18 finished fixtures (1053431–1053471); lobby team counts (e.g. SINQU REHTI 3) do not match the June set (7 appearances), so play's DB diverges from www",
         "source_url": "https://www.hotspawn.com/counter-strike/tournament/urban-riga-open-5",
         "rows": [{"match": None, "time_utc": None, "source_url": None} for _ in range(12)]},
        {"tournament": "CCT Europe 2026 Series #12 Play-In", "lobby_count": 4,
         "observed_rows": 2,
         "www_dates": "2026-10-14 – 2026-10-19", "www_state": "Current tournament; 2 of 4 pick'em cards observed (Enjoy vs B8 Academy, Banda chuya vs 6666); remaining 2 cards fall outside the render window and www shows no times yet (groups B/D: Ryvex, mellren, Privateer without fixtures)",
         "source_url": "https://www.hotspawn.com/counter-strike/tournament/cct-europe-2026-series-12-play-in",
         "rows": [{"match": None, "time_utc": None, "source_url": None} for _ in range(2)]},
    ],
    "totals": {"lobby_state_85": {"rendered": 26, "flagged": 59, "sum": 85},
               "lobby_state_91": {"rendered": 30, "flagged": 61, "sum": 91}},
}
FLAGS.write_text(json.dumps(flags, indent=2, ensure_ascii=False) + "\n")
n = sum(len(e["rows"]) for e in flags["entries"])
print(f"flags written: {len(flags['entries'])} tournaments, {n} blank rows")
