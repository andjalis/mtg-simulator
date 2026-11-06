"""Howling Mine family: "At the beginning of each player's draw step, that player draws an additional card."

Read as ``draw_active``: the player whose draw step it is draws (the handler is in engine/kinds/cx_night_draw.py)."""
from __future__ import annotations


def _draw(m):
    from .cards.model import Effect
    return [Effect("draw_active", 1)]


EFFECT_PATTERNS = [(r"that player draws an additional card", _draw)]
