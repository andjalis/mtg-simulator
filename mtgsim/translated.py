"""Per-card translations: hand-written CardDef data for cards the parser leaves partial (pilot, 2026-11-16).

A translation is a JSON file in ``data/translated/`` that states a card's abilities in the engine's own
structures (Effect, Trigger, Activated, ... and CardDef fields) instead of having the parser derive them
from the Oracle text. It may only use effect kinds, triggers, costs and conditions the engine already
executes; ``check()`` rejects unknown effect kinds. The loader hook (``CardDB.get``) calls ``apply``.

File format::

    {
      "name": "Card Name",                    # exact database name
      "oracle_sha1": "0123456789ab",          # first 12 hex digits of sha1 of the front face's Oracle text
      "covers": ["ignored line", ...],        # exactly the parser's ignored lines (card_coverage().ignored)
      "patches": [                            # applied in order
        {"face": "front", "set": {"field": VALUE, ...}, "add": {"list_field": [VALUE, ...]}}
      ],
      "verify": "tests/translated/test_translated.py::Name",   # the verification scenario
      "notes": "free text"
    }

VALUE is plain JSON plus tagged objects: {"$dc": "module:Class", ...fields} for a dataclass (Effect, Trigger,
Activated, AltCost, ModeSpec, ...), {"$t": [...]} a tuple, {"$fs": [...]} a frozenset, {"$d": [[k, v], ...]}
a dict with non-string keys, {"$modes": [...], "spec": VALUE} a modal.Modes list, {"$fn": "module:name"} a
module-level function. ``encode`` writes the same form, so a parsed structure can be dumped, edited and
loaded back exactly.

A translation is applied only when the card's Oracle hash and its parser-ignored lines still match the file
(otherwise the parser changed or the card was errata'd, and the card stays as the parser left it). A
translated card has ``advanced_rules["translated"]`` set and coverage reports it as ``full (translated)``.
Set MTGSIM_NO_TRANSLATIONS=1 to load every card from the parser alone.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import os
import re
from pathlib import Path

DIR = Path(__file__).parent / "data" / "translated"
_INDEX: dict | None = None
FACES = ("front", "back", "adventure", "split_right", "land_face")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def oracle_sha1(card) -> str:
    return hashlib.sha1((card.oracle or "").encode()).hexdigest()[:12]


def _index() -> dict:
    global _INDEX
    if _INDEX is None:
        _INDEX = {}
        if DIR.is_dir():
            for path in sorted(DIR.glob("*.json")):
                data = json.loads(path.read_text())
                _INDEX[data["name"]] = (path, data)
    return _INDEX


# ------------------------------------------------------------------ encoding

def _import(ref: str):
    mod, _, attr = ref.partition(":")
    obj = importlib.import_module(mod)
    for part in attr.split("."):
        obj = getattr(obj, part)
    return obj


def encode(obj):
    from .modal import Modes
    if isinstance(obj, Modes):
        return {"$modes": [encode(x) for x in obj], "spec": encode(obj.spec)}
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {"$dc": f"{type(obj).__module__}:{type(obj).__qualname__}"}
        for f in dataclasses.fields(obj):
            value = getattr(obj, f.name)
            default = f.default if f.default is not dataclasses.MISSING else (
                f.default_factory() if f.default_factory is not dataclasses.MISSING else dataclasses.MISSING)
            if value is not default and value != default or type(value) is not type(default):
                out[f.name] = encode(value)
        return out
    if isinstance(obj, tuple):
        return {"$t": [encode(x) for x in obj]}
    if isinstance(obj, (set, frozenset)):
        return {"$fs": sorted((encode(x) for x in obj), key=repr)}
    if isinstance(obj, list):
        return [encode(x) for x in obj]
    if isinstance(obj, dict):
        if all(isinstance(k, str) and not k.startswith("$") for k in obj):
            return {k: encode(v) for k, v in obj.items()}
        return {"$d": [[encode(k), encode(v)] for k, v in obj.items()]}
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if callable(obj) and getattr(obj, "__module__", None) and "<" not in obj.__qualname__:
        return {"$fn": f"{obj.__module__}:{obj.__qualname__}"}
    raise TypeError(f"can't encode {type(obj).__name__}: {obj!r}")


def decode(obj):
    if isinstance(obj, list):
        return [decode(x) for x in obj]
    if not isinstance(obj, dict):
        return obj
    if "$modes" in obj:
        from .modal import Modes
        return Modes([decode(x) for x in obj["$modes"]], decode(obj.get("spec")))
    if "$dc" in obj:
        cls = _import(obj["$dc"])
        return cls(**{k: decode(v) for k, v in obj.items() if k != "$dc"})
    if "$t" in obj:
        return tuple(decode(x) for x in obj["$t"])
    if "$fs" in obj:
        return frozenset(decode(x) for x in obj["$fs"])
    if "$d" in obj:
        return {decode(k): decode(v) for k, v in obj["$d"]}
    if "$fn" in obj:
        return _import(obj["$fn"])
    return {k: decode(v) for k, v in obj.items()}


# ------------------------------------------------------------------ checks

def _effects(obj):
    """Every Effect inside a decoded value."""
    from .cards import Effect
    if isinstance(obj, Effect):
        yield obj
        yield from _effects(obj.data)
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            yield from _effects(getattr(obj, f.name))
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for x in obj:
            yield from _effects(x)
    elif isinstance(obj, dict):
        for x in obj.values():
            yield from _effects(x)


def check(data: dict) -> list[str]:
    """Problems with a translation file: unknown CardDef fields, faces or effect kinds the engine can't run."""
    from .cards import CardDef
    importlib.import_module(__package__ + ".engine")      # importing the engine registers every handler
    from .engine.kinds import HANDLERS
    problems = []
    fields = {f.name for f in dataclasses.fields(CardDef)}
    for patch in data.get("patches", []):
        if patch.get("face", "front") not in FACES:
            problems.append(f"unknown face {patch.get('face')!r}")
        for part in ("set", "add"):
            for name, value in (patch.get(part) or {}).items():
                if name not in fields:
                    problems.append(f"unknown CardDef field {name!r}")
                for eff in _effects(decode(value)):
                    if eff.kind not in HANDLERS:
                        problems.append(f"effect kind {eff.kind!r} has no engine handler")
    return problems


