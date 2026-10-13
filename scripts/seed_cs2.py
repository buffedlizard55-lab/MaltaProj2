#!/usr/bin/env python3
"""Seed CS2 pick'em match data extracted from play.hotspawn.com/cs2-pickems
lobby render (fetched 2026-10-13 17:51-18:00 UTC).
Lobby displays times in America/New_York (EDT = UTC-4 on these dates);
UTC values below = display + 4h, cross-checked against www.hotspawn.com match
pages (which show UTC) for 1081076 (21:00 UTC) and lock countdowns.
Tier/points exactly as lobby card shows.
"""
import json, os

# match_id, team_a, team_b, tournament, display_time (lobby local EDT), utc, tier, points
ROWS = [
 (1081076, "ex-Keyd Stars", "Galorys", "ESL Challenger League Season 52: South America - Cup #3", "2026-10-13 17:00", "2026-10-13 21:00", "B", 3),
 (1079546, "Zomblers", "Overtake Sector", "ESL Challenger League Season 52: North America - Cup #3", "2026-10-13 21:00", "2026-10-14 01:00", "B", 3),
 (1079621, "Gothic", "Lavked", "CCT Europe 2026 Series #11", "2026-10-14 04:00", "2026-10-14 08:00", "B", 3),
 (1080176, "9z", "Aurora", "Thunderpick World Championship 2026", "2026-10-14 04:30", "2026-10-14 08:30", "S", 7),
 (1079438, "Astralis", "Sashi", "Stake Pulse Beat III", "2026-10-14 06:00", "2026-10-14 10:00", "B", 3),
 (1079439, "HOTU", "Fnatic", "Stake Pulse Beat III", "2026-10-14 06:00", "2026-10-14 10:00", "B", 3),
 (1079622, "ex-RUSTEC", "mellren", "CCT Europe 2026 Series #11", "2026-10-14 07:00", "2026-10-14 11:00", "B", 3),
 (1080177, "Falcons", "Ninjas in Pyjamas", "Thunderpick World Championship 2026", "2026-10-14 07:00", "2026-10-14 11:00", "S", 7),
 (1080178, "Legacy", "PARIVISION", "Thunderpick World Championship 2026", "2026-10-14 09:30", "2026-10-14 13:30", "S", 7),
 (1079623, "G2 Ares", "The Last Resort", "CCT Europe 2026 Series #11", "2026-10-14 10:00", "2026-10-14 14:00", "B", 3),
 (1080179, "FURIA", "BetBoom", "Thunderpick World Championship 2026", "2026-10-14 12:00", "2026-10-14 16:00", "S", 7),
 (1079624, "FORZE Reload", "LFO 10", "CCT Europe 2026 Series #11", "2026-10-14 13:00", "2026-10-14 17:00", "B", 3),
 (1080279, "WROTBERRY", "EAC", "Elisa BreakOut Series #2", "2026-10-15 04:00", "2026-10-15 08:00", "C", 2),
 (1079440, "MIBR", "BC.Game", "Stake Pulse Beat III", "2026-10-15 06:00", "2026-10-15 10:00", "B", 3),
 (1079442, "Heroic", "Envy", "Stake Pulse Beat III", "2026-10-15 06:00", "2026-10-15 10:00", "B", 3),
 (1080280, "ENCE", "BOJONG", "Elisa BreakOut Series #2", "2026-10-15 06:00", "2026-10-15 10:00", "C", 2),
 (1080281, "WROTBERRY", "ENCE", "Elisa BreakOut Series #2", "2026-10-15 08:00", "2026-10-15 12:00", "C", 2),
 (1080282, "EAC", "BOJONG", "Elisa BreakOut Series #2", "2026-10-15 10:00", "2026-10-15 14:00", "C", 2),
 (1080283, "WROTBERRY", "BOJONG", "Elisa BreakOut Series #2", "2026-10-15 12:00", "2026-10-15 16:00", "C", 2),
 (1080284, "EAC", "ENCE", "Elisa BreakOut Series #2", "2026-10-15 14:00", "2026-10-15 18:00", "C", 2),
 (1080285, "Voca", "Phantom", "Elisa BreakOut Series #2", "2026-10-16 04:00", "2026-10-16 08:00", "C", 2),
 (1080286, "HAVU", "RoundsGG", "Elisa BreakOut Series #2", "2026-10-16 06:00", "2026-10-16 10:00", "C", 2),
 (1080287, "Voca", "HAVU", "Elisa BreakOut Series #2", "2026-10-16 08:00", "2026-10-16 12:00", "C", 2),
 (1080288, "Phantom", "RoundsGG", "Elisa BreakOut Series #2", "2026-10-16 10:00", "2026-10-16 14:00", "C", 2),
 (1080289, "RoundsGG", "Voca", "Elisa BreakOut Series #2", "2026-10-16 12:00", "2026-10-16 16:00", "C", 2),
 (1080290, "Phantom", "HAVU", "Elisa BreakOut Series #2", "2026-10-16 14:00", "2026-10-16 18:00", "C", 2),
]

