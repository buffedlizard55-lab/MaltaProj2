#!/usr/bin/env python3
"""Official Valve Regional Standings (VRS) reader for session 86f3af65.

Source of record: ValveSoftware/counter-strike_regional_standings (public GitHub repo that Valve
publishes its Counter-Strike ranking files in). Nothing here invents a rating: every number comes
from a parsed row of a published standings file, or is explicitly marked as an assumption.

Two things this module handles carefully, because they decide real probabilities:

1. **Duplicate organisation names.** Valve keeps a separate row for every *roster*, so one
   organisation name can appear twice with two different rank values (e.g. "Banda Chuya" #165,
   five players, and "Banda Chuya" #373, two players). The file itself does not say which roster
   is playing tonight's fixture. We therefore record *all* candidates plus the evidence that can
   be read from Valve's own per-roster details page (roster size and the date of the most recent
   counted match) and apply a stated, published selection policy:

       policy DUPLICATE_ROSTER_POLICY below

   A row resolved under this policy is labelled ``roster-selected`` everywhere it is published,
   together with the candidate that was *not* used and the probability that candidate would have
   produced (sensitivity), so the assumption is visible rather than buried.

2. **Teams with no published rating.** Several low-tier HotSpawn fixtures contain a team that is
   absent from all four published files (global + americas + asia + europe). For those the caller
   may pass ``floor_ok=True``, which assigns the lowest rank value Valve publishes (381 = #380).
   That is an *assumption*, never a source value; the resulting probability is labelled
   ``floor-proxy`` and is listed on the Unresolved & limitations page.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*(\d+)\s*\|([^|]+)\|([^|]*)\|\s*\[details\]\(([^)]+)\)", re.M)
DATE_RE = re.compile(r"^\|\s*\d+\s*\|\s*\d+\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", re.M)
REGION_RE = re.compile(r"(?:live/\d{4}/)?standings_(global|americas|asia|europe)_(\d{4}_\d{2}_\d{2})\.md$")

DUPLICATE_ROSTER_POLICY = (
    "When Valve's standings contain more than one row for the same organisation name, a roster "
    "with fewer than five players cannot field a Counter-Strike team and is excluded. If more "
    "than one five-player roster remains, the one whose official Valve details page shows the "
    "most recent counted match is used. If the remaining candidates tie on date the fixture is "
    "left unrated (ambiguous) rather than guessed. This is a stated modelling policy: the "
    "standings file does not itself say which roster is fielded."
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_PREFIX = {"team", "the"}
_SUFFIX = {"team", "esports", "esport", "gaming", "gg", "club", "cs"}


def norm(name: str | None) -> str:
    """Case/accent/punctuation-insensitive team key (generic org words stripped)."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = text.replace("&", "and")
    tokens = [t for t in re.split(r"[^a-z0-9.]+", text) if t]
    while len(tokens) > 1 and tokens[0] in _PREFIX:
        tokens.pop(0)
    while len(tokens) > 1 and tokens[-1] in _SUFFIX:
        tokens.pop()
    return _NON_ALNUM.sub("", "".join(tokens))


def parse_standings(text: str, region: str) -> list[dict]:
    rows = []
    for m in ROW_RE.finditer(text or ""):
        roster = m.group(4).strip()
        rows.append({
            "region": region,
            "standing": int(m.group(1)),
            "points": int(m.group(2)),
            "team": m.group(3).strip(),
            "roster": roster,
            "players": [p.strip() for p in roster.split(",") if p.strip()],
            "details_path": m.group(5).strip(),
        })
    return rows


def latest_match_date(details_md: str) -> tuple[str | None, int]:
    dates = DATE_RE.findall(details_md or "")
    return (max(dates) if dates else None), len(dates)


def file_meta(region: str, path: str) -> dict:
    m = REGION_RE.search(path)
    return {
        "region": m.group(1) if m else region,
        "snapshot": m.group(2) if m else None,
        "path": path,
        "page_url": ("https://github.com/ValveSoftware/counter-strike_regional_standings/"
                     f"blob/main/{path}"),
        "api_url": ("https://api.github.com/repos/ValveSoftware/"
                    f"counter-strike_regional_standings/contents/{path}"),
    }


