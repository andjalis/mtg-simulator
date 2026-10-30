"""Divided damage kind (see mtgsim.cx_damage)."""
from . import kind


@kind("divided_damage")
def divided_damage(game, p, eff, target, item, **_):
    from ... import cx_damage
    cx_damage.resolve(game, p, eff, target, item)
