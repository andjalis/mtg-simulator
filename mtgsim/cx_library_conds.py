"""Conditions on a library or an exact hand size (#629), registered with cx_condlib's rule table:

    Then if your library has no cards in it, you win the game.                      (Jace, Wielder of Mysteries)
    ... if each player has an empty library, sacrifice ~ and you win the game.       (Barren Glory's neighbours)
    ... if you have exactly thirteen cards in your hand, you win the game.           (Triskaidekaphile)
    ... if you have 200 or more cards in your library, you win the game.             (Battle of Wits)

They are ``res`` codes with the new resource "library" (the library's size, read in cx_condlib.check).
"""
from __future__ import annotations

from .cx_condlib import _code, _who, rule

_BIG = r"(?P<n>\d+|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty)"
_WORDS = {"eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
          "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}


def _num(word: str) -> int:
    return int(word) if word.isdigit() else _WORDS[word.lower()]


@rule(r"(?P<who>you|that player|target player|an opponent) (?:has|have) no cards in (?:your|their|his or her) library"
      r"|(?P<who2>your|that player's|target player's) library has no cards in it")
def _empty_library(m):
    who = m["who"] or {"your": "you", "that player's": "that player", "target player's": "target player"}[m["who2"].lower()]
    return _code("res", _who(who), "library", "==", 0)


@rule(r"each player has an empty library|each player's library has no cards in it")
def _all_empty(m):
    return _code("and", _code("res", "you", "library", "==", 0), _code("res", "opp", "library", "==", 0))


@rule(rf"you have exactly {_BIG} cards in your hand")
def _exact_hand(m):
    return _code("res", "you", "hand", "==", _num(m["n"]))


@rule(rf"you have {_BIG} or more cards in your library")
def _library_at_least(m):
    return _code("res", "you", "library", ">=", _num(m["n"]))
