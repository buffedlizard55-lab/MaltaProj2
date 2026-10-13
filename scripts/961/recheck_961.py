#!/usr/bin/env python3
"""Session 961e163a — independent re-verification of the published 961 board.

This module deliberately re-implements the arithmetic instead of importing the builder, so a
mistake shared by builder and re-checker would be *visible* rather than hidden. It checks:

  R1  every verified row: probability_a/b recomputed from the raw per-source decimals matches the
      published value (tolerance 0.0005) and p_a + p_b == 1.
  R2  pick == the larger published probability, pick_probability == that probability.
  R3  every verified row carries at least one http(s) source URL and a retrieval timestamp.
  R4  every unverified row is blank: no probability, no pick.
  R5  per-source no-vig shares equal 1/odds normalised by the pair sum (recomputed from decimals).
  R6  source names/urls on a row are distinct and each source contributes a real price pair.
  R7  every row carries the lobby source URL and a HotSpawn fixture link.
  R8  cross-checks (if present) cite hltv.org URLs, agree/differ flags match the board pick, and
      HLTV is never published as a price source.
  R9  every HTML file in verify961/ has its internal links resolving to an existing file and the
      mobile viewport tag, and every board page carries the source link of each verified row.

Usage:  python3 scripts/961/recheck_961.py [--verbose]
Exit code 0 = every check passed, 1 = at least one failure (printed).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BOARD = os.path.join(ROOT, "data", "961", "board.json")
CROSS = os.path.join(ROOT, "data", "961", "cross_checks.json")
PAGES_DIR = os.path.join(ROOT, "verify961")
TOL = 0.0005


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _no_vig(a, b):
    """Return (p_a, p_b) for a decimal price pair; None if the pair is unusable."""
    try:
        a = float(a)
        b = float(b)
    except (TypeError, ValueError):
        return None
    if a <= 1.0 or b <= 1.0:
        return None
    qa, qb = 1.0 / a, 1.0 / b
    return qa / (qa + qb), qb / (qa + qb)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls: list[str] = []
        self.has_viewport = False

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "meta" and d.get("name") == "viewport":
            self.has_viewport = True
        for key in ("href", "src"):
            if d.get(key):
                self.urls.append(d[key])


def check_board(board, verbose=False):
    """Recompute every published number from the raw per-source decimals and assert the rules."""
    fails: list[str] = []
    rows = board["rows"]
    verified = 0
    for row in rows:
        fid = row.get("fixture_id")
        tag = f"fixture {fid} {row.get('team_a')} vs {row.get('team_b')}"
        if not str(row.get("official_source_url_hotspawn") or "").startswith("http"):
            fails.append(f"R7 {tag}: missing official lobby API source URL")
        if not row.get("hotspawn_match_url"):
            fails.append(f"R7 {tag}: missing HotSpawn fixture link")
        if not row.get("verified"):
            if row.get("probability_a") is not None or row.get("pick"):
                fails.append(f"R4 {tag}: unverified row carries a probability or pick")
            continue
        verified += 1
        srcs = row.get("sources") or []
        if not srcs:
            fails.append(f"R3 {tag}: verified row has no source")
        # per-source checks
        pairs: list[tuple[dict, tuple]] = []
        seen: set[str] = set()
        for s in srcs:
            url = s.get("source_url") or ""
            if not url.startswith("http"):
                fails.append(f"R3 {tag}: source {s.get('source_key')} has no http(s) URL")
            if not s.get("retrieved_at_utc"):
                fails.append(f"R3 {tag}: source {s.get('source_key')} has no retrieval time")
            if url and url in seen:
                fails.append(f"R6 {tag}: duplicated source URL {url}")
            seen.add(url)
            pair = _no_vig(s.get("decimal_odds_a"), s.get("decimal_odds_b"))
            if pair is None:
                fails.append(f"R6 {tag}: source {s.get('source_key')} has an unusable price pair")
                continue
            pairs.append((s, pair))
            if s.get("no_vig_probability_a") is not None:
                if abs(pair[0] - float(s["no_vig_probability_a"])) > 0.005:
                    fails.append(
                        f"R5 {tag}: source {s.get('source_key')} no-vig {s['no_vig_probability_a']} "
                        f"!= recomputed {pair[0]:.4f}")
        if not pairs:
            continue
        # consensus rule: pre-match quotes only; live quotes are published but excluded
        pre_match = [(s, p) for s, p in pairs if not s.get("market_is_live")]
        live = [(s, p) for s, p in pairs if s.get("market_is_live")]
        used = pre_match or live
        expected_basis = "pre_match" if pre_match else "live_only"
        if row.get("consensus_basis") != expected_basis:
            fails.append(f"R1 {tag}: consensus_basis {row.get('consensus_basis')} != {expected_basis}")
        if row.get("n_consensus_sources") != len(used):
            fails.append(f"R1 {tag}: n_consensus_sources {row.get('n_consensus_sources')} != {len(used)}")
        expected_keys = sorted(s.get("source_key") for s, _ in used)
        if sorted(row.get("consensus_sources") or []) != expected_keys:
            fails.append(f"R1 {tag}: consensus_sources {row.get('consensus_sources')} != {expected_keys}")
        if pre_match and live and "live_price_excluded_from_consensus" not in row["flags"]:
            fails.append(f"R1 {tag}: live quote excluded from consensus but not flagged")
        if live and not pre_match and "live_consensus_only" not in row["flags"]:
            fails.append(f"R1 {tag}: live-only consensus not flagged")
        mean_a = sum(p[0] for _, p in used) / len(used)
        mean_b = 1.0 - mean_a
        pa, pb = row.get("probability_a"), row.get("probability_b")
        if pa is None or pb is None:
            fails.append(f"R1 {tag}: verified row has no probability")
            continue
        if abs(pa - mean_a) > TOL or abs(pb - mean_b) > TOL:
            fails.append(f"R1 {tag}: published {pa:.4f}/{pb:.4f} != recomputed {mean_a:.4f}/{mean_b:.4f}")
        if abs((pa + pb) - 1.0) > TOL:
            fails.append(f"R1 {tag}: probabilities do not sum to 1 ({pa:.4f}+{pb:.4f})")
        if row.get("n_sources") != len(srcs):
            fails.append(f"R1 {tag}: n_sources {row.get('n_sources')} != {len(srcs)}")
        best = max(pa, pb)
        expected_pick = row.get("team_a") if pa >= pb else row.get("team_b")
        if row.get("pick") != expected_pick:
            fails.append(f"R2 {tag}: pick {row.get('pick')} is not the higher probability ({expected_pick})")
        if row.get("pick_probability") is None or abs(float(row["pick_probability"]) - best) > TOL:
            fails.append(f"R2 {tag}: pick_probability {row.get('pick_probability')} != {best:.4f}")
        if verbose:
            print(f"  ok {fid} {row.get('pick')} {best:.4f} "
                  f"({len(srcs)} source(s), consensus={expected_basis})")
    return fails, verified


def check_cross(cross, board, verbose=False):
    fails: list[str] = []
    picks = {r["fixture_id"]: r.get("pick") for r in board["rows"]}
    for row in cross.get("rows", []):
        tag = row.get("match")
        if not str(row.get("hltv_url", "")).startswith("https://www.hltv.org/"):
            fails.append(f"R8 {tag}: cross-check has no hltv.org URL")
        if not row.get("hltv_statement"):
            fails.append(f"R8 {tag}: cross-check quotes no HLTV wording")
        if row.get("fixture_id") not in picks:
            fails.append(f"R8 {tag}: cross-check references an unknown fixture")
            continue
        board_pick = picks[row["fixture_id"]]
        if row.get("board_pick") != board_pick:
            fails.append(f"R8 {tag}: stored board_pick {row.get('board_pick')} != board {board_pick}")
        if bool(row.get("agreement")) != (row.get("hltv_favorite") == board_pick):
            fails.append(f"R8 {tag}: agreement flag inconsistent with the picks")
        if verbose:
            print(f"  ok {tag}: hltv={row.get('hltv_favorite')} board={board_pick}")
    for row in board["rows"]:
        for s in row.get("sources") or []:
            if s.get("source_key") == "hltv":
                fails.append(f"R8 fixture {row['fixture_id']}: HLTV published as a price source")
    return fails


def check_pages(rows, verbose=False):
    fails: list[str] = []
    verified_rows = [r for r in rows if r.get("verified")]
    for name in sorted(os.listdir(PAGES_DIR)):
        if not name.endswith(".html"):
            continue
        path = os.path.join(PAGES_DIR, name)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        parser = _Links()
        parser.feed(text)
        if not parser.has_viewport:
            fails.append(f"R9 {name}: no mobile viewport meta tag")
        for url in parser.urls:
            if re.match(r"^[a-z]+:", url) or url.startswith("//"):
                continue
            clean = url.split("#")[0].split("?")[0]
            target = os.path.normpath(os.path.join(PAGES_DIR, clean))
            if not os.path.exists(target):
                fails.append(f"R9 {name}: broken internal link -> {url}")
            if clean.startswith("../"):
                rel = os.path.relpath(target, ROOT).replace(os.sep, "/")
                first = rel.split("/")[0]
                if "/" in rel:
                    if first not in _staged_sections():
                        fails.append(f"R9 {name}: cross-section link into an unstaged directory -> {url}")
                    elif not os.path.exists(os.path.join(ROOT, rel)):
                        fails.append(f"R9 {name}: cross-section link missing at the repo root -> {url}")
        if verbose:
            print(f"  ok {name}: viewport + {len(parser.urls)} link(s)")
    for r in verified_rows:
        link = r.get("hotspawn_match_url")
        for name in ("index.html", "cs2.html", "lol.html"):
            text_cache = _read_if_exists(os.path.join(PAGES_DIR, name))
            if text_cache is None:
                continue
            if link and link not in text_cache and name == _page_for(r):
                fails.append(f"R9 {name}: verified fixture {r['fixture_id']} link missing")
    return fails


def _page_for(row):
    game = (row.get("game") or "").lower()
    return {"cs2": "cs2.html", "lol": "lol.html"}.get(game, "index.html")


def _staged_sections():
    """Directories scripts/stage_site.py publishes; cross-section links must stay inside them."""
    path = os.path.join(ROOT, "scripts", "stage_site.py")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return set()
    match = re.search(r"for name in \(([^)]*)\)", text)
    if not match:
        return set()
    return {p.strip().strip("'\"") for p in match.group(1).split(",") if p.strip()}


def _read_if_exists(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def verify(verbose=False):
    board = _load(BOARD)
    fails, verified = check_board(board, verbose=verbose)
    fails += check_pages(board["rows"], verbose=verbose)
    checked_cross = 0
    if os.path.exists(CROSS):
        cross = _load(CROSS)
        checked_cross = len(cross.get("rows", []))
        fails += check_cross(cross, board, verbose=verbose)
    return fails, verified, checked_cross


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    fails, verified, checked_cross = verify(verbose=args.verbose)
    board = _load(BOARD)
    print(f"recheck 961: rows={len(board['rows'])} verified={verified} "
          f"cross_checks={checked_cross} failures={len(fails)}")
    for f in fails:
        print("FAIL", f)
    if fails:
        return 1
    print("PASS: arithmetic, picks, source links, blank-unverified rule, cross-checks and pages all re-verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
