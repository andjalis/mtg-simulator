"""Protection from a color (rule 702.16).

    Protection from black                       Flying, protection from red and from white
    Equipped creature gets +2/+2 and has protection from black and from red.
    Enchanted creature has protection from green.
    Target creature gains protection from blue until end of turn.
    Target creature you control gains protection from the color of your choice until end of turn.

The keyword itself is one of the five "protection from <color>" KEYWORDS; the rules (it can't be blocked,
targeted, dealt damage, enchanted or equipped by anything of that color) live in the engine around
``engine.state.protected_from``. "The color of your choice" is chosen when the effect resolves: the color of
the opposing spell or ability on the stack, else the most common color among the opponent's creatures, else
among the cards they have shown. Protection from multicolored and from artifacts are keywords too. Not parsed:
protection from creatures, everything, a creature type or a player, and "the chosen color" of an Aura.
"""
from __future__ import annotations

from collections import Counter

KINDS: set = set()
CHOICE = "protection_choice"
_COLOR = r"(white|blue|black|red|green)"
_NAMES = {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}
COLORS = tuple(_NAMES)


def _grant(target, keyword):
    from .cards import Effect
    return Effect("grant", target=target, data={"keyword": keyword})


EFFECT_PATTERNS = [
    (rf"target creature gains protection from {_COLOR} until end of turn",
     lambda m: _grant("creature", f"protection from {m[1]}")),
    (r"target creature(?: you control)? gains protection from the color of your choice until end of turn",
     lambda m: _grant("creature_mine", CHOICE)),
    (r"(?:it|that creature) gains protection from the color of your choice until end of turn",
     lambda m: _grant("prev", CHOICE)),
]


def choose_color(game, p, target) -> str:
    """The protection keyword p picks for target: against the threat on the stack, else the opponent's colors."""
    opp = game.opponent(p)
    for item in reversed(game.stack):
        card = item.card or (item.source.card if item.source is not None else None)
        if item.controller is opp and card is not None and card.colors:
            return f"protection from {_NAMES[min(card.colors, key=COLORS.index)]}"
    counts = Counter(c for x in opp.creatures for c in x.card.colors)
    if not counts:
        counts = Counter(c for zone in (opp.battlefield, opp.graveyard) for x in zone
                         for c in getattr(x, "card", x).colors)
    color = max(COLORS, key=lambda c: (counts[c], -COLORS.index(c))) if counts else "W"
    return f"protection from {_NAMES[color]}"
