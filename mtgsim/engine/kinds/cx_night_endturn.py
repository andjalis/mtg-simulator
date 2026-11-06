"""End the turn: exile the rest of the stack and skip to cleanup."""
from . import kind


@kind("end_turn")
def end_turn(game, p, item, **_):
    for other in list(game.stack):
        if other is item:
            continue
        game.stack.remove(other)
        if other.kind == "spell":
            base, _kind, _ = game._origin(other.card)
            owner = getattr(base, "owner", None) or other.controller
            owner.exile.append(base)
        game.log(f"{other} is exiled from the stack", p)
    if item is not None:
        item.exile_self = True            # "including this card"
    for pl in game.players:
        pl.action_lock_turn = game.turn   # nobody may cast or activate for the rest of the turn
    game.turn_ended = True
    game.log("ends the turn", p)
