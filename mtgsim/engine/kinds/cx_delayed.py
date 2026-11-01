"""Delayed end-step actions: see mtgsim/cx_delayed.py."""
from __future__ import annotations

from . import kind


@kind("cx_delay")
def cx_delay(game, p, eff, prev, item, **_):
    from ...cx_delayed import schedule
    schedule(game, p, eff, prev, item)


@kind("cx_delayed_do")
def cx_delayed_do(game, p, eff, item, **_):
    from ...cx_delayed import act
    act(game, p, eff, item)


@kind("cx_fresh_grant")
def cx_fresh_grant(game, p, eff, prev, item, **_):
    from ...cx_delayed import fresh_grant
    fresh_grant(game, p, eff, prev, item)
