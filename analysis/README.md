# T-A: External betting line collection (session 6196c585)

Goal: for every match in the Hotspawn Pick'em lobby (docs/data/matches.json, 86 fixtures,
27 currently visible cards for Oct 13–16, 2026), collect betting lines from EXTERNAL sources
(bookmakers, HLTV, prediction markets). Hotspawn crowd percentages are never used as a
probability indicator.

Method:
1. Observe odds only from pages/snippets actually retrieved, with URL + retrieval timestamp (UTC).
2. Convert observed prices to implied probabilities with proportional de-vig (scripts/model.py
   arithmetic: q = 1/decimal; p_i = q_i / sum(q)); record the overround.
3. An observation qualifies as "verified line" only if: both outcomes priced, market is match
   winner (2-way), source is the bookmaker/official page itself, event identity (teams +
   tournament) matches the fixture. Everything else stays blank/unverified and is flagged.
4. Raw evidence (fetched page text / search snippets) preserved under analysis/raw/.

Files:
- odds_observations.json — normalized observations (source URL, observed_at, prices, join status)
- lines.json             — per-fixture originated lines (no-vig probabilities) + provenance
- raw/                   — preserved evidence per source

Status legend: verified-join | identity-unverified | not-found
