"""HotSpawn team name -> official-source team name resolutions (session c0e223d3).

Every entry below was read from an official source during this session. Each carries the exact URL
and a quote of what the source says, so a reviewer can re-check it by clicking. Nothing here is
guessed: an entry is only `confirmed` when two independent official sources (Valve's published
regional standings file and HLTV's own event/team pages) agree on the same team through the same
event, the same opponents and the same kickoff offsets.

Session scope: `scripts/c0e223d3/**`, `data/c0e223d3/**`, `summary/**`.
"""

# --------------------------------------------------------------------------------------------
# Official source URLs used as evidence (all read during this session, 2026-10-14)
# --------------------------------------------------------------------------------------------
VALVE_FILE_PATH = "live/2026/standings_global_2026_10_05.md"
VALVE_FILE_PAGE = (
    "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/"
    "live/2026/standings_global_2026_10_05.md"
)
VALVE_FILE_API = (
    "https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings/contents/"
    "live/2026/standings_global_2026_10_05.md"
)
VALVE_REPO_LIVE = "https://github.com/ValveSoftware/counter-strike_regional_standings/tree/main/live/2026"

HLTV_ELISA_EVENT = "https://www.hltv.org/events/9332/elisa-breakout-series-2"
HLTV_ELISA_MATCHES = "https://www.hltv.org/events/9332/matches"
HLTV_WBT_TEAM = "https://www.hltv.org/team/13683/wbt"
HLTV_CCT_EVENT = "https://www.hltv.org/events/9442/cct-2026-europe-series-11"
HLTV_FORZE_LFO10 = (
    "https://www.hltv.org/betting/analytics/2399301/forze-reload-vs-lfo-10-cct-2026-europe-series-11"
)
HLTV_WBT_EAC = "https://www.hltv.org/betting/analytics/2399418/wbt-vs-eac-elisa-breakout-series-2"

LIQUIPEDIA_ELISA = "https://liquipedia.net/counterstrike/Elisa/BreakOut_Series/2"
MELBET_ESPROTS = "https://melbet.com/en/line/esports"
BO3GG_WROTBERRY = "https://bo3.gg/teams/wrotberry"
EGAMERSWORLD_WROTBERRY = "https://egamersworld.com/counterstrike/team/wrotberry-0I2cpR8LZA"
STRAFE_WROTBERRY = "https://www.strafe.com/team/wrotberry-cs-go-b4088f/"
DEVUA_WHITEBIT = "https://dev.ua/en/news/w-group-zapuskaie-whitebit-team-1783681756"

# When each source above was read (UTC), recorded so a reviewer can judge freshness.
READ_TIMES_UTC = {
    VALVE_FILE_PAGE: "2026-10-14T02:52Z",
    VALVE_REPO_LIVE: "2026-10-14T02:52Z",
    HLTV_ELISA_EVENT: "2026-10-14T02:47Z",
    HLTV_ELISA_MATCHES: "2026-10-14T02:47Z",
    HLTV_WBT_TEAM: "2026-10-14T02:52Z",
    HLTV_CCT_EVENT: "2026-10-14T02:56Z",
    HLTV_FORZE_LFO10: "2026-10-14T03:00Z",
    HLTV_WBT_EAC: "2026-10-14T02:47Z",
    LIQUIPEDIA_ELISA: "2026-10-14T02:44Z",
    MELBET_ESPROTS: "2026-10-14T02:45Z",
    BO3GG_WROTBERRY: "2026-10-14T02:44Z",
    EGAMERSWORLD_WROTBERRY: "2026-10-14T02:44Z",
    STRAFE_WROTBERRY: "2026-10-14T02:44Z",
    DEVUA_WHITEBIT: "2026-10-14T02:45Z",
    "https://play.hotspawn.com/lobby": "2026-10-14T02:42Z",
}

