"""Return the creature that just died: "return that card to the battlefield under your control [with a +1/+1 counter on it]."

Used by "When enchanted creature dies", "whenever a creature dealt damage by ~ this turn dies" and similar triggers whose
context is the dead permanent. Read as ``return_dead``; the handler is in engine/kinds/cx_night_dead.py."""
from __future__ import annotations


def _dead(m):
    from .cards.model import Effect
    return [Effect("return_dead", data={"counter": bool(m[1])})]


EFFECT_PATTERNS = [(r"return that card to the battlefield under your control( with a \+1/\+1 counter on it)?", _dead)]
