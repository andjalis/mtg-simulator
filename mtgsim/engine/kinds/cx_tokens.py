"""Token creation from a parsed token description (mtgsim/cx_tokens.py)."""
from __future__ import annotations

from ...cx_tokens import create
from ..state import Permanent, Player
from . import kind


def owner(game, item, target):
    """The owner of "it" in "its owner creates": the previous effect's object, else the card the spell exiled from a
    graveyard, else the source permanent; read from the player whose zone holds that exact object."""
    obj = target if target is not None else getattr(item, "exiled_card", None)
    if obj is None and item is not None and isinstance(item.source, Permanent):
        obj = item.source
    if isinstance(obj, Permanent):
        return obj.owner if isinstance(getattr(obj, "owner", None), Player) else None
    return next((pl for pl in game.players for zone in (pl.graveyard, pl.exile, pl.hand, pl.library)
                 if any(c is obj for c in zone)), None) if obj is not None else None


@kind("cx_token")
def cx_token(game, p, eff, target, opp, item=None, **_):
    if "copy" in eff.data:                  # "a token that's a copy of that creature / it"
        from ...cards import CardDef
        from ...copies import make_copy
        card = target.copiable_card if isinstance(target, Permanent) else target if isinstance(target, CardDef) \
            else None
        if card is not None:
            create(game, p, dict(eff.data, card=make_copy(card, eff.data["copy"])), eff.amount)
        return
    who = eff.data["who"]
    if who == "owner":
        found = owner(game, item, target)
        players = [found] if found is not None else []
    elif who == "that_controller":
        players = [target] if isinstance(target, Player) else []
    else:
        players = list(game.players) if who == "each" else [opp] if who == "opp" else [p]
    n = eff.amount * (len(game.players) - 1 if eff.data.get("per_opponent") else 1)
    for pl in players:
        create(game, pl, eff.data, n)


@kind("cx_token_leave")
def cx_token_leave(game, p, eff, item, **_):
    """The delayed "sacrifice / exile that token at end of combat" of a token a cx_token created."""
    perm = item.source if item is not None else None
    if perm is not None and perm in perm.controller.battlefield:
        if eff.data["how"] == "sacrifice":
            game.sacrifice(perm)
        else:
            game.leave_battlefield(perm, "exile")
