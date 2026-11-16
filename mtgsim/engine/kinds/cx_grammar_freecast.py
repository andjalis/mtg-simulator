"""Kind for "you may cast a <kind> spell from your hand without paying its mana cost" (mtgsim.free_cast, #625)."""
from . import kind


@kind("hand_free_cast")
def hand_free_cast(game, p, eff, **_):
    from ...free_cast import resolve
    resolve(game, p, eff)
