"""Offline review gate: python3 scripts/pilot_gate.py --base origin/main [--fast].

Artifacts (including full logs) live in results/pilot_gate. Full-match regressions,
new parser exceptions, suspicious sampled parses, newly-full cards that raise when their
effects resolve once, and failed checks fail the gate.
Template matching and a smoke run are review aids, not rules-correctness evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import runpy
import signal
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time

SCHEMA = 1
GAME_TIMEOUT = 20
CHECK_TIMEOUT = 1800


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, cwd, log, env=None, timeout=CHECK_TIMEOUT):
    """Bound the whole process group, including a hung check's children."""
    start = time.monotonic()
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            code, timed_out = -9, True
    return {"command": list(map(str, command)), "returncode": code,
            "timeout": timed_out, "seconds": round(time.monotonic() - start, 3),
            "log": log.name}


def suspicious(value, path="parse", seen=None):
    """Inspect actual fields (including defaults hidden by parse_diff.describe)."""
    seen = set() if seen is None else seen
    if is_dataclass(value) and not isinstance(value, type):
        if id(value) in seen:
            return []
        seen.add(id(value))
        value = {f.name: getattr(value, f.name) for f in fields(value)}
    flags = []
    if isinstance(value, dict):
        for key, item in value.items():
            at = f"{path}.{key}"
            if key == "target" and item == "none":
                flags.append(f"{at}='none'")
            if key == "what" and not item:
                flags.append(f"{at} is empty")
            # Oracle/name strings may legitimately contain card or mana symbols.
            if key not in {"oracle", "name", "text"} and isinstance(item, str):
                if re.search(r"\{(?![0-9WUBRGCSXYZTEP/]+\})[^{}]+\}|<[^>]+>|\b(?:unknown|placeholder)\b", item, re.I):
                    flags.append(f"{at}: unknown placeholder {item!r}")
            flags.extend(suspicious(item, at, seen))
    elif isinstance(value, (list, tuple, set, frozenset)):
        for i, item in enumerate(value):
            flags.extend(suspicious(item, f"{path}[{i}]", seen))
    return flags


def compare_coverage(before, after):
    old, new = before["cards"], after["cards"]
    common = old.keys() & new.keys()
    return {
        "regressions": sorted(k for k in common if old[k] == "full" and new[k] != "full"),
        "newly_full": sorted(k for k in new if new[k] == "full" and old.get(k) != "full"),
        "newly_raising": sorted(k for k in common if new[k] == "parse_error" and old[k] != "parse_error"),
        "removed": sorted(old.keys() - new.keys()),
        "deltas": {scope: {label: after[scope].get(label, 0) - before[scope].get(label, 0)
                            for label in sorted(before[scope].keys() | after[scope].keys())}
                   for scope in ("all", "standard")},
    }


def verdict(checks, comparison, samples, smoke, exercise=()):
    reasons = [f"{name} failed" + (" (timeout)" if item.get("timeout") else "")
               for name, item in checks.items() if item["returncode"] != 0]
    for key, label in (("newly_raising", "newly raising cards"),
                       ("regressions", "full-match regressions"), ("removed", "missing census cards")):
        if comparison.get(key):
            reasons.append(f"{len(comparison[key])} {label}")
    # target='none' is normal for untargeted effects (edicts, "each player"), so it is shown, not failed.
    flagged = [s["name"] for s in samples if any(not f.endswith("='none'") for f in s["flags"])]
    if flagged:
        reasons.append(f"Suspicious sampled parses: {', '.join(flagged)}")
    crashed = [e["name"] for e in exercise if not e["ok"]]
    if crashed:
        reasons.append(f"{len(crashed)} newly-full cards crash when resolved: {', '.join(crashed[:10])}")
    if smoke.get("completed") != 50 or smoke.get("failures"):
        reasons.append(f"Smoke completed {smoke.get('completed', 0)}/50 games; {len(smoke.get('failures', []))} failures")
    return ("FAIL" if reasons else "PASS"), reasons


