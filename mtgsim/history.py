"""Run history: every ladder, rank and assessment run of a deck, so versions of a deck can be compared.

    python3 -m mtgsim.history                          # every deck tested, newest first
    python3 -m mtgsim.history show DECK                # a deck's versions and runs
    python3 -m mtgsim.history compare DECK [V1 [V2]]   # what changed between two versions (default: last two)

Runs are kept in a small SQLite file, results/history.sqlite3 (MTGSIM_HISTORY sets another path).
The CLI (--ladder, --rank, mtgsim.assess) and the web page record a run when it finishes.

A deck is known by its name (the decklist file's stem, or the name typed on the web page). A
version of it is its exact main deck: fingerprint(counts) hashes the sorted card counts, so the same
list always gets the same fingerprint and any change in a card or count gets a new one. Versions are
numbered 1, 2, 3 ... per deck name in the order they were first tested.

API for other modules (all rows are plain dicts):

    record_ladder(tracker.to_dict(), counts, engine="python", source="cli") -> run id
    record_assessment(assess(...), counts, engine="python", source="cli") -> run id
    decks()          -> one row per deck name: {"deck", "versions", "runs", "last_run",
                        "latest": {"version", "fingerprint", "mmr", "rank", "kind", "engine", "games",
                                   "grades", "created"} (latest rated run of the latest version) or None,
                        "best": {"version", "mmr", "rank", ...} (highest-MMR run of any version) or None}
    versions(deck)   -> [{"version", "fingerprint", "first_seen", "cards" {name: count}, "runs" [...]}]
    runs(deck=None)  -> [{"id", "deck", "version", "fingerprint", "kind" ("ladder"|"rank"|"assess"),
                          "engine", "source", "created" (ISO UTC), "mmr", "rank", "games",
                          "grades" {criterion: grade} or {}, "scores" {criterion: 0-100} or {},
                          "verdict", "result" (the full ladder dict or assessment)}]  newest first
    compare(deck, a=None, b=None) -> {"deck", "from", "to", "added", "removed", "changed", "mmr", "rank",
                          "grades", "scores"}   (a, b: version numbers or fingerprints; default the last two)

Every function takes path=None to use another store (tests use a temporary file).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "results" / "history.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS versions (
    deck TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    version INTEGER NOT NULL,
    cards TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    PRIMARY KEY (deck, fingerprint)
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deck TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    kind TEXT NOT NULL,
    engine TEXT NOT NULL,
    source TEXT NOT NULL,
    created TEXT NOT NULL,
    mmr INTEGER,
    rank TEXT,
    games INTEGER,
    grades TEXT NOT NULL,
    scores TEXT NOT NULL,
    verdict TEXT NOT NULL,
    result TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_deck ON runs (deck, created);
"""


def store_path(path=None) -> Path:
    return Path(path or os.environ.get("MTGSIM_HISTORY") or DEFAULT_PATH)


def _connect(path=None) -> sqlite3.Connection:
    p = store_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def fingerprint(counts: dict[str, int]) -> str:
    """Short hash of a main deck: the same cards and counts give the same fingerprint,
    whatever the order or capitalisation of the list."""
    merged: dict[str, int] = {}
    for name, n in counts.items():
        if n:
            key = " ".join(name.lower().split())
            merged[key] = merged.get(key, 0) + n
    text = "\n".join(f"{n} {name}" for name, n in sorted(merged.items()))
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record(deck: str, counts: dict[str, int], kind: str, result: dict, *, engine: str = "python",
           source: str = "cli", mmr=None, rank=None, games=None, grades=None, scores=None, verdict: str = "",
           path=None) -> int:
    """Store one finished run and return its id. Most callers want record_ladder or record_assessment."""
    fp = fingerprint(counts)
    now = _now()
    with _connect(path) as con:
        # Serialize version allocation across independent CLI/web sessions. The
        # existence check and MAX(version) must see the same locked snapshot.
        con.execute("BEGIN IMMEDIATE")
        if not con.execute("SELECT 1 FROM versions WHERE deck = ? AND fingerprint = ?", (deck, fp)).fetchone():
            n = con.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM versions WHERE deck = ?", (deck,)).fetchone()[0]
            con.execute("INSERT INTO versions VALUES (?, ?, ?, ?, ?)",
                        (deck, fp, n, json.dumps(dict(sorted(counts.items()))), now))
        cur = con.execute(
            "INSERT INTO runs (deck, fingerprint, kind, engine, source, created, mmr, rank, games, grades, scores, "
            "verdict, result) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (deck, fp, kind, engine, source, now, None if mmr is None else round(mmr), rank, games,
             json.dumps(grades or {}), json.dumps(scores or {}), verdict or "", json.dumps(result)))
        return cur.lastrowid


