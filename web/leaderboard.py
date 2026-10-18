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

from . import theme

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
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def can_replay(d: dict) -> bool:
    """Whether a saved ladder result has what the replay needs: pools, opponents and MMR history."""
    return all(d.get(k) for k in ("pools", "opponents", "history", "ranks"))


def ladder_entry(d: dict, tested: float, link: str, source: str) -> dict:
    return {"deck": d.get("deck") or "?", "mmr": d["mmr"], "rank": d["rank"],
            "rank_color": d.get("rank_color") or _color(d["rank"]), "games": d.get("games"),
            "tested": tested, "link": link, "source": source, "grades": None, "replay": can_replay(d)}


def from_files(results: Path = RESULTS) -> list[dict]:
    out = []
    for p in sorted((results / "ladder").glob("*.json")):
        d = _read(p)
        if d and "mmr" in d and "rank" in d and d.get("status") != "running":
            out.append(ladder_entry(d, p.stat().st_mtime, f"/leaderboard/ladder/{p.stem}", "ladder"))
    for p in sorted((results / "assess").glob("*.json")):
        d = _read(p)
        if (not d or not isinstance(d.get("criteria"), dict)
                or not all(isinstance(c, dict) for c in d["criteria"].values())
                or (d.get("rating") is not None and not isinstance(d["rating"], dict))):
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
                    "replay": run["kind"] != "assess" and can_replay(run["result"]),
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


def _badge(r: dict) -> str:
    return emblem(r["rank"], r["rank_color"]) if emblem and r["rank"] else '<i class="gem"></i>'


def _podium(rows: list[dict]) -> str:
    e = html.escape
    top = [r for r in rows if r["mmr"] is not None][:3]
    if len(top) < 3:
        return ""
    cells = "".join(
        f'<section class="frame"><div class="face"><span class="pl">{("FIRST", "SECOND", "THIRD")[i]}</span>'
        f'{_badge(r)}<a class="nm" href="{e(r["link"])}">{e(r["deck"])}</a>'
        f'<span class="mm">{e(r["rank"] or "Unrated")} · {r["mmr"]} MMR</span></div></section>' for i, r in enumerate(top))
    return f'<div class="podium">{cells}</div>'


def render_page(rows: list[dict], now: float | None = None) -> str:
    now = time.time() if now is None else now
    e = html.escape
    show_grades = any(r["grades"] for r in rows)
    head = "<tr><th>#</th><th>Rank</th><th>Deck</th><th class=n>MMR</th>"
    head += "".join(f"<th>{label}</th>" for _, label in CRITERIA) if show_grades else ""
    head += "<th>Tested</th><th>Actions</th></tr>"
    body = []
    for r in rows:
        rank = r["rank"] or "Unrated"
        deck_label = e(r["deck"])
        cells = (f"<td class=place>{r['place']}</td><td><div class=rk>{_badge(r)}<span>{e(rank)}</span></div></td>"
                 f"<td class=deck>{e(r['deck'])}{_v(r)}</td>"
                 f"<td class='n mmrv'>{'' if r['mmr'] is None else r['mmr']}</td>")
        if show_grades:
            g = r["grades"] or {}
            cells += "".join(f"<td><span class='g g{e(g.get(k) or '')}' title='{label}'>{e(g.get(k) or '–')}</span></td>"
                             for k, label in CRITERIA)
        when = datetime.fromtimestamp(r["tested"]).strftime("%Y-%m-%d %H:%M")
        play = f"<a class=play href='{e(r['link'])}?replay=1' aria-label='Replay the climb for {deck_label}' title='Replay the climb'>▶ Replay</a>" if r.get("replay") else ""
        cells += (f"<td class=note title='{when}'>{_ago(r['tested'], now)}</td>"
                  f"<td class=n>{play}<a href='{e(r['link'])}' aria-label='Results for {deck_label}'>Results ›</a></td>")
        body.append(f"<tr class=p{r['place']}>{cells}</tr>")
    table = (f"<div class=scroll><table class=lb><thead>{head}</thead><tbody>{''.join(body)}</tbody></table></div>"
             if rows else "<p class=empty>No decks tested yet. Run one from the <a href='/'>deck page</a>.</p>")
    hero = ("<div class=hero><h1>Leaderboard</h1><p>Every tested deck, ranked by MMR from its latest rated run.</p>"
            "<p class=flavor>Internal pool ranks and MMR; these are not Arena rankings.</p></div>")
    return theme.page("Deck leaderboard", hero + _podium(rows) + theme.frame("Standings", table), "leaderboard")


def render_assessment(d: dict) -> str:
    """A page for one saved assessment: its rating and the graded criteria."""
    e = html.escape
    r = d.get("rating") or {}
    rows = "".join(f"<tr><td class=deck>{e(c.get('label', k))}</td><td><span class='g g{e(c.get('grade', ''))}'>"
                   f"{e(c.get('grade', ''))}</span></td><td class=n>{e(str(c.get('score', '')))}</td>"
                   f"<td class=note style='font-size:14px'>{e(c.get('summary', ''))}</td></tr>"
                   for k, c in d.get("criteria", {}).items())
    rating = f"{e(r['rank'])} · {e(str(r.get('mmr', '')))} MMR" if r.get("rank") else "Unrated"
    badge = emblem(r["rank"], r.get("rank_color") or _color(r["rank"])) if emblem and r.get("rank") else ""
    badge = badge.replace('class="emblem"', 'class="emblem" width="72" height="80"')
    hero = (f"<a class=back href='/leaderboard'>‹ Leaderboard</a><div class=hero style='display:flex;gap:18px;"
            f"align-items:center'>{badge}"
            f"<div><h1>{e(d.get('deck', ''))}</h1><p>{rating} · assessed {e(d.get('assessed', ''))}</p></div></div>")
    table = ("<div class=scroll><table><thead><tr><th>Criterion</th><th>Grade</th><th class=n>Score</th><th>Summary</th>"
             f"</tr></thead><tbody>{rows}</tbody></table></div>")
    return theme.page(f"{d.get('deck', 'Deck')} assessment",
                      f"<div class=report>{hero}{theme.frame('Deck grades', table)}</div>", "leaderboard")


def replay_panel(d: dict) -> tuple[str, str]:
    """The replay frame for a saved ladder run: (html to put above the report, scripts for the end
    of the page), or two empty strings when the run lacks what the replay needs."""
    if not can_replay(d):
        return "", ""
    data = json.dumps(d).replace("</", "<\\/")
    panel = theme.frame("Replay the climb",
                        "<div class=replaybar><button class=go id=rp-play>▶ Replay the climb</button>"
                        "<button class=ghost id=rp-skip>Skip to result</button>"
                        "<label class=opt><input type=checkbox id=fx> Sound and haptics</label></div>"
                        "<div id=rp-host></div>", "replay")
    scripts = (f'<script type="application/json" id="run-data">{data}</script>'
               '<script src="/static/arena.js"></script><script>initReplay()</script>')
    return panel, scripts
