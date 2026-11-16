"""Authoring helper for per-card translations (mtgsim.translated).

    python3 scripts/translate_tool.py show "Card Name"         # Oracle, ignored lines, the parse (non-default fields)
    python3 scripts/translate_tool.py probe "Oracle text" [--types "Creature — Bear"] [--name X]
                                                                 # how the parser structures a wording, as translation JSON
    python3 scripts/translate_tool.py new "Card Name"          # write a skeleton data/translated/<slug>.json
    python3 scripts/translate_tool.py check [NAME ...]         # validate translation files and whether they apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("MTGSIM_NO_TRANSLATIONS", "")


def _db(raw=False):
    from mtgsim.carddb import CardDB
    if raw:
        os.environ["MTGSIM_NO_TRANSLATIONS"] = "1"
    return CardDB(offline=True)


def show(name):
    from mtgsim import translated as T
    from mtgsim.coverage import card_coverage
    c = _db(raw=True).get(name)
    print(c.name, "| sha", T.oracle_sha1(c))
    print(c.oracle)
    print("--- ignored")
    for line in card_coverage(c).ignored:
        print(" ", json.dumps(line))
    enc = T.encode(c)
    for k in ("name", "oracle", "unsupported", "mana_cost", "cmc", "types", "subtypes", "power", "toughness"):
        enc.pop(k, None)
    print("--- parse")
    _print_fields(enc)


def _print_fields(enc):
    for k, v in enc.items():
        if k in ("$dc", "color_override"):
            continue
        print(f"{k}: {json.dumps(_compact(v), ensure_ascii=False)}")


def _compact(v):
    """Drop the $dc tags of the common classes so a parse reads in one line per field."""
    if isinstance(v, list):
        return [_compact(x) for x in v]
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if k == "$dc":
                out["_"] = x.split(":")[1]
            else:
                out[k] = _compact(x)
        return out
    return v


def probe(text, types, name, full=False):
    from mtgsim import translated as T
    from mtgsim.cards import card_from_scryfall
    data = {"name": name, "mana_cost": "{1}", "cmc": 1, "type_line": types, "oracle_text": text}
    if "Creature" in types:
        data.update(power="2", toughness="2")
    c = card_from_scryfall(data)
    enc = T.encode(c)
    for k in ("name", "oracle", "mana_cost", "cmc", "types", "subtypes", "power", "toughness"):
        enc.pop(k, None)
    _print_fields(enc) if not full else print(json.dumps(enc, indent=1, ensure_ascii=False))


def probes(types, name):
    """One probe per stdin line ("Type line|text" or just text; "\\n" for a line break)."""
    for line in sys.stdin.read().splitlines():
        if not line.strip():
            continue
        t, _, text = line.rpartition("|")
        print("##", text)
        probe(text.replace("\\n", "\n"), t or types, name)


def new(name):
    from mtgsim import translated as T
    from mtgsim.coverage import card_coverage
    c = _db(raw=True).get(name)
    path = T.DIR / f"{T.slug(c.name)}.json"
    if path.exists():
        sys.exit(f"{path} exists")
    T.DIR.mkdir(parents=True, exist_ok=True)
    data = {"name": c.name, "oracle_sha1": T.oracle_sha1(c), "covers": card_coverage(c).ignored,
            "patches": [{"face": "front", "set": {}, "add": {}}],
            "verify": f"tests/translated/test_cards.py::{T.slug(c.name)}", "notes": ""}
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(path)


def check(names):
    from mtgsim import translated as T
    raw = _db(raw=True)
    bad = 0
    for path in sorted(T.DIR.glob("*.json")):
        data = json.loads(path.read_text())
        if names and data["name"] not in names:
            continue
        problems = T.check(data)
        state, _ = T.status(raw.get(data["name"]))
        if state != "applied":
            problems.append(f"would not apply: {state}")
        bad += bool(problems)
        print(f"{'OK ' if not problems else 'BAD'} {data['name']}" + "".join(f"\n    {p}" for p in problems))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("show", "probe", "probes", "new", "check"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--types", default="Creature — Test")
    ap.add_argument("--name", default="Probe Card")
    ap.add_argument("--full", action="store_true", help="probe: print the full tagged JSON")
    a = ap.parse_args(argv)
    if a.cmd == "show":
        for n in a.args:
            show(n)
    elif a.cmd == "probe":
        probe(" ".join(a.args), a.types, a.name, a.full)
    elif a.cmd == "probes":
        probes(a.types, a.name)
    elif a.cmd == "new":
        for n in a.args:
            new(n)
    else:
        return check(a.args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
