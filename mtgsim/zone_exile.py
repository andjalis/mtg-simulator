"""Exile a whole zone (#641): graveyards and hands as the object of a mass exile.

    Exile all cards from all graveyards.                       (Lantern of the Lost, with a rider)
    Exile all creature cards from all graveyards.
    Exile all cards from your graveyard.  /  from each opponent's graveyard.
    Exile target player's graveyard.  /  hand.
    Each player exiles all cards from their hand.             /  Exile all cards from each player's hand.

The card filter is a card description (state.card_matches), so a restriction it can't read leaves the sentence ignored.
The effect is the existing ``graveyard_exile_all`` kind with data {who, zone, desc}.
"""
from __future__ import annotations

import re

_WHOSE = {"all": "each", "each player's": "each", "your": "you", "each opponent's": "opponents",
          "target player's": "target", "target opponent's": "target"}


def _effect(whose, zone, kind=""):
    from .cards.model import NO_MATCH, Effect
    who = _WHOSE.get(whose.lower())
    zone = zone.rstrip("s") if zone.startswith("graveyard") else zone
    if who is None or (whose.lower() == "all" and zone != "graveyard"):
        return NO_MATCH
    kind = kind.strip()
    data = {"who": who, "zone": zone}
    if kind not in ("", "card", "cards"):
        if not kind.endswith(" cards"):
            return NO_MATCH
        from .engine.state import _TYPE_WORDS
        words = re.split(r" or ", kind[:-6])
        if not all(re.sub(r"^non", "", w) in _TYPE_WORDS | {"legendary", "historic"} for w in words):
            return NO_MATCH
        data["desc"] = kind[:-1]
    return Effect("graveyard_exile_all", target="player" if who == "target" else "none", data=data)


EFFECT_PATTERNS = [
    (r"exile all ((?:[a-z-]+(?: or [a-z-]+)? )?cards?) from (all|your|each opponent's|each player's|target player's) "
     r"(graveyards?|hand)", lambda m: _effect(m[2], m[3], m[1])),
    (r"exile (target player's|target opponent's|your|each opponent's) (graveyard|hand)", lambda m: _effect(m[1], m[2])),
    (r"each player exiles all cards from their (graveyard|hand)", lambda m: _effect("each player's", m[1])),
]
