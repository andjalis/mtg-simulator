"""End the turn (Time Stop, Glorious End, Ultima): "End the turn."

Read as ``end_turn``; the handler (engine/kinds/cx_night_endturn.py) exiles every other object on the stack, locks both
players out of further spells and abilities this turn and sets ``game.turn_ended``, which makes the remaining main
phases, combat and end step of the turn do nothing so play goes straight to cleanup."""
from __future__ import annotations

import re

# Final Fortune, Last Chance, Warrior's Oath: the extra turn and the loss at its end step are one effect. The loss is
# checked once that extra turn has been played out (engine/turns.py ``play``), just after its end step.
SUBS = [
    (re.compile(r"take an extra turn after this one\. at the beginning of that turn's end step, you lose the game\.", re.I),
     lambda m: "DOOMED EXTRA TURN."),
]


def _end(m):
    from .cards.model import Effect
    return [Effect("end_turn")]


def _doomed(m):
    from .cards.model import Effect
    return [Effect("extra_turn", data={"doomed": True})]


EFFECT_PATTERNS = [(r"end the turn", _end), (r"doomed extra turn", _doomed)]
