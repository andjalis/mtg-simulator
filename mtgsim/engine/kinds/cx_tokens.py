"""Token creation from a parsed token description (mtgsim/cx_tokens.py)."""
from __future__ import annotations

from ...cx_tokens import create
from ..state import Permanent, Player
from . import kind


@kind("cx_token")
def cx_token(game, p, eff, target, opp, **_):
    if "copy" in eff.data:                  # "a token that's a copy of that creature / it"
        from ...cards import CardDef
        from ...copies import make_copy
        card = target.copiable_card if isinstance(target, Permanent) else target if isinstance(target, CardDef) \
            else None
        if card is not None:
            create(game, p, dict(eff.data, card=make_copy(card, eff.data["copy"])), eff.amount)
        return
    who = eff.data["who"]
    if who == "that_controller":
        players = [target] if isinstance(target, Player) else []
    else:
        players = list(game.players) if who == "each" else [opp] if who == "opp" else [p]
    n = eff.amount * (len(game.players) - 1 if eff.data.get("per_opponent") else 1)
    for pl in players:
        create(game, pl, choose(game, pl, eff.data["choice"]) if "choice" in eff.data else eff.data, n)


def choose(game, p, specs):
    """"a Food token or a Treasure token": Treasure when the hand has a spell the lands can't pay for yet, else
    the first token of the list that isn't Treasure."""
    lands = sum(x.card.is_land for x in p.battlefield)
    wants_mana = any(not c.is_land and c.cmc > lands for c in p.hand)
    ranked = sorted(specs, key=lambda s: (s.get("kind") == "treasure") != wants_mana)
    return ranked[0]


@kind("cx_token_leave")
def cx_token_leave(game, p, eff, item, **_):
    """The delayed "sacrifice / exile that token at end of combat" of a token a cx_token created."""
    perm = item.source if item is not None else None
    if perm is not None and perm in perm.controller.battlefield:
        if eff.data["how"] == "sacrifice":
            game.sacrifice(perm)
        else:
            game.leave_battlefield(perm, "exile")
