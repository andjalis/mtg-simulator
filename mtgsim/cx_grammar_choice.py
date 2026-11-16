"""Grammar verbs: a keyword picked from a list (#627).

    Target creature gets +1/+1 and gains your choice of deathtouch or lifelink until end of turn.   (Alchemist's Gift)
    {G}: ~ gains your choice of reach, trample, or haste until end of turn.                        (Shifting Ceratops)
    Target creature loses your choice of flying, first strike, or trample until end of turn.       (Walking Sponge)

"gains your choice of A, B, or C" is one ``grant`` whose keyword is "choice:A|B|C": on resolution the controller
picks one for that creature (engine/kinds/stats.grant: the best keyword it doesn't have yet). "loses your choice
of ..." is one ``cx_lose_kw`` with the same list: the opponent's creature loses the best one it has. Every option
must be a keyword the engine knows, or the sentence stays ignored. This module sorts before cx_grammar_keywords,
so its parsers are tried first; "gains flying" without "your choice of" falls through to that module.
"""
from __future__ import annotations

import re

from .cx_grammar import Part, keyword_list, verb


def _options(text: str):
    """["deathtouch", "lifelink"] for "deathtouch or lifelink" / "flying, vigilance, deathtouch, or haste"."""
    parts = [p.strip() for p in re.split(r",\s*(?:or\s+)?|\s+or\s+", text.strip()) if p.strip()]
    if len(parts) < 2:
        return None
    out = []
    for p in parts:
        kws = keyword_list(p)
        if not kws or len(kws) != 1:
            return None
        out.append(kws[0])
    return out if len(set(out)) == len(out) else None


@verb(r"gains? your choice of (.+)", heads=("gain", "gains"))
def gains_choice(m, clause):
    options = _options(m[1])
    if options is None or clause.duration != "eot":
        return None
    return [Part("grant", data={"keyword": "choice:" + "|".join(options)})]


@verb(r"loses? your choice of (.+)", heads=("lose", "loses"))
def loses_choice(m, clause):
    options = _options(m[1])
    if options is None or clause.duration != "eot":
        return None
    return [Part("cx_lose_kw", data={"keyword": "choice:" + "|".join(options), "side": "theirs"})]


@verb(r"gains? protection from the color of your choice", heads=("gain", "gains"),
      subjects=("permanent", "group", "host"))
def gains_protection_choice(m, clause):
    """"... gains protection from the color of your choice until end of turn": the existing protection choice
    (protection.choose_color: the colour of the threat on the stack, else the opponent's main colour), one per
    resolution; every member of a group gets the same colour since the pick depends on the game, not the member."""
    if clause.duration != "eot":
        return None
    from .protection import CHOICE
    return [Part("grant", data={"keyword": CHOICE})]


# "Choose a color. Creatures you control gain protection from the chosen color until end of turn." is the same one
# choice as "... gain protection from the color of your choice ..." (Akroma's Blessing, Brave the Elements). Only
# subjects of your own permanents: for "all creatures" the AI's pick (the opponent's colour) would protect their
# creatures too, which is not what the card is cast for.
SUBS = [
    (re.compile(r"choose a color\. ((?:[^.]*?you control|up to \w+ target [^.]*?|x target [^.]*?|target [^.]*?) gains?) "
                r"protection from the chosen color until end of turn\.", re.I),
     lambda m: f"{m[1]} protection from the color of your choice until end of turn."),
]
