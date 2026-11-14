"""Capped counter recharges (the Clockwork creatures, part of #345):

    {X}, {T}: Put up to X +1/+0 counters on this creature. This ability can't cause the total number of +1/+0
    counters on this creature to be greater than four. Activate only during your upkeep.

The two sentences are folded (``SUBS``) into one ``cap_counters`` effect on ~ (``data``: counter kind, cap, X): it
puts min(X, cap - current) counters. ``Game.ability_x`` chooses at most cap - current for it, and ``upkeep`` is the
AI's use: during its upkeep it recharges such a creature once it is down to half its cap or less (tapping it keeps it
out of combat this turn, so a nearly full one isn't worth it).
"""
from __future__ import annotations

import re

_N = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_KIND = r"([+-]\d+/[+-]\d+|[a-z]+)"

SUBS = [
    (re.compile(rf"put up to x {_KIND} counters on ~\. this ability can't cause the total number of \1 counters on ~ "
                rf"to be greater than (one|two|three|four|five|six|seven|eight|nine|ten|\d+)\.", re.I),
     lambda m: f"CAPCOUNTERS {m[1]} {m[2].lower()}."),
]


def _effect(m):
    from .cards.model import Effect
    n = m[2].lower()
    cap = _N[n] if n in _N else int(n)
    return Effect("cap_counters", 0, target="self", data={"counter": m[1], "cap": cap, "x": True})


EFFECT_PATTERNS = [(rf"CAPCOUNTERS {_KIND} (\w+)", _effect)]


def room(perm, eff) -> int:
    return max(0, eff.data["cap"] - perm.counters.get(eff.data["counter"], 0))


def apply(game, p, eff, perm):
    """Put up to X (eff.amount) counters on perm, never past the cap."""
    n = min(eff.amount, room(perm, eff))
    if n > 0:
        kind = eff.data["counter"]
        perm.counters[kind] = perm.counters.get(kind, 0) + n
        game.log(f"puts {n} {kind} counters on {perm.card.name} ({perm.counters[kind]})", p)


def _ability(perm):
    for i, act in enumerate(perm.card.activated):
        effs = [e for e in act.effects if e.kind == "cap_counters"]
        if effs:
            return i, effs[0]
    return None, None


def x_limit(perm, act):
    """The most X worth paying for a cap_counters ability (Game.ability_x)."""
    effs = [e for e in act.effects if e.kind == "cap_counters"]
    return room(perm, effs[0]) if effs else None


def upkeep(game, p):
    """The AI's recharge during its own upkeep: a creature at half its cap or less, X = what fits."""
    for perm in list(p.battlefield):
        idx, eff = _ability(perm)
        if eff is None or perm.tapped or room(perm, eff) * 2 < eff.data["cap"]:
            continue
        if game.can_activate(p, perm, idx):
            x = game.ability_x(p, perm, perm.card.activated[idx])
            if x:
                game.activate_ability(p, perm, idx, x=x)
