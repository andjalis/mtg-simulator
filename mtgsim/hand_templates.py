"""Hand-disruption wordings the earlier templates miss: reveal a hand, choose a described card
(and optionally a mana-value bound), then discard it (Inquisition of Kozilek, Coercion), exile it
for good (Castigate, Appetite for Brains, Psychic Theft, Nimble Larcenist) or tuck it into the
library Nth from the top (Lost Hours).

The discard destination reuses the TARGETDISCARD sentinel from cards/clauses.py; EXILEHAND2 and
TUCKCHOICE are new sentinels. The filter grammar ("artifact, instant, or sorcery", "green or
white creature", "card with mana value 4 or greater") is matched by ``_hand_matches`` in
engine/kinds/cards.py.
"""
from __future__ import annotations

import re

_FILTER = r"([\w, -]+?) card"
_MV = r"(?: with mana value (\d+) or (less|greater))?"


def _discard(m):
    mv = (m[2], m[3]) if m[2] else None
    return "TARGETDISCARD2 %s%s." % (m[1] or "card", "" if not mv else f" {mv[0]} {mv[1]}")


def _exile(m):
    what = (m[1] or "card").strip()
    n, direction = (m[2], m[3]) if m.re.groups >= 3 else (None, None)
    return "EXILEHAND2 %s%s." % (what, "" if not n else f" {n} {direction}")


def _mv(m):
    return {"mv": (int(m[2]), m[3])} if m[2] else {}


def _e(kind_, **kw):
    from .cards import Effect
    return Effect(kind_, 1, **kw)


SUBS = [
    # "… reveals their hand. You choose a <filter> card from it with mana value N or less /
    # greater. That player discards that card." (Inquisition of Kozilek)
    (re.compile(r"(?:target|that) (?:player|opponent) reveals their hand\. you choose an? "
                + _FILTER + r" from it" + _MV + r"\. that player discards that card\.?", re.I),
     _discard),
    # "… reveals their hand. You choose a card from it. That player discards that card."
    # (Coercion: no filter words at all.)
    (re.compile(r"(?:target|that) (?:player|opponent) reveals their hand\. you choose a card "
                r"from it\. that player discards that card\.?", re.I),
     lambda m: "TARGETDISCARD."),
    # "… reveals their hand. You choose a <filter> card from it [with mana value N or …] and
    # exile that card." (Castigate, Psychic Theft, Appetite for Brains, Nimble Larcenist)
    (re.compile(r"(?:target|that) (?:player|opponent) reveals their hand\. you choose "
                r"(?:an? " + _FILTER + r"|a card) from it" + _MV + r" and exile that card\.?",
                re.I),
     _exile),
    # "… reveals their hand. You choose a <filter> card from it. Exile that card." — only the
    # permanent-exile shapes; the until-~-leaves O-rings stay with the HANDEXILE rewrite.
    (re.compile(r"(?:target|that) (?:player|opponent) reveals their hand\. you choose an? "
                + _FILTER + r" from it\. exile that card\.?(?! ?until)", re.I),
     _exile),
    # "… reveals their hand. You choose a <filter> card from it. That player puts that card
    # into their library Nth from the top." (Lost Hours)
    (re.compile(r"(?:target|that) (?:player|opponent) reveals their hand\. you choose an? "
                + _FILTER + r" from it\. that player puts that card into their library "
                r"(second|third|fourth|fifth) from the top\.?", re.I),
     lambda m: "TUCKCHOICE %s %d." % (m[1], {"second": 2, "third": 3, "fourth": 4, "fifth": 5}[m[2]])),
]

EFFECT_PATTERNS = [
    (r"TARGETDISCARD2 (card|[\w, -]+?)(?: (\d+) (less|greater))?",
     lambda m: _e("discard_choice", target="player", filter="" if m[1] == "card" else m[1],
                  data=_mv(m))),
    (r"EXILEHAND2 (card|[\w, -]+?)(?: (\d+) (less|greater))?",
     lambda m: _e("exile_hand_perm", target="player", filter="" if m[1] == "card" else m[1],
                  data=_mv(m))),
    (r"TUCKCHOICE ([\w, -]+?) (\d+)",
     lambda m: _e("tuck_choice", target="player", filter=m[1], data={"depth": int(m[2])})),
    # "Put a/two/N card(s) from your hand on the top/bottom of your library [in any order]"
    # (Brainstorm's rider, Amass the Components, Cavalier of Gales).
    (r"put (a|one|two|three|four|five|six|seven|\d+) cards? from your hand on "
     r"(?:the )?(top|bottom) of your library(?: in any order)?",
     lambda m: _lib(m)),
]


def _lib(m):
    from .cards import Effect, _num
    return Effect("hand_to_library", _num(m[1]), data={"bottom": m[2] == "bottom"})
