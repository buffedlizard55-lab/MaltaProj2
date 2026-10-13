#!/usr/bin/env python3
"""Capture payload samples from JS-rendered odds sources using headless Chromium.

Sources that block plain HTTP clients (Cloudflare bot management) but serve a normal
browser are captured here: the real page is loaded, every XHR/fetch it makes is logged
(with POST bodies for GraphQL), and JSON responses are saved as raw samples.

This is evidence + parser input only: nothing is published from these captures.

Usage: python3 scripts/expanded/capture_browser_samples.py [--outdir DIR]
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

TARGETS = [
    ("ggbet_cs2", "https://gg.bet/en/esports/counter-strike"),
    ("ggbet_lol", "https://gg.bet/en/esports/league-of-legends"),
    ("oddspedia_cs2", "https://oddspedia.com/counter-strike"),
    ("oddspedia_lol", "https://oddspedia.com/league-of-legends"),
]

# Same-origin API calls attempted from inside the loaded page (browser context has the
# cookies / TLS fingerprint the plain client lacks).
IN_PAGE_CALLS = {
    "oddspedia_cs2": [
        "https://oddspedia.com/api/v1/getMatchList?excludeExchanges=1&language=en&sport=counter-strike&status=all&limit=200",
        "https://oddspedia.com/api/v1/getMatchList?language=en&sport=counter-strike&status=all",
        "https://oddspedia.com/api/v1/getPopularLeagues?language=en&sport=counter-strike",
    ],
    "oddspedia_lol": [
        "https://oddspedia.com/api/v1/getMatchList?excludeExchanges=1&language=en&sport=league-of-legends&status=all&limit=200",
    ],
}
JSON_CAP = 400_000
MAX_SAVED = 10


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def capture(outdir: Path) -> dict:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    doc: dict = {"generated_at_utc": now_iso(), "targets": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        for key, url in TARGETS:
            rec: dict = {"key": key, "url": url, "requests": [], "saved": [], "in_page_calls": []}
            ctx = browser.new_context(user_agent=UA, viewport={"width": 1440, "height": 1000},
                                      locale="en-US", timezone_id="UTC")
            page = ctx.new_page()
            counter = {"n": 0}

            def on_request(req, rec=rec):  # noqa: ANN001
                try:
                    if req.resource_type in ("xhr", "fetch"):
                        entry = {"method": req.method, "url": req.url[:400]}
                        if req.method == "POST":
                            try:
                                entry["post_data"] = (req.post_data or "")[:3000]
                            except Exception:  # noqa: BLE001
                                entry["post_data"] = None
                        rec["requests"].append(entry)
                except Exception:  # noqa: BLE001
                    pass

            def on_response(resp, rec=rec, counter=counter):  # noqa: ANN001
                try:
                    ctype = (resp.headers or {}).get("content-type", "")
                    if "json" not in ctype or counter["n"] >= MAX_SAVED:
                        return
                    body = resp.text()
                    if not body or len(body) < 400:
                        return
                    counter["n"] += 1
                    name = f"{rec['key']}__{counter['n']:02d}.json"
                    p = outdir / name
                    p.write_text(body[:JSON_CAP], encoding="utf-8")
                    rec["saved"].append({"file": name, "status": resp.status,
                                         "bytes": len(body), "url": resp.url[:300]})
                except Exception:  # noqa: BLE001
                    pass

            page.on("request", on_request)
            page.on("response", on_response)
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                rec["http_status"] = resp.status if resp else 0
                page.wait_for_timeout(8000)
                try:
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(4000)
                except Exception:  # noqa: BLE001
                    pass
                rec["final_url"] = page.url
                rec["title"] = page.title()
                text = page.inner_text("body")
                rec["bytes_text"] = len(text)
                rec["text_preview"] = text[:1500]
                rec["error"] = None
            except Exception as exc:  # noqa: BLE001
                rec.update({"http_status": 0, "error": f"{type(exc).__name__}: {str(exc)[:250]}"})

            for call in IN_PAGE_CALLS.get(key, []):
                try:
                    result = page.evaluate(
                        """async (u) => {
                             const r = await fetch(u, {headers: {'accept': 'application/json'}});
                             const t = await r.text();
                             return {status: r.status, body: t.slice(0, 300000)};
                           }""", call)
                    entry = {"url": call, "status": result.get("status"),
                             "bytes": len(result.get("body") or "")}
                    if result.get("body"):
                        name = f"{key}__inpage__{len(rec['in_page_calls']) + 1:02d}.json"
                        (outdir / name).write_text(result["body"], encoding="utf-8")
                        entry["file"] = name
                    rec["in_page_calls"].append(entry)
                except Exception as exc:  # noqa: BLE001
                    rec["in_page_calls"].append({"url": call, "error": str(exc)[:200]})

            rec["requests"] = rec["requests"][:80]
            doc["targets"].append(rec)
            print(f"{rec.get('http_status', 0):>4} {key:<16} reqs={len(rec['requests'])} "
                  f"saved={len(rec['saved'])} inpage={len(rec['in_page_calls'])} "
                  f"title={str(rec.get('title'))[:40]}")
            for s in rec["saved"]:
                print(f"      SAVED {s['file']:<28} {s['bytes']:>8}B {s['url'][:110]}")
            for c in rec["in_page_calls"]:
                print(f"      INPAGE {c.get('status')} {c.get('bytes')} {c['url'][:100]}")
            ctx.close()
        browser.close()
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=str(ROOT / "data" / "expanded" / "samples"))
    args = ap.parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    doc = capture(outdir)
    (outdir / "browser_capture.json").write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"\nWROTE {outdir}/browser_capture.json   actions={bool(os.environ.get('GITHUB_ACTIONS'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
