# Independent official-source audit — session 1916f96c

Observed 2026-10-13 through the `fetch_page` research tool. This is a dated evidence handoff, **not a live feed or a claim of complete coverage**. Unknown fields remain `null` in `observations.json`. Do not label these observations current after their date of access.

## Integration ownership

The earlier session `ef111e02` owns the dashboard, source pipeline, tests, documentation and Pages integration. This session stopped overlapping implementation when it discovered that remote claim. Incorporate **only `audits/1916f96c/**`**, not this branch's root COORDINATION.md or duplicate probe workflow. Coordination message: [issue #3](https://github.com/buffedlizard55-lab/MaltaProj2/issues/3).

## Verified observations and limitations

| Observation | Verification / evidence | Official source |
|---|---|---|
| 26 upcoming match cards visible in the text representation | All three chunks of the unfiltered lobby read; 12 Closing Soon cards and 14 Upcoming cards transcribed row by row. Not a claim of complete lobby API coverage. | [Hotspawn lobby](https://play.hotspawn.com/lobby) |
| Lobby headline shows 60 matches this week; initial filters show 86 | Exact displayed counts observed, incompatible with a claim that the 26 visible upcoming cards are the entire inventory. Counts can change between requests. | [Hotspawn lobby](https://play.hotspawn.com/lobby) |
| Supplying `?game=lol` did not establish LoL coverage | Response still contained the same CS2-like match names and CS2/LoL labels; no confirmed parameter contract or LoL API established. No LoL matches invented. | [Lobby query inspected](https://play.hotspawn.com/lobby?game=lol) |
| 9z lobby identity explicitly linked as 9z Team on match detail | Detail heading `9z vs Aurora`, first team link text `9z Team`; official page title identifies Counter-Strike 2. Detail time label `08:30 / 14 OCT`. | [Hotspawn match detail](https://www.hotspawn.com/matches/9z-vs-aurora-thunderpick-world-championship-2026-1080176) |
| Astralis/Sashi match detail | Official page title identifies Counter-Strike 2; heading `Astralis vs Sashi`; second team link `Sashi Esport`; detail time label `10:00 / 14 OCT`. | [Hotspawn match detail](https://www.hotspawn.com/matches/astralis-vs-sashi-stake-pulse-beat-iii-1079438) |
| 9z Team +280, Aurora -455 | Explicit `Main` → `Match Winner` section on official sportsbook match page; `BO3`; `October 14, 04:30`. Two-sided pair observed together, not combined from different sources. | [Thunderpick 9z/Aurora market](https://thunderpick.io/esports/cs2-betting/thunderpick-world-championship-2026/11024/9z-team-vs-aurora/2796376) |
| Astralis -1250, Sashi +530 | Explicit `Main` → `Match Winner` section on official sportsbook match page; `BO3`; `October 14, 06:00`. Two-sided pair observed together. | [Thunderpick Astralis/Sashi market](https://thunderpick.io/esports/cs2-betting/pulse-beat-iii/11173/astralis-vs-sashi/2767822) |
| American odds → implied probabilities | Formulas checked against official exchange help article: positive `100/(A+100)`, negative `abs(A)/(abs(A)+100)`. | [Smarkets formula reference](https://help.smarkets.com/hc/en-gb/articles/214058369-How-to-calculate-implied-probability-in-betting) |
| GG.BET response rejects regional access | Page says `This internet site is not accepting visitors from your region.` This establishes only the response seen, not global availability. No workaround attempted. | [GG.BET](https://gg.bet/en/esports) |
| Rivalry redirected to closure notice | Official response says `Rivalry’s operations have now ceased. Player access is no longer available through this site.` Not a usable current odds source for this audit. | [Rivalry official notice](https://www.rivalry.com/operationally-closed) |
| Official championship team link returned a page-not-found title | Root championship page linked `/teams/`; that response had title `Page not found` and `main content unavailable`. No teams inferred from it. | [Official linked team page](https://world-championship.thunderpick.io/teams/) |

## Independent calculations — not verified true win probabilities

The following are **our mathematical transformations**, using only the official external sportsbook prices above. They are not official bookmaker fair lines, not multi-book consensus, not a trained performance model, and not evidence of future outcomes.

For each complete two-way price pair, convert American odds to raw implied probabilities `q1`, `q2`; compute overround `q1 + q2 - 1`; proportionally normalize `p_i = q_i / (q1 + q2)`; originate fair decimal lines `1 / p_i`. Proportional normalization is our disclosed modeling choice, not a uniquely correct way to remove bookmaker margin.

| Official sportsbook pair | Raw implied A / B | Overround | Derived A / B | Our derived fair decimal A / B | Official price source |
|---|---:|---:|---:|---:|---|
| 9z Team +280 / Aurora -455 | 26.3158% / 81.9820% | 8.2978% | 24.2995% / 75.7005% | 4.1153 / 1.3210 | [Thunderpick match](https://thunderpick.io/esports/cs2-betting/thunderpick-world-championship-2026/11024/9z-team-vs-aurora/2796376) |
| Astralis -1250 / Sashi +530 | 92.5926% / 15.8730% | 8.4656% | 85.3659% / 14.6341% | 1.1714 / 6.8333 | [Thunderpick match](https://thunderpick.io/esports/cs2-betting/pulse-beat-iii/11173/astralis-vs-sashi/2767822) |

No Hotspawn pick percentages, rewards, standings, points, tiers or predictions were fed into these calculations. All other matches have blank odds and probabilities. Due to the join/phase/timestamp uncertainties below, even these two pairs are kept as **independent quote observations** rather than promoted to verified-current lobby probabilities. Exact rational calculations and reproducibility checks are supplied.

## Flagged for Review — required publication

| Flag | Details / safe handling | Source |
|---|---|---|
| Inventory incomplete | Only 26 visible upcoming cards established; headline 60 and filters 86. Do not advertise full coverage. Check authenticated/public application response semantics through the integration pipeline; never generate missing rows from counts. | [Lobby](https://play.hotspawn.com/lobby) |
| Source text is not an API contract | Research-tool markdown does not expose raw HTML, JS bundles, pagination or network requests. This audit does not claim reverse-engineering of undocumented endpoints. | [Lobby](https://play.hotspawn.com/lobby) |
| LoL unverified | Query inspection is insufficient to prove the LoL tab data or its parameter. Keep LoL coverage blank/unverified until observed independently. | [Query inspected](https://play.hotspawn.com/lobby?game=lol) |
| Date/time interpretation unverified | Lobby and sportsbook labels omit explicit timezone and year. Match detail labels differ by four hours (9z 08:30 vs 04:30; Astralis 10:00 vs 06:00). **Do not infer UTC or a four-hour timezone conversion.** Null UTC timestamps prevent falsely claiming exact event joins. | [9z detail](https://www.hotspawn.com/matches/9z-vs-aurora-thunderpick-world-championship-2026-1080176), [Astralis detail](https://www.hotspawn.com/matches/astralis-vs-sashi-stake-pulse-beat-iii-1079438), [lobby](https://play.hotspawn.com/lobby) |
| Market phase unverified | Both official sportsbook match pages include `Live` and describe an `upcoming` match. Do not infer live or prematch state from either isolated phrase. Mathematical quote observations can be shown separately, not asserted as prematch probabilities. | [9z market](https://thunderpick.io/esports/cs2-betting/thunderpick-world-championship-2026/11024/9z-team-vs-aurora/2796376), [Astralis market](https://thunderpick.io/esports/cs2-betting/pulse-beat-iii/11173/astralis-vs-sashi/2767822) |
| Quote timestamps unavailable | Date of tool access is recorded; exact sportsbook price timestamps and tool cache provenance are not supplied. Do not reset these quotes' freshness at build time or in an automated fallback. | [9z market](https://thunderpick.io/esports/cs2-betting/thunderpick-world-championship-2026/11024/9z-team-vs-aurora/2796376), [Astralis market](https://thunderpick.io/esports/cs2-betting/pulse-beat-iii/11173/astralis-vs-sashi/2767822) |
| Event name mismatch | Hotspawn says `Stake Pulse Beat III`; Thunderpick says `Pulse Beat III`. Exact team names/date labels align, but no verified canonical tournament-ID mapping provided here. | [Hotspawn detail](https://www.hotspawn.com/matches/astralis-vs-sashi-stake-pulse-beat-iii-1079438), [Thunderpick event](https://thunderpick.io/esports/cs2-betting/pulse-beat-iii/11173) |
| Single sportsbook only | Two price pairs observed from one operator. No independent second operator prices confirmed. Avoid claiming consensus or confidence calibration. | [Thunderpick 9z market](https://thunderpick.io/esports/cs2-betting/thunderpick-world-championship-2026/11024/9z-team-vs-aurora/2796376) |
| Missing odds for 24 other cards | All official external prices not established in this audit remain blank and flagged per row; HLTV/crowd predictions cannot fill them. | [Lobby](https://play.hotspawn.com/lobby) |
| Direct sandbox network access limited | curl to lobby failed with TLS exit 35 in this restricted sandbox, while research-tool retrieval succeeded. **Do not state the lobby is globally unavailable.** Hosted-runner probe succeeded, but Azure artifact/log download was blocked in the sandbox; no unseen artifact contents used as evidence. | [Hosted probe run](https://github.com/buffedlizard55-lab/MaltaProj2/actions/runs/38442009573), [official lobby](https://play.hotspawn.com/lobby) |

## Reproduce local checks

```sh
python audits/1916f96c/compile_audit.py
python -m unittest discover -s audits/1916f96c -p 'test_*.py' -v
```

The compiler reserializes the dated transcription, **not an automatic retrieval**. Integration must implement its own fresh source collection and must never call this compiler a refresh. Tests verify preservation of all 26 row inputs, official link presence, unknown-field nulls, price conversion examples, exact rational probability checks, overround identities, and that no crowd pick fields are present.

Line-by-line source comparison was performed against the complete lobby text chunks and explicit sportsbook `Match Winner` blocks. No names or tournament rows were inferred from standings/filter team lists. Match-source links are the actual `View Match` links observed in the lobby. Only two official match detail pages were independently opened, so only those rows receive a separately confirmed game value.

## Complete visible-card transcription

These are the 26 observed cards, not the complete weekly inventory. All times are source display labels with timezone/year unverified. Blank cells indicate no verified current odds/probability, even where a dated independent quote is separately documented above.

| Match | Tournament | Displayed schedule | Current verified odds | Current verified probability | Official row source |
|---|---|---|---|---|---|
| ex-Keyd Stars vs Galorys | ESL Challenger League Season 52: South America - Cup #3 | Oct 13, 17:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/ex-keyd-stars-vs-galorys-esl-challenger-league-season-52-south-america-cup-3-1081076) |
| Zomblers vs Overtake Sector | ESL Challenger League Season 52: North America - Cup #3 | Oct 13, 21:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/zomblers-vs-overtake-sector-esl-challenger-league-season-52-north-america-cup-3-1079546) |
| Gothic vs Lavked | CCT Europe 2026 Series #11 | Oct 14, 04:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/gothic-vs-lavked-cct-europe-2026-series-11-1079621) |
| 9z vs Aurora | Thunderpick World Championship 2026 | Oct 14, 04:30 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/9z-vs-aurora-thunderpick-world-championship-2026-1080176) |
| Astralis vs Sashi | Stake Pulse Beat III | Oct 14, 06:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/astralis-vs-sashi-stake-pulse-beat-iii-1079438) |
| HOTU vs Fnatic | Stake Pulse Beat III | Oct 14, 06:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/hotu-vs-fnatic-stake-pulse-beat-iii-1079439) |
| ex-RUSTEC vs mellren | CCT Europe 2026 Series #11 | Oct 14, 07:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/ex-rustec-vs-mellren-cct-europe-2026-series-11-1079622) |
| Falcons vs Ninjas in Pyjamas | Thunderpick World Championship 2026 | Oct 14, 07:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/falcons-vs-ninjas-in-pyjamas-thunderpick-world-championship-2026-1080177) |
| Legacy vs PARIVISION | Thunderpick World Championship 2026 | Oct 14, 09:30 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/legacy-vs-parivision-thunderpick-world-championship-2026-1080178) |
| G2 Ares vs The Last Resort | CCT Europe 2026 Series #11 | Oct 14, 10:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/g2-ares-vs-the-last-resort-cct-europe-2026-series-11-1079623) |
| FURIA vs BetBoom | Thunderpick World Championship 2026 | Oct 14, 12:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/furia-vs-betboom-thunderpick-world-championship-2026-1080179) |
| FORZE Reload vs LFO 10 | CCT Europe 2026 Series #11 | Oct 14, 13:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/forze-reload-vs-lfo-10-cct-europe-2026-series-11-1079624) |
| WROTBERRY vs EAC | Elisa BreakOut Series #2 | Oct 15, 04:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/wrotberry-vs-eac-elisa-breakout-series-2-1080279) |
| MIBR vs BC.Game | Stake Pulse Beat III | Oct 15, 06:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/mibr-vs-bc-game-stake-pulse-beat-iii-1079440) |
| Heroic vs Envy | Stake Pulse Beat III | Oct 15, 06:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/heroic-vs-envy-stake-pulse-beat-iii-1079442) |
| ENCE vs BOJONG | Elisa BreakOut Series #2 | Oct 15, 06:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/ence-vs-bojong-elisa-breakout-series-2-1080280) |
| WROTBERRY vs ENCE | Elisa BreakOut Series #2 | Oct 15, 08:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/wrotberry-vs-ence-elisa-breakout-series-2-1080281) |
| EAC vs BOJONG | Elisa BreakOut Series #2 | Oct 15, 10:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/eac-vs-bojong-elisa-breakout-series-2-1080282) |
| WROTBERRY vs BOJONG | Elisa BreakOut Series #2 | Oct 15, 12:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/wrotberry-vs-bojong-elisa-breakout-series-2-1080283) |
| EAC vs ENCE | Elisa BreakOut Series #2 | Oct 15, 14:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/eac-vs-ence-elisa-breakout-series-2-1080284) |
| Voca vs Phantom | Elisa BreakOut Series #2 | Oct 16, 04:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/voca-vs-phantom-elisa-breakout-series-2-1080285) |
| HAVU vs RoundsGG | Elisa BreakOut Series #2 | Oct 16, 06:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/havu-vs-roundsgg-elisa-breakout-series-2-1080286) |
| Voca vs HAVU | Elisa BreakOut Series #2 | Oct 16, 08:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/voca-vs-havu-elisa-breakout-series-2-1080287) |
| Phantom vs RoundsGG | Elisa BreakOut Series #2 | Oct 16, 10:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/phantom-vs-roundsgg-elisa-breakout-series-2-1080288) |
| RoundsGG vs Voca | Elisa BreakOut Series #2 | Oct 16, 12:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/roundsgg-vs-voca-elisa-breakout-series-2-1080289) |
| Phantom vs HAVU | Elisa BreakOut Series #2 | Oct 16, 14:00 | | | [Lobby](https://play.hotspawn.com/lobby) · [Match](https://www.hotspawn.com/matches/phantom-vs-havu-elisa-breakout-series-2-1080290) |
