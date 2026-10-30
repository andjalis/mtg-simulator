"""Effect templates kept as data: mtgsim/data/wordings/*.json.

Each entry is one Oracle wording (a regex that must match a whole sentence) and the Effect it builds. Adding a
card that fails only on a new wording means adding an entry, not code; mtgsim/data/wordings/README.md is the
guide. Values in an entry are literals, except:

    "$1"          the text of regex group 1 (None when the group did not take part)
    "$1:int"      int(group 1)                 "$1:num"    a number word or digit ("two" -> 2, "a" -> 1)
    "$1:lower"    group 1 in lower case        "$1:bool"   whether group 1 took part
    {"$map": "$1:lower", "values": {"it": "prev", ...}}    look the value up in a table

An entry builds one Effect from "effect" (its kind), "amount", "amount2", "target", "filter", "cond" and "data",
or several from "effects": a list of objects with those keys."""
from __future__ import annotations

import json
import pkgutil
import re

from .model import Effect, _num

FILES = ("core",)
_EFFECT_KEYS = {"effect", "amount", "amount2", "target", "filter", "cond", "data"}
_ENTRY_KEYS = _EFFECT_KEYS | {"match", "effects", "example", "cards", "note"}
_CASTS = {"int": int, "num": _num, "lower": str.lower, "bool": bool}
_REF = re.compile(r"\$(\d+)(?::(int|num|lower|bool))?")


def _value(spec, m):
    if isinstance(spec, str) and spec.startswith("$"):
        ref = _REF.fullmatch(spec)
        text = m[int(ref[1])]
        return text if ref[2] is None else _CASTS[ref[2]](text)
    if isinstance(spec, dict):
        if "$map" in spec:
            return _value(spec["values"][_value(spec["$map"], m)], m)
        return {k: _value(v, m) for k, v in spec.items()}
    if isinstance(spec, list):
        return [_value(v, m) for v in spec]
    return spec


def _effect(spec, m) -> Effect:
    kw = {k: _value(spec[k], m) for k in ("amount2", "target", "filter", "cond", "data") if k in spec}
    return Effect(spec["effect"], _value(spec.get("amount", 0), m), **kw)


def _check_refs(spec, where):
    if isinstance(spec, str) and spec.startswith("$") and not _REF.fullmatch(spec):
        raise ValueError(f"{where}: bad reference {spec!r}")
    if isinstance(spec, dict):
        if "$map" in spec and set(spec) != {"$map", "values"}:
            raise ValueError(f"{where}: a $map has only \"$map\" and \"values\"")
        for v in spec.values():
            _check_refs(v, where)
    if isinstance(spec, list):
        for v in spec:
            _check_refs(v, where)


def builder(entry: dict):
    """The function a template table wants: match object -> Effect or list of Effects."""
    where = entry.get("match", "?")
    unknown = set(entry) - _ENTRY_KEYS
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}")
    re.compile(entry["match"])
    if ("effect" in entry) == ("effects" in entry):
        raise ValueError(f"{where}: give exactly one of \"effect\" and \"effects\"")
    specs = entry["effects"] if "effects" in entry else [entry]
    for spec in specs:
        if "effect" not in spec or set(spec) - _ENTRY_KEYS:
            raise ValueError(f"{where}: every effect needs \"effect\" and only known keys")
        _check_refs({k: spec[k] for k in _EFFECT_KEYS if k in spec}, where)
    if "effects" in entry:
        def build(m):
            return [_effect(s, m) for s in specs]
    else:
        def build(m):
            return _effect(entry, m)
    build.wording = entry
    return build


def load(name: str) -> list[dict]:
    return json.loads(pkgutil.get_data("mtgsim", f"data/wordings/{name}.json").decode())


def patterns(name: str) -> list[tuple]:
    """(regex, builder) pairs for one wordings file, in file order."""
    return [(e["match"], builder(e)) for e in load(name)]
