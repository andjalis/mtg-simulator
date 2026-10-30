"""The fast check: what every pull request must pass, in about a minute on four cores.

    python3 scripts/fast_check.py            # all steps
    python3 scripts/fast_check.py --no-lint  # without pyflakes (not installed locally)
    python3 scripts/fast_check.py --jobs 2

Steps: pyflakes, parse a sample of the card database (every STRIDE-th card; a full parse takes about
several minutes, so the whole database is covered by the nightly run and by parse-diff), a few short seeded
games, and the unit tests except the modules in SLOW_TESTS, run as parallel processes. The slow modules run in the nightly workflow
(`.github/workflows/nightly.yml`) and on demand.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DB = ROOT / "mtgsim" / "data" / "cards.sqlite3"
STRIDE = 10
SMOKE = [("decks/green_stompy.txt", "decks/mono_red_aggro.txt"), ("decks/orzhov_midrange.txt", "decks/green_stompy.txt")]
# Test modules that take over a minute each; they run nightly instead. Measured 2026-10-30.
SLOW_TESTS = {"test_standard_coverage", "test_early_stop", "test_assess", "test_ranks", "test_sideboard", "test_coverage"}


def _parse_shard(args) -> list[str]:
    offset, step = args
    import re
    re._MAXCACHE = 1_000_000    # the parser uses thousands of patterns; the default cache of 512 recompiles them per card
    from mtgsim import cards
    bad = []
    db = sqlite3.connect(DB)
    for i, (key, data) in enumerate(db.execute("select key, data from cards order by key")):
        if i % step == offset:
            try:
                cards.card_from_scryfall(json.loads(data))
            except Exception as e:
                bad.append(f"{key}: {e!r}")
    db.close()
    return bad


def _run_test(module: str) -> tuple[str, int, str]:
    p = subprocess.run([sys.executable, "-m", "unittest", f"tests.{module}"], cwd=ROOT, capture_output=True, text=True)
    return module, p.returncode, p.stderr[-3000:]


def step(name: str, ok: bool, detail: str, started: float) -> bool:
    print(f"{'ok  ' if ok else 'FAIL'} {name} ({time.time() - started:.0f}s)", flush=True)
    if not ok:
        print(detail, flush=True)
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--no-lint", action="store_true")
    a = ap.parse_args(argv)
    if not DB.exists():
        print("cards.sqlite3 is missing: run `python3 -m mtgsim.build_carddb` first", file=sys.stderr)
        return 2
    results = []

    if not a.no_lint:
        t = time.time()
        p = subprocess.run([sys.executable, "scripts/lint.py"], cwd=ROOT, capture_output=True, text=True)
        results.append(step("lint", p.returncode == 0, p.stdout + p.stderr, t))

    with ProcessPoolExecutor(a.jobs) as pool:
        t = time.time()
        shards = [(i, STRIDE) for i in range(STRIDE)]
        bad = [b for part in pool.map(_parse_shard, shards) for b in part]
        results.append(step(f"parse 1 of every {STRIDE} cards", not bad, "\n".join(bad[:20]), t))

        t = time.time()
        procs = [subprocess.Popen([sys.executable, "-m", "mtgsim", x, y, "-n", "4", "--seed", "1"], cwd=ROOT,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for x, y in SMOKE]
        outs = [(p.communicate()[0], p.returncode) for p in procs]
        results.append(step("short games", all(rc == 0 for _, rc in outs), "\n".join(o[-1500:] for o, rc in outs if rc), t))

        t = time.time()
        modules = sorted(p.stem for p in (ROOT / "tests").glob("test_*.py") if p.stem not in SLOW_TESTS)
        failed = [(m, err) for m, rc, err in pool.map(_run_test, modules) if rc]
        results.append(step(f"{len(modules)} test modules", not failed,
                            "\n".join(f"--- {m}\n{err}" for m, err in failed), t))

    print("fast check:", "PASS" if all(results) else "FAIL")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
