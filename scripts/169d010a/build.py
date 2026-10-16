"""Session 169d010a: independent re-check of the TWC Day-3 deciders and the open-fixture board.

Inputs (read-only):
  data/c64a5e19/board.json      canonical open-fixture board (raw quotes, stored probabilities)
  data/169d010a/evidence.json   this session's dated evidence ledger (every entry has a URL + read time)

Outputs (owned by this session):
  data/169d010a/recheck.json    machine-readable re-derivation + decisions
  audits/169d010a/index.html    phone-first executive summary: Day-3 picks, flags, unresolved attempts
  audits/169d010a/open-matches.html  every open fixture, one card per match, source link on each card

Nothing here fetches the network. Every probability shown is either re-derived arithmetic from a
recorded raw quote (no-vig, Pinnacle weight 2 as declared on picks-every-match/method.html) or a
dated secondary cross-check. Crowd (HotSpawn pick %) is ownership context only and never a price.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / 'data/c64a5e19/board.json'
EVIDENCE = ROOT / 'data/169d010a/evidence.json'
OUT_DATA = ROOT / 'data/169d010a/recheck.json'
OUT_DIR = ROOT / 'audits/169d010a'

PINNACLE_WEIGHT = 2.0          # declared consensus weighting (picks-every-match/method.html)
MATCH_TOL = 0.0005             # tolerance between re-derived and stored probability (rounding to 4dp)
DAY3_DESK_FLOOR = 0.30         # floor used by day3/picks.html (contrarian-but-not-stupid)
HUB_FLOOR = 0.35               # stricter floor used by the hub / watchlist wording
OWNERSHIP_MAX = 0.20           # HotSpawn crowd share at or below this = contrarian ownership
FLAGS_MIN = 2                  # verified context flags needed for a climb pick
POINTS_DAY3 = 7                # HotSpawn points for both TWC Day-3 deciders

# HotSpawn crowd % read from the lobby card at the time of this session's fetch.
# Lock 13:54:00Z minus the card countdown 06:35:41 gives a capture time of about 07:18Z.
LOBBY_OWNERSHIP = {
    '1080205': {'Aurora': 0.90, '9z': 0.10, 'capture': '2026-10-16T07:18Z (derived from lock time minus card countdown)'},
    '1081775': {'BetBoom': 0.14, 'Legacy': 0.86, 'capture': '2026-10-16T07:18Z (derived from lock time minus card countdown)'},
}


def utc_now_label() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')


def norm_pair(a: float, b: float) -> tuple[float, float]:
    ia, ib = 1.0 / a, 1.0 / b
    s = ia + ib
    return ia / s, ib / s


def rederive_market(quotes: list[dict]) -> tuple[float | None, list[dict]]:
    """Re-derive the consensus P(team_a) from raw decimal quotes, Pinnacle weighted 2."""
    rows, num, den = [], 0.0, 0.0
    for q in quotes:
        a, b = q.get('decimal_a'), q.get('decimal_b')
        if not a or not b:
            continue
        # Same orientation rule as scripts/c64a5e19/build.py: when the source listed the teams in
        # the opposite order, the first price belongs to team_b and must be swapped before no-vig.
        if q.get('swapped'):
            a, b = b, a
        pa, pb = norm_pair(float(a), float(b))
        w = PINNACLE_WEIGHT if q.get('source_key') == 'pinnacle' else 1.0
        num += w * pa
        den += w
        rows.append({'source': q.get('source_name'), 'decimal_a': a, 'decimal_b': b,
                     'no_vig_a': round(pa, 4), 'weight': w, 'url': q.get('public_url'),
                     'swapped_in_source': bool(q.get('swapped'))})
    if not den:
        return None, rows
    return round(num / den, 4), rows


def pct(x: float) -> str:
    return f'{x * 100:.1f}%'


def decide_day3(name: str, fav: str, dog: str, p_fav: float, p_dog: float, ownership_dog: float,
                flags: list[dict]) -> dict:
    """Safe pick = market favourite. Climb pick = underdog only if every gate passes."""
    counted = [f for f in flags if f['counts_for_underdog']]
    gates = {
        f'market probability >= {DAY3_DESK_FLOOR:.0%} (day-3 desk floor)': p_dog >= DAY3_DESK_FLOOR,
        f'HotSpawn ownership of underdog <= {OWNERSHIP_MAX:.0%} (context only)': ownership_dog <= OWNERSHIP_MAX,
        f'>= {FLAGS_MIN} verified context flags for the underdog': len(counted) >= FLAGS_MIN,
    }
    climb_ok = all(gates.values())
    stricter_ok = p_dog >= HUB_FLOOR
    return {
        'match': name,
        'safe_pick': fav,
        'safe_prob': p_fav,
        'safe_expected_points': round(p_fav * POINTS_DAY3, 2),
        'climb_candidate': dog,
        'climb_prob': p_dog,
        'climb_expected_points': round(p_dog * POINTS_DAY3, 2),
        'expected_points_cost_of_climb': round((p_fav - p_dog) * POINTS_DAY3, 2),
        'ownership_underdog': ownership_dog,
        'leverage_ratio': round(p_dog / ownership_dog, 2) if ownership_dog else None,
        'gates': gates,
        'climb_qualifies_day3_desk_rule': climb_ok,
        'climb_clears_stricter_hub_floor_35pct': stricter_ok,
        'flags_counted': [f['id'] for f in counted],
        'flags': flags,
    }


AURORA_FLAGS = [
    {'id': 'A1', 'for': '9z', 'counts_for_underdog': True, 'strength': 'medium',
     'text': 'Aurora rebuilt in July 2026: new IGL kyxsan, Jimpphat and coach ash joined in the summer; the coach says official-match consistency is still developing (Aug 2026).',
     'evidence': ['E07', 'E08']},
    {'id': 'A2', 'for': '9z', 'counts_for_underdog': True, 'strength': 'medium',
     'text': '9z beat Aurora 2-0 in the Day-1 meeting on 14 Oct 2026 (the latest head-to-head).',
     'evidence': ['E02', 'E04']},
    {'id': 'A3', 'for': '9z', 'counts_for_underdog': False, 'strength': 'weak',
     'text': 'Match load: 9z played three maps on Day 2 (lost 1-2 to Falcons) against two maps for Aurora (2-0 NIP). Not a rest measure, so it is recorded but not counted.',
     'evidence': ['E05']},
    {'id': 'C1', 'for': 'Aurora', 'counts_for_underdog': False, 'strength': 'against 9z',
     'text': 'Aurora is the bookmaker favourite with the best odds and has won 3 of its last 5 (HLTV analytics). Counted against the underdog.',
     'evidence': ['E02']},
]

BETBOOM_FLAGS = [
    {'id': 'B1', 'for': 'BetBoom', 'counts_for_underdog': True, 'strength': 'medium',
     'text': 'Legacy changed a player in summer 2026: Santino "try" Rigal joined the lineup (HLTV rostermania tracker). Onboarding context for Legacy.',
     'evidence': ['E10']},
    {'id': 'B2', 'for': 'BetBoom', 'counts_for_underdog': True, 'strength': 'medium',
     'text': 'Legacy lost its last series 1-2 to FURIA on Day 2 after a 2-0 win over PARIVISION on Day 1.',
     'evidence': ['E06', 'E19']},
    {'id': 'B3', 'for': 'BetBoom', 'counts_for_underdog': False, 'strength': 'weak',
     'text': 'BetBoom came back from 0-2 vs FURIA on Day 1 to beat PARIVISION 2-1 on Day 2 (reverse sweep). Momentum only, not counted.',
     'evidence': ['E06', 'E19']},
    {'id': 'B4', 'for': 'Legacy', 'counts_for_underdog': False, 'strength': 'against BetBoom',
     'text': 'Editorial preview picks Legacy 2-0 (opinion, not a price, not counted).',
     'evidence': ['E13']},
]


def build_recheck() -> dict:
    board = json.loads(BOARD.read_text())
    evidence = json.loads(EVIDENCE.read_text())
    open_rows = board['open']

    rechecked = []
    stats = {'open': len(open_rows), 'priced_rows': 0, 'priced_matches_rederived': 0,
             'model_only_rows': 0, 'rows_with_pick': 0, 'rows_without_pick': 0,
             'mismatches': []}

    for r in open_rows:
        line = r.get('line') or {}
        market = r.get('market') or {}
        stored = market.get('prob_a')
        re_prob, qrows = rederive_market(r.get('quotes', []))
        status = 'no_quotes'
        if stored is not None and re_prob is not None:
            stats['priced_rows'] += 1
            if abs(re_prob - stored) <= MATCH_TOL:
                stats['priced_matches_rederived'] += 1
                status = 'rederived_match'
            else:
                status = 'MISMATCH'
                stats['mismatches'].append(r['fixture_id'])
        elif line.get('basis') == 'model':
            stats['model_only_rows'] += 1
            status = 'model_only_not_rederived'
        pick = line.get('pick_team')
        if pick:
            stats['rows_with_pick'] += 1
        else:
            stats['rows_without_pick'] += 1
        rechecked.append({
            'fixture_id': r['fixture_id'],
            'start_utc': r['start_utc'],
            'competition': r['competition'],
            'tier': r.get('tier'),
            'team_a': r['team_a'],
            'team_b': r['team_b'],
            'hotspawn_url': r.get('hotspawn_url'),
            'pick_team': pick,
            'pick_prob': line.get('pick_prob'),
            'prob_a_stored': stored,
            'prob_a_rederived': re_prob,
            'basis': line.get('basis') or ('none' if not line else line.get('basis')),
            'toss_up_no_edge': re_prob == 0.5,
            'quote_sources': qrows,
            'recheck_status': status,
            'flags': r.get('flags', []),
        })

    by_id = {x['fixture_id']: x for x in rechecked}
    # Day-3 deciders: cross-check the Aurora price against the independent stavka.tv preview.
    stavka = {'P1_aurora': 1.38, 'P2_9z': 2.70}
    s_a, s_b = norm_pair(stavka['P1_aurora'], stavka['P2_9z'])
    aur = by_id['1080205']
    bb = by_id['1081775']
    aur_p = aur['prob_a_rederived']          # Aurora
    bb_p = bb['prob_a_rederived']            # BetBoom
    own_a = LOBBY_OWNERSHIP['1080205']
    own_b = LOBBY_OWNERSHIP['1081775']

    decisions = [
        decide_day3('Aurora vs 9z (Group A decider, 16 Oct 14:00 UTC, 1080205)',
                    'Aurora', '9z', aur_p, round(1 - aur_p, 4), own_a['9z'], AURORA_FLAGS),
        decide_day3('BetBoom vs Legacy (Group B decider, 16 Oct 17:00 UTC, 1081775)',
                    'Legacy', 'BetBoom', round(1 - bb_p, 4), bb_p, own_b['BetBoom'], BETBOOM_FLAGS),
    ]

    data = {
        'session': '169d010a',
        'generated_utc': utc_now_label(),
        'source_board': {'path': 'data/c64a5e19/board.json', 'generated_utc': board.get('generated_utc'),
                         'collected_from_utc': board.get('collected_from_utc'),
                         'open_fixtures': len(open_rows)},
        'stats': stats,
        'rows': rechecked,
        'secondary_cross_check': {
            'source': 'https://stavka.tv/matches/csgo/16-10-2026-aurora-gaming-9z (E12; bookmaker not named)',
            'P1_aurora_decimal': stavka['P1_aurora'], 'P2_9z_decimal': stavka['P2_9z'],
            'aurora_no_vig': round(s_a, 4), 'canonical_aurora': aur_p,
            'delta_pp': round((aur_p - s_a) * 100, 2),
        },
        'day3_decisions': decisions,
        'constants': {'pinnacle_weight': PINNACLE_WEIGHT, 'match_tolerance': MATCH_TOL,
                      'day3_desk_floor': DAY3_DESK_FLOOR, 'hub_floor': HUB_FLOOR,
                      'ownership_max': OWNERSHIP_MAX, 'flags_min': FLAGS_MIN, 'points_day3': POINTS_DAY3},
        'lobby_ownership_context_only': LOBBY_OWNERSHIP,
        'evidence_count': len(evidence['entries']),
        'unresolved_fixture_ids': [x['fixture_id'] for x in rechecked if not x['pick_team']],
    }
    return data


UNRESOLVED_ATTEMPTS = [
    {'fixture_id': '1079167', 'what': 'Bushido Wildcats vs ex-RUSTEC · NODWIN Clutch Series 13 · 16 Oct 11:00 UTC',
     'tried': ['Melbet single quote 1.87 / 1.87 (toss-up, one source) (E17 shows the same pattern)',
               'EGamersWorld 1.8 / 1.8 uniform placeholder (E16, not used)',
               'Polymarket listing with $0 volume (no price)',
               'Valve VRS: Bushido Wildcats 114th (982 pts); ex-RUSTEC has no unambiguous VRS join (board flag ambiguous_vrs_name)'],
     'why': 'Toss-up with one source, and no unambiguous second price or identity for ex-RUSTEC.',
     'would_resolve': 'A second non-toss-up bookmaker price, or a confirmed ex-RUSTEC roster on HLTV/VRS.',
     'evidence': ['E16', 'E17']},
    {'fixture_id': '1081769', 'what': 'ex-Zero Tenacity vs UNiTY · NODWIN Clutch Series 13 · 16 Oct 14:00 UTC',
     'tried': ['Melbet single quote 1.87 / 1.87 (toss-up)', 'kushvsporte.ru 1.87 / 1.87 (same toss-up, E17)',
               'EGamersWorld 1.8 / 1.8 placeholder (E16, not used)',
               'Valve VRS: UNiTY 69th (1167 pts) vs ex-Zero Tenacity 93rd (1066 pts). The board runs a market-first policy, so this model lean is not published.'],
     'why': 'Every price is a toss-up. The only model signal (VRS) contradicts nothing but has not been confirmed on a second source, and the board policy keeps the market toss-up.',
     'would_resolve': 'A non-toss-up second bookmaker price; or the owner of this board ruling that VRS may break market ties.',
     'evidence': ['E16', 'E17']},
    {'fixture_id': '1079170', 'what': 'BET-M vs Just Players · NODWIN Clutch Series 13 · 17 Oct 08:00 UTC',
     'tried': ['HLTV team page BET-M: no upcoming matches (E18)',
               'Polymarket "BET-M 33 vs Just Players" (18 Sep 2026) is a different entity (E18)',
               'No bookmaker quote for this fixture found; Melbet not listed for it in the board'],
     'why': 'No price and no unambiguous identity for either team.',
     'would_resolve': 'A bookmaker listing for BET-M vs Just Players, or an HLTV match page with a confirmed BET-M roster.',
     'evidence': ['E18']},
    {'fixture_id': '1081126', 'what': 'Banda chuya vs Enjoy · CCT Europe 2026 Series 12 Play-In · 18 Oct 08:00 UTC',
     'tried': ['HLTV event page: Banda Chuya ranked #187, Enjoy in the closed qualifier (E18)',
               'EGamersWorld 1.8 / 1.8 placeholder (E16, not used)',
               'Valve VRS: Enjoy 138th (871 pts); Banda chuya has no unambiguous VRS join'],
     'why': 'No price; one side has no official rating join. The HLTV rank gap (#187) is a single factor and is not enough to set a probability honestly.',
     'would_resolve': 'A bookmaker price, or a verified VRS join for Banda chuya.',
     'evidence': ['E16', 'E18']},
    {'fixture_id': '1081529', 'what': 'Nexus vs WROTBERRY · DraculaN Season 7 · 19 Oct 09:00 UTC',
     'tried': ['Melbet quote found only for WhiteBIT Team vs Nexus Gaming; rejected as a different identity by the board join',
               'HLTV blocked for this lobby capture; WROTBERRY absent from the Valve VRS table'],
     'why': 'WROTBERRY has no official rating and the only price names a different opponent.',
     'would_resolve': 'A correctly joined bookmaker price for Nexus vs WROTBERRY.',
     'evidence': ['E18']},
    {'fixture_id': '1081531', 'what': 'Sashi vs mouz NXT · DraculaN Season 7 · 19 Oct 10:45 UTC',
     'tried': ['No bookmaker price found', 'Valve VRS: Sashi 73rd (1131 pts); mouz NXT is an ambiguous name in the VRS join'],
     'why': 'One side is not uniquely identified in the official rating table, so no model probability.',
     'would_resolve': 'A unique VRS / HLTV identity for mouz NXT, plus a bookmaker price.',
     'evidence': ['E18']},
    {'fixture_id': '1081532', 'what': 'ASTRAL vs Leo · DraculaN Season 7 · 19 Oct 10:45 UTC',
     'tried': ['No bookmaker price found', 'Valve VRS: ASTRAL 91st (1072 pts); Leo is an ambiguous name in the VRS join'],
     'why': 'As above: one side is not uniquely identified in the official rating table.',
     'would_resolve': 'A unique VRS / HLTV identity for Leo, plus a bookmaker price.',
     'evidence': ['E18']},
]


FLAGS = [
    ('F1', 'The brief says Aurora had a "recent roster change". The only change found is the July 2026 rebuild (kyxsan IGL, Jimpphat, coach ash). No October change was found.', ['E07', 'E08', 'E09']),
    ('F2', 'Two floors are in use. The day-3 desk uses 30% and the hub uses 35%. 9z sits at 33.4%, so the pick passes one and fails the other. We state both and do not hide the gap.', ['E02']),
    ('F3', 'Pick-count disagreement across boards. The landing says 5 unverified; the hub said 2 blank at 04:43Z; the canonical board now has 24 picks and 7 rows without a pick (2 of those are Melbet toss-ups). The landing undercounts.', []),
    ('F4', 'The Bovada and Pinnacle raw quotes behind the Day-3 probabilities could not be re-read in this session (Bovada: Not Found + reCAPTCHA; Pinnacle: 404). Arithmetic is re-derived from the recorded quotes; the quotes themselves are UNVERIFIED on re-read.', ['E15']),
    ('F5', 'The HLTV "Pick a winner" widget (82/18) is a fan poll and is not a price. Its ordering in the captured text is ambiguous. Not used.', ['E03']),
    ('F6', 'The Polymarket Aurora vs 9z price (76/25) is for the settled Day-1 match and cannot be used for Day 3.', ['E14']),
    ('F7', 'The stavka.tv price (Aurora 66.2%) is a secondary, unnamed-bookmaker cross-check. It agrees with the canonical 66.6% within 0.4 pp; it is not an official source.', ['E12']),
    ('F8', 'EGamersWorld prices of 1.8 / 1.8 are a uniform placeholder and are not used.', ['E16']),
    ('F9', 'Crowd ownership moves between captures: BetBoom was 17% in the canonical 04:59Z capture and 14% in the 07:18Z lobby read. Ownership is context only and does not change the probabilities.', []),
    ('F10', 'Rest was not measured. The only load fact is match count (9z three maps on Day 2, Aurora two). Rest hours are not used.', ['E05']),
    ('F11', 'The landing page carries roughly 30 links from about 20 sessions, which the user describes as confusing on a phone. This is a request to the integration owner, not an edit made here (see COORDINATION.md).', []),
]


def css() -> str:
    return """
