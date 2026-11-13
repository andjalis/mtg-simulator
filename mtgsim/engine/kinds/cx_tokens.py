"""Token creation from a parsed token description (mtgsim/cx_tokens.py)."""
from __future__ import annotations

from ...cx_tokens import create
from ..state import Permanent, Player
from . import kind


def owner(game, item, target):
    """The owner of "it" in "its owner creates": the previous effect's object, else the card the spell exiled from a
    graveyard, else the source permanent; read from the player whose zone holds that exact object."""
    obj = target if target is not None else getattr(item, "exiled_card", None)
    if obj is None and item is not None and isinstance(item.source, Permanent):
        obj = item.source
    if isinstance(obj, Permanent):
        return obj.owner if isinstance(getattr(obj, "owner", None), Player) else None
    return next((pl for pl in game.players for zone in (pl.graveyard, pl.exile, pl.hand, pl.library)
                 if any(c is obj for c in zone)), None) if obj is not None else None


@kind("cx_token")
def cx_token(game, p, eff, target, opp, item=None, **_):
    if "copy" in eff.data:                  # "a token that's a copy of that creature / it"
        from ...cards import CardDef
        from ...copies import make_copy
        card = target.copiable_card if isinstance(target, Permanent) else target if isinstance(target, CardDef) \
            else None
        context = getattr(item, "context", None)
        if card is None and eff.data.get("ref") == "card" and isinstance(context, Player) and context.discarded_cards:
            card = context.discarded_cards[-1]      # "whenever you discard a creature card, ... that card"
        if card is not None:
            from ...copies import entry_counters
            if eff.data.get("who") == "that_controller":       # "its controller creates a token that's a copy of it"
                p = target.controller if isinstance(target, Permanent) else p
            create(game, p, dict(eff.data, card=make_copy(card, eff.data["copy"]),
                                 counters=entry_counters(eff.data["copy"], getattr(item, "x", 0)) or None), eff.amount)
        return
    who = eff.data["who"]
    if who == "owner":
        found = owner(game, item, target)
        players = [found] if found is not None else []
    elif who == "that_controller":
        players = [target] if isinstance(target, Player) else []
    elif who == "they":                     # the previous object's controller, else the trigger's player
        context = getattr(item, "context", None)
        players = [target] if isinstance(target, Player) else [context] if isinstance(context, Player) else []
    else:
        players = list(game.players) if who == "each" else [opp] if who == "opp" else [p]
    n = eff.amount * (len(game.players) - 1 if eff.data.get("per_opponent") else 1)
    if eff.data.get("devotion"):            # "equal to your devotion to <colours>": mana symbols of yours
        n *= sum(devotion(x.card, eff.data["devotion"]) for x in p.battlefield)
    for pl in players:
        create(game, pl, choose(game, pl, eff.data["choice"]) if "choice" in eff.data else eff.data, n)


def devotion(card, colors) -> int:
    """The mana symbols of card's cost that are any of colors. A hybrid pip counts once if it has one of them;
    the cost parser folds each hybrid pip into its first colour, so those are taken back out first."""
    hybrid = getattr(card, "hybrid", ()) or ()
    plain = sum(card.mana_cost.get(c, 0) - sum(pip[0] == c for pip in hybrid) for c in colors)
    return plain + sum(any(c in pip for c in colors) for pip in hybrid)


def choose(game, p, specs):
    """"a Food token or a Treasure token": Treasure when the hand has a spell the lands can't pay for yet, else
    the first token of the list that isn't Treasure."""
    lands = sum(x.card.is_land for x in p.battlefield)
    wants_mana = any(not c.is_land and c.cmc > lands for c in p.hand)
    ranked = sorted(specs, key=lambda s: (s.get("kind") == "treasure") != wants_mana)
    return ranked[0]


@kind("cx_token_leave")
def cx_token_leave(game, p, eff, item, **_):
    """The delayed "sacrifice / exile that token at end of combat" of a token a cx_token created."""
    perm = item.source if item is not None else None
    if perm is not None and perm in perm.controller.battlefield:
        if eff.data["how"] == "sacrifice":
            game.sacrifice(perm)
        else:
            game.leave_battlefield(perm, "exile")
