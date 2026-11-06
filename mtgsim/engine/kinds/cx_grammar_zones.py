"""Kinds for the grammar's zone-change verbs (see mtgsim.cx_grammar_zones)."""
from ..policy import perm_value
from ..state import Permanent, Player
from . import kind


@kind("cx_edict")
def edict(game, p, eff, target, item, **_):
    """"<player> sacrifices N <noun phrase>": that player chooses (the least valuable first) among the permanents
    they control that match, fixed before any is sacrificed."""
    if not isinstance(target, Player):
        return
    from ... import counter_mechanics
    from ...cx_grammar import group_members
    source = item.source if item is not None else None
    pool = group_members(game, target, {"group": eff.data["noun"]}, source, target)
    pool = [x for x in pool if not (eff.data.get("other") and x is source)]
    victims = sorted(pool, key=lambda x: (not x.card.is_token, perm_value(x)))[:eff.amount]
    sources = counter_mechanics.death_sources(game)
    for v in victims:
        if isinstance(v, Permanent) and v in target.battlefield:
            game.log(f"sacrifices {v.card.name}", target)
            game.sacrifice(v, counter_sources=sources)
