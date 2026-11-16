"""Grammar verb: player counters (#629).

    You get an experience counter.                                  (Mairsil-era experience cards)
    Target player gets two poison counters.                         (Swamp Mosquito-like effects)

Life totals as numbers (double, set, exchange, "loses the game") are read by mtgsim.life_total (#760). Rad counters
are not read: their turn-based rule (mill, lose life, remove) is not in the engine.
"""
from __future__ import annotations

from .cx_grammar import Part, ai_value, verb

_COUNT = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


@verb(r"gets? (a|an|one|two|three|four|five|\d+) (experience|poison) counters?", heads=("get", "gets"),
      subjects=("player",))
def gets_counters(m, clause):
    """"You get an experience counter", "target player gets two poison counters": player counters."""
    if clause.duration:
        return None
    n = int(m[1]) if m[1].isdigit() else _COUNT[m[1].lower()]
    side = "theirs" if m[2].lower() == "poison" else "mine"
    return [Part("player_counter", n, data={"counter": m[2].lower(), "side": side})]


@ai_value("player_counter")
def _counter_value(game, me, eff, obj):
    from .engine.state import Player
    if not isinstance(obj, Player):
        return 0.0
    v = (1.5 if eff.data["counter"] == "poison" else 0.7) * eff.amount
    good = eff.data["counter"] != "poison"
    return (v if good else -v) if obj is me else (-v if good else v)
