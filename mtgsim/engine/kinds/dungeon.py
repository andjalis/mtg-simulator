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


@kind("regrow_cmc")
def regrow_cmc(game, p, eff, **_):
    from ... import dungeon_mechanics
    dungeon_mechanics.regrow_cmc(game, p, eff)


@kind("fetch_basic_n")
def fetch_basic_n(game, p, eff, **_):
    from ... import dungeon_mechanics
    dungeon_mechanics.fetch_basic_n(game, p, eff)


@kind("destroy_power_ge")
def destroy_power_ge(game, p, eff, **_):
    from ... import dungeon_mechanics
    dungeon_mechanics.destroy_power_ge(game, p, eff)


@kind("remove_all_counters")
def remove_all_counters(game, p, eff, item, **_):
    from ... import dungeon_mechanics
    dungeon_mechanics.remove_all_counters(game, p, eff, item)
