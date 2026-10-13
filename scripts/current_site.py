"""Static renderer for the T-CURRENT board (session 0f6c89c6). Called by build_current_board.py."""

import html
import os

CSS = """
:root{--bg:#0f1420;--card:#171e2e;--ink:#e9eef8;--mut:#9aa6bd;--ok:#2fbf71;--warn:#f0b429;--bad:#ff6b6b;--acc:#5aa2ff;--line:#26304a}
*{box-sizing:border-box}
body{margin:0;font:16px/1.45 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:var(--bg);color:var(--ink)}
header{padding:18px 16px 8px;max-width:960px;margin:auto}
h1{font-size:1.35rem;margin:0 0 4px}
h2{font-size:1.1rem;margin:18px 0 8px}
p.lead{color:var(--mut);margin:4px 0 10px;font-size:.95rem}
nav{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 4px}
nav a{color:var(--acc);text-decoration:none;border:1px solid var(--line);border-radius:999px;padding:6px 12px;font-size:.9rem}
nav a.on{background:var(--acc);color:#071226}
main{max-width:960px;margin:auto;padding:0 12px 40px}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin:10px 0 14px}
@media(min-width:700px){.stats{grid-template-columns:repeat(4,1fr)}}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.stat b{display:block;font-size:1.5rem}
.stat span{color:var(--mut);font-size:.8rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:0 0 12px}
.meta{color:var(--mut);font-size:.82rem;display:flex;flex-wrap:wrap;gap:6px 12px}
.pick{margin:10px 0 6px;font-size:1.02rem}
.pick em{font-style:normal;color:var(--ok);font-weight:700}
.pick.none em{color:var(--bad)}
.sides{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:8px 0}
.side{border:1px solid var(--line);border-radius:10px;padding:8px 10px}
.side.win{border-color:var(--ok);box-shadow:0 0 0 1px var(--ok) inset}
.side .n{font-weight:600;word-break:break-word}
.side .p{font-size:1.5rem;font-weight:800}
.side .k{color:var(--mut);font-size:.78rem}
.bar{height:8px;border-radius:6px;background:#2a3550;overflow:hidden;display:flex}
.bar i{display:block;height:100%}
.tag{display:inline-block;border-radius:6px;padding:2px 7px;font-size:.75rem;margin-right:4px;background:#222c44;color:var(--ink)}
.tag.q-high{background:#17432e;color:#b8f5d2}.tag.q-med{background:#3b3a16;color:#f7eaa0}.tag.q-low{background:#4a2a14;color:#ffd2a6}.tag.q-none{background:#4a1d1d;color:#ffc5c5}
details{margin-top:8px;font-size:.88rem;color:var(--mut)}
details summary{cursor:pointer;color:var(--acc)}
ul{padding-left:18px;margin:6px 0}
li{margin:4px 0}
a{color:var(--acc)}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th,td{border-bottom:1px solid var(--line);padding:6px 6px;text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600}
.wrap{overflow-x:auto}
.note{background:#1b2540;border:1px solid var(--line);border-radius:10px;padding:10px 12px;color:var(--mut);font-size:.88rem}
footer{color:var(--mut);font-size:.8rem;max-width:960px;margin:auto;padding:10px 16px 30px}
"""


def esc(s):
    return html.escape("" if s is None else str(s), quote=True)


def pct(p):
    return "—" if p is None else f"{round(p * 100, 1):.1f}%"


def utc(s):
    return (s or "").replace("T", " ").replace("Z", " UTC")[:20]


