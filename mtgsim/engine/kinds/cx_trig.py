"""Trigger-head effects: see mtgsim/cx_trig_watch.py."""
from __future__ import annotations

from . import kind


@kind("cx_watch")
def cx_watch(game, p, eff, prev, item, **_):
    from ...cx_trig_watch import watch
    watch(game, p, eff, prev, item)


@kind("cx_draw_up_to_n")
def cx_draw_up_to_n(game, p, eff, **_):
    """"You may draw up to N cards": as many as wanted from 0 to N; the AI draws all it safely can (never from an
    empty library)."""
    game.draw(p, max(0, min(eff.amount, len(p.library))))
