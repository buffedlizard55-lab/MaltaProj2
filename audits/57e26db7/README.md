# Independent every-match audit — session 57e26db7

**Status: PASS** for the committed snapshot collected at `2026-10-14T04:45:51Z`.

## Result

- Independently filtered the committed HotSpawn snapshot to **28 open scheduled CS2 fixtures**; the canonical board contains exactly the same 28 IDs.
- **28/28** rows have a pick and normalized two-team win probabilities.
- Resolution tiers: **16 external-market**, **8 Valve-VRS model**, **4 documented fallback**, **0 blank/no-evidence**.
- Every row has an HTTPS HotSpawn fixture/discovery link plus at least one non-HotSpawn evidence link.
- No HotSpawn crowd-percentage field is present in the board.
- Polymarket numeric match-tag discovery (`tag_id=100780`) returned **86** active full-match moneylines: **34** books met the ≤10-point spread rule and **52** were retained as fallback-only wide books.

## Repaired defects

1. The prior `tag_slug=counter-strike` probe missed the active match corpus and led to a false “no Polymarket coverage” method claim. Collection now uses numeric match tag `100780`, full-match `moneyline` filtering, exact event URLs, and spread/volume metadata.
2. FORZE Reload–LFO 10 previously used an originated LFO 7/8/9 sibling-rating range despite a direct FORZE Reload–Sökerorg market. HLTV's LFO 10 pages and Liquipedia's Sökerorg page independently show the same five-player core. The direct market now drives a tier-C pick; the absent explicit rename announcement remains flagged.
3. The three HotSpawn WROTBERRY slots conflict with HLTV/Liquipedia and direct markets naming WBT/WhiteBIT Team. Those source names are preserved; wide Polymarket books are range-only. Kalshi's WBT Academy midpoint is not used because the published rosters differ.
4. The workflow no longer occupies a runner for 25 minutes to self-dispatch. Its existing twice-hourly cron exceeds the requested 4–8-hour cadence without sleeping jobs.

## Reproduce

```bash
python3 audits/57e26db7/verify.py
python3 -m unittest tests.test_c64a5e19 tests.test_57e26db7 -v
```

The audit is standard-library only and performs no network access. See:

- [`report.json`](report.json) — machine-readable checks and all open rows.
- [`index.html`](index.html) — mobile line-by-line report with source links.
- [`../../picks-every-match/flagged.html`](../../picks-every-match/flagged.html) — current unresolved identity and market-quality limitations.
