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
* 15 fixtures with a bc.game (via EGamersWorld) line, 20 with a Polymarket market.
* 13 flagged items, each with the source link needed to resolve it.

Everything on the site is a point-in-time capture. Re-check the linked source
before acting on any number.
