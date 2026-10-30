"""Prevention shields with "If damage is prevented this way" riders (Acolyte's Reward,
Vengeful Archon).

"Prevent the next X damage that would be dealt to <who> this turn" becomes a
``prevent_shield`` effect: the kind handler adds ``prevent_next`` to the shielded player
or permanent and, when the sentence has a rider, installs it as a temporary
``damage_prevented`` trigger on the shielded permanent (or the resolving source), so the
le-batch5 event — fired to the shield holder with ``event_amount`` set to the prevented
total — carries "that much" into the rider's effects. ", where X is your devotion to
<color>" sizes the shield at resolution; a literal X in an ability's cost sizes it from
``item.x`` (data ``x``, see resolve's shared amount rules).
"""
from __future__ import annotations

import re

_TARGETS = "target creature|target player|any target|you|~"
_MAP = {"target creature": "creature", "target player": "player", "any target": "any",
        "you": "none", "~": "self"}
_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def _shield(m):
    """Rewrite the sentence(s) into a PREVENTSHIELD sentinel.

    Takes a uniform 5-tuple: (whole, amount, target, devotion color, rider sentence)."""
    amount = "X" if m[1].lower() == "x" else m[1]
    color = _COLORS.get(m[3].lower(), "-") if m[3] else "-"
    rider = (m[4] or "-").rstrip(".") if m[4] else "-"
    if rider != "-":
        rider = rider.replace("target player or planeswalker", "target player")
    return f"PREVENTSHIELD {amount} {_MAP[m[2].lower()]} {color} RIDER {rider}."


SUBS = [
    # "Prevent the next X damage that would be dealt to <who> this turn[, where X is your
    # devotion to <color>]. If damage is prevented this way, <rider sentence>."
    (re.compile(r"prevent the next (x|\d+) damage that would be dealt to (" + _TARGETS +
                r") this turn(, where x is your devotion to (white|blue|black|red|green))?"
                r"\. if damage is prevented this way, (.+?)\.", re.I),
     lambda m: _shield((m[0], m[1], m[2], m[4], m[5]))),
    # The devotion-sized shield on its own (no rider sentence follows).
    (re.compile(r"prevent the next x damage that would be dealt to (" + _TARGETS +
                r") this turn, where x is your devotion to (white|blue|black|red|green)\.",
                re.I),
     lambda m: _shield((m[0], "X", m[1], m[2], None))),
]


def _effect(m):
    from .cards import Effect, NO_MATCH, _parse_effects
    amount = 0 if m[1] == "X" else int(m[1])
    data = {"x": True} if m[1] == "X" else {}
    if m[3] != "-":
        data["devotion"] = m[3]
    if m[4] != "-":
        rider, bad = _parse_effects(m[4][0].upper() + m[4][1:] + ".")
        if bad or not rider:
            return NO_MATCH
        data["rider"] = rider
    return Effect("prevent_shield", amount, target=m[2], data=data)


EFFECT_PATTERNS = [
    (r"PREVENTSHIELD (\d+|X) (\w+) (-|[WUBRG]) RIDER (.+)", _effect),
]
