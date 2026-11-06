"""Trigger-head effects: see mtgsim/cx_trig_watch.py."""
from __future__ import annotations

from . import kind


@kind("cx_watch")
def cx_watch(game, p, eff, prev, item, **_):
    from ...cx_trig_watch import watch
    watch(game, p, eff, prev, item)
