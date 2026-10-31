"""Damage to a group written with "and each": "~ deals 3 damage to each creature and each planeswalker",
"~ deals 1 damage to each opponent and each creature they control", and "it deals N damage to each ..." (the source is
the permanent whose ability this is).
"""
from __future__ import annotations

_TYPES = r"(?:creature|planeswalker|artifact|enchantment|land|permanent)"
_SCOPE = r"(?: (?:you control|your opponents control|an opponent controls|you don't control))?"


def _selector(text):
    from .permanent_templates import selector
    return selector(text)


def _group(m):
    from .cards.model import NO_MATCH, Effect
    sel = _selector(f"{m[3]} or {m[4]}{m[5] or ''}")
    if sel is None:
        return NO_MATCH
    return Effect("group_remove", int(m[2]), data={"selector": sel, "op": "damage"})


def _opponent_and_group(m):
    from .cards.model import NO_MATCH, Effect
    types = m[2] if not m[3] else f"{m[2]} or {m[3]}"
    sel = _selector(f"{types} your opponents control")
    if sel is None:
        return NO_MATCH
    return [Effect("damage", int(m[1]), target="player"),
            Effect("group_remove", int(m[1]), data={"selector": sel, "op": "damage"})]


def _it_deals(m):
    from .cards import _parse_effects
    from .cards.model import NO_MATCH
    effects, unmatched = _parse_effects(f"~ deals {m[1]} damage to each {m[2]}")
    return effects if effects and not unmatched else NO_MATCH


EFFECT_PATTERNS = [
    (rf"(~|it) deals (\d+) damage to each ({_TYPES}) and each ({_TYPES})({_SCOPE})", _group),
    (rf"(?:~|it) deals (\d+) damage to each opponent and each ({_TYPES})(?: and ({_TYPES}))? (?:they|your opponents) control",
     _opponent_and_group),
    (r"it deals (\d+) damage to each (creature|other creature|player|nonlegendary creature|attacking creature)", _it_deals),
]
