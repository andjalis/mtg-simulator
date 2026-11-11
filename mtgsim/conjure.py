"""Conjure templates (Alchemy): "Conjure a card named X into your hand / onto the battlefield / ...".

A conjured card is a new card from outside the game, looked up by name in the offline card database
when the effect resolves (a card the database doesn't know is skipped and logged). Supported: one
named card (or N copies) into your hand, graveyard, library (then shuffle, or at random among the top
N cards) or onto the battlefield (tapped or not). Conjuring a duplicate of another card, a spellbook
choice, or several different names stays unmatched. Joined at the end of ``cards/__init__.py``.
"""
from __future__ import annotations

import re

_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20}
_COUNT = "|".join(_WORDS)
_NAME = r"([A-Z][^.,]*?(?:, (?:the |a |an )?[A-Z][^.,]*?)?)"      # "Fblthp, the Lost" has one comma


def _count(word):
    return _WORDS.get(word.lower(), int(word) if word.isdigit() else 1)


def _conjure(m, dest, **more):
    from .cards import Effect, NO_MATCH
    if re.search(r" (?:and|or) (?:an? |one |two |three |four |five |\d+ |X )?cards? named |~|\bnamed\b", m[2]):
        return NO_MATCH                 # "a card named X and a card named Y": two names, not one
    data = {"card_name": m[2], "dest": dest, **more}
    return Effect("conjure", _count(m[1]), data=data)


def _top(m):
    return _conjure(m, "library", top=_count(m[3]))


EFFECT_PATTERNS = [
    (rf"conjure (a|an|one|two|three|four|five|\d+) cards? named {_NAME} into your hand",
     lambda m: _conjure(m, "hand")),
    (rf"conjure (a|an|one|two|three|four|five|\d+) cards? named {_NAME} into your graveyard",
     lambda m: _conjure(m, "graveyard")),
    (rf"conjure (a|an|one|two|three|four|five|\d+) cards? named {_NAME} onto the battlefield( tapped)?"
     r"(?:, then put (a|one|two|three|\d+) \+1/\+1 counters? on it)?",
     lambda m: _conjure(m, "battlefield", tapped=bool(m[3]), **({"counters": _count(m[4])} if m[4] else {}))),
    (rf"conjure (a|an|one|two|three|four|five|\d+) cards? named {_NAME} into your library, then shuffle",
     lambda m: _conjure(m, "library", shuffle=True)),
    (rf"conjure (a|an|one|two|three|four|five|\d+) cards? named {_NAME} into the top ({_COUNT}) cards of your library at random",
     _top),
]
