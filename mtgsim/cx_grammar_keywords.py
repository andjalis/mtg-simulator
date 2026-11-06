"""Grammar verbs: keywords and combat restrictions ("gains flying", "loses defender", "have trample",
"can't block", "attacks this combat if able"). See mtgsim/GRAMMAR.md."""
from __future__ import annotations

from .cx_grammar import Part, keyword_list, verb

_FLAG = {"can't block": "cant_block_now", "can't attack": "cant_attack_now", "can't be blocked": "unblockable",
         "attack": "must_attack_now", "block": "must_block_now"}


@verb(r"gains? (.+)", heads=("gain", "gains"))
def gains(m, clause):
    kws = keyword_list(m[1])
    if not kws or clause.duration != "eot":
        return None
    return [Part("grant", data={"keyword": k}) for k in kws]


@verb(r"loses? (.+)", heads=("lose", "loses"))
def loses(m, clause):
    kws = keyword_list(m[1])
    if not kws or clause.duration != "eot":
        return None
    return [Part("cx_lose_kw", data={"keyword": k, "side": "theirs"}) for k in kws]


@verb(r"(?:has|have) (.+)", heads=("has", "have"), subjects=("group", "host"))
def has(m, clause):
    kws = keyword_list(m[1])
    if not kws or clause.duration != "static":
        return None
    return [Part("grant", data={"keyword": k}) for k in kws]


@verb(r"(can't attack or block|can't block|can't attack|can't be blocked)", heads=("can't",),
      subjects=("permanent", "group", "host"))
def cant(m, clause):
    if clause.duration not in ("eot", "turn", "combat", "static"):
        return None
    words = ["can't attack", "can't block"] if m[1] == "can't attack or block" else [m[1]]
    return [Part("cx_temp_kw", data={"keywords": frozenset({_FLAG[w]}),
                                     "side": "mine" if w == "can't be blocked" else "theirs"}) for w in words]


@verb(r"(attack|block)s? (this turn|this combat|each combat) if able", heads=("attack", "attacks", "block", "blocks"),
      subjects=("permanent", "group", "host"))
def if_able(m, clause):
    if (m[2] == "each combat") != (clause.duration == "static") or clause.duration not in ("", "static"):
        return None
    return [Part("cx_temp_kw", data={"keywords": frozenset({_FLAG[m[1]]}), "side": "theirs"})]
