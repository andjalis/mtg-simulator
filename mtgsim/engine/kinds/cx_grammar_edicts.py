"""Kinds for the grammar's edict verbs (see mtgsim.cx_grammar_edicts)."""
from ..policy import perm_value
from ..state import Player
from . import kind


@kind("cx_keep")
def keep(game, p, eff, target, item, **_):
    """"<player> chooses N <noun> / an X, a Y, ... they control, then sacrifices the rest": that player keeps the most
    valuable matching permanents (the nouns with the fewest candidates are filled first), then sacrifices every other
    permanent of the scope at once."""
    if not isinstance(target, Player):
        return
    from ...cx_grammar import group_members
    from ... import counter_mechanics
    source = item.source if item is not None else None
    scope = group_members(game, target, {"group": eff.data["scope"]}, source, target)
    wanted = []
    for group, n in eff.data["keep"]:
        members = group_members(game, target, {"group": group}, source, target)
        wanted.append((members, n))
    kept: list = []
    for members, n in sorted(wanted, key=lambda w: len(w[0])):
        free = sorted((x for x in members if x not in kept), key=perm_value, reverse=True)
        kept += free[:n]
    victims = [x for x in scope if x not in kept]
    sources = counter_mechanics.death_sources(game)
    for v in victims:
        if v in target.battlefield:
            game.log(f"sacrifices {v.card.name}", target)
            game.sacrifice(v, counter_sources=sources)
