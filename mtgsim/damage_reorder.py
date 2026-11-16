""""~ deals damage equal to <Q> to <recipient>" read as "~ deals damage to <recipient> equal to <Q>" (#319): the same
sentence, in the word order the counted-damage templates read (Goblin Razerunners: "you may have this creature deal
damage equal to the number of +1/+1 counters on it to target player or planeswalker").

With "~" as the source, "counters on it" in that amount is ~'s own counters (the sentence names nothing else).
Only "the number of ..." amounts and the "target player or planeswalker" recipient (the one the forward order
misses) are moved, so sentences that already parse keep their reading; anything the reordered sentence doesn't parse
stays unsupported.
"""
from __future__ import annotations

import re

SUBS = [
    (re.compile(r"(?<!\w)((?:you may have )?~ deals? damage) equal to (the number of [^.]+?) to "
                r"(target player or planeswalker)"
                r"(?=\.|$)", re.I),
     lambda m: f"{m[1]} to {m[3]} equal to {re.sub(r' counters on it$', ' counters on ~', m[2])}"),
]


def _self_destruct(m):
    """"Target creature you control deals X damage to any other target and X damage to itself, where X is its power."
    (Self-Destruct, #320): the referent grammar's bite to the other target, then a second ``ref_bite`` of the same
    recorded source to itself (damage doesn't change power, so X is the same for both)."""
    from .cards.model import NO_MATCH
    from .cx_grammar import parse_sentence
    first = parse_sentence(f"Target creature you control deals damage equal to its power to {m[1]}.")
    second = parse_sentence("Target creature you control deals damage equal to its power to itself.")
    if not first or not second or [e.kind for e in first] != ["bite_src", "ref_bite"] or \
            [e.kind for e in second] != ["bite_src", "ref_bite"]:
        return NO_MATCH
    import dataclasses
    keep = dataclasses.replace(first[1], data=dict(first[1].data, keep=True))     # the same source bites again
    return [first[0], keep, second[1]]


EFFECT_PATTERNS = [
    (r"target creature you control deals x damage to (any other target|another target creature) and x damage to "
     r"itself, where x is its power", _self_destruct),
]
