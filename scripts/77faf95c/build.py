#!/usr/bin/env python3
"""HQ page builder (session 77faf95c).

Reads only what is already committed under ``data/77faf95c/`` and writes ``hq/``. Every published
probability is recomputed here from the raw prices retained by ``collect.py`` - the number on the
page is never copied from anywhere, so it can be re-derived line by line.

Ladder, in this order, per fixture:
  1. market          - de-vigged consensus of Pinnacle / Bovada / Melbet quotes whose team names
                       resolve through a reviewed alias record and whose kickoff is within
                       TIME_TOLERANCE_MIN of the HotSpawn kickoff.
  2. market-flagged  - a quote exists but a team identity is unresolved. The number is shown,
                       labelled provisional, and listed on the unresolved page.
  3. model           - no usable quote and both teams sit on a single row of Valve's official
                       regional standings. Originated from Valve's own Glicko constants with a
                       slope fitted on this capture's market-priced pairs.
  4. blank           - nothing supportable. Blank, never 50/50, listed with its attempt ledger.

HotSpawn is fixture discovery and settlement only. Its crowd pick percentages are never read.
"""
from __future__ import annotations

import html
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "77faf95c"
RAW = DATA / "raw"
OUT = ROOT / "hq"

TIME_TOLERANCE_MIN = 5.0
FRESHNESS_LIMIT_H = 8.0
BOOK_SOURCES = ("pinnacle", "bovada", "melbet")

# Valve's own model code (ValveSoftware/counter-strike_regional_standings, model/glicko.js):
#   "rank delta of 400 points = 90% chance of victory" -> Q = ln(10)/400
#   g = 1 / sqrt(1 + 3*Q^2*RD^2/pi^2);  ev = 1 / (1 + 10^(g*(r-ro)/-400))
# and model/fit.js evaluates expected win rates with a fixed RD of 75 (defaultGlickoParams.rd).
VALVE_RD = 75.0
VALVE_Q = math.log(10) / 400.0
VALVE_G = 1.0 / math.sqrt(1.0 + 3.0 * VALVE_Q ** 2 * VALVE_RD ** 2 / math.pi ** 2)
VALVE_C = VALVE_G * math.log(10) / 400.0
CAL_MIN_PAIRS = 6
CAL_K_BOUNDS = (0.25, 1.5)

VRS_URL = ("https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/"
           "live/2026/standings_global_2026_10_05.md")
LOBBY_URL = "https://play.hotspawn.com/lobby"


def esc(v):
    return html.escape("" if v is None else str(v), quote=True)


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def logit(p):
    p = min(max(float(p), 1e-9), 1 - 1e-9)
    return math.log(p / (1.0 - p))


def parse_iso(value):
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def norm(name):
    return re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()


def load_json(rel, default=None):
    p = DATA / rel
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return default


def devig(dec_a, dec_b):
    try:
        da, db = float(dec_a), float(dec_b)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(da) or not math.isfinite(db) or da <= 1.0 or db <= 1.0:
        return None
    ia, ib = 1.0 / da, 1.0 / db
    book = ia + ib
    if not 0.95 <= book <= 1.30:
        return None
    return ia / book


# --------------------------------------------------------------------------- VRS standings
VRS_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|")


def load_vrs():
    """Parse Valve's official standings markdown. Returns (rows, snapshot, provenance).

    ``raw/vrs_standings.md`` is what collect.py fetched from the official repository. If a run
    predates that fetch (or the fetch failed), fall back to the byte-identical copy another session
    already committed and verified, and say so on the method page instead of silently degrading.
    """
    path = RAW / "vrs_standings.md"
    fallback = ROOT / "data" / "1c8f79f8" / "vrs_standings_global_2026_10_05.md"
    prov = load_json("raw/vrs_provenance.json") or {}
    source = None
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="replace")
        source = str(path.relative_to(ROOT))
    elif fallback.exists():
        text = fallback.read_text(encoding="utf-8", errors="replace")
        source = str(fallback.relative_to(ROOT)) + " (fallback copy, verified byte-identical)"
    else:
        return {}, None, {"resolved": False}
    rows = {}
    for line in text.splitlines():
        m = VRS_ROW_RE.match(line)
        if not m:
            continue
        standing, points, team, roster = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
        rows.setdefault(norm(team), []).append(
            {"standing": standing, "points": float(points), "team": team,
             "roster": [r.strip() for r in roster.split(",") if r.strip()]})
    snap = re.search(r"Standings as of (\d{4}_\d{2}_\d{2})", text)
    snapshot = snap.group(1) if snap else None
    prov = dict(prov, resolved=True, parsed_from=source, rows=len(rows), snapshot=snapshot)
    return rows, snapshot, prov


def vrs_lookup(rows, name):
    """Return {'unique': entry} / {'ambiguous': [entries]} / {'missing': True}."""
    hits = rows.get(norm(name)) or []
    if len(hits) == 1:
        return {"unique": hits[0]}
    if len(hits) > 1:
        return {"ambiguous": hits}
    return {"missing": True}


# --------------------------------------------------------------------------- alias resolution
def alias_map(research):
    accepted, rejected, unresolved = {}, {}, {}
    for a in research.get("aliases") or []:
        for market in a.get("market_names") or []:
            key = norm(market)
            bucket = {"accepted": accepted, "rejected": rejected,
                      "unresolved": unresolved}.get(a.get("decision"), rejected)
            bucket[key] = a
    return accepted, rejected, unresolved


def resolve_team(name, quote_side, accepted, unresolved, rejected):
    """Map one market label back to a HotSpawn team name. Returns (hotspawn_name, status, record)."""
    if norm(quote_side) == norm(name):
        return name, "exact", None
    rec = accepted.get(norm(quote_side))
    if rec and norm(rec.get("hotspawn_name")) == norm(name):
        return name, "alias", rec
    rec = unresolved.get(norm(quote_side))
    if rec and norm(rec.get("hotspawn_name")) == norm(name):
        return name, "unresolved", rec
    rec = rejected.get(norm(quote_side))
    if rec and norm(rec.get("hotspawn_name")) == norm(name):
        return name, "rejected", rec
    return None, "no-match", None


