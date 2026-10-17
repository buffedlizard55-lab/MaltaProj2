#!/usr/bin/env python3
"""Session c32f1b93 board builder + mobile-first site renderer.

Re-derives every pick from retained primary evidence (see core.py docstring) and
writes:
    data/c32f1b93/board.json      the every-match pick board (full provenance)
    audits/c32f1b93/*.html        mobile-first pages (exec summary, picks, TWC
                                  day-4 desk, unresolved, flagged, method)
No network access at build time. Run: python3 scripts/c32f1b93/build.py
"""
from __future__ import annotations

import html
import json
import math
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import (  # noqa: E402
    ALIASES, BLEND_MARKET_WEIGHT, CONFIDENCE_BANDS, EGW_PLACEHOLDER,
    ELO_BASE, ELO_K, ELO_PASSES, FIT_BOUNDS, FIT_MIN_PAIRS, KALSHI_MAX_SPREAD,
    SESSION, VALVE_C, VALVE_G, VALVE_RD, canon, devig, elo_expected, elo_run,
    fit_slope, logit, norm, parse_vrs_file, sigmoid, vrs_join, vrs_prob,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / SESSION
FE80 = ROOT / "data" / "fe803b80"
AUDIT = ROOT / "audits" / SESSION
BUILD_UTC = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def pct(p, digits=1):
    return None if p is None else round(100.0 * p, digits)


def iso(dt_str):
    return str(dt_str).replace("T", " ").replace("Z", " UTC") if dt_str else "—"


def confidence(prob: float | None) -> str:
    if prob is None:
        return "Unresolved"
    for bound, label in CONFIDENCE_BANDS:
        if prob >= bound:
            return label
    return "Toss-up"


# --------------------------------------------------------------------------- load inputs
research = load_json(DATA / "research.json")
crowd_ctx = load_json(DATA / "crowd_context.json")
vrs_file = parse_vrs_file(str(DATA / "vrs_global_2026_10_05.md"))
snapshot = load_json(FE80 / "snapshot.json")

# Live VRS point overrides: the Oct-16 HLTV regional ladders (Europe/Americas/Asia,
# read 2026-10-17T05:00-07:00Z; the Oct-5 global file is the latest full ladder in the
# repo). Every value below was read off a rendered ladder row carrying the verified
# current roster. The Oct-5 file predates the TWC Madrid group stage, so all TWC
# participants MUST be overridden (FURIA -2, Aurora +132, Falcons +37, BETBOOM +23,
# Legacy -172, 9z +425) - using file values here would flip the SF1 model pick.
LIVE_VRS_OVERRIDES = {
    "furia": {"points": 1827, "standing": "AM #1", "region": "Americas",
              "note": "file 1829 -> live 1827 (-2); roster FalleN, yuurih, YEKINDAR, KSCERATO, molodoy unchanged"},
    "aurora": {"points": 1848, "standing": "EU #5", "region": "Europe",
               "note": "file 1716 -> live 1848 (+132: TWC day-1-3 results post-date the Oct-5 file)"},
    "falcons": {"points": 1880, "standing": "EU #4", "region": "Europe",
                "note": "file 1843 -> live 1880 (+37)"},
    "betboom": {"points": 1619, "standing": "EU #8", "region": "Europe",
                "note": "file 1596 -> live 1619 (+23)"},
    "legacy": {"points": 1759, "standing": "AM #2", "region": "Americas",
               "note": "file 1931 -> live 1759 (-172: TWC group exit + 128-day decay of older results); roster arT, dumau, latto, n1ssim, try"},
    "9z": {"points": 1557, "standing": "AM #4", "region": "Americas",
           "note": "file 1132 -> live 1557 (+425: TWC run - beat Aurora twice); roster max, dgt, meyern, luchov, HUASOPEEK unchanged"},
    "betm": {"points": 1064, "standing": "EU #64", "region": "Europe",
             "note": "file 1149 -> live 1064 (-85); roster Raijin, synyx, z1Nny, executor, bluewh1te unchanged"},
    "justplayers": {"points": 1002, "standing": "EU #78", "region": "Europe",
                    "note": "file 974 -> live 1002 (+28); live roster h1te, sm3t, sstiNiX, wh1teout, Temny Prince confirms the bl1x1->wh1teout onboarding"},
    "ex6666": {"points": 994, "standing": "EU #80", "region": "Europe",
               "note": "Oct-5 file has no ex-6666 row (rename happened Oct 14); lineage is file row #127/923 pt (amster, dENZY, kL1o, rendysky, skcH - 4/5 overlap, dENZY->stefienson). Live roster amster, kL1o, rendysky, skcH, stefienson exact. The per-team HLTV page read 1014 pt; the rendered regional ladder row (used here) reads 994 pt - the ladder is the canonical artifact."},
    "g2ares": {"points": 948, "standing": "EU #92", "region": "Europe",
               "note": "file 913 -> live 948 (+35); roster SHiNE, TMKj, hitori, Junyme, yksjupe unchanged"},
    "wbt": {"points": 1214, "standing": "EU #41", "region": "Europe",
            "note": "file 1201.1 -> live 1214 (+13); roster Psycho, Smash, s4ltovsk1yy, DemQQ, tyr1k exact - re-confirms WROTBERRY=WBT"},
    "havu": {"points": 987, "standing": "EU #82", "region": "Europe",
             "note": "file 872 -> live 987 (+115); roster uli, Alxc, p3kko, ottob, 8Juho8"},
    "eternalfire": {"points": 1365, "standing": "EU #30", "region": "Europe",
                    "note": "file 1245 -> live 1365 (+120)"},
    "nucleartigeres": {"points": 1267, "standing": "EU #35", "region": "Europe",
                       "note": "live read supersedes the Oct-5 file row"},
    "ninjasinpyjamas": {"points": 1511, "standing": "EU #12", "region": "Europe",
                        "note": "file 1596 -> live 1511 (-85)"},
    "heroic": {"points": 1545, "standing": "EU #10", "region": "Europe",
               "note": "file 1551 -> live 1545 (-6)"},
    "blackphoenix": {"points": 1168, "standing": "EU #48", "region": "Europe",
                     "note": "live read supersedes the Oct-5 file row; roster 4X1s, karnez, topo, MRcreed, Salazar"},
    "genone": {"points": 1077, "standing": "EU #60", "region": "Europe",
               "note": "live read supersedes the Oct-5 file row; roster Keoz, Djoko, Brooxsy, Chucky, bL4SEZ"},
    "butterfly": {"points": 1009, "standing": "EU #74", "region": "Europe",
                  "note": "live read supersedes the Oct-5 file row; roster Forester, nitzie, Kurama, k1ssly, ayano"},
    "mibr": {"points": 1562, "standing": "AM #3", "region": "Americas",
             "note": "live read supersedes the Oct-5 file row; roster LNZ, nqz, insani, venomzera, tomaszin"},
    "100thieves": {"points": 1490, "standing": "#14 (listed on the EU regional page)", "region": "Europe",
                   "note": "live read supersedes the Oct-5 file row"},
    "lavked": {"points": 855, "standing": "EU #103", "region": "Europe",
               "note": "file 1239 -> live 855 (-384: 128-day decay of the 2026 peak + the jakekeS/relaxxie swap with ex-RUSTEC); live roster 1NVISIBLEE, azukay, xm1nd, jakekeS, k4nfuz"},
    "sokerorg": {"points": 787, "standing": "EU #118", "region": "Europe",
                 "note": "Sökerorg was UNRATED on the Oct-5 file; the live ladder carries the same team as 'LFO 10' (identity verified: bo3.gg roster Jackinho, Sapec, tvs, flaw, dottie; the Oct-14 CCT Series 11 match is filed as 'FORZE Reload vs LFO 10' on HLTV and 'FORZE Reload vs Sökerorg' on bo3.gg/offstage). Live roster dottie, flaw, Sapec, L00m1 + fifth. This upgrades the fixture model from the Elo fallback to a VRS row."},
    "eyeballers": {"points": 1256, "standing": "EU #37", "region": "Europe",
                   "note": "live read supersedes the Oct-5 file row"},
    "gamerlegion": {"points": 1359, "standing": "EU #31", "region": "Europe",
                    "note": "live read supersedes the Oct-5 file row"},
    "ence": {"points": 1022, "standing": "EU #72", "region": "Europe",
             "note": "live read supersedes the Oct-5 file row; roster HENU, millert, teme, Schwarz, joeski"},
    "phantom": {"points": 1172, "standing": "EU #47", "region": "Europe",
                "note": "live read supersedes the Oct-5 file row"},
    "bushidowildcats": {"points": 966, "standing": "EU #88", "region": "Europe",
                        "note": "file 982 -> live 966 (-16); roster Darendeli, Muk0s, Vej, cadnyx, cacan exact match with the Oct-5 row"},
    "gothic": {"points": 736, "standing": "EU #131", "region": "Europe",
               "note": "file 705 -> live 736 (+31); live roster Get_Jeka, Ryujin, shg, m2, tokyoshi (Raijin and synyx departed to BET-M - 3/5 overlap with the file row, same lineage; the ARCRED row EU#128/742 is the stale pre-departure five)"},
    "betclic": {"points": 1232, "standing": "EU #40", "region": "Europe",
                "note": "file 1333 -> live 1232 (-101); live roster Demho, Prism, ex1st, ultimate, Qlocuu exact match with the verified #45-lineage row; the hades-era row survives on the live ladder as EU#145/708 marked 'old roster'"},
    "nemesis": {"points": 1395, "standing": "EU #27", "region": "Europe",
                "note": "file 1455 -> live 1395 (-60)"},
    "baks": {"points": 1053, "standing": "EU #65", "region": "Europe",
             "note": "file 1073 -> live 1053 (-20); roster Norwi, xdENiSZERA, danistzz, whisper, turbo unchanged"},
    "fireflux": {"points": 954, "standing": "EU #91", "region": "Europe",
                 "note": "live read supersedes the Oct-5 file row; roster Cizzx, Quality, zer0UKY, xEternaLxx, zemix"},
    "bbl": {"points": 1333, "standing": "EU #33", "region": "Europe",
            "note": "live read supersedes the Oct-5 file row"},
    "exrustec": {"points": 1072, "standing": "EU #61", "region": "Europe",
                 "note": "file 1066.4 -> live 1072 (+6); live roster shalfey, Brilliance, bl1x1, relaxxie, youka (glowiing->SPARTA, yiksrezo->CYBERSHOKE, bl1x1 in from Just Players, relaxxie in from Lavked); the EU#95/892 row is the stale Patsi/yiksrezo/jakekeS five, marked 'old roster'"},
    "illyrians": {"points": 900, "standing": "EU #94", "region": "Europe",
                  "note": "file 862 -> live 900 (+38); roster cerber, BledarD, ammar, Lewis, rosoneriii"},
    "bandachuya": {"points": 729, "standing": "EU #135", "region": "Europe",
                   "note": "file 801 -> live 729 (-72); roster tomiko, maaryy, AdrieN, ezox, Showk exact match with the Oct-5 row"},
    "enjoy": {"points": 811, "standing": "EU #113", "region": "Europe",
              "note": "file 871 -> live 811 (-60); live roster kurosa, sh1geo, reyoz, nbl, flawix (roxesz and zazzer departed - 3/5 overlap, same lineage)"},
    "forzereload": {"points": 1099, "standing": "EU #59", "region": "Europe",
                    "note": "file 1081 -> live 1099 (+18); roster Lack1, YumsaN, Kaide, KusMe, HeCkBNk"},
    "infinite": {"points": 1173, "standing": "EU #46", "region": "Europe",
                 "note": "file 1259 -> live 1173 (-86); roster kreaz, Blytz, kyuubii, volt, sl3nd unchanged"},
    "aimclub": {"points": 1102, "standing": "EU #58", "region": "Europe",
                "note": "file 1113 -> live 1102 (-11); live roster zewts, ragga, mhN1, ERSIN, waZz confirms the ERSIN->XELLOW onboarding is still bedding in on the ladder"},
    "basementboys": {"points": 1002, "standing": "EU #77", "region": "Europe",
                     "note": "file 948 -> live 1002 (+54); roster kr1vda, OWNER, kAlash, Tr0ublE, maggent"},
    "bcgame": {"points": 1304, "standing": "AS #1", "region": "Asia",
               "note": "live read supersedes the Oct-5 file row; roster s1mple, Magisk, asap, Senzu, mzinho"},
    "drama": {"points": 810, "standing": "EU #114", "region": "Europe",
              "note": "live read supersedes the Oct-5 file row; roster andr1x, DEPRESHN, Chill, choiv7, Goody"},
    "nexus": {"points": 1050, "standing": "EU #67", "region": "Europe",
              "note": "file 967 -> live 1050 (+83); roster shield, fNk, s0und, Nexius, HOLY"},
    "iberiansoul": {"points": 1200, "standing": "EU #42", "region": "Europe",
                    "note": "live read supersedes the Oct-5 file row"},
    "hyperspirit": {"points": 805, "standing": "EU #115", "region": "Europe",
                    "note": "live read supersedes the Oct-5 file row; roster Ciocardau, Q-Q, d1maje, starplajerz, Scr0b"},
    "sashi": {"points": 1042, "standing": "EU #68", "region": "Europe",
              "note": "file 1240 -> live 1042 (-198); live roster acoR, Cabbi, Zyphon, Anlelele, MistR (Beccie departed); the EU#127/744 row is the stale Beccie five, marked 'old roster'"},
    "mouznxt": {"points": 878, "standing": "EU #98", "region": "Europe",
                "note": "file 877 -> live 878 (+1); roster deeN, ay0k, Nikodeon, eSx, mixer exact match (opdust benched)"},
    "astral": {"points": 991, "standing": "EU #81", "region": "Europe",
               "note": "file 1072 -> live 991 (-81); roster gxx-, swiz, RaY5ive, Neqy, meowpop exact match"},
    "leo": {"points": 969, "standing": "EU #86", "region": "Europe",
            "note": "file 1001 -> live 969 (-32); roster drac, leen, next1me, Tarkky, aimy exact match with the verified #112-lineage row"},
    "lynnvision": {"points": 1143, "standing": "AS #7", "region": "Asia",
                   "note": "live read supersedes the Oct-5 file row; roster Westmelon, z4KR, Starry, EmiliaQAQ, C4LLM3SU3"},
    "rareatom": {"points": 818, "standing": "AS #17", "region": "Asia",
                 "note": "live read supersedes the Oct-5 file row; roster Summer, kaze, ChildKing, L1haNg, 3gl"},
    "alterego": {"points": 875, "standing": "AS #13", "region": "Asia",
                 "note": "live read supersedes the Oct-5 file row; roster PokemoN, shadiy, adeX, laxiee, Bloody"},
    "chinggiswarriors": {"points": 1200, "standing": "AS #5", "region": "Asia",
                         "note": "file 1084 -> live 1200 (+116: TWC group-stage points); live roster sk0R, ROUX, cool4st, fury5k, tikuak (yAmi->tikuak onboarding; tikuak is dual-listed with The MongolZ on the live ladder - loan in progress)"},
    "nexvoid": {"points": 1049, "standing": "AS #8", "region": "Asia",
                "note": "live read supersedes the Oct-5 file row; roster erkaSt, xerolte, MiQ, AccuracyTG, Zesta"},
    "vitalemaerem": {"points": 711, "standing": "AS #21", "region": "Asia",
                     "note": "live read supersedes the Oct-5 file row; roster lan, B1NGO, Roninbaby, BZA, rain"},
    "wildcard": {"points": 1332, "standing": "AM #8", "region": "Americas",
                 "note": "file 1239 -> live 1332 (+93); roster nEMANHA, Cxzi, reck, HexT, fr3nd exact match (fr3nd now full-time here after the Betclic stand-in spell)"},
    "dendele": {"points": 1355, "standing": "AM #7", "region": "Americas",
                "note": "file 1368 -> live 1355 (-13); roster gafolo, koala, maxxkor, rdnzao, doc exact match with the Oct-5 row"},
    "phantomacademy": {"points": 758, "standing": "EU #123", "region": "Europe",
                       "note": "file 783 -> live 758 (-25); roster Brain47, Ayteel, kalyambys, Dr3nquu, stefienson exact match with the Oct-5 row"},
}
LIVE_VRS_URL = {
    "Europe": "https://www.hltv.org/valve-ranking/teams/2026/october/16/region/Europe",
    "Americas": "https://www.hltv.org/valve-ranking/teams/2026/october/16/region/Americas",
    "Asia": "https://www.hltv.org/valve-ranking/teams/2026/october/16/region/Asia",
}

# --------------------------------------------------------------------------- VRS rating table
def build_vrs_table():
    """canonical key -> rating row (with join audit), applying live overrides.

    Duplicate-name rule (verified this session against all 31 duplicate keys in
    the Oct-5 file AND the live Oct-16 ladder, which repeats the same pattern):
    the MAIN roster always carries the LOWEST standing number; the higher-standing
    row is the academy/stale lineage. Default pick = min(standing), with
    FIXTURE_VRS_PICKS documenting the roster-evidence check where it matters.
    """
    table = {}
    for key, rows in vrs_file["teams"].items():
        row = min(rows, key=lambda r: r["standing"]) if len(rows) > 1 else rows[0]
        table[key] = {
            "key": key, "points": row["points"], "standing": row["standing"],
            "roster": row["roster"], "raw_name": row["raw_name"],
            "details_url": row["details_url"], "ambiguous": len(rows) > 1,
            "rejected_rows": ([{ "standing": r["standing"], "points": r["points"],
                                  "roster": r["roster"]} for r in rows if r is not row]
                              if len(rows) > 1 else []),
            "source": "Valve VRS global ladder 2026-10-05 (retained copy)",
        }
    # Live Oct-16 overrides: replace points (and standing label) with the fresh
    # regional-ladder read; the file row stays in the audit trail.
    for key, ov in LIVE_VRS_OVERRIDES.items():
        base = table.get(key)
        table[key] = {
            "key": key, "points": float(ov["points"]), "standing": ov["standing"],
            "roster": base["roster"] if base else None,
            "raw_name": (base or {}).get("raw_name", key),
            "details_url": LIVE_VRS_URL[ov["region"]],
            "ambiguous": False,
            "rejected_rows": (base or {}).get("rejected_rows", []),
            "source": f"HLTV live Valve-ranking read 2026-10-16 ({ov['region']} regional ladder)",
            "live_override": True,
            "file_points": (base or {}).get("points"),
            "live_note": ov["note"],
        }
    return table


VRS = build_vrs_table()

# Documented fixture-specific disambiguations (roster evidence beats name match).
# Each entry pins the Oct-5 file row for a team whose name carries duplicates;
# the live override (where present) then refreshes the points on that lineage.
FIXTURE_VRS_PICKS = {
    # Chinggis Warriors carry two Valve rows (#87 1084 pt current five; #220 685 pt
    # older five). The egamersworld lineup for fixture 1081863 (sk0R, cool4st, ROUX,
    # fury5k, tikuak) overlaps row #87 on 4/5 and row #220 on 2/5 -> #87 is correct.
    "chinggiswarriors": {"standing": 87, "points": 1084.0,
                         "roster": ["cool4st", "fury5k", "ROUX", "sk0R", "yAmi"],
                         "rule": "roster overlap 4/5 with the verified egamersworld lineup (sk0R, cool4st, ROUX, fury5k, tikuak); row #220 (Aceari, hasteka five) rejected"},
    # ex-RUSTEC carry two Valve rows (#92 1066.4 pt active lineage; #152 823.9 pt stale,
    # last match 2026-08-17). The current bo3.gg five (Brilliance, shalfey, bl1x1,
    # youka, relaxxie) overlaps #92 on 3/5 and #152 on 3/5 -> tie broken by recency of
    # row activity and the live HLTV rank (#86 next to file #92).
    "exrustec": {"standing": 92, "points": 1066.4,
                 "roster": ["Brilliance", "glowiing", "shalfey", "yiksrezo", "youka"],
                 "rule": "tie on 3/5 roster overlap broken by row recency (#92 last played 2026-09-27 vs #152 last played 2026-08-17) and the live HLTV VRS rank #86 sitting next to file rank #92; two onboardings since the snapshot flagged"},
    # Betclic: file rows #45/1333 (Demho, ex1st, Prism, Qlocuu, ultimate) and
    # #183/765 (Demho, Dr3nquu, eskyy, hades, Prism - the pre-August hades era).
    # HLTV team/12916 starters (Prism 2y2m, Demho 1y10m, ex1st/Qlocuu/ultimate
    # 2 months each) match #45 exactly; HLTV news 45273 + cs2news (Aug 11-12):
    # ultimate replaced hades; Jul 22: the KOLESIE quartet signing inherited
    # KOLESIE's VRS position. The live Oct-16 ladder confirms the split: main row
    # EU#40/1232 carries the current five, the hades-era row survives as EU#145/708
    # marked 'old roster'. fe803b80's board joined #183 (max-standing default) -
    # that error manufactured a -690 pt delta and poisoned its calibration.
    "betclic": {"standing": 45, "points": 1333.0,
                "roster": ["Demho", "ex1st", "Prism", "Qlocuu", "ultimate"],
                "rule": "HLTV team/12916 starters match row #45 on 5/5 (ultimate replaced hades Aug 11; the quartet inherited KOLESIE's VRS position Jul 22); row #183 is the pre-Aug hades era - confirmed stale by the live Oct-16 ladder (main row EU#40/1232 current five; hades-era row EU#145/708 'old roster')"},
    # aimclub: file rows #77/1113 (XELLOW, ragga, zewts, mhN1, waZz) and a
    # higher-standing stale row. bo3.gg/teams/aimclub current five XELLOW, ragga,
    # zewts, mhN1, waZz overlaps #77 on 4/5 (ERSIN->XELLOW onboarding); recent
    # W 2-1 ARGOS, W 1-0 at ENCE. Live ladder EU#58/1102 still lists ERSIN
    # (XELLOW bedding in) - same lineage.
    "aimclub": {"standing": 77, "points": 1113.0,
                "roster": ["XELLOW", "ragga", "zewts", "mhN1", "waZz"],
                "rule": "bo3.gg current five overlaps row #77 on 4/5 (ERSIN->XELLOW); recent W 2-1 ARGOS (Oct 11), W 1-0 at ENCE (Oct 10); live ladder EU#58/1102 same lineage"},
    # Just Players: file rows #118/974 (h1te, sstiNiX, sm3t, bl1x1, Temny Prince)
    # and a higher-standing stale row. bo3.gg current five h1te, sstiNiX, sm3t,
    # wh1teout, Temny Prince overlaps #118 on 4/5 (bl1x1 departed to ex-RUSTEC,
    # wh1teout onboarded); recent L 0-2 ex-Zero Tenacity (Oct 15), L 0-2 FOKUS
    # (Oct 14). Live ladder EU#78/1002 carries the wh1teout five.
    "justplayers": {"standing": 118, "points": 974.0,
                    "roster": ["h1te", "sstiNiX", "sm3t", "bl1x1", "Temny Prince"],
                    "rule": "bo3.gg current five overlaps row #118 on 4/5 (bl1x1->wh1teout drift, bl1x1 now at ex-RUSTEC); live ladder EU#78/1002 lists the wh1teout five"},
    # Bebop: file rows #212/702 (iDISBALANCE, faydett, KENSI, Pipw, redzed) and
    # #282/597 (danistzz, faydett, iDISBALANCE, lov1kus, Norwi - the pre-split
    # five; danistzz and Norwi now anchor BAKS, lov1kus is at PsychoFace).
    # bo3.gg current five matches #212 exactly; recent L 0-2 mellren, L 0-2 6666,
    # W 2-1 at mellren (slide).
    "bebop": {"standing": 212, "points": 702.0,
              "roster": ["iDISBALANCE", "faydett", "KENSI", "Pipw", "redzed"],
              "rule": "bo3.gg current five matches row #212 exactly; row #282's danistzz/Norwi/lov1kus era is dissolved (BAKS/PsychoFace); live ladder has no Bebop row above EU#145, consistent with the slide"},
    # Banda Chuya: file rows #165/801 (AdrieN, ezox, maaryy, Showk, tomiko) and
    # #373/402 (ezox, manio - a 2-player stub). ingame-stats five matches #165
    # exactly; alt org name 'Banda LFO'. Recent W 1-0 regnum4games (Oct 8),
    # L 0-2 benched gods, L 0-2 FORZE Reload. Live ladder EU#135/729 same five.
    "bandachuya": {"standing": 165, "points": 801.0,
                   "roster": ["AdrieN", "ezox", "maaryy", "Showk", "tomiko"],
                   "rule": "ingame-stats five matches row #165 exactly (alt org name 'Banda LFO'); row #373 is a 2-player stub; live ladder EU#135/729 lists the same five"},
    # mouz NXT: file rows #137/877 (Ay0k, deeN, eSx, Nikodeon, mixer) and a
    # higher-standing academy stub carrying Flierax (who is live at Inner Circle
    # Academy). bo3.gg current five matches #137 exactly (opdust benched); recent
    # W FF at Sökerorg, W 2-0 ROUNDS, W 2-0 SINQU REHTI, L 1-2 Saint Sinners,
    # W 2-1 HYPERSPIRIT, L 1-2 at Leo. Live ladder EU#98/878 same five.
    "mouznxt": {"standing": 137, "points": 877.0,
                "roster": ["Ay0k", "deeN", "eSx", "Nikodeon", "mixer"],
                "rule": "bo3.gg current five matches row #137 exactly (opdust benched); the higher-standing duplicate carries Flierax, live at Inner Circle Academy; live ladder EU#98/878 same five"},
    # Leo: file rows #112/1001 (drac, leen, next1me, Tarkky, aimy) and #340
    # (holds ex-6666 players amster/kL1o - stale academy lineage). The known
    # Leo five matches #112 exactly. Live ladder EU#86/969 carries the same five.
    "leo": {"standing": 112, "points": 1001.0,
            "roster": ["drac", "leen", "next1me", "Tarkky", "aimy"],
            "rule": "known Leo five matches row #112 exactly; row #340 holds ex-6666 players amster/kL1o = stale academy lineage; live ladder EU#86/969 same five"},
}


def vrs_rating_for(key: str, lineup: list[str] | None = None):
    """Return (rating_row, join_note) for a canonical key, or (None, None)."""
    if key in FIXTURE_VRS_PICKS:
        pick = FIXTURE_VRS_PICKS[key]
        base = VRS.get(key)
        row = {**base, "standing": pick["standing"], "points": pick["points"],
               "roster": pick["roster"], "join_rule": pick["rule"],
               "disambiguated": True} if base else {
            "key": key, "points": pick["points"], "standing": pick["standing"],
            "roster": pick["roster"], "raw_name": key, "ambiguous": True,
            "join_rule": pick["rule"], "disambiguated": True,
            "source": "Valve VRS global ladder 2026-10-05 (retained copy)",
            "details_url": "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standards_global_2026_10_05.md",
            "rejected_rows": []}
        # The pick pins the LINEAGE (which Valve row is the current roster);
        # a live Oct-16 override then refreshes the POINTS on that lineage.
        live = LIVE_VRS_OVERRIDES.get(key)
        if live:
            row.update({"points": float(live["points"]), "standing": live["standing"],
                        "source": "HLTV live Valve-ranking read 2026-10-16; lineage pinned by fixture pick",
                        "details_url": LIVE_VRS_URL[live["region"]],
                        "live_override": True, "file_points": pick["points"],
                        "live_note": live["note"]})
        return row, pick["rule"]
    row = VRS.get(key)
    if row:
        note = row.get("source", "")
        if row.get("ambiguous"):
            note += " (duplicate name in Valve file; main roster = lowest-standing row, verified against the live Oct-16 ladder)"
        return row, note
    return None, None


# --------------------------------------------------------------------------- Elo (adopted, re-run)
def build_elo():
    teams = snapshot["bo3gg"]["teams"]
    history = snapshot["bo3gg_history"]
    matches, seen = [], set()
    for team_id, entries in history.items():
        for m in entries:
            mid = m.get("id")
            if mid in seen:
                continue
            seen.add(mid)
            t1 = str(teams.get(str(m.get("team1_id")), {}).get("name") or "")
            t2 = str(teams.get(str(m.get("team2_id")), {}).get("name") or "")
            winner = m.get("winner_team_id")
            ka, kb = canon(t1)[0], canon(t2)[0]
            if not ka or not kb or ka == kb:
                continue
            w = "a" if str(winner) == str(m.get("team1_id")) else "b"
            matches.append({"key_a": ka, "key_b": kb, "winner": w,
                            "start_utc": m.get("start_date"), "match_id": mid})
    seeds = {}
    for key, row in VRS.items():
        seeds[key] = row["points"]
    ratings = elo_run(matches, seed=seeds, k=ELO_K, passes=ELO_PASSES)
    return {"ratings": ratings, "n_matches": len(matches),
            "n_history_teams": len(history), "n_seeded": len(seeds),
            "params": {"base": ELO_BASE, "k": ELO_K, "passes": ELO_PASSES,
                       "anchor": "Valve VRS points, re-anchored every pass"},
            "source": "retained bo3.gg match history (data/fe803b80/snapshot.json bo3gg_history), 950-match list"}


ELO = build_elo()

# --------------------------------------------------------------------------- quotes
def fresh_quote(q: dict) -> dict:
    """Research-ledger quote -> board quote record."""
    da, db = float(q["decimal_a"]), float(q["decimal_b"])
    pa, pb = devig(da, db)
    return {"source_key": q["source_key"], "source_name": q["source_key"],
            "decimal_a": da, "decimal_b": db, "prob_a": round(pa, 6),
            "retrieved_utc": q["read_utc"], "public_url": q["url"],
            "note": q.get("note", "")}


def collect_quotes(fixture_id: str, team_a: str, team_b: str, start_utc: str):
    """Join retained snapshot quotes + this session's fresh quotes to a fixture.

    Dedupe rule: when the same source published the same two-sided price in
    the fe803b80 snapshot AND this session's fresh read, the fresh record
    wins (it carries the later retrieved_utc) and is annotated as a
    confirmed-unchanged price; the stale snapshot copy is dropped.
    """
    ka, ka_alias, ka_note = canon(team_a)
    kb, kb_alias, kb_note = canon(team_b)
    quotes, aliases_used, rejections = [], [], []

    def retained_records():
        """Retained external quotes (read 2026-10-17T00:19-00:22Z by fe803b80)."""
        out, keys = [], set()
        for q in snapshot["quotes"]:
            qka, qkb = canon(q.get("team_a"))[0], canon(q.get("team_b"))[0]
            if {qka, qkb} != {ka, kb}:
                continue
            if q.get("start_utc") and start_utc:
                try:
                    qs = datetime.fromisoformat(q["start_utc"].replace("Z", "+00:00"))
                    fs = datetime.fromisoformat(start_utc.replace("Z", "+00:00"))
                    if abs((qs - fs).total_seconds()) > 3 * 3600:
                        continue
                except ValueError:
                    continue
            da, db = q.get("decimal_a"), q.get("decimal_b")
            if not (isinstance(da, (int, float)) and isinstance(db, (int, float))
                    and da > 1.0 and db > 1.0):
                rejections.append({"source_key": q["source_key"], "reason": "non-two-sided price"})
                continue
            overround = 1.0 / da + 1.0 / db - 1.0
            if q["source_key"] == "kalshi" and abs(1.0 / da - 1.0 / db) > 0.10:
                rejections.append({"source_key": q["source_key"], "reason": "wide bid/ask seed (KALSHI_MAX_SPREAD)"})
                continue
            if overround > 0.30:
                rejections.append({"source_key": q["source_key"], "reason": f"overround {overround:.2f} > 0.30 (untrained seed)"})
                continue
            # Map the source's team order onto the fixture's (HotSpawn) order.
            swapped = qka == kb and qkb == ka
            if swapped:
                da, db = db, da
            pa, pb = devig(da, db)
            rec = {"source_key": q["source_key"], "source_name": q.get("source_name", q["source_key"]),
                   "decimal_a": da, "decimal_b": db, "prob_a": round(pa, 6),
                   "retrieved_utc": q.get("retrieved_utc"), "public_url": q.get("public_url"),
                   "retained_from": "fe803b80 snapshot"}
            if swapped:
                rec["note"] = "source lists the teams home/away swapped; prices mapped to HotSpawn order"
            out.append(rec)
            keys.add((q["source_key"], round(da, 2), round(db, 2)))
        return out, keys

    retained, retained_keys = retained_records()

    # This session's fresh quotes (read 2026-10-17T00:52-01:10Z).
    fresh = []
    for section in research["semifinal_lines_fresh"].values():
        if isinstance(section, dict) and str(section.get("fixture_id")) == str(fixture_id):
            fresh.extend(section["quotes"])
    if str(fixture_id) == "1081515":
        fresh.append({"source_key": "polymarket", "decimal_a": 100 / 29.0, "decimal_b": 100 / 72.0,
                      "read_utc": "2026-10-17T01:00:00Z",
                      "url": "https://polymarket.com/esports/cs2/pgl/cs2-bca-nem-2026-10-17",
                      "note": "series moneyline 29c/72c, $75.45 volume (thin but trained; the $0.00-volume seed captured 2026-10-16T20:45Z was rejected as untrained)"})
    fresh_records, fresh_keys = [], set()
    for q in fresh:
        da, db = float(q["decimal_a"]), float(q["decimal_b"])
        if q["source_key"] == "egamersworld" and (round(da, 2), round(db, 2)) == EGW_PLACEHOLDER:
            rejections.append({"source_key": q["source_key"],
                               "reason": "untrained 1.80/1.80 placeholder (zero vote count, no volume)"})
            continue
        rec = fresh_quote(q) | {"retained_from": "c32f1b93 fresh read"}
        key = (q["source_key"], round(da, 2), round(db, 2))
        fresh_keys.add(key)
        if key in retained_keys:
            rec["retained_from"] = "fe803b80 snapshot, re-confirmed by c32f1b93 fresh read"
            rec["note"] = (rec.get("note", "") + " | price unchanged since the fe803b80 snapshot read; fresh re-read confirms").strip(" |")
        fresh_records.append(rec)
    quotes = fresh_records + [r for r in retained if
                              (r["source_key"], round(r["decimal_a"], 2), round(r["decimal_b"], 2)) not in fresh_keys]
    for entry in (ka_alias, kb_alias):
        if entry and entry not in aliases_used:
            aliases_used.append(entry)
    return quotes, aliases_used, rejections, (ka_note, kb_note)


# --------------------------------------------------------------------------- fixtures
def load_fixtures():
    # Open = scheduled AND not yet started at the retained capture moment
    # (the snapshot's generated_utc; the same inventory this session's fresh
    # lobby render at 2026-10-17T00:52Z cross-checks).
    cutoff = datetime.fromisoformat(
        str(snapshot["generated_utc"]).replace("Z", "+00:00"))
    open_rows = []
    for f in snapshot["hotspawn"]["fixtures"]:
        try:
            start = datetime.fromisoformat(str(f["start_utc"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if start <= cutoff:
            continue
        status = f.get("status")
        placeholder = False
        if status == "scheduled":
            pass
        elif status == "started" and start > cutoff + timedelta(hours=48):
            # HotSpawn placeholder quirk: a far-future fixture (1080200,
            # Wildcard vs DENDELE, 2026-11-12) is carried with status
            # 'started' although kickoff is 26 days after the capture. A
            # match cannot legitimately be in progress before it starts,
            # so we keep it and flag it.
            placeholder = True
        else:
            continue
        row = {
            "fixture_id": str(f["fixture_id"]),
            "competition": f.get("competition"),
            "tier": f.get("tier"),
            "stage": f.get("stage"),
            "best_of": f.get("best_of"),
            "start_utc": f.get("start_utc"),
            "lock_utc": f.get("lock_utc"),
            "team_a": f.get("team_a"), "team_b": f.get("team_b"),
            "hotspawn_url": snapshot["hotspawn"]["permalinks"].get(str(f["fixture_id"])),
            "points": f.get("points"), "offered_points": f.get("offered_points"),
        }
        if placeholder:
            row["placeholder_scheduling"] = True
        open_rows.append(row)
    open_rows.sort(key=lambda r: (r["start_utc"] or "", r["fixture_id"]))
    return open_rows


FIXTURES = load_fixtures()


def crowd_for(fixture_id: str, team_a: str, team_b: str):
    """Crowd context by fixture id, falling back to a matchup-keyed index.

    The retained crowd ledger mixes two fixture-id namespaces (the HotSpawn
    lobby render and the API inventory number the same matchup differently),
    so exact-id lookup alone silently drops ~15 of 23 entries. The fallback
    indexes every ledger row by its canonical team pair; team order is
    verified so crowd_a/crowd_b always map onto the fixture's team_a/team_b.
    """
    row = crowd_ctx["fresh"].get(fixture_id) or crowd_ctx["retained_2026_10_16T20_50Z"].get(fixture_id)
    if row:
        return {**row, "read_utc": (crowd_ctx["fresh_read_utc"] if fixture_id in crowd_ctx["fresh"]
                                    else "2026-10-16T20:50:00Z (retained)"),
                "role": "context only - sentiment, never a price"}
    ka, _, _ = canon(team_a)
    kb, _, _ = canon(team_b)
    if not (ka and kb) or ka == kb:
        return None
    hit = CROWD_BY_MATCHUP.get(frozenset((ka, kb)))
    if not hit:
        return None
    ledger_fid, ledger_row, ledger_ka, ledger_kb = hit
    out = dict(ledger_row)
    if ledger_ka == kb and ledger_kb == ka:
        out["crowd_a"], out["crowd_b"] = out["crowd_b"], out["crowd_a"]
    out["matchup_mapped_from_ledger_fixture_id"] = ledger_fid
    out["read_utc"] = ("2026-10-16T20:50:00Z (retained)" if ledger_fid in crowd_ctx["retained_2026_10_16T20_50Z"]
                       else crowd_ctx["fresh_read_utc"])
    out["role"] = "context only - sentiment, never a price"
    return out


# Matchup-keyed crowd index (canonical team pair -> ledger row).
CROWD_BY_MATCHUP = {}
for _sec_name in ("fresh", "retained_2026_10_16T20_50Z"):
    for _fid, _row in crowd_ctx.get(_sec_name, {}).items():
        _ka, _, _ = canon(_row.get("team_a"))
        _kb, _, _ = canon(_row.get("team_b"))
        if _ka and _kb and _ka != _kb:
            CROWD_BY_MATCHUP[frozenset((_ka, _kb))] = (_fid, _row, _ka, _kb)


# --------------------------------------------------------------------------- row builder
_MATCH_URL_HINTS = ("bo3.gg/matches/", "/match/", "hltv.org/matches/")


def fixture_url_for(fid: str, f: dict, quotes: list, twc: dict | None) -> str | None:
    """Best verified link back to the fixture's primary listing.

    HotSpawn permalinks were captured for only 10 of the 227 snapshot rows, so
    most fixtures fall through to a verified match-page URL from this row's own
    evidence (bo3.gg / egamersworld / HLTV match pages), or the HLTV playoff
    bracket page for the TWC semis. URLs are never constructed - only retained
    evidence is linked.
    """
    if f.get("hotspawn_url"):
        return f["hotspawn_url"]
    bracket = research["results"].get("playoff_bracket", {})
    for entry in bracket.values():
        if isinstance(entry, dict) and entry.get("url"):
            teams = {canon(t)[0] for t in entry.get("teams", [])}
            mine = {canon(f["team_a"])[0], canon(f["team_b"])[0]}
            if teams == mine:
                return entry["url"]
    for q in quotes:
        url = q.get("public_url") or ""
        if any(h in url for h in _MATCH_URL_HINTS):
            return url
    # This session's hand-verified form notes carry the bo3.gg match page
    # for every fixture they cover (keyed '<fixture_id>_<matchup>').
    for key, entry in research["form_notes"].items():
        if key.startswith(str(fid) + "_") and isinstance(entry, dict) and entry.get("url"):
            return entry["url"]
    if twc and twc.get("lineups", {}).get("source"):
        return twc["lineups"]["source"]
    for s in sorted({q.get("public_url", "") for q in quotes}):
        if s:
            return s
    return None


def build_row(f: dict, calibration: dict) -> dict:
    fid = f["fixture_id"]
    quotes, aliases_used, rejections, alias_notes = collect_quotes(
        fid, f["team_a"], f["team_b"], f["start_utc"])
    ka, _, _ = canon(f["team_a"])
    kb, _, _ = canon(f["team_b"])

    # -- market: median of per-source no-vig probabilities (our disclosed rule)
    market = None
    if quotes:
        pas = [q["prob_a"] for q in quotes]
        market = {"prob_a": round(statistics.median(pas), 6),
                  "prob_b": round(1.0 - statistics.median(pas), 6),
                  "n_sources": len(quotes),
                  "sources": sorted({q["source_key"] for q in quotes}),
                  "spread_a": round(max(pas) - min(pas), 6) if len(pas) > 1 else None,
                  "rule": "median of per-source no-vig probabilities"}

    # -- model: Valve VRS ladder first, adopted Elo as fallback
    ra, note_a = vrs_rating_for(ka, lineup_for(fid, "a"))
    rb, note_b = vrs_rating_for(kb, lineup_for(fid, "b"))
    model, flags = None, []
    if ra and rb:
        prob_a = vrs_prob(ra["points"], rb["points"], calibration["k"])
        model = {"basis": "valve_vrs", "prob_a": round(prob_a, 6),
                 "vrs": {"points_a": ra["points"], "points_b": rb["points"],
                         "standing_a": ra["standing"], "standing_b": rb["standing"],
                         "vrs_name_a": ra["raw_name"], "vrs_name_b": rb["raw_name"],
                         "delta": round(ra["points"] - rb["points"], 1),
                         "k": calibration["k"], "rd": VALVE_RD,
                         "join_a": note_a, "join_b": note_b}}
    else:
        ea, eb = ELO["ratings"].get(ka), ELO["ratings"].get(kb)
        if ea is not None and eb is not None:
            prob_a = elo_expected(ea, eb)
            model = {"basis": "originated_elo", "prob_a": round(prob_a, 6),
                     "elo": {"rating_a": round(ea, 1), "rating_b": round(eb, 1),
                             "anchored_a": ka in VRS, "anchored_b": kb in VRS,
                             **ELO["params"], "n_matches": ELO["n_matches"]}}
        elif ra or rb:
            # one side rated, the other derivable on the Elo scale only
            ea = ELO["ratings"].get(ka)
            eb = ELO["ratings"].get(kb)
            if ea is not None and eb is not None:
                prob_a = elo_expected(ea, eb)
                model = {"basis": "originated_elo_mixed", "prob_a": round(prob_a, 6),
                         "elo": {"rating_a": round(ea, 1), "rating_b": round(eb, 1),
                                 "anchored_a": ka in VRS, "anchored_b": kb in VRS,
                                 **ELO["params"], "n_matches": ELO["n_matches"],
                                 "note": "one side carries a Valve VRS rating (Elo-anchored), the other is Elo-only"},
                         "vrs_side": ka if ka in VRS else kb}
    if ra and rb and model and model["basis"] == "valve_vrs":
        if ra.get("live_override") or rb.get("live_override"):
            flags.append("live_vrs_override")
        if ra.get("disambiguated") or rb.get("disambiguated"):
            flags.append("vrs_row_disambiguated")
        if FIXTURE_VRS_PICKS.get(ka) or FIXTURE_VRS_PICKS.get(kb):
            flags.append("stale_row_corrected")

    # -- published line
    line = None
    if market and model:
        pa = BLEND_MARKET_WEIGHT * market["prob_a"] + (1 - BLEND_MARKET_WEIGHT) * model["prob_a"]
        line = {"prob_a": round(pa, 6), "prob_b": round(1 - pa, 6), "pick": None,
                "basis": "market+model", "market_weight": BLEND_MARKET_WEIGHT}
        if abs(market["prob_a"] - model["prob_a"]) >= 0.10:
            flags.append("market_model_divergence")
    elif market:
        line = {"prob_a": market["prob_a"], "prob_b": market["prob_b"], "pick": None,
                "basis": "market", "market_weight": 1.0}
    elif model:
        line = {"prob_a": model["prob_a"], "prob_b": round(1.0 - model["prob_a"], 6),
                "pick": None, "basis": "model", "market_weight": 0.0}
    if line:
        line["pick"] = f["team_a"] if line["prob_a"] >= 0.5 else f["team_b"]
        line["pick_probability"] = max(line["prob_a"], line["prob_b"])
        if market and len(market["sources"]) == 1:
            flags.append("single_source")
    else:
        flags.append("no_derived_line")

    # -- crowd context + contrarian screen (never a price)
    crowd = crowd_for(fid, f["team_a"], f["team_b"])
    if crowd and line:
        our_side = "a" if line["pick"] == f["team_a"] else "b"
        crowd_ours = crowd["crowd_a"] if our_side == "a" else crowd["crowd_b"]
        gap = abs((line["pick_probability"] * 100) - crowd_ours)
        if gap >= 15:
            flags.append("crowd_divergence")

    # -- enrichment, roles, per-fixture flags
    twc = None
    if fid == "1080207":
        twc = research["semifinal_lines_fresh"]["sf1_furia_aurora"]
        flags.append("twc_semifinal")
    elif fid == "1080208":
        twc = research["semifinal_lines_fresh"]["sf2_falcons_betboom"]
        flags.append("twc_semifinal")
    if f.get("placeholder_scheduling"):
        flags.append("placeholder_scheduling")
    if fid == "1081515":
        flags += ["freshly_priced_this_session", "thin_volume"]
    if fid == "1081863":
        flags += ["unrated_opponent", "no_published_price", "policy_blank"]
    if fid in ("1079633", "1081521"):
        flags.append("live_vrs_override")
    if fid == "1079638":
        flags += ["stale_row_corrected", "roster_drift", "form_conflict_note"]
    if fid == "1079634":
        flags += ["roster_drift", "form_conflict"]
    if fid == "1079635":
        flags.append("form_conflict")
    if fid == "1080200":
        flags.append("far_future_scheduling")
    if aliases_used:
        flags.append("alias_applied")
    try:
        lock = datetime.fromisoformat((f["lock_utc"] or "").replace("Z", "+00:00"))
        now = datetime.fromisoformat(BUILD_UTC.replace("Z", "+00:00"))
        if lock and (lock - now).total_seconds() < 3 * 3600:
            flags.append("closing_soon")
    except ValueError:
        pass

    role = None
    if line:
        p = line["pick_probability"]
        crowd_ours = None
        if crowd:
            our_side = "a" if line["pick"] == f["team_a"] else "b"
            crowd_ours = crowd["crowd_a"] if our_side == "a" else crowd["crowd_b"]
        if crowd_ours is not None and crowd_ours <= 40 and p >= 0.55:
            backer = ("market price and model" if line["basis"] == "market+model"
                      else line["basis"])
            role = f"climb (contrarian: crowd owns the other side, {backer} backs this pick)"
        elif crowd_ours is not None and crowd_ours >= 75:
            role = "safe (crowd-aligned; ownership inflated - treat as sentiment)"
        elif p >= 0.62:
            role = "safe"
        elif p >= 0.55:
            role = "lean"
        else:
            role = "toss-up"

    return {
        "fixture_id": fid, "competition": f["competition"], "tier": f["tier"],
        "stage": f["stage"], "best_of": f["best_of"],
        "start_utc": f["start_utc"], "lock_utc": f["lock_utc"],
        "team_a": f["team_a"], "team_b": f["team_b"],
        "hotspawn_url": f.get("hotspawn_url"),
        "fixture_url": fixture_url_for(fid, f, quotes, twc),
        "points": f["points"],
        "market": market, "quotes": quotes, "quote_rejections": rejections,
        "model": model, "line": line,
        "pick": line["pick"] if line else None,
        "pick_probability": line["pick_probability"] if line else None,
        "confidence": confidence(line["pick_probability"]) if line else "Unresolved",
        "basis": line["basis"] if line else "blank",
        "role": role, "crowd": crowd, "flags": sorted(set(flags)),
        "aliases_applied": aliases_used, "alias_notes": [n for n in alias_notes if n],
        "twc": twc,
        "sources": sorted({q["public_url"] for q in quotes if q.get("public_url")} |
                          ({ra["details_url"], rb["details_url"]} if ra and rb else set()) |
                          ({ra["details_url"]} if ra else set()) |
                          ({rb["details_url"]} if rb else set())),
    }


_LINEUP_CACHE = {}


def lineup_for(fixture_id: str, side: str):
    """Verified starting five from this session's research (TWC semis + CCT pages)."""
    key = (fixture_id, side)
    if key in _LINEUP_CACHE:
        return _LINEUP_CACHE[key]
    lineup = None
    if fixture_id == "1080207":
        lineup = (research["semifinal_lines_fresh"]["sf1_furia_aurora"]["lineups"]["furhia"]
                  if side == "a" else
                  research["semifinal_lines_fresh"]["sf1_furia_aurora"]["lineups"]["aurora"])
    elif fixture_id == "1080208":
        lineup = (research["semifinal_lines_fresh"]["sf2_falcons_betboom"]["lineups"]["falcons"]
                  if side == "a" else
                  research["semifinal_lines_fresh"]["sf2_falcons_betboom"]["lineups"]["betboom"])
    elif fixture_id == "1081863" and side == "a":
        lineup = ["sk0R", "cool4st", "ROUX", "fury5k", "tikuak"]
    _LINEUP_CACHE[key] = lineup
    return lineup


# --------------------------------------------------------------------------- calibration + build
def calibrate():
    """Fit the VRS slope on joined (market + both-side-VRS) pairs, our own fit."""
    pairs = []
    for f in FIXTURES:
        quotes, _, _, _ = collect_quotes(f["fixture_id"], f["team_a"], f["team_b"], f["start_utc"])
        if not quotes:
            continue
        ka, _, _ = canon(f["team_a"])
        kb, _, _ = canon(f["team_b"])
        ra, _ = vrs_rating_for(ka, lineup_for(f["fixture_id"], "a"))
        rb, _ = vrs_rating_for(kb, lineup_for(f["fixture_id"], "b"))
        if not (ra and rb):
            continue
        pas = [q["prob_a"] for q in quotes]
        pairs.append({"fixture_id": f["fixture_id"],
                      "delta": ra["points"] - rb["points"],
                      "market_prob_a": statistics.median(pas)})
    fit = fit_slope(pairs)
    fit["pairs"] = pairs
    return fit


CALIBRATION = calibrate()
BOARD_ROWS = [build_row(f, CALIBRATION) for f in FIXTURES]

# --------------------------------------------------------------------------- unresolved ledger
UNRESOLVED = []
for row in BOARD_ROWS:
    if row["line"] is None:
        UNRESOLVED.append({
            "fixture_id": row["fixture_id"], "match": f"{row['team_a']} vs {row['team_b']}",
            "start_utc": row["start_utc"], "competition": row["competition"],
            "hotspawn_url": row["hotspawn_url"],
            "fixture_url": row.get("fixture_url"),
            "directional_pick": "Chinggis Warriors" if row["fixture_id"] == "1081863" else None,
            "attempt_ledger": [], "flags": row["flags"],
        })
CHINGGIS_LEDGER = [
    {"step": "HotSpawn lobby + API inventory", "result": "fixture 1081863 confirmed open, Chinggis Warriors vs WXM, VOID Autumn Cup 2026, 2026-10-20T07:00Z", "url": "https://play.hotspawn.com/lobby"},
    {"step": "egamersworld match page", "result": "fixture exists with lineups (Chinggis: sk0R, cool4st, ROUX, fury5k, tikuak) but odds are an untrained 1.80/1.80 placeholder with 0% vote - rejected as a price", "url": "https://egamersworld.com/counterstrike/match/EJcHRdr5Vx/chinggis-warriors-vs-wxm-_ddme1I7dZ"},
    {"step": "Polymarket esports CS2 event pages", "result": "no market exists for this fixture", "url": "https://polymarket.com/esports/cs2/"},
    {"step": "Pinnacle / Bovada / Melbet / Kalshi / Thunderpick (via retained bo3.gg bet_updates)", "result": "no two-sided price published for this fixture", "url": "https://bo3.gg/matches/"},
    {"step": "bo3.gg VOID Autumn Cup tournament page", "result": "fixture confirmed (as 'Wept Xyloid Melancholy vs Chinggis Warriors') but no odds block published", "url": "https://bo3.gg/tournaments/void-autumn-cup-2026"},
    {"step": "Valve VRS global ladder 2026-10-05", "result": "Chinggis Warriors rated (#87, 1084 pt, roster cool4st/fury5k/ROUX/sk0R/yAmi - verified against the egamersworld lineup); WXM absent from the ladder", "url": "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standards_global_2026_10_05.md"},
    {"step": "bo3.gg match history (Elo origination)", "result": "WXM ('Wept Xyloid Melancholy', bo3.gg team id 25531) has zero recorded matches - Elo cannot be originated for them either", "url": "https://bo3.gg/teams/25531"},
    {"step": "HLTV / Mais Esports event pages", "result": "WXM identified as 'Wept Xyloid Melancholy', a Chinese lineup (Currant, Kinatie, outccc, 1romma, Genxiu) playing the VOID Autumn Cup 2026 (Oct 20-24, Shanghai, $12,000, 8 teams) - identity verified, rating still unavailable", "url": "https://www.hltv.org/events/9435/macemedia-void-autumn-cup-2026"},
]
for entry in UNRESOLVED:
    if entry["fixture_id"] == "1081863":
        entry["attempt_ledger"] = CHINGGIS_LEDGER
        entry["policy"] = ("No published two-sided price on any reachable bookmaker or exchange, "
                           "and the opponent is absent from Valve's VRS ladder and from bo3.gg's "
                           "match history, so neither the market basis nor any documented model "
                           "basis can produce a probability. Per policy the probability stays "
                           "BLANK; the directional pick (Chinggis Warriors, Valve-rated #87/1084 pt "
                           "against an unrated opponent) is published as direction only, low "
                           "confidence, and is never presented as a percentage.")

# Backfill: rows still without a fixture link get the first retained evidence
# URL from the unresolved attempt ledger (e.g. the blank Chinggis-WXM fixture
# keeps its egamersworld match page).
for _row in BOARD_ROWS:
    if _row.get("fixture_url"):
        continue
    for _entry in UNRESOLVED:
        if _entry["fixture_id"] == _row["fixture_id"]:
            for _step in _entry.get("attempt_ledger", []):
                if _step.get("url"):
                    _row["fixture_url"] = _step["url"]
                    break
            break

# --------------------------------------------------------------------------- summary
n_market = sum(1 for r in BOARD_ROWS if r["market"])
n_model_only = sum(1 for r in BOARD_ROWS if not r["market"] and r["model"])
n_blank = sum(1 for r in BOARD_ROWS if r["line"] is None)
picks = [r for r in BOARD_ROWS if r["line"]]
SUMMARY = {
    "open_fixtures": len(BOARD_ROWS),
    "with_market_line": sum(1 for r in BOARD_ROWS if r["line"] and r["basis"] in ("market", "market+model")),
    "model_only_line": n_model_only,
    "blank_unresolved": n_blank,
    "n_sources_total": len({q["public_url"] for r in BOARD_ROWS for q in r["quotes"]}),
    "strong_picks": sum(1 for r in picks if r["confidence"] == "Strong"),
    "contrarian_climb": sum(1 for r in picks if r["role"] and r["role"].startswith("climb")),
    "flags_raised": sum(len(r["flags"]) for r in BOARD_ROWS),
}

BOARD = {
    "session": SESSION,
    "generated_utc": BUILD_UTC,
    "data_as_of": {
        "hotspawn_lobby_render": "2026-10-17T00:52:00Z (this session, manual read)",
        "hotspawn_api_inventory": "2026-10-17T00:22:00Z (retained fe803b80 snapshot)",
        "external_quotes_retained": "2026-10-17T00:19:42Z/00:21:36Z (fe803b80 capture)",
        "external_quotes_fresh": "2026-10-17T00:52:00Z/01:10:00Z (this session)",
        "valve_vrs_ladder": "2026-10-05 official global snapshot (latest full ladder published)",
        "live_vrs_overrides": "2026-10-17T00:53Z/01:10Z HLTV live Valve-ranking reads",
    },
    "rules": {
        "market_consensus": "median of per-source no-vig probabilities",
        "blend": f"{BLEND_MARKET_WEIGHT:.2f} market / {1 - BLEND_MARKET_WEIGHT:.2f} model when both exist",
        "vrs_model": f"Valve Glicko expected-score formula, RD={VALVE_RD} (Valve's fit.js default), slope k fitted against joined market lines",
        "elo_model": f"plain Elo over retained bo3.gg history, k={ELO_K}, {ELO_PASSES} chronological passes, VRS teams anchored at their Valve points",
        "blank_policy": "a probability is published only when derivable from a retained source; otherwise the cell stays blank and the fixture is ledgered as unresolved",
        "crowd_policy": "HotSpawn pick'em crowd share is context only and is never a probability input",
        "seed_policy": "untrained seed prices (exact 1.80/1.80 placeholders with zero votes, $0-volume markets, wide bid/ask seeds, overround > 0.30) are rejected, not averaged",
    },
    "calibration": CALIBRATION,
    "elo": {k: v for k, v in ELO.items() if k != "ratings"},
    "summary": SUMMARY,
    "open": BOARD_ROWS,
    "twc": {
        "event": research["event"],
        "results": research["results"],
        "aurora_roster_verdict": research["aurora_roster_verdict"],
    },
    "unresolved": UNRESOLVED,
    "corrections": [
        {"fixture_id": "1079638", "title": "ex-RUSTEC joined to the stale Valve row",
         "detail": "The full-coverage board joined ex-RUSTEC to Valve row #152 (823.9 pt; Brilliance, jakekeS, Patsi, youka - last played 2026-08-17). The active lineage is row #92 (1066.4 pt; last match 2026-09-27), which the live HLTV VRS rank (#86) confirms. This board uses row #92 and the pick flips from ILLYRIANS to ex-RUSTEC. Current five (Brilliance, shalfey, bl1x1, youka, relaxxie) overlaps the row on 3/5 - roster-drift flagged.",
         "evidence": ["https://www.hltv.org/team/13901/ex-rustec", "https://bo3.gg/matches/ex-rustec-vs-illyrians-18-10-2026"]},
        {"fixture_id": "1081863", "title": "Chinggis Warriors joined to the wrong Valve row",
         "detail": "The full-coverage board joined Chinggis Warriors to Valve row #220 (685 pt; Aceari, hasteka five). The fixture's verified lineup (sk0R, cool4st, ROUX, fury5k, tikuak - egamersworld) overlaps row #87 (1084 pt) on 4/5 and row #220 on 2/5. Row #87 is correct; the fixture nonetheless stays blank because WXM is unrated everywhere.",
         "evidence": ["https://egamersworld.com/counterstrike/match/EJcHRdr5Vx/chinggis-warriors-vs-wxm-_ddme1I7dZ"]},
        {"fixture_id": "1080291/1081529", "title": "WROTBERRY = WBT join verified (no correction needed)",
         "detail": "Suspected after the Oct-5 file grep (no team literally named WROTBERRY). Verified correct: Valve carries the roster as WBT (#60, 1201.1 pt, DemQQ/Psycho/s4ltovsk1yy/Smash/tyr1k) and HLTV team 13683 - page title now WBT, formerly WROTBERRY - lists that exact five and upcoming matches '17 Oct vs HAVU' and '19 Oct vs Nexus', matching HotSpawn fixtures 1080291 and 1081529 on opponent and date.",
         "evidence": ["https://www.hltv.org/team/13683/wbt"]},
        {"title": "Canonical board's VRS slope is internally inconsistent",
         "detail": "Re-deriving the documented Valve Glicko formula row-by-row against the full-coverage board's published model probabilities implies effective slopes from ~0.10 to ~1.33 across rows of the same board. This board fits ONE global slope on the joined market pairs and publishes the fit (k, pair count, MAE) with the board.",
         "evidence": ["data/c32f1b93/board.json calibration section"]},
        {"title": "Day-1 TWC Nuke score capture error confirmed",
         "detail": "One prior desk capture recorded 9z's day-1 Nuke win over Aurora as 16-14. The HLTV match page reads 13-1 (11:1; 2:0). 13-1 is confirmed by direct read this session; the 16-14 capture stays flagged.",
         "evidence": ["https://www.hltv.org/matches/2399384/9z-vs-aurora-thunderpick-world-championship-2026"]},
        {"title": "HLTV analytics prose vs fetched prices on FURIA-Aurora",
         "detail": "HLTV's betting-analytics page says 'Aurora is the bookmaker favorite with the best odds', while every directly fetched price this session (egamersworld 1.83/1.90, Polymarket 53c/48c, plus the retained Pinnacle/Bovada/Melbet/Kalshi/Thunderpick lines) prices FURIA marginally ahead. Both are published with read times; the pick follows the prices and the divergence is flagged, not reconciled.",
         "evidence": ["https://www.hltv.org/betting/analytics/2399414/furia-vs-aurora-thunderpick-world-championship-2026"]},
    ],
    "vrs_file": {"path": "data/c32f1b93/vrs_global_2026_10_05.md",
                 "source": "https://github.com/ValveSoftware/counter-strike_regional_standings/blob/main/live/2026/standards_global_2026_10_05.md",
                 "teams_in_file": sum(len(v) for v in vrs_file["teams"].values())},
}

DATA.mkdir(parents=True, exist_ok=True)
with open(DATA / "board.json", "w", encoding="utf-8") as fh:
    json.dump(BOARD, fh, indent=1, ensure_ascii=False)
print(f"board.json written: {SUMMARY['open_fixtures']} open fixtures, "
      f"{SUMMARY['with_market_line']} market lines, {SUMMARY['model_only_line']} model-only, "
      f"{SUMMARY['blank_unresolved']} blank; fitted k={CALIBRATION['k']:.4f} "
      f"(raw {CALIBRATION.get('k_raw')}) on {CALIBRATION['n_pairs']} pairs")
