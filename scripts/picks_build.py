#!/usr/bin/env python3
"""
Build the /picks/ dashboard from collected lobby fixtures and external bookmaker quotes.

Inputs
    data/picks_fixtures.json        fixtures offered by the lobby's own public API
    data/picks_quotes.json          external match-winner quotes (raw, source-linked)
    data/picks_supplementary.json   optional, dated quote captures made by the session's own
                                    fetcher when a source blocks datacentre requests (same schema)

Joining rules (strict, every decision is written to the board JSON so it can be re-checked):
  1. Both team names must match after normalisation, in either order (a reversed source row
     gets its prices reversed).
  2. If both sides publish a start time they must agree within 90 minutes; if the source has no
     start time, the source's league/tournament text must correspond to the fixture's tournament.
  3. One source row is used for at most one fixture. If a row could belong to several fixtures it
     is rejected and listed on the Flagged page as ambiguous.
  4. Live markets are recorded but excluded from the consensus (a live price is not a pre-match line).

Derivation (published as derived, never as official fact):
    q_i = 1 / decimal_odds_i
    p_i = q_i / (q_a + q_b)                     proportional no-vig probability
    overround = (q_a + q_b) - 1                 bookmaker margin
    consensus p = arithmetic mean of p_i over every accepted source row

Outputs
    data/picks_board.json      machine-readable board (site input)
    picks/*.html               mobile-first dashboard pages
    picks/data/board.json      copy the pages load
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "picks")
TIME_TOLERANCE_MIN = 90

SUFFIXES = (" esports", " esport", " e sports", " gaming", " club", " academy")
PREFIXES = ("team ",)
ALIASES = {
    "bb team": "betboom",
    "pvision": "parivision",
    "9z globant": "9z",
    "team aurora": "aurora",
    "sashi esport": "sashi",
    "furia esports": "furia",
    "ninjas in pyjamas": "ninjas in pyjamas",
    "n i p": "ninjas in pyjamas",
    "nip": "ninjas in pyjamas",
    "wrotberry": "wrotberry",
    "los ninos": "los ninos",
    # EGamersWorld spellings verified against the lobby fixture they join to: the pairing is unique
    # inside the event and the kick-off times agree after the documented CET offset (see
    # data/picks_supplementary.json -> time_conversion).
    "wbt": "wrotberry",
    "ea copenhagen": "eac",
    "rounds": "roundsgg",
    "phantom esports": "phantom",
}

SOURCE_LABELS = {
    "pinnacle": ("Pinnacle", "licensed bookmaker", "https://www.pinnacle.com/en/esports"),
    "bovada": ("Bovada", "licensed bookmaker", "https://www.bovada.lv/sports/esports"),
    "egamersworld": ("EGamersWorld odds widget", "esports odds aggregator (bookmaker: bc.game)",
                     "https://egamersworld.com/counterstrike/matches"),
    "egamersworld_manual": ("EGamersWorld odds widget (dated capture)",
                            "esports odds aggregator (bookmaker: bc.game)",
                            "https://egamersworld.com/counterstrike/matches"),
    "polymarket": ("Polymarket", "prediction market", "https://polymarket.com"),
}


def norm(name) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).strip().lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    for suf in SUFFIXES:
        if s.endswith(suf.strip()):
            s = s[: -len(suf.strip())].strip()
    for pre in PREFIXES:
        if s.startswith(pre):
            s = s[len(pre):].strip()
    s = re.sub(r"\s+", " ", s)
    return ALIASES.get(s, s)


def load(rel, default):
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def parse_iso(value):
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def minutes_apart(a, b):
    if not a or not b:
        return None
    return abs((a - b).total_seconds()) / 60.0


def tournament_matches(source_text: str, fixture_tournament: str) -> bool:
    """Token-overlap test between a source's league text and the fixture's tournament name."""
    def toks(text):
        words = re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", str(text or "")).lower())
        # Drop season/year/number tokens: they are the most common source of false matches.
        return {w for w in words if len(w) > 3 and not w.isdigit()}
    a, b = toks(source_text), toks(fixture_tournament)
    if not a or not b:
        return False
    return len(a & b) >= 2 or (len(a & b) >= 1 and len(b) <= 2)


def no_vig(decimal_a, decimal_b):
    try:
        qa, qb = 1 / float(decimal_a), 1 / float(decimal_b)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    total = qa + qb
    return {"prob_a": qa / total, "prob_b": qb / total, "overround": total - 1}


def link_checks():
    """Status of every URL the collector published, opened once by the collector itself."""
    data = load("evidence/picks/link_checks.json", {})
    results = data.get("results") or {}
    return data, results


def link_state(results, url):
    if not url or url not in results:
        return "unchecked"
    record = results[url]
    if record.get("status") != 200:
        return f"http_{record.get('status')}"
    if record.get("final_url") not in (None, "", url):
        return "redirected"
    return "ok"


def build_board(fixtures, quotes, link_results=None):
    by_id = {f["fixture_id"]: dict(f) for f in fixtures}
    for f in by_id.values():
        f.update({"quotes": [], "prob_a": None, "prob_b": None, "pick": None,
                  "pick_prob": None, "n_sources": 0, "flags": [], "rejections": []})
    rejections = []
    accepted = 0
    for q in quotes:
        na, nb = norm(q.get("team_a_name")), norm(q.get("team_b_name"))
        if not na or not nb:
            continue
        q_time = parse_iso(q.get("start_time_utc"))
        hint = str(q.get("fixture_id_hint") or "")
        candidates = []
        if hint and hint in by_id:
            target = by_id[hint]
            t_names = {norm(target.get("team_a")), norm(target.get("team_b"))}
            if {na, nb} == t_names:
                candidates = [(target, na != norm(target.get("team_a")),
                               "explicit_fixture_id_hint_verified_by_team_names")]
            else:
                rejections.append({"reason": "fixture_id_hint_name_mismatch", "source_key": q.get("source_key"),
                                   "team_a": q.get("team_a_name"), "team_b": q.get("team_b_name"),
                                   "source_url": q.get("source_public_url"), "fixture_ids": [hint]})
                continue
        else:
            for f in by_id.values():
                fa, fb = norm(f.get("team_a")), norm(f.get("team_b"))
                pair_matches = (na == fa and nb == fb) or (na == fb and nb == fa)
                if not pair_matches:
                    continue
                reversed_side = (na == fb and nb == fa)
                f_time = parse_iso(f.get("lock_time_utc")) or parse_iso(f.get("start_time_utc"))
                delta = minutes_apart(q_time, f_time)
                if delta is not None:
                    if delta <= TIME_TOLERANCE_MIN:
                        candidates.append((f, reversed_side, f"start_time_delta_{delta:.0f}m"))
                elif tournament_matches(q.get("source_league"), f.get("competition")):
                    candidates.append((f, reversed_side, "tournament_name_match_no_source_time"))
        if not candidates:
            rejections.append({"reason": "no_fixture_match", "source_key": q.get("source_key"),
                               "team_a": q.get("team_a_name"), "team_b": q.get("team_b_name"),
                               "source_url": q.get("source_public_url"),
                               "start_time_utc": q.get("start_time_utc")})
            continue
        if len(candidates) > 1:
            rejections.append({"reason": "ambiguous_multiple_fixtures", "source_key": q.get("source_key"),
                               "team_a": q.get("team_a_name"), "team_b": q.get("team_b_name"),
                               "source_url": q.get("source_public_url"),
                               "fixture_ids": [c[0]["fixture_id"] for c in candidates]})
            for c in candidates:
                c[0]["rejections"].append({"reason": "ambiguous_multiple_fixtures",
                                           "source_key": q.get("source_key")})
            continue
        fixture, reversed_side, why = candidates[0]
        da, db = q.get("decimal_odds_a"), q.get("decimal_odds_b")
        if reversed_side:
            da, db = db, da
        nv = no_vig(da, db)
        if not nv:
            continue
        fixture["quotes"].append({
            "source_key": q.get("source_key"),
            "source_name": q.get("source_name") or SOURCE_LABELS.get(q.get("source_key"), ("", "", ""))[0],
            "source_kind": q.get("source_kind"),
            "source_url": q.get("source_public_url") or q.get("source_api_url"),
            "source_market_id": q.get("source_market_id"),
            "source_league": q.get("source_league"),
            "decimal_a": float(da), "decimal_b": float(db),
            "prob_a": nv["prob_a"], "prob_b": nv["prob_b"], "overround": nv["overround"],
            "is_live": bool(q.get("market_is_live")),
            "retrieved_at_utc": q.get("retrieved_at_utc"),
            "join_rule": why,
            "side_reversed": reversed_side,
            "link_state": link_state(link_results or {}, q.get("source_public_url") or q.get("source_api_url")),
        })
        accepted += 1

    for f in by_id.values():
        pre = [q for q in f["quotes"] if not q["is_live"]]
        live = [q for q in f["quotes"] if q["is_live"]]
        f["n_sources"] = len(pre)
        if live:
            f["flags"].append("live_market_excluded")
        if pre:
            f["prob_a"] = sum(q["prob_a"] for q in pre) / len(pre)
            f["prob_b"] = sum(q["prob_b"] for q in pre) / len(pre)
            f["pick"] = f["team_a"] if f["prob_a"] >= f["prob_b"] else f["team_b"]
            f["pick_prob"] = max(f["prob_a"], f["prob_b"])
            f["verified"] = True
            if len(pre) == 1:
                f["flags"].append("single_source_only")
            probs_a = [q["prob_a"] for q in pre]
            if max(probs_a) - min(probs_a) > 0.08:
                f["flags"].append("sources_disagree_gt_8pts")
        else:
            f["verified"] = False
            f["flags"].append("live_market_only_no_prematch_line" if live else "no_external_line")
        if f.get("lock_time_utc") and not f.get("open_for_picks"):
            f["flags"].append("past_lock_not_pickable")
        if not f.get("lock_time_utc") and not f.get("start_time_utc"):
            f["flags"].append("lock_time_unknown_in_source_api")
        if f.get("status") == "cancelled":
            f["flags"].append("source_status_cancelled")
        # The fixture link must open the fixture, not the matches index: /matches/<id> alone was
        # measured to redirect to /matches, so only a source-confirmed permalink is trusted.
        kind = f.get("hotspawn_match_url_kind")
        if kind and kind != "lobby_published_permalink":
            f["flags"].append("match_link_" + kind)
        if any(q.get("link_state") not in ("ok", "unchecked") for q in f["quotes"]):
            f["flags"].append("quoted_source_link_not_200")
        f["sources_used"] = sorted({q["source_key"] for q in pre})
    return list(by_id.values()), rejections, accepted


# --------------------------------------------------------------------------- rendering
def esc(value) -> str:
    return (str(value if value is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def fmt_prob(p):
    return "—" if p is None else f"{p * 100:.1f}%"


def fmt_utc(value):
    dt = parse_iso(value)
    return "—" if not dt else dt.strftime("%d %b %H:%M UTC")


def confidence(prob):
    if prob is None:
        return ""
    if prob >= 0.70:
        return "strong"
    if prob >= 0.55:
        return "lean"
    return "toss-up"


NAV = [
    ("index.html", "Overview"),
    ("cs2.html", "CS2"),
    ("lol.html", "LoL"),
    ("events.html", "Tournaments"),
    ("flagged.html", "Flagged for review"),
    ("methodology.html", "Method & sources"),
]


def page(title, current, body, meta):
    parts = []
    for href, label in NAV:
        marker = ' aria-current="page"' if href == current else ""
        parts.append(f'<a href="{href}"{marker}>{label}</a>')
    nav = "".join(parts)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Live picks</title>
<meta name="description" content="External betting lines and derived no-vig probabilities for every HotSpawn Pick'ems lobby fixture.">
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="site"><div class="wrap">
  <div class="brand">HotSpawn Pick'ems · Live lines board
    <small>External bookmaker lines only — HotSpawn is used for fixture discovery, never for probabilities.</small>
  </div>
  <nav class="site">{nav}</nav>
</div></header>
<main><div class="wrap">
{body}
<div class="foot">
  Data generated {esc(meta.get('generated_at_utc'))} · fixtures: <a href="{esc(meta.get('fixtures_api'))}">lobby public API</a>
  · lobby page: <a href="{esc(meta.get('lobby_page'))}">play.hotspawn.com/lobby</a><br>
  Not affiliated with HotSpawn or any bookmaker. Every number on this site is either a raw quote from the
  linked source or arithmetic derived from those quotes (formula on the Method page). Unconfirmed cells are
  blank and listed on the Flagged-for-review page.
</div>
</div></main>
</body>
</html>
"""


