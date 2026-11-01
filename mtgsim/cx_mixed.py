"""Mixed sentences: a P/T change joined to a combat clause.

    It gets +2/+2 until end of turn and can block an additional creature this turn.
    Target creature gets +3/+3 until end of turn and must be blocked this turn if able.
    ~ gets +3/+0 until end of turn and can attack this turn as though it didn't have defender.

The SUB splits the sentence in two ("... until end of turn. It can block ..."), so each half reaches the template
that already reads it; the clause refers to the same creature ("it", or "~" for the source). A few "it" / "that
creature" forms of those clauses are added here. Static forms ("Equipped creature gets +2/+2 and can't block.",
"As long as ..., ~ gets +2/+2 and can't block.") are read by cx_statics and cx_conditions."""
from __future__ import annotations

import re

_SUBJ = r"(?P<s>~|it|that creature|target creature(?: you control| an opponent controls| you don't control)?)"
_CLAUSE = r"(?P<c>(?:can|can't|must|attacks|blocks)\b[^.]*?this (?:turn|combat)[^.]*)"
_SPLIT = re.compile(rf"(?<![\w]){_SUBJ} gets (?P<pt>[+-]\d+/[+-]\d+) until end of turn and {_CLAUSE}(?=\.|$)", re.I)


def _split(m):
    it = "~" if m["s"] == "~" else "it"
    return f"{m['s']} gets {m['pt']} until end of turn. {it.capitalize() if it == 'it' else it} {m['c']}"


SUBS = [(_SPLIT, _split)]


def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


EFFECT_PATTERNS = [
    (r"it attacks this (?:turn|combat) if able", lambda m: _effect("grant", target="prev",
                                                                   data={"keyword": "must_attack_now"})),
    (r"that creature can't be blocked this turn", lambda m: _effect("unblockable", target="prev")),
    (r"(?P<w>~|it|that creature) can't block this turn",
     lambda m: _effect("grant", target="self" if m["w"] == "~" else "prev", data={"keyword": "cant_block_now"})),
]
