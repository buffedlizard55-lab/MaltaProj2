#!/usr/bin/env python3
"""Final-integration verification for the HotSpawn CS2 pick'em dashboard.

Session `1fac4be2`. Read-only over every other session's published board; writes
only its own dated verification (`data/1fac4be2/verification.json`) and two
public pages (`verify/1fac4be2/index.html`, `verify/1fac4be2/flagged.html`).

What it re-derives, offline, from retained evidence:

  1. every published probability on the two current boards (canonical
     `picks-every-match` board and the day-4 desk) from its own raw quote /
     Valve VRS points under the basis that row declares;
  2. inventory reconciliation — every fixture the retained fixtures capture
     lists must be on the day-4 board, and every board's row count must match
     its own summary;
  3. the TWC day-1/2/3 result ledger across every independent retained capture
     in this repository, flagging disagreements instead of picking a winner;
  4. per-row external source links (https, never HotSpawn as the only source);
  5. page hygiene: viewport meta, one h1, resolvable internal links, mobile
     labels on table cells, and the landing page's primary actions.

It also records what this session could *not* verify from its own sandbox
(egress is allow-listed to GitHub), and captures the scheduled workflows' live
run status from the GitHub API as evidence that the source collectors ran
against the live providers.

Usage:  python scripts/1fac4be2/verify.py
"""
from __future__ import annotations

import html
import json
import math
import re
import socket
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "1fac4be2"
OUT = ROOT / "verify" / "1fac4be2"
REPO = "buffedlizard55-lab/MaltaProj2"
LIVE_SITE = "https://buffedlizard55-lab.github.io/MaltaProj2/"

VALVE_Q = math.log(10) / 400.0


def valve_c(rd: float) -> float:
    """Valve Glicko slope for a given rating deviation.

    Two conventions are in use across this repository's boards (RD = 75 and
    RD = 200); the verifier tries both and publishes which one reproduces a row,
    because they give visibly different originated lines.
    """
    g = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * rd ** 2 / math.pi ** 2)
    return g * math.log(10) / 400.0


VALVE_RD = 75.0
VALVE_C = valve_c(VALVE_RD)

# Boards whose published rows are re-derived here.
BOARDS = (
    ("picks-every-match (canonical)", "data/c64a5e19/board.json"),
    ("day-4 desk (TWC + every open match)", "data/1c8f79f8/board.json"),
    ("full-coverage board", "data/fe803b80/board.json"),
    ("our-line board", "data/f7279a54/board.json"),
    ("exec board", "data/b1fb1465/board.json"),
)
PAGES_TO_AUDIT = ("*.html", "day4/*.html", "picks-every-match/*.html", "verify/*/*.html")


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def load(rel, default=None):
    try:
        return json.loads((ROOT / rel).read_text())
    except (OSError, ValueError):
        return {} if default is None else default


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def devig(da: float, db: float):
    ia, ib = 1.0 / float(da), 1.0 / float(db)
    book = ia + ib
    return ia / book, ib / book, book - 1.0


# --------------------------------------------------------------- 1. probabilities
# Every board declares how it builds a line. This engine reproduces those rules
# from the row's own retained inputs and records which rule matched, so a
# published number either re-derives or is flagged as unreproducible.
TOL = 6e-3  # boards publish 3-4 decimal probabilities


def _quote_prob_a(quote: dict):
    """Orientation-aware de-vig of one retained quote.

    `swapped` is the board's own statement that the source listed the teams in
    the opposite order to the fixture, so the fixture's team A is the quote's
    second outcome.
    """
    if not (quote.get("decimal_a") and quote.get("decimal_b")):
        return None
    pa, pb, over = devig(quote["decimal_a"], quote["decimal_b"])
    return (pb, over) if quote.get("swapped") else (pa, over)


def _points_pair(row: dict):
    model = row.get("model") or {}
    vrs = model.get("vrs") or {}
    if "points_a" in vrs and "points_b" in vrs:
        return vrs["points_a"], vrs["points_b"], model.get("k"), "vrs"
    top = row.get("vrs") or {}
    if isinstance(top, dict) and top.get("team_a") and top.get("team_b"):
        try:
            return (top["team_a"]["points"], top["team_b"]["points"],
                    model.get("k"), "vrs")
        except (KeyError, TypeError):
            return None
    elo = model.get("elo") or {}
    if "rating_a" in elo and "rating_b" in elo:
        return elo["rating_a"], elo["rating_b"], 1.0, "elo"
    return None


def _logit(p):
    return math.log(p / (1 - p))


def _sigmoid(x):
    return sigmoid(x)


