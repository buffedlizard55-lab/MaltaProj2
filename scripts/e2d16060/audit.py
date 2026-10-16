#!/usr/bin/env python3
"""Audit the canonical, source-linked CS2 pick surface without changing it.

This audit intentionally treats ``data/c64a5e19`` and ``picks-every-match`` as one
versioned publication batch.  Other boards (including ``data/f7279a54`` and
``ourline``) are recorded as separate snapshots and are never blended into the
canonical counts.

The script is offline by design.  It verifies retained evidence, arithmetic,
rendered rows, source-link presence, internal links, and mobile/accessibility
markers.  It does not claim that an HTTPS URL was reachable at audit time.
Values that are absent in the retained board remain blank/unresolved.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_BOARD = Path("data/c64a5e19/board.json")
ALTERNATE_BOARD = Path("data/f7279a54/board.json")
PICKS_PAGE = Path("picks-every-match/picks.html")
SURFACES = (
    Path("index.html"),
    Path("flagged.html"),
    Path("picks-every-match/index.html"),
    Path("picks-every-match/picks.html"),
    Path("picks-every-match/inventory.html"),
    Path("picks-every-match/unresolved.html"),
    Path("picks-every-match/flagged.html"),
    Path("picks-every-match/method.html"),
    Path("twc-2026/index.html"),
    Path("twc-2026/day-4.html"),
    Path("twc-2026/results.html"),
    Path("twc-2026/roster.html"),
    Path("twc-2026/flagged.html"),
    Path("twc-2026/method.html"),
    Path("hub/index.html"),
    Path("hub/unresolved.html"),
    Path("hub/flagged.html"),
)

# Official/public source roots already retained by the canonical collector.  This
# is a classification aid only: the audit never treats a URL as verified merely
# because its hostname looks familiar.
SOURCE_LABELS = {
    "hotspawn": "HotSpawn",
    "play.hotspawn.com": "HotSpawn",
    "www.hotspawn.com": "HotSpawn",
    "bovada": "Bovada",
    "melbet": "Melbet",
    "pinnacle": "Pinnacle",
    "kalshi": "Kalshi",
    "api.elections.kalshi.com": "Kalshi",
    "github.com/ValveSoftware": "Valve VRS",
    "www.hltv.org": "HLTV",
    "hltv.org": "HLTV",
    "github.com/buffedlizard55-lab/MaltaProj2": "Repository evidence",
}


def read_json(path: Path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def same_name(a: str | None, b: str | None) -> bool:
    def norm(value):
        return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())

    return bool(norm(a)) and norm(a) == norm(b)


def as_percent(value: float | None) -> str:
    return "—" if value is None else f"{float(value) * 100:.1f}%"


def source_label(url: str) -> str:
    lower = url.casefold()
    for key, label in SOURCE_LABELS.items():
        if key.casefold() in lower:
            return label
    return "External source"


class PicksPageParser(HTMLParser):
    """Extract the semantic fields needed to audit a generated picks table."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self.row: dict | None = None
        self.cell: str | None = None
        self.cell_class = ""
        self.current: dict | None = None
        self.current_label: str | None = None
        self.current_text: list[str] = []
        self.current_values: dict[str, list[str]] = {}
        self.links: list[dict] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr" and "data-match" in attrs:
            self.row = {
                "id": attrs.get("id", ""),
                "basis": attrs.get("data-basis", ""),
                "search": attrs.get("data-search", ""),
                "expires": attrs.get("data-expires"),
                "until": attrs.get("data-until"),
                "lock": attrs.get("data-lock"),
                "cells": {},
                "links": [],
                "source_links": [],
                "current_values": {},
            }
            self.links = []
        elif self.row is not None and tag == "td":
            self.cell = attrs.get("data-label", "")
            self.cell_class = attrs.get("class", "")
        elif self.row is not None and tag == "a":
            href = attrs.get("href", "")
            self.links.append({"href": href, "cell": self.cell or ""})
        elif self.row is not None and tag == "span" and "data-current" in attrs:
            self.current = self.row
            self.current_label = self.cell or ""
            self.current_text = []

    def handle_data(self, data):
        if self.row is None or self.cell is None:
            return
        self.row["cells"].setdefault(self.cell, "")
        self.row["cells"][self.cell] += data
        if self.current is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if self.row is None:
            return
        if tag == "span" and self.current is not None:
            text = "".join(self.current_text).strip()
            self.current_values.setdefault(self.current_label or "", []).append(text)
            self.current = None
            self.current_label = None
            self.current_text = []
        elif tag == "td":
            self.cell = None
            self.cell_class = ""
        elif tag == "tr":
            self.row["links"] = list(self.links)
            self.row["source_links"] = [
                link["href"] for link in self.links if link["cell"] == "Official sources"
            ]
            self.row["current_values"] = self.current_values
            self.rows.append(self.row)
            self.row = None
            self.links = []
            self.current_values = {}