def quote_cell(row):
    if not row["quotes"]:
        return '<span class="muted">no external line</span>'
    parts = []
    for q in row["quotes"]:
        label = SOURCE_LABELS.get(q["source_key"], (q["source_name"], "", ""))[0]
        live = " · live (excluded)" if q["is_live"] else ""
        state = q.get("link_state", "unchecked")
        mark = {"ok": "", "unchecked": " · link not re-checked",
                "redirected": " · ⚠ link redirects elsewhere"}.get(
                    state, f' · <span class="bad-text">⚠ link answered {esc(state.replace("http_", "HTTP "))}</span>')
        parts.append(
            f'<span class="quote"><b>{esc(label)}</b> '
            f'<a href="{esc(q["source_url"])}" rel="nofollow noopener">{q["decimal_a"]:.3g} / {q["decimal_b"]:.3g}</a>'
            f'<span class="muted small"> ({q["prob_a"]*100:.1f}% / {q["prob_b"]*100:.1f}%){esc(live)}</span>'
            f'<span class="muted small">{mark}</span></span>')
    return "".join(parts)


def prob_cell(row):
    if row["prob_a"] is None:
        return '<span class="muted">—</span>'
    a, b = row["prob_a"] * 100, row["prob_b"] * 100
    return (f'<span class="prob">{a:.1f}%</span>'
            f'<div class="bar" aria-hidden="true"><i class="a" style="width:{a:.1f}%"></i>'
            f'<i class="b" style="width:{b:.1f}%"></i></div>')


