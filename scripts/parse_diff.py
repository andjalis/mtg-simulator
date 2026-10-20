"""Compare how every card in the card database parses under two versions of the code.

Before pushing a parser change, compare your working tree with main:

    python3 scripts/parse_diff.py local                  # against `git merge-base HEAD origin/main`
    python3 scripts/parse_diff.py local main --show 5    # against main, with field diffs for 5 cards

CI's parse-diff job runs the same steps by hand:

    PYTHONPATH=../base python3 scripts/parse_diff.py dump base.tsv   # the base branch's parser
    python3 scripts/parse_diff.py dump head.tsv                      # this checkout's parser
    python3 scripts/parse_diff.py compare base.tsv head.tsv --report report.md

`dump` writes one line per card: its database key and every CardDef field (`describe`), or ERR and the
exception.
`compare` lists the cards whose parse changed (also into $GITHUB_STEP_SUMMARY when set, and into
--report as Markdown for the PR comment) and exits 1 only when a card that parsed before now raises.
Changed parses are expected in card rounds; the list is there so a reviewer can see which cards a
change touched.
"""
from __future__ import annotations

import argparse
import dataclasses
import difflib
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))      # after PYTHONPATH, so `PYTHONPATH=../base` picks the base checkout's mtgsim
DB = ROOT / "mtgsim" / "data" / "cards.sqlite3"
SHOWN = 100
MARKER = "<!-- parse-diff -->"


def describe(v, seen=frozenset()) -> str:
    """Every field of a CardDef, recursively, in a form that is the same in every process: CardDef's own
    repr is just its name, sets are sorted (string hashes vary by process) and memory addresses are dropped."""
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        if id(v) in seen:
            return f"<{type(v).__name__} cycle>"
        seen = seen | {id(v)}
        return f"{type(v).__name__}(" + ", ".join(f"{f.name}={describe(getattr(v, f.name), seen)}"
                                                  for f in dataclasses.fields(v)) + ")"
    if isinstance(v, (set, frozenset)):
        return "{" + ", ".join(sorted(describe(x, seen) for x in v)) + "}"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{describe(k, seen)}: {describe(x, seen)}" for k, x in v.items()) + "}"
    if isinstance(v, (list, tuple)):
        inner = ", ".join(describe(x, seen) for x in v)
        return f"[{inner}]" if isinstance(v, list) else f"({inner})"
    if callable(v):
        return f"<{getattr(v, '__qualname__', type(v).__name__)}>"
    return re.sub(r" at 0x[0-9a-f]+", "", repr(v))


def dump(out: str) -> None:
    from mtgsim import cards
    print(f"parsing with {Path(cards.__file__).parent.parent}", file=sys.stderr)
    db = sqlite3.connect(DB)
    with open(out, "w") as f:
        for key, data in db.execute("select key, data from cards order by key"):
            try:
                r = describe(cards.card_from_scryfall(json.loads(data)))
            except Exception as e:
                r = "ERR " + repr(e)
            f.write(f"{key}\t{r}\n")
    db.close()


def load(path: str) -> dict[str, str]:
    with open(path) as f:
        return dict(line.rstrip("\n").split("\t", 1) for line in f)


def field_diff(old: str, new: str) -> list[str]:
    """The fields of two CardDef reprs that differ, as -/+ lines."""
    a, b = old.split(", "), new.split(", ")
    return [l for l in difflib.unified_diff(a, b, n=0, lineterm="") if l[:1] in "+-" and l[:3] not in ("---", "+++")]


def compare(old_path: str, new_path: str, report_path: str | None = None, show: int = 0) -> int:
    old, new = load(old_path), load(new_path)
    common = old.keys() & new.keys()
    changed = sorted(k for k in common if old[k] != new[k])
    broke = [k for k in changed if new[k].startswith("ERR") and not old[k].startswith("ERR")]
    fixed = [k for k in changed if old[k].startswith("ERR") and not new[k].startswith("ERR")]
    lines = [f"Card parsing: {len(changed)} of {len(common)} cards parse differently from the base branch."]
    if broke:
        lines += ["", f"**{len(broke)} card(s) now raise an exception:**", ""]
        lines += [f"- {k}: `{new[k][4:]}`" for k in broke[:SHOWN]]
    if fixed:
        lines += ["", f"{len(fixed)} card(s) no longer raise."]
    if changed:
        lines += ["", "Changed cards" + (f" (first {SHOWN})" if len(changed) > SHOWN else "") + ":", ""]
        lines += [f"- {k}" for k in changed[:SHOWN]]
    report = "\n".join(lines)
    print(report)
    for k in changed[:show]:
        print(f"\n{k}:")
        print("\n".join("  " + l for l in field_diff(old[k], new[k])))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(report + "\n")
    if report_path:
        with open(report_path, "w") as f:
            f.write(f"{MARKER}\n{report}\n")
    return 1 if broke else 0


def local(base: str | None, show: int) -> int:
    """Dump the parse at `base` (default: the merge base with origin/main) and in this working tree, then compare."""
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    rev = git("rev-parse", base) if base else git("merge-base", "HEAD", "origin/main")
    me = str(Path(__file__).resolve())
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "base"
        git("worktree", "add", "--detach", str(tree), rev)
        try:
            env = {**os.environ, "PYTHONPATH": str(tree)}
            subprocess.run([sys.executable, me, "dump", f"{tmp}/base.tsv"], env=env, check=True)
            env.pop("PYTHONPATH")
            subprocess.run([sys.executable, me, "dump", f"{tmp}/head.tsv"], env=env, check=True)
            print(f"Base: {rev[:12]}")
            return compare(f"{tmp}/base.tsv", f"{tmp}/head.tsv", show=show)
        finally:
            git("worktree", "remove", "--force", str(tree))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump")
    d.add_argument("out")
    c = sub.add_parser("compare")
    c.add_argument("old")
    c.add_argument("new")
    c.add_argument("--report", help="also write the report as Markdown, for the PR comment")
    c.add_argument("--show", type=int, default=0, help="print the changed fields of the first N changed cards")
    lo = sub.add_parser("local")
    lo.add_argument("base", nargs="?", help="git revision to compare with (default: merge base with origin/main)")
    lo.add_argument("--show", type=int, default=0, help="print the changed fields of the first N changed cards")
    a = ap.parse_args()
    if a.cmd == "dump":
        dump(a.out)
        return 0
    if a.cmd == "compare":
        return compare(a.old, a.new, a.report, a.show)
    return local(a.base, a.show)


if __name__ == "__main__":
    sys.exit(main())