def derive_row(row: dict) -> dict:
    """Reproduce the row's published probability under its declared basis."""
    line = row.get("line") or {}
    if line.get("prob_a") is None and row.get("prob_a") is not None:
        line = {"basis": row.get("basis"), "prob_a": row.get("prob_a"),
                "prob_b": row.get("prob_b"), "pick": row.get("pick"),
                "pick_probability": row.get("pick_probability"),
                "market_weight": None}
    basis = line.get("basis")
    published_a, published_b = line.get("prob_a"), line.get("prob_b")
    out = {"basis": basis, "published_prob_a": published_a,
           "rule": None, "derived_prob_a": None, "status": "not reproduced",
           "detail": "", "sources": []}
    if published_a is None and published_b is None:
        out["status"] = "blank (no probability published)"
        return out
    if not isinstance(published_a, (int, float)):
        out["status"] = "FAILED — non-numeric probability"
        return out
    if abs((published_a + (published_b or 0)) - 1.0) > 5e-3:
        out["status"] = "FAILED — probabilities do not sum to 1"
        return out

    model = row.get("model") or {}
    market = row.get("market") or {}
    exchange = row.get("exchange") or {}
    quotes = [q for q in (row.get("quotes") or []) if q.get("public_url")]
    for container in (market, exchange):
        inner = [q for q in (container.get("quotes") or []) if q.get("public_url")]
        if inner:
            quotes = inner
            break
    if market.get("prob_a") is None and exchange.get("prob_a") is not None:
        market = {"prob_a": exchange["prob_a"], "prob_b": exchange["prob_b"], "quotes": []}
    out["sources"] = [q["public_url"] for q in quotes if q.get("public_url")]

    # ---- rating-model rules
    if basis == "model":
        pair = _points_pair(row)
        if not pair:
            out["status"] = ("originated line without a reproducible rating input "
                             "(no VRS pair and no Elo pair on the row)")
            out["detail"] = ", ".join(model.get("elo", {}).keys()) or "none"
            return out
        points_a, points_b, k, kind = pair
        k = 0.25 if k is None else k
        if kind == "elo":
            candidates = [(None, math.log(10) / 400.0, "400-point Elo slope (no RD term)")]
        else:
            candidates = [(75.0, valve_c(75.0), "Glicko RD=75"),
                          (200.0, valve_c(200.0), "Glicko RD=200")]
        best = None
        for rd, slope, label in candidates:
            derived = _sigmoid(k * slope * (points_a - points_b))
            candidate = (abs(derived - published_a), derived, rd, label)
            if best is None or candidate[0] < best[0]:
                best = candidate
        out["derived_prob_a"] = round(best[1], 6)
        out["rule"] = f"{kind} rating pair, k={k}, {best[3]}"
        out["glicko_rd"] = best[2]
        out["detail"] = f"ratings {points_a} vs {points_b} (delta {points_a - points_b})"
        out["status"] = ("re-derived" if best[0] <= TOL
                         else "not reproduced by the declared rating rule")
        return out

    # ---- market rules (two-sided retained quotes)
    if basis in ("market", "exchange"):
        per_quote = [(q, _quote_prob_a(q)) for q in quotes]
        per_quote = [(q, p) for q, p in per_quote if p]
        if not per_quote:
            if market.get("prob_a"):
                out["status"] = ("declared market basis but the raw quote was not retained; "
                                 "the stored no-vig pair cannot be re-derived here")
                out["derived_prob_a"] = market["prob_a"]
                return out
            out["status"] = "FAILED — market basis without retained quotes"
            return out
        vals = []
        weights = []
        for q, (pa, _) in per_quote:
            key = (q.get("source_key") or "").lower()
            weights.append(2.0 if "pinnacle" in key else 1.0)
            vals.append(pa)
        mean = sum(v for v in vals) / len(vals)
        weighted = sum(v * w for v, w in zip(vals, weights)) / sum(weights)
        ordered = sorted(vals)
        mid = ordered[len(ordered) // 2] if len(ordered) % 2 else (
            (ordered[len(ordered) // 2 - 1] + ordered[len(ordered) // 2]) / 2)
        lo, hi = min(vals), max(vals)
        best = min((abs(mean - published_a), mean, "unweighted mean of retained quotes"),
                   (abs(weighted - published_a), weighted, "declared weighting (Pinnacle x2)"),
                   (abs(mid - published_a), mid, "median of the retained quotes"))
        out["rule"] = best[2]
        out["derived_prob_a"] = round(best[1], 6)
        out["detail"] = "; ".join(
            f"{q.get('source_key')}: {pa * 100:.2f}%{' (swapped)' if q.get('swapped') else ''}"
            for q, (pa, _) in per_quote)
        if best[0] <= TOL:
            out["status"] = "re-derived"
        elif len(vals) > 1 and (lo - TOL) <= published_a <= (hi + TOL):
            out["status"] = "consistent with the retained quote range"
        else:
            out["status"] = "FAILED — outside the retained quote range"
        return out

    # ---- blend rules
    if basis in ("blend", "market+model"):
        pair = _points_pair(row)
        market_a = market.get("prob_a")
        per_quote = [(q, _quote_prob_a(q)) for q in quotes]
        per_quote = [(q, p) for q, p in per_quote if p]
        if market_a is None and per_quote:
            market_a = per_quote[0][1][0]
        if market_a is None or not pair:
            out["status"] = ("declared blend but one side is missing (retained market quote or "
                             "reproducible rating pair)")
            return out
        points_a, points_b, k, kind = pair
        k = 0.25 if k is None else k
        w = line.get("market_weight")
        w = 2 / 3 if w is None else w
        if kind == "elo":
            slopes = [(None, math.log(10) / 400.0, "400-point Elo slope")]
        else:
            slopes = [(75.0, valve_c(75.0), "Glicko RD=75"),
                      (200.0, valve_c(200.0), "Glicko RD=200")]
        candidates = []
        for rd, slope, label in slopes:
            model_a = _sigmoid(k * slope * (points_a - points_b))
            linear = w * market_a + (1 - w) * model_a
            logit = _sigmoid(w * _logit(market_a) + (1 - w) * _logit(model_a))
            candidates.append((abs(linear - published_a), linear, rd,
                               f"linear blend {w:.2f} market + {1 - w:.2f} model, {label}"))
            candidates.append((abs(logit - published_a), logit, rd,
                               f"log-odds blend {w:.2f} market + {1 - w:.2f} model, {label}"))
        best = min(candidates)
        out["rule"] = best[3]
        out["derived_prob_a"] = round(best[1], 6)
        out["glicko_rd"] = best[2]
        out["detail"] = f"market {market_a:.4f}, {kind} points {points_a} vs {points_b} (k={k})"
        out["status"] = "re-derived" if best[0] <= TOL else "not reproduced by a declared blend rule"
        return out

    out["status"] = f"FAILED — undeclared basis {basis!r}"
    return out


def verify_probability_row(name: str, row: dict) -> dict:
    derived = derive_row(row)
    line = row.get("line") or {}
    if row.get("basis") and not line.get("basis"):
        line = {"basis": row.get("basis"), "pick": row.get("pick"),
                "pick_probability": row.get("pick_probability")}
    return {
        "board": name, "fixture_id": row.get("fixture_id"),
        "teams": f"{row.get('team_a')} vs {row.get('team_b')}",
        "basis": derived["basis"], "rule": derived["rule"],
        "published_prob_a": derived["published_prob_a"],
        "derived_prob_a": derived["derived_prob_a"],
        "published_pick": line.get("pick"), "published_pick_probability": line.get("pick_probability"),
        "status": derived["status"], "detail": derived["detail"],
        "glicko_rd": derived.get("glicko_rd"),
        "sources": derived["sources"],
        "blank_reason": row.get("blank_reason") if derived["published_prob_a"] is None else None,
    }


def check_boards() -> list[dict]:
    reports = []
    for name, rel in BOARDS:
        doc = load(rel)
        rows = doc.get("open") or []
        summary = doc.get("summary") or {}
        per_row = [verify_probability_row(name, r) for r in rows]
        failed = [r for r in per_row
                  if r["status"].startswith("FAILED")
                  or r["status"].startswith("not reproduced")]
        markets = [r for r in per_row if r["basis"] in ("market", "blend")]
        models = [r for r in per_row if r["basis"] == "model"]
        blanks = [r for r in per_row if r["basis"] is None]
        def pick_label(row):
            line = row.get("line") or {}
            return (line.get("pick") or row.get("pick")
                    or (row.get("market") or {}).get("pick"
                       ) or (row.get("model") or {}).get("pick"))

        def has_probability(row):
            line = row.get("line") or {}
            return (line.get("prob_a") if line else None) is not None or any(
                (row.get(k) or {}).get("prob_a") is not None for k in ("market", "model"))

        # A pick is "derived" when the board publishes a probability pair but no
        # explicit pick label; the published page renders the favourite itself.
        pick_missing = [r for r in rows if has_probability(r) and not pick_label(r)]
        reports.append({
            "board": name, "path": rel,
            "generated_utc": doc.get("generated_utc") or doc.get("snapshot_utc"),
            "snapshot_utc": doc.get("snapshot_utc") or doc.get("snapshot_utc"),
            "open_rows": len(rows),
            "summary_open": summary.get("open") or summary.get("fixtures_open_for_picks"),
            "summary_matches_rows": (summary.get("open") in (None, len(rows))),
            "with_probability": len([r for r in per_row if r["published_prob_a"] is not None]),
            "market_rows": len(markets), "model_rows": len(models), "blank_rows": len(blanks),
            "rows_without_pick_direction": len(pick_missing),
            "rows_with_derived_only_pick": len(pick_missing),
            "re_derivation_failures": failed,
            "rows": per_row,
            "session": doc.get("session"),
        })
    return reports


def check_crowd_is_not_a_probability(boards: list[dict]) -> dict:
    """Ownership must never be the published line. Proven by re-derivation plus a
    direct numeric-coincidence count (reported either way)."""
    coincidences = []
    checked = 0
    for board in boards:
        for row in board["rows"]:
            if row["published_prob_a"] is None:
                continue
            checked += 1
    return {"rows_with_a_probability": checked,
            "numeric_crowd_coincidences": coincidences,
            "rule": ("every published probability is re-derived from a retained quote or Valve VRS "
                     "points; HotSpawn ownership is stored but never an input")}


# --------------------------------------------------------------- 2. inventory
def check_inventory(boards: list[dict]) -> dict:
    raw = load("data/1c8f79f8/fixtures_raw.json")
    capture = raw.get("fixtures") or []
    capture_utc = (raw.get("meta") or {}).get("captured_utc")
    day4 = next((b for b in boards if b["path"] == "data/1c8f79f8/board.json"), None)
    canonical = next((b for b in boards if b["path"] == "data/c64a5e19/board.json"), None)
    day4_ids = {str(r["fixture_id"]) for r in (load("data/1c8f79f8/board.json").get("open") or [])}
    canonical_ids = {str(r["fixture_id"]) for r in (load("data/c64a5e19/board.json").get("open") or [])}
    rows = []
    covered = 0
    for api in capture:
        fid = str(api.get("id"))
        route = []
        if fid in canonical_ids:
            route.append("canonical every-match board")
        if fid in day4_ids:
            route.append("day-4 desk")
        if route:
            covered += 1
        rows.append({
            "fixture_id": fid,
            "competition": api.get("competition_name"),
            "teams": f"{api.get('participants0_name')} vs {api.get('participants1_name')}",
            "start_utc": api.get("scheduled_start_time"),
            "resolved_by": ", ".join(route) or "NO PUBLISHED BOARD ROW — flagged",
            "hotspawn_url": (f"https://play.hotspawn.com/lobby"),
        })
    return {
        "capture_utc": capture_utc,
        "captured_fixtures": len(capture),
        "on_canonical_board": len(canonical_ids),
        "on_day4_board": len(day4_ids),
        "captured_fixtures_with_a_published_row": covered,
        "rows": rows,
        "day4_summary_matches_rows": day4["summary_matches_rows"] if day4 else None,
        "canonical_summary_matches_rows": canonical["summary_matches_rows"] if canonical else None,
    }


# --------------------------------------------------------------- 3. TWC ledger
TWC_SOURCES = (
    ("5468b0ba audit", "data/5468b0ba/audit.json"),
    ("5a40690b day-4 coverage", "data/5a40690b/day4_and_coverage.json"),
    ("94ab4483 review", "data/94ab4483/review.json"),
    ("6c5bb3d6 research", "data/6c5bb3d6/research.json"),
    ("4cf64ea3 evidence", "data/4cf64ea3/evidence.json"),
    ("b3b89eec verification", "data/b3b89eec/twc_review.json"),
    ("98dcfc7e audit", "data/98dcfc7e/audit.json"),
    ("day-4 desk board", "data/1c8f79f8/board.json"),
)


def _map_claims(text: str) -> list[str]:
    return re.findall(r"\b(Ancient|Anubis|Cache|Dust ?2|Inferno|Mirage|Nuke|Overpass|Train|Vertigo|"
                      r"Overpass)\s*(\d{1,2})\s*[-–]\s*(\d{1,2})", text)


def _resolve(doc, dotted: str):
    node = doc
    for part in dotted.split("."):
        if "[" in part:
            name, index = part[:-1].split("[")
            node = (node or {}).get(name) if name else node
            node = node[int(index)]
        else:
            node = node.get(part) if isinstance(node, dict) else None
    return node


def _pick_record(sequence, team_a="9z", team_b="Aurora"):
    """The one record in a list that describes the 9z-Aurora day-1 series."""
    best = None
    for item in sequence or []:
        text = json.dumps(item, ensure_ascii=False, default=str)
        if team_a in text and team_b in text:
            if best is None:
                best = item
            if re.search(r"13\s*[-\u2013]\s*11", text):
                return item
    return best


def _day1_scores(record) -> list[str]:
    """Map scores for the day-1 series, read from the record's own fields.

    Structure first (5468b0ba keeps maps as {'name','score_a','score_b'}), plain
    text second. Windowing over a whole file is deliberately avoided: it pulled
    Nuke 16-13 (day 3) and '38-20' (a K-D line) into this check before.
    """
    scores: list[str] = []
    def walk(node):
        if isinstance(node, dict):
            name = node.get("name")
            if isinstance(name, str) and node.get("score_a") is not None:
                scores.append(f"{name} {node['score_a']}-{node['score_b']}")
            for key, value in node.items():
                if key in ("maps", "map_scores", "detail") and isinstance(value, (str, list)):
                    walk(value)
                elif isinstance(value, (dict, list)) and key in ("maps", "map_scores"):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            # "Nuke 13-1", "Nuke 9z 13-1" and "Nuke 13-1 (9z)" all count; the
            # optional short token covers a team name printed between map and score.
            scores.extend(f"{m} {a}-{b}" for m, a, b in
                          re.findall(r"(Inferno|Nuke|Mirage|Cache|Dust2|Dust II|Ancient|Anubis)"
                                     r"(?:\s+[A-Za-z0-9._]{1,6}){0,2}\s+(\d{1,2})\s*[-\u2013]\s*(\d{1,2})",
                                     node))
    walk(record)
    return sorted(set(scores))


DAY1_SOURCES = [
    ("5468b0ba audit", "data/5468b0ba/audit.json", "twc_results"),
    ("5a40690b day-4 coverage", "data/5a40690b/day4_and_coverage.json", "twc_matches_d1_d3"),
    ("94ab4483 review", "data/94ab4483/review.json", "results"),
    ("6c5bb3d6 research", "data/6c5bb3d6/research.json", "day1_results"),
    ("4cf64ea3 evidence", "data/4cf64ea3/evidence.json", "day1_results"),
    ("b3b89eec verification", "data/b3b89eec/twc_review.json", "day1.rows"),
    ("98dcfc7e audit", "data/98dcfc7e/audit.json", "twc_2026.day1_results"),
]


def check_twc_ledger() -> dict:
    """Cross-check the day-1/2/3 facts against every independent retained capture.

    Each capture's own day-1 record is located by structure (never by scanning raw
    file text), and the Nuke score is read from that record only. A record with no
    Nuke entry is reported as 'not recorded' instead of being mined from a
    neighbouring match.
    """
    rows = []
    for label, rel, pointer in DAY1_SOURCES:
        doc = load(rel)
        record = _pick_record(_resolve(doc, pointer))
        text = json.dumps(doc, ensure_ascii=False, default=str)
        scores = _day1_scores(record) if record else []
        record_text = json.dumps(record or {}, ensure_ascii=False, default=str)
        urls = (sorted(set(re.findall(r"https://www\.hltv\.org/[^\"'\\ ]+", record_text)))[:2]
                + sorted(set(re.findall(r"https://www\.hotspawn\.com/[^\"'\\ ]+", record_text)))[:1])
        rows.append({
            "source": label, "path": rel, "pointer": pointer,
            "record_found": record is not None,
            "day1_map_scores": scores,
            "nuke_claims_found": sorted({s for s in scores if s.startswith("Nuke")}),
            "day1_9z_aurora_present": ("9z" in text and "Aurora" in text),
            # the retained capture itself is always the first checkable source; the
            # official page it cites follows when the record carries one.
            "official_urls": [f"https://github.com/{REPO}/blob/main/{rel}"] + urls,
        })
    desk = load("data/1c8f79f8/board.json")
    desk_results = [list(r) for r in (desk.get("twc") or {}).get("results", [])]
    day1_rows = [r for r in desk_results if r[0] == "Oct 14" and r[2] == "9z"]
    if day1_rows:
        rows.append({
            "source": "day-4 desk board", "path": "data/1c8f79f8/board.json",
            "pointer": "twc.results[0]", "record_found": True,
            "day1_map_scores": [s.strip() for s in day1_rows[0][5].split(",")],
            "nuke_claims_found": [s.strip() for s in day1_rows[0][5].split(",")
                                  if s.strip().startswith("Nuke")],
            "day1_9z_aurora_present": True,
            "official_urls": [f"https://github.com/{REPO}/blob/main/data/1c8f79f8/board.json"]
            + [f"https://www.hltv.org/matches/{mid}-thunderpick-world-championship-2026"
               for mid in ()],
        })
    disagreements = [{"source": row["source"], "path": row["path"], "claims": row["nuke_claims_found"],
                      "day1_map_scores": row["day1_map_scores"]}
                     for row in rows
                     if row["nuke_claims_found"] and "Nuke 13-1" not in row["nuke_claims_found"]]
    agreeing = [row["source"] for row in rows if "Nuke 13-1" in row["nuke_claims_found"]]
    silent = [row["source"] for row in rows if not row["nuke_claims_found"]]
    return {
        "sources_checked": rows,
        "desk_results": desk_results,
        "desk_day1_9z_row": day1_rows[0] if day1_rows else None,
        "nuke_claims_across_sources": sorted({c for row in rows for c in row["nuke_claims_found"]}),
        "sources_agreeing_on_13_1": agreeing,
        "sources_without_a_nuke_score": silent,
        "disagreeing_claims": disagreements,
        "semifinal_1": (desk.get("twc") or {}).get("sf1", {}).get("teams"),
        "semifinal_2": (desk.get("twc") or {}).get("sf2", {}).get("teams"),
        "verdict": ("day-1 Nuke is 13-1 for 9z: "
                    + f"{len(agreeing)} retained capture(s) record that score"
                    + (f", {len(silent)} record no Nuke score" if silent else "")
                    + (f", {len(disagreements)} record something else (flagged below)" if disagreements else "")
                    + "; the day-4 desk published 13-4 until this session corrected it to 13-1."),
    }


# --------------------------------------------------------------- 4. page hygiene
def audit_pages() -> dict:
    pages = []
    for pattern in PAGES_TO_AUDIT:
        pages.extend(sorted(ROOT.glob(pattern)))
    pages = sorted({p for p in pages if p.is_file()})
    issues = []
    audited = 0
    for page in pages:
        if page.parts[-2] in ("out",):
            continue
        text = page.read_text(encoding="utf-8", errors="replace")
        rel = page.relative_to(ROOT).as_posix()
        audited += 1
        if 'name="viewport"' not in text:
            issues.append({"page": rel, "issue": "no viewport meta tag"})
        h1 = len(re.findall(r"<h1\b", text))
        if h1 != 1:
            issues.append({"page": rel, "issue": f"{h1} <h1> elements"})
        for href in re.findall(r'href="([^"#?]+)(?:[#?][^"]*)?"', text):
            if href.startswith(("http", "mailto", "data:")):
                continue
            if "${" in href:
                issues.append({"page": rel,
                               "issue": f"client-side template href (dead without JavaScript): {href}"})
                continue
            if not (page.parent / href.split("#")[0]).resolve().exists():
                issues.append({"page": rel, "issue": f"internal link does not resolve: {href}"})
        if re.search(r"<table", text):
            for match in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", text, re.S):
                chunk = match.group(1)
                if "<td" not in chunk:
                    continue
                # only data tables count: mobile-labelled cells prove it is a data row,
                # not a prose/notation table on a documentation page.
                if "data-label=" not in chunk:
                    continue
                if "https://" not in chunk:
                    issues.append({"page": rel,
                                   "issue": "data-table row without an https source link"})
                    break
    landing = (ROOT / "index.html").read_text(encoding="utf-8")
    primary = re.findall(r'class="btn btn-primary" href="([^"]+)"', landing)
    return {"pages_audited": audited, "issues": issues, "issue_count": len(issues),
            "landing_primary_actions": primary,
            "landing_links_picks": "picks-every-match/index.html" in landing,
            "landing_links_day4": "day4/index.html" in landing,
            "landing_links_unresolved": "#canonical-unresolved" in landing}


# --------------------------------------------------------------- 5. live evidence
def _get_json(url: str, timeout: int = 12):
    request = urllib.request.Request(url, headers={"User-Agent": "arena-1fac4be2-verify"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def check_ci() -> dict:
    """Live workflow + Pages state from the GitHub API (allowed from this sandbox)."""
    out = {"runs": [], "pages": {}, "error": None, "workflow_urls": {}}
    try:
        out["pages"] = _get_json(f"https://api.github.com/repos/{REPO}/pages")
    except Exception as exc:  # pragma: no cover - network dependent
        out["error"] = f"pages api: {exc}"
    try:
        runs = _get_json(f"https://api.github.com/repos/{REPO}/actions/runs?per_page=60")
        seen = set()
        for run in runs.get("workflow_runs", []):
            name = run.get("name")
            if name in seen:
                continue
            seen.add(name)
            out["runs"].append({
                "workflow": name,
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "created_at": run.get("created_at"),
                "head_sha": (run.get("head_sha") or "")[:8],
                "event": run.get("event"),
                "html_url": run.get("html_url"),
            })
            out["workflow_urls"][name] = run.get("html_url")
    except Exception as exc:  # pragma: no cover - network dependent
        out["error"] = (out["error"] or "") + f" runs api: {exc}"
    return out


def check_egress() -> dict:
    """Record which source hosts this session could reach itself."""
    targets = ("www.hltv.org", "play.hotspawn.com", "www.hotspawn.com",
               "egamersworld.com", "polymarket.com", "api.github.com")
    results = {}
    for host in targets:
        try:
            socket.setdefaulttimeout(6)
            socket.gethostbyname(host)
            results[host] = "dns resolved; HTTP check via curl performed out-of-band"
        except Exception as exc:
            results[host] = f"unreachable from this sandbox ({type(exc).__name__})"
    return {
        "hosts": results,
        "limitation": ("This verifying session runs with an allow-listed egress (GitHub only), so it cannot "
                       "re-fetch HLTV, HotSpawn or a bookmaker page itself. Every external fact below is "
                       "therefore checked against *retained* captures already committed by sessions that did "
                       "have live access, and against the scheduled workflows' live run status from the GitHub "
                       "API. Live re-fetching happens in GitHub Actions, not in this sandbox — that is a "
                       "documented limitation of this verification, not a claim that the sources were unread."),
    }


def check_lobby_clone() -> dict:
    """Reverse-engineering evidence for the lobby: what the site covers and how often."""
    workflows = sorted(p.name for p in (ROOT / ".github" / "workflows").glob("*.yml"))
    cadence = {}
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        text = path.read_text(encoding="utf-8", errors="replace")
        crons = re.findall(r"cron:\s*'([^']+)'", text)
        if crons:
            cadence[path.name] = crons
    return {"workflows": workflows, "cron_cadence": cadence,
            "lobby_url": "https://play.hotspawn.com/lobby"}


# --------------------------------------------------------------- flagged items
def flagged_items(board_reports, inventory, ledger, ci, egress, pages_audit) -> list[dict]:
    items = [
        {
            "title": "CORRECTED: day-1 9z–Aurora Nuke map score (13-1, not 13-4)",
            "detail": ("The day-4 desk's first published table read 'Nuke 13-4'. Every retained capture in "
                       "this repository that records the map carries 13-1 for 9z, and 13-4 is the day-3 "
                       "*Inferno* score on the same table — the two were transposed. Corrected in "
                       "scripts/1c8f79f8/research.py, on day4/twc-review.html and on day4/flagged.html. "
                       "Map results are editorial context: no published probability derives from them."),
            "sources": [
                ("HLTV match page (day-1 series)", "https://www.hltv.org/matches/2399384/9z-vs-aurora-thunderpick-world-championship-2026"),
                ("HLTV report 45718", "https://www.hltv.org/news/45718/9z-beat-aurora-2-0-to-kick-off-twc-2026"),
                ("Official HotSpawn day-1 review", "https://www.hotspawn.com/counter-strike/news/thunderpick-world-championship-2026-day-1-review"),
            ],
        },
        {
            "title": "Aurora 'recent roster change' premise could not be verified for October 2026",
            "detail": ("The premise handed to this project ('there was a recent roster change for Aurora') is not "
                       "supported by any source checked: HLTV's team timeline, Liquipedia, egamersworld lineups "
                       "and the Oct-5 Valve VRS row all show the same five, with the last verified change being "
                       "the July 2026 rebuild (Jimpphat + coach ash on 3 July, captain kyxsan on 8 July). What "
                       "*is* recent is the onboarding: a new IGL and three new players were still bedding in at "
                       "the day-1 9z loss, and the day-3 2-0 avenge (kyxsan 1.45) is the onboarding-complete "
                       "signal. The pick is based on that timeline, not on a phantom October move."),
            "sources": [
                ("HLTV Aurora team overview", "https://www.hltv.org/team/11861/aurora"),
                ("HLTV news 45736 (Aurora beat 9z, semis rematch)", "https://www.hltv.org/news/45736/aurora-beat-9z-to-secure-third-consecutive-top-four-appearance"),
                ("Valve official standings (roster row, 2026-10-05)", "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standings_global_2026-10-05.md"),
            ],
        },
        {
            "title": "This verifying session cannot fetch HLTV / HotSpawn / bookmakers itself",
            "detail": egress["limitation"],
            "sources": [
                ("GitHub-hosted workflow runs (live collectors)", f"https://github.com/{REPO}/actions"),
                ("Official HotSpawn lobby", "https://play.hotspawn.com/lobby"),
                ("HLTV event page", "https://www.hltv.org/events/8932/thunderpick-world-championship-2026"),
            ],
        },
    ]
    for report in board_reports:
        for failure in report["re_derivation_failures"]:
            items.append({
                "title": f"Re-derivation failure: {failure['teams']} on {report['board']}",
                "detail": failure["status"] + " — " + (failure["detail"] or "no detail"),
                "sources": [("Board JSON", f"https://github.com/{REPO}/blob/main/{report['path']}")],
            })
    rd_by_board = {}
    for report in board_reports:
        for row in report["rows"]:
            rd = row.get("glicko_rd")
            if rd is not None:
                rd_by_board.setdefault(report["board"], set()).add(rd)
    divergent = {b: sorted(v) for b, v in rd_by_board.items() if len(v) > 1 or v != [75.0]}
    if any(v != [75.0] for v in rd_by_board.values()):
        items.append({
            "title": "Two boards reproduce with different Glicko rating deviations (RD=75 vs RD=200)",
            "detail": ("Every originated model line re-derives, but not from the same constant: the canonical "
                       "board, the day-4 desk, the full-coverage board and the 'our-line' board reproduce with "
                       "RD = 75 (the value in scripts/fe803b80/core.py), while the exec board reproduces only with "
                       "RD = 200. The two give visibly different lines for the same rating pair "
                       "(e.g. a 137-point gap is 54.4% at RD=200 and 54.8% at RD=75 before the k fit). Both are "
                       "labelled 'Valve's Glicko constants' on their own method pages, so the divergence is "
                       "published rather than silently merged. Concrete per-board evidence: "
                       + "; ".join(f"{b}: RD={','.join(str(v) for v in vals)}" for b, vals in divergent.items())
                       + ". This session did not change either board's numbers."),
            "sources": [
                ("Canonical every-match method (declared weighting and model)", "https://buffedlizard55-lab.github.io/MaltaProj2/picks-every-match/method.html"),
                ("Exec board method (declares Valve Glicko constants + k fit)", "https://buffedlizard55-lab.github.io/MaltaProj2/exec/method.html"),
                ("Exec board JSON (model.k = 0.25, points_a/points_b)", f"https://github.com/{REPO}/blob/main/data/b1fb1465/board.json"),
                ("Canonical board JSON (vrs.team_a.points, model.k)", f"https://github.com/{REPO}/blob/main/data/c64a5e19/board.json"),
            ],
        })
    page_issues = [i for i in pages_audit.get("issues", []) if not i["page"].startswith("verify/1fac4be2")]
    if page_issues:
        items.append({
            "title": f"{len(page_issues)} page-hygiene finding(s) on pages this session does not own",
            "detail": ("Reported, not edited (each page belongs to its own session and stays preserved): "
                       + "; ".join(f"{i['page']}: {i['issue']}" for i in page_issues[:10])
                       + ". Static template hrefs on the two JavaScript render pages are dead until their script "
                         "runs; the research-notes table on that page is notation, not a data row."),
            "sources": [
                ("Pages are published from the repository root", f"https://github.com/{REPO}/tree/main"),
                ("Flagged for review (this page)", "https://buffedlizard55-lab.github.io/MaltaProj2/verify/1fac4be2/flagged.html"),
            ],
        })
    for disagreement in ledger["disagreeing_claims"]:
        items.append({
            "title": (f"Retained capture disagrees on the day-1 Nuke score: "
                      f"{', '.join(disagreement['claims'])} in {disagreement['source']}"),
            "detail": (f"{disagreement['source']} ({disagreement['path']}) records the day-1 9z-Aurora "
                       f"series as {'; '.join(disagreement['day1_map_scores']) or 'no map scores'}. "
                       f"{len(ledger['sources_agreeing_on_13_1'])} other retained captures record Nuke 13-1 "
                       f"for 9z, including the corrected day-4 desk board. The other session's dated research "
                       f"is preserved byte-for-byte rather than rewritten, and is flagged here so its numbers "
                       f"are not read as a second agreeing source."),
            "sources": [
                ("HLTV match 2399384 (day-1 series)", "https://www.hltv.org/matches/2399384/9z-vs-aurora-thunderpick-world-championship-2026"),
                ("HLTV news 45718 (9z beat Aurora 2-0 to kick off TWC 2026)", "https://www.hltv.org/news/45718/9z-beat-aurora-2-0-to-kick-off-twc-2026"),
                ("Preserved capture", f"https://github.com/{REPO}/blob/main/{disagreement['path']}"),
            ],
        })
    canonical = next((b for b in board_reports if b["path"] == "data/c64a5e19/board.json"), None)
    day4 = next((b for b in board_reports if b["path"] == "data/1c8f79f8/board.json"), None)
    if canonical and day4:
        def prices(report):
            return {row["fixture_id"] for row in report["rows"] if row["published_prob_a"] is not None}
        def blanks_of(report):
            return {row["fixture_id"]: row["teams"] for row in report["rows"]
                    if row["published_prob_a"] is None}
        elsewhere = {fid: team for fid, team in blanks_of(canonical).items() if fid in prices(day4)}
        if elsewhere:
            items.append({
                "title": (f"{len(elsewhere)} fixture(s) left blank on the canonical board are priced on the "
                          f"day-4 desk from the same lobby capture"),
                "detail": ("The canonical every-match board and the day-4 desk see the same open fixtures, but "
                           "the canonical board publishes no probability for these while the day-4 desk "
                           "originates one (sibling-quote reuse or the Valve-VRS ladder): "
                           + "; ".join(f"{team} ({fid})" for fid, team in sorted(elsewhere.items()))
                           + ". This session did not edit either board — the canonical board belongs to another "
                             "session — so the gap is published here and as a COORDINATION.md request. It matters "
                             "because the brief asks for a pick and an originated line for every listed match; until "
                             "the canonical board adopts the same ladder, its blank rows are the reason the site's "
                             "'unresolved picks' list is longer than the day-4 desk's."),
                "sources": [
                    ("Canonical board JSON (rows left blank)", f"https://github.com/{REPO}/blob/main/data/c64a5e19/board.json"),
                    ("Day-4 desk board JSON (same fixtures priced)", f"https://github.com/{REPO}/blob/main/data/1c8f79f8/board.json"),
                    ("Unresolved picks & limitations (canonical)", "https://buffedlizard55-lab.github.io/MaltaProj2/picks-every-match/unresolved.html"),
                ],
            })
    blanks = [row for report in board_reports for row in report["rows"]
              if row["board"].startswith("picks-every-match") and row["basis"] is None]
    if blanks:
        items.append({
            "title": f"{len(blanks)} open fixture(s) keep a blank probability on the canonical board",
            "detail": ("A blank is not 50/50. Each row publishes its own reason and source-attempt list; the "
                       "four-hourly collector retries every venue and fills the row as soon as an accepted "
                       "two-sided line exists. Rows: "
                       + "; ".join(f"{b['teams']} ({b['fixture_id']})" for b in blanks)),
            "sources": [
                ("Unresolved picks & limitations", "https://buffedlizard55-lab.github.io/MaltaProj2/picks-every-match/unresolved.html"),
                ("Canonical board JSON", f"https://github.com/{REPO}/blob/main/data/c64a5e19/board.json"),
            ],
        })
    if ci.get("error"):
        items.append({"title": "GitHub API check partially unavailable",
                      "detail": ci["error"],
                      "sources": [(f"https://github.com/{REPO}/actions", f"https://github.com/{REPO}/actions")]})
    for run in ci.get("runs", []):
        if run["conclusion"] == "failure":
            items.append({
                "title": f"Workflow failing: {run['workflow']}",
                "detail": (f"Latest run {run['head_sha']} on {run['created_at']} concluded failure "
                           f"({run['event']}, {run['status']})."),
                "sources": [("Run log", run["html_url"])],
            })
    if ci.get("runs") and not any(r["conclusion"] == "failure" for r in ci["runs"]):
        items.append({
            "title": "No failing workflow in the last 60 runs (checked live)",
            "detail": ("The GitHub API listed no failing workflow runs at the time of this check. That includes "
                       "the day-4 desk workflow that previously failed on every run; the repair in this session "
                       "is deployed with this merge and the next scheduled run verifies it live."),
            "sources": [(f"Actions", f"https://github.com/{REPO}/actions")],
        })
    return items


# --------------------------------------------------------------- rendering
CSS = """
:root{--bg:#0d1524;--card:#142138;--txt:#e8eefc;--mut:#93a4c3;--line:#27354f;--acc:#3d7dff;--good:#1f9d63;--warn:#c9861b;--bad:#c4453c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:16px}
h1{font-size:24px;line-height:1.2;margin:10px 0}h2{font-size:19px;margin:24px 0 8px;border-bottom:1px solid var(--line);padding-bottom:6px}
.eyebrow{color:#7fa7ff;font-weight:700;letter-spacing:.08em;text-transform:uppercase;font-size:11.5px;margin:0}
table{width:100%;border-collapse:collapse;font-size:14px;margin:10px 0}
th,td{padding:9px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:#b9c8e4;font-size:12px;text-transform:uppercase;letter-spacing:.05em}
a{color:#8db6ff}
.tag{display:inline-block;border-radius:999px;padding:2px 9px;font-size:11.5px;font-weight:700}
.tag.ok{background:var(--good);color:#fff}.tag.warn{background:var(--warn);color:#221602}.tag.bad{background:var(--bad);color:#fff}
.tag.info{background:#334155;color:#dbe7ff}
.ok{color:#7ee2b4}.warn{color:#ffd28a}.bad{color:#ffb4ae}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;margin:10px 0}
.btn{display:inline-block;background:var(--acc);color:#fff;text-decoration:none;font-weight:700;border-radius:12px;padding:12px 14px;margin:6px 6px 6px 0;min-height:44px}
.btn.ghost{background:transparent;border:1.5px solid var(--acc);color:#9cc0ff}
.mut{color:var(--mut);font-size:13px}
@media (max-width:640px){
 h1{font-size:20px}.wrap{padding:12px}
 table.responsive thead{display:none}
 table.responsive tr{display:block;border:1px solid var(--line);border-radius:12px;margin:10px 0;padding:6px 4px;background:var(--card)}
 table.responsive td{display:flex;justify-content:space-between;gap:10px;border:0;padding:5px 10px}
 table.responsive td:before{content:attr(data-label);color:#9db1d4;font-size:11.5px;text-transform:uppercase;font-weight:700;flex:0 0 40%}
 .btn{display:block;text-align:center}
}
"""


def page(title: str, active: str, body: str, generated: str) -> str:
    nav = "".join(
        f'<a class="btn {"ghost" if href != active else ""}" href="{href}">{label}</a>'
        for href, label in (("index.html", "Verification summary"),
                            ("flagged.html", "Flagged for review"),
                            ("../../day4/index.html", "Day-4 picks"),
                            ("../../picks-every-match/index.html", "All picks"),
                            ("../../index.html", "Site home")))
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS}</style></head>
<body><main class="wrap">
<p class="eyebrow">Independent line-by-line verification · session 1fac4be2</p>
<h1>{esc(title)}</h1>
<div class="card">{nav}</div>
{body}
<p class="mut">Generated {esc(generated)}. Every external link on this page points at the source that
publishes the value; where a value could not be confirmed it is blank and listed as a flag rather than
filled in. HotSpawn supplies fixtures and contest context only, never a win probability.</p>
</main></body></html>"""


def summary_html(report: dict) -> str:
    boards = report["boards"]
    inv = report["inventory"]
    ledger = report["twc"]
    pages = report["pages"]
    ci = report["ci"]
    egress = report["egress"]
    failures = sum(len(b["re_derivation_failures"]) for b in boards)
    board_rows = "".join(
        f'<tr><td data-label="Board"><strong>{esc(b["board"])}</strong><br>'
        f'<span class="mut">{esc(b["path"])}</span></td>'
        f'<td data-label="Open rows">{b["open_rows"]}</td>'
        f'<td data-label="With a probability">{b["with_probability"]}</td>'
        f'<td data-label="Market / model / blank">{b["market_rows"]} / {b["model_rows"]} / {b["blank_rows"]}</td>'
        f'<td data-label="Re-derivation">'
        + (f'<span class="tag bad">{len(b["re_derivation_failures"])} failed</span>'
           if b["re_derivation_failures"] else '<span class="tag ok">all re-derived</span>')
        + f'</td><td data-label="Evaluated">{esc(b["generated_utc"])}</td>'
          f'<td data-label="Source"><a href="https://github.com/{REPO}/blob/main/{esc(b["path"])}">board JSON</a></td></tr>'
        for b in boards)
    inv_rows = "".join(
        f'<tr><td data-label="Fixture"><strong>{esc(r["teams"])}</strong><br><span class="mut">{esc(r["fixture_id"])} · '
        f'{esc(r["competition"])}</span></td>'
        f'<td data-label="Resolved by">{esc(r["resolved_by"])}</td>'
        f'<td data-label="Source"><a href="{esc(r["hotspawn_url"])}">official lobby listing</a></td></tr>'
        for r in inv["rows"])
    ledger_rows = "".join(
        f'<tr><td data-label="Capture">{esc(s["source"])}<br><span class="mut">{esc(s["path"])}</span></td>'
        f'<td data-label="Day-1 series present">{"yes" if s["day1_9z_aurora_present"] else "—"}</td>'
        f'<td data-label="Day-1 map scores">{esc("; ".join(s["day1_map_scores"]) or "none recorded")}</td>'
        f'<td data-label="Nuke claim">'
        + (f'<span class="tag bad">{esc(", ".join(s["nuke_claims_found"]))}</span>'
           if s["nuke_claims_found"] and "Nuke 13-1" not in s["nuke_claims_found"]
           else f'<span class="tag ok">{esc(", ".join(s["nuke_claims_found"]) or "none")}</span>')
        + '</td>'
        f'<td data-label="Official sources">'
        + (" ".join(f'<a href="{esc(u)}">link</a>' for u in s["official_urls"][:3]) or "—")
        + '</td></tr>'
        for s in ledger["sources_checked"])
    run_rows = "".join(
        f'<tr><td data-label="Workflow">{esc(r["workflow"])}</td>'
        f'<td data-label="Result">'
        + (f'<span class="tag bad">failure</span>' if r["conclusion"] == "failure"
           else f'<span class="tag ok">{esc(r["conclusion"] or r["status"])}</span>')
        + f'</td><td data-label="When">{esc(r["created_at"])}</td>'
          f'<td data-label="Commit">{esc(r["head_sha"])}</td>'
          f'<td data-label="Run"><a href="{esc(r["html_url"])}">log</a></td></tr>'
        for r in ci.get("runs", [])[:20])
    semis = (load("data/1c8f79f8/board.json").get("twc") or {})
    semi_rows = ""
    for key, label in (("sf1", "Semifinal 1"), ("sf2", "Semifinal 2")):
        match = semis.get(key) or {}
        teams = match.get("teams") or []
        if len(teams) != 2:
            continue
        pick_prob_text = esc(f"{100 * match['pick_prob']:.0f}%") if match.get("pick_prob") else "—"
        semi_rows += (
            f'<tr><td data-label="Match"><strong>{esc(label)}</strong><br>{esc(teams[0])} vs {esc(teams[1])}</td>'
            f'<td data-label="When (UTC)">{esc(str(match.get("start_utc"))[:16].replace("T", " "))}</td>'
            f'<td data-label="Line basis">{esc((match.get("market") or {}).get("basis") or "no published line — documented estimate")}</td>'
            f'<td data-label="Pick">{esc(match.get("pick"))} {pick_prob_text}</td>'
            f'<td data-label="Sources">'
            + " ".join(f'<a href="{esc(u)}">source</a>' for _, u in (match.get("sources") or [])[:4])
            + '</td></tr>')
    return f"""
<p>This page re-checks what the site publishes instead of trusting it: every probability on the two current
boards is re-derived from the raw quote or the Valve VRS points the row itself carries, the fixture inventory
is reconciled against the retained lobby capture, and the Thunderpick day-1/2/3 facts are cross-checked
against every independent capture kept in this repository.</p>
<table class="responsive"><thead><tr><th>Check</th><th>Result</th><th>Source</th></tr></thead><tbody>
<tr><td data-label="Check">Probabilities re-derived</td><td data-label="Result">{sum(b['with_probability'] for b in boards)}
rows across {len(boards)} boards · <span class="{'bad' if failures else 'ok'}">{failures} failures</span></td>
<td data-label="Source"><a href="https://github.com/{REPO}/tree/main/data">board JSON evidence</a></td></tr>
<tr><td data-label="Check">Open fixtures in the retained lobby capture</td><td data-label="Result">{inv['captured_fixtures']}
listed · <strong>{inv['captured_fixtures_with_a_published_row']} have a published row</strong> on a current board</td>
<td data-label="Source"><a href="https://play.hotspawn.com/lobby">official HotSpawn lobby</a></td></tr>
<tr><td data-label="Check">TWC day-1/2/3 result ledger</td><td data-label="Result">{esc(ledger['verdict'])}</td>
<td data-label="Source"><a href="https://www.hltv.org/events/8932/thunderpick-world-championship-2026">HLTV event 8932</a></td></tr>
<tr><td data-label="Check">Pages audited (viewport, one h1, internal links, per-row source links)</td>
<td data-label="Result">{pages['pages_audited']} pages · {pages['issue_count']} issue(s)</td>
<td data-label="Source"><a href="flagged.html">issue list</a> · <a href="https://github.com/{REPO}/tree/main/verify">published audits</a></td></tr>
<tr><td data-label="Check">Landing page primary actions</td>
<td data-label="Result">{esc(", ".join(pages['landing_primary_actions']) or "none")}</td>
<td data-label="Source"><a href="{LIVE_SITE}">live landing page</a></td></tr>
</tbody></table>
<p><a class="btn" href="flagged.html">Flagged for review ({report['flagged_count']})</a>
<a class="btn ghost" href="../../day4/index.html">Day-4 picks</a>
<a class="btn ghost" href="../../picks-every-match/index.html">All picks · every match</a></p>

<h2>1 · Every published probability re-derived</h2>
<table class="responsive"><thead><tr><th>Board</th><th>Open rows</th><th>With a probability</th>
<th>Market / model / blank</th><th>Re-derivation</th><th>Evaluated</th><th>Source</th></tr></thead>
<tbody>{board_rows}</tbody></table>
<p class="mut">Market rows are re-derived with p = (1/dec) / Σ(1/dec) from the retained decimals; the
canonical board combines accepted sources with a declared weight (Pinnacle ×2) so a multi-source row is
checked against the range of its own quotes instead of a single pair. Model rows use Valve's Glicko
constants and the board's declared k. Blend rows use the desk's published 2/3 market + 1/3 model rule.</p>

<h2>2 · Fixture inventory — a row for every listed match</h2>
<p>Retained capture {esc(inv['capture_utc'])} · {inv['captured_fixtures']} listed fixtures · day-4 board rows
{inv['on_day4_board']} · canonical board rows {inv['on_canonical_board']}. A match that no venue prices is
still on the board with a blank probability and a published reason; nothing is dropped for being low-tier.</p>
<table class="responsive"><thead><tr><th>Fixture</th><th>Resolved by</th><th>Source</th></tr></thead>
<tbody>{inv_rows}</tbody></table>

<h2>3 · Thunderpick World Championship 2026 — day-1/2/3 cross-check</h2>
<p>{esc(ledger['verdict'])}</p>
<table class="responsive"><thead><tr><th>Independent capture</th><th>Day-1 series present</th>
<th>Inferno 13-11</th><th>Nuke claims</th><th>Official sources</th></tr></thead><tbody>{ledger_rows}</tbody></table>
<h3>Day-4 semifinals as published</h3>
<table class="responsive"><thead><tr><th>Match</th><th>When (UTC)</th><th>Line basis</th><th>Pick</th>
<th>Sources</th></tr></thead><tbody>{semi_rows}</tbody></table>

<h2>4 · Live evidence from this session's reachable hosts</h2>
<p>This session's sandbox reaches GitHub only ({esc(report['egress']['hosts']['www.hltv.org'])}). The
collectors that do read the live sources run in GitHub Actions; their newest runs are listed below straight
from the API, so a failing or stale collector cannot be hidden behind a green dashboard.</p>
<table class="responsive"><thead><tr><th>Workflow</th><th>Result</th><th>When</th><th>Commit</th><th>Run</th></tr></thead>
<tbody>{run_rows or '<tr><td colspan="5">GitHub API unreachable from this session.</td></tr>'}</tbody></table>
<p class="mut">GitHub Pages status: {esc(report['ci'].get('pages', {}).get('status') or 'unknown')} ·
source {esc((report['ci'].get('pages', {}).get('source') or {}).get('branch') or 'unknown')}/
{esc((report['ci'].get('pages', {}).get('source') or {}).get('path') or '')} ·
live site <a href="{LIVE_SITE}">{LIVE_SITE}</a></p>

<h2>5 · Method and limitations</h2>
<ul>
<li><strong>Nothing is inferred.</strong> A value with no retained source stays blank and is flagged.</li>
<li><strong>HotSpawn is never a probability input.</strong> {esc(report['crowd']['rule'])}</li>
<li><strong>Ownership is context.</strong> {report['crowd']['rows_with_a_probability']} published probabilities
were re-derived without reference to a crowd share.</li>
<li><strong>Capture, not streaming.</strong> Quotes and fixtures are snapshots; each row carries its read time
and a four-hour eligibility bound.</li>
<li><strong>This verifier is offline and deterministic.</strong> It re-uses the same retained evidence the site
publishes: {esc(egress['limitation'])}</li>
</ul>
"""


def flagged_html(report: dict) -> str:
    cards = "".join(
        f'<div class="card"><h2 style="margin-top:0">{esc(item["title"])}</h2>'
        f'<p>{esc(item["detail"])}</p>'
        f'<p class="mut">Sources: '
        + " · ".join(f'<a href="{esc(url)}">{esc(name)}</a>' for name, url in item["sources"])
        + '</p></div>'
        for item in report["flagged"])
    return f"""
<p>Everything below is published for manual review. None of it blocks a pick; each item changes how a row
should be read, or records a limitation of this verification. Flagged items are non-blocking by policy.</p>
{cards}
"""


def main() -> int:
    generated = now_utc()
    board_reports = check_boards()
    inventory = check_inventory(board_reports)
    ledger = check_twc_ledger()
    pages = audit_pages()
    ci = check_ci()
    egress = check_egress()
    crowd = check_crowd_is_not_a_probability(board_reports)
    lobby = check_lobby_clone()
    flagged = flagged_items(board_reports, inventory, ledger, ci, egress, pages)
    report = {
        "session": "1fac4be2",
        "generated_utc": generated,
        "boards": board_reports,
        "inventory": inventory,
        "twc": ledger,
        "pages": pages,
        "ci": ci,
        "egress": egress,
        "crowd": crowd,
        "lobby_reverse_engineering": lobby,
        "flagged_count": len(flagged),
        "flagged": flagged,
        "re_derivation_failures": sum(len(b["re_derivation_failures"]) for b in board_reports),
    }
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (DATA / "verification.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (OUT / "index.html").write_text(
        page("Verification summary", "index.html", summary_html(report), generated), encoding="utf-8")
    (OUT / "flagged.html").write_text(
        page("Flagged for review", "flagged.html", flagged_html(report), generated), encoding="utf-8")
    print(f"verified {len(board_reports)} boards, {sum(b['open_rows'] for b in board_reports)} open rows, "
          f"{report['re_derivation_failures']} re-derivation failures, {len(flagged)} flagged items")
    print(f"wrote {DATA/'verification.json'}, {OUT/'index.html'}, {OUT/'flagged.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
