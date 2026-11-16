"""Grammar verbs: static base power and toughness ("Enchanted creature has base power and toughness 0/2", "Other
creatures have base power and toughness 1/1", "During your turn, ~ has base power and toughness 5/2"). See
mtgsim/GRAMMAR.md and mtgsim/cx_static_chars.py (#406).

The value is a cx_static rule ``cx_chars``: a tuple of layer operations, here ``(("set_base", p, t),)``.
cx_static_chars.effects turns every such rule that reaches a permanent (its own, its Aura's or Equipment's, a group
static, a gated row) into a timestamped layer-7b ContinuousEffect, so counters and pumps apply on top and a later
animation wins. Static only: the one-shot "until end of turn" form is cx_grammar_stats'."""
from __future__ import annotations

from .cx_grammar import Part, _stat_conditioned, verb

_SUBJECTS = ("permanent", "group", "host")


def _part(clause, power, toughness):
    if clause.duration != "static":
        return None
    group = clause.subject.group or {}
    spec = group.get("selector", group)
    if clause.subject.kind == "group" and (_stat_conditioned(spec) or "cx_desc" in spec):
        return None             # "creatures with power 2 or less have base power ..." would read its own result
    return [Part("cx_static", data={"rule": "cx_chars", "value": (("set_base", power, toughness),)})]


@verb(r"(?:has|have) base power and toughness (\d+)/(\d+)", heads=("has", "have"), subjects=_SUBJECTS)
def base_pt(m, clause):
    return _part(clause, int(m[1]), int(m[2]))


@verb(r"(?:has|have) base (power|toughness) (\d+)", heads=("has", "have"), subjects=_SUBJECTS)
def base_one(m, clause):
    n = int(m[2])
    return _part(clause, n if m[1] == "power" else None, n if m[1] == "toughness" else None)


@verb(r"loses? all abilities", heads=("lose", "loses"), subjects=("permanent", "group"))
def lose_all(m, clause):
    """"Until end of turn, target creature loses all abilities" (Turn to Frog): a layer-6 lose_all effect
    (cx_static_chars, #406 slice 3) until end of turn, or for good without a duration. Static lines are
    cx_static_chars' own."""
    if clause.duration not in ("eot", ""):
        return None
    return [Part("cx_lose_all", data={"eot": clause.duration == "eot", "side": "theirs"})]
