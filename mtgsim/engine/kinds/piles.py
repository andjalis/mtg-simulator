"""The piles kind (#634): see mtgsim/piles.py."""
from __future__ import annotations

from . import kind


@kind("piles")
def piles(game, p, eff, target, item, **_):
    from ...piles import resolve
    resolve(game, p, eff, target, item)
