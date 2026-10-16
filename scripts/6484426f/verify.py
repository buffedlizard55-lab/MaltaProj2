#!/usr/bin/env python3
"""Re-derive every published number in data/6484426f/board.json from the retained evidence.

Independent of the code that published the board: prices come from the raw decimals stored on each
quote, model rows from the published ratings plus the published slope, picks from the re-derived
probabilities. Writes data/6484426f/verification.json (published at desk/verify.html).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shared  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "6484426f"
BOARD = OUT / "board.json"
VERIFY = OUT / "verification.json"
TOL = 5e-7


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check(cid, name, rows, failures, detail):
    return {"id": cid, "name": name, "status": "pass" if not failures else "fail",
            "detail": detail, "rows_checked": rows, "rows_failed": len(failures),
            "failures": [str(f) for f in failures[:12]]}


def main() -> int:
    board = json.loads(BOARD.read_text())
    core = shared.core()
    rows = board["rows"]
    checks = []
    quotes_rederived = 0

    # C1 - market/exchange rows re-derive from their own raw prices.
    failures = []
    for row in rows:
        if row["basis"] not in ("market", "exchange"):
            continue
        book_keys = {"pinnacle", "bovada", "melbet", "thunderpick_via_bo3gg"}
        usable = [q for q in row["quotes"]
                  if q["source_key"] in (book_keys if row["basis"] == "market" else {"kalshi"})]
        if not usable:
            failures.append(f"{row['fixture_id']} publishes a {row['basis']} line with no retained quote")
            continue
        if row["basis"] == "exchange":
            value = usable[0]["no_vig_prob_team_a"]
        else:
            wsum = sum(core.SOURCE_WEIGHTS.get(q["source_key"], 1.0) for q in usable)
            value = sum(core.SOURCE_WEIGHTS.get(q["source_key"], 1.0) * q["no_vig_prob_team_a"]
                        for q in usable) / wsum
        for q in usable:
            nv = core.no_vig(q["decimal_a"], q["decimal_b"])
            quotes_rederived += 1
            if not nv:
                failures.append(f"{row['fixture_id']} {q['source_key']}: odds pair is not a usable book")
                continue
            if abs(nv["prob_a"] - q.get("raw_no_vig_team1", -1)) > 2e-6:
                failures.append(f"{row['fixture_id']} {q['source_key']}: source-order no-vig "
                                f"{q.get('raw_no_vig_team1')} != re-derived {nv['prob_a']:.6f}")
            oriented = 1.0 - nv["prob_a"] if q["swapped"] else nv["prob_a"]
            if abs(oriented - q["no_vig_prob_team_a"]) > 2e-6:
                failures.append(f"{row['fixture_id']} {q['source_key']}: orientation flag "
                                f"{q['swapped']} does not map source order to the fixture order")
        if abs(value - row["prob_a"]) > TOL:
            failures.append(f"{row['fixture_id']}: published {row['prob_a']:.6f} != re-derived {value:.6f}")
    checks.append(check("C1", "Market, esportsbook and exchange probabilities re-derive from the "
                        "retained raw prices",
                        sum(1 for r in rows if r["basis"] in ("market", "exchange")), failures,
                        "no-vig = (1/dec_a)/(1/dec_a+1/dec_b); multi-book rows use the declared weights"))

    # C2 - model rows re-derive from the published ratings and slope.
    failures = []
    for row in rows:
        if row["basis"] != "model":
            continue
        vrs = row.get("vrs") or {}
        ta, tb = (vrs.get("team_a") or {}).get("resolved"), (vrs.get("team_b") or {}).get("resolved")
        if not ta or not tb:
            failures.append(f"{row['fixture_id']}: model line without two official ratings")
            continue
        expected = core.vrs_prob(ta["points"], tb["points"], board["calibration"]["k"])
        if abs(expected - row["prob_a"]) > TOL:
            failures.append(f"{row['fixture_id']}: published {row['prob_a']:.6f} != model {expected:.6f}")
    checks.append(check("C2", "Originated lines re-derive from the official ratings and the published slope",
                        sum(1 for r in rows if r["basis"] == "model"), failures,
                        "P(A)=sigmoid(k*C*delta) with Valve's C at RD 75 and this build's fitted k"))

    # C3 - probability conservation and pick = argmax (or the declared tiebreak).
    failures = []
    for row in rows:
        pa, pb = row.get("prob_a"), row.get("prob_b")
        if (pa is None) != (pb is None):
            failures.append(f"{row['fixture_id']}: one side priced and the other blank")
            continue
        if pa is None:
            continue
        if abs(pa + pb - 1.0) > TOL:
            failures.append(f"{row['fixture_id']}: probabilities sum to {pa + pb:.9f}")
        safe = row.get("safe_pick")
        if abs(pa - pb) < 1e-9:
            if row.get("tie_break") is None:
                failures.append(f"{row['fixture_id']}: exact tie without a declared tiebreak")
            continue
        best = row["team_a"] if pa > pb else row["team_b"]
        if safe != best:
            failures.append(f"{row['fixture_id']}: pick {safe} is not the higher-probability side")
    checks.append(check("C3", "Probabilities sum to one and the pick is the higher-probability side",
                        len(rows), failures, "exact ties must publish a declared tiebreak instead"))

    # C4 - blanks stay blank and carry a limitation.
    failures, blanks = [], 0
    for row in rows:
        if row["basis"] == "unresolved":
            blanks += 1
            if row.get("prob_a") is not None or row.get("safe_pick"):
                failures.append(f"{row['fixture_id']}: unresolved row publishes a probability or pick")
            if not row.get("limitation"):
                failures.append(f"{row['fixture_id']}: unresolved row without a published limitation")
            if row.get("quotes"):
                failures.append(f"{row['fixture_id']}: unresolved row with a retained quote")
    checks.append(check("C4", "Unresolved rows stay blank and publish why", len(rows), failures,
                        f"{blanks} unresolved row(s) in this build"))

    # C5 - every row carries at least one https source link.
    failures = []
    for row in rows:
        links = [s.get("url") for s in row.get("sources") or []]
        if not links or not all(str(u).startswith("http") for u in links):
            failures.append(f"{row['fixture_id']}: missing or non-http source link")
    checks.append(check("C5", "Every row carries at least one http(s) source link", len(rows), failures,
                        "a row without a link is unpublished, not inferred"))

    # C6 - the crowd share is never numerically equal to a published probability.
    collisions = []
    for row in rows:
        crowd = row.get("crowd") or {}
        for key in ("a", "b"):
            share = crowd.get(key)
            if share is None:
                continue
            for side in ("prob_a", "prob_b"):
                if row.get(side) is not None and abs(row[side] - share) < TOL:
                    collisions.append(f"{row['fixture_id']}: {side} equals crowd share {key}")
    checks.append(check("C6", "Crowd ownership never equals a published probability", len(rows),
                        collisions, "static collision check; the unit suite also mutates crowd shares"
                                    " and asserts the published numbers do not move"))

    # C7 - climb gates and the daily cap.
    failures, active = [], [r for r in rows if r.get("climb_active")]
    for row in rows:
        gates = row.get("gates") or {}
        if row.get("climb_active"):
            dog = row.get("underdog") or {}
            if not gates.get("prob_floor_30pct") or not gates.get("leverage_2x"):
                failures.append(f"{row['fixture_id']}: climb activated without clearing both gates")
            if row.get("climb_pick") != dog.get("team"):
                failures.append(f"{row['fixture_id']}: climb pick is not the gated underdog")
    if len(active) > board["policy"]["climb_max_per_day"]:
        failures.append(f"{len(active)} activations exceed the daily cap")
    checks.append(check("C7", "Climb picks clear the declared gates and the daily cap", len(rows),
                        failures, f"{len(active)} activation(s), cap "
                                  f"{board['policy']['climb_max_per_day']}"))

    # C8 - identity and ambiguity decisions are published where they were applied.
    failures, published = [], 0
    for row in rows:
        vrs = row.get("vrs") or {}
        for side in ("team_a", "team_b"):
            for note in (vrs.get(side) or {}).get("notes") or []:
                published += 1
                if note.get("type") == "ambiguous_official_name" and not note.get("candidates"):
                    failures.append(f"{row['fixture_id']}: ambiguous name without published candidates")
                if note.get("type") == "identity_alias" and not note.get("sources"):
                    failures.append(f"{row['fixture_id']}: alias applied without evidence links")
    checks.append(check("C8", "Ambiguity and alias decisions are published with their evidence",
                        len(rows), failures, f"{published} decision(s) recorded"))

    # C9 - the page set exists, is mobile-ready and its internal links resolve.
    failures, pages = [], sorted((ROOT / "desk").glob("*.html"))
    names = {p.name for p in pages}
    for page in pages:
        text = page.read_text()
        if 'name="viewport"' not in text:
            failures.append(f"{page.name}: no mobile viewport")
        if "px" in text and "max-width" not in text:
            failures.append(f"{page.name}: rendered without a width constraint")
        for target in set(__import__("re").findall(r'href="([a-z0-9_.-]+\.html)(?:#[^"]*)?"', text)):
            if target not in names:
                failures.append(f"{page.name}: broken internal link {target}")
    checks.append(check("C9", "Desk pages exist, are mobile-ready and link only to real pages",
                        len(pages), failures, ", ".join(sorted(names))))

    # C10 - the refresh cadence sits inside the required 4-8 hour band.
    failures = []
    workflow = ROOT / ".github" / "workflows" / "desk-6484426f.yml"
    if not workflow.exists():
        failures.append("workflow file missing")
    else:
        import re
        text = workflow.read_text()
        found = re.findall(r"cron:\s*'(\S+ \S+ \S+ \S+ \S+)'", text)
        if not found:
            failures.append("no schedule cron found")
        for expr in found:
            minute, hour, *_ = expr.split()
            if hour.startswith("*/"):
                step = int(hour[2:])
                if not (4 <= step <= 8) or step not in (4, 6, 8):
                    failures.append(f"cron {expr} is outside the 4-8 hour band")
            elif "," in hour or "*" == hour:
                failures.append(f"cron {expr} is not a fixed multi-hour cadence")
    checks.append(check("C10", "Refresh cadence stays inside the 4-8 hour policy", 1, failures,
                        "workflow .github/workflows/desk-6484426f.yml"))

    failed = sum(1 for c in checks if c["status"] == "fail")
    source_mix = {}
    for row in rows:
        for q in row.get("quotes") or []:
            source_mix[q["source_key"]] = source_mix.get(q["source_key"], 0) + 1
    out = {"session": "6484426f", "generated_utc": iso_now(), "source_mix": source_mix,
           "board_generated_utc": board["generated_utc"],
           "checks": checks,
           "summary": {"checks": len(checks), "passed": len(checks) - failed, "failed": failed},
           "quotes_re_derived": quotes_rederived, "rows_checked": len(rows), "blank_rows": blanks,
           "crowd_probability_collisions": len(collisions)}
    VERIFY.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(out["summary"], indent=1))
    for c in checks:
        if c["status"] != "pass":
            print(c["id"], c["name"], c["failures"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
