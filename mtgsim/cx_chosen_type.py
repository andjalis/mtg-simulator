"""The chosen creature type (#627): "<permanents> of the chosen type" reads the source's ``chosen_type``.

The choice is stored on the permanent as it enters ("As ~ enters, choose a creature type", Game.enter_battlefield):
the selector key ``chosen_type`` (permanent_templates.selector / matches) then compares a permanent's subtypes with
the source's choice. A card that chooses on resolution ("Choose a creature type. ... of the chosen type ...") has
nowhere to keep the choice, so it is listed unsupported (``unbound``) rather than matching nothing.

Which type the AI names: the most common creature type in its own deck (the existing rule), except for a card whose
chosen-type text hurts those creatures ("get -1/-1", "don't untap", "your opponents control"): then the opponent's
most common creature type, on the battlefield first, else in their deck (``hostile`` / ``pick_hostile``).
"""
from __future__ import annotations

import re

_USES = re.compile(r"\bof the chosen (?:creature )?type\b", re.I)
_HOSTILE = re.compile(r"of the chosen (?:creature )?type(?: your opponents control)? (?:get -|don't untap)|"
                      r"of the chosen (?:creature )?type your opponents control", re.I)


def _uses_key(obj, depth=0) -> bool:
    """Whether any parsed effect or static carries the ``chosen_type`` selector key."""
    if depth > 6 or obj is None:
        return False
    if isinstance(obj, dict):
        return bool(obj.get("chosen_type") is True) or any(_uses_key(v, depth + 1) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_uses_key(v, depth + 1) for v in obj)
    data = getattr(obj, "data", None)
    if isinstance(data, dict):
        return _uses_key(data, depth + 1)
    effects = getattr(obj, "effects", None)
    return _uses_key(effects, depth + 1) if effects is not None else False


def unbound(oracle: str, extra: dict, *parsed) -> list:
    """Unsupported notes for a card whose parsed text reads "of the chosen type" through the selector key without
    storing a choice as it enters (the choice is made on resolution: nothing to compare with)."""
    if not _USES.search(oracle or "") or extra.get("choose_type") or not _uses_key(list(parsed)):
        return []
    return ["chosen creature type made on resolution: no stored choice for 'of the chosen type'"]


def hostile(oracle: str) -> bool:
    return bool(_HOSTILE.search(oracle or ""))


def pick_hostile(game, p) -> str:
    """The opponent's most common creature type: their battlefield, else their deck."""
    opp = game.opponent(p)
    for pool in ([x.card for x in opp.battlefield if x.is_creature], [c for c in opp.deck if c.is_creature]):
        counts: dict = {}
        for c in pool:
            for t in c.subtypes:
                counts[t] = counts.get(t, 0) + 1
        if counts:
            return max(counts, key=counts.get)
    return ""