def parse_picks(path: Path) -> list[dict]:
    parser = PicksPageParser()
    parser.feed((ROOT / path).read_text(encoding="utf-8"))
    return parser.rows


def find_percentages(values: list[str]) -> list[float]:
    result = []
    for value in values:
        match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)%\s*", value)
        if match:
            result.append(float(match.group(1)))
    return result


def text_pick(values: list[str]) -> str | None:
    text = " ".join(values).strip()
    match = re.search(r"Pick:\s*(.+?)(?:\s*$)", text, flags=re.I)
    if match:
        return match.group(1).strip()
    return None


def source_urls(row: dict) -> list[str]:
    urls: list[str] = []
    hotspawn = row.get("hotspawn_url")
    if hotspawn:
        urls.append(hotspawn)
    for quote in row.get("quotes") or []:
        url = quote.get("public_url")
        if url and url not in urls:
            urls.append(url)
    vrs_url = (row.get("vrs") or {}).get("page_url")
    if vrs_url and vrs_url not in urls:
        urls.append(vrs_url)
    return urls


def check_probability_arithmetic(board: dict) -> tuple[list[dict], list[dict]]:
    checks = []
    failures = []
    for row in board.get("open", []):
        line = row.get("line")
        if not line:
            continue
        pa, pb = line.get("prob_a"), line.get("prob_b")
        if not isinstance(pa, (int, float)) or not isinstance(pb, (int, float)):
            failures.append({"fixture_id": row.get("fixture_id"), "reason": "non-numeric line"})
            continue
        if not (math.isfinite(pa) and math.isfinite(pb)):
            failures.append({"fixture_id": row.get("fixture_id"), "reason": "non-finite line"})
            continue
        if abs((pa + pb) - 1.0) > 0.0002:
            failures.append({"fixture_id": row.get("fixture_id"), "reason": "probabilities do not sum to one"})
        pick_side = line.get("pick_side")
        expected_side = "a" if pa >= pb else "b"
        if pick_side != expected_side:
            failures.append({"fixture_id": row.get("fixture_id"), "reason": "pick is not the maximum side"})
        pick_team = line.get("pick_team")
        expected_team = row.get("team_a") if expected_side == "a" else row.get("team_b")
        if not same_name(pick_team, expected_team):
            failures.append({"fixture_id": row.get("fixture_id"), "reason": "pick team does not match side"})
        basis = line.get("basis")
        if basis == "market":
            market = row.get("market") or {}
            for key in ("prob_a", "prob_b"):
                if key in market and abs(float(market[key]) - float(line[key])) > 0.0002:
                    failures.append({"fixture_id": row.get("fixture_id"), "reason": f"line differs from market {key}"})
        elif basis == "model":
            model = row.get("model") or {}
            for key in ("prob_a", "prob_b"):
                if key in model and abs(float(model[key]) - float(line[key])) > 0.0002:
                    failures.append({"fixture_id": row.get("fixture_id"), "reason": f"line differs from model {key}"})
        checks.append(
            {
                "fixture_id": row.get("fixture_id"),
                "prob_a": pa,
                "prob_b": pb,
                "basis": basis,
                "pick_team": pick_team,
                "status": "pass" if not any(f["fixture_id"] == row.get("fixture_id") for f in failures) else "fail",
            }
        )
    return checks, failures


