"""``cx_sac_that``: "sacrifice that permanent" (see mtgsim/cx_trig_attach.py, #538)."""
from __future__ import annotations

from ..state import Permanent
from . import kind


@kind("cx_sac_that")
def sac_that(game, p, target, **_):
    """You sacrifice it only if you still control it (and it is still on the battlefield)."""
    if isinstance(target, Permanent) and target.controller is p and target in p.battlefield:
        game.sacrifice(target)
