"""Leaderboard: every tested deck, ranked by MMR.

Entries come from the run history (mtgsim.history: every ladder, rank and assessment run, from the
CLI and the web page), with each deck's latest version's latest rated run. Decks tested before the
history existed still show from the files they left, through the same adapter (collect):

    results/ladder/*.json   ranked-ladder runs from the command line (LadderTracker.to_dict())
    results/assess/*.json   deck assessments (mtgsim.assess): MMR from the meta field, plus S-F grades
    runs on the web page    finished runs the server still holds in memory

Each deck appears once, with its latest run; grades come from its latest assessment.
"""
from __future__ import annotations

import html
import json
import time
from datetime import datetime
from pathlib import Path

try:
    from mtgsim import history
except ImportError:  # pragma: no cover
    history = None

try:
    from mtgsim.ladder_report import emblem
    from mtgsim.rating import RANKS, rank_for
except ImportError:  # pragma: no cover - the rating module ships with the repo
    emblem = rank_for = None
    RANKS = []

RESULTS = Path(__file__).resolve().parent.parent / "results"
CRITERIA = [("meta", "Meta"), ("mana", "Mana"), ("speed", "Speed"), ("consistency", "Consistency")]


def _color(rank: str) -> str:
    return next((r.color for r in RANKS if r.name == rank), "#888")


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ladder_entry(d: dict, tested: float, link: str, source: str) -> dict:
    return {"deck": d.get("deck") or "?", "mmr": d["mmr"], "rank": d["rank"],
            "rank_color": d.get("rank_color") or _color(d["rank"]), "games": d.get("games"),
            "tested": tested, "link": link, "source": source, "grades": None}


def from_files(results: Path = RESULTS) -> list[dict]:
    out = []
    for p in sorted((results / "ladder").glob("*.json")):
        d = _read(p)
        if d and "mmr" in d and "rank" in d and d.get("status") != "running":
            out.append(ladder_entry(d, p.stat().st_mtime, f"/leaderboard/ladder/{p.stem}", "ladder"))
    for p in sorted((results / "assess").glob("*.json")):
        d = _read(p)
        if not d or "criteria" not in d:
            continue
        tested = p.stat().st_mtime
        try:  # the file's date is the day it was assessed; keep the file time if it's that day
            day = datetime.fromisoformat(d["assessed"]).date()
            if datetime.fromtimestamp(tested).date() != day:
                tested = datetime.combine(day, datetime.min.time()).timestamp()
        except (KeyError, TypeError, ValueError):
            pass
        r = d.get("rating") or {}
        out.append({"deck": d.get("deck") or p.stem, "mmr": r.get("mmr"), "rank": r.get("rank"),
                    "rank_color": r.get("rank_color") or _color(r.get("rank")), "games": None,
                    "tested": tested, "link": f"/leaderboard/assess/{p.stem}", "source": "assess",
                    "grades": {k: c.get("grade") for k, c in d["criteria"].items()}})
    return out


def from_history(path=None) -> list[dict]:
    """One entry per deck: the latest rated run of its latest version (else its latest run),
    with the grades of that version's latest graded run."""
    by_deck: dict[str, list[dict]] = {}
    for r in history.runs(path=path):  # newest first
        by_deck.setdefault(r["deck"], []).append(r)
    out = []
    for deck, rs in by_deck.items():
        latest_v = max(r["version"] for r in rs)
        mine = [r for r in rs if r["version"] == latest_v]
        run = next((r for r in mine if r["mmr"] is not None), mine[0])
        graded = next((r for r in mine if r["grades"]), None)
        tested = datetime.fromisoformat(run["created"].replace("Z", "+00:00")).timestamp()
        out.append({"deck": deck, "mmr": None if run["mmr"] is None else round(run["mmr"]), "rank": run["rank"],
                    "rank_color": _color(run["rank"]), "games": run["games"], "tested": tested,
                    "link": f"/leaderboard/history/{run['id']}", "source": "history", "version": latest_v,
                    "grades": graded["grades"] if graded else None})
    return out


def history_run(run_id: int, path=None) -> dict | None:
    """The saved result of one history run: {"kind", "result"}, or None."""
    if history is None:
        return None
    try:
        r = next((r for r in history.runs(path=path) if r["id"] == run_id), None)
    except Exception:
        return None
    return r and {"kind": r["kind"], "result": r["result"]}


def collect(results: Path = RESULTS, web_runs: list[dict] = (), history_path=None) -> list[dict]:
    """One row per deck (latest rated run wins), best MMR first; unrated decks go last.
    A deck in the run history is shown from it; files and web runs only fill in decks it lacks."""
    by_deck: dict[str, dict] = {}
    grades: dict[str, tuple[float, dict]] = {}
    known = []
    if history is not None:
        try:
            known = from_history(history_path)
        except Exception:  # an unreadable store must not take the page down
            known = []
    in_history = {e["deck"].strip().lower() for e in known}
    rest = [e for e in [*from_files(results), *web_runs] if e["deck"].strip().lower() not in in_history]
    for e in [*known, *rest]:
        key = e["deck"].strip().lower()
        if e.get("grades") and (key not in grades or e["tested"] > grades[key][0]):
            grades[key] = (e["tested"], e["grades"])
        if e["mmr"] is None and key in by_deck:
            continue
        old = by_deck.get(key)
        if old is None or old["mmr"] is None or e["tested"] > old["tested"]:
            by_deck[key] = dict(e)
    rows = []
    for key, e in by_deck.items():
        e["grades"] = grades.get(key, (0, None))[1]
        rows.append(e)
    rows.sort(key=lambda e: (e["mmr"] is None, -(e["mmr"] or 0), e["deck"].lower()))
    for i, e in enumerate(rows, 1):
        e["place"] = i
    return rows