def check_links_and_mobile(path: Path) -> dict:
    """Check local targets and required responsive/accessibility markers in one page."""
    text = (ROOT / path).read_text(encoding="utf-8")
    parser = HTMLParser(convert_charrefs=True)
    # Local link scan uses a small attribute parser rather than executing page scripts.
    class AttrParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.urls = []
            self.ids = set()

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if attrs.get("id"):
                self.ids.add(attrs["id"])
            for key in ("href", "src"):
                if attrs.get(key):
                    self.urls.append(attrs[key])

    attrs = AttrParser()
    attrs.feed(text)
    missing = []
    broken_fragments = []
    for url in attrs.urls:
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc or not parsed.path:
            if parsed.fragment and not parsed.scheme and not parsed.netloc and parsed.fragment not in attrs.ids:
                broken_fragments.append(url)
            continue
        target = (ROOT / path.parent / unquote(parsed.path)).resolve()
        try:
            target.relative_to(ROOT.resolve())
        except ValueError:
            missing.append(url)
            continue
        if not target.exists():
            missing.append(url)
        if parsed.fragment and parsed.fragment not in attrs.ids:
            # Fragments can target another document; resolve the target document.
            frag_target = target
            if frag_target.exists():
                target_ids = set(re.findall(r"\bid=['\"]([^'\"]+)", frag_target.read_text(encoding="utf-8")))
                if parsed.fragment not in target_ids:
                    broken_fragments.append(url)
    missing_markers = []
    if not re.search(r'<html\b[^>]*\blang=["\']en["\']', text, re.I):
        missing_markers.append("html lang=en")
    if not re.search(r'<meta\b[^>]*name=["\']viewport["\']', text, re.I):
        missing_markers.append("viewport meta")
    if not re.search(r'<a\b[^>]*href=["\']#[^"\']+["\'][^>]*>\s*Skip', text, re.I):
        missing_markers.append("skip link")
    if not re.search(r'<main\b', text, re.I):
        missing_markers.append("main landmark")
    if not re.search(r'<nav\b[^>]*aria-label=', text, re.I):
        missing_markers.append("labelled navigation")
    if "<table" in text.lower() and not re.search(r"<caption\b", text, re.I):
        missing_markers.append("table caption")
    # Responsive rules are often kept in a local stylesheet rather than inline.
    style_text = text
    for url in attrs.urls:
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc or not parsed.path or not parsed.path.casefold().endswith(".css"):
            continue
        css_path = (ROOT / path.parent / unquote(parsed.path)).resolve()
        try:
            css_path.relative_to(ROOT.resolve())
        except ValueError:
            continue
        if css_path.exists():
            style_text += "\n" + css_path.read_text(encoding="utf-8")
    if not re.search(r"@media\s*\(", style_text, re.I):
        missing_markers.append("responsive media query")
    # Malformed option attributes are a concrete browser-facing issue even when
    # browsers recover the DOM.  Keep this separate so integration can repair it.
    malformed_options = len(re.findall(r"</option\s+[^>]+>", text, re.I))
    return {
        "path": str(path),
        "missing_local_links": sorted(set(missing)),
        "broken_fragments": sorted(set(broken_fragments)),
        "missing_mobile_accessibility_markers": missing_markers,
        "malformed_option_end_tags": malformed_options,
        "has_viewport": "viewport" not in missing_markers,
    }


