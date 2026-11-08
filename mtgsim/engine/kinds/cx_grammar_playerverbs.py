"""Kinds for the grammar's player verbs (see mtgsim.cx_grammar_playerverbs): discards that read their player."""
from ..state import Player
from . import kind


def _who(game, p, eff, target, item, prev):
    """The discarding players: data["who"] (an untargeted object), the player ``target`` (inside cx_players or a
    target player), else the controller."""
    if eff.data.get("who"):
        from ...cx_grammar import players
        return players(game, p, eff.data["who"], item, prev, target)
    return [target if isinstance(target, Player) else p]


@kind("cx_discard_random")
def discard_random(game, p, eff, target, item, prev=None, **_):
    n = getattr(item, "x", 0) if eff.data.get("x") else eff.amount
    for who in _who(game, p, eff, target, item, prev):
        for _ in range(min(n, len(who.hand))):
            card = game.rng.choice(list(who.hand))
            game.discard_card(who, card)
            game.log(f"discards {card.name} at random", who)


@kind("cx_discard_hand")
def discard_hand(game, p, eff, target, item, prev=None, **_):
    for who in _who(game, p, eff, target, item, prev):
        for card in list(who.hand):
            game.discard_card(who, card)
        game.log("discards their hand", who)
