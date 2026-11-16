"""Face states (#635): "transform it" bound to the right object."""
from __future__ import annotations

from . import kind
from ..state import Permanent


@kind("transform_it")
def transform_it(game, target, item, **_):
    """"Transform it": the object "it" names, which is the previous object or the permanent the trigger fired on
    (the entering Werewolf, a conjured card), and the source itself when there is none (a player was dealt damage,
    an upkeep trigger, an activated ability on ~)."""
    obj = target if isinstance(target, Permanent) else None
    if obj is None and item is not None and isinstance(item.source, Permanent):
        obj = item.source
    if obj is not None and obj in obj.controller.battlefield:
        game.transform(obj)