def fixture_audit(board: dict, page_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    by_id = {str(row.get("fixture_id")): row for row in board.get("open", [])}
    pages_by_id: dict[str, list[dict]] = {}
    for page_row in page_rows:
        fixture_id = str(page_row.get("id", "")).removeprefix("m-")
        pages_by_id.setdefault(fixture_id, []).append(page_row)

    fixtures = []
    failures = []
    for fixture_id, row in by_id.items():
        line = row.get("line")
        expected_basis = (line or {}).get("basis", "unverified")
        page_matches = pages_by_id.get(fixture_id, [])
        page_row = page_matches[0] if page_matches else None
        row_failures = []
        if len(page_matches) != 1:
            row_failures.append("page row count is " + str(len(page_matches)))
        if page_row:
            if page_row.get("basis") != expected_basis:
                row_failures.append(f"basis {page_row.get('basis')!r} != {expected_basis!r}")
            source_links = page_row.get("source_links") or []
            if not source_links:
                row_failures.append("no source link in Official sources cell")
            if any(not url.startswith("https://") for url in source_links):
                row_failures.append("non-HTTPS source link")
            expected_until = row.get("valid_until_utc")
            if expected_until and page_row.get("until") != expected_until:
                row_failures.append("page evidence deadline differs from board")
            values = find_percentages(page_row.get("current_values", {}).get("Win probability", []))
            if line:
                expected_values = [float(line["prob_a"]) * 100, float(line["prob_b"]) * 100]
                if len(values) != 2 or any(abs(a - b) > 0.11 for a, b in zip(values, expected_values)):
                    row_failures.append("rendered probabilities differ from retained line")
                picked = text_pick(page_row.get("current_values", {}).get("Pick & basis", []))
                if not picked or not same_name(picked, line.get("pick_team")):
                    row_failures.append("rendered pick differs from retained line")
            else:
                if values:
                    row_failures.append("unresolved row contains a numeric probability")
                pick_text = " ".join(page_row.get("current_values", {}).get("Pick & basis", []))
                if re.search(r"\bPick:", pick_text, re.I):
                    row_failures.append("unresolved row contains a pick")
        if row_failures:
            failures.append({"fixture_id": fixture_id, "reasons": row_failures})
        source_urls_for_row = source_urls(row)
        fixtures.append(
            {
                "fixture_id": fixture_id,
                "competition": row.get("competition"),
                "team_a": row.get("team_a"),
                "team_b": row.get("team_b"),
                "start_utc": row.get("start_utc"),
                "hotspawn_url": row.get("hotspawn_url"),
                "basis": expected_basis,
                "pick_team": (line or {}).get("pick_team"),
                "prob_a": (line or {}).get("prob_a"),
                "prob_b": (line or {}).get("prob_b"),
                "flags": row.get("flags") or [],
                "source_urls": source_urls_for_row,
                "page_source_urls": (page_row or {}).get("source_links", []),
                "status": "pass" if not row_failures else "fail",
                "audit_failures": row_failures,
            }
        )
    extra_page_ids = sorted(set(pages_by_id) - set(by_id))
    if extra_page_ids:
        failures.append({"fixture_id": "page-only", "reasons": [f"page contains IDs not in board: {extra_page_ids}"]})
    return fixtures, failures


def make_finding(fid: str, severity: str, title: str, observation: str, action: str, urls: list[str]) -> dict:
    return {
        "id": fid,
        "severity": severity,
        "title": title,
        "observation": observation,
        "action": action,
        "source_urls": [url for url in urls if url],
    }


def build_report(audit_time: str) -> dict:
    board = read_json(CANONICAL_BOARD)
    alternate = read_json(ALTERNATE_BOARD) if (ROOT / ALTERNATE_BOARD).exists() else None
    page_rows = parse_picks(PICKS_PAGE)
    arithmetic, arithmetic_failures = check_probability_arithmetic(board)
    fixtures, fixture_failures = fixture_audit(board, page_rows)
    surface_checks = [check_links_and_mobile(path) for path in SURFACES if (ROOT / path).exists()]
    # The malformed option is in a shared page.  Report it, but do not silently
    # edit that owner-owned file from this independent audit.
    malformed_pages = [s["path"] for s in surface_checks if s["malformed_option_end_tags"]]
    missing_links = [s for s in surface_checks if s["missing_local_links"] or s["broken_fragments"]]
    marker_failures = [s for s in surface_checks if s["missing_mobile_accessibility_markers"]]
    sources_failed = list(board.get("summary", {}).get("sources_failed") or [])
    findings: list[dict] = []
    if malformed_pages:
        findings.append(
            make_finding(
                "AUD-E2D-001",
                "needs review",
                "Malformed option end tag in the shared picks filter",
                "The canonical picks page contains a closing option tag with attributes; browser recovery may still render it, but the markup is not valid option syntax.",
                "Repair the shared template/page in the integration scope, then rerun the mobile/browser checks.",
                ["https://play.hotspawn.com/lobby", "https://github.com/buffedlizard55-lab/MaltaProj2"],
            )
        )
    if sources_failed:
        findings.append(
            make_finding(
                "AUD-E2D-002",
                "needs review",
                "HLTV probe is recorded as failed for this batch",
                "The canonical board records the source failure instead of using HLTV as an unverified probability input. Market evidence and Valve VRS evidence remain separately labeled.",
                "Reattempt the HLTV read in the next scheduled refresh; do not backfill a number from a blocked or stale page.",
                ["https://www.hltv.org/", "https://github.com/ValveSoftware/counter-strike_regional_standings"],
            )
        )
    unresolved = [row for row in board.get("open", []) if not row.get("line")]
    if unresolved:
        findings.append(
            make_finding(
                "AUD-E2D-003",
                "unresolved",
                "Unresolved rows remain blank by policy",
                f"{len(unresolved)} of {len(board.get('open', []))} canonical open fixtures have no eligible retained line. The page keeps both probabilities and the pick blank rather than inventing 50/50.",
                "Use the dedicated unresolved page and its source-attempt ledger. A later refresh may resolve a row only after identity, kickoff and source-price checks pass.",
                ["https://play.hotspawn.com/lobby", "https://github.com/ValveSoftware/counter-strike_regional_standings"],
            )
        )
    if alternate:
        alt_generated = alternate.get("generated_utc")
        can_generated = board.get("generated_utc")
        if alt_generated and can_generated and alt_generated > can_generated:
            findings.append(
                make_finding(
                    "AUD-E2D-004",
                    "needs review",
                    "A newer alternate snapshot must not be mixed into canonical counts",
                    f"The separate ourline snapshot is stamped {alt_generated}; the canonical picks batch is stamped {can_generated}. They have different policies and open-line counts, so this audit keeps them separate.",
                    "The integration owner should choose and publish one coherent batch per board; never copy a probability across snapshots without replaying its retained evidence.",
                    ["https://play.hotspawn.com/lobby", "https://github.com/buffedlizard55-lab/MaltaProj2"],
                )
            )
    if arithmetic_failures:
        findings.append(
            make_finding(
                "AUD-E2D-005",
                "fail",
                "Probability or pick arithmetic mismatch",
                f"{len(arithmetic_failures)} retained priced rows failed arithmetic checks.",
                "Do not publish the affected rows until the source replay and derivation are repaired.",
                ["https://github.com/ValveSoftware/counter-strike_regional_standings"],
            )
        )
    if fixture_failures:
        findings.append(
            make_finding(
                "AUD-E2D-006",
                "fail",
                "Rendered page does not match its retained board",
                f"{len(fixture_failures)} fixture/page comparisons failed.",
                "Regenerate the canonical page from the same retained board before publishing.",
                ["https://play.hotspawn.com/lobby", "https://github.com/buffedlizard55-lab/MaltaProj2"],
            )
        )
    if missing_links:
        findings.append(
            make_finding(
                "AUD-E2D-007",
                "fail",
                "Broken local link or fragment on a canonical surface",
                f"{len(missing_links)} canonical surface(s) contain unresolved local targets or fragments.",
                "Run the staged-site link gate and repair the owning page before publishing.",
                ["https://github.com/buffedlizard55-lab/MaltaProj2"],
            )
        )
    if marker_failures:
        findings.append(
            make_finding(
                "AUD-E2D-008",
                "needs review",
                "Mobile/accessibility marker missing",
                f"{len(marker_failures)} canonical surface(s) miss one or more required mobile/accessibility markers.",
                "Repair the owning template and re-run the phone-width browser checks.",
                ["https://github.com/buffedlizard55-lab/MaltaProj2"],
            )
        )

    summary = board.get("summary", {})
    return {
        "audit_session": "e2d16060",
        "audit_generated_utc": audit_time,
        "scope": {
            "canonical_board": str(CANONICAL_BOARD),
            "canonical_page": str(PICKS_PAGE),
            "surfaces": [str(p) for p in SURFACES if (ROOT / p).exists()],
            "policy": "audit retained canonical batch only; no external URL reachability is claimed",
        },
        "source_capture": {
            "generated_utc": board.get("generated_utc"),
            "collected_from_utc": board.get("collected_from_utc"),
            "freshness_limit_hours": board.get("freshness_limit_hours"),
            "week": board.get("week"),
            "source_status": {
                "ok": summary.get("sources_ok", []),
                "failed": sources_failed,
            },
        },
        "summary": {
            "listed_open": len(board.get("open", [])),
            "board_with_line": sum(bool(row.get("line")) for row in board.get("open", [])),
            "board_unresolved": len(unresolved),
            "page_rows": len(page_rows),
            "arithmetic_rows_checked": len(arithmetic),
            "arithmetic_failures": len(arithmetic_failures),
            "fixture_failures": len(fixture_failures),
            "surface_count": len(surface_checks),
            "surfaces_with_missing_links": len(missing_links),
            "surfaces_with_marker_failures": len(marker_failures),
            "findings": len(findings),
        },
        "probability_checks": {
            "rows": arithmetic,
            "failures": arithmetic_failures,
        },
        "fixture_checks": fixtures,
        "surface_checks": surface_checks,
        "findings": findings,
        "alternate_snapshot": {
            "path": str(ALTERNATE_BOARD),
            "generated_utc": alternate.get("generated_utc") if alternate else None,
            "open": len(alternate.get("open", [])) if alternate else None,
            "with_line": sum(bool(row.get("line")) for row in (alternate or {}).get("open", [])),
            "kept_separate": True,
        },
        "manual_review_sources": [
            {"label": "HotSpawn lobby", "url": "https://play.hotspawn.com/lobby"},
            {"label": "Official Valve regional standings", "url": "https://github.com/ValveSoftware/counter-strike_regional_standings"},
            {"label": "HLTV", "url": "https://www.hltv.org/"},
            {"label": "Repository source evidence", "url": "https://github.com/buffedlizard55-lab/MaltaProj2"},
        ],
    }


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def link_html(url: str, label: str | None = None) -> str:
    label = label or source_label(url)
    return f'<a href="{esc(url)}" rel="noopener">{esc(label)}</a>'


def links_html(urls: list[str]) -> str:
    if not urls:
        return '<span class="muted">No retained URL</span>'
    seen = []
    for url in urls:
        if url and url not in seen:
            seen.append(url)
    return " · ".join(link_html(url) for url in seen)


CSS = """
:root{color-scheme:dark;--bg:#0b121a;--panel:#141f2c;--line:#2c3b4c;--text:#eef4fb;--muted:#b5c2d0;--green:#69e4bd;--amber:#ffcf83;--red:#ff9c9c;--blue:#94caff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}a{color:var(--blue);text-underline-offset:3px}a:focus-visible{outline:3px solid var(--amber);outline-offset:3px}.skip{position:absolute;left:-9999px}.skip:focus{left:12px;top:12px;background:var(--amber);color:#221b0e;padding:10px;z-index:10}header{background:#101923;border-bottom:1px solid var(--line)}.wrap{max-width:1180px;margin:auto;padding:16px}.brand{font-weight:760;letter-spacing:.02em}.small,.muted{color:var(--muted)}.small{font-size:.85rem}nav{display:flex;flex-wrap:wrap;gap:4px 14px;margin-top:8px}nav a{min-height:44px;padding:9px 0;text-decoration:none}nav a[aria-current]{color:var(--green);font-weight:750}h1{font-size:clamp(1.8rem,5vw,2.7rem);line-height:1.15;margin:10px 0 12px}h2{font-size:1.3rem;border-bottom:1px solid var(--line);padding-bottom:6px;margin:26px 0 10px}.eyebrow{color:var(--green);font-weight:750;letter-spacing:.1em;text-transform:uppercase;font-size:.78rem}.actions{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}.button{display:inline-block;min-height:48px;padding:12px 16px;border-radius:9px;border:1px solid var(--line);text-decoration:none;font-weight:700;background:var(--panel)}.primary{background:var(--green);border-color:var(--green);color:#09251f}.notice,.ok{padding:12px 15px;border-left:3px solid var(--amber);background:#292316;color:#ffe5b4;border-radius:0 8px 8px 0}.ok{border-color:var(--green);background:#12251f;color:#c9f5e8}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}.stat,.panel{border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:14px}.stat b{display:block;font-size:1.7rem}.stat span{font-size:.82rem;color:var(--muted)}.table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}table{width:100%;border-collapse:collapse;font-size:.9rem}caption{text-align:left;color:var(--muted);padding:7px 0}th{text-align:left;color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.04em}td,th{padding:12px 9px;border-bottom:1px solid var(--line);vertical-align:top}td{overflow-wrap:anywhere}.num{font-variant-numeric:tabular-nums;font-weight:750;white-space:nowrap}.pick{color:var(--green);font-weight:750}.badge{display:inline-block;padding:2px 7px;border-radius:6px;border:1px solid var(--line);font-size:.75rem;font-weight:700}.pass{color:#08261e;background:var(--green);border-color:var(--green)}.fail{color:#2b1212;background:var(--red);border-color:var(--red)}.needs-review,.unresolved{color:#2b2110;background:var(--amber);border-color:var(--amber)}.source a{display:inline-block;padding:4px 0;min-height:32px;margin-right:7px}details{border:1px solid var(--line);border-radius:9px;padding:10px 12px;background:var(--panel);margin:10px 0}summary{cursor:pointer;min-height:32px;font-weight:700}footer{border-top:1px solid var(--line);margin-top:30px;padding-top:16px}code{overflow-wrap:anywhere}@media(max-width:700px){.wrap{padding:12px}.stats{grid-template-columns:repeat(2,1fr);gap:8px}table,tbody,tr,td{display:block;width:100%}thead{display:none}tr{border:1px solid var(--line);border-radius:12px;background:var(--panel);margin-bottom:12px;padding:6px}td{border:0;padding:8px}td:before{content:attr(data-label);display:block;color:var(--muted);font-size:.68rem;letter-spacing:.04em;text-transform:uppercase;margin-bottom:3px}.source a{min-height:44px}}
"""


def shell(title: str, current: str, body: str) -> str:
    nav = [("index.html", "Audit summary"), ("flagged.html", "Flagged for review"), ("method.html", "Method & sources")]
    nav_html = "".join(
        f'<a href="{href}"' + (' aria-current="page"' if href == current else '') + f'>{esc(label)}</a>'
        for href, label in nav
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)}</title><style>{CSS}</style></head><body><a class="skip" href="#main">Skip to content</a><header><div class="wrap"><div class="brand">CS2 / HOTSPAWN <span class="small">Independent publication audit · e2d16060</span></div><nav aria-label="Audit navigation">{nav_html}</nav></div></header><main id="main" class="wrap">{body}<footer class="small"><p>Audit evidence is dated and offline-replayed. A source URL is a manual-review link, not a claim that this run fetched it. HotSpawn supplies fixture discovery only; its crowd ownership never enters the win-probability arithmetic.</p><p><a href="report.json">Machine-readable audit report</a> · <a href="../../picks-every-match/index.html">Canonical picks</a> · <a href="../../picks-every-match/unresolved.html">Canonical unresolved picks</a> · <a href="../../twc-2026/day-4.html">TWC Day 4 review</a> · <a href="../../flagged.html">Site Flagged for Review</a></p></footer></main></body></html>"""


def render(report: dict):
    out = ROOT / "audits/e2d16060"
    out.mkdir(parents=True, exist_ok=True)
    summary = report["summary"]
    source_capture = report["source_capture"]
    fixtures = report["fixture_checks"]
    findings = report["findings"]
    line_status = "pass" if not summary["arithmetic_failures"] else "fail"
    fixture_status = "pass" if not summary["fixture_failures"] else "fail"
    link_status = "pass" if not summary["surfaces_with_missing_links"] else "fail"
    marker_status = "pass" if not summary["surfaces_with_marker_failures"] else "needs-review"
    body = f"""
