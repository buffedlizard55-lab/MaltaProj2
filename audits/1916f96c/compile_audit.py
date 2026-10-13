"""Compile the independently transcribed official-source observation, not a live feed.

Inputs below were read through fetch_page on 2026-10-13. Never derives factual
fields from URL slugs or dates. All probability fields are explicitly mathematical
transformations of sportsbook odds, not factual assertions about future results.
"""
import json
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOBBY = 'https://play.hotspawn.com/lobby'
BASE = 'https://www.hotspawn.com/matches/'
# Exact lobby text and exact observed View Match URL paths; no crowd picks retained.
CCT = 'CCT Europe 2026 Series #11'
TP = 'Thunderpick World Championship 2026'
PULSE = 'Stake Pulse Beat III'
ELISA = 'Elisa BreakOut Series #2'
OBSERVED = [
    ('Oct 13, 17:00', 'ex-Keyd Stars', 'Galorys', 'ESL Challenger League Season 52: South America - Cup #3', 'ex-keyd-stars-vs-galorys-esl-challenger-league-season-52-south-america-cup-3-1081076'),
    ('Oct 13, 21:00', 'Zomblers', 'Overtake Sector', 'ESL Challenger League Season 52: North America - Cup #3', 'zomblers-vs-overtake-sector-esl-challenger-league-season-52-north-america-cup-3-1079546'),
    ('Oct 14, 04:00', 'Gothic', 'Lavked', CCT, 'gothic-vs-lavked-cct-europe-2026-series-11-1079621'),
    ('Oct 14, 04:30', '9z', 'Aurora', TP, '9z-vs-aurora-thunderpick-world-championship-2026-1080176'),
    ('Oct 14, 06:00', 'Astralis', 'Sashi', PULSE, 'astralis-vs-sashi-stake-pulse-beat-iii-1079438'),
    ('Oct 14, 06:00', 'HOTU', 'Fnatic', PULSE, 'hotu-vs-fnatic-stake-pulse-beat-iii-1079439'),
    ('Oct 14, 07:00', 'ex-RUSTEC', 'mellren', CCT, 'ex-rustec-vs-mellren-cct-europe-2026-series-11-1079622'),
    ('Oct 14, 07:00', 'Falcons', 'Ninjas in Pyjamas', TP, 'falcons-vs-ninjas-in-pyjamas-thunderpick-world-championship-2026-1080177'),
    ('Oct 14, 09:30', 'Legacy', 'PARIVISION', TP, 'legacy-vs-parivision-thunderpick-world-championship-2026-1080178'),
    ('Oct 14, 10:00', 'G2 Ares', 'The Last Resort', CCT, 'g2-ares-vs-the-last-resort-cct-europe-2026-series-11-1079623'),
    ('Oct 14, 12:00', 'FURIA', 'BetBoom', TP, 'furia-vs-betboom-thunderpick-world-championship-2026-1080179'),
    ('Oct 14, 13:00', 'FORZE Reload', 'LFO 10', CCT, 'forze-reload-vs-lfo-10-cct-europe-2026-series-11-1079624'),
    ('Oct 15, 04:00', 'WROTBERRY', 'EAC', ELISA, 'wrotberry-vs-eac-elisa-breakout-series-2-1080279'),
    ('Oct 15, 06:00', 'MIBR', 'BC.Game', PULSE, 'mibr-vs-bc-game-stake-pulse-beat-iii-1079440'),
    ('Oct 15, 06:00', 'Heroic', 'Envy', PULSE, 'heroic-vs-envy-stake-pulse-beat-iii-1079442'),
    ('Oct 15, 06:00', 'ENCE', 'BOJONG', ELISA, 'ence-vs-bojong-elisa-breakout-series-2-1080280'),
    ('Oct 15, 08:00', 'WROTBERRY', 'ENCE', ELISA, 'wrotberry-vs-ence-elisa-breakout-series-2-1080281'),
    ('Oct 15, 10:00', 'EAC', 'BOJONG', ELISA, 'eac-vs-bojong-elisa-breakout-series-2-1080282'),
    ('Oct 15, 12:00', 'WROTBERRY', 'BOJONG', ELISA, 'wrotberry-vs-bojong-elisa-breakout-series-2-1080283'),
    ('Oct 15, 14:00', 'EAC', 'ENCE', ELISA, 'eac-vs-ence-elisa-breakout-series-2-1080284'),
    ('Oct 16, 04:00', 'Voca', 'Phantom', ELISA, 'voca-vs-phantom-elisa-breakout-series-2-1080285'),
    ('Oct 16, 06:00', 'HAVU', 'RoundsGG', ELISA, 'havu-vs-roundsgg-elisa-breakout-series-2-1080286'),
    ('Oct 16, 08:00', 'Voca', 'HAVU', ELISA, 'voca-vs-havu-elisa-breakout-series-2-1080287'),
    ('Oct 16, 10:00', 'Phantom', 'RoundsGG', ELISA, 'phantom-vs-roundsgg-elisa-breakout-series-2-1080288'),
    ('Oct 16, 12:00', 'RoundsGG', 'Voca', ELISA, 'roundsgg-vs-voca-elisa-breakout-series-2-1080289'),
    ('Oct 16, 14:00', 'Phantom', 'HAVU', ELISA, 'phantom-vs-havu-elisa-breakout-series-2-1080290'),
]
ODDS = [
    {
        'teams': ['9z Team', 'Aurora'],
        'american_odds': [280, -455],
        'date_label': 'October 14, 04:30',
        'tournament': TP,
        'source': 'https://thunderpick.io/esports/cs2-betting/thunderpick-world-championship-2026/11024/9z-team-vs-aurora/2796376',
        'identity_evidence': BASE + OBSERVED[3][4],
        'identity_note': 'Hotspawn detail heading 9z vs Aurora explicitly links the first team as 9z Team; no fuzzy alias inference.',
        'lobby_row_index': 3,
        'hotspawn_detail_time_label': '08:30 / 14 OCT',
    },
    {
        'teams': ['Astralis', 'Sashi'],
        'american_odds': [-1250, 530],
        'date_label': 'October 14, 06:00',
        'tournament': 'Pulse Beat III',
        'source': 'https://thunderpick.io/esports/cs2-betting/pulse-beat-iii/11173/astralis-vs-sashi/2767822',
        'identity_evidence': BASE + OBSERVED[4][4],
        'identity_note': 'Exact team labels match lobby. Event labels differ: Stake Pulse Beat III versus Pulse Beat III. No canonical event mapping asserted.',
        'lobby_row_index': 4,
        'hotspawn_detail_time_label': '10:00 / 14 OCT',
    },
]


