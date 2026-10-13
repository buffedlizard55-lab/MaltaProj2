# Repo verification — session `ac475c09`

Generated 2026-10-13T21:41:48Z. Mechanical, re-runnable checks over this repository's published pick'em artefacts.

**0 high · 1 medium · 1 low · 17 informational**

| Check | Severity | File | Finding |
|---|---|---|---|
| price_provenance | info | `data/odds.json` | all 21 stored price rows carry a source URL |
| price_provenance | info | `data/lines.json` | all 0 stored price rows carry a source URL |
| price_provenance | info | `data/cs2_odds_egamersworld.json` | all 32 stored price rows carry a source URL |
| price_provenance | info | `data/lol_odds_egamersworld.json` | all 7 stored price rows carry a source URL |
| price_provenance | info | `data/picks_quotes.json` | all 25 stored price rows carry a source URL |
| price_units | info | `data/odds.json` | no decimal_odds_* field is out of range |
| price_units | info | `data/lines.json` | no decimal_odds_* field is out of range |
| freshness | info | `data/hotspawn_matches.json` | snapshot is 0.0h old |
| freshness | info | `data/cs2_matches.json` | snapshot is 2.7h old |
| freshness | info | `data/lol_matches.json` | snapshot is 2.7h old |
| freshness | info | `data/odds.json` | snapshot is 0.0h old |
| freshness | info | `data/lines.json` | snapshot is 0.0h old |
| freshness | info | `data/probabilities.json` | snapshot is 2.1h old |
| freshness | info | `data/picks_fixtures.json` | snapshot is 0.0h old |
| freshness | info | `data/picks_board.json` | snapshot is 0.0h old |
| published_counts | info | `data/lines.json` | summary and rows agree (9 priced fixtures of 92) |
| typed_quotes | medium | `scripts/*.py` | price-like literals are typed into generator scripts; they cannot be re-verified without opening the linked page, so they are listed for review |
| cross_pipeline | low | `data/lines.json vs data/picks_board.json` | no fixture currently carries a pre-match line in both pipelines (the older collection captured them before they started), so the two collections cannot be cross-checked on this build |
| fixture_drift | info | `data/hotspawn_matches.json vs data/picks_fixtures.json` | older snapshot lists 406 fixtures, the fresh API read lists 11570 fixtures in total and 29 CS2 / 239 LoL fixtures still open for picks |

## How to re-run

```bash
python3 verify/ac475c09/verify_repo.py
```

