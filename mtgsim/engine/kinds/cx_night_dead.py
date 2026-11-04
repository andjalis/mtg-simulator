"""Return "that card" to the battlefield under p's control: the creature that just died (a dies trigger's context) or
the creature the same ability just exiled (a blink: Cloudshift, Restoration Angel)."""
from . import kind
from ..state import Permanent


@kind("return_dead")
def return_dead(game, p, eff, item, prev=None, **_):
    gone = prev if isinstance(prev, Permanent) else item.context if item is not None else None
    if not isinstance(gone, Permanent) or gone in gone.controller.battlefield:
        return
    card, owner = gone.front, gone.owner
    zone = owner.graveyard if card in owner.graveyard else owner.exile if card in owner.exile else None
    if zone is None:
        return
    zone.remove(card)
    perm = game.enter_battlefield(p, card, counters={"+1/+1": 1} if eff.data.get("counter") else None)
    if perm is not None:
        game.log(f"{card.name} returns to the battlefield under {p}'s control", p)
