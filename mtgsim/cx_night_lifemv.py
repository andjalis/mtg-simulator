"""Healing Technique, Razor Hippogriff: "You gain life equal to that card's mana value."

Read as ``gain_card_mv``: the card the earlier part of the same ability returned from a graveyard (Healing Technique, Razor Hippogriff) or revealed
from the top of the library (Sifter Wurm). Other "that card" sources keep their unsupported line."""
from __future__ import annotations


def _gain(m):
    from .cards.model import Effect
    return [Effect("gain_card_mv")]


EFFECT_PATTERNS = [(r"you gain life equal to that card's mana value", _gain)]