<div class="eyebrow">Executive summary</div><h1>Canonical CS2 board: independent line-by-line audit</h1>
<p class="muted">This page audits one coherent retained publication batch. It does not merge another board's newer snapshot or use HotSpawn ownership as a probability.</p>
<div class="actions"><a class="button primary" href="../../picks-every-match/picks.html">Open every current pick →</a><a class="button" href="../../picks-every-match/unresolved.html">Unresolved picks &amp; limitations</a><a class="button" href="../../twc-2026/day-4.html">TWC Day 1–3 → Day 4</a><a class="button" href="flagged.html">Audit flags</a></div>
<div class="stats"><div class="stat"><b>{summary['listed_open']}</b><span>canonical open fixtures</span></div><div class="stat"><b>{summary['board_with_line']}</b><span>with retained line/pick</span></div><div class="stat"><b>{summary['board_unresolved']}</b><span>blank + unresolved</span></div><div class="stat"><b>{summary['arithmetic_failures']}</b><span>arithmetic mismatches</span></div></div>
<div class="notice"><b>Capture:</b> {esc(source_capture.get('generated_utc'))} generated from {esc(source_capture.get('collected_from_utc'))}; freshness limit {esc(source_capture.get('freshness_limit_hours'))} hours. This is a dated estimate, not a live feed. Source failures recorded for this batch: {esc(', '.join(source_capture['source_status']['failed']) or 'none')}.</div>
<div class="{'ok' if line_status == 'pass' and fixture_status == 'pass' and link_status == 'pass' else 'notice'}"><b>Audit verdict:</b> arithmetic <span class="badge {line_status}">{line_status}</span> · rendered rows <span class="badge {fixture_status}">{fixture_status}</span> · local links <span class="badge {link_status}">{link_status}</span> · mobile markers <span class="badge {marker_status}">{marker_status}</span>. See <a href="flagged.html">all findings</a>; unresolved rows are intentionally not forced.</div>
<h2>Where to find the picks</h2><p>For a phone-first route, open <a href="../../picks-every-match/picks.html">All open CS2 picks</a>. Its filterable rows show both team probabilities, an obvious pick when supported, the evidence basis, match lock and source links. <a href="../../picks-every-match/unresolved.html">Unresolved picks</a> lists the rows that remain blank. The <a href="../../twc-2026/day-4.html">TWC review</a> is separate from the all-match board.</p>
<h2>Every canonical open fixture</h2><div class="table-wrap"><table><caption>Each row is joined by HotSpawn fixture ID to the retained board and rendered page. Each row includes source links for manual review.</caption><thead><tr><th>Fixture</th><th>Probabilities</th><th>Pick / basis</th><th>Row sources</th><th>Audit</th></tr></thead><tbody>"""
    for row in fixtures:
        status_cls = "pass" if row["status"] == "pass" else "fail"
        probs = f"{esc(row['team_a'])} <span class=\"num\">{as_percent(row['prob_a'])}</span><br>{esc(row['team_b'])} <span class=\"num\">{as_percent(row['prob_b'])}</span>"
        pick = f"<span class=\"pick\">{esc(row['pick_team'])}</span>" if row["pick_team"] else '<span class="muted">Blank — no supported pick</span>'
        pick += f"<br><span class=\"badge {'unresolved' if row['basis'] == 'unverified' else 'pass'}\">{esc(row['basis'])}</span>"
        audit_text = "OK" if row["status"] == "pass" else "; ".join(row["audit_failures"])
        body += f"<tr><td data-label=\"Fixture\"><b>{esc(row['competition'])}</b><br><span class=\"small\">{esc(row['team_a'])} vs {esc(row['team_b'])}<br>#{esc(row['fixture_id'])} · {esc(row['start_utc'])}</span></td><td data-label=\"Probabilities\">{probs}</td><td data-label=\"Pick / basis\">{pick}</td><td data-label=\"Row sources\" class=\"source\">{links_html(row['source_urls'])}</td><td data-label=\"Audit\"><span class=\"badge {status_cls}\">{esc(audit_text)}</span></td></tr>"
    body += "</tbody></table></div>"
    body += f"<h2>Batch checks</h2><ul><li><b>{summary['arithmetic_rows_checked']}</b> priced rows rechecked: probabilities normalize, pick side is the maximum, and market/model line values match their retained component.</li><li><b>{summary['page_rows']}</b> rendered rows were joined to <b>{summary['listed_open']}</b> open board rows; no numeric value is displayed for an unresolved board row.</li><li><b>{summary['surface_count']}</b> canonical/mobile surfaces were inspected for local links and required markers.</li></ul>"
    body += "<h2>Scope boundary</h2><p>The separate <code>data/f7279a54</code> / <code>ourline</code> snapshot is newer but follows a different board scope and has a different count. It is shown only as a flagged boundary, not silently substituted into this page's totals. Review the <a href=\"flagged.html#AUD-E2D-004\">snapshot finding</a>.</p>"
    (out / "index.html").write_text(shell("Canonical CS2 board audit · e2d16060", "index.html", body), encoding="utf-8")

    flag_body = f"""<div class="eyebrow">Flagged for review</div><h1>Audit findings and limitations</h1><p class="muted">These flags are published rather than hidden. A flag does not mean a probability was invented; it identifies a source, rendering, coverage, or integration limitation.</p><div class="actions"><a class="button primary" href="index.html">Back to audit summary</a><a class="button" href="../../picks-every-match/flagged.html">Canonical row flags</a><a class="button" href="../../flagged.html">Site-wide flags</a></div><div class="table-wrap"><table><caption>Every finding has a manual-review source link. External links were not fetched by this offline audit.</caption><thead><tr><th>ID / severity</th><th>Observation</th><th>Action</th><th>Sources</th></tr></thead><tbody>"""
    for finding in findings:
        sev = finding["severity"].replace(" ", "-")
        flag_body += f"<tr id=\"{esc(finding['id'])}\"><td data-label=\"ID / severity\"><b>{esc(finding['id'])}</b><br><span class=\"badge {esc(sev)}\">{esc(finding['severity'])}</span><br><b>{esc(finding['title'])}</b></td><td data-label=\"Observation\">{esc(finding['observation'])}</td><td data-label=\"Action\">{esc(finding['action'])}</td><td data-label=\"Sources\" class=\"source\">{links_html(finding['source_urls'])}</td></tr>"
    flag_body += "</tbody></table></div>"
    if not findings:
        flag_body += '<p class="ok">No findings were generated for this batch.</p>'
    flag_body += "<h2>Unresolved fixture rule</h2><p>An unresolved row is not a failure. If HLTV, a book, an exchange, or Valve VRS cannot provide defensible identity, kickoff, and price evidence, the canonical row remains blank and links to its evidence flag. This is the only honest way to meet the no-hallucination constraint.</p>"
    (out / "flagged.html").write_text(shell("Flagged for review · e2d16060", "flagged.html", flag_body), encoding="utf-8")

    method_body = f"""<div class="eyebrow">Method &amp; sources</div><h1>How this audit was verified</h1><p>This audit replays committed evidence; it does not make a network request and cannot certify that an external page is currently reachable. The audited batch is <code>data/c64a5e19/board.json</code>, generated {esc(source_capture.get('generated_utc'))} from {esc(source_capture.get('collected_from_utc'))}.</p><h2>Line-by-line checks</h2><ol><li>Load every open fixture from the canonical board and parse every rendered row in <code>picks-every-match/picks.html</code>.</li><li>Join by fixture ID. Compare basis, both displayed percentages, rendered pick, deadline, and source-link presence.</li><li>For priced rows, check finite probabilities sum to one within 0.02 percentage points and the pick matches the maximum side. Market rows are compared to retained market probabilities; model rows to retained model probabilities.</li><li>For unresolved rows, require no numeric probability and no rendered pick. The absence is reported as unresolved; it is not turned into 50/50.</li><li>Scan canonical user-facing surfaces for local link targets, fragment targets, viewport metadata, language, skip link, main landmark, labelled nav, table caption, and a responsive media query.</li></ol><h2>Source hierarchy</h2><p>HotSpawn is a fixture/lock source only. Bookmaker or exchange URLs retained on a row support the market-derived display; Valve's official VRS repository supports model-only identity/rating inputs. HLTV is a research source requested by the brief, but this batch records an HLTV probe failure, so the audit does not manufacture a value from it. Crowd ownership is not match probability.</p><p>Manual review: {links_html([item['url'] for item in report['manual_review_sources']])}</p><h2>Refresh and snapshot limits</h2><p>The canonical board says its freshness limit is {esc(source_capture.get('freshness_limit_hours'))} hours. Automated updates may be delayed by scheduler, provider, CDN, or access restrictions. This report compares one coherent batch only. The newer alternate snapshot is kept separate and flagged if it is newer; mixing snapshots would make a seemingly current table unverifiable.</p><h2>Related pages</h2><ul><li><a href="../../picks-every-match/method.html">Canonical probability method and retained payloads</a></li><li><a href="../../twc-2026/method.html">TWC Day 1–3 / Day 4 method</a></li><li><a href="../../twc-2026/roster.html">Aurora roster evidence and limits</a></li><li><a href="report.json">Full JSON audit report</a></li></ul>"""
    (out / "method.html").write_text(shell("Method and sources · e2d16060", "method.html", method_body), encoding="utf-8")
    (out / "style.css").write_text(CSS, encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-time", default=None, help="UTC ISO timestamp for reproducible output")
    args = parser.parse_args(argv)
    try:
        report = build_report(args.audit_time or utc_now())
        out = ROOT / "audits/e2d16060"
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        render(report)
        print(json.dumps(report["summary"], indent=2, sort_keys=True))
        # Arithmetic and rendered-join failures are hard errors for the audit;
        # unresolved/source/access limitations are published findings instead.
        return 1 if report["summary"]["arithmetic_failures"] or report["summary"]["fixture_failures"] or report["summary"]["surfaces_with_missing_links"] else 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"audit failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
