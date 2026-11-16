"""The return_self_bf kind (#635): see mtgsim/enter_transformed.py."""
from __future__ import annotations

from . import kind


@kind("return_self_bf")
def return_self_bf(game, p, eff, item, target=None, **_):
    from ...enter_transformed import resolve
    resolve(game, p, eff, item, target)
