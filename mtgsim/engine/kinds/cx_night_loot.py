"""Loot: draw cards, then discard as many."""
from . import kind


@kind("loot")
def loot(game, p, eff, **_):
    game.draw(p, eff.amount)
    for _ in range(min(eff.amount, len(p.hand))):
        card = p.ai.choose_discard(game, p)
        game.discard_card(p, card)
        game.log(f"discards {card.name}", p)