:root{--ink:#14202b;--mut:#5b6b78;--bg:#f6f8fa;--card:#fff;--ok:#0a7d4f;--warn:#9a5b00;--bad:#b42318;--line:#dbe3ea;--acc:#1f5fbf}
*{box-sizing:border-box}
body{margin:0;font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--bg)}
header{background:#0f2a44;color:#fff;padding:18px 16px}
header h1{font-size:1.35rem;margin:0 0 6px}
header p{margin:0;color:#cfe0f2;font-size:.95rem}
main{max-width:920px;margin:0 auto;padding:14px}
nav.quick{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
nav.quick a{background:var(--acc);color:#fff;text-decoration:none;padding:10px 12px;border-radius:10px;font-size:.95rem;min-height:44px;display:inline-flex;align-items:center}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin:12px 0}
h2{font-size:1.15rem;margin:0 0 10px}
h3{font-size:1rem;margin:12px 0 6px}
.pick{border:2px solid var(--ok);border-radius:12px;padding:12px;margin:10px 0;background:#f2fbf6}
.climb{border:2px dashed var(--warn);border-radius:12px;padding:12px;margin:10px 0;background:#fffaf0}
.big{font-size:1.1rem;font-weight:700}
.pill{display:inline-block;border-radius:999px;padding:2px 9px;font-size:.8rem;margin-right:4px;background:#e6edf4;color:#25394d}
.pill.ok{background:#dff5ea;color:var(--ok)}.pill.warn{background:#fff1d6;color:var(--warn)}.pill.bad{background:#fde4e1;color:var(--bad)}
ul{padding-left:20px}li{margin:4px 0}
a{color:var(--acc)}
.card{border:1px solid var(--line);border-radius:10px;padding:10px;margin:8px 0;background:#fff}
.card .meta{color:var(--mut);font-size:.9rem}
.small{font-size:.88rem;color:var(--mut)}
.num{font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;font-size:.92rem}
th,td{text-align:left;padding:6px;border-bottom:1px solid var(--line);vertical-align:top}
@media (min-width:760px){.cards-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
"""


def page(title: str, body: str, desc: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<style>{css()}</style>
</head>
<body>
<header><h1>{html.escape(title)}</h1><p>{html.escape(desc)}</p></header>
<main>
{body}
</main>
</body>
</html>
"""


def fmt_pts(x: float) -> str:
    return f'{x:.2f}'


def render_index(data: dict) -> str:
    dec = data['day3_decisions']
    aur, bb = dec[0], dec[1]
    ev = {e['id']: e for e in json.loads(EVIDENCE.read_text())['entries']}

    def ev_links(ids: list[str]) -> str:
        out = []
        for i in ids:
            e = ev.get(i)
            if e:
                out.append(f'<a href="{html.escape(e["url"])}" rel="nofollow">{i}</a>')
        return ' · '.join(out)

    def decision_block(d: dict, safe_name: str, climb_name: str) -> str:
        gates_html = ''.join(
            f'<li>{"✅" if ok else "❌"} {html.escape(g)}</li>' for g, ok in d['gates'].items())
        flags_html = ''.join(
            f'<li><b>{f["id"]}</b> ({html.escape(f["strength"])}, for {html.escape(f["for"])}): '
            f'{html.escape(f["text"])} <span class="small">Sources: {ev_links(f["evidence"])}</span></li>'
            for f in d['flags'])
        verdict = ('Qualifies under the day-3 desk rule.' if d['climb_qualifies_day3_desk_rule']
                   else 'Does not qualify under the day-3 desk rule.')
        floor_note = ('Also clears the stricter 35% hub floor.' if d['climb_clears_stricter_hub_floor_35pct']
                      else 'Does NOT clear the stricter 35% hub floor. Flagged as a judgement call.')
        return f"""
<div class="pick">
  <div class="small">SAFE PICK · expected {fmt_pts(d['safe_expected_points'])} pts</div>
  <div class="big">{html.escape(safe_name)} · {pct(d['safe_prob'])}</div>
</div>
<div class="climb">
  <div class="small">CLIMB PICK (contrarian, not stupid) · expected {fmt_pts(d['climb_expected_points'])} pts · cost vs safe {fmt_pts(d['expected_points_cost_of_climb'])} pts</div>
  <div class="big">{html.escape(climb_name)} · {pct(d['climb_prob'])}</div>
  <p class="small">HotSpawn crowd on {html.escape(climb_name)}: {pct(d['ownership_underdog'])} · leverage {d['leverage_ratio']}× (market ÷ crowd). Crowd is ownership context only.</p>
  <p><b>{verdict}</b> {floor_note}</p>
  <h3>Gates</h3><ul>{gates_html}</ul>
  <h3>Context flags</h3><ul>{flags_html}</ul>
</div>
"""

    sec_decisions = (
        '<section id="day3"><h2>1 · TWC Day 3 deciders (16 Oct 2026)</h2>'
        '<h3>Aurora vs 9z · Group A decider · 14:00 UTC · 7 pts</h3>'
        + decision_block(aur, 'Aurora', '9z')
        + '<h3>BetBoom vs Legacy · Group B decider · 17:00 UTC · 7 pts</h3>'
        + decision_block(bb, 'Legacy', 'BetBoom')
        + '</section>'
    )

    cc = data['secondary_cross_check']
    sec_checks = f"""
<section id="checks"><h2>2 · Independent checks</h2>
<ul>
<li>Open CS2 fixtures re-read from the canonical board: <b class="num">{data['stats']['open']}</b></li>
<li>Priced rows re-derived from stored raw quotes: <b class="num">{data['stats']['priced_matches_rederived']}</b> of {data['stats']['priced_rows']} match the stored probability within 0.05 pp. Mismatches: <b>{len(data['stats']['mismatches'])}</b>.</li>
<li>Model-only rows (not re-derived here): <b class="num">{data['stats']['model_only_rows']}</b></li>
<li>Rows with a pick: <b class="num">{data['stats']['rows_with_pick']}</b> · rows without a pick: <b class="num">{data['stats']['rows_without_pick']}</b> (see section 4)</li>
<li>Second price for Aurora vs 9z (stavka.tv, bookmaker unnamed): Aurora <b>{pct(cc['aurora_no_vig'])}</b> vs canonical <b>{pct(cc['canonical_aurora'])}</b>, a difference of {cc['delta_pp']} pp. <span class="small">Source: <a href="{html.escape(cc['source'].split(' ')[0])}">stavka.tv</a></span></li>
<li>Kickoffs: HLTV match 2399412 shows 10:00 with a 6h 39m countdown, consistent with 14:00 UTC (HotSpawn and the 3-book start times agree).</li>
</ul>
<p class="small">Method: each book's two decimal prices are no-vigged (1/odds, normalised). The consensus averages those values with Pinnacle counted twice, as declared on the canonical method page. Reproduce it with <code>python3 scripts/169d010a/build.py</code>.</p>
</section>"""

    flags_html = ''.join(
        f'<li><b>{fid}</b> {html.escape(txt)} <span class="small">{ev_links(evs) if evs else ""}</span></li>'
        for fid, txt, evs in FLAGS)
    sec_flags = f'<section id="flags"><h2>3 · Flagged for review</h2><ul>{flags_html}</ul></section>'

    un_rows = ''
    for u in UNRESOLVED_ATTEMPTS:
        tried = ''.join(f'<li>{html.escape(t)}</li>' for t in u['tried'])
        un_rows += f"""
<div class="card">
  <div class="big">{html.escape(u['what'])}</div>
  <p class="small"><a href="https://play.hotspawn.com/lobby">HotSpawn lobby</a> · sources: {ev_links(u['evidence'])}</p>
  <h3>Attempted</h3><ul>{tried}</ul>
  <p><b>Why no pick:</b> {html.escape(u['why'])}</p>
  <p><b>What would resolve it:</b> {html.escape(u['would_resolve'])}</p>
  <p><span class="pill warn">UNRESOLVED · blank, not 50/50</span></p>
</div>"""
    sec_unres = f"""
<section id="unresolved"><h2>4 · Unresolved picks and limitations</h2>
<p>Seven open fixtures still have no pick under the rules. None is filled with a guess. Each row lists what was tried and what would change the result. The full board with probabilities is on <a href="../../picks-every-match/unresolved.html">the canonical unresolved page</a>.</p>
{un_rows}
</section>"""

    nav = """
<nav class="quick" aria-label="Quick links">
  <a href="../../hub/index.html">Mobile hub (every match)</a>
  <a href="../../picks-every-match/index.html">All CS2 picks</a>
  <a href="open-matches.html">Every open match (31)</a>
  <a href="../../picks-every-match/unresolved.html">Unresolved picks</a>
  <a href="../../twc-2026/index.html">TWC Day 2 → Day 3</a>
  <a href="../../index.html">Landing</a>
</nav>"""

    head_note = (
        f'<p class="small">Generated {html.escape(data["generated_utc"])} from canonical board captured '
        f'{html.escape(str(data["source_board"]["collected_from_utc"]))}. HotSpawn crowd % = ownership only. '
        'Probabilities are re-derived from recorded raw quotes. Session 169d010a, an independent re-check; '
        'it does not replace the canonical board.</p>')

    bottom = f"""
<section id="bottom-line"><h2>Bottom line</h2>
<ul>
<li><b>Aurora vs 9z:</b> safe pick <b>{html.escape(aur['safe_pick'])}</b> ({pct(aur['safe_prob'])}). Climb pick <b>{html.escape(aur['climb_candidate'])}</b> ({pct(aur['climb_prob'])}, crowd {pct(aur['ownership_underdog'])}). It passes the 30% desk floor with {len(aur['flags_counted'])} counted flags, but it misses the stricter 35% hub floor by {round((0.35 - aur['climb_prob']) * 100, 1)} pp. Take 9z only if you need variance.</li>
<li><b>BetBoom vs Legacy:</b> safe pick <b>{html.escape(bb['safe_pick'])}</b> ({pct(bb['safe_prob'])}). Climb pick <b>{html.escape(bb['climb_candidate'])}</b> ({pct(bb['climb_prob'])}, crowd {pct(bb['ownership_underdog'])}). It clears both floors with {len(bb['flags_counted'])} counted flags, so it is the cleaner contrarian of the two.</li>
<li><b>Roster premise:</b> the Aurora change is the July 2026 rebuild, not an October move. No October change was found (flag F1).</li>
<li><b>Coverage:</b> 24 of 31 open fixtures have a pick; 7 are unresolved and listed in section 4 with what was tried.</li>
</ul></section>"""
    body = nav + head_note + bottom + sec_decisions + sec_checks + sec_flags + sec_unres
    return page('TWC Day 3 picks · independent re-check (169d010a)', body,
                'Safe pick and climb pick for both TWC Day-3 deciders, plus the 31-fixture re-check, flags and unresolved list.')


def render_open(data: dict) -> str:
    cards = []
    for r in data['rows']:
        ps = r['prob_a_rederived']
        if r['pick_team']:
            side_prob = r['pick_prob']
            pick_html = f'<span class="pill ok">PICK</span> <b>{html.escape(r["pick_team"])}</b> · {pct(side_prob)}'
        else:
            pick_html = '<span class="pill warn">UNRESOLVED</span> no pick (see index section 4)'
        if r['toss_up_no_edge']:
            basis = 'Toss-up (exactly 50/50, no edge)'
        elif r['basis'] == 'market':
            basis = 'Market (no-vig consensus)'
        elif r['basis'] == 'model':
            basis = 'Originated model (Valve VRS curve)'
        else:
            basis = 'No supported price'
        quotes = '<br>'.join(
            f'<a href="{html.escape(q["url"] or "")}">{html.escape(q["source"] or "")}</a>'
            f' ({html.escape(r["team_a"])} {q["decimal_a"]:.2f}, {html.escape(r["team_b"])} {q["decimal_b"]:.2f})'
            for q in r['quote_sources'] if q.get('url')) or 'no bookmaker quote'
        re_txt = ('re-derived ✓' if r['recheck_status'] == 'rederived_match'
                  else 'model only (not re-derived here)' if r['recheck_status'] == 'model_only_not_rederived'
                  else 'no quotes' if r['recheck_status'] == 'no_quotes'
                  else 'MISMATCH — flagged')
        cards.append(f"""
<div class="card">
  <div class="meta">{html.escape(r['start_utc'].replace('T', ' ').replace(':00Z', 'Z'))} · {html.escape(r['competition'])} · tier {html.escape(str(r['tier']))} · #{r['fixture_id']}</div>
  <div class="big">{html.escape(r['team_a'])} vs {html.escape(r['team_b'])}</div>
  <div>{pick_html}</div>
  <div class="small">{html.escape(basis)} · {('no probability' if ps is None else html.escape(r['team_a']) + ' ' + pct(ps) + ' · ' + html.escape(r['team_b']) + ' ' + pct(1 - ps))} · recheck: {html.escape(re_txt)}</div>
  <div class="small">Quotes: {quotes}</div>
  <div class="small"><a href="{html.escape(r['hotspawn_url'] or 'https://play.hotspawn.com/lobby')}">HotSpawn fixture (official)</a></div>
</div>""")
    body = (
        '<nav class="quick"><a href="index.html">← Day-3 picks &amp; flags</a>'
        '<a href="../../picks-every-match/index.html">All CS2 picks</a></nav>'
        '<p class="small">One card per open fixture on the canonical board. Probabilities are shown for the first-listed team unless a pick is given. '
        'HotSpawn crowd % is never a price.</p>'
        + ''.join(cards))
    return page('Every open CS2 fixture · re-check (169d010a)', body,
                f'{len(data["rows"])} open fixtures, each with a pick or an explicit UNRESOLVED status, source links and recheck result.')


def main() -> None:
    data = build_recheck()
    OUT_DATA.parent.mkdir(parents=True, exist_ok=True)
    OUT_DATA.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / 'index.html').write_text(render_index(data))
    (OUT_DIR / 'open-matches.html').write_text(render_open(data))
    print('wrote', OUT_DATA.relative_to(ROOT), 'and audits/169d010a/*.html')
    print('stats', json.dumps(data['stats'], ensure_ascii=False))
    for d in data['day3_decisions']:
        print(d['match'], '| safe', d['safe_pick'], d['safe_prob'], '| climb', d['climb_candidate'], d['climb_prob'],
              '| qualifies', d['climb_qualifies_day3_desk_rule'], '| 35%', d['climb_clears_stricter_hub_floor_35pct'])


if __name__ == '__main__':
    main()