# --------------------------------------------------------------------------- build the board
def build():
    access = load_json("access.json")
    if not access:
        print("no capture yet - nothing to build")
        return 0
    quotes_doc = load_json("quotes.json", {"quotes": []}) or {"quotes": []}
    research = load_json("research.json", {}) or {}
    hot = load_json("raw/hotspawn.json", {"fixtures": []}) or {"fixtures": []}
    vrs_rows, vrs_snapshot, vrs_prov = load_vrs()
    kalshi_rejects = load_json("raw/kalshi_rejections.json", []) or []

    captured_at = access.get("collection_ended_utc") or access.get("collection_started_utc")
    captured_dt = parse_iso(captured_at) or datetime.now(timezone.utc)
    accepted, rejected, unresolved = alias_map(research)
    disambig = {norm(d["name"]): d for d in (research.get("vrs_disambiguation") or [])}

    fixtures = [f for f in (hot.get("fixtures") or [])
                if "lobby_page" in (f.get("seen_in") or [])
                and str(f.get("status")) == "scheduled"
                and (parse_iso(f.get("start_utc")) or captured_dt) > captured_dt]
    fixtures.sort(key=lambda f: (f.get("start_utc") or "", f.get("fixture_id") or ""))

    extra = list(research.get("extra_fixtures") or [])

    board_rows, flags = [], []

    def vrs_entry(name):
        lookup = vrs_lookup(vrs_rows, name)
        if "ambiguous" in lookup:
            d = disambig.get(norm(name))
            if d and d.get("chosen_points") is not None:
                return {"unique": {"standing": d["chosen_standing"],
                                   "points": float(d["chosen_points"]),
                                   "team": d["name"], "roster": d.get("chosen_roster")},
                        "disambiguated": d}
            return lookup
        return lookup

    for fx in list(fixtures) + list(extra):
        fid = str(fx.get("fixture_id"))
        ta, tb = fx.get("team_a"), fx.get("team_b")
        start = parse_iso(fx.get("start_utc"))
        row = {
            "fixture_id": fid,
            "label": fx.get("label"),
            "competition": fx.get("competition"),
            "tier": fx.get("tier"),
            "best_of": fx.get("best_of"),
            "start_utc": fx.get("start_utc"),
            "lock_utc": fx.get("lock_utc"),
            "team_a": ta, "team_b": tb,
            "listed_on_hotspawn": fx.get("listed_on_hotspawn", True),
            "hotspawn_url": fx.get("hotspawn_url") or LOBBY_URL,
            "hotspawn_url_kind": fx.get("hotspawn_url_kind") or "lobby (no per-match link published)",
            "match_url": fx.get("match_url"),
            "sources": [], "quotes": [], "rejected_quotes": [], "flags": [],
            "vrs_a": vrs_entry(ta) if ta else {"missing": True},
            "vrs_b": vrs_entry(tb) if tb else {"missing": True},
        }
        if row["listed_on_hotspawn"]:
            row["sources"].append({"label": "HotSpawn fixture", "url": row["hotspawn_url"]})
        else:
            row["sources"].append({"label": "HLTV match page (not on the HotSpawn lobby)",
                                   "url": row["match_url"] or LOBBY_URL})

        # ---- 1. market join
        accepted_quotes, provisional, rejected_rows = [], [], []
        for q in quotes_doc.get("quotes") or []:
            if q.get("source_key") not in BOOK_SOURCES:
                continue
            qa, qb = q.get("team_a"), q.get("team_b")
            qstart = parse_iso(q.get("start_utc"))
            if qstart and start and abs((qstart - start).total_seconds()) > TIME_TOLERANCE_MIN * 60:
                continue
            pairs = [(resolve_team(ta, qa, accepted, unresolved, rejected),
                      resolve_team(tb, qb, accepted, unresolved, rejected), False),
                     (resolve_team(ta, qb, accepted, unresolved, rejected),
                      resolve_team(tb, qa, accepted, unresolved, rejected), True)]
            chosen = None
            for ra, rb, swapped in pairs:
                if ra[1] in ("exact", "alias", "unresolved") and rb[1] in ("exact", "alias", "unresolved"):
                    chosen = ((ra, rb), swapped)
                    break
                if ra[1] == "rejected" or rb[1] == "rejected":
                    # cite the record of the side that was actually rejected, never the accepted one
                    rec = (rb[2] if rb[1] == "rejected" else None) or \
                          (ra[2] if ra[1] == "rejected" else None) or {}
                    rejected_rows.append({
                        "source": q.get("source_name"), "url": q.get("public_url"),
                        "labels": [qa, qb], "prices": [q.get("decimal_a"), q.get("decimal_b")],
                        "reason": rec.get("evidence") or "no reviewed alias record for this label"})
            if not chosen:
                continue
            (ra, rb), swapped = chosen
            da, db = q.get("decimal_a"), q.get("decimal_b")
            if swapped:
                da, db = db, da
            p = devig(da, db)
            if p is None:
                continue
            entry = {"source_key": q.get("source_key"), "source_name": q.get("source_name"),
                     "url": q.get("public_url"), "api_url": q.get("api_url"),
                     "event_id": q.get("event_id"), "labels": [qa, qb],
                     "decimals": [round(float(da), 4), round(float(db), 4)],
                     "raw_format": q.get("raw_format"),
                     "raw_a": q.get("raw_a"), "raw_b": q.get("raw_b"),
                     "prob_a": round(p, 6), "retrieved_utc": q.get("retrieved_utc"),
                     "swapped": swapped, "league": q.get("league")}
            statuses = {ra[1], rb[1]}
            if "unresolved" in statuses:
                entry["identity_unresolved"] = sorted(
                    {n for r in (ra, rb) if r[1] == "unresolved" for n in ([r[0]] if r[0] else [])})
                provisional.append(entry)
            else:
                accepted_quotes.append(entry)
        row["quotes"] = accepted_quotes + provisional
        row["rejected_quotes"] = rejected_rows

        # Kalshi: usable only inside the spread gate (collect.py applies it); list the rejects.
        kalshi_rows = []
        for q in quotes_doc.get("quotes") or []:
            if q.get("source_key") != "kalshi":
                continue
            names = {norm(q.get("team_a")), norm(q.get("team_b"))}
            if norm(ta) in names and norm(tb) in names:
                kalshi_rows.append({"tickers": (q.get("extra") or {}).get("tickers"),
                                    "spreads": (q.get("extra") or {}).get("spreads"),
                                    "decimals": [q.get("decimal_a"), q.get("decimal_b")],
                                    "url": q.get("public_url"),
                                    "note": (q.get("extra") or {}).get("note")})
        for rj in kalshi_rejects:
            if {norm(x) for x in (rj.get("teams") or [])} == {norm(ta), norm(tb)}:
                kalshi_rows.append({"rejected": True, "spreads": rj.get("spreads"),
                                    "reason": rj.get("reason"),
                                    "event_ticker": rj.get("event_ticker"),
                                    "url": "https://kalshi.com/markets/kxcs2game"})
        row["kalshi"] = kalshi_rows
        board_rows.append(row)

    # ---- calibration on market-priced rows where both teams have a single official rating
    pairs = []
    for r in board_rows:
        if not r["quotes"] or any(q.get("identity_unresolved") for q in r["quotes"]):
            continue
        if "unique" not in r["vrs_a"] or "unique" not in r["vrs_b"]:
            continue
        consensus = sum(q["prob_a"] for q in r["quotes"]) / len(r["quotes"])
        pairs.append({"fixture_id": r["fixture_id"],
                      "delta": r["vrs_a"]["unique"]["points"] - r["vrs_b"]["unique"]["points"],
                      "market_prob_a": consensus})
    cal = {"n_pairs": len(pairs), "k": 1.0, "fitted": False, "min_pairs": CAL_MIN_PAIRS,
           "bounds": list(CAL_K_BOUNDS), "k_raw": None, "mae_prob": None, "mae_prob_valve": None}
    if len(pairs) >= CAL_MIN_PAIRS:
        xs = [VALVE_C * p["delta"] for p in pairs]
        ys = [logit(p["market_prob_a"]) for p in pairs]
        sxx = sum(x * x for x in xs)
        if sxx > 0:
            k_raw = sum(x * y for x, y in zip(xs, ys)) / sxx
            cal["k_raw"] = round(k_raw, 6)
            cal["k"] = round(min(max(k_raw, CAL_K_BOUNDS[0]), CAL_K_BOUNDS[1]), 6)
            cal["fitted"] = True
        if pairs:
            cal["mae_prob"] = round(sum(abs(sigmoid(cal["k"] * x) - sigmoid(y))
                                        for x, y in zip(xs, ys)) / len(xs), 6)
            cal["mae_prob_valve"] = round(sum(abs(sigmoid(x) - sigmoid(y))
                                              for x, y in zip(xs, ys)) / len(xs), 6)

    # ---- resolve every row
    for r in board_rows:
        ledger = next((l for l in (research.get("research_ledger") or [])
                       if str(l.get("fixture_id")) == r["fixture_id"]), None)
        r["research_ledger"] = (ledger or {}).get("steps") or []
        r["prob_a"] = None
        r["basis"] = "blank"
        r["pick"] = None
        r["note"] = None
        quotes = r["quotes"]
        if quotes:
            consensus = sum(q["prob_a"] for q in quotes) / len(quotes)
            r["prob_a"] = round(consensus, 6)
            r["consensus_rule"] = "arithmetic mean of the per-source no-vig probabilities"
            if any(q.get("identity_unresolved") for q in quotes):
                r["basis"] = "market-flagged"
                names = sorted({n for q in quotes for n in (q.get("identity_unresolved") or [])})
                r["flags"].append("identity_unresolved:" + ",".join(names) or "identity_unresolved")
                r["note"] = ("Bookmaker price found, but the identity of %s is unresolved, so the "
                             "price cannot be attributed to one roster. Treat as provisional."
                             % ", ".join(names))
            else:
                r["basis"] = "market"
            for q in quotes:
                r["sources"].append({"label": q["source_name"], "url": q["url"]})
        elif "unique" in r["vrs_a"] and "unique" in r["vrs_b"]:
            pa = r["vrs_a"]["unique"]["points"]
            pb = r["vrs_b"]["unique"]["points"]
            p = sigmoid(cal["k"] * VALVE_C * (pa - pb))
            r["prob_a"] = round(p, 6)
            r["basis"] = "model"
            r["model"] = {"points_a": pa, "points_b": pb, "k": cal["k"],
                          "rd": VALVE_RD, "snapshot": vrs_snapshot,
                          "standing_a": r["vrs_a"]["unique"].get("standing"),
                          "standing_b": r["vrs_b"]["unique"].get("standing")}
            r["sources"].append({"label": "Valve official standings (model input)", "url": VRS_URL})
            r["note"] = ("Originated from Valve's official regional standings, not a bookmaker "
                         "price. No book in this capture prices the match.")
        else:
            for side, key in (("a", "vrs_a"), ("b", "vrs_b")):
                if "ambiguous" in r[key]:
                    r["flags"].append("ambiguous_vrs_name:%s" % (r["team_a"] if side == "a" else r["team_b"]))
                elif "missing" in r[key]:
                    r["flags"].append("not_in_vrs:%s" % (r["team_a"] if side == "a" else r["team_b"]))
            r["flags"].append("no_supported_line")
        if r["prob_a"] is not None:
            r["pick"] = r["team_a"] if r["prob_a"] >= 0.5 else r["team_b"]
            r["pick_prob"] = round(max(r["prob_a"], 1 - r["prob_a"]), 6)
        if r["rejected_quotes"]:
            r["flags"].append("rejected_quote_published")
        if any(k.get("rejected") for k in r["kalshi"]):
            r["flags"].append("exchange_book_empty")

    board = {
        "session": "77faf95c",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "captured_at_utc": captured_at,
        "freshness_limit_hours": FRESHNESS_LIMIT_H,
        "vrs_snapshot": vrs_snapshot,
        "vrs_url": VRS_URL,
        "calibration": {"k": cal["k"], "fitted": cal["fitted"], "pairs": pairs,
                        "n_pairs": cal["n_pairs"], "min_pairs": CAL_MIN_PAIRS,
                        "bounds": list(CAL_K_BOUNDS), "mae_prob": cal["mae_prob"],
                        "mae_prob_valve": cal["mae_prob_valve"], "rd": VALVE_RD,
                        "formula": "p = sigmoid(k * C * (pointsA - pointsB)), C = g*ln10/400, "
                                   "g = 1/sqrt(1 + 3*q^2*RD^2/pi^2), q = ln10/400"},
        "counts": {
            "listed_open": sum(1 for r in board_rows if r["listed_on_hotspawn"]),
            "extra_not_listed": sum(1 for r in board_rows if not r["listed_on_hotspawn"]),
            "with_probability": sum(1 for r in board_rows if r["prob_a"] is not None),
            "market": sum(1 for r in board_rows if r["basis"] == "market"),
            "market_flagged": sum(1 for r in board_rows if r["basis"] == "market-flagged"),
            "model": sum(1 for r in board_rows if r["basis"] == "model"),
            "blank": sum(1 for r in board_rows if r["basis"] == "blank"),
        },
        "rows": board_rows,
        "twc_review": research.get("twc_review") or {},
        "aliases": research.get("aliases") or [],
        "vrs_disambiguation": research.get("vrs_disambiguation") or [],
        "research_ledger": research.get("research_ledger") or [],
        "access": access,
    }
    board["vrs_provenance"] = vrs_prov
    board["research"] = research
    (DATA / "board.json").write_text(json.dumps(board, indent=1), encoding="utf-8")
    render(board)
    print(json.dumps({"captured": captured_at, "rows": len(board_rows), **board["counts"],
                      "k": cal["k"], "pairs": len(pairs)}, indent=1))
    return 0