def record_ladder(d: dict, counts: dict[str, int], *, engine: str = "python", source: str = "cli",
                  deck: str | None = None, path=None) -> int:
    """Store a finished ladder or rank run: d is LadderTracker.to_dict()."""
    return record(deck or d["deck"], counts, "ladder" if d.get("ladder") else "rank", d, engine=engine,
                  source=source, mmr=d.get("mmr"), rank=d.get("rank"), games=d.get("games"),
                  verdict=d.get("verdict", ""), path=path)


def record_assessment(a: dict, counts: dict[str, int], *, engine: str = "python", source: str = "cli",
                      deck: str | None = None, path=None) -> int:
    """Store a finished assessment: a is what mtgsim.assess.assess() returns."""
    r = a.get("rating") or {}
    crit = a.get("criteria", {})
    games = sum(m.get("games") or 0 for m in crit.get("meta", {}).get("details", {}).get("matchups", [])) or None
    return record(deck or a["deck"], counts, "assess", a, engine=engine, source=source, mmr=r.get("mmr"),
                  rank=r.get("rank"), games=games,
                  grades={k: c["grade"] for k, c in crit.items()}, scores={k: c["score"] for k, c in crit.items()},
                  path=path)


def try_record(fn, *args, **kwargs) -> int | None:
    """Call record_ladder / record_assessment without letting a history problem fail the run."""
    try:
        return fn(*args, **kwargs)
    except (sqlite3.Error, OSError) as e:
        print(f"Run history not saved: {e}", file=sys.stderr)
        return None


# ------------------------------------------------------------------ reading
def _version_numbers(con, deck=None) -> dict[tuple[str, str], int]:
    q, args = "SELECT deck, fingerprint, version FROM versions", ()
    if deck is not None:
        q, args = q + " WHERE deck = ?", (deck,)
    return {(r["deck"], r["fingerprint"]): r["version"] for r in con.execute(q, args)}


def _run_row(r, nums) -> dict:
    return {"id": r["id"], "deck": r["deck"], "version": nums.get((r["deck"], r["fingerprint"])),
            "fingerprint": r["fingerprint"], "kind": r["kind"], "engine": r["engine"], "source": r["source"],
            "created": r["created"], "mmr": r["mmr"], "rank": r["rank"], "games": r["games"],
            "grades": json.loads(r["grades"]), "scores": json.loads(r["scores"]), "verdict": r["verdict"],
            "result": json.loads(r["result"])}


def runs(deck: str | None = None, path=None) -> list[dict]:
    """Every run (of one deck, if given), newest first."""
    with _connect(path) as con:
        nums = _version_numbers(con, deck)
        q, args = "SELECT * FROM runs", ()
        if deck is not None:
            q, args = q + " WHERE deck = ?", (deck,)
        return [_run_row(r, nums) for r in con.execute(q + " ORDER BY created DESC, id DESC", args)]


def versions(deck: str, path=None) -> list[dict]:
    """A deck's versions, oldest first, each with its runs (newest first)."""
    all_runs = runs(deck, path)
    with _connect(path) as con:
        rows = con.execute("SELECT * FROM versions WHERE deck = ? ORDER BY version", (deck,)).fetchall()
    return [{"version": r["version"], "fingerprint": r["fingerprint"], "first_seen": r["first_seen"],
             "cards": json.loads(r["cards"]), "runs": [x for x in all_runs if x["fingerprint"] == r["fingerprint"]]}
            for r in rows]


