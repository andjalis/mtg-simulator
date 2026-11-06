"""Flip the source permanent to its other face."""
from . import kind
from ..state import Permanent


@kind("flip_self")
def flip_self(game, p, item, **_):
    src = item.source if item is not None else None
    if isinstance(src, Permanent) and src in src.controller.battlefield and src.card.back is not None \
            and getattr(src, "front_face", None) is None:
        game.transform(src)
