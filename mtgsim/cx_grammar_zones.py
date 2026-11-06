"""Grammar verbs that move permanents between zones: destroy, exile and return to hand, said as an imperative
("Destroy target creature or planeswalker that's red or green.", "Exile up to two target artifacts.", "Return all
nonland permanents to their owners' hands."). The object is read by ``cx_grammar.object_phrase``: one or more
targets, "it" / "that creature", or a group ("all"/"each" <noun phrase>, a list "artifacts, creatures, and lands").

The existing kinds do the work, so the rules stay theirs: ``destroy`` (indestructible, regeneration),
``exile_permanent`` and ``bounce`` (``leave_battlefield``: a card goes to its owner's exile or hand, a token
ceases to exist). See mtgsim/GRAMMAR.md.
"""
from __future__ import annotations

import re

from .cx_grammar import Part, count, object_phrase, verb

_KINDS = {"destroy": "destroy", "exile": "exile_permanent", "return": "bounce"}
# Words that turn a zone change into something these kinds don't do: linked exile, a rider, a choice, a
# condition, or a card in another zone.
_REJECT = re.compile(r"\b(?:until|unless|if|instead|card|cards|graveyards?|library|exile|hand|from|then|"
                     r"face (?:up|down)|at the beginning|at end of|this way|and/or|this turn|last turn|chosen|your choice|"
                     r"that player|defending player|its controller|its owner)\b|\bor all\b")


_COLOR = r"(?:white|blue|black|red|green)"
_THATS = re.compile(rf"((?:(?:up to )?\w+ )?(?:other |another )?target |all |each )?([a-z]+(?: or [a-z]+)*) that's "
                    rf"({_COLOR}(?:,? or {_COLOR})*)")


def _object(text: str):
    """object_phrase, also reading "target creature or planeswalker that's red or green" as "target red or green
    creature or planeswalker" (types without other qualifiers only)."""
    m = _THATS.fullmatch(text)
    if m:
        text = f"{m[1] or ''}{m[3]} {m[2]}"
    return object_phrase(text)


def objects(text: str):
    """The Subjects an object phrase names: one; one per item of "target A, target B, and target C"; or one
    group per item of "all A, B, and C". None if any part is not understood."""
    if _REJECT.search(text):
        return None
    obj = _object(text)
    if obj is not None:
        # "it" / "that creature" (target "prev") waits for the back-reference round
        return [obj] if obj.kind == "group" or obj.kind == "permanent" and obj.target != "prev" else None
    items = re.split(r",? and |, ", text)
    if len(items) > 1 and all(i.startswith("target ") for i in items):      # "target creature and target land"
        objs = [_object(i) for i in items]
        ok = all(o is not None and o.kind == "permanent" and o.target == "permanent" and o.copies == 1 for o in objs)
        return objs if ok else None
    m = re.fullmatch(r"(all|each) (.+)", text)
    if m is None:
        return None
    items = re.split(r",? and (?:all )?|, (?:all )?", m[2])
    if len(items) < 2:
        return None
    out = []
    for words in items:
        obj = _object(f"{m[1]} {words}")
        if obj is None or obj.kind != "group":
            return None
        out.append(obj)
    return out


def _parts(kind: str, text: str):
    objs = objects(text)
    if objs is None:
        return None
    return [Part(kind, obj=obj) for obj in objs]


@verb(r"(destroy|exile) (.+)", heads=("destroy", "exile"), subjects=("imperative",))
def destroy_exile(m, clause):
    if clause.duration:
        return None
    return _parts(_KINDS[m[1]], m[2])


@verb(r"return (.+?) to (?:its|their) owners?'? hands?", heads=("return",), subjects=("imperative",))
def bounce(m, clause):
    if clause.duration:
        return None
    return _parts("bounce", m[1])


@verb(r"sacrifices? (a|an|one|two|three|four|five|\d+) (.+)", heads=("sacrifice", "sacrifices"),
      subjects=("player",))
def sacrifice(m, clause):
    """"Each player sacrifices two lands", "each opponent sacrifices a creature or planeswalker": cx_edict."""
    n = count(m[1])
    noun = m[2]
    if not n or clause.duration or _REJECT.search(noun) or re.search(r"\b(?:you|they|control|controls|other|"
                                                                      r"than|greatest|least|with the)\b", noun):
        return None
    if (n == 1) == bool(re.fullmatch(r".*s", noun)) and not re.fullmatch(r".*(?:ss|elves|dwarves)", noun):
        return None                     # "a creatures" / "two creature": not a phrase we read
    obj = object_phrase(("each " if n == 1 else "all ") + noun)
    if obj is None or obj.kind != "group":
        return None
    return [Part("cx_edict", n, data={"noun": obj.group, "scales": True})]
