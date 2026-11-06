"""Small one-sentence effects from the night census.

* "Each player may discard their hand and draw seven cards." (Raphael's Technique, Ruin Grinder, Variable Chaser) is
  the existing ``wheel_all``. The "may" is always taken: a simplification, since an AI holding a strong hand might
  decline."""
from __future__ import annotations


def _wheel_seven(m):
    from .cards.model import Effect
    return Effect("wheel_all", 7)


EFFECT_PATTERNS = [
    (r"each player may discard their hand and draw seven cards", _wheel_seven),
]


def damage_floor(game, player, amount: int) -> int:
    """Ali from Cairo: damage that would reduce your life total to less than 1 reduces it to 1 instead."""
    from .residual_templates import sources
    if player.life >= 1 and any(x.controller is player for x in sources(game, "life_floor")):
        return min(amount, player.life - 1)
    return amount
