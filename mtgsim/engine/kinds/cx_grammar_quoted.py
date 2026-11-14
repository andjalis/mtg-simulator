"""The dies-return of a granted quoted ability (#338): "When this creature dies, return it to the battlefield
[tapped] under its owner's control [with a +1/+1 counter on it]."""
from . import kind
from ..state import Permanent


@kind("cx_return_died")
def cx_return_died(game, p, eff, item, **_):
    """Return the card the trigger's permanent became when it died, if it is still that card in its owner's
    graveyard: it went straight from the battlefield there and hasn't moved since (a card exiled from the graveyard
    in response, or that left and came back, is a new object)."""
    gone = item.source if item is not None else None
    if not isinstance(gone, Permanent) or gone in gone.controller.battlefield:
        return
    card, owner = gone.front, gone.owner
    if card not in owner.graveyard or getattr(card, "last_zone", "battlefield") != "battlefield" or \
            getattr(gone, "last_destination", "graveyard") != "graveyard":
        return
    owner.graveyard.remove(card)
    game.log(f"{card.name} returns to the battlefield under {owner}'s control", owner)
    back = game.enter_battlefield(owner, card, tapped=eff.data.get("tapped", False),
                                  counters={"+1/+1": 1} if eff.data.get("counter") else None)
    from . import HANDLERS
    for then in eff.data.get("then", ()):      # "... and suspect it": "it" is the returned permanent
        if then.target == "prev" and back is None:
            continue
        HANDLERS[then.kind](game, p=p, eff=then, target=back if then.target == "prev" else None, item=item,
                            opp=game.opponent(p), prev=back, cause=f"cx_return_died: {then.kind}", k=then.kind,
                            source=back)
