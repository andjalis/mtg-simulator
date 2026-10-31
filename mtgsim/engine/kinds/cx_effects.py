"""Handlers for mtgsim/cx_effects.py."""
from __future__ import annotations

from . import kind
from ... import cx_effects


@kind("cx_gy_top")
def gy_top(game, p, eff, **_):
    cx_effects.gy_top(game, p, eff)


@kind("cx_gy_random")
def gy_random(game, p, eff, **_):
    cx_effects.gy_random(game, p, eff)


@kind("cx_exile_turn")
def exile_turn(game, p, **_):
    game.cx_exile_turn = game.turn      # "If a creature would die this turn, exile it instead."


@kind("cx_win")
def win(game, p, eff, **_):
    cx_effects.win(game, p, eff)        # "You win the game." / "You lose the game."
