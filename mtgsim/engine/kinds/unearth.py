"""Unearth (CR 702.84): an activated ability from the graveyard, not a spell."""
from . import kind


@kind("unearth_return")
def unearth_return(game, p, eff, **_):
    card = eff.data["card"]
    if card not in p.graveyard:
        return
    game.move_card(card, p.graveyard, p.exile, reason="unearth")     # off the graveyard; the permanent re-enters below
    p.exile.remove(card)
    perm = game.enter_battlefield(p, card)
    if perm is not None:
        perm.unearthed = True        # haste; exiled at the next end step or if it would leave the battlefield