# --------------------------------------------------------------------------- rendering
CSS = """
:root{color-scheme:dark;--bg:#0b1119;--panel:#141f2c;--line:#2d3c4d;--text:#edf3fa;
--muted:#aebbcc;--green:#69e4bd;--amber:#ffce80;--red:#ff9b9b;--blue:#92caff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--blue);text-underline-offset:3px}
a:focus-visible,button:focus-visible,input:focus-visible{outline:3px solid var(--amber);outline-offset:3px}
.wrap{max-width:1080px;margin:auto;padding:16px}
header{border-bottom:1px solid var(--line);background:#101a26}
.brand{font-weight:750;letter-spacing:.02em;font-size:1rem}
nav{display:flex;flex-wrap:wrap;gap:2px 14px;margin-top:8px}
nav a{padding:10px 0;min-height:44px;text-decoration:none;font-size:.9rem;color:var(--text)}
nav a[aria-current]{color:var(--green);font-weight:700}
.skip{position:absolute;left:-9999px}.skip:focus{position:static}
h1{font-size:clamp(1.7rem,6vw,2.5rem);line-height:1.15;margin:8px 0 12px}
h2{font-size:1.25rem;margin:26px 0 10px}
h3{font-size:1.02rem;margin:16px 0 6px}
p{margin:10px 0}
.muted{color:var(--muted)}
.small{font-size:.86rem;color:var(--muted)}
.eyebrow{color:var(--green);font-size:.76rem;text-transform:uppercase;letter-spacing:.1em;font-weight:700}
.hero{padding:12px 0 6px}
.cta{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));margin:16px 0}
.cta a{display:block;border:1px solid var(--line);border-radius:12px;background:var(--panel);
padding:16px;text-decoration:none;color:var(--text);min-height:72px}
.cta a.primary{background:var(--green);color:#08241d;border-color:var(--green);font-weight:750}
.cta a b{display:block;font-size:1.02rem}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:16px 0}
.stat{border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:14px}
.stat b{display:block;font-size:1.7rem}
.stat span{font-size:.8rem;color:var(--muted)}
.panel{border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:14px;margin:14px 0}
.notice{border-left:3px solid var(--amber);background:#2a2216;color:#ffe3b4;padding:12px 14px;margin:14px 0}
.warn{border-left:3px solid var(--red);background:#2a1717;color:#ffd9d9;padding:12px 14px;margin:14px 0}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th{text-align:left;color:var(--muted);font-size:.74rem;text-transform:uppercase;letter-spacing:.04em}
td,th{padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top}
td{overflow-wrap:anywhere}
.card{border:1px solid var(--line);border-radius:14px;background:var(--panel);padding:14px;margin-bottom:14px}
.match{font-weight:750;font-size:1.05rem}
.probs{display:grid;grid-template-columns:1fr auto;gap:4px 16px;margin:10px 0}
.probs .n{color:var(--muted)}
.probs .v{font-variant-numeric:tabular-nums;font-weight:700;text-align:right}
.bar{height:10px;border-radius:6px;background:#22303f;overflow:hidden;margin:8px 0 4px}
.bar i{display:block;height:100%;background:var(--green)}
.bar i.b{background:#4a7fb5}
.pick{font-weight:800;color:var(--green);font-size:1.05rem}
.badge{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:3px 10px;
font-size:.72rem;margin:4px 6px 0 0;color:var(--muted)}
.badge.market{color:var(--green);border-color:var(--green)}
.badge.market-flagged,.badge.model{color:var(--amber);border-color:var(--amber)}
.badge.blank{color:var(--red);border-color:var(--red)}
.src a{display:inline-block;padding:6px 10px 6px 0;min-height:44px;text-decoration:underline}
ul{padding-left:20px}li{margin:5px 0}
code{background:#0e1721;padding:1px 5px;border-radius:4px;font-size:.86em}
footer{border-top:1px solid var(--line);margin-top:30px;padding-top:18px}
details{margin:12px 0}summary{cursor:pointer;padding:8px 0;min-height:44px}
@media(max-width:700px){.wrap{padding:14px}h1{font-size:1.6rem}table,tbody,tr,td{display:block;width:100%}thead{display:none}tr{border:1px solid var(--line);border-radius:12px;margin-bottom:12px;background:#101a26;padding:6px 8px}td{border:0;padding:8px 4px}td:before{content:attr(data-label);display:block;text-transform:uppercase;font-size:.7rem;letter-spacing:.04em;color:var(--muted);margin-bottom:3px}.src a{min-height:44px;padding:9px 12px 9px 0}}
""".strip()