def select_tests(changed, root):
    """Use related filename tests; fall back to the suite for broad/unknown changes."""
    selected = {p for p in changed if p.startswith("tests/test_") and p.endswith(".py") and (root / p).is_file()}
    available = list((root / "tests").glob("test_*.py"))
    for name in changed:
        if not name.endswith(".py") or name.startswith("tests/"):
            continue
        stem = Path(name).stem
        related = [p for p in available if stem in p.stem]
        if not related or name.startswith("mtgsim/cards/") or name.startswith("mtgsim/engine/"):
            return ["discover", "-s", "tests", "-t", "."]
        selected.update(str(p.relative_to(root)) for p in related)
    # No Python changes still gets a complete check; never silently run zero tests.
    return sorted(p[:-3].replace("/", ".") for p in selected) or ["discover", "-s", "tests", "-t", "."]


def census(root, standard_path, output):
    from mtgsim.carddb import CardDB
    from mtgsim.coverage import card_coverage
    from mtgsim.standard_coverage import standard_cards

    db = CardDB(offline=True)
    if db._all is None:
        raise ValueError("Missing offline database: run python3 -m mtgsim.build_carddb")
    cards, counts = {}, Counter()
    try:
        # Seed canonical names once, keeping bundled/cache overrides. Repeated
        # CardDB.get otherwise scans all earlier face aliases for every new row.
        names = []
        for name, data in db._all.execute("SELECT name, data FROM cards ORDER BY key"):
            db.raw.setdefault(name.lower(), json.loads(data))
            names.append(name)
        for name in names:
            try:
                status = card_coverage(db.get(name)).status
            except Exception:
                status = "parse_error"
            cards[name] = status
            counts[status] += 1
        _, names = standard_cards(Path(standard_path))
        standard = Counter()
        for name in names:
            try:
                status = card_coverage(db.get(name)).status
            except KeyError:
                status = "unknown"
            except Exception:
                status = "parse_error"
            standard[status] += 1
        write_json(Path(output), {"cards": cards, "all": dict(counts, total=len(cards)),
                                  "standard": dict(standard, total=len(names)),
                                  "standard_scope": "Saved Standard set snapshot, nonbasic cards (standard_coverage)"})
    finally:
        db._all.close()