def slugify(a, b, tourney, mid):
    import re
    def s(x):
        x = x.lower().replace("&", "-and-")
        x = re.sub(r"[^a-z0-9]+", "-", x).strip("-")
        return x
    # hotspawn slug pattern: <teamA>-vs-<teamB>-<tourney-slug>-<id>
    # NOTE: slugs on cards are authoritative; re-derive only as fallback.
    t = tourney.lower()
    t = t.replace(":", "").replace("–", "-")
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return f"{s(a)}-vs-{s(b)}-{t}-{mid}"

def main():
    rows = []
    for mid, a, b, tourney, disp, utc, tier, pts in ROWS:
        rows.append({
            "match_id": mid,
            "game": "CS2",
            "team_a": a,
            "team_b": b,
            "tournament": tourney,
            "time_display": disp + " (America/New_York)",
            "time_utc": utc,
            "tier": tier,
            "points": pts,
            "source_url": f"https://play.hotspawn.com/cs2-pickems",
            "match_url": None,  # filled from lobby links below
        })
    # authoritative match URLs from lobby cards
    urls = {
      1081076: "https://www.hotspawn.com/matches/ex-keyd-stars-vs-galorys-esl-challenger-league-season-52-south-america-cup-3-1081076",
      1079546: "https://www.hotspawn.com/matches/zomblers-vs-overtake-sector-esl-challenger-league-season-52-north-america-cup-3-1079546",
      1079621: "https://www.hotspawn.com/matches/gothic-vs-lavked-cct-europe-2026-series-11-1079621",
      1080176: "https://www.hotspawn.com/matches/9z-vs-aurora-thunderpick-world-championship-2026-1080176",
      1079438: "https://www.hotspawn.com/matches/astralis-vs-sashi-stake-pulse-beat-iii-1079438",
      1079439: "https://www.hotspawn.com/matches/hotu-vs-fnatic-stake-pulse-beat-iii-1079439",
      1079622: "https://www.hotspawn.com/matches/ex-rustec-vs-mellren-cct-europe-2026-series-11-1079622",
      1080177: "https://www.hotspawn.com/matches/falcons-vs-ninjas-in-pyjamas-thunderpick-world-championship-2026-1080177",
      1080178: "https://www.hotspawn.com/matches/legacy-vs-parivision-thunderpick-world-championship-2026-1080178",
      1079623: "https://www.hotspawn.com/matches/g2-ares-vs-the-last-resort-cct-europe-2026-series-11-1079623",
      1080179: "https://www.hotspawn.com/matches/furia-vs-betboom-thunderpick-world-championship-2026-1080179",
      1079624: "https://www.hotspawn.com/matches/forze-reload-vs-lfo-10-cct-europe-2026-series-11-1079624",
      1080279: "https://www.hotspawn.com/matches/wrotberry-vs-eac-elisa-breakout-series-2-1080279",
      1079440: "https://www.hotspawn.com/matches/mibr-vs-bc-game-stake-pulse-beat-iii-1079440",
      1079442: "https://www.hotspawn.com/matches/heroic-vs-envy-stake-pulse-beat-iii-1079442",
      1080280: "https://www.hotspawn.com/matches/ence-vs-bojong-elisa-breakout-series-2-1080280",
      1080281: "https://www.hotspawn.com/matches/wrotberry-vs-ence-elisa-breakout-series-2-1080281",
      1080282: "https://www.hotspawn.com/matches/eac-vs-bojong-elisa-breakout-series-2-1080282",
      1080283: "https://www.hotspawn.com/matches/wrotberry-vs-bojong-elisa-breakout-series-2-1080283",
      1080284: "https://www.hotspawn.com/matches/eac-vs-ence-elisa-breakout-series-2-1080284",
      1080285: "https://www.hotspawn.com/matches/voca-vs-phantom-elisa-breakout-series-2-1080285",
      1080286: "https://www.hotspawn.com/matches/havu-vs-roundsgg-elisa-breakout-series-2-1080286",
      1080287: "https://www.hotspawn.com/matches/voca-vs-havu-elisa-breakout-series-2-1080287",
      1080288: "https://www.hotspawn.com/matches/phantom-vs-roundsgg-elisa-breakout-series-2-1080288",
      1080289: "https://www.hotspawn.com/matches/roundsgg-vs-voca-elisa-breakout-series-2-1080289",
      1080290: "https://www.hotspawn.com/matches/phantom-vs-havu-elisa-breakout-series-2-1080290",
    }
    for r in rows:
        r["match_url"] = urls[r["match_id"]]

    meta = {
      "fetched_at_utc": "2026-10-13T17:51:00Z / 2026-10-13T18:00:00Z",
      "source": "https://play.hotspawn.com/cs2-pickems (lobby SSR render)",
      "lobby_counts": {
        "total": 85,
        "tiers": {"S": 4, "B": 26, "C": 55},
        "tournaments": {
          "CCT Europe 2026 Challengers #4": 8,
          "CCT Europe 2026 Series #11": 4,
          "CCT South America 2026 Series #3": 8,
          "DACH CS Masters Season 5": 1,
          "DraculaN Season 7": 6,
          "Elisa BreakOut Series #2": 12,
          "ESL Challenger League Season 52: North America - Cup #3": 1,
          "ESL Challenger League Season 52: South America - Cup #3": 1,
          "European Pro League Series 8": 1,
          "European Pro League Series 8 Play-In": 6,
          "LG UltraGear Tournament 2026": 1,
          "Rainhas do Clutch 2026": 2,
          "Stake Pulse Beat III": 4,
          "Svenska CS-Ligan 2026": 6,
          "Thunderpick World Championship 2026": 4,
          "Thunderpick World Championship 2026: South American Series #1": 8,
          "Urban Riga Open #5": 12,
        },
        "note": "Counts as rendered 2026-10-13 ~17:56 UTC; first render showed total 86 / CCT S11=5, later 85/4 (one match left the pool between renders) - flagged for review.",
      },
      "remaining_tournaments_needed": [
        "CCT Europe 2026 Challengers #4", "CCT South America 2026 Series #3",
        "DACH CS Masters Season 5", "DraculaN Season 7",
        "European Pro League Series 8", "European Pro League Series 8 Play-In",
        "LG UltraGear Tournament 2026", "Rainhas do Clutch 2026",
        "Svenska CS-Ligan 2026", "Thunderpick World Championship 2026: South American Series #1",
        "Urban Riga Open #5",
      ],
      "remaining_needed_count": 59,
    }
    os.makedirs("data", exist_ok=True)
    out = {"meta": meta, "matches": rows}
    with open("data/cs2_matches.json", "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"Wrote {len(rows)} CS2 rows")

if __name__ == "__main__":
    main()
