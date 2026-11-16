"""Bounce residue (#638): a player returns a permanent they control to its owner's hand, chosen on resolution.

    Return another permanent you control to its owner's hand.        (Ambrosia Whiteheart, Deputy of Acquittals)
    Return an artifact you control to its owner's hand.              (Esperzoa)
    Each player returns a creature they control to its owner's hand. (Curfew)
    Each opponent returns a nonland permanent they control to its owner's hand.

The noun phrase is a battlefield selector (permanent_templates.selector), so any restriction it can't read leaves
the sentence ignored. A creature phrase of the older ``return_own`` template is left to it.
"""
from __future__ import annotations


_WHO = {"each player": "each", "each opponent": "opponents"}


def _build(m):
    from .cards.model import NO_MATCH, Effect
    from .permanent_templates import selector
    who = _WHO[m[1].lower()] if m[1] else "you"
    sel = selector(m[2])
    if not sel or "cx_desc" in sel or sel.get("controller") or sel.get("owner"):
        return NO_MATCH
    return Effect("bounce_choice", 1, data={"selector": dict(sel, controller="mine"), "who": who})


EFFECT_PATTERNS = [
    (r"(?:return|(each player|each opponent) returns) ((?:an?|another) [^,.]+?) (?:you|they) control to "
     r"(?:its|their) owners?'s? hands?", _build),
]
