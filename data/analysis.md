# T3 — Win Probability Analysis (derived from external betting lines only)

Captured: 2026-10-13. Method: proportional de-vig of two-way decimal bookmaker odds:

    p_i = (1/o_i) / (1/o_1 + 1/o_2)

Probabilities are **never** derived from Hotspawn community pick percentages (those are shown
in the pick'em only as context). Matches with no external bookmaker line are left blank and
flagged **unverified** — never inferred or filled.

## Coverage

| Segment | Picked matches | With external line | Unverified (no line published) |
|---|---|---|---|
| CS2 — Thunderpick WC (S) | 4 | 4 | 0 |
| CS2 — Stake Pulse Beat III (B) | 4 | 4 | 0 |
| CS2 — CCT Europe #11 (B) | 4 | 2 | 2 (ex-RUSTEC/mellren; FORZE Reload/LFO 10) |
| CS2 — ESL Challenger cups (B) | 2 | 2 | 0 |
| CS2 — Elisa BreakOut #2 (C) | 12 | 12 | 0 |
| LoL — Worlds Play-In | 2 | 2 | 0 |
| LoL — Demacia Cup / EM Summer | 2 | 2 | 0 |
| LoL — LGC Rising Playoffs | 2 | 0 | 2 (widget shows 1.8/1.8 placeholder) |
| LoL — minor leagues (PRM 2nd/3rd, Tunisian, RIVALS, Arabian 2nd, Komplettligaen, LigaGG CELOL A, Superstrike, MängudeÖÖ, Benelux) | 225 | 0 | 225 (no bookmaker market exists on any source checked) |
| **Total** | **257** | **28** | **229** |

## Sources (all external to Hotspawn)

- EGamersWorld event/match pages — bookmaker widgets labeled **GG.BET** (Stake Pulse Beat III,
  Elisa BreakOut S2), **BC.GAME** (Thunderpick WC, CCT Europe #11, ESL NA Cup #3), **N1 Bet**
  (2026 World Championship), plus the EGW bookmaker widget on match pages (ESL SA Cup #3,
  Demacia Cup, EMEA Masters Summer). Per-row links in `data/odds.csv`.
- GG.bet prices via tips.gg / win.gg (Cloud9 vs Karmine Corp) — secondary line.
- Polymarket series moneyline (KT Rolster vs BNK FearX) — secondary cross-check.
- HLTV (schedule/pairings cross-check for TWC; HLTV "win probability" simulations are a model
  output, **not** a betting line, and were not used as odds).

## Key findings (market vs Hotspawn community, community = context only)

Hotspawn community % from `data/matches.csv` (collected for inventory; **not** used in any probability).

| Match | Market favorite (our line) | Hotspawn public favorite | Read |
|---|---|---|---|
| ex-Keyd Stars vs Galorys | **Galorys 62.5%** (2.43/1.46) | ex-Keyd Stars 86% | Clearest divergence: market favorite is Galorys; public heavily on ex-Keyd Stars |
| WROTBERRY vs ENCE | **WROTBERRY 57.9%** (1.6/2.2) | ENCE 71% | Divergence: market makes WROTBERRY the favorite |
| Zomblers vs Overtake Sector | Overtake Sector 62.4% (2.46/1.48) | Overtake Sector 89% | Same side; public far more extreme than the market |
| HOTU vs Fnatic | Fnatic 52.0% (1.97/1.82) | Fnatic 91% | Same side; market sees a near coin-flip |
| Phantom vs HAVU | Phantom 67.5% (1.37/2.84) | Phantom 100% | Same side; public 100% on Phantom |
| Voca vs Phantom | Phantom 51.2% (1.9/1.81) | Phantom 73% | Same side; market near coin-flip |
| Voca vs HAVU | Voca 66.9% (1.38/2.79) | Voca 64% | Market and public aligned |
| Cloud9 vs Karmine Corp | **Karmine Corp 65.8%** (2.71/1.41) | no picks yet (0/0) | GG.bet (2.41/1.54) and N1 Bet both make KC favorite |
| KT Rolster vs BNK FearX | **KT Rolster 71.4%** (1.31/3.27) | no picks yet (0/0) | EGW widget and Polymarket (KT 65–66% devig) agree |
| Falcons vs NiP | Falcons 76.3% (1.23/3.95) | Falcons 89% | One-sided Bo3, both sides agree |
| 9z vs Aurora | Aurora 73.9% (3.6/1.27) | Aurora 95% | One-sided Bo3, both sides agree |

## Expected-value framing (from our probabilities only)

Pick'em scoring: base points by tier (CS2 S=7 B=3 C=2; LoL S=30 A=20 C/other=10), ×1.5/×2/×3
tier multipliers where the card shows them (CS2 S ×3, B ×1.5; LoL S ×3, A ×2), ×1.25 streak.
Expected points for a pick = P(win) × points × applicable multipliers. Because multipliers are
symmetric between the two teams of a match, the EV comparison inside a match always follows
the higher probability — our value-add is *which side* that is versus the public.

## Reproduce

`python3 tools/build_odds.py` regenerates `data/odds.csv` and `data/probabilities.csv`
from the capture records embedded in the script (each tied to match_id + team names and
asserted against `data/matches.csv`).