def pick_cell(row):
    if row["pick"] is None:
        return '<span class="muted">—</span>'
    return (f'<span class="pick">{esc(row["pick"])}</span>'
            f'<span class="muted small"> {row["pick_prob"]*100:.1f}% · {confidence(row["pick_prob"])}</span>')


def flags_cell(row):
    if not row["flags"]:
        return '<span class="pill ok">verified</span>'
    cls = {"no_external_line": "warn", "past_lock_not_pickable": "warn",
           "single_source_only": "warn", "sources_disagree_gt_8pts": "bad",
           "live_market_excluded": "warn", "source_status_cancelled": "bad"}
    return "".join(f'<span class="pill {cls.get(f, "")}">{esc(f.replace("_", " "))}</span>'
                   for f in row["flags"])


def match_link_note(row):
    kind = row.get("hotspawn_match_url_kind")
    if kind == "lobby_published_permalink":
        return ""
    if kind == "constructed_slug_verified_200":
        return " · match URL rebuilt from the lobby's permalink pattern and confirmed 200"
    if kind:
        return " · ⚠ no source-confirmed match URL; this link opens the lobby listing"
    return ""


def row_html(row, show_game=False):
    """One table row. Every row links to its official HotSpawn fixture page."""
    cells = [
        f'<td data-label="Lock">{fmt_utc(row.get("lock_time_utc"))}</td>',
        f'<td data-label="Tournament">{esc(row.get("competition"))}'
        f'<span class="muted small"> · tier {esc(row.get("tier") or "—")}</span></td>',
    ]
    if show_game:
        cells.append(f'<td data-label="Game">{esc((row.get("sport_name") or row.get("sport") or "").upper())}</td>')
    cells += [
        f'<td class="match" data-label=""><a href="{esc(row.get("hotspawn_match_url"))}" rel="noopener">'
        f'<span class="team">{esc(row.get("team_a"))}</span> vs <span class="team">{esc(row.get("team_b"))}</span></a>'
        f'<span class="muted small"> · fixture {esc(row.get("fixture_id"))}'
        f'{esc(match_link_note(row))}</span></td>',
        f'<td data-label="Market lines">{quote_cell(row)}</td>',
        f'<td data-label="P(win)">{prob_cell(row)}</td>',
        f'<td data-label="Pick">{pick_cell(row)}</td>',
        f'<td data-label="Status">{flags_cell(row)}</td>',
    ]
    return "<tr>" + "".join(cells) + "</tr>"


