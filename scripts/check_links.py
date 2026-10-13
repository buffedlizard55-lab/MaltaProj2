#!/usr/bin/env python3
"""Verify the generated site has no broken internal links/assets.

External links are listed (not fetched - the build runs offline) so they can be
spot-checked by hand. Exit code is non-zero if any local target is missing.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "pickem")

ATTR = re.compile(r'(?:href|src)\s*=\s*"([^"]+)"', re.I)


def main():
    missing, externals, pages = [], set(), 0
    for name in sorted(os.listdir(DOCS)):
        if not name.endswith(".html"):
            continue
        pages += 1
        path = os.path.join(DOCS, name)
        with open(path) as f:
            html = f.read()
        for url in ATTR.findall(html):
            if url.startswith(("http://", "https://", "mailto:", "#", "data:")):
                externals.add(url)
                continue
            target = os.path.join(DOCS, url.split("#")[0].split("?")[0])
            if not os.path.exists(target):
                missing.append(f"{name} -> {url}")
    print(f"pages checked: {pages}")
    print(f"external links referenced: {len(externals)}")
    if missing:
        print("BROKEN LOCAL LINKS:")
        for m in sorted(set(missing)):
            print("  " + m)
        return 1
    print("no broken local links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
