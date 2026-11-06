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
    for pl in players:
        create(game, pl, eff.data, eff.amount)
