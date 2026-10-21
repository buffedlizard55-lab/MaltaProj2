#!/usr/bin/env python3
"""Headless Chromium mobile (390x844) & desktop (1280x900) verification for lobby/ & root index.html."""
from __future__ import annotations

import functools
import http.server
import os
import shutil
import socketserver
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PAGES = [
    "index.html",
    "lobby/index.html",
    "lobby/picks.html",
    "lobby/featured.html",
    "lobby/low-tier.html",
    "lobby/unresolved.html",
    "lobby/flagged.html",
    "lobby/inventory.html",
    "lobby/methodology.html",
]


def main() -> int:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    class QuietTCPServer(socketserver.TCPServer):
        allow_reuse_address = True
        def log_message(self, *args):
            pass

    server = QuietTCPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with sync_playwright() as p:
            chrome_path = shutil.which("google-chrome") or "/usr/bin/google-chrome"
            launch_kwargs = {"headless": True, "args": ["--no-sandbox"]}
            if os.path.exists(chrome_path):
                launch_kwargs["executable_path"] = chrome_path
            browser = p.chromium.launch(**launch_kwargs)
            for label, width, height in (("mobile", 390, 844), ("desktop", 1280, 900)):
                ctx = browser.new_context(viewport={"width": width, "height": height})
                page = ctx.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

                for rel in PAGES:
                    resp = page.goto(f"http://127.0.0.1:{port}/{rel}", wait_until="networkidle")
                    assert resp and resp.status == 200, f"{rel}: HTTP {resp.status if resp else None}"
                    assert not errors, f"JS errors on {rel} ({label}): {errors}"
                    overflow = page.evaluate(
                        "document.documentElement.scrollWidth - window.innerWidth"
                    )
                    assert overflow <= 1, f"Horizontal overflow {overflow}px on {rel} ({label})"

                # Interactive filter check on lobby/picks.html
                page.goto(f"http://127.0.0.1:{port}/lobby/picks.html", wait_until="networkidle")
                total_rows = page.locator("tr[data-row]").count()
                assert total_rows >= 1, "Expected at least 1 match row on lobby/picks.html"
                first_term = page.locator("tr[data-row]").first.inner_text().split(" vs ")[0].strip().lower()
                page.fill("#match-filter", first_term)
                assert page.locator("tr[data-row]:not([hidden])").count() >= 1
                page.fill("#match-filter", "__no_such_cs2_team_xyz__")
                assert page.locator("tr[data-row]:not([hidden])").count() == 0
                page.fill("#match-filter", "zetta")
                if page.locator("tr[data-row]:not([hidden])").count() >= 1:
                    text = page.locator("tr[data-row]:not([hidden])").first.inner_text()
                    assert "BLANK" in text and "Unverified" in text, text
                page.fill("#match-filter", "")

                shot_dir = Path("/tmp/7adc7718-shots")
                shot_dir.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(shot_dir / f"lobby-picks-{label}.png"), full_page=False)
                page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="networkidle")
                page.screenshot(path=str(shot_dir / f"root-index-{label}.png"), full_page=False)
                ctx.close()
            browser.close()
    finally:
        server.shutdown()

    print("PASS: 7adc7718 Playwright mobile (390x844) + desktop (1280x900) checks clean across 9 pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
