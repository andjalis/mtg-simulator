"""Gain life equal to the mana value of "that card": the one just returned from a graveyard (``moved_card``) or the
revealed top card (``link_card``)."""
from . import kind


@kind("gain_card_mv")
def gain_card_mv(game, p, item, cause="gain", **_):
    card = getattr(item, "moved_card", None) or getattr(item, "link_card", None)
    cmc = getattr(card, "cmc", 0) or 0
    if cmc > 0:
        game.change_life(p, int(cmc), cause)
