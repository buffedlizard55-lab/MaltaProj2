# Independent repository review (T-B) — session 6196c585

Reviewed 2026-10-13 (UTC) on branch `arena/6196c585-maltaproj2` @ `6e4a805`.
Scope: everything on `main` from PR #7 (root model, session `898abb4f`), PR #8/#10 (docs dashboard, session `ef111e02`), and the audit handoffs `audits/1916f96c/**`, `audits/1d4de836/**`, plus cross-checks against this session's T-A dataset (`analysis/`).

Method (disclosed): official primary sources fetched directly where possible — Valve's Regional Standings repo via `api.github.com` raw content (only host class reachable from this sandbox besides search). All other external checks via `web_search` snippets with URLs recorded; `fetch_page` was in a persistent outage (SignatureDoesNotMatch) for this whole session, noted where it limits verification. Nothing below is inferred: every verdict cites a source; unverifiable items are explicitly marked **unverified**.

## Verdict summary

| Area | Verdict |
|---|---|
| PR #7 root model — VRS numbers, results history, rosters, real names | **Largely TRUE and exactly accurate** (verified claim-by-claim below) |
| PR #7 root model — tournament field (Virtus.pro) | **STALE/WRONG at generation time**: VP withdrew Oct 9; NIP replaced them Oct 9–12 announcements. Model generated Oct 13 18:00Z still prices VP and omits NIP |
| PR #7 `IRREG-001` / `IRREG-002` premises | **FALSE as of Oct 13**: groups + opening fixtures published Oct 12 (HLTV/pley.gg/EGW); sportsbook lines existed (Thunderpick own book, bwin, Polymarket $104K vol) |
| PR #7 PARIVISION roster / HObbit signing claim | **CONFLICTS with official VRS Oct 5** (slaxejezzz in, HObbit out) |
| PR #7 origination engine arithmetic | **Reproducible** — effective ratings, Bradley-Terry, 4.5% vig verified by recomputation |
| PR #8 docs dashboard data (`docs/data/matches.json`) | **VERIFIED 86/86 exact** vs raw lobby evidence (teams, UTC starts, status, tournament, best_of) |
| PR #8 quotes (Thunderpick ×2) | **Corroborated twice independently** (audit 1916f96c via fetch_page; this session via search snippets) |
| audits/1916f96c | **Sound, conservative**; its open 4-hour timezone flag is now **resolved** (Thunderpick displays EDT) |
| audits/1d4de836 | Sound for its date; its "VP qualified for Malta Finals" statement is **superseded** by the Oct 9 withdrawal |

---

## Section A — PR #7 root model (session 898abb4f): claim-by-claim verification

Files reviewed: `data/teams_verified.json`, `data/originated_matches.json` (28 lines), `data/originated_outrights.json`, `data/origination_summary.json`, `data/flagged_irregularities.json`, `scripts/originate_lines.py`, root `index.html` / `lines.html` / `methodology.html` / `teams.html` / `flagged.html`, `tests/test_site.py`.

### A1. Valve Regional Standings claims — ALL EXACT ✓

Primary source fetched raw via GitHub API:
[standings_global_2026_10_05.md](https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/invitation/2026/standings_global_2026_10_05.md) (repo pushed 2026-10-05T16:36:14Z) and
[standings_global_2026_08_03.md](https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/invitation/2026/standings_global_2026_08_03.md).

| teams_verified.json claim | Official VRS value | Verdict |
|---|---|---|
| Legacy oct05 #2 / 1931 pts | #2 / 1931 | ✓ exact |
| Falcons oct05 #6 / 1843 | #6 / 1843 | ✓ exact |
| FURIA #7 / 1829 | #7 / 1829 | ✓ exact |
| Aurora #9 / 1716 | #9 / 1716 | ✓ exact |
| BetBoom #11 / 1596 | #11 / 1596 | ✓ exact |
| 9z #17 / 1543 | #17 / 1543 | ✓ exact |
| PARIVISION #36 / 1411 | #36 / 1411 | ✓ exact |
| Virtus.pro #51 / 1309 | #51 / 1309 | ✓ exact (number true; participation stale — see B1) |
| Falcons invite #2 / 1950 | Aug 3 snapshot #2 / 1950 | ✓ exact |
| Legacy invite #7 / 1773 | Aug 3 #7 / 1773 | ✓ exact |
| FURIA invite #8 / 1771 | Aug 3 #8 / 1771 | ✓ exact |
| 9z invite #4 / 1847 | Aug 3 #4 / 1847 | ✓ exact |
| BetBoom invite #9 / 1742 | Aug 3 #9 / 1742 | ✓ exact |
| Aurora invite #10 / 1690 | Aug 3 #10 / 1690 | ✓ exact |
| PARIVISION invite #12 / 1685 | Aug 3 #12 / 1685 | ✓ exact |
| Virtus.pro invite #37 / 1359 | Aug 3 #37 / 1359 | ✓ exact |
| "Ninjas in Pyjamas" absence | NiP is in the same Oct 5 file at **#18 / 1534** | ✗ omission (see B1) |

