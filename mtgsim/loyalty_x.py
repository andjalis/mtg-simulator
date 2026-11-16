"""−X loyalty costs (#839): "−X: Chandra Nalaar deals X damage to target creature."

The parser keeps such an ability at cost 0 and lists its index in ``CardDef.loyalty_x``; ``Game.activate_loyalty``
asks ``choose`` for X (0 <= X <= loyalty, CR 606.4), removes X loyalty counters, and puts X on the stack item, where
the effects' X (``data["x"]``) reads it like a spell's X. ``effects_at`` is the ability as it would resolve with that
X, which the AI scores and the targets are chosen for.
"""
from __future__ import annotations

import dataclasses


def is_x(card, idx: int) -> bool:
    return idx in getattr(card, "loyalty_x", ())


def effects_at(effects: list, x: int) -> list:
    """The effects with their X amounts (and an X mana-value bound, ``stat_x``) set to x."""
    out = []
    for e in effects:
        if e.data.get("x") is True:
            e = dataclasses.replace(e, amount=x, amount2=x if e.data.get("x2") else e.amount2)
        if e.data.get("stat_x"):
            sel = e.data["selector"]
            e = dataclasses.replace(e, data={**e.data, "selector": {**sel, "stat": [sel["stat"][0], sel["stat"][1], x]}})
        out.append(e)
    return out


def _ugin(m):
    from .cards.model import Effect
    return Effect("group_remove", data={"selector": {"stat": ["mana value", "<=", 0], "types_all": ["permanent"],
                                                     "colors_any": ["W", "U", "B", "R", "G"]},
                                        "op": "exile", "stat_x": True})


# "Exile each permanent with mana value X or less that's one or more colors." (Ugin, the Spirit Dragon's −X): the
# bound is the X paid (effects_at), so colorless permanents and anything above X stay.
EFFECT_PATTERNS = [
    (r"exile each permanent with mana value x or less that's one or more colors", _ugin),
]


def scored(game, me, pw, effects, value):
    """(score, x) for each X the walker can pay: the effect's value at that X (``value(effects)``), plus a little
    for the loyalty kept, less for a walker the ability would kill."""
    out = []
    for x in range(1, pw.loyalty + 1):
        v = value(effects_at(effects, x))
        if v <= 0:
            continue
        left = pw.loyalty - x
        out.append((v + 0.25 * left - (2 if left == 0 else 0), x))
    return out


def choose(game, me, pw, effects) -> int | None:
    """The X to pay: the best-scored one (the smallest of equal scores), or None when no X does anything."""
    from .engine.policy import _mode_value
    options = scored(game, me, pw, effects, lambda effs: _mode_value(game, me, effs))
    if not options:
        return None
    return max(options, key=lambda t: (t[0], -t[1]))[1]


def options(game, me, pw):
    """(index, cost, effects) of each loyalty ability with X chosen: what the AI scores. A "−X" ability no X helps is
    left out."""
    for i, (cost, effects) in enumerate(pw.card.loyalty_abilities):
        if is_x(pw.card, i):
            x = choose(game, me, pw, effects)
            if x is None:
                continue
            yield i, -x, effects_at(effects, x)
        else:
            yield i, cost, effects
