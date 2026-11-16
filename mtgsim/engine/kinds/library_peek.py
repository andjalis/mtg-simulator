"""Kinds for looking at a target player's library (mtgsim.library_peek, #346)."""
from __future__ import annotations

from . import kind
from ..state import Player


def wants_lands(who) -> bool:
    """Whether who would rather draw lands than spells next (the rule reorder_top already used)."""
    return sum(x.card.is_land for x in who.battlefield) + sum(c.is_land for c in who.hand) < 5


def order_top(who, n: int, friendly: bool) -> None:
    """Put the top n of who's library back: the cards who wants on top if friendly, else at the bottom of the n."""
    n = min(n, len(who.library))
    if n < 2:
        return
    top = who.library[-n:]
    want = wants_lands(who)
    good = (lambda c: (c.is_land == want, c.cmc if not want else 0))     # sorts the wanted ones last (= on top)
    top.sort(key=good, reverse=not friendly)
    who.library[-n:] = top


def top_is_good(who, n: int = 1) -> bool:
    top = who.library[-n:]
    return bool(top) and all(c.is_land == wants_lands(who) for c in top)


@kind("peek_library")
def peek_library(game, p, eff, target, **_):
    """"Look at the top N cards of target player's library": no change to the game; it names the player for a
    following "you may have that player shuffle"."""
    who = target if isinstance(target, Player) else p
    game.log(f"looks at the top {min(eff.amount, len(who.library))} cards of {who.name}'s library", p)


@kind("may_shuffle_prev")
def may_shuffle_prev(game, p, eff, target, prev, item, **_):
    """"You may have that player shuffle": the player whose library the previous effect looked at. Shuffled only
    when the controller dislikes what is on top now (after its own reordering that is rarely the case)."""
    who = next((x for x in (target, prev) if isinstance(x, Player)), None) or next(
        (t for t in (getattr(item, "targets", None) or []) if isinstance(t, Player)), None)
    if who is None:
        return
    dislike = not top_is_good(who) if who is p else top_is_good(who)
    if dislike:
        who.library.shuffle(game.rng)
        game.log(f"has {who.name} shuffle their library", p)


@kind("peek_mill")
def peek_mill(game, p, eff, target, **_):
    """Look at the top N of target player's library; keep amount2 of them on top, the rest into the graveyard.
    The controller keeps what is worst for that player (or best, for its own library)."""
    who = target if isinstance(target, Player) else p
    n = min(eff.amount, len(who.library))
    if n == 0:
        return
    order_top(who, n, friendly=(who is p))      # the wanted-by-the-chooser ones end up on top
    keep = min(eff.amount2, n)
    milled = who.library[-n:len(who.library) - keep] if keep else who.library[-n:]
    for c in list(milled):
        game.move_card(c, who.library, who.graveyard, reason="mill")
    game.log(f"looks at {n} of {who.name}'s library and mills {len(milled)}", p)
