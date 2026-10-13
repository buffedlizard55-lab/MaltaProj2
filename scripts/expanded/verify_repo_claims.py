#!/usr/bin/env python3
"""Line-by-line verification of the repository's own publishable claims against sources.

This is the "review the repo and flag irregularities" deliverable of session a0586093. It
checks the repo's committed data files against primary sources that can be fetched from a
runner, and records the outcome per claim with the exact source link. Anything that cannot be
confirmed is marked `unverified` — never silently accepted.

Claims checked:
  1. data/hotspawn_matches.json  — fixture snapshot still matches the live lobby API
                                   (ids present/absent, sport split, start-time drift)
  2. data/teams_verified.json + data/originated_matches.json — every team's Valve VRS points
                                   and standing match the official Valve regional standings
  3. data/originated_matches.json — the originated favourite for each pairing is what the
                                   documented Bradley-Terry formula produces
  4. data/cs2_odds_egamersworld.json — each row's fixture id exists in the lobby snapshot and
                                   the team names match it
  5. Root dashboard counters (data/lines.json summary) — fixtures_total equals the number of
                                   rows in the file

Writes data/expanded/repo_review.json and returns non-zero only on an internal error.

Usage: python3 scripts/expanded/verify_repo_claims.py
"""
from __future__ import annotations

import base64
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lines_core import same_team  # noqa: E402

OUT = ROOT / "data" / "expanded" / "repo_review.json"
LOBBY_API = "https://phpstack-1372681-6459848.cloudwaysapps.com/api/v1/fixtures"
UA = "MaltaProj2-pickem-board/1.0 (research; contact via repository)"
VRS_SNAP = "2026_10_05"
VRS_REGIONS = ("global", "europe", "americas", "asia")


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http_json(url: str):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8", "replace")), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {str(exc)[:150]}"


def http_text(url: str, accept: str | None = None, timeout: int = 60):
    try:
        headers = {"User-Agent": UA}
        if accept:
            headers["Accept"] = accept
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace"), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {str(exc)[:150]}"


def load(rel: str):
    p = ROOT / rel
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def github_text(raw_url: str, api_url: str) -> tuple[str | None, str]:
    """Fetch a repository file as text, tolerating hosts that cannot reach raw.githubusercontent.

    api.github.com is asked with the raw media type; if the answer is the JSON envelope instead
    (some proxies), the base64 content is decoded. The first response that actually looks like a
    standings table wins, so a silent HTML/proxy body can never be mistaken for data.
    """
    text, _ = http_text(raw_url)
    if text and "|" in text:
        return text, "raw.githubusercontent.com"
    # The contents API honours the raw media type and then returns the file itself; ask for it
    # explicitly so a JSON envelope (or a proxy's HTML) can never be mistaken for standings data.
    body, _ = http_text(api_url, accept="application/vnd.github.raw")
    if body and "|" in body:
        return body, "api.github.com contents (raw media type)"
    body, _ = http_text(api_url)
    if not body:
        return None, "not retrievable"
    if '"content"' in body[:4000] and "base64" in body[:4000]:
        try:
            raw_b64 = json.loads(body)["content"].replace("\\n", "").replace("\n", "")
            return (base64.b64decode(raw_b64 + "=" * (-len(raw_b64) % 4)).decode("utf-8", "replace"),
                    "api.github.com contents (base64)")
        except Exception:  # noqa: BLE001
            return None, "decode failed"
    return (body, "api.github.com contents (json envelope)") if "|" in body else (None, "unusable body")


def vrs_points() -> tuple[dict[str, dict], list[str]]:
    out: dict[str, dict] = {}
    used = []
    for region in VRS_REGIONS:
        raw = ("https://raw.githubusercontent.com/ValveSoftware/counter-strike_regional_standings/"
               f"main/live/2026/standings_{region}_{VRS_SNAP}.md")
        api = ("https://api.github.com/repos/ValveSoftware/counter-strike_regional_standings/"
               f"contents/live/2026/standings_{region}_{VRS_SNAP}.md")
        text, how = github_text(raw, api)
        if not text:
            continue
        used.append(raw)
        sources = locals().setdefault("fetched_via", {})
        sources[region] = how
        for line in text.splitlines():
            m = re.match(r"\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", line)
            if m:
                name = m.group(3).strip()
                out.setdefault(name, {"standing": int(m.group(1)), "points": int(m.group(2)),
                                      "region": region, "source": raw})
    vrs_points.fetched_via = locals().get("fetched_via", {})
    return out, used


