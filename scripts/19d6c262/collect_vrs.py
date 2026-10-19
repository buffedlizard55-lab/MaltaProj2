#!/usr/bin/env python3
"""Session 19d6c262 — fetch the official Valve Regional Standings (VRS) from GitHub.

Source of truth: ValveSoftware/counter-strike_regional_standings (official). We read the
newest published `live/<year>/standings_global_<date>.md` and, for teams named in the
HotSpawn fixture list (and any ambiguous duplicate names), each team's official `details`
file to record the counted roster and the most recent counted match date. Nothing here is
inferred: every field is copied from the official files, and the file path + snapshot date
are stored so each row can be re-checked against the source.
"""
from __future__ import annotations
import base64, json, re, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "19d6c262"
REPO = "ValveSoftware/counter-strike_regional_standings"
UA = {"Accept": "application/vnd.github+json", "User-Agent": "malta-everymatch-resolver"}


def gh(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def b64_text(blob: dict) -> str:
    if isinstance(blob, dict) and blob.get("content"):
        return base64.b64decode(blob["content"]).decode("utf-8", "replace")
    return ""


def canon(name: str) -> str:
    s = (name or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def latest_match_date(md: str):
    dates = re.findall(r"(20\d{2}-\d{2}-\d{2})", md or "")
    return max(dates) if dates else None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tree = gh(f"https://api.github.com/repos/{REPO}/git/trees/main?recursive=1")
    newest = None
    for node in tree.get("tree", []):
        m = re.match(r"^live/(\d{4})/standings_global_(\d{4}_\d{2}_\d{2})\.md$", str(node.get("path")))
        if m and (newest is None or m.group(2) > newest[1]):
            newest = (m.group(1), m.group(2), node["path"])
    if not newest:
        print("no standings file found", file=sys.stderr)
        return 1
    path = newest[2]
    text = b64_text(gh(f"https://api.github.com/repos/{REPO}/contents/{path}"))
    base_dir = path.rsplit("/", 1)[0]
    teams = []
    for m in re.finditer(r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]+)\|([^|]*)\|\s*\[details\]\(([^)]+)\)", text, re.M):
        teams.append({"standing": int(m.group(1)), "points": int(m.group(2)),
                      "team": m.group(3).strip(), "roster": m.group(4).strip(),
                      "details_path": f"{base_dir}/{m.group(5).strip()}"})
    # Which teams do we need details for? Every team named by an open fixture, plus every
    # duplicate-name group (so an ambiguous join can be reviewed with roster evidence).
    board_path = ROOT / "data" / "f7279a54" / "board.json"
    wanted = set()
    try:
        board = json.loads(board_path.read_text())
        for r in board.get("open", []):
            wanted.add(canon(r["team_a"]))
            wanted.add(canon(r["team_b"]))
    except (OSError, ValueError):
        pass
    # Also fetch details for documented alias targets (e.g. "Aurora YB" -> "Aurora Young Blud"),
    # so an alias-resolved row still carries its official details link. Mirrors resolve.ALIASES.
    try:
        import resolve  # noqa: PLC0415
        for _tgt, _basis in resolve.ALIASES.values():
            wanted.add(canon(_tgt))
    except Exception:
        pass
    groups: dict[str, list] = {}
    for t in teams:
        groups.setdefault(canon(t["team"]), []).append(t)
    need = {k for k in wanted if k in groups} | {k for k, rows in groups.items() if len(rows) > 1}
    for key in sorted(need):
        for t in groups[key]:
            dp = t["details_path"]
            from urllib.parse import quote
            md = b64_text(gh(f"https://api.github.com/repos/{REPO}/contents/{quote(dp)}"))
            t["latest_match_date"] = latest_match_date(md)
            t["details_url"] = f"https://github.com/{REPO}/blob/main/{quote(dp)}"
    out = {"snapshot": newest[1], "path": path,
           "page_url": f"https://github.com/{REPO}/blob/main/{path}",
           "api_url": f"https://api.github.com/repos/{REPO}/contents/{path}",
           "n_teams": len(teams), "teams": teams,
           "floor": {"standing": core.VRS_FLOOR_STANDING, "points": core.VRS_FLOOR_POINTS}}
    (OUT / "vrs_global.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"VRS snapshot {newest[1]}: {len(teams)} teams; details fetched for {len(need)} names")
    return 0


if __name__ == "__main__":
    sys.exit(main())
