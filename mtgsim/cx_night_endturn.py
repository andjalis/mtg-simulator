"""End the turn (Time Stop, Glorious End, Ultima): "End the turn."

Read as ``end_turn``; the handler (engine/kinds/cx_night_endturn.py) exiles every other object on the stack, locks both
players out of further spells and abilities this turn and sets ``game.turn_ended``, which makes the remaining main
phases, combat and end step of the turn do nothing so play goes straight to cleanup."""
from __future__ import annotations


def _end(m):
    from .cards.model import Effect
    return [Effect("end_turn")]


EFFECT_PATTERNS = [(r"end the turn", _end)]