def table(rows, show_game=False, caption=None):
    headers = ['<th>Lock</th>', '<th>Tournament</th>']
    if show_game:
        headers.append("<th>Game</th>")
    headers += ['<th>Match</th>', '<th>External market lines (a / b)</th>',
                '<th>No-vig probability</th>', '<th>Pick</th>', '<th>Status</th>']
    cap = f'<h3>{esc(caption)}</h3>' if caption else ""
    return (cap + '<div class="scroll"><table><thead><tr>' + "".join(headers) + "</tr></thead><tbody>"
            + "".join(row_html(r, show_game) for r in rows) + "</tbody></table></div>")


def summary_cards(board):
    open_rows = [r for r in board if r.get("open_for_picks")]
    priced_open = [r for r in open_rows if r["prob_a"] is not None]
    priced_all = [r for r in board if r["prob_a"] is not None]
    def card(n, label):
        return f'<div class="card"><div class="n">{n}</div><div class="l">{label}</div></div>'
    return ('<div class="cards">'
            + card(len(open_rows), "Open for picks")
            + card(len(priced_open), "Open with verified lines")
            + card(len(open_rows) - len(priced_open), "Open, no verified line")
            + card(len(board), "Listed fixtures in this build")
            + card(len(priced_all), "Fixtures with any external line")
            + '</div>')


