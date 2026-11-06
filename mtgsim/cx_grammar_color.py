"""Grammar verbs: colour changes ("becomes black", "becomes red in addition to its other colors"). Layer 5,
the cx_color kind (engine/kinds/cx_grammar.py). See mtgsim/GRAMMAR.md."""
from __future__ import annotations

import re

from .cx_grammar import Part, verb

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def colors(text: str):
    """frozenset of colour letters for "black" / "red and white" / "colorless", or None."""
    text = text.lower().strip()
    if text == "colorless":
        return frozenset()
    parts = re.split(r",? and |, ", text)
    if any(p not in _COLORS for p in parts):
        return None
    return frozenset(_COLORS[p] for p in parts)


@verb(r"becomes? (.+?)( in addition to its other colors)?", heads=("become", "becomes"))
def becomes(m, clause):
    cols = colors(m[1])
    if cols is None or not cols and m[2] or clause.duration not in ("eot", ""):
        return None
    return [Part("cx_color", data={"colors": "".join(sorted(cols)), "op": "add_colors" if m[2] else "set_colors",
                                   "eot": clause.duration == "eot", "side": "theirs"})]
