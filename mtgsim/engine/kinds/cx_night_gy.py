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
