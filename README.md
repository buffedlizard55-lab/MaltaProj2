# MaltaProj2 — Hotspawn Pick'em → independent betting lines

Reverse-engineering project for the **Hotspawn Play CS2 Pick'em lobby**
(<https://play.hotspawn.com/lobby>): every fixture that is open for picks is
enumerated, verified against independent esports data sources, priced from
external betting markets, and converted into **our own de-margined probability**.

**Live site:** <https://buffedlizard55-lab.github.io/MaltaProj2/>

## Ground rules this repo enforces

* **Hotspawn is never used as a probability.** The crowd "picked" percentage is
  shown in its own column labelled *context only* and is excluded from every
  calculation.
* **Every row carries source links** to the official pages used for it.
* **Nothing is inferred.** If a value could not be confirmed from a source, the
  cell is left empty and the item is published on the *Flagged for review* page.

## Layout

| Path | What it is |
|---|---|
| `data/pickem_pool.json` | Canonical dataset: 26 open fixtures, captured prices, derived probabilities, sources, tournament pool counts, flagged items |
| `data/keys.json` | Field-by-field description of the dataset |
| `scripts/build.py` | Single source of truth: captured values + URLs + derivation + site generator |
| `scripts/check_links.py` | Internal link/asset checker for the generated site |
| `docs/` | Static GitHub Pages site (dashboard, all matches, by tournament, analysis, methodology, flagged for review, sources) |
| `COORDINATION.md` | Shared task board for parallel agent sessions, with the verification log |

## Pipeline

1. **Enumerate** — `play.hotspawn.com/lobby` + `/cs2-pickems` (three reads; the
   open-for-picks list was stable, crowd percentages tick).
2. **Verify** — HLTV match pages / event listings, plus bo3.gg where HLTV has no
   per-match page yet.
3. **Price** — external markets only: EGamersWorld's `Bets on <event> by bc.game`
   odds modules and Polymarket CS2 markets.
4. **De-margin** — `p_i = (1/o_i) / Σ(1/o_j)` for bookmaker odds;
   `p_i = c_i / Σ c_j` for prediction-market cents.
5. **Our line** — equal-weight average of the de-margined sources captured for
   that fixture; fair odds = `1/p`. Rows with no captured two-sided price stay
   blank and are flagged.

## Build

```bash
python3 scripts/build.py        # regenerates data/*.json and docs/**
python3 scripts/check_links.py  # verifies no broken internal links
```

## Coverage (snapshot 2026-10-13, UTC)

* 26 fixtures open for picks; 25 carry a line, 1 left blank and flagged.
* 22 fixtures with a bc.game (via EGamersWorld) line, 20 with a Polymarket market, 17 with both.
* Quality badges: 12 High, 8 Medium, 5 Low, 1 n/a (blank row).
* 14 flagged items, each with the source link needed to resolve it.
* Kickoffs are UTC, taken from the lobby payload's `scheduled_start` epoch and matched against HLTV
  (the lobby's rendered clock reads 4 h earlier, US Eastern - see the Flagged page).

Everything on the site is a point-in-time capture. Re-check the linked source
before acting on any number.

## Corrections made after the first pass (all logged on the Flagged page)

* Kickoff times are UTC from the lobby payload epoch, not the rendered (US Eastern) labels.
* `RoundsGG vs Voca` (hs-1080289) had its Polymarket prices double-flipped in the first build;
  corrected to RoundsGG 47c / Voca 91c and re-verified against the market page and the HLTV slug.
* The two ESL Challenger League fixtures now carry their HLTV match pages (2399204, 2399232, both bo3).
* Elisa BreakOut bc.game lines were completed from the EGamersWorld event page (7 fixtures added), and
  the WBT/EA Copenhagen pair refined to the page's own 1.989/1.722 figures.
* The independent 86-row lobby audit committed here (`audits/1d4de836/`) is cited by the coverage flag.
