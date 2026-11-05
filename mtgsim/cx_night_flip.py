"""Champions-of-Kamigawa flip cards: "you may flip it" (ki counter creatures).

Read as an optional ``flip_self``; the handler (engine/kinds/cx_night_flip.py) turns the source over through the
double-faced transform machinery, since the second face of a flip card is parsed as the card's back."""
from __future__ import annotations


def _flip(m):
    from .cards.model import Effect
    return [Effect("pay_gate", data={"gate": ("may", "")}), Effect("flip_self")]


EFFECT_PATTERNS = [(r"you may flip (?:it|~)", _flip)]