def _ago(ts: float, now: float) -> str:
    s = max(0, now - ts)
    for unit, n in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if s >= n:
            k = int(s // n)
            return f"{k} {unit}{'s' if k != 1 else ''} ago"
    return "just now"


def _v(r: dict) -> str:
    v = r.get("version")
    return f" <span class=ver title='version {v} of this list'>v{v}</span>" if v and v > 1 else ""


CSS = """
:root{--bg:#f6f7f9;--panel:#fff;--text:#1d2129;--muted:#5f6b7a;--line:#e3e6eb;--link:#2c64c8}
@media (prefers-color-scheme:dark){:root{--bg:#121418;--panel:#1b1e24;--text:#e7eaee;--muted:#9aa5b1;--line:#2c313a;--link:#7aa7ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px}h1{margin:0 0 4px;font-size:26px}
.sub{color:var(--muted);margin:0 0 18px}a{color:var(--link)}nav{margin-bottom:12px;font-size:14px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow-x:auto}
table{border-collapse:collapse;width:100%}th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:600}
tr:last-child td{border-bottom:0}td.n{text-align:right;font-variant-numeric:tabular-nums}
.rk{display:flex;align-items:center;gap:8px}.rk .emblem{width:28px;height:31px}
.deck{font-weight:600}.g{display:inline-block;min-width:22px;text-align:center;font-weight:700;border-radius:4px;padding:0 4px}
.gS,.gA{color:#1f8a4c}.gB{color:#4a8a1f}.gC{color:#a07a00}.gD,.gF{color:#c0392b}
.ver{color:var(--muted);font-weight:400;font-size:13px}.empty{padding:28px;text-align:center;color:var(--muted)}
"""


def render_page(rows: list[dict], now: float | None = None) -> str:
    now = time.time() if now is None else now
    e = html.escape
    show_grades = any(r["grades"] for r in rows)
    head = "<tr><th>#</th><th>Rank</th><th>Deck</th><th class=n>MMR</th>"
    head += "".join(f"<th>{label}</th>" for _, label in CRITERIA) if show_grades else ""
    head += "<th>Tested</th><th></th></tr>"
    body = []
    for r in rows:
        rank = r["rank"] or "Unrated"
        badge = emblem(rank, r["rank_color"]) if emblem and r["rank"] else ""
        cells = (f"<td class=n>{r['place']}</td><td><div class=rk>{badge}<span>{e(rank)}</span></div></td>"
                 f"<td class=deck>{e(r['deck'])}{_v(r)}</td><td class=n>{'' if r['mmr'] is None else r['mmr']}</td>")
        if show_grades:
            g = r["grades"] or {}
            cells += "".join(f"<td><span class='g g{e(g.get(k) or '')}'>{e(g.get(k) or '–')}</span></td>"
                             for k, _ in CRITERIA)
        when = datetime.fromtimestamp(r["tested"]).strftime("%Y-%m-%d %H:%M")
        cells += (f"<td title='{when}'>{_ago(r['tested'], now)}</td>"
                  f"<td><a href='{e(r['link'])}'>Results</a></td>")
        body.append(f"<tr>{cells}</tr>")
    table = (f"<table><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>" if rows else
             "<div class=empty>No decks tested yet. Run one from the <a href='/'>ladder page</a>.</div>")
    return ("<!doctype html><html><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>Deck leaderboard</title><style>{CSS}</style></head><body><main>"
            "<nav><a href='/'>← Test a deck</a></nav><h1>Leaderboard</h1>"
            "<p class=sub>Every tested deck, ranked by MMR from its latest run.</p>"
            f"<div class=panel>{table}</div></main></body></html>")


def render_assessment(d: dict) -> str:
    """A plain page for one saved assessment: its rating and the four graded criteria."""
    e = html.escape
    r = d.get("rating") or {}
    rows = "".join(f"<tr><td>{e(c.get('label', k))}</td><td><span class='g g{e(c.get('grade', ''))}'>"
                   f"{e(c.get('grade', ''))}</span></td><td class=n>{c.get('score', '')}</td>"
                   f"<td style='white-space:normal'>{e(c.get('summary', ''))}</td></tr>"
                   for k, c in d.get("criteria", {}).items())
    rating = f"{e(r['rank'])} · {r['mmr']} MMR" if r.get("rank") else "Unrated"
    return ("<!doctype html><html><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{e(d.get('deck', 'Deck'))} assessment</title><style>{CSS}</style></head><body><main>"
            f"<nav><a href='/leaderboard'>← Leaderboard</a></nav><h1>{e(d.get('deck', ''))}</h1>"
            f"<p class=sub>{rating} · assessed {e(d.get('assessed', ''))}</p><div class=panel><table>"
            f"<thead><tr><th>Criterion</th><th>Grade</th><th class=n>Score</th><th>Summary</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div></main></body></html>")
