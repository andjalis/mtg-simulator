"""Views of a ranked ladder run (see rating.py): a live terminal line, a text summary and an HTML report.

Every view renders the plain dict from LadderTracker.to_dict(), so a web page can reuse them:
    render_fragment(data)  -> an HTML <section> with its own scoped <style> (no scripts needed;
                              one small optional script adds chart tooltips)
    render_page(data)      -> a whole HTML page; while data["status"] == "running" it reloads itself
    HtmlReport(path)       -> a tracker listener that rewrites the page as the run goes
"""
from __future__ import annotations

import html
import json
import os
import sys
import time
from pathlib import Path

from .rating import RANKS

SPARK = "▁▂▃▄▅▆▇█"


# -- terminal ---------------------------------------------------------------------
class TerminalView:
    """Listener that keeps one live status line on stderr (only when it is a terminal)."""

    def __init__(self, stream=None, min_interval=0.1):
        self.stream = stream or sys.stderr
        self.live = self.stream.isatty()
        self.min_interval, self.last = min_interval, 0.0

    def __call__(self, tracker):
        if not self.live:
            return
        now = time.time()
        if tracker.status == "running" and now - self.last < self.min_interval:
            return
        self.last = now
        d = tracker.to_dict()
        line = f"  {badge(d)}"
        if d["current"]:
            c = d["current"]
            done = c["games"] / c["total"] if c["total"] else 0
            bar = "█" * round(done * 16) + "░" * (16 - round(done * 16))
            wr = f"{c['win_rate']:.0%}" if c["win_rate"] is not None else "--"
            line += f"  vs {c['opponent']}  {bar} {c['games']}/{c['total']}  won {wr}"
        print("\r\033[K" + line, end="" if tracker.status == "running" else "\n",
              file=self.stream, flush=True)

    def clear(self):
        if self.live:
            print("\r\033[K", end="", file=self.stream, flush=True)


def badge(d: dict) -> str:
    nxt = f", {d['to_next']} to {d['next_rank']}" if d["next_rank"] else ""
    return f"[{d['rank']} · {d['mmr']} MMR{nxt}]"


def sparkline(history, width=40) -> str:
    vals = [m for _, m in history]
    if len(vals) > width:
        vals = [vals[round(i * (len(vals) - 1) / (width - 1))] for i in range(width)]
    lo, hi = min(vals), max(vals)
    if hi - lo < 1:
        return SPARK[3] * len(vals)
    return "".join(SPARK[round((v - lo) / (hi - lo) * (len(SPARK) - 1))] for v in vals)


def text_summary(d: dict) -> str:
    """The rank ladder as text: every rank band, the pools in it and where the deck landed."""
    lines = [f"Rank: {d['deck']} is {d['rank']} at {d['mmr']} MMR (peak {d['peak']}, {d['games']} games)"]
    lines.append("  Internal pool ranks/MMR, not Arena equivalents. Main-deck only; no sideboarding. AI pilot and rules limitations apply.")
    pools_by_rank = {}
    for p in d["pools"]:
        if p["rank"]:
            pools_by_rank.setdefault(p["rank"], []).append(p)
    for r in reversed(d["ranks"]):
        here = f"  ◀ {d['deck']} {d['mmr']}" if r["name"] == d["rank"] else ""
        pools = ", ".join(
            f"{p['label']} pool {p['rating']}" + (f" (won {p['rate']:.0%})" if p["rate"] is not None else "")
            for p in pools_by_rank.get(r["name"], []))
        lines.append(f"  {r['name']:<12}{r['floor']:>5}+  {pools}{here}".rstrip())
    lines.append(f"  MMR over the run {d['history'][0][1]:.0f} → {d['mmr']}: {sparkline(d['history'])}")
    return "\n".join(lines)


