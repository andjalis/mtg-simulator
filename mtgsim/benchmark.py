"""Run a small, auditable main-deck benchmark; neither simulator is ground truth.

    python3 -m mtgsim.benchmark --engine both --forge-dir ~/forge -n 20 --out results/benchmark
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import subprocess
import uuid

from .carddb import CardDB
from .coverage import deck_coverage, format_coverage
from .decklist import load_deck
from .forge import ForgeError, run_forge_match
from .provenance import (ROOT, artifacts, atomic_json, deck_identity, digest,
                         output_lock, runtime_identity, valid_artifacts)
from .runner import build_deck, run_match, wilson

DEFAULT_MANIFEST = ROOT / "benchmarks" / "small.json"
LIMITATIONS = (
    "Main-deck games only; no sideboarding or BO3 match prediction. "
    "Results measure deck + rules implementation + AI pilot under these settings. "
    "Forge is an independent comparator, not ground truth. Both pilots can misplay, especially "
    "control and combo; agreement cannot establish human accuracy. Confidence intervals describe "
    "sampling uncertainty under an independent-game model, not rules errors or pilot bias. "
    "Ranks and MMR elsewhere in this project are internal pool scores, not Arena equivalents."
)


def load_manifest(path: Path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema") != 1:
        raise ValueError("Unsupported benchmark manifest schema")
    decks = {}
    for item in manifest["decks"]:
        name = item["id"]
        if not re.fullmatch(r"[a-z0-9_-]+", name) or name in decks:
            raise ValueError(f"Invalid or duplicate deck id: {name}")
        deck_path = (path.parent / item["path"]).resolve()
        counts = load_deck(deck_path)[1]
        if not counts or any(n <= 0 for n in counts.values()):
            raise ValueError(f"Empty or invalid deck: {name}")
        decks[name] = {**item, **deck_identity(deck_path, counts)}
    pairs = manifest["matchups"]
    if not pairs or len({tuple(p) for p in pairs}) != len(pairs):
        raise ValueError("Missing or duplicate matchups")
    for pair in pairs:
        if len(pair) != 2 or pair[0] == pair[1] or any(n not in decks for n in pair):
            raise ValueError(f"Invalid matchup: {pair}")
    # Only explicitly curated, exact-list game evidence may supply a human expectation.
    # A URL is provenance, not automatic source verification: curators must review it.
    for evidence in manifest.get("human_evidence", []):
        a, b = evidence["matchup"]
        if [a, b] not in pairs or evidence["unit"] != "main_deck_game":
            raise ValueError("Human evidence must concern a manifest matchup and main-deck games, never BO3 matches")
        if evidence["deck_sha256"] != [decks[a]["sha256"], decks[b]["sha256"]]:
            raise ValueError("Human evidence does not match the exact deck files")
        for field in ("source_url", "event", "format", "date", "applicability", "reviewed_by"):
            if not isinstance(evidence.get(field), str) or not evidence[field].strip():
                raise ValueError(f"Human evidence needs {field}")
        if not evidence["source_url"].startswith(("https://", "http://")):
            raise ValueError("Human evidence needs an actual source URL")
        if any(type(evidence.get(k)) is not int or evidence[k] < 0 for k in ("wins_a", "wins_b", "draws")):
            raise ValueError("Human evidence needs nonnegative integer game outcomes")
        if not sum(evidence[k] for k in ("wins_a", "wins_b", "draws")):
            raise ValueError("Human evidence needs observed games")
    return manifest, decks


def record(res) -> dict:
    if res.games < 1 or res.wins_a + res.wins_b + res.draws != res.games:
        raise ValueError("Invalid result counts")
    splits = {}
    for label, n, wins, draws in (
            ("play", res.games_a_on_play, res.wins_a_on_play, res.draws_a_on_play),
            ("draw", res.games_a_on_draw, res.wins_a_on_draw, res.draws_a_on_draw)):
        splits[label] = dict(games=n, wins=wins, losses=n-wins-draws, draws=draws,
                             win_ci95=list(wilson(wins, n)), win_probability=wins/n if n else None)
    return {**asdict(res), "splits": splits,
            "unknown_first_player": res.games - res.games_a_on_play - res.games_a_on_draw,
            "turn_unit": "player-turn", "unknown_game_length": res.games - len(res.turns),
            "win_probability_a": res.wins_a / res.games,
            "win_ci95": list(wilson(res.wins_a, res.games)),
            "score_a": res.win_rate_a, "draw_rate": res.draws / res.games}


def reusable(entry, games, folder):
    if not entry or entry.get("status") != "complete":
        return False
    r = entry.get("result", {})
    return (r.get("games") == games and
            all(type(r.get(k)) is int and r[k] >= 0 for k in ("wins_a", "wins_b", "draws")) and
            sum(r[k] for k in ("wins_a", "wins_b", "draws")) == games and
            entry.get("result_sha256") == digest(r) and
            valid_artifacts(folder, entry.get("artifacts", {})))


def write_report(path: Path, state: dict):
    manifest = state["manifest"]
    out = [f"# {manifest['name']}", "", f"Status: {state['status']}. Run identity: `{state['identity']}`.", "",
           manifest["scope"], "", LIMITATIONS, "", "## Coverage and human evidence", ""]
    out += [f"- Missing coverage: {gap}" for gap in manifest.get("missing_coverage", [])]
    if "combo" not in {d["archetype"] for d in state["decks"].values()}:
        out.append("- Combo coverage is missing; this benchmark cannot validate combo play.")
    out += [f"- {manifest['missing_evidence']}",
            "- Human expectations are absent for every matchup without reviewed, applicable game evidence.",
            "- Repository deck comments are not evidence of format legality or tournament provenance.", ""]
    for e in manifest.get("human_evidence", []):
        n = sum(e[k] for k in ("wins_a", "wins_b", "draws"))
        lo, hi = wilson(e["wins_a"], n)
        out += [f"Human evidence ({' vs '.join(e['matchup'])}): {e['wins_a']}/{n} wins, {e['draws']} draws; "
                f"95% Wilson interval {lo:.1%}–{hi:.1%}. [Source]({e['source_url']}); "
                f"{e['event']}, {e['format']}, {e['date']}; reviewed by {e['reviewed_by']}. {e['applicability']}", ""]
    settings = state["provenance"]["settings"]
    out += ["## Run configuration", "",
            f"Engines: {', '.join(settings['engines'])}; {settings['games']} games per pairing/engine; "
            f"seed {settings['seed']}; Forge jobs {settings['jobs']}, game clock {settings['clock']} s, "
            f"worker wall timeout {settings['worker_timeout'] or 'automatic'}.", "",
            "Full content fingerprints, settings and counts: [results.json](results.json).", ""]
    for name, deck in state["decks"].items():
        out.append(f"- {name} ({deck['archetype']}): {sum(deck['main_deck'].values())} main-deck cards. "
                   f"{deck.get('reason', '')}")
    out += ["", "## Simulated games", "",
            "A win probability counts draws as non-wins; its 95% Wilson interval uses all games. "
            "Score = (wins + half draws) / games and is displayed separately. Small samples are diagnostic only.", "",
            "| Matchup (A vs B) | Engine | W–L–D | A win probability (95% CI) | A score | Review logs |",
            "|---|---|---|---|---|---|"]
    for key, entry in sorted(state["results"].items()):
        if entry["status"] != "complete":
            out.append(f"| {key} | failed/incomplete | — | — | — | {entry.get('error', '')} |")
            continue
        r = entry["result"]
        lo, hi = r["win_ci95"]
        logs = ", ".join(f"[{Path(p).name}]({p})" for p in entry["artifacts"] if p.endswith(".log"))
        out.append(f"| {r['deck_a']} vs {r['deck_b']} | {entry['engine']} | "
                   f"{r['wins_a']}–{r['wins_b']}–{r['draws']} | {r['win_probability_a']:.1%} "
                   f"({lo:.1%}–{hi:.1%}) | {r['score_a']:.1%} | {logs} |")
    out += ["", "### Observed first-player balance and game length", "",
            "Each split gives W–L–D and A's win probability with a 95% Wilson interval; draws count as non-wins. "
            "Unknown first players are excluded from both splits. Turn units are individual player-turns.", "",
            "| Matchup / engine | A on play | A on draw | Unknown first | Mean player-turns (known games) |",
            "|---|---|---|---|---|"]
    for key, entry in sorted(state["results"].items()):
        if entry["status"] != "complete":
            continue
        r = entry["result"]
        cells = []
        for label in ("play", "draw"):
            split = r["splits"][label]
            lo, hi = split["win_ci95"]
            cells.append(f"{split['wins']}–{split['losses']}–{split['draws']}; "
                         f"{split['win_probability']:.1%} ({lo:.1%}–{hi:.1%})" if split["games"] else "no observations")
        length = f"{sum(r['turns']) / len(r['turns']):.1f} ({len(r['turns'])}/{r['games']})" if r["turns"] else "unknown"
        out.append(f"| {key} | {' | '.join(cells)} | {r['unknown_first_player']} | {length} |")
    out += ["", "Builtin alternates the first player (A starts the first game; odd samples are unbalanced). "
            "Forge first player and length are parsed conservatively from full logs; quiet or incomplete metadata stays unknown. "
            "Forge starting players are observed, not forced balanced; reversing seats would not guarantee balance. "
            "Seeds are engine-specific, not paired random games. "
            "Forge uses fresh default settings per worker; jobs changes partitioning and seeds. "
            "Builtin draws include the turn cap; Forge draws can include clock expirations or internal "
            "errors. Raw logs need review to distinguish causes.", "", "## Engine comparison", ""]
    for a, b in manifest["matchups"]:
        py = state["results"].get(f"{a}-vs-{b}/builtin", {})
        fg = state["results"].get(f"{a}-vs-{b}/forge", {})
        if py.get("status") == fg.get("status") == "complete":
            gap = py["result"]["win_probability_a"] - fg["result"]["win_probability_a"]
            out.append(f"- {a} vs {b}: builtin − Forge win-probability gap {gap:+.1%}. "
                       "Inspect both intervals and logs; no accuracy verdict follows from this gap.")
        else:
            out.append(f"- {a} vs {b}: comparison missing (both engines must finish).")
    out += ["", "## Builtin card coverage", "",
            "Template coverage is not a rules-correctness guarantee. Details also apply when only Forge ran.", ""]
    for name, details in state["coverage"].items():
        out += ["```text", details, "```", ""]
    out += ["## Review procedure", "", "1. Check coverage gaps, deck sizes, settings and missing human evidence.",
            "2. Read each retained builtin game log and Forge worker log; inspect mulligans, mana, targets, "
            "combat, sweepers, win conditions, draws and exceptions. Logs are not automatically adjudicated.",
            "3. Reproduce suspicious decisions with these decks/seeds; add rules regression tests or "
            "pilot comparisons before interpreting win-rate changes.",
            "4. Use a new output directory for changed inputs/settings or independent seeds. "
            "Only compare to reviewed, applicable main-deck human games; BO3 matches cannot supply that baseline."]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def run(args):
    engines = ["builtin", "forge"] if args.engine == "both" else [args.engine]
    manifest, decks = load_manifest(args.manifest)
    print("Fingerprinting code, decks, card data and selected runtime resources…", flush=True)
    runtime = runtime_identity("forge" in engines, args.forge_dir, args.java)
    settings = {"engines": engines, "games": args.games, "seed": args.seed, "jobs": args.jobs,
                "clock": args.clock, "worker_timeout": args.worker_timeout, "offline": True,
                "builtin_logs": getattr(args, "builtin_logs", "first")}
    provenance = {"manifest": manifest, "decks": decks, "runtime": runtime, "settings": settings}
    identity = digest(provenance)
    out = args.out
    with output_lock(out):
        checkpoint = out / "results.json"
        if checkpoint.exists():
            state = json.loads(checkpoint.read_text())
            if state.get("identity") != identity or state.get("status") == "invalid":
                raise ValueError("Resume refused: inputs/code/data/runtime/settings changed or run invalid. Use a new --out directory.")
        else:
            state = {"schema": 1, "identity": identity, "provenance": provenance, "manifest": manifest,
                     "decks": decks, "results": {}, "coverage": {}, "status": "running",
                     "created": datetime.now(timezone.utc).isoformat()}
        db = CardDB(offline=True)
        built = {}
        for name, deck in decks.items():
            rows = deck_coverage(db, deck["main_deck"])
            state["coverage"][name] = format_coverage(name, rows)
            if "builtin" in engines:
                built[name] = build_deck(db, deck["main_deck"])
        state["status"] = "running"
        # Invalidate missing/corrupted artifacts before showing any resumed results.
        for key, entry in state["results"].items():
            if not reusable(entry, args.games, out):
                entry["status"] = "incomplete"
        atomic_json(checkpoint, state)
        write_report(out / "report.md", state)
        for a, b in manifest["matchups"]:
            for engine in engines:
                key = f"{a}-vs-{b}/{engine}"
                if reusable(state["results"].get(key), args.games, out):
                    print(f"Reuse {key}", flush=True)
                    continue
                attempt = out / "logs" / f"{a}-vs-{b}" / engine / uuid.uuid4().hex[:12]
                attempt.mkdir(parents=True)
                print(f"Run {key}: {args.games} games", flush=True)
                entry = {"engine": engine, "status": "failed", "log_dir": str(attempt.relative_to(out))}
                try:
                    if engine == "builtin":
                        def save_log(number, events):
                            (attempt / f"game-{number:04d}.log").write_text("\n".join(events) + "\n", encoding="utf-8")
                        result, log = run_match(a, built[a], b, built[b], games=args.games,
                                                seed=args.seed, log_first=True,
                                                log_game=save_log if settings["builtin_logs"] == "all" else None)
                        if settings["builtin_logs"] == "first":
                            (attempt / "first-game.log").write_text("\n".join(log) + "\n", encoding="utf-8")
                    else:
                        result = run_forge_match(a, decks[a]["main_deck"], b, decks[b]["main_deck"],
                                                 games=args.games, seed=args.seed, forge_dir=args.forge_dir,
                                                 java=args.java, clock=args.clock, jobs=args.jobs,
                                                 log_dir=attempt, isolated=True, worker_timeout=args.worker_timeout)
                    if result.games != args.games:
                        raise ValueError("Incomplete game count")
                    entry.update(status="complete", result=record(result))
                    entry["result_sha256"] = digest(entry["result"])
                except (ForgeError, OSError, ValueError) as exc:
                    entry["error"] = str(exc)
                    print(f"Failed {key}: {exc}", file=sys.stderr)
                entry["artifacts"] = {str((attempt / p).relative_to(out)): sha for p, sha in artifacts(attempt).items()}
                state["results"][key] = entry
                atomic_json(checkpoint, state)
                write_report(out / "report.md", state)
        # Detect changes during execution, not just between invocations.
        now_manifest, now_decks = load_manifest(args.manifest)
        unchanged = (now_manifest == manifest and now_decks == decks and
                     runtime_identity("forge" in engines, args.forge_dir, args.java) == runtime)
        state["status"] = ("invalid" if not unchanged else "complete" if
                           all(e["status"] == "complete" for e in state["results"].values()) else "incomplete")
        atomic_json(checkpoint, state)
        write_report(out / "report.md", state)
        print(f"{state['status']}: {out / 'report.md'}")
        return 0 if state["status"] == "complete" else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--engine", choices=("builtin", "forge", "both"), default="builtin")
    ap.add_argument("-n", "--games", type=int, default=20, help="games per pairing per engine")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--forge-dir")
    ap.add_argument("--java", default="java")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--builtin-logs", choices=("first", "all"), default="first",
                    help="retain first game per pairing (default) or all games, streamed one at a time")
    ap.add_argument("--clock", type=int, default=30)
    ap.add_argument("--worker-timeout", type=int, default=None, help="wall seconds per Forge worker, including startup")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "benchmark")
    args = ap.parse_args(argv)
    if min(args.games, args.jobs, args.clock, args.worker_timeout or 1) < 1 or args.worker_timeout == 0:
        ap.error("games, jobs, clock and worker-timeout must be positive")
    if args.seed < 0 or args.seed + args.jobs - 1 > 2**63 - 1:
        ap.error("seed and worker seeds must be nonnegative signed 64-bit integers")
    try:
        return run(args)
    except (ValueError, KeyError, OSError, ForgeError, subprocess.SubprocessError) as exc:
        ap.error(str(exc))


if __name__ == "__main__":
    sys.exit(main())
