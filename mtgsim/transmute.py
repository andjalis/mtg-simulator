"""Transmute {1}{B}{B}   ({1}{B}{B}, Discard this card: search your library for a card with the same mana value,
reveal it, put it into your hand, then shuffle. Sorcery speed, from your hand.)

``parse_line`` reads the keyword into an AltCost("transmute"). It is a main-phase action, not a spell: the AI
transmutes in its second main phase (``actions``) with the mana left after its other plays, taking the best card
(engine.choose_tutor) among those with the discarded card's mana value.
"""
from __future__ import annotations

import re


def parse_line(line: str, st) -> bool:
    from .cards.model import AltCost, parse_mana_cost
    m = re.fullmatch(r"Transmute ((?:\{[^}]+\})+)", line)
    if not m:
        return False
    st.alt_costs.append(AltCost("transmute", parse_mana_cost(m[1])))
    return True


def transmute(game, p, card) -> bool:
    """Pay the transmute cost, discard the card and fetch another with the same mana value."""
    from .engine import choose_tutor
    alt = next((a for a in card.alt_costs if a.kind == "transmute"), None)
    if card not in p.hand or alt is None or game.stack or game.pay(p, alt.cost) is None:
        return False
    game.discard_card(p, card)
    game.log(f"transmutes {card.name}", p)
    found = [c for c in p.library if c.cmc == card.cmc]
    if found:
        pick = choose_tutor(game, p, found)
        p.library.remove(pick)
        p.hand.append(pick)
        game.log(f"searches for {pick.name}", p)
    p.library.shuffle(game.rng)
    game.library_searched(p)
    return True


def actions(game, p):
    """Transmute each card left in hand once the turn's plays are done, if a card of that mana value remains."""
    for card in [c for c in p.hand if any(a.kind == "transmute" for a in c.alt_costs)]:
        alt = next(a for a in card.alt_costs if a.kind == "transmute")
        if not any(c.cmc == card.cmc and c.name != card.name for c in p.library):
            continue
        reserve = min((c.cmc for c in p.hand if c is not card and not c.is_land and c.instant_speed), default=0)
        if game.can_pay(p, {**alt.cost, "generic": alt.cost.get("generic", 0) + reserve}):
            transmute(game, p, card)
