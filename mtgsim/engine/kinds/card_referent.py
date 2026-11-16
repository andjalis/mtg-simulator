"""Kinds for amounts read from a card an earlier effect revealed (mtgsim.card_referent)."""
from ..state import Player
from . import kind


@kind("reveal_random")
def reveal_random(game, p, target, item=None, **_):
    """"Target player reveals a card at random from their hand": the card stays in the hand; "that card" is it."""
    from ...referent import remember_card
    remember_card(item, None)
    if not isinstance(target, Player) or not target.hand:
        return
    card = game.rng.choice(target.hand)
    remember_card(item, card)
    game.log(f"reveals {card.name} at random", target)