# -- HTML -------------------------------------------------------------------------
CSS = """
.mmr{--ink:#1d2129;--ink2:#545b66;--muted:#8a919c;--line:#e3e6ea;--panel:#f6f7f9;--bg:#fff;--bar:#3b7ddd;
  font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);background:var(--bg);
  max-width:960px;margin:0 auto;padding:16px;box-sizing:border-box}
.mmr td:first-child{overflow-wrap:break-word}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .mmr{--ink:#e8eaed;--ink2:#b3b9c2;
  --muted:#7f8792;--line:#30353d;--panel:#1b1e23;--bg:#121418;--bar:#6aa1f0}}
:root[data-theme="dark"] .mmr{--ink:#e8eaed;--ink2:#b3b9c2;--muted:#7f8792;--line:#30353d;--panel:#1b1e23;
  --bg:#121418;--bar:#6aa1f0}
.mmr h1{font-size:20px;margin:0 0 4px}.mmr h2{font-size:15px;margin:24px 0 8px}
.mmr .sub{color:var(--ink2);margin:0}
.mmr .head{display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.mmr .emblem{width:72px;height:80px;flex:none}
.mmr .big{font-size:32px;font-weight:650;font-variant-numeric:tabular-nums;line-height:1.1}
.mmr .prog{height:8px;background:var(--line);border-radius:4px;overflow:hidden;margin:6px 0 2px;max-width:320px}
.mmr .prog>i{display:block;height:100%;border-radius:4px}
.mmr .live{display:inline-block;font-size:12px;padding:1px 8px;border-radius:9px;background:var(--panel);
  color:var(--ink2);margin-left:8px;vertical-align:middle}
.mmr svg text{fill:var(--muted);font-size:11px}
.mmr .chart{width:100%;height:auto;display:block}
.mmr table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
.mmr td,.mmr th{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left}
.mmr th{color:var(--ink2);font-weight:550;font-size:12px}
.mmr .n{text-align:right;white-space:nowrap}
.mmr .wr{width:45%}
.mmr .wr>span{display:block}
.mmr .wr>span{height:8px;background:var(--line);border-radius:4px;position:relative}
.mmr .wr>span>i{position:absolute;left:0;top:0;bottom:0;background:var(--bar);border-radius:4px}
.mmr .wr>span>b{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--ink2)}
.mmr .dot{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.mmr .tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--bg);padding:4px 8px;
  border-radius:6px;font-size:12px;display:none;white-space:nowrap}
@media (max-width:560px){.mmr{padding:12px}.mmr .big{font-size:26px}.mmr .hide-s{display:none}}
"""

TIP_JS = """
document.querySelectorAll('.mmr .chart').forEach(function(svg){
  var pts=JSON.parse(svg.dataset.pts),tip=svg.parentNode.querySelector('.tip'),
      cross=svg.querySelector('.cross'),x0=+svg.dataset.x0,x1=+svg.dataset.x1;
  svg.addEventListener('mousemove',function(e){
    var r=svg.getBoundingClientRect(),vb=svg.viewBox.baseVal,x=(e.clientX-r.left)/r.width*vb.width;
    var best=pts[0];pts.forEach(function(p){if(Math.abs(p[2]-x)<Math.abs(best[2]-x))best=p});
    if(x<x0-10||x>x1+10){tip.style.display='none';cross.style.display='none';return}
    cross.setAttribute('x1',best[2]);cross.setAttribute('x2',best[2]);cross.style.display='';
    tip.textContent='after '+best[0]+' games: '+Math.round(best[1])+' MMR';tip.style.display='block';
    tip.style.left=Math.min(e.clientX+12,innerWidth-tip.offsetWidth-8)+'px';tip.style.top=(e.clientY-28)+'px'});
  svg.addEventListener('mouseleave',function(){tip.style.display='none';cross.style.display='none'});
});
"""


def _e(s) -> str:
    return html.escape(str(s))


def emblem(rank: str, color: str) -> str:
    """A shield badge; higher ranks get more pips."""
    names = [r.name for r in RANKS]
    level = names.index(rank) if rank in names else 0
    pips = "".join(f'<circle cx="{36 - (level - 1) * 4 + i * 8}" cy="14" r="2.6" fill="#fff" opacity=".9"/>'
                   for i in range(level))
    crown = ('<path d="M22 6 L28 14 L36 4 L44 14 L50 6 L48 18 L24 18 Z" fill="#ffd54a" stroke="#0003"/>'
             if rank == "Grandmaster" else "")
    return (f'<svg class="emblem" viewBox="0 0 72 80" role="img" aria-label="{_e(rank)} rank">'
            f'<path d="M36 4 L66 14 L62 50 Q58 66 36 76 Q14 66 10 50 L6 14 Z" fill="{color}" stroke="#0003" stroke-width="2"/>'
            f'<path d="M36 12 L58 19 L55 48 Q52 60 36 68 Q20 60 17 48 L14 19 Z" fill="#fff" opacity=".18"/>'
            f'{crown}{pips}<text x="36" y="50" text-anchor="middle" style="fill:#fff;font-size:22px;font-weight:700">'
            f'{_e(rank[0])}</text></svg>')


