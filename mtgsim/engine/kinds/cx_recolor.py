"""Colour and type changes: see mtgsim/cx_recolor.py."""
from __future__ import annotations

from . import kind
from ..state import Permanent


@kind("cx_retype")
def cx_retype(game, p, eff, target, prev, item, **_):
    from ...cx_recolor import retype
    perm = {"self": getattr(item, "source", None), "prev": prev}.get(eff.target, target)
    if isinstance(perm, Permanent) and perm in perm.controller.battlefield:
        retype(game, p, eff, perm)