class Standings:
    """Index of every published VRS row, with roster-aware duplicate handling."""

    def __init__(self, files: list[dict], rows: list[dict], floor_points: int = 381,
                 floor_standing: int = 380):
        self.files = files
        self.rows = rows
        self.floor_points = int(floor_points)
        self.floor_standing = int(floor_standing)
        self.groups: dict[str, list[dict]] = {}
        for row in rows:
            key = norm(row["team"])
            if key:
                self.groups.setdefault(key, []).append(row)
        for group in self.groups.values():
            # Global rows first: probabilities are only comparable inside the global pool.
            group.sort(key=lambda r: (r["region"] != "global", r["standing"]))

    # ---------------------------------------------------------------- construction helpers
    @classmethod
    def from_capture(cls, vrs: dict) -> "Standings":
        return cls(vrs.get("files") or [], vrs.get("rows") or [],
                   (vrs.get("floor") or {}).get("points", 381),
                   (vrs.get("floor") or {}).get("standing", 380))

    def global_rows(self) -> list[dict]:
        return [r for r in self.rows if r["region"] == "global"]

    # ---------------------------------------------------------------- resolution
    def resolve(self, name: str, floor_ok: bool = False) -> dict:
        """Resolve one team name to a citable rating, or explain why it cannot be resolved.

        Returns a dict with ``status`` in
            unique | roster-selected | absent | ambiguous
        plus ``row`` (the row used, if any), ``candidates`` (every duplicate candidate with the
        evidence used) and ``source`` (the page URL a reader can check).
        """
        key = norm(name)
        group = self.groups.get(key, [])
        out = {
            "team": name,
            "key": key,
            "status": "absent",
            "row": None,
            "candidates": [],
            "rejected": [],
            "source": None,
            "policy": None,
        }
        if not group:
            out["assumption"] = None
            if floor_ok:
                out.update({
                    "status": "floor-proxy",
                    "assumption": (
                        f"{name} is absent from the published global, americas, asia and europe "
                        f"standings files, so it is assigned the lowest rank value Valve publishes "
                        f"({self.floor_points} points, standing #{self.floor_standing})."),
                    "row": {
                        "region": "floor",
                        "standing": self.floor_standing,
                        "points": self.floor_points,
                        "team": name,
                        "roster": None,
                        "details_path": None,
                        "is_floor_proxy": True,
                    },
                })
                out["source"] = (self.files[0]["page_url"] if self.files
                                 else "https://github.com/ValveSoftware/"
                                      "counter-strike_regional_standings")
            return out

        # Global rows are the comparable pool; a regional-only row would not be comparable.
        pool = [r for r in group if r["region"] == "global"] or group
        out["candidates"] = [{k: r.get(k) for k in ("region", "standing", "points", "team",
                                                    "roster", "details_path",
                                                    "latest_match_date", "counted_matches")}
                             for r in pool]
        five = [r for r in pool if len(r.get("players") or []) >= 5]
        if len(pool) == 1:
            out.update({"status": "unique", "row": pool[0]})
        elif len(five) == 1:
            out.update({"status": "roster-selected", "row": five[0], "policy": DUPLICATE_ROSTER_POLICY})
            out["rejected"] = [r for r in pool if r is not five[0]]
        elif len(five) > 1:
            dated = [r for r in five if r.get("latest_match_date")]
            if len(dated) >= 1:
                best = max(dated, key=lambda r: (r["latest_match_date"], -r["standing"]))
                ties = [r for r in dated if r["latest_match_date"] == best["latest_match_date"]]
                if len(ties) == 1:
                    out.update({"status": "roster-selected", "row": best,
                                "policy": DUPLICATE_ROSTER_POLICY})
                    out["rejected"] = [r for r in pool
                                       if r["details_path"] != best["details_path"]]
                else:
                    out["status"] = "ambiguous"
            else:
                out["status"] = "ambiguous"
        else:
            out["status"] = "ambiguous"

        if out["row"]:
            meta = file_meta(out["row"]["region"], "") if out["row"]["region"] == "floor" else None
            if meta is None:
                reg = next((f for f in self.files if f["region"] == out["row"]["region"]), None)
                out["source"] = reg["page_url"] if reg else None
        return out


def load_pinned_standings(valve_dir: Path) -> tuple[Standings, dict]:
    """Load the standings markdown files pinned under data/86f3af65/valve/."""
    files, rows = [], []
    live = {}
    live_path = valve_dir / "live_reads.json"
    if live_path.exists():
        try:
            live = json.loads(live_path.read_text())
        except ValueError:
            live = {}
    live_files = live.get("files") or {}
    for path in sorted(valve_dir.glob("standings_*.md")):
        m = REGION_RE.search(path.name)
        if not m:
            continue
        region, snapshot = m.group(1), m.group(2)
        text = path.read_text(encoding="utf-8")
        meta = file_meta(region, f"live/2026/{path.name}")
        meta["snapshot"] = snapshot
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        recorded = live_files.get(path.name) or {}
        meta["sha256"] = sha
        meta["bytes"] = len(path.read_bytes())
        meta["git_sha"] = recorded.get("git_sha")
        meta["retrieved_utc"] = live.get("read_utc")
        meta["sha256_matches_live_read"] = (recorded.get("sha256") == sha) if recorded else None
        files.append(meta)
        rows.extend(parse_standings(text, region))
    # Attach the per-roster details evidence that was pinned next to the standings files.
    details_dir = valve_dir / "details"
    if details_dir.is_dir():
        index = {}
        for md in details_dir.glob("*.md"):
            date, count = latest_match_date(md.read_text(encoding="utf-8"))
            index[md.name] = {"latest_match_date": date, "counted_matches": count}
        for row in rows:
            name = row["details_path"].rsplit("/", 1)[-1]
            if name in index:
                row.update(index[name])
    order = {"global": 0, "americas": 1, "asia": 2, "europe": 3}
    files.sort(key=lambda f: (order.get(f["region"], 9), f["snapshot"]))
    global_rows = [r for r in rows if r["region"] == "global"]
    floor = max(global_rows, key=lambda r: r["standing"]) if global_rows else {"points": 381,
                                                                               "standing": 380}
    manifest = {
        "snapshot": files[0]["snapshot"] if files else None,
        "files": files,
        "floor": {"points": floor["points"], "standing": floor["standing"],
                  "team": floor.get("team")},
        "counts": {f["region"]: sum(1 for r in rows if r["region"] == f["region"])
                   for f in files},
    }
    return Standings(files, rows, floor["points"], floor["standing"]), manifest


if __name__ == "__main__":  # pragma: no cover - inspection helper
    st, man = load_pinned_standings(Path(__file__).resolve().parents[2] / "data/86f3af65/valve")
    print(json.dumps(man, indent=1))
    for name in ("Banda chuya", "The Huns", "benched gods", "LOS NINOS", "Zetta"):
        print(name, json.dumps(st.resolve(name, floor_ok=True), indent=1)[:600])