def mmr_chart(d: dict, w=900, h=300) -> str:
    """MMR after each game, over horizontal rank bands."""
    pad_l, pad_r, pad_t, pad_b = 84, 16, 10, 26
    hist = d["history"]
    if len(hist) > 400:
        step = (len(hist) - 1) / 399
        hist = [hist[round(i * step)] for i in range(400)]
    vals = [m for _, m in hist] + [p["rating"] for p in d["pools"] if p["rating"] is not None]
    lo = min(min(vals) - 80, 900)
    hi = max(max(vals) + 80, 1300)
    ranks = d["ranks"]
    n_games = max(hist[-1][0], 1)
    x = lambda g: pad_l + (w - pad_l - pad_r) * g / n_games
    y = lambda m: pad_t + (h - pad_t - pad_b) * (1 - (m - lo) / (hi - lo))
    out = []
    for i, r in enumerate(ranks):
        top = ranks[i + 1]["floor"] if i + 1 < len(ranks) else hi
        b0, b1 = max(r["floor"], lo), min(top, hi)
        if b1 <= b0:
            continue
        out.append(f'<rect x="{pad_l}" y="{y(b1):.1f}" width="{w - pad_l - pad_r}" height="{y(b0) - y(b1):.1f}" '
                   f'fill="{r["color"]}" opacity=".13"/>')
        out.append(f'<rect x="{pad_l - 4}" y="{y(b1) + 1:.1f}" width="3" height="{max(y(b0) - y(b1) - 2, 1):.1f}" '
                   f'rx="1.5" fill="{r["color"]}"/>')
        out.append(f'<text x="{pad_l - 10}" y="{(y(b0) + y(b1)) / 2 + 4:.1f}" text-anchor="end">{_e(r["name"])}</text>')
    for p in d["pools"]:
        if p["rating"] is not None and lo < p["rating"] < hi:
            yy = y(p["rating"])
            out.append(f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="currentColor" '
                       f'stroke-opacity=".25" stroke-dasharray="3 4"/>')
            out.append(f'<text x="{w - pad_r - 4}" y="{yy - 4:.1f}" text-anchor="end">{_e(p["label"])} pool</text>')
    pts = [(g, m, x(g), y(m)) for g, m in hist]
    path = " ".join(f"{'M' if i == 0 else 'L'}{px:.1f},{py:.1f}" for i, (_, _, px, py) in enumerate(pts))
    out.append(f'<path d="{path}" fill="none" stroke="{d["rank_color"]}" stroke-width="2.2" '
               f'stroke-linejoin="round" stroke-linecap="round"/>')
    gx, gm, px, py = pts[-1]
    out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="{d["rank_color"]}" stroke="var(--bg)" stroke-width="2"/>')
    out.append(f'<text x="{pad_l}" y="{h - 6}">0</text>'
               f'<text x="{w - pad_r}" y="{h - 6}" text-anchor="end">{n_games} games</text>')
    out.append(f'<line class="cross" y1="{pad_t}" y2="{h - pad_b}" stroke="currentColor" stroke-opacity=".35" '
               f'style="display:none"/>')
    data = json.dumps([[g, round(m), round(px, 1)] for g, m, px, _ in pts])
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="MMR over the run, from '
            f'{hist[0][1]:.0f} to {d["mmr"]}" data-pts="{_e(data)}" data-x0="{pad_l}" data-x1="{w - pad_r}" '
            f'style="color:var(--ink)">{"".join(out)}</svg><div class="tip"></div>')


