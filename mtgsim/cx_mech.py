"""Named mechanics (cx_mech*): rare keywords that need their own cast option.

    Splice onto Arcane {1}{W}   (as you cast an Arcane spell, reveal this card from your hand and pay its splice
                                 cost: add this card's effects to that spell; this card stays in your hand)

``parse_line`` reads the keyword into ``AltCost("splice", cost)`` (never a cast option of the card itself: a
spliceable card is only cast normally). ``variants`` offers, for each Arcane spell in hand, one variant per other
spliceable card in hand: the Arcane spell's cost plus the splice cost, its effects followed by the spliced card's.
"""
from __future__ import annotations

import re


def parse_line(line: str, st) -> bool:
    from .cards.model import AltCost, parse_mana_cost
    m = re.fullmatch(r"Splice onto Arcane ((?:\{[^}]+\})+)(?: \(.*\))?", line)
    if m:
        st.alt_costs.append(AltCost("splice", parse_mana_cost(m[1])))
        return True
    return False


def variants(game, p, card) -> list:
    """Splice variants of the hand card (an Arcane spell) with each other spliceable card in hand."""
    from .cards import AltCost, add_mana
    if "Arcane" not in card.subtypes or card.is_permanent:
        return []
    out = []
    for other in p.hand:
        splice = next((a for a in other.alt_costs if a.kind == "splice"), None)
        if other is card or splice is None or not other.spell_effects:
            continue
        alt = AltCost(f"splice_{getattr(other, 'physical_id', id(other))}", add_mana(card.mana_cost, splice.cost),
                      extra=list(other.spell_effects))
        v = game._variant(card, alt.kind, alt)
        v.spliced = other
        out.append(v)
    return out
