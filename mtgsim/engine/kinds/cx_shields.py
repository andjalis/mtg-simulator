"""Damage prevention and redirection for the turn: see mtgsim/cx_shields.py."""
from __future__ import annotations

from . import kind
from ..state import Permanent


@kind("cx_shield")
def cx_shield(game, p, eff, target, prev, item, **_):
    from ...cx_shields import add_rule
    source = getattr(item, "source", None) if item is not None else None
    source = source if isinstance(source, Permanent) else None
    rule = eff.data["rule"]
    if eff.data.get("pool_x"):
        rule = dict(rule, budget=getattr(item, "x", 0) or 0)
    until = p if eff.data.get("until_next_turn") else None      # "until your next turn" (#839)
    if add_rule(game, p, rule, source, target=target, prev=prev, until=until):
        game.log("sets up a damage shield", p)


@kind("cx_shield_rider")
def cx_shield_rider(game, p, eff, **_):
    from ...cx_shields import add_rider
    add_rider(game, p, eff.data["rider"])
