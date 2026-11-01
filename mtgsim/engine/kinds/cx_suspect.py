"""Suspect riders: see mtgsim/cx_suspect.py."""
from __future__ import annotations

from . import kind
from ..state import Permanent


@kind("cx_unsuspect")
def cx_unsuspect(game, p, eff, prev, item, **_):
    from ...cx_suspect import unsuspect
    if eff.data.get("all"):
        for pl in game.players:
            for x in pl.battlefield:
                unsuspect(game, p, x)
        return
    perm = getattr(item, "source", None) if eff.target == "self" else prev
    if isinstance(perm, Permanent):
        unsuspect(game, p, perm)
