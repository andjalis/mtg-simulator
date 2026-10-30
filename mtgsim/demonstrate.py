"""Demonstrate (Strixhaven): "When you cast this spell, you may copy it. If you do, choose an
opponent to also copy it."

The keyword line (its reminder text rides in parentheses the face parser strips) becomes a
cast-self trigger, exactly like ripple. Resolving it puts two copies on the stack: yours and
the chosen opponent's (the two-player game has one opponent), each with fresh targets where
better, through the copies foundation. The granting statics ("Creature spells you cast have
demonstrate") are not built.

Recorded simplification: the copy is always made — the AI never declines, and cannot weigh
the opponent's copy against its own.
"""
from __future__ import annotations


def _e(kind, amount=1, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


EFFECT_PATTERNS = [
    (r"demonstrate", lambda m: _e("demonstrate")),
]

TRIGGERS = [
    (r"(Demonstrate)", ("cast_self",)),
]


def demonstrate(game, p, eff, item):
    """Your copy of the spell, then the opponent's."""
    from . import copies
    from .engine.state import StackItem
    spell = item.context if item is not None else None
    if not isinstance(spell, StackItem):
        return
    copies.copy_spell(game, p, spell)
    copies.copy_spell(game, game.opponent(p), spell)