def _summary(run: dict | None) -> dict | None:
    if not run:
        return None
    return {k: run[k] for k in ("version", "fingerprint", "mmr", "rank", "kind", "engine", "games", "grades",
                                "created")}


def decks(path=None) -> list[dict]:
    """One row per deck tested, most recently run first: its latest version's latest rated run
    (the deck's current standing) and its best run of any version."""
    by_deck: dict[str, list[dict]] = {}
    for r in runs(path=path):
        by_deck.setdefault(r["deck"], []).append(r)
    out = []
    for deck, rs in by_deck.items():
        latest_v = max(r["version"] for r in rs)
        rated = [r for r in rs if r["mmr"] is not None]
        current = [r for r in rated if r["version"] == latest_v]
        out.append({"deck": deck, "versions": latest_v, "runs": len(rs), "last_run": rs[0]["created"],
                    "latest": _summary(current[0] if current else None),
                    "best": _summary(max(rated, key=lambda r: r["mmr"]) if rated else None)})
    return out


def _pick(vs: list[dict], key) -> dict:
    key = str(key).lstrip("v") if str(key)[1:].isdigit() else str(key)
    for v in vs:
        if str(v["version"]) == key:
            return v
    for v in vs:
        if v["fingerprint"].startswith(key):
            return v
    raise KeyError(f"no version {key}; versions are " + ", ".join(str(v["version"]) for v in vs))


def _latest(v: dict, kinds) -> dict | None:
    return next((r for r in v["runs"] if r["kind"] in kinds and r["mmr"] is not None), None)


def compare(deck: str, a=None, b=None, path=None) -> dict:
    """What changed from version a to version b of a deck (default: the two newest versions):
    the cards, and the MMR, rank, grades and scores of each version's latest run."""
    vs = versions(deck, path)
    if not vs:
        raise KeyError(f"no runs recorded for {deck}")
    if a is None and b is None:
        old, new = (vs[-2] if len(vs) > 1 else vs[-1]), vs[-1]
    else:
        old, new = _pick(vs, a), _pick(vs, vs[-1]["version"] if b is None else b)
    names = sorted(set(old["cards"]) | set(new["cards"]))
    added = {n: new["cards"][n] for n in names if n not in old["cards"]}
    removed = {n: old["cards"][n] for n in names if n not in new["cards"]}
    changed = {n: [old["cards"][n], new["cards"][n]] for n in names
               if n in old["cards"] and n in new["cards"] and old["cards"][n] != new["cards"][n]}

    def side(v):
        ladder = _latest(v, ("ladder", "rank"))
        assessed = next((r for r in v["runs"] if r["kind"] == "assess"), None)
        rated = _latest(v, ("ladder", "rank", "assess"))
        return {"version": v["version"], "fingerprint": v["fingerprint"], "runs": len(v["runs"]),
                "mmr": rated and rated["mmr"], "rank": rated and rated["rank"], "rated_by": rated and rated["kind"],
                "ladder": _summary(ladder), "assessment": _summary(assessed),
                "grades": assessed["grades"] if assessed else {}, "scores": assessed["scores"] if assessed else {}}

    f, t = side(old), side(new)
    crit = list(dict.fromkeys(list(f["scores"]) + list(t["scores"])))
    return {"deck": deck, "from": f, "to": t, "added": added, "removed": removed, "changed": changed,
            "mmr": {"from": f["mmr"], "to": t["mmr"],
                    "delta": t["mmr"] - f["mmr"] if None not in (f["mmr"], t["mmr"]) else None},
            "rank": {"from": f["rank"], "to": t["rank"]},
            "grades": {k: [f["grades"].get(k), t["grades"].get(k)] for k in crit},
            "scores": {k: [f["scores"].get(k), t["scores"].get(k)] for k in crit}}


