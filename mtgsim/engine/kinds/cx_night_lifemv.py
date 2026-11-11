"""Gain life equal to the mana value of "that card": the one just returned from a graveyard (``moved_card``) or the
revealed top card (``link_card``)."""
from . import kind


@kind("gain_card_mv")
def gain_card_mv(game, p, item, cause="gain", **_):
    from ...referent import card_stat
    cmc = card_stat(item, "mana value")
    if cmc > 0:
        game.change_life(p, int(cmc), cause)


@kind("gain_card_stat")
def gain_card_stat(game, p, eff, item, cause, **_):
    from ...referent import card_stat
    value = max(0, card_stat(item, eff.data["stat"]))
    game.change_life(p, -value if eff.data.get("lose") else value, cause)
