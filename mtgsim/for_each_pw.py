""""For each ..." wordings on planeswalkers (#839), rewritten to forms the effect templates read:

    For each opponent, return up to one target nonland permanent that player controls to its owner's hand.  (Venser)
      -> Return up to one target nonland permanent an opponent controls to its owner's hand.
    For each creature card in your graveyard, put a +1/+1 counter on each creature you control.  (Vraska, Regal Gorgon)
      -> Put X +1/+1 counters on each creature you control, where X is the number of creature cards in your graveyard.
    Until end of turn, creatures you control get +1/+1 for each Forest you control and gain trample.  (Nissa, Ascended Animist)
      -> Creatures you control get +1/+1 for each Forest you control until end of turn. Creatures you control gain
         trample until end of turn.
    ~ deals 2 damage to target tapped creature for each card you've drawn this turn.  (Niko Aris)
      -> ~ deals X damage to target tapped creature, where X is twice the number of cards you've drawn this turn.

The game is two-player, so "for each opponent / other player, ... that player controls" is the one opponent.
"""
from __future__ import annotations

import re

_TIMES = {1: "", 2: "twice "}


def _niko(m):
    n = int(m[1])
    if n not in _TIMES:
        return m[0]
    return f"~ deals X damage to target {m[2]}, where X is {_TIMES[n]}the number of cards you've drawn this turn"


_CHECKING: list = []


def _opponent(m):
    """Only when no template reads the sentence as written (Grasp of Fate's own template keeps "up to one")."""
    if _CHECKING:
        return m[0]
    from .cards.parse import _parse_effects
    sentence = m.string[m.start():].split(". ")[0].rstrip(".") + "."
    _CHECKING.append(1)
    try:
        effects, bad = _parse_effects(sentence[0].upper() + sentence[1:])
    finally:
        _CHECKING.pop()
    if effects and not bad:
        return m[0]
    return f"{m[1]} up to one target {m[2]} an opponent controls"


SUBS = [
    (re.compile(r"\bfor each (?:opponent|other player), (exile|return|destroy|tap) up to one target ([\w ,-]+?) "
                r"that player controls\b", re.I), _opponent),
    (re.compile(r"\bfor each (creature|land|artifact|instant|sorcery) card in your graveyard, put a \+1/\+1 counter on "
                r"each creature you control\b", re.I),
     lambda m: f"put X +1/+1 counters on each creature you control, where X is the number of {m[1].lower()} cards in "
               f"your graveyard"),
    (re.compile(r"\buntil end of turn, creatures you control get \+(\d+)/\+(\d+) for each (\w+) you control and gain "
                r"(flying|trample|haste|vigilance|lifelink|menace|deathtouch)\b", re.I),
     lambda m: f"creatures you control get +{m[1]}/+{m[2]} for each {m[3]} you control until end of turn. "
               f"creatures you control gain {m[4]} until end of turn"),
    (re.compile(r"~ deals (\d+) damage to target ([\w ]+?) for each card you've drawn this turn", re.I), _niko),
]