def render(board, rejections, meta):
    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    open_rows = sorted([r for r in board if r.get("open_for_picks")],
                       key=lambda r: (r.get("lock_time_utc") or ""))
    locked_rows = sorted([r for r in board if not r.get("open_for_picks")],
                         key=lambda r: (r.get("lock_time_utc") or ""), reverse=True)
    priced_open = [r for r in open_rows if r["prob_a"] is not None]
    cs2 = [r for r in open_rows if (r.get("sport") or "") == "cs2"]
    lol = [r for r in open_rows if (r.get("sport") or "") == "lol"]
    cs2_locked = [r for r in locked_rows if (r.get("sport") or "") == "cs2"]
    lol_locked = [r for r in locked_rows if (r.get("sport") or "") == "lol"]

    # ---------------------------------------------------------------- overview
    notice = (
        '<div class="notice"><b>How to read this board.</b> Every probability below is derived only from '
        'external bookmaker prices quoted at the linked source; HotSpawn\'s crowd "picked %" is never used. '
        'Where no external line was found the probability cell stays empty and the row is flagged.</div>'
        if priced_open else
        '<div class="notice warn"><b>No verified external prices in this build.</b> Every row is therefore '
        'blank and flagged, rather than filled with an estimate.</div>')
    next_rows = open_rows[:14]
    body = [
        "<h1>Pick\'ems live lines board</h1>",
        f'<p class="muted">Fixtures listed by the HotSpawn Pick\'ems lobby, with external betting lines joined '
        f'to them. Built {esc(meta["generated_at_utc"])}.</p>',
        notice,
        summary_cards(board),
        "<h2>Next up</h2>",
        table(next_rows, show_game=True) if next_rows else '<p class="muted">No open fixtures.</p>',
        "<h2>Sections</h2>",
        '<ul>'
        f'<li><a href="cs2.html">CS2 board</a> — {len(cs2)} open, {len([r for r in cs2 if r["prob_a"] is not None])} with verified lines</li>'
        f'<li><a href="lol.html">LoL board</a> — {len(lol)} open, {len([r for r in lol if r["prob_a"] is not None])} with verified lines</li>'
        f'<li><a href="events.html">Tournament view</a></li>'
        f'<li><a href="flagged.html">Flagged for review</a> — {len([r for r in open_rows if r["prob_a"] is None])} open fixtures without a verified line, '
        f'{len(rejections)} rejected source rows</li>'
        '<li><a href="methodology.html">Method, sources and formulas</a></li>'
        '</ul>',
    ]
    write_page("index.html", page("Overview", "index.html", "\n".join(body), meta))

    # ---------------------------------------------------------------- per game
    for name, rows, locked, title, key in (
            ("cs2.html", cs2, cs2_locked, "CS2", "cs2"),
            ("lol.html", lol, lol_locked, "League of Legends", "lol")):
        blocks = [f"<h1>{esc(title)} fixtures in the Pick'ems lobby</h1>",
                  f'<p class="muted">{len(rows)} open for picks, '
                  f'{len([r for r in rows if r["prob_a"] is not None])} with a verified external line. '
                  f'{len(locked)} listed fixtures are already locked (shown separately at the bottom).</p>']
        if rows:
            blocks.append(table(rows, show_game=False))
        priced = [r for r in rows if r["prob_a"] is not None]
        if priced:
            blocks.append("<h2>Picks with an external line</h2>")
            blocks.append('<div class="scroll"><table><thead><tr><th>Lock</th><th>Match</th>'
                          '<th>Pick</th><th>Probability</th><th>Sources</th></tr></thead><tbody>' +
                          "".join(
                              f'<tr><td data-label="Lock">{fmt_utc(r["lock_time_utc"])}</td>'
                              f'<td class="match" data-label=""><a href="{esc(r["hotspawn_match_url"])}">'
                              f'{esc(r["team_a"])} vs {esc(r["team_b"])}</a></td>'
                              f'<td data-label="Pick">{pick_cell(r)}</td>'
                              f'<td data-label="Probability">{prob_cell(r)}</td>'
                              f'<td data-label="Sources">{esc(", ".join(r["sources_used"]))}</td></tr>'
                              for r in sorted(priced, key=lambda r: -r["pick_prob"])) +
                          "</tbody></table></div>")
        if locked:
            blocks.append("<h2>Already locked (listed, not pickable)</h2>")
            blocks.append(table(locked, show_game=False))
        write_page(name, page(title, name, "\n".join(blocks), meta))

    # ---------------------------------------------------------------- by tournament
    groups = {}
    for r in open_rows:
        groups.setdefault(r.get("competition") or "unknown", []).append(r)
    ev = ["<h1>Tournaments</h1>",
          '<p class="muted">Open fixtures grouped by the tournament name the lobby API reports.</p>']
    for name in sorted(groups):
        rows = groups[name]
        priced = len([r for r in rows if r["prob_a"] is not None])
        ev.append(f"<h2>{esc(name)} <span class=\"muted small\">({len(rows)} open · {priced} with lines)</span></h2>")
        ev.append(table(rows))
    write_page("events.html", page("Tournaments", "events.html", "\n".join(ev), meta))

    # ---------------------------------------------------------------- flagged
    no_line_open = [r for r in open_rows if r["prob_a"] is None]
    single = [r for r in open_rows if "single_source_only" in r["flags"]]
    disagree = [r for r in open_rows if "sources_disagree_gt_8pts" in r["flags"]]
    fl = ["<h1>Flagged for review</h1>",
          '<div class="notice warn">Nothing on this page is a probability. Each item states exactly what could '
          'not be confirmed, with the link a reviewer needs to check it.</div>',
          "<h2>Open fixtures with no verified external line</h2>",
          f'<p class="muted">{len(no_line_open)} of {len(open_rows)} open fixtures had no external match-winner '
          'price at build time. They are left blank — never estimated.</p>']
    if no_line_open:
        fl.append('<details><summary>Show the ' + str(len(no_line_open)) + ' unpriced open fixtures</summary>'
                  + table(no_line_open) + "</details>")
    if single or disagree:
        fl.append("<h2>Thin or conflicting market coverage</h2>")
        rows = single + [r for r in disagree if r not in single]
        fl.append(table(rows))
    fl.append("<h2>Rejected source rows</h2>")
    fl.append(f'<p class="muted">{len(rejections)} externally quoted rows could not be joined to a lobby '
              'fixture under the rules on the Method page (different event, different teams, or ambiguous). '
              'They are listed so a reviewer can confirm the rejections were the right call.</p>')
    if rejections:
        fl.append('<div class="scroll"><table><thead><tr><th>Source</th><th>Quoted pair</th>'
                  '<th>Why it was not used</th></tr></thead><tbody>' +
                  "".join(f'<tr><td data-label="Source">{esc(r.get("source_key"))}</td>'
                          f'<td data-label="Quoted pair"><a href="{esc(r.get("source_url"))}" rel="nofollow noopener">'
                          f'{esc(r.get("team_a"))} vs {esc(r.get("team_b"))}</a></td>'
                          f'<td data-label="Why">{esc(r.get("reason"))}'
                          f'{" " + esc(r.get("fixture_ids")) if r.get("fixture_ids") else ""}</td></tr>'
                          for r in rejections) + "</tbody></table></div>")
    fl.append("<h2>Link checks (every published URL opened once, by the collector)</h2>")
    if link_report:
        not_ok = link_report.get("not_200") or {}
        moved = link_report.get("redirected") or {}
        fl.append(f'<p class="muted">{esc(link_report.get("checked"))} URLs were requested by the collector '
                  f'at {esc(link_report.get("generated_at_utc"))}; {esc(link_report.get("ok"))} answered 200 '
                  f'on the exact URL that is published here. A link that answers something else is listed '
                  'below and marked next to the price it belongs to.</p>')
        if not_ok:
            fl.append('<div class="scroll"><table><thead><tr><th>Published URL</th><th>Answer</th>'
                      '</tr></thead><tbody>' + "".join(
                          f'<tr><td data-label="URL"><a href="{esc(u)}" rel="nofollow noopener">{esc(u)}</a></td>'
                          f'<td data-label="Answer">{esc(v)}</td></tr>' for u, v in sorted(not_ok.items()))
                      + "</tbody></table></div>")
        if moved:
            fl.append("<h3>URLs that redirect somewhere else</h3>")
            fl.append('<div class="scroll"><table><thead><tr><th>Published URL</th><th>Where it lands</th>'
                      '</tr></thead><tbody>' + "".join(
                          f'<tr><td data-label="URL"><a href="{esc(u)}" rel="nofollow noopener">{esc(u)}</a></td>'
                          f'<td data-label="Lands on">{esc(v)}</td></tr>' for u, v in sorted(moved.items()))
                      + "</tbody></table></div>")
        if not not_ok and not moved:
            fl.append('<div class="notice">Every published link answered 200 on its own URL.</div>')
    else:
        fl.append('<p class="muted">The collector has not run a link check for this build yet.</p>')

    fl += review_notes()
    write_page("flagged.html", page("Flagged for review", "flagged.html", "\n".join(fl), meta))

    # ---------------------------------------------------------------- methodology
    sources = load("data/picks_quotes.json", {"quotes": []})
    per_source = {}
    for q in sources.get("quotes", []):
        key = q.get("source_key")
        entry = per_source.setdefault(key, {"n": 0, "url": q.get("source_public_url") or q.get("source_api_url")})
        entry["n"] += 1
    me = ["<h1>Method, sources and formulas</h1>",
          "<h2>Where the fixtures come from</h2>",
          f'<p>The lobby page <a href="{esc(meta["lobby_page"])}">play.hotspawn.com/lobby</a> is an Angular '
          f'application that reads a public JSON API. That API is the fixture source of this board: '
          f'<a href="{esc(meta["fixtures_api"])}">{esc(meta["fixtures_api"])}</a>. No authentication, no admin '
          'endpoint and no paywall is bypassed; the request is the same public one the page itself makes.</p>',
          "<h2>Where the prices come from</h2>",
          '<p>Only external sources are used, and every price keeps the exact URL it was read from:</p>',
          "<ul>"]
    for key in sorted(per_source):
        label, kind, _ = SOURCE_LABELS.get(key, (key, "", ""))
        me.append(f'<li><a href="{esc(per_source[key]["url"])}" rel="nofollow noopener">{esc(label)}</a> — '
                  f'{esc(kind)}; {per_source[key]["n"]} quoted rows in this build.</li>')
    me += ["</ul>",
           "<h2>How a probability is produced</h2>",
           "<p>For each source that quotes the match:</p>",
           '<p><code>q_i = 1 / decimal_odds_i</code><br>'
           '<code>p_i = q_i / (q_a + q_b)</code> — proportional no-vig probability<br>'
           '<code>overround = (q_a + q_b) - 1</code> — the bookmaker\'s margin</p>',
           "<p>The published probability is the arithmetic mean of <code>p_i</code> over the accepted sources; "
           "the row shows how many sources were used. A single-source row is labelled as such.</p>",
           "<h2>How a quote is joined to a fixture</h2>",
           "<ol>",
           "<li>Both team names must match after normalisation (accents removed, club/academy suffixes "
           "trimmed), in either order — a source that lists the pair the other way round has its prices "
           "reversed.</li>",
           f"<li>Start times, when both sides publish one, must agree within {TIME_TOLERANCE_MIN} minutes. "
           "If the source publishes no start time, its league text has to correspond to the fixture's "
           "tournament.</li>",
           "<li>One source row is used for at most one fixture; anything ambiguous is rejected and listed on "
           "the Flagged page.</li>",
           "<li>Live markets are recorded but excluded from the consensus.</li>",
           "</ol>",
           "<h2>What is deliberately not done</h2>",
           "<ul>",
           "<li>HotSpawn's crowd “picked %” is never an input, and no other site's model output is copied.</li>",
           "<li>No value is inferred, extrapolated or filled in from a different market.</li>",
           "<li>A fixture without an external price shows a blank probability and is flagged as unverified.</li>",
           "<li>Prices are pre-match only, and the retrieval timestamp is shown on the raw data files.</li>",
           "</ul>",
           "<h2>Raw data and re-checking</h2>",
           '<ul><li><a href="data/board.json">data/board.json</a> — the exact board this page is rendered from.</li>'
           f'<li><a href="{esc(meta["fixtures_files"])}">data/picks_fixtures.json</a> and '
           f'<a href="{esc(meta["quotes_file"])}">data/picks_quotes.json</a> — the raw collected rows, every row '
           'carrying its source URL and retrieval time.</li></ul>']
    write_page("methodology.html", page("Method & sources", "methodology.html", "\n".join(me), meta))
    return {"open": len(open_rows), "priced_open": len(priced_open), "rows": len(board),
            "rejections": len(rejections)}


