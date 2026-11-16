"""Three-or-more-part effect lists: "A, B, and C" where every part has a subject of its own.

``cards.parse._split_compound`` splits "A, then B" and "A and B"; a comma list of whole clauses (Together as One:
"Target player draws X cards, ~ deals X damage to any target, and you gain X life") is split here, only when each
part starts with its own subject and parses alone. A part without a subject continues the clause before it
("draws a card, discards a card, ...") and the list is left whole.
"""
from __future__ import annotations

import re


def split_list(s: str):
    """"A, B, and C" with a subject of its own in every part (Together as One: "Target player draws X cards, ~ deals
    X damage to any target, and you gain X life"): each part parsed alone, else None."""
    pieces = re.split(r", (?:and )?", s)
    if len(pieces) < 3 or not re.search(r", and [^,]+$", s):
        return None
    from .cards import _parse_effects
    out = []
    for piece in pieces:
        if not re.match(r"(?:you|~|target (?:player|opponent)|each (?:player|opponent)|that player)(?= )", piece, re.I):
            return None     # a part without its own subject continues the one before ("..., discards a card")
        effs, bad = _parse_effects(piece[0].upper() + piece[1:] + ".")
        if bad or not effs:
            return None
        out += effs
    return out
