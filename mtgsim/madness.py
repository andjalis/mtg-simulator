"""Madness (CR 702.35): a discarded card with madness is exiled instead of going to the graveyard, and a
trigger lets its owner cast it for the madness cost; otherwise it is put into the graveyard."""


def madness_cost(card):
    return next((a for a in card.alt_costs if a.kind == "madness"), None)


def discard_destination(game, p, card):
    """Where a discard goes: exile for a madness card, else the graveyard."""
    return p.exile if madness_cost(card) is not None else p.graveyard


def after_discard(game, p, card):
    """Queue the madness trigger for a card just exiled by a discard."""
    from .cards import Effect
    alt = madness_cost(card)
    if alt is not None and card in p.exile:
        game.queue_trigger(p, [Effect("madness", data={"card": card, "alt": alt})], None,
                           f"{card.name}: madness")


_GRAVEYARD_VALUE = ("flashback", "escape", "unearth", "jump_start", "retrace", "aftermath", "recover", "embalm",
                    "eternalize", "disturb")


def declines(card):
    """Madness is optional ("you may cast it"): the AI keeps a card that is worth more in the graveyard there."""
    return any(a.kind in _GRAVEYARD_VALUE for a in card.alt_costs)


def resolve(game, p, eff):
    """The madness trigger: cast the exiled card for its madness cost, or put it into the graveyard."""
    card, alt = eff.data["card"], eff.data["alt"]
    if card not in p.exile:
        return
    if not declines(card) and game.cast(p, game._variant(card, "madness", alt)):
        return
    if card in p.exile:
        game.log(f"puts {card.name} into the graveyard (madness not cast)", p)
        game.move_card(card, p.exile, p.graveyard, reason="madness")