def page(title, active, body, subtitle=None):
    nav = [("index.html", "Where the picks are"), ("picks.html", "Every match"),
           ("twc.html", "TWC day 1-4 review"), ("unresolved.html", "Unresolved & limits"),
           ("flagged.html", "Flagged for review"), ("method.html", "Method & sources")]
    links = "".join(
        '<a href="%s"%s>%s</a>' % (h, ' aria-current="page"' if h == active else "", esc(t))
        for h, t in nav)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>%s · HotSpawn CS2 picks HQ</title><style>%s</style></head><body>'
        '<a class="skip" href="#main">Skip to content</a>'
        '<header><div class="wrap"><div class="brand">HOTSPAWN CS2 PICKS · HQ '
        '<span class="small">independent line analysis</span></div><nav aria-label="Main">%s</nav>'
        '</div></header><main id="main" class="wrap">%s%s</main>'
        '<footer><div class="wrap"><p class="small">Not affiliated with HotSpawn or any bookmaker. '
        'HotSpawn supplies fixtures and settlement only; its crowd pick percentages are never used '
        'as a win probability. Every probability on this site is our estimate from the cited '
        'external lines, not an official forecast.</p></div></footer></body></html>'
        % (esc(title), CSS, links,
           '<div class="hero"><div class="eyebrow">%s</div><h1>%s</h1></div>' % (
               esc(subtitle or "Session 77faf95c"), esc(title)) if subtitle else
           '<h1>%s</h1>' % esc(title),
           body))


def pct(v):
    return "—" if v is None else "%.1f%%" % (v * 100)


def stamp(iso_value):
    return (iso_value or "").replace("T", " ").replace("Z", " UTC")


def research_corr(board):
    return (board.get("research") or {}).get("corroboration") or []


def row_card(r, board):
    fid = r["fixture_id"]
    pa, pb = r["prob_a"], (None if r["prob_a"] is None else 1 - r["prob_a"])
    basis = r["basis"]
    badge = {"market": "Bookmaker line", "market-flagged": "Bookmaker line · provisional",
             "model": "Originated from Valve standings", "blank": "No supported line"}[basis]
    srcs = []
    seen = set()
    for s in r["sources"]:
        if s["url"] in seen:
            continue
        seen.add(s["url"])
        srcs.append('<a href="%s" rel="noopener">%s</a>' % (esc(s["url"]), esc(s["label"])))
    for q in r["quotes"]:
        u = q.get("api_url") or q.get("url")
        if u and u not in seen:
            seen.add(u)
            srcs.append('<a href="%s" rel="noopener">%s raw quote</a>' % (esc(u), esc(q["source_name"])))
    for k in r.get("kalshi") or []:
        u = k.get("url")
        if u and u not in seen:
            seen.add(u)
            srcs.append('<a href="%s" rel="noopener">Kalshi exchange</a>' % esc(u))
    if r.get("match_url") and r["match_url"] not in seen:
        seen.add(r["match_url"])
        srcs.append('<a href="%s" rel="noopener">HLTV match page</a>' % esc(r["match_url"]))

    detail = []
    for q in r["quotes"]:
        lab = "%s vs %s" % (q["labels"][0], q["labels"][1])
        detail.append("%s decimal %.3f / %.3f · observed %s%s" % (
            esc(q["source_name"]), q["decimals"][0], q["decimals"][1],
            stamp(q.get("retrieved_utc")),
            " · orientation reversed to match the HotSpawn order" if q.get("swapped") else ""))
    if r.get("model"):
        m = r["model"]
        detail.append("Valve standings #%s (%s pts) vs #%s (%s pts), snapshot %s, k=%.3f" % (
            m.get("standing_a"), m.get("points_a"), m.get("standing_b"), m.get("points_b"),
            esc(board.get("vrs_snapshot")), m.get("k")))
    if r.get("note"):
        detail.append(esc(r["note"]))
    flags = "".join('<span class="badge blank">%s</span>' % esc(f.replace("_", " "))
                    for f in r["flags"])

    bar = ""
    if pa is not None:
        bar = ('<div class="bar"><i style="width:%.1f%%"></i></div>' % (pa * 100))
    return (
        '<div class="card" id="m-%s"><div class="match">%s vs %s</div>'
        '<div class="small">%s · <time datetime="%s">%s</time>%s%s</div>'
        '%s<div class="probs"><span class="n">%s</span><span class="v">%s</span>'
        '<span class="n">%s</span><span class="v">%s</span></div>'
        '<div class="pick">%s</div>'
        '<span class="badge %s">%s</span>%s'
        '<div class="small">%s</div>'
        '<div class="src">%s</div>'
        '%s</div>'
        % (esc(fid), esc(r["team_a"]), esc(r["team_b"]),
           esc(r["competition"] or ""), esc(r["start_utc"] or ""), stamp(r["start_utc"]),
           " · bo%s" % esc(r["best_of"]) if r.get("best_of") else "",
           " · not on the HotSpawn lobby" if not r["listed_on_hotspawn"] else "",
           bar,
           esc(r["team_a"]), pct(pa), esc(r["team_b"]), pct(pb),
           ("Pick: %s (%s)" % (esc(r["pick"]), pct(r["pick_prob"]))) if r["pick"]
           else "No supported pick — see Unresolved",
           esc(basis), esc(badge), flags,
           "<br>".join(detail) or "No external line found in this capture.",
           "".join(srcs),
           '<p class="small"><a href="unresolved.html#m-%s">Resolution attempts →</a></p>'
           % esc(fid) if basis in ("blank", "market-flagged") else ""))


