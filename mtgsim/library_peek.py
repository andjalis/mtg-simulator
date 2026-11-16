"""Looking at the top cards of a target player's library (#346).

    Look at the top three cards of target player's library, then put them back in any order.   (Architects of Will)
    You may have that player shuffle.                                                           (Portent)
    Look at the top five cards of target player's library.                                      (Visions)
    That player looks at the top three cards of your library, then puts them back in any order. (Tahngarth's Glare)
    Look at the top two cards of target player's library. Put one of them into their graveyard. (Wu Spy)
    Look at the top three cards of target player's library. Put one back and the rest into that player's graveyard.
    Look at the top five cards of your library, put one of them into your hand, and exile the rest.   (Browse)

The engine kinds are reorder_top (cards.py, now with a target player), peek_library, may_shuffle_prev and peek_mill
(engine/kinds/library_peek.py), and dig_gy with rest "exile". Looking is not revealing: nothing here shows the
cards to anyone else, and the AI orders the cards only by what it just looked at.
"""
from __future__ import annotations

import re

_N = r"(two|three|four|five|six|seven|\d+)"
_K = r"(one|two|three|\d+)"
_WHO = r"target (player|opponent)'s library"


def _num(word):
    from .cards.model import _num as num
    return num(word)


def _e(kind, amount=0, amount2=0, **kw):
    from .cards import Effect
    return Effect(kind, amount, amount2, **kw)


def _reorder(m):
    opp = m[2].lower() == "opponent"
    return _e("reorder_top", _num(m[1]), target="player", filter="opp" if opp else "",
              data={"side": "theirs" if opp else "mine"})


def _peek_mill(n, who, keep=None, mill=None):
    n = _num(n)
    keep = n - _num(mill) if mill is not None else _num(keep)
    if not 0 <= keep < n:
        return None
    return _e("peek_mill", n, keep, target="player", filter="opp" if who == "opponent" else "", data={"side": "theirs"})


EFFECT_PATTERNS = [
    (r"look at the top " + _N + r" cards of " + _WHO + r",? then put them back in any order", _reorder),
    (r"(?:you may )?(?:then )?have that player shuffle(?: that library| their library)?",
     lambda m: _e("may_shuffle_prev", target="prev")),
    (r"that player looks at the top " + _N + r" cards of your library,? then puts them back in any order",
     lambda m: _e("reorder_top", _num(m[1]), data={"chooser": "opponent"})),
    (r"PEEKMILL (player|opponent) " + _N + r" keep " + _K, lambda m: _peek_mill(m[2], m[1].lower(), keep=m[3])),
    (r"PEEKMILL (player|opponent) " + _N + r" mill " + _K, lambda m: _peek_mill(m[2], m[1].lower(), mill=m[3])),
    # Orcish Spy, Visions: only a look (the engine keeps no hidden-information model, so nothing changes; a
    # following "you may have that player shuffle" decides on what was seen)
    (r"look at the top " + _N + r" cards of " + _WHO,
     lambda m: _e("peek_library", _num(m[1]), target="player", filter="opp" if m[2].lower() == "opponent" else "",
                  data={"side": "theirs"})),
    (r"look at the top " + _N + r" cards of your library,? (?:then )?put (one|two|three|\d+) of them into your hand,? "
     r"and exile the rest", lambda m: _e("dig_gy", _num(m[1]), _num(m[2]), data={"rest": "exile"})),
]

_THEIR = r"(?:that player's|their)"
SUBS = [
    # Dimir Charm: "Put one back and the rest into that player's graveyard"
    (re.compile(r"look at the top " + _N + r" cards of target (player|opponent)'s library\. put (one|two) back and the "
                r"rest into " + _THEIR + r" graveyard\.", re.I), lambda m: f"PEEKMILL {m[2]} {m[1]} keep {m[3]}."),
    # Wu Spy: "Put one of them into their graveyard" (the other stays on top); Cruel Fate: "... and the rest on top
    # of their library in any order"
    (re.compile(r"look at the top " + _N + r" cards of target (player|opponent)'s library\. put (one|two) of (?:them|"
                r"those cards) into " + _THEIR + r" graveyard(?: and the rest on top of " + _THEIR + r" library in any "
                r"order)?\.", re.I), lambda m: f"PEEKMILL {m[2]} {m[1]} mill {m[3]}."),
]
