#!/usr/bin/env python3
"""Headless-Chromium probe of JS-rendered esports odds pages.

Many bookmakers/aggregators block plain HTTP clients (Cloudflare bot management) but
still serve a normal browser. This probe loads each page in real Chromium and records:

  * navigation status, final URL, title
  * visible text length and count of odds-like tokens (e.g. ``1.75``)
  * every XHR/fetch request the page made, with status + content type, so that a
    machine-readable data endpoint can be identified for automated re-collection
  * for JSON responses, a size-limited preview of the raw payload

No odds value is taken from this probe — it only records reachability and payload
structure as evidence. Prices are only ever taken from a source payload that a later
collector parses explicitly, with its own per-row provenance.

Usage: python3 scripts/expanded/probe_rendered.py [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

TARGETS = [
    ("egamersworld_cs_matches", "https://egamersworld.com/counterstrike/matches"),
    ("egamersworld_lol_matches", "https://egamersworld.com/leagueoflegends/matches"),
    ("hltv_matches", "https://www.hltv.org/matches"),
    ("thunderpick_cs2", "https://thunderpick.io/esports/cs2-betting"),
    ("oddspedia_esports", "https://oddspedia.com/esports"),
    ("ggbet_esports", "https://gg.bet/en/esports"),
    ("betway_esports", "https://sports.betway.com/en/sports/grp/esports"),
    ("bovada_esports", "https://www.bovada.lv/sports/esports"),
    ("pinnacle_esports", "https://www.pinnacle.com/en/esports/"),
    ("betonline_esports", "https://www.betonline.ag/sportsbook/esports"),
    ("betano_esports", "https://www.betano.pt/sport/esports/"),
    ("unibet_esports", "https://www.unibet.com/betting/sports/filter/esports/all/matches"),
]

APILIHOOD_RE = re.compile(r"(api|odds|market|event|match|graphql|feed|line)", re.I)
ODDS_TOKEN_RE = re.compile(r"(?<![\d.])(\d\.\d{2})(?![\d.])")


def now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def probe() -> list[dict]:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    out: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        for key, url in TARGETS:
            rec: dict = {"key": key, "url": url, "requests": [], "json_responses": []}
            ctx = browser.new_context(user_agent=UA, viewport={"width": 1440, "height": 1000},
                                      locale="en-US", timezone_id="UTC")
            page = ctx.new_page()

            def on_response(resp, rec=rec):  # noqa: ANN001
                try:
                    ctype = (resp.headers or {}).get("content-type", "")
                    entry = {"status": resp.status, "url": resp.url[:300],
                             "content_type": ctype[:80]}
                    if APILIHOOD_RE.search(resp.url):
                        rec["requests"].append(entry)
                    if "json" in ctype and len(rec["json_responses"]) < 12:
                        try:
                            body = resp.text()
                        except Exception:  # noqa: BLE001
                            body = ""
                        if body:
                            rec["json_responses"].append(
                                {"status": resp.status, "url": resp.url[:300],
                                 "bytes": len(body), "preview": body[:1200]})
                except Exception:  # noqa: BLE001
                    pass

            page.on("response", on_response)
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                rec["http_status"] = resp.status if resp else 0
                page.wait_for_timeout(8000)
                try:
                    page.mouse.wheel(0, 3000)
                    page.wait_for_timeout(3000)
                except Exception:  # noqa: BLE001
                    pass
                text = page.inner_text("body")
                rec.update({
                    "final_url": page.url,
                    "title": page.title(),
                    "bytes_text": len(text),
                    "odds_tokens": len(ODDS_TOKEN_RE.findall(text[:200_000])),
                    "preview": text[:800],
                    "error": None,
                })
            except Exception as exc:  # noqa: BLE001
                rec.update({"http_status": 0, "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            rec["requests"] = rec["requests"][:40]
            out.append(rec)
            print(f"{rec.get('http_status', 0):>4} {key:<28} tokens={rec.get('odds_tokens')} "
                  f"reqs={len(rec['requests'])} json={len(rec['json_responses'])} "
                  f"title={str(rec.get('title'))[:50]} err={str(rec.get('error'))[:70]}")
            for jr in rec["json_responses"][:6]:
                print(f"      JSON {jr['status']} {jr['bytes']}B {jr['url'][:140]}")
            ctx.close()
        browser.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "expanded" / "rendered_probe.json"))
    args = ap.parse_args()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "generated_at_utc": now_iso(),
        "purpose": ("Reachability + payload-structure evidence for JS-rendered esports odds pages. "
                    "Records network calls made by the real page so an automatable JSON endpoint "
                    "can be identified. No odds value is taken from this probe."),
        "runner": {"github_actions": bool(os.environ.get("GITHUB_ACTIONS"))},
        "pages": probe(),
    }
    out_path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"WROTE {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
