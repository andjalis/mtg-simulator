"""Compare how every card in the card database parses under two versions of the code (CI's parse-diff job).

    PYTHONPATH=../base python3 scripts/parse_diff.py dump base.tsv   # the base branch's parser
    python3 scripts/parse_diff.py dump head.tsv                      # this checkout's parser
    python3 scripts/parse_diff.py compare base.tsv head.tsv

`dump` writes one line per card: its database key and every CardDef field, or ERR and the exception.
`compare` lists the cards whose parse changed (also into $GITHUB_STEP_SUMMARY when set) and exits 1
only when a card that parsed before now raises. Changed parses are expected in card rounds; the
list is there so a reviewer can see which cards a change touched.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))      # after PYTHONPATH, so `PYTHONPATH=../base` picks the base checkout's mtgsim
DB = ROOT / "mtgsim" / "data" / "cards.sqlite3"
SHOWN = 100


def describe(value) -> str:
    """Every field, recursively, with sets sorted: CardDef's own repr is only its name."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        inner = ", ".join(f"{f.name}={describe(getattr(value, f.name))}" for f in dataclasses.fields(value))
        return f"{type(value).__name__}({inner})"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{describe(k)}: {describe(v)}" for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(describe(v) for v in value) + "]"
    if isinstance(value, (set, frozenset)):
        return "{" + ", ".join(sorted(describe(v) for v in value)) + "}"
    return repr(value)


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


def compare(old_path: str, new_path: str) -> int:
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
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(report + "\n")
    return 1 if broke else 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "dump":
        dump(sys.argv[2])
    elif len(sys.argv) == 4 and sys.argv[1] == "compare":
        sys.exit(compare(sys.argv[2], sys.argv[3]))
    else:
        sys.exit(__doc__)