def sample_cards(root, names_path, output):
    from mtgsim.carddb import CardDB

    spec = importlib.util.spec_from_file_location("parse_diff", root / "scripts/parse_diff.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    db = CardDB(offline=True)
    samples = []
    try:
        for name in json.loads(Path(names_path).read_text()):
            card = db.get(name)
            raw = db.raw[db._key(name)]
            oracle = raw.get("oracle_text") or "\n//\n".join(f.get("oracle_text", "") for f in raw.get("card_faces", []))
            samples.append({"name": name, "oracle": oracle, "parsed": module.describe(card),
                            "flags": suspicious(card)})
        write_json(Path(output), samples)
    finally:
        if db._all:
            db._all.close()


EXERCISE_BOARD = ("Mountain", "Forest", "Island", "Plains", "Swamp", "Grizzly Bears", "Hill Giant",
                  "Llanowar Elves", "Sol Ring", "Glorious Anthem")


def exercise_cards(root, names_path, output):
    """Resolve every effect of each newly-full card once on a stock board; record crashes, not behavior."""
    import traceback
    from mtgsim.ai import HeuristicAI
    from mtgsim.carddb import CardDB
    from mtgsim.engine import Game, Permanent, Player, StackItem

    def timeout(*_):
        raise TimeoutError("resolution took over 10 s")

    def targets(game, p, effects, source=None):
        # The AI declines targets it sees no value in (a 0-damage parse); any legal one still runs the handler.
        chosen = game.auto_targets(p, effects, source)
        for i, (eff, tgt) in enumerate(zip(effects, chosen)):
            if tgt is None:
                legal = game.legal_targets(p, eff)
                chosen[i] = next((t for t in legal if getattr(t, "controller", t) is not p), legal[0] if legal else None)
        return chosen

    db = CardDB(offline=True)
    board = [c for c in map(db.get, EXERCISE_BOARD) if c is not None]
    results = []
    try:
        for name in json.loads(Path(names_path).read_text()):
            card = db.get(name)
            a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
            game = Game(a, b, random.Random(0))
            game.turn, game.step = 1, "main1"
            for pl in (a, b):
                pl.library = board * 3
                pl.hand = list(board[5:])
                pl.graveyard = list(board[5:8])
                for c in board:
                    pl.battlefield.append(Permanent(c, pl))
                for perm in pl.battlefield:
                    perm.sick = False
            groups = [("cast", None, card.spell_effects)] + [("mode", None, m) for m in card.modes]
            groups += [("activated", True, act.effects) for act in card.activated if act.effects]
            groups += [("trigger " + t.event, True, t.effects) for t in card.triggers if t.event != "etb" and t.effects]
            groups += [("loyalty", True, effects) for _, effects in card.loyalty_abilities]
            step = "setup"
            if hasattr(signal, "SIGALRM"):
                signal.signal(signal.SIGALRM, timeout)
                signal.alarm(10)
            try:
                source = None
                for step, on_permanent, effects in groups:
                    if on_permanent and source is None:
                        source = Permanent(card, a)
                        source.sick = False
                        a.battlefield.append(source)
                    if step == "cast":      # a permanent spell enters, firing its own ETB triggers
                        game.stack.append(StackItem(a, effects, targets(game, a, effects), card=card))
                    else:
                        game.stack.append(StackItem(a, effects, targets(game, a, effects, source),
                                                    source=source, kind="trigger"))
                    for _ in range(30):
                        if not game.stack:
                            break
                        game.resolve_top()
                results.append({"name": name, "ok": True})
            except Exception as exc:
                frame = traceback.extract_tb(exc.__traceback__)[-1]
                results.append({"name": name, "ok": False, "step": step,
                                "error": f"{type(exc).__name__}: {exc}",
                                "at": f"{Path(frame.filename).name}:{frame.lineno}"})
            finally:
                if hasattr(signal, "SIGALRM"):
                    signal.alarm(0)
        write_json(Path(output), results)
    finally:
        if db._all:
            db._all.close()


def choose_decks(root, newly_full):
    from mtgsim.decklist import load_deck

    candidates = []
    wanted = {n.casefold() for n in newly_full}
    for path in sorted((root / "decks").rglob("*.txt")):
        _, counts = load_deck(path)
        if sum(counts.values()) >= 40:
            hits = sorted(n for n in counts if n.casefold() in wanted)
            candidates.append((len(hits), str(path.relative_to(root)), hits))
    candidates.sort(key=lambda c: (-c[0], c[1]))
    if len(candidates) < 2:
        raise ValueError("Need at least two deck fixtures for smoke")
    # Prefer all decks containing newly full cards; rotate deterministic opponents.
    fallback = [c for c in candidates if c[1] in {"decks/mono_red_aggro.txt", "decks/green_stompy.txt"}]
    opponents = fallback or candidates[:2]
    preferred = [c for c in candidates if c[0]] or opponents
    pairs = [(preferred[i % len(preferred)][1], opponents[(i + 1) % len(opponents)][1]) for i in range(50)]
    return {"pairs": pairs, "newly_full_in_decks": sorted({n for c in preferred for n in c[2]}),
            "selection": "matching repository decks" if wanted and any(c[0] for c in candidates) else "repository fallback (no newly-full cards in decks)"}


def smoke_game(root, a, b, seed):
    from mtgsim.carddb import CardDB
    from mtgsim.decklist import load_deck
    from mtgsim.runner import build_deck, run_match

    db = CardDB(offline=True)
    try:
        _, ca = load_deck(root / a)
        _, cb = load_deck(root / b)
        da, dbb = build_deck(db, ca), build_deck(db, cb)
        # Reverse seats on alternate seeds, preserving per-game reproducibility.
        if seed % 2:
            da, dbb = dbb, da
        result, _ = run_match(a, da, b, dbb, games=1, seed=seed)
        if result.games != 1:
            raise RuntimeError(f"Expected one smoke game, got {result.games}")
        print(json.dumps({"games": result.games, "wins_a": result.wins_a,
                          "wins_b": result.wins_b, "draws": result.draws}))
    finally:
        if db._all:
            db._all.close()


def markdown(report):
    lines = [f"# Pilot gate: {report['verdict']}", "",
             f"Base `{report['base'][:12]}` → `{report['head'][:12]}`; "
             f"{'fast' if report['fast'] else 'full'} tests; {report['seconds']:.1f}s.", ""]
    lines += [f"- {reason}" for reason in report["reasons"]] or ["All checks passed."]
    lines += ["", "| Check | Exit | Seconds |", "| --- | ---: | ---: |"]
    lines += [f"| [{name}]({item['log']}) | {item['returncode']} | {item['seconds']:.1f} |"
              for name, item in report["checks"].items()]
    comp = report.get("comparison", {})
    lines += ["", "Coverage deltas (same offline inputs; Standard = saved nonbasic set snapshot):"]
    for scope, delta in comp.get("deltas", {}).items():
        lines.append(f"- {scope}: " + ", ".join(f"{k} {v:+d}" for k, v in delta.items()))
    for key in ("regressions", "newly_full", "newly_raising"):
        names = comp.get(key, [])
        lines.append(f"- {key} ({len(names)}): " + (", ".join(names[:20]) or "none") +
                     (" … (all names in verdict.json)" if len(names) > 20 else ""))
    smoke = report.get("smoke", {})
    crashed = [e for e in report.get("exercise", []) if not e["ok"]]
    lines.append(f"- Exercise: {len(report.get('exercise', [])) - len(crashed)}/{len(report.get('exercise', []))} newly-full cards "
                 "resolved every effect once without raising.")
    lines += [f"  - **{e['name']}** ({e['step']}): {e['error']} at {e['at']}" for e in crashed[:20]]
    lines += [f"- Smoke: {smoke.get('completed', 0)}/50; seed 1729+i; {GAME_TIMEOUT}s/game; "
              f"{smoke.get('selection', 'unavailable')}.", "",
              "False-full sample (up to 10, seed 1729; Oracle beside parsed fields):", ""]
    for sample in report.get("samples", []):
        lines += [f"**{sample['name']}** — " + ("; ".join(sample["flags"]) or "no flags"), "",
                  "| Oracle | Parsed |", "| --- | --- |",
                  "| " + " | ".join(s.replace("&", "&amp;").replace("<", "&lt;").replace("|", "&#124;").replace("\n", "<br>")
                                     for s in (sample["oracle"], sample["parsed"])) + " |", ""]
    if not report.get("samples"):
        lines.append("No newly-full cards to sample.")
    lines += ["", "Template matching and smoke games do not establish rules correctness. Full evidence: verdict.json and linked logs."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--worktree", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--fast", action="store_true")
    args = parser.parse_args(argv)
    root = args.worktree.expanduser().resolve()
    git = lambda *a: subprocess.check_output(["git", *a], cwd=root, text=True).strip()
    base = git("rev-parse", "--verify", args.base + "^{commit}")
    head = git("rev-parse", "HEAD")
    branch = re.sub(r"[^A-Za-z0-9_.-]", "-", git("branch", "--show-current")) or "detached"
    dest = root / "results/pilot_gate" / f"{branch}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}"
    dest.mkdir(parents=True)
    start = time.monotonic()
    report = {"base": base, "head": head, "worktree": str(root), "fast": args.fast,
              "dirty": git("status", "--porcelain", "--untracked-files=no"),
              "checks": {}, "samples": [], "exercise": [], "smoke": {"completed": 0, "failures": []}}
    checks = report["checks"]
    script = Path(__file__).resolve()
    env = dict(os.environ, PYTHONHASHSEED="0")
    test_env = dict(env)
    # Freeze DB/cache/Standard inputs for both revision censuses and smoke.
    # Tests retain normal lookup paths: browser ZIP tests intentionally hide sqlite3.
    try:
        with tempfile.TemporaryDirectory(prefix="pilot-gate-") as temp:
            temp = Path(temp)
            db_path = Path(os.environ.get("MTGSIM_CARDDB", root / "mtgsim/data/cards.sqlite3"))
            if not db_path.is_file():
                raise ValueError("Missing offline database: run python3 -m mtgsim.build_carddb first")
            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as source:
                with sqlite3.connect(temp / "cards.sqlite3") as target:
                    source.backup(target)
            cache_path = Path(os.environ.get("MTGSIM_CACHE", Path.home() / ".cache/mtgsim/cards.json"))
            (temp / "cards.json").write_bytes(cache_path.read_bytes() if cache_path.exists() else b"[]")
            env.update(MTGSIM_CARDDB=str(temp / "cards.sqlite3"), MTGSIM_CACHE=str(temp / "cards.json"))
            standard = root / "tests/fixtures/forge_scripts/standard"
            import shutil
            shutil.copytree(standard, temp / "standard")
            standard = temp / "standard"
            identity = {"schema": SCHEMA, "base": base, "worker": fingerprint(script),
                        "database": fingerprint(temp / "cards.sqlite3"), "cache": fingerprint(temp / "cards.json"),
                        "python": sys.version,
                        "standard": [(str(p.relative_to(standard)), fingerprint(p)) for p in sorted(standard.rglob("*")) if p.is_file()]}
            report["inputs"] = identity
            def check(name, command, cwd=root, timeout=CHECK_TIMEOUT, custom_env=None):
                print(f"pilot gate: {name}", flush=True)
                item = run(command, cwd, dest / f"{name}.log", custom_env or env, timeout)
                checks[name] = item
                return item["returncode"] == 0

            check("lint", [sys.executable, "scripts/lint.py"], custom_env=test_env)
            changed = set(git("diff", "--name-only", base).splitlines())
            changed.update(git("ls-files", "--others", "--exclude-standard", "tests", "scripts", "mtgsim").splitlines())
            tests = select_tests(changed, root) if args.fast else ["discover", "-s", "tests", "-t", "."]
            report["tests"] = tests
            check("tests", [sys.executable, str(script), "_worker", str(root), "tests", *tests], custom_env=test_env)
            cache_dir = root / "results/pilot_gate/cache" / base
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            cached = cache_dir / f"{cache_key}.json"
            base_tree = temp / "base"
            base_tree.mkdir()
            archive = temp / "base.tar"
            subprocess.run(["git", "archive", "--format=tar", "--output", str(archive), base], cwd=root, check=True)
            with tarfile.open(archive) as tar:
                if sys.version_info >= (3, 12):
                    tar.extractall(base_tree, filter="data")
                else:
                    tar.extractall(base_tree)
            def worker(name, tree, operation, *extra):
                return check(name, [sys.executable, str(script), "_worker", str(tree), operation, *map(str, extra)])

            report["base_cache_hit"] = cached.exists()
            if cached.exists():
                before = json.loads(cached.read_text())
            else:
                if not worker("coverage_base", base_tree, "census", standard, dest / "coverage_base.json"):
                    raise RuntimeError("base coverage census failed")
                before = json.loads((dest / "coverage_base.json").read_text())
                staging = cache_dir / f"{cache_key}-{dest.name}.tmp"
                write_json(staging, before)
                staging.replace(cached)
            write_json(dest / "coverage_base.json", before)
            if not worker("coverage_head", root, "census", standard, dest / "coverage_head.json"):
                raise RuntimeError("head coverage census failed")
            after = json.loads((dest / "coverage_head.json").read_text())
            report["comparison"] = compare_coverage(before, after)
            # Existing parse_diff dump uses its script's DB path; use a private copy
            # with the frozen DB, and explicit PYTHONPATH to select each parser.
            driver = temp / "scripts/parse_diff.py"
            driver.parent.mkdir()
            driver.write_bytes((root / "scripts/parse_diff.py").read_bytes())
            (temp / "mtgsim/data").mkdir(parents=True)
            shutil.copyfile(temp / "cards.sqlite3", temp / "mtgsim/data/cards.sqlite3")
            for label, tree in (("base", base_tree), ("head", root)):
                worker(f"parse_{label}", tree, "dump", driver, dest / f"{label}.tsv")
            check("parse_diff", [sys.executable, str(driver), "compare", str(dest / "base.tsv"),
                                 str(dest / "head.tsv"), "--report", str(dest / "parse_diff.md")], cwd=temp)
            names = random.Random(1729).sample(report["comparison"]["newly_full"], min(10, len(report["comparison"]["newly_full"])))
            write_json(dest / "sample_names.json", names)
            if worker("sample", root, "sample", dest / "sample_names.json", dest / "samples.json"):
                report["samples"] = json.loads((dest / "samples.json").read_text())
            if not worker("decks", root, "decks", dest / "sample_all_names.json", dest / "decks.json"):
                raise RuntimeError("deck selection failed")
            selection = json.loads((dest / "decks.json").read_text())
            if worker("exercise", root, "exercise", dest / "sample_all_names.json", dest / "exercise.json"):
                report["exercise"] = json.loads((dest / "exercise.json").read_text())
            report["smoke"].update(selection)
            for i, (a, b) in enumerate(selection["pairs"]):
                item = run([sys.executable, str(script), "_worker", str(root), "game", a, b, str(1729 + i)],
                           root, dest / f"game-{i:02d}.log", env, GAME_TIMEOUT)
                if item["returncode"] == 0:
                    report["smoke"]["completed"] += 1
                else:
                    report["smoke"]["failures"].append(dict(item, seed=1729 + i, decks=[a, b]))
                    break
            report["verdict"], report["reasons"] = verdict(checks, report["comparison"], report["samples"], report["smoke"],
                                                           report["exercise"])
    except Exception as exc:
        report["verdict"] = "FAIL"
        report["reasons"] = [f"{type(exc).__name__}: {exc}"]
        reasons = verdict(checks, report.get("comparison", {}), report["samples"], report["smoke"], report["exercise"])[1]
        report["reasons"].extend(reasons)
    report["seconds"] = round(time.monotonic() - start, 3)
    write_json(dest / "verdict.json", report)
    (dest / "verdict.md").write_text(markdown(report), encoding="utf-8")
    print(f"{report['verdict']}: {dest / 'verdict.md'} ({report['seconds']:.1f}s)")
    return int(report["verdict"] != "PASS")


def worker_main():
    root, operation, *extra = sys.argv[2:]
    root = Path(root)
    sys.path.insert(0, str(root))
    # Hundreds of templates plus dynamic face patterns overflow CPython's cache.
    # Keep compiled patterns in these short-lived workers; parsing is unchanged.
    # Other Python implementations can simply retain their cache defaults.
    for name, size in (("_MAXCACHE", 8192), ("_MAXCACHE2", 4096)):
        if hasattr(re, name):
            setattr(re, name, max(size, getattr(re, name)))
    if operation == "tests":
        sys.argv = ["python3 -m unittest", *extra]
        runpy.run_module("unittest", run_name="__main__")
    elif operation == "dump":
        driver, output = extra
        sys.argv = [driver, "dump", output]
        runpy.run_path(driver, run_name="__main__")
    elif operation == "census":
        census(root, *extra)
    elif operation == "sample":
        sample_cards(root, *extra)
    elif operation == "decks":
        # Pass every newly-full name, not only the reviewer sample.
        names_path, output = map(Path, extra)
        comparison = json.loads((output.parent / "coverage_head.json").read_text())
        before = json.loads((output.parent / "coverage_base.json").read_text())
        names = compare_coverage(before, comparison)["newly_full"]
        write_json(names_path, names)
        write_json(output, choose_decks(root, names))
    elif operation == "exercise":
        exercise_cards(root, *extra)
    elif operation == "game":
        smoke_game(root, extra[0], extra[1], int(extra[2]))
    else:
        raise ValueError(operation)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "_worker":
        worker_main()
    else:
        sys.exit(main())
