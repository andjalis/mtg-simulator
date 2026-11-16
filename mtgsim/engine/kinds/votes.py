"""The vote kind (#634): see mtgsim/votes.py."""
from __future__ import annotations

from . import kind


@kind("vote")
def vote(game, p, eff, item, **_):
    from ...votes import resolve
    resolve(game, p, eff, item)
