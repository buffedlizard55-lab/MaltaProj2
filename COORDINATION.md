# COORDINATION.md — Shared Task Board

Repo: `MaltaProj2` — Hotspawn Pick'em betting-line analysis & GitHub Pages dashboard

**Session registry**

| Session ID | Branch | Role | Status |
|---|---|---|---|
| `arena-1da4b0ef-maltaproj2` | `arena/1da4b0ef-maltaproj2` | worker + final integration (single active session in this repo) | active |

> Note: This Arena session is bound to branch `arena/1da4b0ef-maltaproj2` and cannot create other
> branches. That branch is therefore used as both the session working branch and the integration
> branch. If a future session joins, it should claim unclaimed tasks below and coordinate via this file.

**Rules in force** (from project brief):
- Claim a task here (session ID + file scope) and commit/push the claim before starting.
- Never start a task another session has claimed. Scopes must not overlap.
- Small, frequent commits. `git pull --rebase` before every push.
- Never mark anything "verified" without checking it against an official source and linking that source.
- Shared outputs (combined table data, site index/navigation) are only changed by the final integration pass.
- Flagged irregularities / unverified items do not block merge; they are published on the "Flagged for Review" page.

---

## Task board

| # | Task | Status | Owner (session) | File scope | Notes |
|---|---|---|---|---|---|
| T0 | Repo review + this coordination board | done | arena-1da4b0ef-maltaproj2 | COORDINATION.md, README.md | Repo was empty except README "Initial commit" — no pre-existing data to review. |
| T1 | Inventory of all matches listed in the Hotspawn pick'em game (CS2 + LoL), with official links | in progress | arena-1da4b0ef-maltaproj2 | data/matches.csv, data/irregularities.md | Sources: play.hotspawn.com lobby pages + www.hotspawn.com WP REST API. |
| T2 | External betting lines for CS2 pick'em matches + our implied probabilities | unclaimed | — | data/odds_cs2.csv, data/odds_sources.md | Will use outside sources only (HLTV, bookmakers, aggregators). Never Hotspawn pick %. |
| T3 | External betting lines for LoL pick'em matches + our implied probabilities | unclaimed | — | data/odds_lol.csv | Same methodology as T2. |
| T4 | Build GH Pages dashboard site (landing + category subpages + tables + analysis + flagged page) | unclaimed | — | docs/**, tools/build_site.py | Generated from data/ by tools/build_site.py (single source of truth). |
| T5 | Line-by-line verification pass (every row has source link; blanks flagged) | unclaimed | — | data/verification_log.md | |
| T6 | Final integration: re-verify combined data, site build check (no broken links), PR to main, enable GitHub Pages, record PR + deploy result here | unclaimed | — | COORDINATION.md, README.md | |

---

## Task detail logs

### T0 — Repo review (done)
- Reviewed repository at commit `e489221` ("Initial commit"): only `README.md` (title "MaltaProj2"). Nothing else to audit.
- Irregularities: none.

### T1 — Match inventory (in progress)
- Claimed: arena-1da4b0ef-maltaproj2 @ 2026-10-13. Scope: `data/matches.csv`, `data/irregularities.md`.
- Sources being used:
  - https://play.hotspawn.com/lobby (pick'em lobby — match cards, tiers, points, lock times)
  - https://play.hotspawn.com/cs2-pickems and https://play.hotspawn.com/lol-pickems (per-game lobbies)
  - https://www.hotspawn.com/matches (official match schedule / cross-check)
  - https://www.hotspawn.com/wp-json/wp/v2/fixtures (official Hotspawn WordPress REST API — fixture records, external IDs)
  - https://www.hotspawn.com/wp-json/fixtures/v1/get?external_id=... (official fixture endpoint)
- Verification performed: TBD at completion (every row must carry its official Hotspawn match-page URL).

---

## Change log / handoffs
- 2026-10-13 — session `arena-1da4b0ef-maltaproj2` created this board, claimed T0 (done) and T1 (in progress). T2-T6 remain unclaimed. No handoffs.
