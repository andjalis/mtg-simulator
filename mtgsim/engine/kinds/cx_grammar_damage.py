"""Kinds for the grammar's damage verbs (see mtgsim.cx_grammar_damage)."""
from ..state import Permanent, Player
from . import kind


def damage_source(item, source, prev=None):
    """The object dealing the damage: "self" the resolving spell or permanent, "prev" ("it" / "that creature") the
    previous object (a trigger starts it at the permanent it triggered on), else the object itself, "host" the
    enchanted or equipped creature."""
    if item is None:
        return None
    own = item.source if item.source is not None else item.card
    if source == "prev":
        return prev if isinstance(prev, Permanent) else own
    if source == "host":
        return (item.source.aura_host or item.source.attached_to) if isinstance(item.source, Permanent) else None
    return own


@kind("cx_damage")
def cx_damage(game, p, eff, target, item, prev=None, cause=None, **_):
    """Real damage from the named source to the recipient: a permanent or player (``target``), or the players
    ``data["who"]`` names ("that creature's controller", "each opponent", "defending player")."""
    from ...cx_grammar import players
    src = damage_source(item, eff.data.get("source", "self"), prev)
    if src is None:
        return
    n = getattr(item, "x", 0) if eff.data.get("x") else eff.amount
    if eff.data.get("source_power"):        # "damage equal to its power": the source's power as it deals it
        n = max(0, src.power) if isinstance(src, Permanent) else 0
    victims = players(game, p, eff.data["who"], item, prev, target) if eff.data.get("who") else [target]
    by = src.controller if isinstance(src, Permanent) else p
    for victim in victims:
        if isinstance(victim, Player) or isinstance(victim, Permanent) and victim in victim.controller.battlefield:
            game.deal_damage(victim, n, by=by, cause=cause or "noncombat damage", source=src)
