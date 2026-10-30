"""Venture into the dungeon, the initiative, and die rolls (see dungeon_mechanics)."""
from . import kind


@kind("venture")
def venture(game, p, **_):
    from ... import dungeon_mechanics
    dungeon_mechanics.venture(game, p)


@kind("take_initiative")
def take_initiative(game, p, **_):
    from ... import dungeon_mechanics
    dungeon_mechanics.take_initiative(game, p)


@kind("die_roll")
def die_roll(game, p, eff, target, item, prev, **_):
    from ... import dungeon_mechanics
    dungeon_mechanics.roll(game, p, eff, item, target, prev)


@kind("die_amount")
def die_amount(game, p, eff, target, item, **_):
    from ... import dungeon_mechanics
    dungeon_mechanics.die_amount(game, p, eff, target, item)


@kind("die_check")
def die_check(game, p, eff, target, item, prev, **_):
    from ... import dungeon_mechanics
    dungeon_mechanics.die_check(game, p, eff, target, item, prev)
