"""Kinds for "<player> <puts cards away>, then draw(s) that many cards" (mtgsim.cx_grammar_thatmany).

cx_away puts the player's cards away and records how many actually went, per player, on the resolving item;
cx_draw_that_many draws that count (plus or minus a fixed amount) for the same player, or with data["greatest"]
the largest count any player put away (Windfall). Both run inside cx_players
with target = the player."""
from ..state import Player
from . import kind


def _counts(game, item) -> dict:
    """The per-player counts of this resolution (on the item; on the game for an item-less resolution)."""
    holder = item if item is not None else game
    counts = getattr(holder, "cx_that_many", None)
    if counts is None or counts[0] is not item:
        counts = (item, {})
        holder.cx_that_many = counts
    return counts[1]


@kind("cx_away")
def away(game, p, eff, target, item=None, **_):
    who = target if isinstance(target, Player) else p
    mode = eff.data["mode"]
    if mode.endswith("_any"):       # "any number of cards": the player's choice
        cards = list(game.hook(who, "choose_rummage")(game, who, len(who.hand)))
    else:
        cards = list(who.hand)
    n = 0
    for card in cards:
        if card not in who.hand:
            continue
        if mode.startswith("discard"):
            game.discard_card(who, card)
        elif mode == "exile_hand":
            game.move_card(card, who.hand, who.exile, reason="exile")
        else:           # shuffled into or put on the bottom of the library
            game.move_card(card, who.hand, who.library, reason="hand_to_library")
            if mode.startswith("bottom"):
                who.library.remove(card)
                who.library.insert(0, card)         # the library's top is its end
        n += 1
    if mode.startswith("shuffle"):
        who.library.shuffle(game.rng)
    _counts(game, item)[id(who)] = n
    game.log(f"puts {n} card(s) away ({mode})", who)


@kind("cx_draw_that_many")
def draw_that_many(game, p, eff, target, item=None, **_):
    who = target if isinstance(target, Player) else p
    counts = _counts(game, item)
    base = max(counts.values(), default=0) if eff.data.get("greatest") else counts.get(id(who), 0)
    n = max(0, base + eff.data.get("delta", 0))
    if n:
        game.draw(who, n)


@kind("cx_discard_drawn")
def discard_drawn(game, p, eff, target, item=None, **kw):
    """"..., then discard a card for each card drawn this way": as many cards as the draw just before it in this
    resolution actually drew (kinds.cards.draw records it), the player's choice."""
    import dataclasses
    from . import HANDLERS
    tw = getattr(item, "this_way", None) if item is not None else None
    n = tw[2] if tw is not None and tw[0] == "drawn" else 0
    if n:
        HANDLERS["discard"](game, p=p, eff=dataclasses.replace(eff, kind="discard", amount=n), target=target,
                            item=item, **kw)
