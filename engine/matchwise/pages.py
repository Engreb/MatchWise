"""Static, indexable pages: one per upcoming fixture, an index of them, and a sitemap.

The app itself is a single page with #-routes, which search engines and link previews can't
see. These pages carry each prediction in plain HTML (title, description, the numbers) and link
into the app for the full match view. They're rebuilt on every update and never committed.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

SITE = "https://engreb.github.io/MatchWise/"
DIR = "m"  # pages live at <app>/m/<league>/<slug>.html
UK = ZoneInfo("Europe/London")
GRID_START, GRID_N = 11, 6  # payload layout from pipeline.payload()

STYLE = """
:root{--bg:#f6f7f9;--card:#fff;--text:#14181f;--muted:#5d6675;--line:#e3e6eb;--accent:#1f6feb;--bar:#dfe7f5}
@media (prefers-color-scheme:dark){:root{--bg:#0f1217;--card:#171b22;--text:#e8ebf0;--muted:#9aa3b2;--line:#283040;--accent:#5b9dff;--bar:#22324d}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:640px;margin:0 auto;padding:24px 16px 48px}a{color:var(--accent)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin:14px 0}
h1{font-size:1.5rem;line-height:1.25;margin:4px 0 2px}.muted{color:var(--muted)}.small{font-size:.875rem}
.row{display:grid;grid-template-columns:7.5rem 1fr 3.2rem;gap:10px;align-items:center;margin:8px 0}
.bar{height:10px;border-radius:5px;background:var(--bar);overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}
.num{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;text-align:center}.stats b{display:block;font-size:1.2rem}
.btn{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;padding:10px 16px;border-radius:10px;font-weight:600}
ul.list{list-style:none;padding:0;margin:0}ul.list li{padding:8px 0;border-top:1px solid var(--line)}ul.list li:first-child{border-top:0}
"""


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def page_path(f: dict) -> str:
    return f"{DIR}/{f['league']}/{slug(f['home'])}-vs-{slug(f['away'])}-{f['date']}.html"


def _pct(v: float) -> str:
    return f"{round(v * 100)}%"


def _kickoff(f: dict) -> str:
    k = f["kickoff"]
    if "T" not in k:
        return datetime.fromisoformat(k).strftime("%a %d %b %Y").replace(" 0", " ")
    t = datetime.fromisoformat(k.replace("Z", "+00:00")).astimezone(UK)
    return t.strftime("%a %d %b %Y, %H:%M UK time").replace(" 0", " ", 1)


def _shell(title: str, desc: str, canonical: str, body: str, extra_head: str = "", depth: int = 2) -> str:
    up = "../" * depth
    e = html.escape
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canonical)}"><link rel="icon" href="{up}icons/icon.svg">
<meta property="og:type" content="website"><meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}"><meta property="og:url" content="{e(canonical)}">
<meta property="og:image" content="{SITE}icons/icon-512.png"><meta name="twitter:card" content="summary">
{extra_head}<style>{STYLE}</style></head>
<body><main>{body}
<p class="small muted">Matchwise is a personal football model. These are probabilities, not betting advice: in testing,
no way of betting on its predictions made money over the long run.</p></main></body></html>
"""


def match_page(f: dict, league_name: str) -> str:
    p = f["blend"] or f["model"]
    h, a, e = f["home"], f["away"], html.escape
    H, D, A, o25, btts = p[2], p[3], p[4], p[7], p[10]
    grid = p[GRID_START:GRID_START + GRID_N * GRID_N]
    k = max(range(len(grid)), key=grid.__getitem__)
    score, score_p = f"{k // GRID_N}–{k % GRID_N}", grid[k]
    when = _kickoff(f)
    pick = max(((H, f"{h} win"), (D, "a draw"), (A, f"{a} win")))
    title = f"{h} vs {a} prediction, {league_name} · Matchwise"
    desc = (f"{h} vs {a}, {when}: {h} {_pct(H)}, draw {_pct(D)}, {a} {_pct(A)}. "
            f"Most likely score {score}. Over 2.5 goals {_pct(o25)}, both teams to score {_pct(btts)}.")
    url = SITE + page_path(f)
    app = f"../../index.html#/match/{f['league']}/{quote(h)}/{quote(a)}"
    basis = ("Model blended with bookmaker odds" if f["blend"] else "Model only (no bookmaker odds published yet)")
    ld = {"@context": "https://schema.org", "@type": "SportsEvent", "name": f"{h} vs {a}", "sport": "Football",
          "startDate": f["kickoff"], "homeTeam": {"@type": "SportsTeam", "name": h},
          "awayTeam": {"@type": "SportsTeam", "name": a}, "description": desc,
          "superEvent": {"@type": "SportsEvent", "name": league_name}}
    rows = "".join(f'<div class="row"><span>{e(n)}</span><span class="bar"><i style="width:{v * 100:.1f}%"></i></span>'
                   f'<span class="num">{_pct(v)}</span></div>' for n, v in ((h, H), ("Draw", D), (a, A)))
    body = f"""<p class="small"><a href="../index.html">All match predictions</a></p>
<p class="small muted">{e(league_name)} · {e(when)}</p>
<h1>{e(h)} vs {e(a)}</h1>
<p class="muted">Most likely outcome: <b>{e(pick[1])}</b> ({_pct(pick[0])}).</p>
<div class="card">{rows}<p class="small muted" style="margin:10px 0 0">{e(basis)}.</p></div>
<div class="card stats"><div><b>{score}</b><span class="small muted">Most likely score ({_pct(score_p)})</span></div>
<div><b>{_pct(o25)}</b><span class="small muted">Over 2.5 goals</span></div>
<div><b>{_pct(btts)}</b><span class="small muted">Both teams score</span></div></div>
<p><a class="btn" href="{e(app)}">Full match view in Matchwise</a></p>"""
    head = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>\n'
    return _shell(title, desc, url, body, head)


def index_page(items: list[tuple[dict, str]], generated: str) -> str:
    e = html.escape
    by_league: dict[str, list] = {}
    for f, name in items:
        by_league.setdefault(name, []).append(f)
    sections = "".join(
        f'<div class="card"><h2 style="margin:0 0 6px;font-size:1.1rem">{e(name)}</h2><ul class="list">'
        + "".join(f'<li><a href="{e(page_path(f)[len(DIR) + 1:])}">{e(f["home"])} vs {e(f["away"])}</a>'
                  f'<br><span class="small muted">{e(_kickoff(f))}</span></li>' for f in fs)
        + "</ul></div>" for name, fs in by_league.items())
    body = (f'<p class="small"><a href="../index.html">Open Matchwise</a></p><h1>Football match predictions</h1>'
            f'<p class="muted">Upcoming fixtures in {len(by_league)} leagues, updated {e(generated)}.</p>{sections}')
    return _shell("Football match predictions · Matchwise",
                  f"Probabilities for {len(items)} upcoming football matches in {len(by_league)} leagues.",
                  SITE + f"{DIR}/index.html", body, depth=1)


def write(app_dir: Path, fixture_rows: list[dict], league_names: dict[str, str], generated_at: str, log=print) -> int:
    out = app_dir / DIR
    if out.exists():
        shutil.rmtree(out)  # fixtures that have been played drop out
    items = [(f, league_names[f["league"]]) for f in fixture_rows
             if f.get("status") != "started" and f.get("assessable") and (f.get("blend") or f.get("model"))]
    for f, name in items:
        path = app_dir / page_path(f)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(match_page(f, name), encoding="utf-8")
    day = generated_at[:10]
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(index_page(items, day), encoding="utf-8")
    urls = [SITE, SITE + f"{DIR}/index.html"] + [SITE + page_path(f) for f, _ in items]
    (app_dir / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{html.escape(u)}</loc><lastmod>{day}</lastmod></url>\n" for u in urls)
        + "</urlset>\n", encoding="utf-8")
    log(f"  wrote {len(items)} match pages and sitemap.xml")
    return len(items)
