"""Quantities that name a spell ("that spell's mana value"): "equal to" is rewritten to the supported
", where X is ..." form, which the engine evaluates against the spell a cast trigger fired on or a
counterspell targeted (``("spell", stat)`` in cards/clauses._xq, ``Game.x_quantity``).

Also handles damage to a targeted spell's controller and controller riders after a counterspell.
"""
from __future__ import annotations

import re

_Q = r"(that spell's (?:mana value|power|toughness))"
_NOUN = r"(cards?|charge counters?|\+1/\+1 counters?|[a-z-]+ counters?)"


def _controller_damage(m):
    from .cards import Effect
    return Effect("damage", 1, target="spell", data={"spell_controller": True, "xq": ("spell", m[1].lower())})


EFFECT_PATTERNS = [
    (r"~ deals damage to target spell's controller equal to that spell's (mana value|power|toughness)",
     _controller_damage),
]


def parse_rider(text, effects):
    """In a counterspell rider, 'its controller' refers to the targeted spell, not the damage source."""
    m = re.fullmatch(r"~ deals X damage to its controller, where X is that spell's (power|toughness|mana value)",
                     text, re.I)
    if m and effects and effects[-1].kind == "counter":
        from .cards import Effect
        effects.append(Effect("cx_damage", 1, data={"source": "self", "who": "spell_controller",
                                                  "xq": ("spell", m[1].lower())}))
        return True
    # "Whenever ~ becomes the target of a spell, counter that spell [unless its controller pays {N}]":
    # the engine hands the targeting stack item to the trigger as its target. Not matched after a
    # "counter target spell ..." rider, where "that spell" names the already-countered spell.
    mc = re.fullmatch(r"counter that spell(?: or ability)?(?: unless its controller pays \{(\d+)\})?",
                      text, re.I)
    if mc and not (effects and effects[-1].kind in ("counter", "bounce_spell") and effects[-1].target == "spell"):
        from .cards import Effect
        effects.append(Effect("counter", int(mc[1] or 0), target="spell", data={"that_spell": True}))
        return True
    return False

SUBS = [
    (re.compile(r"\bthe number of colors that spell is\b", re.I), "the number of that spell's colors"),
    (re.compile(r"\bfor each color that spell is\b", re.I), "for each of that spell's colors"),
    (re.compile(r"\bfor each of that spell's colors, ([^.]+)", re.I),
     lambda m: f"{m[1]} for each of that spell's colors"),
    # "Whenever you cast a spell that's one or more colors" (Ancient Cornucopia): same filter as "multicolored"
    (re.compile(r"\b((?:a |an )?)spell that's one or more colors\b", re.I), r"\1multicolored spell"),
    # "that spell or ability's controller": the engine reads the targeting item's controller either way
    (re.compile(r"\bthat spell or ability's controller\b", re.I), "that spell's controller"),
    # "That spell's controller may draw a card" (Vex): the engine's "may draw" gate is always taken anyway
    (re.compile(r"\b(that spell's controller) may draw a card\b", re.I), r"\1 draws a card"),
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