Invite snapshot identification independently confirmed: [Liquipedia TWC 2026](https://liquipedia.net/counterstrike/Thunderpick/World_Championship/2026) lists invite route "VRS Global (Aug. 2026)"; [pley.gg](https://pley.gg/cs2/thunderpick-world-championship-2026/): "Seven teams were invited through the global Valve Regional Standings in August."

### A2. Rosters and real names

| Claim | Source checked | Verdict |
|---|---|---|
| Falcons roster karrigan/NiKo/m0NESY/TeSeS/kyousuke + coach zonic | VRS Oct 5 row #6; [Liquipedia participants](https://liquipedia.net/counterstrike/Thunderpick/World_Championship/2026) (roster + "Denmark zonic Coach"); [cs2news.com](https://cs2news.com/news/zonic-falcons-hierarchy-m0nesy-main-player) | ✓ |
| karrigan=Finn Andersen, NiKo=Nikola Kovač, m0NESY=Ilya Osipov, TeSeS=René Madsen, kyousuke=Maksim Lukin, zonic=Danny Sørensen | [csspot.org](https://csspot.org/teams/teamfalcons/), [cs2news.com](https://cs2news.com/news/zonic-falcons-hierarchy-m0nesy-main-player), [pley.gg](https://pley.gg/cs2/falcons/) | ✓ all five + coach |
| Legacy roster arT/dumau/latto/n1ssim/try | VRS Oct 5 row #2 (identical) | ✓ |
| FURIA FalleN/KSCERATO/yuurih/YEKINDAR/molodoy | VRS Oct 5 row #7 | ✓ |
| Aurora XANTARES/woxic/Jimpphat/kyxsan/Wicadia | VRS Oct 5 row #9 | ✓ |
| BetBoom Boombl4/zorte/d1Ledez/Magnojez/S1ren | VRS Oct 5 row #11 | ✓ |
| 9z max/dgt/meyern/luchov/HUASOPEEK | VRS Oct 5 row #17 | ✓ |
| VP mir/b1st/F0R3VER/AquaRS/tO0RO | VRS Oct 5 row #51 | ✓ (roster), participation stale (B1) |
| **PARIVISION roster Jame/FL1T/HObbit/xiELO/zweih** | **VRS Oct 5 row #36: FL1T, Jame, slaxejezzz, xiELO, zweih — no HObbit** | ✗ **conflict** (B4). Note [critfeed (Oct 13)](https://critfeed.com/thunderpick-world-championship-2026/) repeats HObbit; official VRS disagrees; VRS Sep 7 still had HObbit + slaxejezzz. Roster in flux; official source wins |
| "Signed Major Champion HObbit permanently on Sep 17, 2026" | Contradicted by official VRS Oct 5 roster (HObbit absent) | ✗ conflict (B4) |
| "Rio 2022 Major winning core (Jame, dastan, FL1T)" | Jame+FL1T were Outsiders Rio 2022 champions; dastan coach | plausible, **unverified** in this session (no primary source fetched) |
| `hltv_rank_sept` values (Falcons 5, Legacy 6, FURIA 4, Aurora 9, BetBoom 15, 9z 16, PARI 19, VP 50) | HLTV ranking archive not reachable from sandbox | **unverified** |

### A3. Results-history claims

| Claim | Source checked | Verdict |
|---|---|---|
| Falcons "IEM Cologne Major 2026 Champions (June 21, 2026, 3-0 vs FURIA)" | [HLTV news 44972](https://www.hltv.org/news/44972/falcons-sweep-furia-to-win-iem-cologne-major) (via [YouTube post](https://www.youtube.com/post/UgkxC2TepoBM9IpE0I36o82vflsThm-BXqGn)); [vpesports](https://vpesports.com/more-esports/falcons-are-iem-cologne-major-2026-champions) (13-8 ×3, MVP m0NESY); [EGW](https://egamersworld.com/counterstrike/news/35641/falcons-defeat-furia-to-win-iem-cologne-major-2026-O0_LH-eP2) | ✓ true |
| Falcons "PGL Bucharest 2025 Champions" | [BLAST.tv](https://blast.tv/cs/news/falcons-win-pgl-bucharest-with-3-0-over-g2) (Apr 13 2025, 3-0 vs G2); [escharts](https://escharts.com/news/pgl-bucharest-2025-viewership) | ✓ true |
| Falcons "Won all 4 head-to-head series vs FURIA in 2026" | Only the Cologne final 3-0 confirmed; full H2H count needs HLTV team page | **unverified count** |
| FURIA "Defending TWC Champions (Won TWC 2025 in Malta 3-2 vs NAVI)" | [escharts](https://escharts.com/news/thunderpick-world-championship-2025-viewership) (0:2→3:2 reverse sweep, decider Train 13:1); [Hotspawn news](https://www.hotspawn.com/counter-strike/news/furia-reverse-sweep-navi-to-win-thunderpick-world-championship-2025); [prnewswire Aug 13 2026](https://www.prnewswire.com/news-releases/thunderpick-world-championship-2026-returns-to-malta-with-1-million-prize-pool-302850259.html) | ✓ true |
| FURIA "Cologne Major 2026 Grand Finalists (Runner-up to Falcons)" | same Cologne sources | ✓ true |
| FURIA "StarSeries Fall 2026 3rd place" | [fragster](https://www.fragster.com/vitality-win-starseries-fall-2026/) standings table (3rd FURIA $35k); [tips.gg](https://tips.gg/article/vitality-defeat-aurora-in-the-final-to-lift-the-starladder-starseries-fall-2026-trophy-event-story/) | ✓ true |
| Legacy "FISSURE Playground 3 Champions (Sep 13, 2026, 3-0 vs G2; latto MVP)" | [HLTV news 45509](https://www.hltv.org/news/45509/legacy-sweep-g2-to-lift-fissure-playground-3-trophy); [NewsBreak/Field Level](https://www.newsbreak.com/field-level-media-353847889/4883683917484-legacy-sweep-g2-to-win-fissure-playground-3); [vloot](https://blog.vloot.io/fissure-playground-3-results/) | ✓ true |
| Legacy "Three consecutive tournament titles won in China" | HLTV 45509: "third title on Chinese soil after claiming the CAC 2025 and 2026 trophies" | ✓ true (3 China titles; "consecutive" phrasing loose — CAC 2025, CAC 2026, FP3) |
| Aurora "StarSeries Fall 2026 Grand Finalists (Runner-up 1-3 to Vitality, Sep 20)" | [fragster](https://www.fragster.com/vitality-win-starseries-fall-2026/) (Vitality 3-1 Aurora, Barcelona); [skin.club](https://community.skin.club/en/news/vitality-beat-furia-to-reach-grand-final-at-starladder-starseries-fall-2026) | ✓ true |
| Aurora "Top-10 Global VRS" | VRS Aug 3 #10, Oct 5 #9 | ✓ true |
| BetBoom "FISSURE Playground 3 Semifinalists (3rd-4th, Sep 13, 2026)" | [vloot](https://blog.vloot.io/fissure-playground-3-results/) (G2 beat BETBOOM in SF: 13-7 Mirage lost, 16-13 OT Anubis, 13-7 Ancient) | ✓ true |
| BetBoom "Cologne Major 2026 playoff qualification with stand-in adversity" | Playoff berth ✓ ([EGW prize list](https://egamersworld.com/counterstrike/news/35641/falcons-defeat-furia-to-win-iem-cologne-major-2026-O0_LH-eP2): 5th-8th BetBoom); "stand-in adversity" **unverified** | partially |
| BetBoom "VRS #11 entering Malta" | VRS Oct 5 #11 | ✓ true |
| 9z "Defeated Team Falcons 2-1 in PGL Astana group stage (May 10, 2026)" | [escorenews](https://escorenews.com/en/csgo/pgl-astana-2026/group-stage/falcons-vs-9z-650158) (FLC 1:2 9z, 2026-05-10, map scores); [strafe](https://www.strafe.com/news/read/team-falcons-lose-to-9z-globant-in-pgl-astana-2026-swiss-stage/); [Liquipedia PGL Astana](https://liquipedia.net/counterstrike/PGL/2026/Astana) | ✓ true (sources call it Swiss stage; model says "group stage" — trivial) |
| 9z "Highest ranked South American pure roster at invitation time (VRS #4)" | Aug 3: 9z #4 (Legacy #7 next SA team) | ✓ true ("pure roster" qualifier unverified) |
| 9z "ESL Pro League Season 24 main event participant" | Not checked | **unverified** |
| VP "TWC 2026 Closed Qualifier Winners (Defeated HOTU 3-0 in Grand Final, Sep 13, 2026)" | [Hotspawn news](https://www.hotspawn.com/counter-strike/news/virtus-pro-qualify-for-thunderpick-wc-2026-after-closed-qualifier-victory); [Hotspawn qualifier page](https://www.hotspawn.com/counter-strike/tournament/thunderpick-world-championship-2026-closed-qualifier) (16 teams, GAM3RS_X, Sep 9–13, final Bo5); [fragster](https://www.fragster.com/virtus-pro-thunderpick-world-championship-2026/) (Dust2 16-14, Anubis 13-6, Ancient 16-13) | ✓ true |
| VP "Swept 5 consecutive series after opening loss to K27" | fragster: lost 1-2 to K27; then BESTIA, K27, FOKUS, HEROIC, HOTU = 5 straight | ✓ true |
| VP "First major international LAN qualification since IEM Chengdu 2025" | Not checked | **unverified** |
| TWC structure: Oct 14–18, Malta, $1M, 8 teams, organizer GAM3RS_X, BLAST (Arena) Studios | [Liquipedia](https://liquipedia.net/counterstrike/Thunderpick/World_Championship/2026); [prnewswire](https://www.prnewswire.com/news-releases/thunderpick-world-championship-2026-returns-to-malta-with-1-million-prize-pool-302850259.html); [HLTV events](https://www.hltv.org/events) | ✓ true |
| Cited URLs (VRS GitHub file, HLTV event 8932, Liquipedia TWC, prnewswire field reveal) | VRS + Liquipedia + HLTV confirmed live this session; prnewswire field-reveal headline confirmed via [g3newswire reprint (Sep 17)](https://g3newswire.com/thunderpick-confirms-eight-team-field-for-1m-malta-finals/) | ✓ exist (prnewswire exact URL not fetched from sandbox) |

### A4. Origination engine arithmetic — reproducible ✓

Recomputed from `scripts/originate_lines.py` + `data/teams_verified.json`:
effective_rating = 0.75·VRS_oct05 + 0.25·VRS_invite + hardcoded momentum bonus (Falcons +35, Legacy +25, FURIA +15, Aurora +10, VP −10, others 0); p = logistic Bradley-Terry with 400 divisor, clamped [0.08, 0.92]; decimal = 1/p floored at 1.02; overround target 4.5%.
Spot check (Falcons vs Legacy): 1904.75 vs 1916.5 → diff −11.75 → p 0.4831/0.5169 → 1.98/1.85 decimals, +107/−107 American. Matches `originated_matches.json` exactly. American↔decimal conversions follow the standard formulas (independently confirmed against the Smarkets reference cited by audit 1916f96c).

Caveats (disclosed here, not on the root site's data):
- The momentum bonuses are **unsourced subjective constants**; the JSON labels the method "Tier-1 LAN momentum adjustments", which overstates their provenance.
- Feeding raw VRS point differences (~tens of points) into an Elo/400-scale logistic compresses gaps: e.g. Legacy−Falcons 11.75 pts → 51.7/48.3, i.e. near coin-flip for #2 vs #6. Actual markets for real fixtures diverge substantially from the model where comparable (see Section E).
- All 28 pairings are hypothetical; 7 involve a non-participating team (B1) and 7 real NiP pairings are missing entirely.

---

## Section B — Major irregularities (root model, PR #7)

**B1 (critical) — Stale tournament field: Virtus.pro withdrew Oct 9; Ninjas in Pyjamas replaced them.**
- [HLTV news 45706 (Oct 12)](https://www.hltv.org/news/45706/thunderpick-world-championship-teams-format-schedule-prizes-talent-fantasy): "Ninjas in Pyjamas were brought in to replace Virtus.pro, whose withdrawal followed visa issues affecting Aleksandr 'AquaRS' Kovalev and health problems that forced Dias 'F0R3VER' Kutubay to temporarily step away." Groups: A Falcons/NIP/9z/Aurora, B Legacy/PARIVISION/FURIA/BetBoom.
- [pley.gg (updated Oct 12)](https://pley.gg/cs2/thunderpick-world-championship-2026/): "On 9 October, Virtus.pro withdrew… the spot went to the next eligible European team in the VRS, Ninjas in Pyjamas" (#18).
- [fragster (Oct 10)](https://www.fragster.com/nip-replace-virtus-pro-thunderpick-world-championship/), [esports.gg (Oct 12)](https://esports.gg/news/counter-strike-2/cs2-thunderpick-world-championship-2026-results/), [cybersport.in (Oct 12)](https://cybersport.in/9975-falcons-vs-nip-thunderpick-world-championship-2026-kicks-off/) — same.
- Independently corroborated by live market infrastructure: Hotspawn's own board carries fixture 1080177 **Falcons vs Ninjas in Pyjamas** (Oct 14 11:00 UTC, from raw lobby evidence `docs/evidence/probe/lobby.txt`), and Polymarket's Falcons–NiP market shows **$104.70K volume** (`analysis/odds_observations.json` OBS-026).
- Consequence: `origination_summary.json` (`generated_utc: 2026-10-13T18:00:00Z`) and root `index.html` price Virtus.pro (outright 0.3%, 277.13) — a team not in the event — and contain **no line for NiP**, which plays the day-1 fixture the pick'em board actually asks about. All 12 VP pairings in `originated_matches.json` are impossible; 7 NiP pairings (including the real Falcons–NiP opener) are missing.
- The model's VRS data for VP is accurate, and VP genuinely won the qualifier (A3) — the failure is freshness, not fabrication of that team's stats.

**B2 — `IRREG-001` premise false at generation time.** "As of October 13, 2026, the specific group compositions (Group A vs Group B) and opening head-to-head fixtures have not been officially drawn/published" — groups and all four opening fixtures were published by Oct 12 at the latest (HLTV news 45706 Oct 12 14:52; pley.gg Oct 12; EGW blog Oct 12; fragster Oct 10). The 28-pairing workaround was built on a premise that was already outdated when the file was generated (Oct 13 18:00Z). Actual opening fixtures (all BO3, verified identical across Hotspawn UTC / pley.gg CEST / EGW EEST / HLTV CEST):
Oct 14 — 9z vs Aurora 08:30 UTC · Falcons vs NiP 11:00 UTC · Legacy vs PARIVISION 13:30 UTC · FURIA vs BetBoom 16:00 UTC.

**B3 — `IRREG-002` premise false at generation time.** "Traditional retail sportsbooks … have not posted published fixed match lines prior to the official group draw." The draw was public (B2), and match lines were posted: Thunderpick (title sponsor's own sportsbook) match pages with American odds — captured twice independently (audit `1916f96c` via fetch_page on Oct 13; this session via search snippets, OBS-001/002) — plus bwin (OBS-015) and Polymarket match markets (OBS-026: $104.70K volume). The repo's own commit `e2c07f2` ("pinnacle+polymarket+bovada extractors (raw quotes…)") contradicts the claim that no feeds existed.

**B4 — PARIVISION roster conflict with the official source the model itself cites.** VRS Oct 5 lists FL1T, Jame, **slaxejezzz**, xiELO, zweih; `teams_verified.json` lists Jame, FL1T, **HObbit**, xiELO, zweih and claims HObbit was "signed permanently on Sep 17, 2026". Secondary coverage conflicts too ([critfeed](https://critfeed.com/thunderpick-world-championship-2026/) also shows HObbit). Per policy, the official Valve file governs: root-model PARIVISION roster is **wrong/unverified**; flag, do not adopt.

**B5 — Compliance block overstates verification.** `origination_summary.json.standards_compliance` asserts `"verified_against_official_sources": true` and `"no_hallucinations": true`. Most individual facts did verify (Section A), but the participating-field claim was contradicted by the model's own cited sources (HLTV event page, Liquipedia) at generation time, the PARIVISION roster contradicts its cited VRS file, and the "momentum adjustments" are unsourced constants. Correct labeling would be "partially verified; field stale; see flags". This is exactly the concern ef111e02 recorded as **F14** (`docs/flags.html`) — this audit confirms F14 with primary evidence and adds B1–B4 specifics.

---

## Section C — PR #8/#10 docs dashboard (session ef111e02)

- **`docs/data/matches.json` VERIFIED**: re-parsed the raw lobby evidence (`docs/evidence/probe/lobby.txt`, script#ng-state embedded API payload, 86 fixture records) and compared every field: id sets identical (86/86), team_a/team_b, start_utc (from `scheduled_start_time` epoch ms), source_status, competition name, best_of — **0 mismatches**. The 27 visible-card subset, lock times and lock offsets also trace to the same payload.
- **`docs/data/quotes.json`**: the two Thunderpick quotes (9z +280/−455; Astralis −1250/+530) match this session's independently captured OBS-001/OBS-002 exactly (same URLs, same numbers). "reference only" status and null `quoted_at` are appropriately conservative.
- **`docs/data/health.json`**: accurate (lobby cached Age 3839 at 17:51:30 GMT probe; Thunderpick direct probe 403 Cloudflare — reproducible from this sandbox's constraints).
- Flags F01–F13 remain accurate descriptions of open gaps. **T-A now closes much of F01/F05–F08**: 24 of the 27 current fixtures now have sourced two-sided lines with per-observation provenance (`analysis/lines.json`), 3 remain blank-and-flagged (Black Phoenix–6666 no line; FORZE Reload–LFO 10 no line; Voca–Phantom one-sided only).
- All-odds-null invariants in `tests/test_project.py` were correct for PR #8's state; they must be amended in T-C when sourced lines are integrated (new invariant: no odds/probability without source URL + observation timestamp).

## Section D — Audit handoffs

**audits/1916f96c** (fetch_page evidence, Oct 13): methodologically sound; every quote it published is corroborated by this session's independent capture. Two of its open flags can now be advanced:
- *4-hour time-label discrepancy* (Thunderpick "October 14, 04:30" vs Hotspawn detail "08:30 / 14 OCT"; Astralis 06:00 vs 10:00): resolved consistently as **Thunderpick displaying US Eastern Daylight Time (UTC−4)** — 04:30 EDT = 08:30 UTC = 10:30 CEST ([pley.gg schedule](https://pley.gg/cs2/thunderpick-world-championship-2026/) shows 10:30 CEST for 9z–Aurora), and 06:00 EDT = 10:00 UTC = 12:00 CEST for Astralis–Sashi. Both fixtures show the identical −4h offset; Hotspawn times independently confirmed UTC via Polymarket/EGW anchors (see `analysis/odds_observations.json` timezone notes). Marked resolved-with-evidence, not inferred from a single sample.
- *"Single sportsbook only / no second operator"*: superseded — T-A adds Polymarket, bwin, EGamersWorld-aggregated books, and RU aggregators for 24 fixtures.

**audits/1d4de836**: sound for its observation date. Its statement that "only 1 team (Virtus.pro) qualified for the Malta Finals" via the qualifier portal was true (VP won the Sep 13 qualifier final 3-0 vs HOTU) but is **superseded** by the Oct 9 withdrawal (B1). Its "Hotspawn sandbox direct HTTPS returns TLS EOF" observation remains accurate for this sandbox as well.

## Section E — Cross-checks: T-A market consensus vs root synthetic model vs crowd

| Fixture (real, on the board) | T-A sourced consensus (de-vigged) | Root synthetic model | Hotspawn crowd (context only) |
|---|---|---|---|
| 9z vs Aurora | 26.0 / 74.0 (2 src) | 35.9 / 64.1 (VRS-only) | 0 / 100 |
| Falcons vs NiP | 78.0 / 22.0 (2 src) | **no line (NiP absent)** | 94 / 6 |
| Legacy vs PARIVISION | 55.6 / 44.4 (2 src) | no such pairing (model has Legacy-VP instead) | 88 / 12 |
| FURIA vs BetBoom | 66.7 / 33.3 (2 src) | 60.2 / 39.8 (model) | 94 / 6 |
| Astralis vs Sashi (SPB III) | 85.1 / 14.9 (3 src) | out of model scope | 100 / 0 |

The synthetic model is directionally reasonable on the three comparable TWC pairings but systematically compressed toward 50/50 (B4 caveat), and it cannot serve the actual pick'em board because it prices a withdrawn team and omits a participating one. **T-A's `analysis/lines.json` is the only dataset in the repo that covers the real 27-fixture board with sourced market lines.**

Crowd-vs-book divergences worth surfacing on the site (crowd % from raw lobby evidence, `analysis/hotspawn_picked_pct.json`; never used as probability per requirements):
- **ex-Keyd Stars vs Galorys**: crowd 83% on ex-Keyd; all books price Galorys favorite (consensus ex-Keyd 36.8%). Crowd on the underdog — largest divergence on the board. (Note: a prior internal memo had this pair reversed; the raw API payload `participants0_picked_percent=83` binds to ex-Keyd Stars explicitly.)
- **Gothic vs Lavked**: crowd 13/88 vs single-source market 52.8/47.2.
- **MIBR vs BC.Game**: crowd 32/68 vs books 59.3/40.7 (4 sources) — direct contradiction; books firmly MIBR.
- **HOTU vs Fnatic**: crowd 10/90 vs market 46.5/53.5.
- **Elisa Group A trio**: WROT–EAC (crowd 71 vs market 48.6), WROT–ENCE (31 vs 56.4), EAC–ENCE (29 vs 60.6) — crowd and (thin, $0-volume Polymarket) books disagree in direction on all three; both sides low-confidence; flagged in `analysis/lines.json`.
- Crowd cells with `total_picks` ≤ 25 (most of them) are tiny samples — a 100/0 cell can be ~20 votes. Displayed with pick counts for this reason.

## Section F — Integration consequences (for T-C)

1. Do **not** merge root `data/*.json` into the docs dashboard as verified lines; keep F14 open, now backed by B1–B5 primary evidence. Root site pages stay as-is (other session's scope) with the review findings published under Flagged for Review.
2. Integrate `analysis/lines.json` (24 priced fixtures + 3 blank-and-flagged + 59 stale blank-and-flagged) with per-row source URLs, observation timestamps, confidence tiers and flags.
3. Publish divergence context (crowd %, with total_picks and the never-used-as-probability disclaimer) alongside the market consensus.
4. Carry forward resolved items: Thunderpick timezone = EDT (D), TWC schedule verified across 4 independent timezones (B2), Elisa prize-pool discrepancy $17,521 (Hotspawn) vs $17,348 (HLTV) remains open (OBS-057/058), Liquipedia HOTU–fnatic 11:00 UTC vs Hotspawn 10:00 UTC remains open (OBS-063).

## Source register (primary links used in this review)

- Valve VRS (official): [Oct 5 global standings](https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/invitation/2026/standings_global_2026_10_05.md) · [Sep 7](https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/invitation/2026/standings_global_2026_09_07.md) · [Aug 3](https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/invitation/2026/standings_global_2026_08_03.md) (fetched raw via api.github.com)
- HLTV: [news 45706 field/groups](https://www.hltv.org/news/45706/thunderpick-world-championship-teams-format-schedule-prizes-talent-fantasy) · [news 45509 FP3](https://www.hltv.org/news/45509/legacy-sweep-g2-to-lift-fissure-playground-3-trophy) · [news 44972 Cologne Major](https://www.hltv.org/news/44972/falcons-sweep-furia-to-win-iem-cologne-major) · [event 8932](https://www.hltv.org/events/8932/thunderpick-world-championship-2026)
- Liquipedia: [TWC 2026](https://liquipedia.net/counterstrike/Thunderpick/World_Championship/2026) · [PGL Astana 2026](https://liquipedia.net/counterstrike/PGL/2026/Astana)
- Tournament/field news: [pley.gg](https://pley.gg/cs2/thunderpick-world-championship-2026/) · [fragster VP→NiP](https://www.fragster.com/nip-replace-virtus-pro-thunderpick-world-championship/) · [fragster StarSeries](https://www.fragster.com/vitality-win-starseries-fall-2026/) · [esports.gg](https://esports.gg/news/counter-strike-2/cs2-thunderpick-world-championship-2026-results/) · [cybersport.in](https://cybersport.in/9975-falcons-vs-nip-thunderpick-world-championship-2026-kicks-off/) · [critfeed](https://critfeed.com/thunderpick-world-championship-2026/) · [g3newswire field reveal](https://g3newswire.com/thunderpick-confirms-eight-team-field-for-1m-malta-finals/) · [prnewswire Aug 13](https://www.prnewswire.com/news-releases/thunderpick-world-championship-2026-returns-to-malta-with-1-million-prize-pool-302850259.html)
- Results history: [escharts TWC 2025](https://escharts.com/news/thunderpick-world-championship-2025-viewership) · [Hotspawn TWC 2025 final](https://www.hotspawn.com/counter-strike/news/furia-reverse-sweep-navi-to-win-thunderpick-world-championship-2025) · [Hotspawn VP qualifier](https://www.hotspawn.com/counter-strike/news/virtus-pro-qualify-for-thunderpick-wc-2026-after-closed-qualifier-victory) · [Hotspawn qualifier page](https://www.hotspawn.com/counter-strike/tournament/thunderpick-world-championship-2026-closed-qualifier) · [fragster VP qualifier](https://www.fragster.com/virtus-pro-thunderpick-world-championship-2026/) · [vloot FP3](https://blog.vloot.io/fissure-playground-3-results/) · [NewsBreak FP3](https://www.newsbreak.com/field-level-media-353847889/4883683917484-legacy-sweep-g2-to-win-fissure-playground-3) · [skin.club Cologne](https://community.skin.club/en/news/falcons-vs-furia-iem-cologne-major-2026-grand-final) · [vpesports Cologne](https://vpesports.com/more-esports/falcons-are-iem-cologne-major-2026-champions) · [hellcase Cologne](https://hellcase.com/blog/esports/iem-cologne-2026-grand-final/) · [EGW Cologne](https://egamersworld.com/counterstrike/news/35641/falcons-defeat-furia-to-win-iem-cologne-major-2026-O0_LH-eP2) · [skin.club StarSeries](https://community.skin.club/en/news/vitality-beat-furia-to-reach-grand-final-at-starladder-starseries-fall-2026) · [tips.gg StarSeries](https://tips.gg/article/vitality-defeat-aurora-in-the-final-to-lift-the-starladder-starseries-fall-2026-trophy-event-story/) · [escorenews PGL Astana](https://escorenews.com/en/csgo/pgl-astana-2026/group-stage/falcons-vs-9z-650158) · [strafe PGL Astana](https://www.strafe.com/news/read/team-falcons-lose-to-9z-globant-in-pgl-astana-2026-swiss-stage/) · [BLAST.tv Bucharest](https://blast.tv/cs/news/falcons-win-pgl-bucharest-with-3-0-over-g2) · [escharts Bucharest](https://escharts.com/news/pgl-bucharest-2025-viewership)
- Rosters/names: [cs2news zonic](https://cs2news.com/news/zonic-falcons-hierarchy-m0nesy-main-player) · [csspot Falcons](https://csspot.org/teams/teamfalcons/) · [pley.gg Falcons](https://pley.gg/cs2/falcons/)
- EGW TWC blog (groups/schedule EEST + odds widgets): [egamersworld.com blog](https://egamersworld.com/blog/thunderpick-world-championship-2026-schedule-teams-3y5NuMb4pp)
- Local evidence: `docs/evidence/probe/lobby.txt` (raw Hotspawn lobby payload), `analysis/odds_observations.json` (OBS-001…066), `analysis/lines.json`, `analysis/hotspawn_picked_pct.json`, `audits/1916f96c/REPORT.md`, `audits/1d4de836/**`