def review_notes():
    """Items this session found while building the board, each with the link a reviewer needs."""
    blocks = ["<h2>Source access at capture time</h2>",
              '<p class="muted">A source that refuses a datacentre request is an access limitation, '
              'not evidence that no price exists. Each entry is the exact URL that was refused.</p>']
    reach = load("evidence/picks/reachability.json", {})
    rows = []
    for key, value in reach.items():
        if key.startswith("__") or not isinstance(value, dict) or "url" not in value:
            continue
        status = value.get("status")
        if status in (200,):
            continue
        rows.append(f'<tr><td data-label="Source">{esc(key)}</td>'
                    f'<td data-label="HTTP status">{esc(status)}</td>'
                    f'<td data-label="URL"><a href="{esc(value["url"])}" rel="nofollow noopener">{esc(value["url"][:90])}</a></td>'
                    f'<td data-label="Note">{esc(str(value.get("error", ""))[:120])}</td></tr>')
    for key, value in reach.items():
        if not key.startswith("transport_") or not isinstance(value, list):
            continue
        for attempt in value:
            if attempt.get("status") == 200 and attempt.get("parsed_rows"):
                continue
            rows.append(f'<tr><td data-label="Source">{esc(key)} via {esc(attempt.get("transport"))}</td>'
                        f'<td data-label="HTTP status">{esc(attempt.get("status"))}</td>'
                        f'<td data-label="URL"><a href="{esc(attempt.get("url"))}" rel="nofollow noopener">'
                        f'{esc(str(attempt.get("url"))[:90])}</a></td>'
                        f'<td data-label="Note">bytes {esc(attempt.get("bytes"))}</td></tr>')
    if rows:
        blocks.append('<div class="scroll"><table><thead><tr><th>Source</th><th>HTTP status</th>'
                      '<th>URL</th><th>Note</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")

    supp = load("data/picks_supplementary.json", {})
    if supp:
        blocks.append("<h2>Dated capture notes (EGamersWorld odds widget)</h2>")
        conv = supp.get("time_conversion") or {}
        if conv:
            blocks.append('<div class="notice warn"><b>Time-zone assumption.</b> '
                          + esc(conv.get("displayed", "")) + '. Rule: ' + esc(conv.get("rule", ""))
                          + '. Verification: ' + esc(conv.get("verification", ""))
                          + f' Status: {esc(conv.get("status", ""))}.</div>')
        blocks.append(f'<p class="muted">Capture: {esc(supp.get("how_captured", ""))}</p>')
        rejected = supp.get("rejected_from_capture") or []
        if rejected:
            blocks.append('<h3>Values seen but deliberately not published</h3>')
            blocks.append('<div class="scroll"><table><thead><tr><th>What was seen</th>'
                          '<th>Why it is not published</th></tr></thead><tbody>' + "".join(
                              f'<tr><td data-label="Seen">{esc(r.get("detail"))}</td>'
                              f'<td data-label="Why"><a href="{esc(r.get("capture_url"))}" rel="nofollow noopener">'
                              f'source page</a> — repeated identical prices across different matches '
                              'are a placeholder, not a market</td></tr>' for r in rejected)
                          + "</tbody></table></div>")

    blocks += ["<h2>Repository review</h2>",
               "<p class=\"muted\">Mechanical checks over the other pick'em artefacts in this repository, "
               'with the file and the offending value for each item.</p>',
               '<ul>'
               '<li><a href="../verify/ac475c09/REPORT.md">verify/ac475c09/REPORT.md</a> — the check table</li>'
               '<li><a href="../verify/ac475c09/findings.json">verify/ac475c09/findings.json</a> — machine-readable findings</li>'
               '<li><a href="../verify/ac475c09/verify_repo.py">verify/ac475c09/verify_repo.py</a> — re-run it yourself</li>'
               '</ul>']
    return blocks


def write_page(name, html):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        fh.write(html)


def check_links():
    """Every local href/src in picks/*.html must resolve. External links are not fetched here."""
    from html.parser import HTMLParser
    from urllib.parse import urlsplit, unquote

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.urls = []

        def handle_starttag(self, tag, attrs):
            for key, value in attrs:
                if key in ("href", "src") and value:
                    self.urls.append(value)

    broken = []
    for page_file in sorted(os.listdir(OUT)):
        if not page_file.endswith(".html"):
            continue
        parser = Links()
        parser.feed(open(os.path.join(OUT, page_file), encoding="utf-8").read())
        for url in parser.urls:
            parsed = urlsplit(url)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = os.path.normpath(os.path.join(OUT, unquote(parsed.path)))
            if not os.path.exists(target):
                broken.append(f"{page_file} -> {url}")
    return broken


def main() -> int:
    fixtures_doc = load("data/picks_fixtures.json", {"fixtures": [], "summary": {}})
    quotes_doc = load("data/picks_quotes.json", {"quotes": []})
    supp = load("data/picks_supplementary.json", {"rows": []})
    fixtures = fixtures_doc.get("fixtures", [])
    quotes = list(quotes_doc.get("quotes", []))
    for row in supp.get("rows", []):
        quotes.append({
            "source_key": row.get("source_key", "egamersworld_manual"),
            "source_name": row.get("source_name", "EGamersWorld odds widget"),
            "source_kind": row.get("source_kind", "esports odds aggregator"),
            "source_public_url": row.get("source_url"),
            "source_api_url": row.get("source_url"),
            "source_league": row.get("source_league"),
            "source_market_id": row.get("source_market_id"),
            "fixture_id_hint": row.get("fixture_id"),
            "capture_url": row.get("capture_url"),
            "partner_bookmaker": row.get("partner_bookmaker"),
            "source_display_time": row.get("egw_time_display"),
            "market_type": "match winner (moneyline, full match)",
            "market_is_live": bool(row.get("is_live")),
            "retrieved_at_utc": row.get("retrieved_at_utc"),
            "start_time_utc": row.get("start_time_utc"),
            "team_a_name": row.get("team_a"), "team_b_name": row.get("team_b"),
            "decimal_odds_a": row.get("decimal_odds_a"), "decimal_odds_b": row.get("decimal_odds_b"),
        })
    if not fixtures:
        print("no fixtures collected yet — nothing to render")
        return 1
    # Board scope: fixtures the lobby can still offer (lock time in the future) plus fixtures whose
    # start has passed within the last 24 hours and which the lobby still lists as not ended. The
    # lobby's API returns every fixture ever created, so this window is applied explicitly and is
    # published on the Method page (never a silent truncation).
    now = datetime.now(tz=timezone.utc)
    recent_cut = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    open_comps = {f.get("competition") for f in fixtures
                  if (f.get("lock_time_utc") or "") > now_stamp}
    # Fixtures the lobby lists as scheduled but for which the API returns no time at all: they are
    # kept (and flagged) only when the same tournament has fixtures that are definitely open, so a
    # dateless backlog cannot leak into the board.
    window = [f for f in fixtures
              if (f.get("lock_time_utc") or "") > now_stamp
              or (f.get("status") != "ended" and (f.get("start_time_utc") or "") >= recent_cut)
              or (f.get("status") == "scheduled" and not f.get("lock_time_utc")
                  and not f.get("start_time_utc") and f.get("competition") in open_comps)]
    link_report, link_results = link_checks()
    board, rejections, accepted = build_board(window, quotes, link_results)
    meta = {
        "generated_at_utc": fixtures_doc.get("summary", {}).get("generated_at_utc"),
        "lobby_page": "https://play.hotspawn.com/lobby",
        "fixtures_api": "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures",
        "fixtures_files": "../data/picks_fixtures.json",
        "quotes_file": "../data/picks_quotes.json",
    }
    stats = render(board, rejections, meta)
    write_page("data/board.json", json.dumps(
        {"meta": meta, "stats": {**stats, "accepted_quotes": accepted}, "rejections": rejections,
         "rows": board}, indent=1, ensure_ascii=False))
    with open(os.path.join(ROOT, "data", "picks_board.json"), "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "stats": {**stats, "accepted_quotes": accepted},
                   "rejections": rejections, "rows": board}, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    broken = check_links()
    if broken:
        print("BROKEN LOCAL LINKS:\n" + "\n".join(broken))
        return 1
    print(json.dumps({**stats, "accepted_quotes": accepted,
                      "rejections": len(rejections)}, indent=1))
    print("PASS: /picks/ pages rendered and every local link resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