# ------------------------------------------------------------------ loading

def _face(card, name):
    return card if name == "front" else getattr(card, name)


def status(card) -> tuple[str, dict | None]:
    """("none" | "applied" | "stale-oracle" | "stale-lines", data) for this card's translation file."""
    entry = _index().get(card.name)
    if entry is None:
        return "none", None
    data = entry[1]
    if data.get("oracle_sha1") != oracle_sha1(card):
        return "stale-oracle", data
    from .coverage import card_coverage
    if sorted(card_coverage(card).ignored) != sorted(data.get("covers", [])):
        return "stale-lines", data
    return "applied", data


def _hist_heads(obj, out):
    """Turn-history heads ("you cast a spell") a translated value reads: in lib: condition codes and in
    ("cxq", "hist", head) quantities."""
    if isinstance(obj, str) and obj.lstrip("!").startswith("lib:"):
        _hist_heads(json.loads(obj.lstrip("!")[4:]), out)
    elif isinstance(obj, (list, tuple)):
        if len(obj) >= 2 and obj[0] == "hist" and isinstance(obj[1], str):
            out.add(obj[1])
        if len(obj) >= 3 and obj[0] == "cxq" and obj[1] == "hist" and isinstance(obj[2], str):
            out.add(obj[2])
        for x in obj:
            _hist_heads(x, out)
    elif isinstance(obj, dict):
        for x in obj.values():
            _hist_heads(x, out)
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            _hist_heads(getattr(obj, f.name), out)


def _register_history(values):
    """The condition library counts only turn-history heads registered before the events happen; the parser
    registers them as a side effect of parsing, so a translation must register its own as it loads."""
    heads = set()
    for v in values:
        _hist_heads(v, heads)
    if not heads:
        return
    from . import cx_condlib
    from .cx_events import compile_head
    for head in heads:
        if head not in cx_condlib._HIST_HEADS:
            got = compile_head("Whenever " + head)
            if got is not None:
                cx_condlib._HIST_HEADS[head] = got


def apply(card):
    """The card with its translation applied, when one exists and still matches; else the card unchanged."""
    if os.environ.get("MTGSIM_NO_TRANSLATIONS") or card.name not in _index():
        return card
    state, data = status(card)
    if state != "applied":
        return card
    loaded = []
    for patch in data.get("patches", []):
        face = _face(card, patch.get("face", "front"))
        for name, value in (patch.get("set") or {}).items():
            loaded.append(decode(value))
            setattr(face, name, loaded[-1])
        for name, value in (patch.get("add") or {}).items():
            loaded.append(decode(value))
            getattr(face, name).extend(loaded[-1])
    _register_history(loaded)
    for name in FACES:
        face = _face(card, name)
        if face is not None:
            face.unsupported = []
    card.advanced_rules = dict(card.advanced_rules, translated=_index()[card.name][0].name)
    return card