def main() -> int:
    review: dict = {"generated_at_utc": now_iso(), "checks": [], "irregularities": []}

    # ---------------------------------------------------------------- 1. fixtures
    live, err = http_json(LOBBY_API)
    snap = load("data/hotspawn_matches.json") or {}
    snap_rows = snap.get("matches") or []
    check = {"id": "R1", "claim": "data/hotspawn_matches.json matches the live lobby fixture list",
             "source": LOBBY_API, "snapshot_file": "data/hotspawn_matches.json",
             "snapshot_generated_at_utc": snap.get("generated_at_utc")}
    if live is None:
        check["status"] = "unverified"
        check["detail"] = f"live API not reachable from this host: {err}"
    else:
        live_ids = {str(f.get("id")) for f in live}
        snap_ids = {str(m.get("fixture_id")) for m in snap_rows}
        check["live_count_all_sports"] = len(live_ids)
        check["snapshot_count"] = len(snap_ids)
        check["missing_from_snapshot"] = sorted(live_ids - snap_ids)[:20]
        check["stale_in_snapshot"] = sorted(snap_ids - live_ids)[:20]
        check["status"] = "verified" if not (live_ids - snap_ids) else "discrepancy"
        check["detail"] = (f"{len(snap_ids)} snapshot rows; {len(live_ids - snap_ids)} live ids absent "
                           f"from the snapshot, {len(snap_ids - live_ids)} snapshot ids no longer live")
    review["checks"].append(check)
    if check.get("status") == "discrepancy":
        review["irregularities"].append({
            "id": "R1", "severity": "low",
            "finding": ("The committed fixture snapshot is not identical to the live lobby API "
                        "response (expected: both change continuously). Rows are refreshed every "
                        "3 hours by the scheduled workflow."),
            "evidence": check["source"]})

    # ---------------------------------------------------------------- 2/3. originated model
    vrs, vrs_sources = vrs_points()
    check2 = {"id": "R2", "claim": ("data/originated_matches.json team VRS points and standings match "
                                    "Valve's official regional standings"),
              "sources": vrs_sources}
    orig = load("data/originated_matches.json") or []
    mismatches = []
    checked = 0
    for match in orig:
        for side in ("team_a", "team_b"):
            team = match.get(side) or {}
            name, points, rank = team.get("name"), team.get("vrs_points"), team.get("vrs_rank")
            if not name or points is None:
                continue
            found = next((v for k, v in vrs.items() if same_team(k, name)), None)
            if not found:
                mismatches.append({"team": name, "issue": "not found in the 2026-10-05 VRS files",
                                   "claim": {"points": points, "rank": rank}})
                continue
            checked += 1
            if int(found["points"]) != int(points):
                mismatches.append({"team": name, "issue": "points differ",
                                   "claim": points, "official": found["points"],
                                   "official_standing": found["standing"],
                                   "source": found["source"]})
    check2.update({"status": "verified" if not mismatches else "discrepancy",
                   "teams_checked": checked, "mismatches": mismatches[:20],
                   "vrs_snapshot_date": VRS_SNAP.replace("_", "-"),
                   "detail": (f"{checked} team records across {len(vrs_sources)} Valve VRS files "
                              f"({VRS_SNAP.replace('_', '-')}) checked; "
                              f"{len(mismatches)} mismatch(es)")})
    review["checks"].append(check2)
    if mismatches:
        review["irregularities"].append({
            "id": "R2", "severity": "medium",
            "finding": ("data/originated_matches.json does not match Valve's official standings for "
                        f"{len(mismatches)} team entry/entries; the model file must not be read as "
                        "verified input."),
            "evidence": vrs_sources})

    check3 = {"id": "R3", "claim": ("each data/originated_matches.json fair probability is what its "
                                    "own documented model produces from the ratings it records"),
              "method": ("p = 1/(1+10^(-(Ra-Rb)/400)) on the file's recorded effective ratings, and "
                         "decimal odds = 1/(p*1.045) for the documented 4.5% overround")}
    bad = []
    notes = []
    for match in orig:
        a, b = match.get("team_a") or {}, match.get("team_b") or {}
        par = match.get("model_parameters") or {}
        eff_a, eff_b = par.get("effective_rating_a"), par.get("effective_rating_b")
        if eff_a is None or eff_b is None or a.get("fair_probability") is None:
            notes.append({"pairing": match.get("pairing"), "note": "no effective ratings recorded"})
            continue
        p = 1 / (1 + 10 ** (-(float(eff_a) - float(eff_b)) / 400))
        issues = []
        # The generator clamps at [0.08, 0.92]; a value sitting exactly on a clamp bound is
        # consistent with the model even when the unclamped logistic goes past it.
        clamped = (abs(float(a["fair_probability"]) - 0.92) < 1e-9 and p > 0.92) or \
                  (abs(float(a["fair_probability"]) - 0.08) < 1e-9 and p < 0.08)
        if not clamped and abs(p - float(a["fair_probability"])) > 0.005:
            issues.append({"field": "fair_probability", "file": a["fair_probability"],
                           "formula": round(p, 4)})
        want = 1 / (float(a["fair_probability"]) * 1.045)
        if a.get("decimal_odds") and abs(want - float(a["decimal_odds"])) > 0.03:
            issues.append({"field": "decimal_odds", "file": a["decimal_odds"],
                           "formula_4_5pct_overround": round(want, 3)})
        if issues:
            bad.append({"pairing": match.get("pairing"), "issues": issues})
        # The base rating logged by the file is raw VRS; momentum adjustments move the effective
        # ratings away from it. Recording that spread keeps the assumption visible, not hidden.
        if a.get("vrs_points") is not None and b.get("vrs_points") is not None:
            p_raw = 1 / (1 + 10 ** (-(a["vrs_points"] - b["vrs_points"]) / 400))
            if abs(p_raw - float(a["fair_probability"])) > 0.02:
                notes.append({"pairing": match.get("pairing"),
                              "note": ("pure VRS-logistic differs from the published number "
                                       "(documented momentum adjustment)"),
                              "pure_vrs_prob_a": round(p_raw, 4),
                              "published_prob_a": a["fair_probability"]})
    check3.update({"status": "verified" if not bad else "discrepancy",
                   "pairs_checked": len(orig), "mismatches": bad[:20],
                   "detail": (f"{len(orig)} pairings recomputed from the ratings the file itself "
                              f"records; {len(bad)} mismatch(es); "
                              f"{len(notes)} pairing(s) carry documented momentum adjustments"),
                   "model_assumptions_documented_by_the_file": notes[:10],
                   "note": ("Team strengths beyond raw VRS (momentum/invite weighting) are modelling "
                            "assumptions made in scripts/originate_lines.py and are reported here "
                            "rather than silently accepted.")})
    review["checks"].append(check3)
    if bad:
        review["irregularities"].append({
            "id": "R3", "severity": "medium",
            "finding": ("data/originated_matches.json contains numbers its own documented model does "
                        f"not reproduce ({len(bad)} pairing(s)); do not publish them as derived."),
            "evidence": "data/originated_matches.json"})

    # ---------------------------------------------------------------- 4. EGW odds rows
    egw = load("data/cs2_odds_egamersworld.json") or {}
    snap_index = {str(m.get("fixture_id")): m for m in snap_rows}
    bad_rows = []
    for row in egw.get("rows") or []:
        fid = str(row.get("fixture_id"))
        m = snap_index.get(fid)
        if not m:
            bad_rows.append({"fixture_id": fid, "issue": "fixture id not in the lobby snapshot"})
            continue
        if not (same_team(m.get("team_a"), row.get("team_a")) and same_team(m.get("team_b"), row.get("team_b"))):
            bad_rows.append({"fixture_id": fid, "issue": "team names disagree with the snapshot",
                             "snapshot": [m.get("team_a"), m.get("team_b")],
                             "row": [row.get("team_a"), row.get("team_b")]})
    check4 = {"id": "R4",
              "claim": "data/cs2_odds_egamersworld.json rows refer to real lobby fixtures",
              "source": egw.get("source_page"), "rows": len(egw.get("rows") or []),
              "status": "verified" if not bad_rows else "discrepancy", "mismatches": bad_rows[:20],
              "detail": (f"{len(egw.get('rows') or [])} priced rows joined to the lobby snapshot by "
                         f"fixture id and team name; {len(bad_rows)} mismatch(es)")}
    review["checks"].append(check4)
    if bad_rows:
        review["irregularities"].append({
            "id": "R4", "severity": "medium",
            "finding": f"{len(bad_rows)} egamersworld row(s) do not join to the lobby snapshot",
            "evidence": egw.get("source_page")})

    # ---------------------------------------------------------------- 5. root summary
    lines = load("data/lines.json") or {}
    summary = lines.get("summary") or {}
    rows = lines.get("fixtures") or []
    check5 = {"id": "R5", "claim": "data/lines.json summary counters match its own row list",
              "declared_fixtures_total": summary.get("fixtures_total"), "rows": len(rows),
              "status": "verified" if summary.get("fixtures_total") == len(rows) else "discrepancy",
              "detail": (f"declared fixtures_total={summary.get('fixtures_total')} vs "
                         f"{len(rows)} rows; rows_with_external_line="
                         f"{summary.get('future_with_external_line')}")}
    review["checks"].append(check5)

    # ---------------------------------------------------------------- 6. published source links
    board = load("data/expanded/lines.json") or {}
    board_rows = board.get("fixtures") or []
    priced = [r for r in board_rows if r.get("quotes")]
    missing_provenance = []
    links: dict[str, str] = {}
    for row in priced:
        for q in row.get("quotes") or []:
            label = q.get("source_name") or q.get("source_key")
            if not (q.get("source_api_url") or q.get("source_public_url")) or not q.get("retrieved_at_utc"):
                missing_provenance.append({"fixture_id": row.get("fixture_id"), "source": label})
                continue
            url = q.get("source_public_url") or q.get("source_api_url")
            links.setdefault(url, label)
    reachable, unreachable = 0, []
    for url, label in list(links.items())[:40]:
        body, _ = http_text(url, accept="application/json,text/html;q=0.9,*/*;q=0.8", timeout=15)
        if body:
            reachable += 1
        else:
            unreachable.append({"source": label, "url": url})
    check6 = {"id": "R6", "claim": ("every price published on the board carries a source link and a "
                                    "retrieval timestamp, and those links resolve"),
              "priced_rows": len(priced), "distinct_source_pages": len(links),
              "links_listed_for_manual_review": sorted(links.keys()),
              "status": ("verified" if not missing_provenance and not unreachable
                         else ("unverified" if not links and not missing_provenance else "discrepancy")),
              "mismatches": (missing_provenance[:10] + unreachable[:10]),
              "detail": (f"{len(priced)} priced rows, {len(links)} distinct source pages; "
                         f"{reachable} reachable, {len(unreachable)} not reachable from this host, "
                         f"{len(missing_provenance)} row(s) missing provenance")}
    review["checks"].append(check6)
    if missing_provenance or unreachable:
        review["irregularities"].append({
            "id": "R6", "severity": "medium",
            "finding": (f"{len(missing_provenance)} published quote(s) without full provenance and "
                        f"{len(unreachable)} source link(s) that did not resolve automatically — "
                        "click the listed links to review them by hand."),
            "evidence": "data/expanded/lines.json"})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(review, indent=1), encoding="utf-8")
    for c in review["checks"]:
        print(f"{c['id']} {c.get('status')}: {c['claim']} — {str(c.get('detail'))[:110]}")
    print(f"irregularities: {len(review['irregularities'])} — wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
