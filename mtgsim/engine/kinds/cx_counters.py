"""Poison counters for a player named by context: see mtgsim/cx_counters.py."""
from __future__ import annotations

from . import kind
from ..state import Permanent, Player


@kind("cx_poison")
def cx_poison(game, p, eff, target, prev, **_):
    who = p if eff.data.get("who") == "you" else target
    if isinstance(who, Permanent):
        who = who.controller
    if isinstance(who, Player):
        who.counters["poison"] = who.counters.get("poison", 0) + eff.amount
        game.log(f"gets {eff.amount} poison counter(s)", who)


@kind("cx_distribute")
def cx_distribute(game, p, eff, item, **_):
    """The slot-0 effect splits ``amount`` counters over every target chosen for the group (see cx_counters)."""
    if eff.data.get("slot") or item is None:
        return
    group = [t for e, t in zip(item.effects, item.targets)
             if e.kind == "cx_distribute" and e.data.get("counter") == eff.data["counter"] and isinstance(t, Permanent)
             and t in t.controller.battlefield]
    chosen = []
    for t in group:
        if all(t is not c for c in chosen):
            chosen.append(t)
    if not chosen:
        return
    each, extra = divmod(eff.amount, len(chosen))
    for i, t in enumerate(chosen):
        t.counters[eff.data["counter"]] = t.counters.get(eff.data["counter"], 0) + each + (1 if i < extra else 0)
