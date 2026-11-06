"""Grammar verbs: basic land type changes ("Target land becomes an Island until end of turn.", "Target nonbasic
land becomes a Mountain.", "Each land you control becomes a Forest in addition to its other types until end of
turn."). See mtgsim/GRAMMAR.md.

A "becomes a Swamp" land loses its other land types and the mana and abilities they gave, and taps for B; "in
addition to its other types" adds the type and its mana. The cx_landtype kind keeps the change on the land
(Permanent.cx_landtype_extra) for the turn or for good; cx_landtypes.update applies it with the static ones."""
from __future__ import annotations

import re

from .cx_grammar import Part, verb

_BASIC = {"plains": "Plains", "island": "Island", "swamp": "Swamp", "mountain": "Mountain", "forest": "Forest"}


@verb(r"becomes? (?:an? )?(plains|islands?|swamps?|mountains?|forests?)( in addition to (?:its|their) other (?:land )?types)?",
      heads=("become", "becomes"), subjects=("permanent", "group"))
def becomes_land_type(m, clause):
    subj = clause.subject
    if clause.duration not in ("eot", ""):
        return None
    if subj.target != "prev" and not re.search(r"\blands?\b|plains|islands?|swamps?|mountains?|forests?",
                                                subj.text, re.I):
        return None             # only lands: "target permanent becomes a Forest" would make a nonland one
    word = m[1] if m[1] in _BASIC else m[1][:-1]
    if (word != m[1]) != (subj.kind == "group" and clause.verb.startswith("become ")):
        return None             # "becomes an Island" for one land, "become Islands" for a group
    return [Part("cx_landtype", data={"mode": "add" if m[2] else "set", "types": (_BASIC[word],),
                                      "eot": clause.duration == "eot", "side": "theirs"})]


def extra(perm) -> tuple:
    """The (mode, types) land-type changes cx_landtype put on perm that still last."""
    game = getattr(perm.controller, "_game", None)
    return tuple((mode, types) for turn, mode, types in getattr(perm, "cx_landtype_extra", ())
                 if turn is None or game is not None and turn == game.turn)
