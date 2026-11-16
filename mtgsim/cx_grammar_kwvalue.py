"""#633: keywords with a number, granted like plain keywords: "have ward {2}", "has toxic 1", "gains ward {1}".

    Goblins and Orcs you control have ward {2}.                      (Saruman, the White Hand)
    Each other Human you control gets +1/+0 and has ward {1}.         (Coppercoat Vanguard)
    Enchanted creature has toxic 2.                                   (Necrogen Communion)

A valued keyword travels through every keyword-grant path as the string ``"ward:2"`` / ``"toxic:1"`` (static group
grants, an Equipment's or Aura's keywords, a temporary grant). ``kw_values.amounts`` collects the ones a permanent
really has (``Permanent.has`` decides, so conditions, layers and "loses all abilities" apply as for any keyword);
``Permanent.ward`` takes the highest ward (as it already does for printed and Equipment ward) and toxic adds up
(CR 702.164c: a creature's toxic total). Only keywords the engine implements with a number are read here.
"""
from __future__ import annotations

import re

from .cx_grammar import Part, keyword_list, verb

_VALUED = re.compile(r"(ward) \{(\d+)\}|(toxic) (\d+)", re.I)


def valued_list(text: str):
    """["ward:2", "flying"] for "ward {2} and flying"; None unless at least one valued keyword and all are read."""
    out, valued = [], False
    for piece in re.split(r",? and |, ", text.strip()):
        m = _VALUED.fullmatch(piece.strip())
        if m:
            name, n = (m[1], m[2]) if m[1] else (m[3], m[4])
            out.append(f"{name.lower()}:{int(n)}")
            valued = True
            continue
        kws = keyword_list(piece)
        if not kws:
            return None
        out += kws
    return out if valued else None


@verb(r"(?:has|have) (.+)", heads=("has", "have"), subjects=("group", "host"))
def has_valued(m, clause):
    kws = valued_list(m[1])
    if not kws or clause.duration != "static":
        return None
    sel = ((clause.subject.group or {}).get("selector") or {}) if clause.subject else {}
    if (sel.get("counter") or ("x",))[0] in ("a", "an", "any"):
        return None         # "with a counter on them": no counter kind the selector checks yet (as static_ward)
    return [Part("grant", data={"keyword": k}) for k in kws]


@verb(r"gains? (.+)", heads=("gain", "gains"))
def gains_valued(m, clause):
    kws = valued_list(m[1])
    if not kws or clause.duration != "eot":
        return None
    return [Part("grant", data={"keyword": k}) for k in kws]
