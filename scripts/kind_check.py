"""Every effect kind a parsed card can produce must have a handler (engine/kinds HANDLERS).

    python3 scripts/kind_check.py              # all cards: kinds without a handler, with example cards
    python3 scripts/kind_check.py --jobs 4

Game.resolve skips an effect whose kind has no handler, so such a card can count as full while the effect
does nothing. fast_check runs the same collection (``kinds_of``) while it parses every card.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DB = ROOT / "mtgsim" / "data" / "cards.sqlite3"


def _effects(obj, depth=0):
    """Every Effect reachable from a parsed card, its faces, abilities, modes and nested inner effects."""
    from mtgsim.cards import Effect
    if depth > 8 or obj is None:
        return
    if isinstance(obj, Effect):
        yield obj
        for v in (obj.data or {}).values():
            yield from _effects(v, depth + 1)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for x in obj:
            yield from _effects(x, depth + 1)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _effects(v, depth + 1)
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            if f.name not in ("oracle", "unsupported", "approximations"):
                yield from _effects(getattr(obj, f.name), depth + 1)


def kinds_of(card) -> set:
    return {e.kind for e in _effects(card)}


def handled() -> set:
    from mtgsim.engine.kinds import HANDLERS
    return set(HANDLERS)


def _shard(args):
    offset, step = args
    import re
    re._MAXCACHE = 1_000_000
    from mtgsim import cards
    from mtgsim.coverage import card_coverage
    out = {}
    db = sqlite3.connect(DB)
    for i, (key, data) in enumerate(db.execute("select key, data from cards order by key")):
        if i % step != offset:
            continue
        try:
            card = cards.card_from_scryfall(json.loads(data))
        except Exception:
            continue
        status = card_coverage(card).status
        for k in kinds_of(card):
            out.setdefault(k, []).append((card.name, status))
    db.close()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    a = ap.parse_args(argv)
    found: dict = {}
    with ProcessPoolExecutor(a.jobs) as pool:
        for part in pool.map(_shard, [(i, 16) for i in range(16)]):
            for k, v in part.items():
                found.setdefault(k, []).extend(v)
    missing = sorted(set(found) - handled())
    for k in missing:
        full = [n for n, s in found[k] if s == "full"]
        print(f"{k}: {len(found[k])} cards ({len(full)} full) e.g. {', '.join(n for n, _ in found[k][:5])}")
    print(f"kind check: {len(found)} kinds produced, {len(missing)} without a handler")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
