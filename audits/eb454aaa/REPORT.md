# Independent expanded-market safety audit

Session: `eb454aaa`. This is a **dated read-only review**, not a claim to have collected fresh HotSpawn/HLTV/bookmaker evidence in this sandbox, and not a replacement for the root dashboard.

## Deliverables

- [Audit overview](index.html)
- [Flagged for Review](flagged.html): eight specific issues and requested fixes
- [Row-by-row review](rows.html): every labeled-future row, plus historical quoted rows
- [Complete machine-readable audit](report.json): all 1,210 inventory rows, source URLs, flags and input SHA-256 fingerprints
- [Valve official-source verification](valve_verification.json): four dated regional standings files checked independently against Valve's official GitHub contents API

## Verification boundaries

The repository already contains an integrated, mobile-friendly GitHub Pages site and hourly root-CS2 refresh. The expanded board refreshes every two hours. Those schedules were checked in the committed workflows and GitHub's workflow API. A schedule does not guarantee fresh, correct, available quotes or complete pricing coverage.

The expanded snapshot audited here was generated at **2026-10-13T22:48:04Z**. It contains 1,210 CS2/LoL inventory records, 263 labeled-future records, and 27 future records with external quotes (23 CS2, 4 LoL). **18** of those 27 have at least one conservative safety-review flag, including team aliases requiring primary identity evidence. This is **not** a claim that all 18 prices are wrong. The other nine have passed the enumerated mechanical checks, **not** independently certified market identity or win probability.

- Per-source proportional no-vig arithmetic and mean-consensus arithmetic were independently recomputed for every quoted row. No arithmetic mismatches were found in this snapshot.
- Every inventory row was checked for game, participant names and status consistency with the separately committed normalized fixture capture. This is internal evidence consistency, not a new official lobby fetch.
- Original provider URLs, quote retrieval times, source kickoff times, source state and live marker are retained per quoted row.
- Quote age is assessed **at the snapshot time**, never misrepresented as current-time eligibility. A dated report cannot certify a current betting line.
- No probabilities or picks are published by this audit. Their fields are blank even when mechanical checks pass. HotSpawn crowd percentages are never audit inputs.
- A team alias alone is not primary-source proof of team identity. Aliased joins are flagged rather than silently certified.
- The official Valve files were newly fetched via the allowed GitHub API. All four 2026-10-05 stored snapshots match byte-for-byte. This validates their rating input, not the assumption that a VRS difference maps to a calibrated win probability through an Elo-style scale of 400.
- Bookmaker license claims and LineFeed market-code semantics were not independently certified in this session. This audit makes no jurisdictional licensing assertion and does not certify an inferred feed market as an official full-match moneyline.
- Sandbox outbound access excludes HotSpawn, HLTV, bookmaker hosts and the public Pages domain. Runner evidence is therefore clearly identified as prior capture. No authentication bypass, challenge evasion or network-policy workaround was used.

## Review findings / integration requests

Source links and per-row evidence are published on [Flagged for Review](flagged.html).

1. **F1 — non-open state**: two future Bovada quotes have state `S`, but are averaged into the market consensus. No undocumented state meaning is inferred; these quotes are not confirmed open.
2. **F2 — relaxed join**: four quotes for two LoL fixtures join across a five-hour kickoff disagreement. Actual code accepts one shared competition token and up to 720 minutes; the published method says 90 minutes. Reconcile against explicit official source identities and schedules before certification.
3. **F3 — in-play consensus**: past ex-Keyd Stars–Galorys has a live Bovada quote in consensus. The board flags it as past, but still averages the live quote.
4. **F4 — missing gates**: expanded consensus has no source-age, fixture-lock, or open-market gate. Its root current-board counterpart has a stricter policy and should remain the current-pick reference.
5. **F5 — side-order risk**: expanded Bovada parsing assumes competitor and outcome arrays have the same order rather than using `competitorId`. Captured samples checked here do align; no actual inversion is asserted.
6. **F6 — workflow failure masking**: collector/verifier/renderer/link-check failures are echoed and publication runs `always()`. Evidence collection should be separate from fail-closed validation and atomic publication.
7. **F7 — scope**: 821 inventory records are forfeited; one labeled-future record is `started` despite a November kickoff. API membership is not proof of present lobby eligibility. Official source inconsistency remains unverified.
8. **F8 — model wording**: labeled originated estimates coexist with a footer saying “Nothing is estimated.” Make the wording consistent and do not portray uncalibrated model estimates as official forecasts.

These are non-blocking **needs review** items, not changes to another session's claimed files. The expanded collector owner receives the requests through COORDINATION.md. Existing source work and datasets are preserved.

## Reproduce

```sh
python -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt
.venv/bin/python audits/eb454aaa/audit.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/stage_site.py
```

The generator writes only within `audits/eb454aaa/` and does not fetch any source or edit an upstream fixture, quote, model or generator. Re-running against newer inputs creates a new **dated** report; the input fingerprints make that change explicit. `valve_verification.json` records a separate official-source comparison and is not overwritten by this generator.

The isolated read-only browser workflow verifies the audit overview, flagged page and row table at 320, 390 and 1280 pixels on GitHub runners. It checks row source links, deliberately empty probabilities, search filtering, no page overflow, successful local responses and no JavaScript errors.

A complete repository line-by-line primary-source verification and a source-confirmed probability for every lobby match are **not achieved**. Existing coverage gaps and the findings above are exposed instead of invented or hidden.