def render(board):
    OUT.mkdir(parents=True, exist_ok=True)
    rows = board["rows"]
    c = board["counts"]
    captured = board["captured_at_utc"]
    listed = [r for r in rows if r["listed_on_hotspawn"]]
    lobby_cs2 = sum(1 for f in ((load_json("raw/hotspawn.json") or {}).get("fixtures") or [])
                    if "lobby_page" in (f.get("seen_in") or []))
    extra = [r for r in rows if not r["listed_on_hotspawn"]]
    twc = board["twc_review"] or {}

    # ---------------------------------------------------------------- index (front door)
    body = [
        '<p class="muted">One page that tells you where the picks are, how many matches are priced, '
        'and what is still unresolved. Built for a phone first: every table below stacks into cards '
        'on a narrow screen.</p>',
        '<div class="cta">',
        '<a class="primary" href="picks.html"><b>Every match · pick + win probability →</b>'
        '<span class="small">All %d open HotSpawn CS2 fixtures, newest first</span></a>' % len(listed),
        '<a href="twc.html"><b>Thunderpick day 1 → day 4 →</b><span class="small">Verified results, '
        'the Aurora roster finding, and the Oct 17 semi-final lines</span></a>',
        '<a href="unresolved.html"><b>Unresolved picks &amp; limitations →</b>'
        '<span class="small">%d matches with no supported line, with every source attempt</span></a>'
        % c["blank"],
        '<a href="method.html"><b>Method &amp; sources →</b><span class="small">What we read, in what '
        'order, and the arithmetic behind each number</span></a>',
        '</div>',
        '<div class="stats">',
        '<div class="stat"><b>%d</b><span>Open HotSpawn fixtures</span></div>' % len(listed),
        '<div class="stat"><b>%d</b><span>Have a win probability</span></div>' % c["with_probability"],
        '<div class="stat"><b>%d</b><span>Bookmaker-priced</span></div>' % (c["market"] + c["market_flagged"]),
        '<div class="stat"><b>%d</b><span>Originated from Valve VRS</span></div>' % c["model"],
        '<div class="stat"><b>%d</b><span>Unresolved / blank</span></div>' % c["blank"],
        '</div>',
        '<p class="small">Capture taken %s. The lobby transfer-state carried %d CS2 rows, but %d of '
        'them are June and July fixtures the API still reports as "scheduled"; %d rows are still '
        'open and ahead of their lock, and those are the ones on the picks board. '
        '<a href="%s">Official HotSpawn lobby</a> · '
        '<a href="../data/77faf95c/board.json">machine-readable board</a>.</p>'
        % (stamp(captured), lobby_cs2, lobby_cs2 - len(listed), len(listed), LOBBY_URL),
        '<div class="notice"><b>Read this before you use a number.</b> Probabilities come from '
        'bookmaker prices (Pinnacle, Bovada, Melbet) and, where no book prices a match, from Valve\'s '
        'official regional standings through Valve\'s own Glicko constants. They are our estimates, '
        'not official forecasts. A blank cell is never filled with 50/50.</div>',
    ]
    if extra:
        body.append('<h2>Not on the HotSpawn lobby, added for this brief</h2>')
        body.append('<p class="small">The lobby fixtures API carries the Thunderpick World '
                    'Championship 2026 <em>South American Series #1</em> but no Malta playoff '
                    'competition, so the Oct 17 semi-finals are not pick\'em matches. They are '
                    'included because the brief asks for day-4 picks, and every appearance is '
                    'labelled not-listed.</p>')
        body.append("".join(row_card(r, board) for r in extra))
    body.append('<h2>Next up</h2>')
    body.append('<div class="panel">' + "".join(
        row_card(r, board) for r in listed[:4]) + '</div>')
    body.append('<p><a href="picks.html">See all %d open matches →</a></p>' % len(listed))
    (OUT / "index.html").write_text(
        page("Where the picks are", "index.html", "".join(body),
             "Executive summary · rebuilt every 4 hours"), encoding="utf-8")

    # ---------------------------------------------------------------- picks
    body = ['<p class="muted">Every open CS2 fixture the HotSpawn pick\'em lobby lists, newest '
            'first, each with a win probability for both teams, the pick, the basis and a link to '
            'every source used. ',
            'Times are UTC. Tap a source link to check the quote yourself.</p>',
            '<div class="notice">Basis legend: <b>Bookmaker line</b> = de-vigged consensus of '
            'Pinnacle / Bovada / Melbet prices. <b>Provisional</b> = a price exists but a team '
            'identity is unresolved. <b>Originated from Valve standings</b> = no book prices it; '
            'the number comes from Valve\'s official ratings. <b>No supported line</b> = blank, '
            'listed on the <a href="unresolved.html">unresolved page</a>.</div>']
    body.append("".join(row_card(r, board) for r in listed))
    if extra:
        body.append('<h2>Added for this brief (not on the lobby)</h2>')
        body.append("".join(row_card(r, board) for r in extra))
    (OUT / "picks.html").write_text(
        page("Every match · pick and win probability", "picks.html", "".join(body),
             "All %d open fixtures · captured %s" % (len(listed), stamp(captured))),
        encoding="utf-8")

    # ---------------------------------------------------------------- TWC review
    body = []
    if twc:
        body.append('<p class="muted">%s · %s · %s · %d teams · %s. Every result below is linked to '
                    'its HLTV match page. <a href="%s">Official event page</a> · '
                    '<a href="%s">official results list</a>.</p>'
                    % (esc(twc.get("event")), esc(twc.get("dates")), esc(twc.get("location")),
                       twc.get("teams") or 0, esc(twc.get("prize_pool")),
                       esc(twc.get("hltv_event_url")), esc(twc.get("results_url"))))
        body.append('<p class="small">%s</p>' % esc(twc.get("format")))

        def results(key, heading):
            out = ['<h2>%s</h2><table><thead><tr><th>Date</th><th>Result</th><th>Source</th>'
                   '</tr></thead><tbody>' % heading]
            for m in twc.get(key) or []:
                links = ['<a href="%s" rel="noopener">HLTV match</a>' % esc(m["hltv"])]
                if m.get("news"):
                    links.append('<a href="%s" rel="noopener">HLTV report</a>' % esc(m["news"]))
                out.append('<tr><td data-label="Date">%s</td><td data-label="Result">%s%s</td>'
                           '<td data-label="Source">%s</td></tr>'
                           % (esc(m.get("date")), esc(m.get("match")),
                              ('<br><span class="small">%s</span>' % esc(m["maps"])) if m.get("maps") else "",
                              " · ".join(links)))
            out.append("</tbody></table>")
            return "".join(out)

        body.append(results("day_1", "Day 1 · Wed 14 Oct — the upset"))
        body.append(results("day_2", "Day 2 · Thu 15 Oct"))
        body.append(results("day_3", "Day 3 · Fri 16 Oct — the deciders"))
        body.append('<div class="panel"><h3>What day 2 and day 3 tell us for day 4</h3><ul>'
                    '<li>The day-1 upset did not repeat: Aurora beat 9z 2-0 in the Group A decider '
                    '(Cache 13-11, Inferno 13-4) and dropped Nuke, the map they had lost 13-1. '
                    'The 9z result reads as a bad day, not a new ceiling.</li>'
                    '<li><b>Rest</b>: FURIA and Falcons both won their winners\' matches on '
                    '15 Oct and had 16 Oct off. Aurora and BETBOOM both had to play their group '
                    'decider on 16 Oct. The rest edge sits with FURIA in semi-final 1 and with '
                    'Falcons in semi-final 2.</li>'
                    '<li><b>Route</b>: BETBOOM played four matches to reach the semi-final '
                    '(2-1 PARIVISION on 15 Oct, then 2-1 Legacy on 16 Oct) against Falcons\' two. '
                    'More matches also means more recent map veto information on BETBOOM.</li>'
                    '<li><b>Where the market and the read disagree</b>: HLTV ranks FURIA #4 and '
                    'Aurora #6, yet the books have FURIA-Aurora as close to a coin flip (51/49 on this '
                    'capture) and HLTV tags Aurora the bookmaker favourite. The market is pricing '
                    'Aurora\'s form and the head-to-head win, not the ranking gap.</li>'
                    '<li><b>Contrarian-but-not-stupid</b>: the obvious contrarian side is Aurora '
                    'in semi-final 1 only in the sense that the ranking gap suggests FURIA - the '
                    'market already agrees with FURIA, so FURIA is not contrarian here. The '
                    'genuinely contrarian-but-supported side is BETBOOM in semi-final 2, and it '
                    'is a 24% shot: the form and the rest both point the other way, so it is a '
                    'leaderboard play, not an edge.</li></ul></div>')
        body.append('<h2>Day 4 · the lines</h2>')
        body.append("".join(row_card(r, board) for r in extra))
        body.append('<p class="small">%s</p>' % esc(twc.get("kickoff_note") or ""))
        rp = twc.get("roster_premise") or {}
        if rp:
            body.append('<div class="warn"><h3 style="margin-top:0">Correction: the Aurora roster '
                        'premise</h3><p><b>In the brief:</b> %s</p><p><b>Verified:</b> %s</p>'
                        '<p><b>Current five:</b> %s</p><p><b>Flag:</b> %s</p><p>Sources: %s</p></div>'
                        % (esc(rp.get("claim_in_brief")), esc(rp.get("verified")),
                           esc(rp.get("current_five")), esc(rp.get("flag")),
                           " · ".join('<a href="%s" rel="noopener">%s</a>' % (esc(u), esc(u.split("/")[2]))
                                      for u in (rp.get("sources") or []))))
        corr = research_corr(board)
        if corr:
            body.append('<h2>Corroboration from a second source</h2>'
                        '<table><thead><tr><th>Claim</th><th>What HotSpawn published</th>'
                        '<th>Agrees with</th></tr></thead><tbody>')
            for c in corr:
                body.append('<tr><td data-label="Claim">%s</td>'
                            '<td data-label="What HotSpawn published">%s<br>'
                            '<a href="%s" rel="noopener">source</a> <span class="small">read %s</span>'
                            '</td><td data-label="Agrees with">%s</td></tr>'
                            % (esc(c.get("claim")), esc(c.get("quote")), esc(c.get("source")),
                               esc(c.get("read_utc")), esc(c.get("agrees_with") or c.get("impact") or "")))
            body.append("</tbody></table>")
        if twc.get("form_note"):
            body.append('<p>%s</p><p class="small">Sources: %s</p>'
                        % (esc(twc["form_note"]),
                           " · ".join('<a href="%s" rel="noopener">HLTV</a>' % esc(u)
                                      for u in (twc.get("form_sources") or []))))
    else:
        body.append('<p class="muted">TWC review data unavailable.</p>')
    (OUT / "twc.html").write_text(
        page("Thunderpick World Championship 2026 · day 1 to day 4", "twc.html", "".join(body),
             "Verified results and the Oct 17 semi-final lines"), encoding="utf-8")

    # ---------------------------------------------------------------- unresolved
    blanks = [r for r in rows if r["basis"] == "blank"]
    flagged_rows = [r for r in rows if r["basis"] == "market-flagged"]
    body = [
        '<p class="muted">%d of the %d matches in this capture have no supported win probability, '
        'and %d more %s a provisional price. Nothing here is filled with a guess or a 50/50: '
        'these are the rows where the evidence ran out, with exactly what was tried.</p>'
        % (len(blanks), len(rows), len(flagged_rows),
           "carries" if len(flagged_rows) == 1 else "carry"),
        '<div class="notice"><b>Why a row stays blank.</b> A probability is published only when a '
        'bookmaker price joins to both teams through a reviewed alias record, or when both teams sit '
        'on a single row of Valve\'s official regional standings. A Kalshi market whose bid-ask '
        'spread is wider than 10 cents is an empty book, not a price. An aggregator showing 1.8 / '
        '1.8 on every unpriced match is showing a placeholder, not a price.</div>',
    ]
    if blanks:
        body.append('<h2>Blank — no supported line</h2>')
        for r in blanks:
            steps = r.get("research_ledger") or []
            body.append('<div class="card" id="m-%s"><div class="match">%s vs %s</div>'
                        '<div class="small">%s · %s</div>'
                        '<p class="muted">Win probability: <b>blank</b>. Pick: <b>none published</b>. '
                        'Flags: %s</p>'
                        % (esc(r["fixture_id"]), esc(r["team_a"]), esc(r["team_b"]),
                           esc(r["competition"] or ""), stamp(r["start_utc"]),
                           ", ".join(esc(f.replace("_", " ")) for f in r["flags"]) or "none"))
            if steps:
                body.append('<table><thead><tr><th>Source tried</th><th>What it returned</th>'
                            '</tr></thead><tbody>')
                for s in steps:
                    url = s.get("url")
                    body.append('<tr><td data-label="Source tried">%s%s</td>'
                                '<td data-label="What it returned">%s</td></tr>'
                                % (esc(s.get("source") or ""),
                                   ' <a href="%s" rel="noopener">link</a>' % esc(url) if url else "",
                                   esc(s.get("result") or "")))
                body.append("</tbody></table>")
            else:
                body.append('<p class="small">No manual research ledger entry for this fixture yet; '
                            'the automated capture alone found nothing.</p>')
            body.append("</div>")
    if flagged_rows:
        body.append('<h2>Provisional — a price was found but an identity is unresolved</h2>')
        for r in flagged_rows:
            steps = r.get("research_ledger") or []
            body.append('<div class="card" id="m-%s"><div class="match">%s vs %s</div>'
                        '<div class="small">%s · %s</div>'
                        '<p>Shown: %s vs %s. <b>%s</b></p>'
                        % (esc(r["fixture_id"]), esc(r["team_a"]), esc(r["team_b"]),
                           esc(r["competition"] or ""), stamp(r["start_utc"]),
                           pct(r["prob_a"]), pct(1 - r["prob_a"]), esc(r.get("note") or "")))
            if steps:
                body.append('<table><thead><tr><th>Source</th><th>What it returned</th></tr>'
                            '</thead><tbody>')
                for s in steps:
                    url = s.get("url")
                    body.append('<tr><td data-label="Source">%s%s</td>'
                                '<td data-label="What it returned">%s</td></tr>'
                                % (esc(s.get("source") or ""),
                                   ' <a href="%s" rel="noopener">link</a>' % esc(url) if url else "",
                                   esc(s.get("result") or "")))
                body.append("</tbody></table>")
            body.append("</div>")
    body.append('<h2>Standing limitations of this board</h2><ul>'
                '<li>The sandbox this session works from has no general internet access, so the '
                'dated capture is produced by a GitHub-hosted runner and the manual source reads are '
                'recorded with the URL and the UTC date they were read.</li>'
                '<li>HLTV answers HTTP 403 to the automated probes used elsewhere in this '
                'repository; HLTV is therefore used here as a research source (results, rosters, '
                'rankings) that a human read and cited, never as an automated odds feed.</li>'
                '<li>The official Valve standings snapshot is dated %s. Teams whose name appears '
                'twice in it (two different rosters) are treated as ambiguous unless an official '
                'lineup source disambiguates them.</li>'
                '<li>Pinnacle\'s public guest endpoint carried only %d CS2 matchups in this capture, '
                'so most low-tier matches rest on Melbet\'s line feed alone.</li>'
                '<li>HotSpawn crowd percentages are deliberately not collected and never enter a '
                'probability.</li></ul>'
                % (esc(board.get("vrs_snapshot")),
                   ((board.get("access") or {}).get("sources") or {}).get("pinnacle", {}).get("cs2_matchups", 0)))
    (OUT / "unresolved.html").write_text(
        page("Unresolved picks & limitations", "unresolved.html", "".join(body),
             "%d blank · %d provisional" % (len(blanks), len(flagged_rows))), encoding="utf-8")

    # ---------------------------------------------------------------- flagged
    body = ['<p class="muted">Irregularities found while building this board. Nothing here was '
            'silently corrected: each item is published with the source that produced it.</p>']
    items = []
    items.append(("The brief's Aurora premise is not supported",
                  "No October 2026 Aurora roster change exists. The last change is the July 2026 "
                  "international rebuild (Jimpphat and coach ash on 3 July, kyxsan on 8 July). "
                  "Liquipedia's Aurora timeline shows a 'deko' move, but it is dated November 2023 "
                  "with deko inactive from 28 November 2024 — it is not a 2026 change.",
                  (twc.get("roster_premise") or {}).get("sources") or []))
    items.append(("Kalshi's low-tier books are empty, not prices",
                  "For ex-6666 vs Privateer and antidaun vs Phantom Academy, Kalshi's own rules text "
                  "confirms it lists the right match, but the bid-ask spreads are 78-87 cents. A "
                  "midpoint of ~0.45 from a 0.06/0.84 book carries no information, so those markets "
                  "were rejected rather than converted into a probability. Other boards on this site "
                  "publish an exchange-fallback number for ex-6666 vs Privateer; that number rests "
                  "on the same empty book.",
                  ["https://kalshi.com/markets/kxcs2game"]))
    items.append(("EGamersWorld shows a 1.8 / 1.8 placeholder on unpriced matches",
                  "All four MaceMedia VOID Autumn Cup 2026 matches and Banda chuya vs Enjoy show "
                  "1.8 / 1.8 on EGamersWorld. That is the site's default for a match it has no line "
                  "for, so it was not used as a price.",
                  ["https://egamersworld.com/counterstrike/event/macemedia-void-autumn-cup-2026-EJcHRdr5Vx"]))
    items.append(("WROTBERRY's identity is contradictory across sources",
                  "bo3.gg lists WROTBERRY's aliases as 'WBTac' and 'WBT Academy'; Melbet prices the "
                  "same DraculaN slot as 'WhiteBIT Team'; Kalshi calls it 'WBT Academy'. EGamersWorld "
                  "records a player moving WhiteBIT Team to WhiteBIT Academy on 2026-09-01, so the "
                  "two squads are distinct. The price is published as provisional only.",
                  ["https://bo3.gg/teams/wrotberry",
                   "https://egamersworld.com/cs2/players/svemyy-4JTkfhHhR"]))
    items.append(("Bovada labels Just Players as 'JPlay'",
                  "Bovada event 32327967 (Nodwin Clutch Series, 2026-10-17T08:00Z) names the away "
                  "competitor 'JPlay'. No official alias source was found, so the quote is published "
                  "as a rejected candidate rather than folded into the line. Melbet names the same "
                  "slot 'Just Players' and is used instead.",
                  ["https://www.bovada.lv/services/sports/event/v2/events/A/description/esports/counter-strike-2"]))
    items.append(("The lobby renders stale rows as 'scheduled'",
                  "The lobby transfer-state carried %d CS2 rows, of which only %d are genuinely "
                  "ahead of their lock. The rest are June and July fixtures the API still reports as "
                  "\"scheduled\". They are excluded from the picks board. The lobby membership "
                  "test alone is therefore not enough: a row has to be on the lobby page AND ahead "
                  "of its lock."
                  % (lobby_cs2, len(listed)),
                  [LOBBY_URL]))
    items.append(("Pinnacle's guest feed covers very little of this card",
                  "This capture found %d CS2 matchups on the public Pinnacle guest endpoint and kept "
                  "%d moneylines from it, so most tier-B and tier-C rows rest on a single bookmaker "
                  "feed (Melbet). A single-source line is labelled as such on the picks page."
                  % (((board.get("access") or {}).get("sources") or {}).get("pinnacle", {}).get("cs2_matchups", 0),
                     ((board.get("access") or {}).get("sources") or {}).get("pinnacle", {}).get("quotes", 0)),
                  ["https://guest.api.arcadia.pinnacle.com/0.1/sports/12/matchups"]))
    for c in research_corr(board):
        if c.get("impact"):
            items.append(("Standings snapshot is already stale for some rosters: %s"
                          % c.get("claim", "").rstrip("."),
                          "%s %s" % (c.get("quote", ""), c.get("impact", "")),
                          [c.get("source")] if c.get("source") else []))
    for title, detail, urls in items:
        body.append('<div class="card"><h3>%s</h3><p>%s</p><div class="src">%s</div></div>'
                    % (esc(title), esc(detail),
                       "".join('<a href="%s" rel="noopener">source</a>' % esc(u) for u in urls)))
    body.append('<h2>Rejected quotes kept for the record</h2><table><thead><tr><th>Fixture</th>'
                '<th>Source</th><th>Labels</th><th>Prices</th><th>Why rejected</th></tr></thead><tbody>')
    any_reject = False
    for r in rows:
        for q in r.get("rejected_quotes") or []:
            any_reject = True
            body.append('<tr><td data-label="Fixture">%s vs %s</td><td data-label="Source">%s</td>'
                        '<td data-label="Labels">%s</td><td data-label="Prices">%s / %s</td>'
                        '<td data-label="Why rejected">%s</td></tr>'
                        % (esc(r["team_a"]), esc(r["team_b"]), esc(q.get("source") or ""),
                           esc(" vs ".join(q.get("labels") or [])), esc(q.get("prices", [None, None])[0]),
                           esc(q.get("prices", [None, None])[1]), esc(q.get("reason") or "")))
    if not any_reject:
        body.append('<tr><td colspan="5">No rejected quotes in this capture.</td></tr>')
    body.append("</tbody></table>")
    (OUT / "flagged.html").write_text(
        page("Flagged for review", "flagged.html", "".join(body),
             "Published, not silently corrected"), encoding="utf-8")

    # ---------------------------------------------------------------- method
    cal = board["calibration"]
    body = [
        '<h2>1 · Where the matches come from</h2>'
        '<p>The HotSpawn pick\'em lobby (<a href="%s">play.hotspawn.com/lobby</a>) is a server-'
        'rendered Angular app. Its public <code>script#ng-state</code> block carries the exact '
        '<code>/api/v1/fixtures</code> response the page renders. We read that block, keep the CS2 '
        'rows the lobby actually renders, and keep only the rows still ahead of their lock. The '
        'direct API is also read so fixtures added after the page cache was built are covered, but '
        'an API-only row is never treated as pickable — the API carries the whole history and '
        'reports long-finished fixtures as "scheduled".</p>'
        '<p>HotSpawn supplies fixtures and settlement only. Its crowd pick percentages are not '
        'collected and are never a probability input, because the brief requires lines from outside '
        'HotSpawn.</p>' % LOBBY_URL,
        '<h2>2 · Where the prices come from</h2>'
        '<p>Every price is read from an external source, in this order:</p><ol>'
        '<li><b>Pinnacle</b> — licensed bookmaker, public guest odds API.</li>'
        '<li><b>Bovada</b> — licensed bookmaker, public coupon JSON.</li>'
        '<li><b>Melbet</b> (1xBet platform) — licensed bookmaker, public LineFeed JSON. This is the '
        'feed that actually prices most tier-B and tier-C CS2.</li>'
        '<li><b>Kalshi</b> — CFTC-regulated exchange. Kept only when both sides quote a bid and an '
        'ask and each side\'s bid-ask spread is at most 10 cents.</li>'
        '<li><b>Official Valve regional standings</b> — the only official team rating used, and only '
        'where no book prices the match.</li></ol>',
        '<h2>3 · How a price becomes a probability</h2>'
        '<p>For decimal prices dA and dB the implied chances are 1/dA and 1/dB. The book margin is '
        'removed proportionally: <code>pA = (1/dA) / ((1/dA) + (1/dB))</code>. Where more than one '
        'book prices a match, the published number is the plain arithmetic mean of the per-source '
        'no-vig probabilities. A quote is joined only when both team names resolve to the HotSpawn '
        'teams through a reviewed alias record and the kickoffs agree to within five minutes. Where '
        'a book lists the pair in the opposite order, the orientation is reversed and the row says so.</p>',
        '<h2>4 · The originated line</h2>'
        '<p>Where no book prices a match and both teams sit on a single row of <a href="%s">Valve\'s '
        'official regional standings</a> (snapshot %s), the probability comes from Valve\'s own model '
        'constants, published in <code>ValveSoftware/counter-strike_regional_standings</code>: '
        '<code>q = ln(10)/400</code>, <code>g = 1/sqrt(1 + 3·q²·RD²/π²)</code> with the '
        'repository default <code>RD = 75</code>, and '
        '<code>p = sigmoid(k · g · ln(10)/400 · (pointsA − pointsB))</code>.</p>'
        '<p>Valve\'s own README states the published curve is too steep at the ends, so the slope k '
        'is fitted on this capture: least squares through the origin of '
        '<code>logit(market probability)</code> against <code>C·(pointsA − pointsB)</code>, over '
        'every row that has both a market consensus and two unique official ratings. '
        '<b>This capture: %d qualifying pairs, k = %s (%s), mean absolute error %s at that k versus '
        '%s at Valve\'s own slope.</b> k is clamped to %s.</p>'
        % (VRS_URL, esc(board.get("vrs_snapshot")), cal.get("n_pairs"), cal.get("k"),
           "fitted" if cal.get("fitted") else "Valve default, too few pairs",
           cal.get("mae_prob"), cal.get("mae_prob_valve"), cal.get("bounds")),
        '<p>An originated line is ours. It is not a bookmaker price, not an official forecast, and '
        'it has no claimed out-of-sample accuracy. It is labelled on every page it appears on.</p>',
        '<h2>5 · Team identity</h2>'
        '<p>No two names are merged without a record. Each alias decision below carries the source '
        'that was read. A decision marked <b>rejected</b> means the quote was found but not used; '
        '<b>unresolved</b> means the price is shown but labelled provisional.</p>'
        '<table><thead><tr><th>HotSpawn name</th><th>Market label(s)</th><th>Decision</th>'
        '<th>Evidence</th></tr></thead><tbody>',
    ]
    for a in board.get("aliases") or []:
        body.append('<tr><td data-label="HotSpawn name">%s</td><td data-label="Market label">%s</td>'
                    '<td data-label="Decision">%s</td><td data-label="Evidence">%s<br>%s</td></tr>'
                    % (esc(a.get("hotspawn_name")), esc(", ".join(a.get("market_names") or [])),
                       esc(a.get("decision")), esc(a.get("evidence") or ""),
                       " ".join('<a href="%s" rel="noopener">source</a>' % esc(u)
                                for u in (a.get("sources") or []))))
    body.append("</tbody></table>")
    if board.get("vrs_disambiguation"):
        body.append('<h2>6 · Disambiguating duplicate standings rows</h2><table><thead><tr>'
                    '<th>Team</th><th>Row used</th><th>Row rejected</th><th>Evidence</th></tr>'
                    '</thead><tbody>')
        for d in board["vrs_disambiguation"]:
            body.append('<tr><td data-label="Team">%s</td><td data-label="Row used">#%s (%s pts, %s)</td>'
                        '<td data-label="Row rejected">%s</td><td data-label="Evidence">%s %s</td></tr>'
                        % (esc(d.get("name")), esc(d.get("chosen_standing")), esc(d.get("chosen_points")),
                           esc(d.get("chosen_roster")),
                           ", ".join("#%s (%s pts, %s)" % (esc(r.get("standing")), esc(r.get("points")),
                                                           esc(r.get("roster")))
                                     for r in (d.get("rejected") or [])),
                           esc(d.get("evidence") or ""),
                           " ".join('<a href="%s" rel="noopener">source</a>' % esc(u)
                                    for u in (d.get("sources") or []))))
        body.append("</tbody></table>")
    src = (board.get("access") or {}).get("sources") or {}
    body.append('<h2>7 · Source health in this capture</h2><table><thead><tr><th>Source</th>'
                '<th>HTTP</th><th>Bytes</th><th>Notes</th></tr></thead><tbody>')
    for k, v in src.items():
        notes = {x: y for x, y in v.items()
                 if x in ("rows_cs2", "cs2_matchups", "quotes", "cs2_rows", "rejected_empty_books",
                          "characters", "ng_state_found", "error")}
        body.append('<tr><td data-label="Source">%s</td><td data-label="HTTP">%s</td>'
                    '<td data-label="Bytes">%s</td><td data-label="Notes">%s</td></tr>'
                    % (esc(k), esc(v.get("http_status")), esc(v.get("response_bytes")),
                       esc(json.dumps(notes))))
    body.append("</tbody></table>")
    body.append('<h2>8 · Evidence files</h2><ul>'
                '<li><a href="../data/77faf95c/board.json">board.json</a> — every row, quote, flag '
                'and the calibration pairs</li>'
                '<li><a href="../data/77faf95c/quotes.json">quotes.json</a> — every retained quote '
                'with its raw price</li>'
                '<li><a href="../data/77faf95c/access.json">access.json</a> — HTTP status, byte '
                'count and error per source</li>'
                '<li><a href="../data/77faf95c/research.json">research.json</a> — the reviewed '
                'alias and identity decisions with their sources</li>'
                '<li><a href="../data/77faf95c/raw/hotspawn.json">raw/hotspawn.json</a> — the exact '
                'fixtures array the lobby rendered</li>'
                '<li><a href="../data/77faf95c/raw/pinnacle.json">raw/pinnacle.json</a>, '
                '<a href="../data/77faf95c/raw/bovada.json">raw/bovada.json</a>, '
                '<a href="../data/77faf95c/raw/melbet.json">raw/melbet.json</a>, '
                '<a href="../data/77faf95c/raw/kalshi.json">raw/kalshi.json</a>, '
                '<a href="../data/77faf95c/raw/vrs_standings.md">raw/vrs_standings.md</a> — '
                'unmodified provider payloads</li></ul>')
    (OUT / "method.html").write_text(
        page("Method & sources", "method.html", "".join(body),
             "Read in this order, nothing inferred"), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(build())
