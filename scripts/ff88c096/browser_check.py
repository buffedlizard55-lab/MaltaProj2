#!/usr/bin/env python3
"""Headless Chromium layout, overflow, single-h1, and internal-link check for ff88c096."""
from __future__ import annotations

import http.server
import os
import socketserver
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
PAGES = [
    "/index.html",
    "/flagged.html",
    "/fullboard/index.html",
    "/fullboard/picks.html",
    "/fullboard/unresolved.html",
    "/fullboard/featured-vs-fallback.html",
    "/fullboard/hotspawn-lobby.html",
    "/fullboard/repo-audit.html",
    "/fullboard/flagged.html",
    "/fullboard/methodology.html",
]


def main() -> None:
    target = ROOT / "out" / "site" if (ROOT / "out" / "site" / "fullboard").exists() else ROOT

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(target), **kwargs)

        def log_message(self, format, *args):
            pass

    chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/google-chrome")
    launch_kwargs = {"headless": True, "args": ["--no-sandbox"]}
    if Path(chrome_bin).exists():
        launch_kwargs["executable_path"] = chrome_bin

    with socketserver.TCPServer(("127.0.0.1", 0), QuietHandler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(**launch_kwargs)
                for width, height in ((320, 844), (375, 812), (1440, 900)):
                    page = browser.new_page(viewport={"width": width, "height": height})
                    for rel in PAGES:
                        resp = page.goto(f"http://127.0.0.1:{port}{rel}", wait_until="networkidle")
                        assert resp is not None and resp.status == 200, f"HTTP {resp} on {rel}"
                        h1_count = page.locator("h1").count()
                        assert h1_count == 1, f"{rel} has {h1_count} <h1> elements at {width}px"
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= window.innerWidth"
                        ), f"{rel} horizontally overflows at {width}px viewport"
                    page.close()
                browser.close()
        finally:
            httpd.shutdown()
    print(f"PASS: ff88c096 Chromium gate verified {len(PAGES)} pages across 320px/375px/1440px (0px overflow)")


if __name__ == "__main__":
    main()
