"""Quantities that name a spell ("that spell's mana value"): "equal to" is rewritten to the supported
", where X is ..." form, which the engine evaluates against the spell a cast trigger fired on or a
counterspell targeted (``("spell", stat)`` in cards/clauses._xq, ``Game.x_quantity``).

Joined at the end of ``cards/__init__.py``; only SUBS (no effect patterns of its own).
"""
from __future__ import annotations

import re

_Q = r"(that spell's (?:mana value|power|toughness))"
_NOUN = r"(cards?|charge counters?|\+1/\+1 counters?|[a-z-]+ counters?)"

SUBS = [
    # "loses life equal to that spell's mana value" / "gain life equal to ..."
    (re.compile(r"\b(loses|lose|gains|gain) life equal to " + _Q + r"(?=[,.])", re.I),
     lambda m: f"{m[1]} X life, where X is {m[2]}"),
    # "~ deals damage equal to that spell's mana value to any target"
    (re.compile(r"\b(deals) damage equal to " + _Q + r" to ([^.,]+?)(?=\.|$)", re.I),
     lambda m: f"{m[1]} X damage to {m[3]}, where X is {m[2]}"),
    # "mills cards equal to ..." / "draw cards equal to ..."
    (re.compile(r"\b(mills|mill|draws|draw) cards equal to " + _Q + r"(?=[,.])", re.I),
     lambda m: f"{m[1]} X cards, where X is {m[2]}"),
    # "put a number of +1/+1 counters equal to that spell's mana value on <object>"
    (re.compile(r"\bput (?:a number of )?" + _NOUN + r" equal to " + _Q + r" on ([^.,]+?)(?=\.|$)", re.I),
     lambda m: f"put X {m[1]} on {m[3]}, where X is {m[2]}"),
]