# ------------------------------------------------------------------ text
def _when(iso: str) -> str:
    return iso.replace("T", " ")[:16]


def _rating(r: dict | None) -> str:
    return f"{r['rank']} {r['mmr']}" if r and r.get("mmr") is not None else "unrated"


def format_decks(rows: list[dict]) -> str:
    if not rows:
        return "No runs recorded yet. Ladder, rank and assessment runs are saved here when they finish."
    out = [f"{'Deck':<28} {'Now':<18} {'Best':<18} {'Versions':>8} {'Runs':>5}  Last run"]
    for d in rows:
        out.append(f"{d['deck']:<28} {_rating(d['latest']):<18} {_rating(d['best']):<18} "
                   f"{d['versions']:>8} {d['runs']:>5}  {_when(d['last_run'])}")
    return "\n".join(out)


def format_versions(deck: str, vs: list[dict]) -> str:
    if not vs:
        return f"No runs recorded for {deck}."
    out = [f"{deck}: {len(vs)} version(s)"]
    for v in vs:
        out.append(f"  v{v['version']}  {v['fingerprint']}  {sum(v['cards'].values())} cards, "
                   f"first tested {_when(v['first_seen'])}")
        for r in v["runs"]:
            grades = " ".join(f"{k} {g}" for k, g in r["grades"].items())
            games = f", {r['games']} games" if r["games"] else ""
            out.append(f"      {_when(r['created'])}  {r['kind']:<6} {r['engine']:<6} {_rating(r):<18}"
                       f"{games}{'  ' + grades if grades else ''}")
    return "\n".join(out)


def format_compare(c: dict) -> str:
    f, t = c["from"], c["to"]
    out = [f"{c['deck']}: v{f['version']} ({f['fingerprint']}) -> v{t['version']} ({t['fingerprint']})"]
    if f["version"] == t["version"]:
        out.append("  Only one version recorded; showing it on both sides.")
    if c["added"] or c["removed"] or c["changed"]:
        out.append("  Cards:")
        out += [f"    + {n} {name}" for name, n in c["added"].items()]
        out += [f"    - {n} {name}" for name, n in c["removed"].items()]
        out += [f"    ~ {name}: {a} -> {b}" for name, (a, b) in c["changed"].items()]
    elif f["version"] != t["version"]:
        out.append("  Cards: no change")
    m = c["mmr"]
    delta = f" ({m['delta']:+d})" if m["delta"] is not None else ""
    out.append(f"  MMR:  {_rating(f)} -> {_rating(t)}{delta}")
    for k, (ga, gb) in c["grades"].items():
        sa, sb = c["scores"][k]
        fmt = lambda g, s: f"{g} ({s})" if g else "-"
        out.append(f"  {k.capitalize():<12} {fmt(ga, sa):>8} -> {fmt(gb, sb)}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mtgsim.history", description="Past runs of each deck, and how versions compare.")
    ap.add_argument("command", nargs="?", default="list", choices=["list", "show", "compare"])
    ap.add_argument("deck", nargs="?", help="deck name (the decklist file name without .txt)")
    ap.add_argument("versions", nargs="*", help="compare: two version numbers or fingerprints (default the last two)")
    ap.add_argument("--db", help=f"history file (default {DEFAULT_PATH}, or MTGSIM_HISTORY)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = ap.parse_args(argv)
    if args.command != "list" and not args.deck:
        ap.error(f"{args.command} needs a deck name")
    if args.deck and args.deck.endswith(".txt"):
        args.deck = Path(args.deck).stem
    try:
        if args.command == "list":
            data, text = decks(args.db), format_decks
        elif args.command == "show":
            data, text = versions(args.deck, args.db), lambda v: format_versions(args.deck, v)
        else:
            if len(args.versions) > 2:
                ap.error("compare takes at most two versions")
            data, text = compare(args.deck, *args.versions, path=args.db), format_compare
    except KeyError as e:
        sys.exit(str(e).strip("'\""))
    print(json.dumps(data, indent=2) if args.json else text(data))


if __name__ == "__main__":
    main()
