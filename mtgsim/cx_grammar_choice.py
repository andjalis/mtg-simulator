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
