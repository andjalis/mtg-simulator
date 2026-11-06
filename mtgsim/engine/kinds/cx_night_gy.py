"""Graveyard picks of "up to N target cards": exile from the opponent's graveyard, shuffle your own into the library."""
from . import kind


@kind("exile_gy_n")
def exile_gy_n(game, eff, opp, **_):
    """Decompose, Rapid Decay, Scarab Feast: exile up to N cards from one graveyard, the most dangerous first
    (creatures, then higher mana value)."""
    picks = sorted(opp.graveyard, key=lambda c: (c.is_creature, c.cmc), reverse=True)[:eff.amount]
    for card in picks:
        game.move_card(card, opp.graveyard, opp.exile, reason="exile_graveyard")
    if picks:
        game.log(f"exiles {len(picks)} card(s) from {opp}'s graveyard", game.opponent(opp))


@kind("shuffle_gy_n")
def shuffle_gy_n(game, p, eff, **_):
    """Dwell on the Past, Rite of Renewal: shuffle up to N cards from your graveyard into your library. The AI
    recycles the cheapest cards first, which keeps its better graveyard cards for recursion."""
    picks = sorted(p.graveyard, key=lambda c: (c.cmc, c.is_creature))[:eff.amount]
    for card in picks:
        p.graveyard.remove(card)
        p.library.append(card)
    if picks:
        p.library.shuffle(game.rng)
        game.log(f"shuffles {len(picks)} card(s) from the graveyard into the library", p)


@kind("hand_cycle")
def hand_cycle(game, p, eff, **_):
    """Whirlpool Drake, Arjun: put the whole hand back into the library (shuffled in, or on the bottom), then draw as
    many cards."""
    cards = list(p.hand)
    n = len(cards)
    if not n:
        return
    for card in cards:
        p.hand.remove(card)
        if eff.data.get("bottom"):
            p.library.insert(0, card)
        else:
            p.library.append(card)
    if not eff.data.get("bottom"):
        p.library.shuffle(game.rng)
    game.draw(p, n)
    game.log(f"puts {n} card(s) from hand into the library and draws {n}", p)


@kind("edict_each_nontoken")
def edict_each_nontoken(game, p, opp, **_):
    """Accursed Marauder: each player sacrifices a nontoken creature of their choice (their cheapest)."""
    from ..policy import perm_value
    from ... import counter_mechanics
    for pl in (p, opp):
        victims = sorted((c for c in pl.creatures if not c.card.is_token), key=perm_value)[:1]
        sources = counter_mechanics.death_sources(game)
        for v in victims:
            game.sacrifice(v, counter_sources=sources)


@kind("opp_hand_to_top")
def opp_hand_to_top(game, p, opp, **_):
    """Chimney Imp: the opponent puts a card from their hand on top of their library: their least useful one (an
    extra land if they hold any, else the cheapest card)."""
    if not opp.hand:
        return
    lands = [c for c in opp.hand if c.is_land]
    card = lands[-1] if lands else min(opp.hand, key=lambda c: c.cmc)
    opp.hand.remove(card)
    opp.library.append(card)
    game.log("puts a card from hand on top of the library", opp)


@kind("edict_attacking")
def edict_attacking(game, p, target, opp, **_):
    """Entrapment Maneuver, Wing Shards: the player sacrifices an attacking creature of their choice (their cheapest)."""
    from ..policy import perm_value
    from ..state import Permanent
    from ... import counter_mechanics
    victim_owner = target if target is not None and not isinstance(target, Permanent) else opp
    mine = [c for c in game.attackers if c.controller is victim_owner]
    for v in sorted(mine, key=perm_value)[:1]:
        game.sacrifice(v, counter_sources=counter_mechanics.death_sources(game))


@kind("sac_unless_discard_kind")
def sac_unless_discard_kind(game, p, eff, item, **_):
    """Fallow Wurm ("a land card") and Balduvian Horde ("a card at random"): keep the source by paying the discard when
    able, else sacrifice it."""
    from ..state import Permanent
    src = item.source if item is not None else None
    if not isinstance(src, Permanent) or src not in p.battlefield:
        return
    if eff.data["mode"] == "land":
        lands = [c for c in p.hand if c.is_land]
        card = lands[0] if lands else None
    else:
        card = game.rng.choice(list(p.hand)) if p.hand else None
    if card is None:
        game.sacrifice(src)
    else:
        game.discard_card(p, card)
