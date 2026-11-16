"""Keyword counters picked from a list (#627):

    ~ enters with your choice of a deathtouch counter or a lifelink counter on it.               (Boot Nipper)
    ~ enters with your choice of two different counters on it from among menace, deathtouch, and lifelink. (Grimdancer)

``etb_named_counters = ("choice:A|B", 1)`` (or "choice2:A|B|C" for two different ones); Game.enter_battlefield asks
``pick`` which: the best keywords (by the grant ranking) the creature doesn't have yet. Every option must be a
keyword counter the engine knows. "Put your choice of a X or Y counter on it" is not read here: in the cards that
say it, "it" follows an effect that doesn't record its object (T-45 Power Armor's "untap equipped creature", The
Night of the Doctor's graveyard return), so the counter would land nowhere.
"""
from __future__ import annotations

import re

_KW_COUNTERS = ("flying", "first strike", "double strike", "deathtouch", "lifelink", "vigilance", "trample", "haste",
                "hexproof", "indestructible", "menace", "reach")
_KW = "|".join(_KW_COUNTERS)
_ENTERS = re.compile(rf"~ enters with your choice of an? ({_KW}) counter or an? ({_KW}) counter on it\.", re.I)
_TWO = re.compile(rf"~ enters with your choice of two different counters on it from among ((?:{_KW}), (?:{_KW}),? and "
                  rf"(?:{_KW}))\.", re.I)


def _options(text: str):
    opts = [o.strip().lower() for o in re.split(r",\s*(?:or\s+)?|\s+or\s+", text) if o.strip()]
    return opts if len(opts) >= 2 and len(set(opts)) == len(opts) and all(o in _KW_COUNTERS for o in opts) else None


def parse_line(line: str, st) -> bool:
    if st.extra.get("etb_named_counters"):
        return False
    m = _TWO.fullmatch(line.strip())
    if m:           # Grimdancer: two different ones from three
        opts = _options(m[1].replace(" and ", " or "))
        if opts is None:
            return False
        st.extra["etb_named_counters"] = ("choice2:" + "|".join(opts), 1)
        return True
    m = _ENTERS.fullmatch(line.strip())
    if m is None:
        return False
    opts = _options(f"{m[1]} or {m[2]}")
    if opts is None:
        return False
    st.extra["etb_named_counters"] = ("choice:" + "|".join(opts), 1)
    return True


def pick(perm, name: str) -> list:
    """The counter kinds an entering permanent gets: [name], or for "choice:A|B" the best keyword it doesn't already
    have, for "choice2:A|B|C" the best two different ones."""
    if not name.startswith(("choice:", "choice2:")):
        return [name]
    from .engine.kinds.stats import _KEYWORD_RANK
    head, _, rest = name.partition(":")
    ranked = sorted(rest.split("|"), key=lambda k: (perm.has(k), _KEYWORD_RANK.get(k, 20)))
    return ranked[:2 if head == "choice2" else 1]
