"""``cx_turn_trigger``: "Whenever <event> this turn, <effects>" (see mtgsim/cx_trig_turn.py, #399)."""
from __future__ import annotations

from . import kind


@kind("cx_turn_trigger")
def turn_trigger(game, p, eff, item=None, **_):
    from ...cx_trig_turn import register
    register(game, p, eff, item)