def page(title, active, body, generated):
    nav = (
        f'<a href="index.html" class="{"on" if active == "index" else ""}">Current picks</a>'
        f'<a href="flagged.html" class="{"on" if active == "flagged" else ""}">Flagged for review</a>'
        f'<a href="../index.html">Main dashboard</a>'
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<style>{CSS}</style></head>
<body>
<header><h1>{esc(title)}</h1>
<nav>{nav}</nav></header>
<main>{body}</main>
<footer>Snapshot {esc(generated)}. Not affiliated with Hotspawn, Pinnacle, Bovada or EGamersWorld.
Hotspawn crowd % is shown for context only and is never used as a probability.
Probabilities are our own proportional no-vig derivations of captured external prices.</footer>
</body></html>
"""


def card(r):
    a, b = r["team_a"], r["team_b"]
    pa, pb = r["probability_a"], r["probability_b"]
    q = r["quality"] or ""
    qcls = "q-high" if q.startswith("High") else "q-med" if q.startswith("Medium") else "q-low" if q.startswith("Low") else "q-none"
    qlabel = q if q else "No external line"
    if r["quote_captured"]:
        pick_win = r["pick"]
        pick_html = (f'<div class="pick">PICK: <em>{esc(pick_win)}</em> &middot; '
                     f'{pct(r["pick_probability"])} &middot; {esc(r["pick_confidence"])}</div>')
        bar_a = round((pa or 0) * 100, 1)
        bar_b = round((pb or 0) * 100, 1)
        bar = (f'<div class="bar"><i style="width:{bar_a}%;background:var(--ok)"></i>'
               f'<i style="width:{bar_b}%;background:#41506f"></i></div>')
        sides = (
            f'<div class="sides">'
            f'<div class="side {"win" if pick_win == a else ""}"><div class="n">{esc(a)}</div>'
            f'<div class="p">{pct(pa)}</div><div class="k">win probability</div></div>'
            f'<div class="side {"win" if pick_win == b else ""}"><div class="n">{esc(b)}</div>'
            f'<div class="p">{pct(pb)}</div><div class="k">win probability</div></div></div>'
        )
    else:
        pick_html = '<div class="pick none">PICK: <em>none — no external line captured</em></div>'
        bar = ""
        sides = (
            f'<div class="sides">'
            f'<div class="side"><div class="n">{esc(a)}</div><div class="p">—</div><div class="k">no line captured</div></div>'
            f'<div class="side"><div class="n">{esc(b)}</div><div class="p">—</div><div class="k">no line captured</div></div></div>'
        )
    srcs = "".join(
        f'<li><a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(s["source"])}</a> '
        f'&middot; {esc(s["decimal_a"])} / {esc(s["decimal_b"])} &middot; '
        f'{pct(s["p_a"])} / {pct(1 - s["p_a"])} &middot; captured {esc(utc(s["retrieved_at_utc"]))}</li>'
        for s in r["sources"] if s.get("url")
    ) or "<li>No qualifying external quote.</li>"
    flags = "".join(f"<li>{esc(f)}</li>" for f in r["flags"]) or "<li>none</li>"
    hs = r["hotspawn_pick_pct_reference_only"]
    return f"""<article class="card">
<div class="meta"><span>{esc(utc(r["kickoff_utc"]))}</span><span>{esc(r["event"])}</span>
<span>Tier {esc(r["tier"])} · {esc(r["points"])} pts</span></div>
<h2 style="margin:8px 0 0">{esc(a)} <span style="color:var(--mut)">vs</span> {esc(b)}</h2>
<div><span class="tag {qcls}">{esc(qlabel)}</span></div>
{pick_html}{sides}{bar}
<details><summary>Sources, flags and Hotspawn reference</summary>
<p>Hotspawn crowd (reference only): {esc(a)} {esc(hs["team_a"])}% · {esc(b)} {esc(hs["team_b"])}%.
<a href="{esc(r["hotspawn_url"])}" target="_blank" rel="noopener">Hotspawn match page</a></p>
<p><strong>External quotes used</strong></p><ul>{srcs}</ul>
<p><strong>Flags</strong></p><ul>{flags}</ul>
</details></article>"""


def render(doc, out_dir):
    rows = doc["rows"]
    s = doc["summary"]
    gen = doc["generated_at_utc"]
    stats = (
        f'<div class="stats">'
        f'<div class="stat"><b>{s["open_cs2_fixtures"]}</b><span>open CS2 fixtures</span></div>'
        f'<div class="stat"><b>{s["with_named_bookmaker_line"]}</b><span>with Pinnacle/Bovada line</span></div>'
        f'<div class="stat"><b>{s["with_egw_fallback_only"]}</b><span>fallback widget quote only</span></div>'
        f'<div class="stat"><b>{s["without_any_line"]}</b><span>no line (blank, flagged)</span></div>'
        f'</div>'
    )
    intro = (
        '<p class="lead">Every CS2 match that is open for picks in the Hotspawn pick\'em, one card each. '
        'The probability is derived only from external bookmaker prices. Hotspawn crowd percentages are '
        'shown only as reference.</p>'
        '<div class="note">Blank probability = no qualifying external price was captured. We do not fill it in. '
        'See the Flagged page for every such row and every irregularity.</div>'
    )
    cards = "".join(card(r) for r in rows)
    body_index = intro + stats + "<h2>Matches (earliest first)</h2>" + cards
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page("CS2 pick'em: current picks", "index", body_index, gen))

    # flagged page
    unv = [r for r in rows if not r["quote_captured"]]
    lowq = [r for r in rows if r["quality"] and r["quality"].startswith("Low")]
    irr = doc.get("irregularities", [])
    trs = "".join(
        f'<tr><td>{esc(utc(r["kickoff_utc"]))}</td><td>{esc(r["team_a"])} vs {esc(r["team_b"])}</td>'
        f'<td>{esc(r["event"])}</td><td>{esc(r["quality"] or "none")}</td>'
        f'<td><a href="{esc(r["hotspawn_url"])}" target="_blank" rel="noopener">Hotspawn</a></td>'
        f'<td>{"; ".join(esc(f) for f in r["flags"])}</td></tr>'
        for r in rows if r["flags"]
    )
    irr_items = "".join(
        f'<li>{esc(i["match"])}: {esc(i["issue"])}'
        + (f' — <a href="{esc(i["url"])}" target="_blank" rel="noopener">source</a>' if i.get("url") else "")
        + "</li>"
        for i in irr
    )
    body_flag = (
        '<p class="lead">Rows and irregularities that need manual review. Nothing here is hidden from the picks page.</p>'
        f'<div class="stats"><div class="stat"><b>{len(unv)}</b><span>rows with no line</span></div>'
        f'<div class="stat"><b>{len(lowq)}</b><span>rows on fallback widget only</span></div>'
        f'<div class="stat"><b>{len(irr)}</b><span>irregularities logged</span></div></div>'
        "<h2>Rows with flags</h2><div class=\"wrap\"><table><thead><tr><th>Kickoff</th><th>Match</th>"
        "<th>Event</th><th>Quality</th><th>Source</th><th>Flags</th></tr></thead><tbody>"
        f"{trs}</tbody></table></div>"
        f"<h2>Irregularities</h2><ul>{irr_items or '<li>none</li>'}</ul>"
    )
    with open(os.path.join(out_dir, "flagged.html"), "w", encoding="utf-8") as fh:
        fh.write(page("Flagged for review: current board", "flagged", body_flag, gen))
