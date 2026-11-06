"""Counters on several targets at once.

* "Put a <counter> counter on each of up to N [other] target <desc>" (also "N <counter> counters"): N effects with
  distinct targets, each picked from the same description by the selector grammar (``permanent_templates``). Fewer
  legal targets than N is fine ("up to"), as with every optional target.
"""
from __future__ import annotations

import re

_N = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_COUNTER = r"(?:[+-]\d+/[+-]\d+|[a-z]+(?:-[a-z]+)?)"


def _num(word):
    return int(word) if word.isdigit() else _N[word]


def _singular(desc):
    """"creatures you control" -> "creature you control": the plural noun is the one before any "you control"."""
    head = re.fullmatch(r"(.+?)( you control| an opponent controls| you don't control)?", desc)[1]
    rest = desc[len(head):]
    words = head.split(" ")
    last = words[-1]
    words[-1] = "elf" if last == "elves" else last[:-1] if last.endswith("s") and not last.endswith("ss") else last
    return " ".join(words) + rest


def _each_of_up_to(m):
    from .cards.model import NO_MATCH
    from .permanent_templates import build
    count = _N.get(m[3])
    if count is None:
        return NO_MATCH
    out = []
    for _ in range(count):
        eff = build("add_counter", "up to one " + ("other " if m[4] else "") + "target " + _singular(m[5]),
                    amount=_num(m[1]), data={"counter": m[2], "distinct": True})
        if eff is None or eff.target == "group":
            return NO_MATCH
        out.append(eff)
    return out


EFFECT_PATTERNS = [
    (rf"put (a|an|one|two|three|four|five) ({_COUNTER}) counters? on each of up to (two|three|four|five) "
     rf"(other )?target (.+)", _each_of_up_to),
]
