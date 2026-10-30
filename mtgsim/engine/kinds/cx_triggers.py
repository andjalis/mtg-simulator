"""Crabomination's exile kind (see mtgsim.cx_triggers)."""
from . import kind


@kind("exile_three_zones")
def exile_three_zones(game, p, eff, target, item, **_):
    from ... import cx_triggers
    cx_triggers.resolve(game, p, eff, target, item)
