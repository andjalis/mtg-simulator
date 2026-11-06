"""Grammar verbs: power and toughness ("gets +2/+0", "has base power and toughness 1/1"). See mtgsim/GRAMMAR.md."""
from __future__ import annotations

from .cx_grammar import Part, verb


@verb(r"gets? ([+-]\d+)/([+-]\d+)", heads=("get", "gets"), subjects=("permanent", "group", "host"))
def gets(m, clause):
    p, t = int(m[1]), int(m[2])
    if clause.duration == "static":
        return [Part("pump", p, t)]               # a static: an anthem or the host's bonus
    if clause.duration != "eot":
        return None                               # a one-shot pump needs "until end of turn"
    if p <= 0 and t <= 0:
        return [Part("debuff_one", -p, -t)]
    return [Part("pump", p, t)]


@verb(r"(?:has|have) base power and toughness (\d+)/(\d+)", heads=("has", "have"))
def base_pt(m, clause):
    if clause.duration != "eot":
        return None
    return [Part("cx_set_base", int(m[1]), int(m[2]))]
