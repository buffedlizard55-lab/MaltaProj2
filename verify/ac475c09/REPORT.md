# Repo verification — session `ac475c09`

Generated 2026-10-13T22:07:12Z. Mechanical, re-runnable checks over this repository's published pick'em artefacts.

**0 high · 1 medium · 1 low · 21 informational**

| Check | Severity | File | Finding |
|---|---|---|---|
| price_provenance | info | `data/odds.json` | all 20 stored price rows carry a source URL |
| price_provenance | info | `data/lines.json` | all 0 stored price rows carry a source URL |
| price_provenance | info | `data/cs2_odds_egamersworld.json` | all 32 stored price rows carry a source URL |
| price_provenance | info | `data/lol_odds_egamersworld.json` | all 7 stored price rows carry a source URL |
| price_provenance | info | `data/picks_quotes.json` | all 25 stored price rows carry a source URL |
| price_units | info | `data/odds.json` | no decimal_odds_* field is out of range |
| price_units | info | `data/lines.json` | no decimal_odds_* field is out of range |
| freshness | info | `data/hotspawn_matches.json` | snapshot is 0.1h old |
| freshness | info | `data/cs2_matches.json` | snapshot is 3.1h old |
| freshness | info | `data/lol_matches.json` | snapshot is 3.1h old |
| freshness | info | `data/odds.json` | snapshot is 0.1h old |
| freshness | info | `data/lines.json` | snapshot is 0.1h old |
| freshness | info | `data/probabilities.json` | snapshot is 2.5h old |
| freshness | info | `data/picks_fixtures.json` | snapshot is 0.1h old |
| freshness | info | `data/picks_board.json` | snapshot is 0.1h old |
| published_counts | info | `data/lines.json` | summary and rows agree (9 priced fixtures of 92) |
| typed_quotes | medium | `scripts/*.py` | price-like literals are typed into generator scripts; they cannot be re-verified without opening the linked page, so they are listed for review |
| cross_pipeline | low | `data/lines.json vs data/picks_board.json` | no fixture currently carries a pre-match line in both pipelines (the older collection captured them before they started), so the two collections cannot be cross-checked on this build |
| fixture_drift | info | `data/hotspawn_matches.json vs data/picks_fixtures.json` | older snapshot lists 406 fixtures, the fresh API read lists 11570 fixtures in total and 28 CS2 / 239 LoL fixtures still open for picks |
| published_links | info | `data/picks_board.json` | none of 292 rows publish the redirecting bare /matches/<id> URL |
| published_links | info | `evidence/picks/link_checks.json` | 21 published quote URLs were opened by the collector |
| pickable_accounting | info | `data/picks_board.json` | no cancelled fixture is counted as open for picks |
| dated_capture | info | `data/picks_supplementary.json` | 11 captured rows, each carrying its own URL and retrieval time |

## How to re-run

```bash
python3 verify/ac475c09/verify_repo.py
```

