"""Token creation from a parsed token description (mtgsim/cx_tokens.py)."""
from __future__ import annotations

from ...cx_tokens import create
from ..state import Player
from . import kind


@kind("cx_token")
def cx_token(game, p, eff, target, opp, **_):
    who = eff.data["who"]
    if who == "that_controller":
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
