"""Cross-check the built-in engine against Forge: play the same matchups in both and flag
the ones where the win rates disagree by more than chance explains.

    python3 -m mtgsim.crosscheck --forge-dir ~/forge [--forge-games 40] [--python-games 500] [--jobs 4]

By default the matchups are UB Snow Control against every deck in the rank pools
(decks/ranks/, or the older decks/tiers/ when the ranks aren't there), plus a round robin
inside each rank. Results are saved to results/cross_check/results.json as they finish,
so an interrupted run picks up where it stopped; report.md is rewritten from that file.

A big disagreement points at something wrong in one engine: a card the built-in engine
only partly simulates, a rules bug, or a misplay by one of the AIs. The "partial cards"
columns say how many distinct cards in each deck have rules text the built-in engine ignores.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
from pathlib import Path

from .carddb import CardDB
from .decklist import load_deck
from .forge import ForgeError, run_forge_match
from .runner import build_deck, run_match, wilson
try:  # the seven ranks (Bronze to Grandmaster) replace the five tiers
    from .ranks import RANKS as POOLS
except ImportError:
    from .tiers import TIERS as POOLS

ROOT = Path(__file__).resolve().parent.parent
UB_SNOW = ROOT / "results" / "ub_snow_control" / "decks" / "ub_snow_control.txt"
OUT = ROOT / "results" / "cross_check"


def default_matchups() -> list[tuple[str, Path, str, Path]]:
    """UB Snow vs every rank deck, then every pair inside each rank."""
    pairs = []
    for t in POOLS:
        for p in t.decks():
            pairs.append(("ub_snow_control", UB_SNOW, f"{t.key}/{p.stem}", p))
    for t in POOLS:
        for a, b in itertools.combinations(t.decks(), 2):
            pairs.append((f"{t.key}/{a.stem}", a, f"{t.key}/{b.stem}", b))
    return pairs


def z_score(p1: float, n1: int, p2: float, n2: int) -> float:
    """Two-proportion z statistic for p1 - p2 (pooled variance)."""
    if not n1 or not n2:
        return 0.0
    p = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = math.sqrt(max(p * (1 - p), 1e-9) * (1 / n1 + 1 / n2))
    return (p1 - p2) / se


def partial_cards(db: CardDB, counts: dict[str, int]) -> tuple[int, int, list[str]]:
    """(distinct cards with ignored text, distinct cards, their names) in the built-in engine."""
    deck = build_deck(db, counts)
    distinct = {c.name: c for c in deck}
    part = sorted(n for n, c in distinct.items() if c.unsupported)
    return len(part), len(distinct), part


def load_results(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def save_results(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")


def record(res) -> dict:
    return {"games": res.games, "wins_a": res.wins_a, "wins_b": res.wins_b, "draws": res.draws,
            "win_rate_a": round(res.win_rate_a, 4)}


def classify(row: dict, min_gap: float, min_z: float) -> str:
    gap, z = row["gap"], row["z"]
    if abs(gap) >= min_gap and abs(z) >= min_z:
        return "DISAGREE"
    if abs(z) >= 2:
        return "minor"
    return ""


def build_rows(pairs, data, partial, min_gap, min_z) -> list[dict]:
    rows = []
    for a, _, b, _ in pairs:
        r = data.get(f"{a} vs {b}", {})
        py, fg = r.get("python"), r.get("forge")
        if not py or not fg:
            continue
        p1, n1, p2, n2 = py["win_rate_a"], py["games"], fg["win_rate_a"], fg["games"]
        row = {"a": a, "b": b, "python": p1, "python_games": n1, "forge": p2, "forge_games": n2,
               "forge_draws": fg["draws"], "gap": p1 - p2, "z": z_score(p1, n1, p2, n2),
               "forge_ci": wilson(fg["wins_a"] + 0.5 * fg["draws"], n2),
               "partial_a": partial[a][:2], "partial_b": partial[b][:2]}
        row["flag"] = classify(row, min_gap, min_z)
        rows.append(row)
    return rows


def write_report(rows, partial, path: Path, min_gap: float, min_z: float, settings: str):
    flagged = sorted((r for r in rows if r["flag"] == "DISAGREE"), key=lambda r: -abs(r["gap"]))
    gaps = [abs(r["gap"]) for r in rows]
    out = [
        "# Built-in engine vs Forge",
        "",
        f"{len(rows)} matchups played in both engines ({settings}). Win rates are for the first deck,",
        "draws counted as half a win. A matchup is flagged when the engines differ by at least "
        f"{min_gap:.0%} and the difference is beyond chance (|z| ≥ {min_z}).",
        "",
        f"- Flagged: **{len(flagged)}** of {len(rows)}",
        f"- Median gap {sorted(gaps)[len(gaps) // 2]:.0%}, mean gap {sum(gaps) / max(len(gaps), 1):.0%}"
        if gaps else "- No matchups finished yet",
        "",
        "Partial cards = distinct cards whose rules text the built-in engine partly ignores / distinct cards.",
        "",
        "## Flagged matchups, biggest gap first",
        "",
        "| Matchup | Built-in | Forge (95% range) | Gap | z | Partial cards (A / B) |",
        "|---|---|---|---|---|---|",
    ]
    for r in flagged:
        out.append(f"| {r['a']} vs {r['b']} | {r['python']:.0%} | {r['forge']:.0%} "
                   f"({r['forge_ci'][0]:.0%}–{r['forge_ci'][1]:.0%}) | {r['gap']:+.0%} | {r['z']:+.1f} "
                   f"| {r['partial_a'][0]}/{r['partial_a'][1]} / {r['partial_b'][0]}/{r['partial_b'][1]} |")
    out += ["", "## All matchups", "",
            "| Matchup | Built-in | Forge | Gap | z | Flag |", "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['a']} vs {r['b']} | {r['python']:.0%} | {r['forge']:.0%} | {r['gap']:+.0%} "
                   f"| {r['z']:+.1f} | {r['flag']} |")
    out += ["", "## Partly simulated cards per deck (built-in engine)", ""]
    for name, (n, total, names) in sorted(partial.items()):
        out.append(f"- **{name}** {n}/{total}" + (f": {', '.join(names)}" if names else ""))
    path.write_text("\n".join(out) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mtgsim.crosscheck", description=__doc__.split("\n\n")[0])
    ap.add_argument("--forge-dir", help="Forge install folder (or set FORGE_HOME)")
    ap.add_argument("--forge-games", type=int, default=40)
    ap.add_argument("--python-games", type=int, default=500)
    ap.add_argument("--jobs", type=int, default=4, help="Java processes per Forge matchup")
    ap.add_argument("--clock", type=int, default=120, help="Forge: seconds before a game is a draw")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--min-gap", type=float, default=0.15, help="flag gaps at least this big (default 0.15)")
    ap.add_argument("--min-z", type=float, default=3.0, help="flag only beyond this |z| (default 3)")
    ap.add_argument("--skip-forge", action="store_true", help="only (re)run the built-in engine")
    ap.add_argument("--rerun", action="store_true", help="replay matchups that already have results")
    ap.add_argument("--only", nargs="+", metavar="TEXT", help="only matchups whose names contain all of these")
    args = ap.parse_args(argv)

    pairs = default_matchups()
    if args.only:
        pairs = [p for p in pairs if all(t in f"{p[0]} vs {p[2]}" for t in args.only)]
    results_path = args.out / "results.json"
    data = load_results(results_path)
    db = CardDB(offline=True)
    counts = {}
    for a, pa, b, pb in pairs:
        counts.setdefault(a, load_deck(pa)[1])
        counts.setdefault(b, load_deck(pb)[1])
    partial = {n: partial_cards(db, c) for n, c in counts.items()}
    decks = {n: build_deck(db, c) for n, c in counts.items()}

    for i, (a, _, b, _) in enumerate(pairs, 1):
        key = f"{a} vs {b}"
        entry = data.setdefault(key, {})
        if args.rerun or "python" not in entry or entry["python"]["games"] != args.python_games:
            res, _ = run_match(a, decks[a], b, decks[b], games=args.python_games, seed=args.seed)
            entry["python"] = record(res)
            save_results(results_path, data)
        if not args.skip_forge and (args.rerun or "forge" not in entry
                                    or entry["forge"]["games"] < args.forge_games):
            print(f"[{i}/{len(pairs)}] Forge {key}", file=sys.stderr, flush=True)
            try:
                res = run_forge_match(a, counts[a], b, counts[b], games=args.forge_games, seed=args.seed,
                                      forge_dir=args.forge_dir, clock=args.clock, jobs=args.jobs)
            except ForgeError as e:
                print(f"  skipped: {e}", file=sys.stderr)
                continue
            entry["forge"] = record(res)
            save_results(results_path, data)
            print(f"  built-in {entry['python']['win_rate_a']:.0%}, Forge {res.win_rate_a:.0%}",
                  file=sys.stderr, flush=True)

    rows = build_rows(pairs, data, partial, args.min_gap, args.min_z)
    settings = (f"built-in engine {args.python_games} games, Forge {args.forge_games} games per matchup, "
                f"seed {args.seed}")
    write_report(rows, partial, args.out / "report.md", args.min_gap, args.min_z, settings)
    print(f"Wrote {args.out / 'report.md'}: {sum(r['flag'] == 'DISAGREE' for r in rows)} of "
          f"{len(rows)} matchups flagged")


if __name__ == "__main__":
    main()