# --------------------------------------------------------------------------------------------
# Resolutions
# --------------------------------------------------------------------------------------------
# `valve_name` is the exact "Team Name" string in Valve's standings_global_2026_10_05.md.
RESOLUTIONS = [
    {
        "hotspawn_name": "WROTBERRY",
        "valve_name": "WBT",
        "also_known_as": ["WBT", "WhiteBIT Team"],
        "status": "confirmed",
        "affects_fixtures": ["1080279", "1080281", "1080283"],
        "affects_events": ["Elisa BreakOut Series #2"],
        "evidence": [
            {
                "source": "Valve regional standings (official repository)",
                "url": VALVE_FILE_PAGE,
                "quote": "standing 60, 1201 points, team 'WBT', roster 'DemQQ, Psycho, s4ltovsk1yy, Smash, tyr1k'",
            },
            {
                "source": "HLTV team page",
                "url": HLTV_WBT_TEAM,
                "quote": "Team 'WBT' (Ukraine), Valve ranking VRS #64, world ranking #109, "
                         "lineup Psycho / Smash / s4ltovsk1yy / DemQQ / tyr1k - identical to Valve's 'WBT' row",
            },
            {
                "source": "HLTV event overview (group draw and schedule)",
                "url": HLTV_ELISA_EVENT,
                "quote": "Group A = WBT, ENCE, EAC, BOJONG. HLTV lists 'WBT vs EAC' 15 Oct 04:00, "
                         "'WBT vs ENCE' 08:00, 'WBT vs BOJONG' 12:00 - the same three pairings and the "
                         "same kickoff offsets HotSpawn publishes as WROTBERRY vs EAC / ENCE / BOJONG "
                         "(08:00Z, 12:00Z, 16:00Z)",
            },
            {
                "source": "Melbet esports line feed",
                "url": MELBET_ESPROTS,
                "quote": "quotes 'WhiteBIT Team' against EA Copenhagen, ENCE and BOJONG in the same window",
            },
        ],
        "conflict": (
            "bo3.gg, egamersworld and strafe.com all publish a 'WROTBERRY' roster of "
            "fl1peR / svemyy / aRTYSAN / tired73 / lyoli. That five is Valve's 'WBT Academy' row "
            "(standing 130, 911 points), not the 'WBT' row that HotSpawn's schedule actually matches. "
            "HotSpawn's fixture list follows WBT, so WBT is used here; the naming conflict is flagged."
        ),
        "conflict_links": [BO3GG_WROTBERRY, EGAMERSWORLD_WROTBERRY, STRAFE_WROTBERRY, VALVE_FILE_PAGE],
    },
    {
        "hotspawn_name": "RoundsGG",
        "valve_name": "ROUNDS",
        "also_known_as": ["ROUNDS"],
        "status": "confirmed",
        "affects_fixtures": ["1080286", "1080288", "1080289"],
        "affects_events": ["Elisa BreakOut Series #2"],
        "evidence": [
            {
                "source": "Valve regional standings (official repository)",
                "url": VALVE_FILE_PAGE,
                "quote": "standing 310, 548 points, team 'ROUNDS', roster 'Kollo, Lapa, Monoxx, Tumppis, ykis'",
            },
            {
                "source": "HLTV event overview (group draw and schedule)",
                "url": HLTV_ELISA_EVENT,
                "quote": "Group B = Voca, Phantom, HAVU, ROUNDS. HLTV lists 'HAVU vs ROUNDS' 16 Oct 06:00, "
                         "'Phantom vs ROUNDS' 10:00, 'Voca vs ROUNDS' 12:00 - the same three pairings and "
                         "kickoff offsets HotSpawn publishes as HAVU/Phantom/Voca vs RoundsGG "
                         "(10:00Z, 14:00Z, 16:00Z)",
            },
            {
                "source": "HLTV event match list",
                "url": HLTV_ELISA_MATCHES,
                "quote": "per-match pages 2399425 havu-vs-rounds, 2399427 phantom-vs-rounds, "
                         "2399428 voca-vs-rounds - one for each HotSpawn RoundsGG fixture",
            },
        ],
        "conflict": None,
        "conflict_links": [],
    },
    {
        "hotspawn_name": "LFO 10",
        "valve_name": None,
        "also_known_as": [],
        "status": "unresolved",
        "affects_fixtures": ["1079624"],
        "affects_events": ["CCT Europe 2026 Series #11"],
        "evidence": [
            {
                "source": "Valve regional standings (official repository)",
                "url": VALVE_FILE_PAGE,
                "quote": "no team named 'LFO 10' in the latest published global standings file "
                         "(2026_10_05). Valve's file does list LFO 8 (279), LFO 7 (285) and LFO 9 (297), "
                         "so the numbering exists but 'LFO 10' is absent.",
            },
            {
                "source": "HLTV match analytics page",
                "url": HLTV_FORZE_LFO10,
                "quote": "'LFO 10 is worse ranked (Unranked)' - HLTV's own pre-match insight states "
                         "LFO 10 carries no ranking, while FORZE Reload is listed as #75",
            },
            {
                "source": "HLTV event overview (CCT 2026 Europe Series 11)",
                "url": HLTV_CCT_EVENT,
                "quote": "the group-seed column shows '#170 LFO 10', which contradicts the 'Unranked' "
                         "label on HLTV's own analytics page for the same match - flagged as an "
                         "HLTV-internal inconsistency, not used as a value",
            },
        ],
        "conflict": (
            "No official rating exists for LFO 10 in Valve's latest published standings file, and HLTV "
            "contradicts itself (unranked on the match analytics page, #170 on the event page). "
            "Per the project rule, the probability stays blank and flagged rather than being filled in."
        ),
        "conflict_links": [VALVE_FILE_PAGE, HLTV_FORZE_LFO10, HLTV_CCT_EVENT],
    },
]

# Teams whose Valve row is used directly (no alias needed) - recorded so the audit can show that
# the lookup is a name match against the official file, not a substitution.
DIRECT_MATCH_NOTE = (
    "EAC, ENCE, BOJONG, HAVU, Voca, Phantom and FORZE Reload appear verbatim in Valve's "
    "standings_global_2026_10_05.md, so their ratings are read straight from the file with no alias."
)


def by_hotspawn_name(name: str):
    """Return the resolution for a HotSpawn team name, or None when no alias is recorded."""
    target = (name or "").strip().casefold()
    for entry in RESOLUTIONS:
        if entry["hotspawn_name"].casefold() == target:
            return entry
    return None
