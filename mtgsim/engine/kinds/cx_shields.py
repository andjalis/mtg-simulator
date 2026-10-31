"""Damage prevention and redirection for the turn: see mtgsim/cx_shields.py."""
from __future__ import annotations

from . import kind
from ..state import Permanent


@kind("cx_shield")
def cx_shield(game, p, eff, target, prev, item, **_):
    from ...cx_shields import add_rule
    source = getattr(item, "source", None) if item is not None else None
    source = source if isinstance(source, Permanent) else None
    if add_rule(game, p, eff.data["rule"], source, target=target, prev=prev):
        game.log("sets up a damage shield", p)
