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
