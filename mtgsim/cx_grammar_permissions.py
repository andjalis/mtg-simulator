"""Grammar verbs: combat permissions ("can attack as though it didn't have defender"), as statics on ~, a host or a
group, gated or not (cx_static_gate), and for this turn. See mtgsim/GRAMMAR.md.

The permission is the ``attacks_despite_defender`` keyword, which ``Permanent.can_attack`` reads."""
from __future__ import annotations

from .cx_grammar import Part, verb


@verb(r"can attack(?: this turn)? as though (?:it|they) didn't have defender", heads=("can",),
      subjects=("permanent", "group", "host"))
def defender(m, clause):
    if clause.duration == "static" and "this turn" not in m[0]:
        return [Part("grant", data={"keyword": "attacks_despite_defender"})]
    return None