def opponent_table(d: dict) -> str:
    labels = {p["key"]: p for p in d["pools"]}
    rows = []
    for key, pool in labels.items():
        opps = [o for o in d["opponents"] if o["pool"] == key]
        rate = f'{pool["rate"]:.0%}' if pool["rate"] is not None else ""
        state = ""
        if pool["cleared"] is not None:
            state = " · cleared" if pool["cleared"] else " · failed"
        colour = next((r["color"] for r in d["ranks"] if r["name"] == pool["rank"]), "#888")
        rows.append(f'<tr><th colspan="2"><span class="dot" style="background:{colour}"></span>{_e(pool["label"])} '
                    f'pool <span class="hide-s">· {pool["rating"]} MMR</span>{state}</th>'
                    f'<th class="n">{rate}</th><th class="n hide-s">{pool["games"] or ""}</th></tr>')
        for o in opps:
            if o["win_rate"] is None:
                rows.append(f'<tr><td>{_e(o["name"].split("/", 1)[-1].replace("_", " "))}</td><td class="wr"><span></span></td>'
                            f'<td class="n" style="color:var(--muted)">not played</td><td class="n hide-s"></td></tr>')
                continue
            wr = o["win_rate"]
            rows.append(f'<tr><td>{_e(o["name"].split("/", 1)[-1].replace("_", " "))}</td>'
                        f'<td class="wr" title="won {wr:.1%} of {o["games"]} games"><span><i style="width:{wr * 100:.1f}%">'
                        f'</i><b style="left:{d["pass_rate"] * 100:.0f}%"></b></span></td>'
                        f'<td class="n">{wr:.0%}</td><td class="n hide-s">{o["games"]}</td></tr>')
    return ('<table><thead><tr><th>Opponent</th><th>Win rate (tick marks the '
            f'{d["pass_rate"]:.0%} line)</th><th class="n">Won</th><th class="n hide-s">Games</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def render_fragment(d: dict) -> str:
    nxt = d["next_rank"]
    floor = next(r["floor"] for r in d["ranks"] if r["name"] == d["rank"])
    top = next((r["floor"] for r in d["ranks"] if r["name"] == nxt), None)
    pct = 100 if top is None else max(0, min(100, (d["mmr"] - floor) / (top - floor) * 100))
    progress_text = f"{d['to_next']} MMR to {nxt}" if nxt else "Top rank"
    live = ""
    if d["status"] == "running":
        c = d["current"]
        live = f'<span class="live">live · {d["games"]} games'
        live += f' · vs {_e(c["opponent"])} {c["games"]}/{c["total"]}' if c else ""
        live += "</span>"
    return (f'<section class="mmr"><style>{CSS}</style>'
            f'<div class="head">{emblem(d["rank"], d["rank_color"])}<div>'
            f'<h1>{_e(d["deck"])}{live}</h1>'
            f'<div class="big">{_e(d["rank"])} · {d["mmr"]} MMR</div>'
            f'<div class="prog"><i style="width:{pct:.0f}%;background:{d["rank_color"]}"></i></div>'
            f'<p class="sub">{progress_text} · peak {d["peak"]} · {d["games"]} games</p></div></div>'
            + (f'<p>{_e(d["verdict"])}</p>' if d["verdict"] else "")
            + '<p>Internal pool ranks/MMR, not Arena equivalents. Main-deck only; no sideboarding. AI pilot and rules limitations apply.</p>'
            + f'<h2>MMR over the run</h2><div style="position:relative">{mmr_chart(d)}</div>'
            f'<h2>Results by opponent</h2>{opponent_table(d)}'
            f'<script>{TIP_JS}</script></section>')


def render_page(d: dict, refresh: int = 2) -> str:
    meta = f'<meta http-equiv="refresh" content="{refresh}">' if d["status"] == "running" else ""
    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">{meta}'
            f'<title>{_e(d["deck"])} ranked ladder</title>'
            f'<style>body{{margin:0;background:#fff}}@media (prefers-color-scheme:dark){{body{{background:#121418}}}}'
            f'</style></head><body>{render_fragment(d)}</body></html>')


class HtmlReport:
    """Listener that rewrites an HTML page (and a JSON file beside it) as the run goes."""

    def __init__(self, path, min_interval=1.0):
        self.path = Path(path)
        self.json_path = self.path.with_suffix(".json")
        self.min_interval, self.last = min_interval, 0.0

    def __call__(self, tracker):
        now = time.time()
        if tracker.status == "running" and now - self.last < self.min_interval:
            return
        self.last = now
        d = tracker.to_dict()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for path, text in ((self.path, render_page(d)), (self.json_path, json.dumps(d, indent=1))):
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
