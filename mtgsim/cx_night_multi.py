"""Spells and abilities that act on several separate targets: "~ deals 3 damage to each of two target creatures",
"Destroy two target nonblack creatures", "Return two target creatures to their owners' hands".

The sentence is read as its one-target form and repeated once per target, each copy flagged ``distinct`` so that the
targeting step gives every copy a different target (the way "target creature you control gets +1/+1 ... another target
creature" already does). "Up to" and "one or two" are played as the full number: the AI picks whatever is legal.
"""
from __future__ import annotations

import re

_NUMBERS = {"two": 2, "three": 3, "up to two": 2, "up to three": 3, "one or two": 2, "one, two, or three": 3}
_COUNT = "|".join(sorted(_NUMBERS, key=len, reverse=True))
_KINDS = {"damage", "destroy", "bounce", "tap", "untap", "debuff", "exile_permanent", "p1_counters", "add_counter"}


def _singular(noun):
    """"nonblack creatures" -> "nonblack creature"; None when the noun is not a plain plural."""
    noun = noun.strip()
    if " and/or " in noun or " or " in noun or "," in noun or not noun.endswith("s") or noun.endswith("ss"):
        return None
    return noun[:-1]


def _several(m):
    from .cards import _parse_effects
    from .cards.model import NO_MATCH
    noun = _singular(m["noun"])
    if noun is None:
        return NO_MATCH
    single = f"{m['pre']}target {noun}{m['post']}"
    single = single.replace("to their owners' hands", "to its owner's hand")
    effects, unmatched = _parse_effects(single[0].upper() + single[1:])
    if unmatched or len(effects) != 1 or effects[0].kind not in _KINDS or effects[0].data.get("distinct") or \
            effects[0].target not in ("creature", "any", "artifact", "land", "nonland_perm", "creature_pw"):
        return NO_MATCH
    out = []
    for _ in range(_NUMBERS[m["n"].lower()]):
        eff = _parse_effects(single[0].upper() + single[1:])[0][0]
        eff.data["distinct"] = True
        out.append(eff)
    return out


EFFECT_PATTERNS = [
    (rf"(?P<pre>.*?)(?:each of )?(?P<n>{_COUNT}) target (?P<noun>[\w -]+?s)(?P<post>(?: to their owners' hands)?)",
     lambda m: _several(m)),
]
