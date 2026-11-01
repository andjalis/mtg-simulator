"""Suspect: "Suspect it", "suspect target creature an opponent controls", "suspect up to one other target creature you
control", "suspect enchanted creature".

The sentence is read as the matching "Tap ..." sentence, which already knows these target phrases, and the resulting
effect is turned into ``suspect`` (the engine handler is in engine/kinds/cx_night_suspect.py)."""
from __future__ import annotations

import dataclasses


def _suspect(m):
    from .cards import _parse_effects
    from .cards.model import NO_MATCH
    rest = m["rest"]
    sentence = f"Tap {rest}."
    effects, unmatched = _parse_effects(sentence)
    if unmatched or len(effects) != 1 or effects[0].kind not in ("tap", "tap_host"):
        return NO_MATCH
    eff = effects[0]
    if eff.kind == "tap_host":
        return [dataclasses.replace(eff, kind="suspect", target="host")]
    data = dict(eff.data, side="theirs") if eff.target == "creature" else eff.data
    return [dataclasses.replace(eff, kind="suspect", amount=0, data=data)]


EFFECT_PATTERNS = [
    (r"suspect (?P<rest>it|enchanted creature|(?:up to one )?(?:other )?target creature(?: an opponent controls| you control)?)", _suspect),
]
