"""Optional looting riders: "you may draw a card. If you do, discard a card." (Marauding Looter, Shipwreck Looter,
Force Away).

Drawing has no drawback, so the optional draw is always taken. The pair is folded into one ``loot`` effect (draw, then
discard) rather than two, so a condition on the sentence ("Ferocious - If you control a creature with power 4 or
greater, ...") covers the discard as well as the draw."""
from __future__ import annotations

import re

# Only the form with an "if ..." clause in front: the plain "you may draw a card. If you do, discard a card." already
# works through the pay gate (Smuggler's Copter, Murder of Crows) and is left alone.
SUBS = [
    (re.compile(r"(if [^.]*?, )you may draw a card\. if you do, discard a card\.", re.I),
     lambda m: f"{m[1]}LOOT 1."),
]


def _loot(m):
    from .cards.model import Effect
    return Effect("loot", 1)


EFFECT_PATTERNS = [(r"loot 1", _loot)]
