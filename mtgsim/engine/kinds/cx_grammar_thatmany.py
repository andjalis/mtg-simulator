"""Kinds for "<player> <puts cards away>, then draw(s) that many cards" (mtgsim.cx_grammar_thatmany).

cx_away puts the player's cards away and records how many actually went, per player, on the resolving item;
cx_draw_that_many draws that count (plus or minus a fixed amount) for the same player, or with data["greatest"]
the largest count any player put away (Windfall). Both run inside cx_players
with target = the player."""
from ..state import Permanent, Player, note_this_way
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
    if mode == "sac_any":
        _sacrifice_any(game, who, eff, item)
        return
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


# ---------------------------------------------------------------- "Sacrifice any number of <types>"

def sac_candidates(game, who, spec, source):
    """who's permanents of the named types ("other": not the source)."""
    def fits(x, t):
        return {"permanent": True, "token": x.card.is_token, "artifact": x.card.is_artifact, "creature": x.is_creature,
                "land": x.card.is_land, "enchantment": "Enchantment" in x.card.types,
                "planeswalker": "Planeswalker" in x.card.types}[t]
    return [x for x in who.battlefield if not (spec["other"] and x is source) and any(fits(x, t) for t in spec["types"])]


def choose_sac_any(game, me, cands) -> list:
    """The permanents worth less than a card, chosen conservatively: Clue tokens; other noncreature tokens
    (Treasure, Food, ...) once five lands are out; lands beyond the seventh. Never a creature, a nontoken
    artifact or enchantment, or a planeswalker. An AI may override it with its own choose_sac_any."""
    own = getattr(me.ai, "choose_sac_any", None)
    if own is not None:
        return own(game, me, cands)
    lands_out = sum(1 for x in me.battlefield if x.card.is_land)
    picks = []
    for x in cands:
        if x.is_creature or not x.card.is_token:
            continue
        if x.card.token_kind == "clue" or lands_out >= 5:
            picks.append(x)
    lands = [x for x in cands if x.card.is_land and not x.is_creature]
    picks += sorted(lands, key=lambda x: (not x.tapped, len(x.card.produces)))[:max(0, len(lands) - 7)]
    return picks


def _sacrifice_any(game, who, eff, item):
    source = item.source if item is not None and isinstance(item.source, Permanent) else None
    spec = eff.data["sac"]
    n = sum(1 for x in choose_sac_any(game, who, sac_candidates(game, who, spec, source))
            if x in who.battlefield and game.sacrifice(x) is not False)
    _counts(game, item)[id(who)] = n
    # "for each permanent sacrificed this way": one count, so only the one type the text named (CR 608.2c)
    nouns = ["permanent"] + (spec["types"] if len(spec["types"]) == 1 else [])
    note_this_way(item, "sacrificed", nouns, n)
    game.log(f"sacrifices {n} permanent(s)", who)
