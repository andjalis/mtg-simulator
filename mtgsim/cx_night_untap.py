"""Untapping a counted number of lands: "Untap up to three lands", "Untap two target lands".

Played with the existing ``untap_lands`` handler, which untaps the controller's best tapped mana producers."""
from __future__ import annotations

_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_N = "|".join(_NUMBERS)


def _untap_lands(m):
    from .cards.model import Effect
    return [Effect("untap_lands", _NUMBERS[m["n"].lower()])]


EFFECT_PATTERNS = [
    (rf"untap (?:up to )?(?P<n>{_N}) (?:target )?lands(?: you control)?", _untap_lands),
]
