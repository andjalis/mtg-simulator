"""Amplify (Legions): "As this creature enters, put N +1/+1 counters on it for each [type]
card you reveal in your hand."

The keyword line (the revealed type rides in the reminder parentheses the face parser strips)
becomes an enters-the-battlefield trigger. Every printed amplify card reveals the types that
match its own creature types, so the effect counts the cards in hand sharing a subtype with
the creature instead of tracking a reveal choice.

Recorded simplification: the "reveal" is just the count; the counters land via the etb trigger
rather than "as it enters" (after it is on the battlefield).
"""
from __future__ import annotations


def _e(kind, amount=1, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


EFFECT_PATTERNS = [
    (r"amplify (\d+)", lambda m: _e("amplify", int(m[1]))),
]

TRIGGERS = [
    (r"(Amplify \d+)", ("etb",)),
]


def amplify(game, p, eff, item):
    """N +1/+1 counters for each hand card sharing a creature type with the source."""
    from .engine.state import Permanent
    src = item.source if item is not None else None
    if not isinstance(src, Permanent) or src not in src.controller.battlefield:
        return
    subs = src.card.subtypes
    n = sum(1 for c in p.hand if c.subtypes & subs) * eff.amount
    if n:
        src.counters["+1/+1"] = src.p1 + n
        game.log(f"amplifies {src.card.name} with {n} +1/+1 counters", p)
