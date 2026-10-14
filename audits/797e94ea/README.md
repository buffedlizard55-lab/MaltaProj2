# Session 797e94ea — root CS2 source-integrity audit

**Published review page:** [`audits/797e94ea/index.html`](index.html) (staged at `/audits/797e94ea/` by the repository’s existing Pages staging process).

## Scope

This is a **read-only** audit of the root CS2 probability snapshot generated at
`2026-10-14T01:16:08Z`:

- [`snapshot_lines.json`](snapshot_lines.json) — immutable copy of the captured external odds, joins, no-vig shares and consensus;
- [`snapshot_current_probabilities.json`](snapshot_current_probabilities.json) — immutable copy of the root table mirror; and
- [`snapshot_cs2.txt`](snapshot_cs2.txt) — immutable copy of the rendered root page.

These copies pin the audit to its stated observation. The live root files refresh automatically and are intentionally not inputs when this historical audit is rebuilt.

It does **not** change a collector, regenerate a market, add a probability,
or validate every independent research board in this repository. It is not a
claim that a timestamped price remains current after the snapshot time.

## Reproducible checks

```bash
python3 audits/797e94ea/build_audit.py
python3 -m unittest tests.test_797e94ea
```

The builder writes:

- [`report.json`](report.json): row-level captured-source, eligibility and arithmetic checks;
- [`source_check_ledger.json`](source_check_ledger.json): dated, manual public-source observations; and
- [`index.html`](index.html): a mobile-first manual review page.

## Source links

Each valued fixture row links to the public HotSpawn discovery feed and to the
exact Pinnacle/Bovada source link stored by the root snapshot. The audit’s live
read ledger also links to the [HotSpawn lobby](https://play.hotspawn.com/lobby),
Pinnacle’s public matchup/market endpoints, and Bovada’s public coupon endpoint.

The ledger has two deliberately conservative findings:

1. the public 9z–Aurora Pinnacle price had moved by the audit re-read, so the
   root price is a dated snapshot rather than a live assertion;
2. the lobby’s rendered `All tiers` counter changed from the captured snapshot’s
   90 to 89, so inventory completeness needs a timestamp and cannot be inferred
   from an old count.

A direct Bovada event-page sample returned a reCAPTCHA/Not Found surface in the
reader while the public coupon endpoint returned JSON. This is recorded as a
read-access limitation—not as proof the captured Bovada price was wrong.
