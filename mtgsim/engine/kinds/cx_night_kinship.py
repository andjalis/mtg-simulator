"""Kinship: at your upkeep look at the top card; if it shares a creature type with the source, reveal it for a bonus."""
from ..state import Permanent
from . import kind


def shares_type(top, source) -> bool:
    if "Creature" not in top.types and "Kindred" not in top.types:
        return False
    return bool(set(top.subtypes) & set(source.card.subtypes)) or "Changeling" in top.keywords or \
        "changeling" in top.keywords or "changeling" in source.card.keywords


@kind("kinship")
def kinship(game, p, eff, item, **_):
    source = item.source if item is not None else None
    if not isinstance(source, Permanent) or not p.library:
        return
    top = p.library[-1]
    if not shares_type(top, source):
        return
    game.log(f"reveals {top.name} (kinship)", p)
    for sub in eff.data["effects"]:
        game.resolve(p, sub, None, item)
