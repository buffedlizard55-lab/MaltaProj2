# Independent Line-by-Line Verification Report — session `8e7a652d`

**Branch:** `arena/8e7a652d-maltaproj2` · **Verification window:** 2026-10-13 18:07–18:50 UTC
**Scope:** all data published on `main` as of merge `d530651` (PRs #2, #7, #8, #10, #11, #12, #14), plus the active parallel branch `arena/0c90448b-maltaproj2` (odds collection, not yet merged).
**Method:** every claim re-checked against an official primary source (Valve's official VRS GitHub repository, HLTV, Liquipedia, Thunderpick's official betting site, Pinnacle's public guest API, the live Hotspawn lobby). Nothing below is inferred; where a value could not be confirmed it is listed as unverified in the irregularity register.

---

## A. Valve Regional Standings (VRS) — VERIFIED EXACT (8/8 teams)

Source: official Valve repository `ValveSoftware/counter-strike_regional_standings`, files
`invitation/2026/standings_global_2026_10_05.md` and `invitation/2026/standings_global_2026_08_03.md`
(fetched via the GitHub API on 2026-10-13; verbatim copies archived in [`evidence/`](evidence/)).

| Team (as in Valve table) | Valve VRS Oct 5 | Published in repo (`data/teams_verified.json`) | Result |
|---|---|---|---|
| Legacy | #2 / 1931 pts | #2 / 1931 | ✅ exact |
| Falcons | #6 / 1843 pts | #6 / 1843 | ✅ exact |
| FURIA | #7 / 1829 pts | #7 / 1829 | ✅ exact |
| Aurora | #9 / 1716 pts | #9 / 1716 | ✅ exact |
| BETBOOM | #11 / 1596 pts | #11 / 1596 | ✅ exact |
| 9z | #17 / 1543 pts | #17 / 1543 | ✅ exact |
| Ninjas in Pyjamas | #18 / 1534 pts | #18 / 1534 (added by PR #12) | ✅ exact |
| PARIVISION | #36 / 1411 pts | #36 / 1411 | ✅ exact |
| Virtus.pro (withdrawn) | #51 / 1309 pts | #51 / 1309 | ✅ exact |

Aug 3 invitation-snapshot points also verified exact for every team that carries them
(Falcons 1950 @#2, Legacy 1773 @#7, FURIA 1771 @#8, Aurora 1690 @#10, 9z 1847 @#4, PARIVISION 1685 @#12, Virtus.pro 1359 @#37).

**Rosters:** the 5-man rosters in Valve's Oct 5 table match `data/teams_verified.json` exactly for 7/8 teams.
PARIVISION differs (Valve: FL1T, Jame, slaxejezzz, xiELO, zweih vs published: HObbit for slaxejezzz) — this is **correctly flagged** on the site: PARIVISION announced on 2026-09-17 that HObbit signed permanently and slaxejezzz was benched ([PARIVISION announcements, Sep 17 2026](https://www.shanethegamer.com/news/parivision-hobbit-slaxejezzz-benched-cs2-roster/); [Liquipedia PARIVISION timeline](https://liquipedia.net/counterstrike/PARIVISION): "September 17th - PARIVISION bench slaxejezzz and sign HObbit"). Valve's Oct 5 table still lists the pre-transfer five.

Links for manual review:
- https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/invitation/2026/standings_global_2026_10_05.md
- https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/invitation/2026/standings_global_2026_08_03.md
- Local verbatim copies: [evidence/standings_global_2026_10_05.md](evidence/standings_global_2026_10_05.md), [evidence/standings_global_2026_08_03.md](evidence/standings_global_2026_08_03.md)

## B. TWC 2026 event facts — VERIFIED

Cross-checked on [HLTV event 8932](https://www.hltv.org/events/8932/thunderpick-world-championship-2026) and
[Liquipedia](https://liquipedia.net/counterstrike/Thunderpick/World_Championship/2026): Oct 14–18 2026, Malta
(BLAST Arena Studios, Attard), $1,000,000, 8 teams, organizer GAM3RS_X, S-Tier / Valve Tier 1. Both match the published site content.

**Withdrawal/replacement (verified):** Liquipedia event note — "October 9th - Virtus.pro withdraw from the event due to health and visa issues; they are replaced by Ninjas in Pyjamas." PR #12 already propagated this to the root site (NiP #18/1534, `data/withdrawn_team.json`). ✅ consistent.

**Groups (verified on Liquipedia):** Group A = Falcons, 9z, Aurora, NiP · Group B = Legacy, FURIA, BetBoom, PARIVISION. ✅ matches root site (post-PR #12).

## C. Opening fixtures — TRIPLE-VERIFIED

Each of the four opening matches is confirmed on three independent families of sources:
(1) the live [Hotspawn pick'em lobby](https://play.hotspawn.com/lobby) (fixture discovery only),
(2) [Liquipedia](https://liquipedia.net/counterstrike/Thunderpick/World_Championship/2026) / HLTV match pages
([2399384](https://www.hltv.org/matches/2399384/9z-vs-aurora-thunderpick-world-championship-2026),
[2399385](https://www.hltv.org/matches/2399385/falcons-vs-ninjas-in-pyjamas-thunderpick-world-championship-2026),
[2399386](https://www.hltv.org/matches/2399386/legacy-vs-parivision-thunderpick-world-championship-2026),
[2399387](https://www.hltv.org/matches/2399387/furia-vs-betboom-thunderpick-world-championship-2026)),
(3) Pinnacle's open markets (matchup IDs 1638111785 / 1638111674 / 1638111786 / 1638111787) whose `cutoffAt` timestamps equal the fixture kickoffs.

| Match (BO3) | Kickoff UTC | Hotspawn | Liquipedia/HLTV | Pinnacle cutoff | Result |
|---|---|---|---|---|---|
| 9z vs Aurora | 2026-10-14 08:30 | ✅ | ✅ | 2026-10-14T08:30Z | ✅ |
| Falcons vs NiP | 2026-10-14 11:00 | ✅ | ✅ | 2026-10-14T11:00Z | ✅ |
| Legacy vs PARIVISION | 2026-10-14 13:30 | ✅ | ✅ | 2026-10-14T13:30Z | ✅ |
| FURIA vs BetBoom | 2026-10-14 16:00 | ✅ | ✅ | 2026-10-14T16:00Z | ✅ |

## D. Betting lines — INDEPENDENTLY CAPTURED & CROSS-CHECKED

All raw prices and de-vig mathematics are in [`verified_market_lines.json`](verified_market_lines.json).
De-vig method: proportional (multiplicative) margin removal, `fair_i = (1/dec_i)/(1/dec_a + 1/dec_b)` (formula reference: [Smarkets](https://help.smarkets.com/hc/en-gb/articles/214058369-How-to-calculate-implied-probability-in-betting)).

| Match | Pinnacle (18:20Z) | Thunderpick (18:15Z) | Bovada (18:01Z) | bc.game/EGW (14:15Z) | Polymarket (14:15Z) | Consensus fair |
|---|---|---|---|---|---|---|
| 9z vs Aurora | +218/−275 | +280/−455 | 3.65/1.26 | 3.60/1.27 | 26c/75c | **26.4% / 73.6%** |
| Falcons vs NiP | −295/+233 | not captured | 1.2299/3.90 | 1.23/3.95 | 77c/24c | **75.0% / 25.0%** |
| Legacy vs PARIVISION | −129/+106 | not captured | 1.69/2.10 | 1.65/2.18 | 59c/42c | **56.1% / 43.9%** |
| FURIA vs BetBoom | −207/+168 | not captured | 1.3636/3.00 | 1.37/2.96 | — | **67.2% / 32.8%** |

Verification notes:
- The Thunderpick 9z–Aurora quote (+280/−455) matches the earlier reference quote in `docs/data/quotes.json` exactly — that stored quote is confirmed still live at 18:15Z. Same page also carries map handicap (−1.5: +600 / +1.5: −118), totals O/U 2.5 maps (+120/−172) and Map-1 winner (+220/−333) markets.
- Pinnacle prices were fetched directly from the public guest API (no authentication), status `open`, and are **American odds**. Session 0c90448b's `data/odds.json` stores identical Pinnacle quotes under a field named `decimal_odds_a/b` — a mislabel (see IR-V2). Its 18:01Z captures (−150/+123 for Legacy–PARIVISION etc.) are consistent with my 18:20Z captures after normal line movement.
- Thunderpick outright Winner market captured 18:25Z (see next section).

**Verified outright market (Thunderpick, official tournament sponsor bookmaker):**
[Falcons +150 · FURIA +325 · Legacy +375 · Aurora +500 · BB Team +1100 · PARIVISION +1900 · 9z +2900 · NiP +2900](https://thunderpick.io/esports/cs2-betting/thunderpick-world-championship-2026/11024/outright/outrights/2734735) — book overround 121.25%; de-vigged fair probabilities: **Falcons 33.0% · FURIA 19.4% · Legacy 17.4% · Aurora 13.8% · BetBoom 6.9% · PARIVISION 4.1% · 9z 2.8% · NiP 2.8%**.

## E. Hotspawn pick'em lobby structure — VERIFIED LIVE

Fetched https://play.hotspawn.com/lobby at 18:10Z: "This week 60 matches", filter counts "All tiers (86) — S (4) · B (27) · C (55)", CS2 + LoL tabs, per-card points/tier/multiplier, lock countdowns (~6 min before kickoff per card, matching the epoch-derived `lock_offset_sec: 360`), and crowd pick percentages displayed on every card. The four TWC cards (tier S ×3, 7 pts, stage "Group Stage And Playoffs", multiplier ×1.25) list exactly the four verified fixtures. Crowd percentages are **not** used anywhere as a probability input. ✅ consistent with `audits/1d4de836/lobby-snapshot-audit.json` and `data/pickem_pool.json` (26 open CS2 fixtures).

## F. Context claims spot-checks — VERIFIED

- **Falcons, IEM Cologne Major 2026 champions, 3–0 vs FURIA, June 21 2026** — verified ([shanethegamer](https://www.shanethegamer.com/esports-news/iem-cologne-major-2026-falcons-furia-final/), [vpesports](https://vpesports.com/more-esports/falcons-are-iem-cologne-major-2026-champions); maps 13–8 ×3; m0NESY MVP). ✅
- **Legacy, FISSURE Playground 3 champions, 3–0 vs G2, Sep 13 2026, latto MVP** — verified ([esports-news.co.uk](https://esports-news.co.uk/2026/09/14/legacy-deliver-at-4-1-to-win-fissure-playground-3), [1vX.gg](https://1vx.gg/news/legacy-sweep-g2-3-0-to-win-fissure-playground-3-as-latto-takes-mvp); third title in China). ✅
- **PARIVISION HObbit/slaxejezzz, Sep 17 2026** — verified (see section A). ✅

## G. Model arithmetic — INTERNALLY CONSISTENT

`scripts/originate_lines.py` was re-run and its outputs recomputed independently from the verified inputs:
all 28 pairwise fair probabilities/odds and all 8 outright probabilities reproduce **exactly**
(logistic on effective rating = 0.75×VRS_Oct5 + 0.25×VRS_Aug3 + momentum bonuses; fair-prob clamps [0.08, 0.92];
4.5% two-way and 10% outright overrounds; outright softmax scale 130). Outright fair probabilities sum to 1.0000. ✅
All 15 unit tests pass (`python3 -m unittest discover tests/`; requires `beautifulsoup4`).

## H. Automated tests on merged main — PASS

`python3 -m unittest discover tests/` → 15/15 OK (898abb4f site integrity, ef111e02 project tests).

---

## Irregularity register (this session's findings)

| ID | Finding | Severity | Action taken / recommendation |
|---|---|---|---|
| IR-V1 | **Root pairwise model diverges materially from the real market.** Model: Legacy 92.0% vs PARIVISION; real Pinnacle market at 18:20Z implies 53.7% fair. Model outright favorite Legacy 34.4%; verified Thunderpick outright market has Falcons 33.0% favorite and Legacy 17.4%. The VRS-point logistic with a 400-point scale drastically overstates favorites (see also the 0.92 clamp). | High | Published on the verification page; recommendation: for the four **actual** fixtures use the market-anchored consensus (this page / `pickem/`), and treat the root 28-pairing model as a labeled hypothetical only. Already partially mitigated by PR #12's "Derived, not a bookmaker quote" labels. |
| IR-V2 | Pinnacle quotes in session 0c90448b's `data/odds.json` are stored in fields named `decimal_odds_a/b` but are **American odds** (e.g. −150/+123). Any consumer treating them as decimals would compute garbage. | High (data quality) | Flagged; correct decimal conversions published in `verified_market_lines.json`. Owner session notified via COORDINATION.md. |
| IR-V3 | Thunderpick outright page lists "Ninjas in Pyjamas +2900" in the Winner market but a boosted special "NiP to win the tournament +5000" on the same page — internally inconsistent pricing (stale cell or extraction ambiguity). | Medium | Flagged; Winner market used for the de-vig table with a note. |
| IR-V4 | **LoL coverage gap.** The pick'em lobby lists 245 upcoming LoL fixtures (plus 27 upcoming CS2) — the published boards price the 26 open CS2 fixtures only. Bovada captured several LoL lobby fixtures (e.g. KT Rolster vs BNK FearX, JD Gaming vs Rogue Warriors) on the unmerged 0c90448b branch. | Medium | Left blank rather than inferred; gap noted for follow-up integration of 0c90448b's collection. |
| IR-V5 | **Line movement is rapid.** Pinnacle Legacy–PARIVISION moved −150/+123 (18:01Z) → −129/+106 (18:20Z) in 19 minutes. All published prices are point-in-time captures and must be timestamped (they are). | Medium | Timestamps retained everywhere; page carries an explicit point-in-time disclaimer. |
| IR-V6 | Bovada capture contains 4 price rows per match with no explicit market label (likely headline + alternate/period lines); the first row per match was taken as the headline line. | Medium | Flagged; cross-checked against Pinnacle/bc.game — deviations are within normal book-to-book spread. |
| IR-V7 | Root `data/external_outrights_snapshot.json` (FreeTips secondary article, Oct 11, unattributed bookmaker) differs from the directly verified Thunderpick outright market — most notably 9z 14.00 vs verified 30.00 and Legacy 3.80 vs 4.75. | Medium | The verified Thunderpick capture is published as the primary outright source; FreeTips snapshot retained as flagged secondary (as PR #12 already labeled it). |
| IR-V8 | `docs/data/matches.json` (86 fixtures) is a June-2026 API payload — 60 of 86 kickoffs precede the capture date (stale source entries). Already flagged by the LineWatch audits (F02/F09). | Low | Confirmed; no change needed. |
| IR-V9 | `hltv_rank_sept` fields (Falcons 5, Legacy 6, …) were not independently re-verified (HLTV ranking archive page is heavy and partially JS-loaded). | Low | Left as published; not used in any probability computation on this site. |
| IR-V10 | Sandbox `curl` cannot reach non-GitHub hosts (TLS allowlist); all non-GitHub evidence in this report was captured with the platform fetch tool or by hosted GitHub Actions runners, as documented by earlier audit sessions. | Info | Documented; no bypass attempted anywhere. |

## Sign-off

Verified against official primary sources: Valve VRS (8/8 teams exact, 380-row Oct 5 table archived), TWC 2026
event facts, the NiP-for-Virtus.pro replacement, all four opening fixtures (three independent source families),
live bookmaker prices from Pinnacle, Thunderpick and Bovada plus the bc.game/Polymarket captures from PR #11,
the Hotspawn lobby structure, roster-transfer facts, and the internal arithmetic of the published model.
Unverified or contradictory items are blanked or flagged above — none are silently filled in.

— session `8e7a652d`, 2026-10-13