def implied(american):
    if not isinstance(american, int) or isinstance(american, bool) or abs(american) < 100:
        raise ValueError('American odds must have absolute value >= 100')
    return Fraction(100, american + 100) if american > 0 else Fraction(-american, -american + 100)


def calculate(pair):
    q = [implied(x) for x in pair]
    total = sum(q)
    p = [x / total for x in q]
    return {
        'method': 'proportional removal of two-way overround',
        'kind': 'derived estimate, not independently verified true probability',
        'raw_implied_probability': [float(x) for x in q],
        'overround': float(total - 1),
        'probability': [float(x) for x in p],
        'fair_decimal_odds': [float(1 / x) for x in p],
        'exact_probability_fractions': [str(x) for x in p],
    }


def build():
    rows = []
    for i, (date, a, b, tournament, path) in enumerate(OBSERVED):
        rows.append({
            'id': path.rsplit('-', 1)[1],
            'teams': [a, b],
            'tournament': tournament,
            'scheduled_label': date,
            'scheduled_at_utc': None,
            'timezone': None,
            'year': None,
            'game': 'CS2' if i in (3, 4) else None,
            'section': 'Closing Soon' if i < 12 else 'Upcoming',
            'source': LOBBY,
            'source_chunks': [0] if i < 11 else ([0, 1] if i == 11 else [1]),
            'match_source': BASE + path,
            'verification': {'teams': 'observed on official lobby', 'tournament': 'observed on official lobby', 'scheduled_label': 'observed; timezone and year not established', 'game': 'confirmed by official match detail title' if i in (3, 4) else 'not separately confirmed'},
            'odds': None,
            'probabilities': None,
            'status': 'needs review',
            'flags': ['UTC time/year unverified', 'Independent current match-winner odds unverified'],
        })
    quotes = []
    for observation in ODDS:
        quote = {**observation, 'bookmaker': 'Thunderpick', 'market': 'Match Winner', 'format': 'American', 'best_of': 'BO3', 'market_phase': None, 'timezone': None, 'year': None, 'observed_date': '2026-10-13', 'observed_at_utc': None, 'verification': 'Exact official match page market labels and paired prices read through fetch_page, chunk 1', 'analysis': calculate(observation['american_odds']), 'flags': ['Market phase unverified: page includes Live label and calls this an upcoming match', 'Source quote timestamp unavailable; date of access is not quote time', 'Lobby/detail schedule labels differ; timezone must not be inferred', 'Single bookmaker, not a multi-book consensus'], 'publish_as_current_lobby_probability': False}
        rows[observation['lobby_row_index']]['external_quote_sources'] = [observation['source']]
        rows[observation['lobby_row_index']]['flags'].append('Official external price observation exists but current event/phase/timestamp join not verified; see independent quotes')
        quotes.append(quote)
    return {
        'schema_version': 1,
        'session': '1916f96c',
        'observed_date': '2026-10-13',
        'observation_channel': 'fetch_page official-site text, not hosted runner artifact',
        'is_live_feed': False,
        'coverage': {'visible_cards_observed': len(rows), 'headline_matches_this_week': 60, 'initial_filter_count': 86, 'completeness': 'unverified', 'lol_coverage': 'unverified'},
        'policy': 'No Hotspawn pick percentages, ratings, tier, rewards, or standings used in probability calculations. Blank fields remain null. Calculations are separately labeled estimates. Do not serve this dated audit as fresh automated feed.',
        'matches': rows,
        'independent_official_price_observations': quotes,
        'method_source': 'https://help.smarkets.com/hc/en-gb/articles/214058369-How-to-calculate-implied-probability-in-betting',
    }


if __name__ == '__main__':
    result = build()
    (ROOT / 'observations.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f"Compiled {len(result['matches'])} official lobby observations and {len(result['independent_official_price_observations'])} independently sourced price pairs")
