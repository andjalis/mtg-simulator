"""Distribute +1/+1 counters: "Distribute three +1/+1 counters among one, two, or three target creatures you
control." and the X form ("Distribute X +1/+1 counters among any number of target creatures you control.").

One ``distribute_counters`` effect. The first target is chosen when the spell or ability goes on the stack
(a creature you control, so the effect needs at least one); the others are picked when it resolves, because the
stack holds one target per effect. Counters go round-robin over the best creatures: at most one target per
counter and never more targets than the line allows. The AI only ever helps its own creatures, so "target
creatures" without "you control" also targets creatures you control. Without "target" (Awaken the Maelstrom)
the creatures are chosen on resolution. An X amount is the X paid for the spell (see xspells.py). Riders
("then double the number of counters", "{S} spent", "other") are not matched, so those lines stay unsupported.
"""
from __future__ import annotations

ANY = 99
_SLOTS = {"one or two": 2, "one, two, or three": 3, "any number of": ANY}


def _build(m):
    from .cards import Effect, _num  # at match time: this module loads before cards
    x = m[1].lower() == "x"
    data = {"slots": _num(m[3]) if m[3] else _SLOTS[m[2].lower()]}
    if x:
        data["x"] = True
    return Effect("distribute_counters", 0 if x else _num(m[1]), target="creature_mine" if m[4] else "none",
                  data=data)


EFFECT_PATTERNS = [
    (r"distribute (\d+|X|one|two|three|four|five|six|seven|eight) \+1/\+1 counters? among "
     r"(one or two|one, two, or three|any number of|up to (one|two|three|four|five))"
     r"(?:( target) creatures?(?: you control)?| creatures you control)", _build),
]


def split(counters, creatures):
    """Counters per creature, round-robin, using at most one creature per counter (creatures: best first)."""
    chosen = creatures[:max(counters, 0)]
    return [(c, counters // len(chosen) + (i < counters % len(chosen))) for i, c in enumerate(chosen)] if chosen else []
