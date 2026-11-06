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
