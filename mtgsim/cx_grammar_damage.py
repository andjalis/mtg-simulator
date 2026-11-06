"""Grammar verbs for damage: "<source> deals N damage to <recipient>[ and M damage to <recipient>]".

    ~ deals 2 damage to any target and 1 damage to any other target.
    ~ deals 5 damage to target creature and 2 damage to that creature's controller.
    It deals 1 damage to each creature without flying.
    ~ deals 2 damage to that land's controller.
    ~ deals 1 damage to it.                                  (in a trigger: the permanent it triggered on)

The subject is the damage source: "~" (the resolving spell or the permanent), "it" / "that creature" (the trigger's
permanent, else the object itself) or the enchanted / equipped creature. The recipient is read by
``cx_grammar.object_phrase`` and carried as the Part's own object. With "~" as the source, a single recipient goes to the
engine's ``damage`` kind (its AI target choice, lifelink, infect, prevention and "exile if it would die" all apply);
another source, a group ("each creature without flying") or a set of players go to ``cx_damage``, which deals the
same real damage from that source. Amounts are a number or X (the X paid). "Divided as you choose" stays with cx_damage.py; "that
much", "equal to ..." and "where X is ..." amounts are not read here. See mtgsim/GRAMMAR.md.
"""
from __future__ import annotations

import re

from .cx_grammar import Part, count, object_phrase, verb

_AMOUNT = r"(\w+)"


def _amount(word: str):
    """(amount, data) for "3" / "three" / "X", or None."""
    if word.lower() == "x":
        return 0, {"x": True}
    n = count(word)
    return (n, {}) if n else None


def _source(clause):
    """The source key for the clause subject, or None when the subject can't deal the damage here."""
    subj = clause.subject
    if subj.kind == "host":
        return "host"
    if subj.kind == "permanent" and subj.copies == 1 and subj.target in ("self", "prev"):
        return subj.target
    return None


def _object(text: str, source: str):
    """The recipient Subject, or None. "itself" is the source; "that land's controller" is the controller of the
    permanent the sentence refers to. "Its controller" / "its owner" are rejected: "its" names the source here, while
    the grammar's "controller" reads the previous object."""
    low = text.strip().lower()
    if low.startswith("its "):
        return None
    if low == "itself":
        return object_phrase({"self": "~", "prev": "it"}[source]) if source in ("self", "prev") else None
    low = re.sub(r"^that (?:land|artifact|enchantment|planeswalker)'s (controller|owner)$", r"that permanent's \1", low)
    return object_phrase(low)


def _targeted(obj) -> bool:
    return obj is not None and obj.target not in ("none", "self", "prev", "host")


def _part(n, data, obj, source, first_targeted):
    """One damage Part, or None. ``first_targeted``: an earlier recipient of the sentence was a target."""
    if obj is None:
        return None
    if source == "self" and (_targeted(obj) or obj.kind not in ("player", "group")):
        return Part("damage", n, 0, data, obj=obj)
    if obj.kind == "group" and data.get("x"):
        return None         # a group's X would need the wrapper's amount (not on this branch's core)
    if _targeted(obj):
        return None     # another source would need cx_damage, which the default AI can't aim yet
    if source == "prev" and first_targeted:
        return None     # "it" would read the first recipient once that one is chosen
    return Part("cx_damage", n, 0, dict(data, source=source, side="theirs"), obj=obj)


@verb(rf"deals? {_AMOUNT} damage to (.+?)(?: and {_AMOUNT} damage to (.+))?",
      heads=("deal", "deals"), subjects=("permanent", "host"))
def deals(m, clause):
    if clause.duration:
        return None
    source = _source(clause)
    if source is None:
        return None
    first = _amount(m[1])
    if first is None or re.search(r"\b(?:divided|each of|where|equal|that much|instead|unless|for each)\b",
                                  clause.verb):
        return None
    m2, m3, m4 = m[2], m[3], m[4]
    both = re.fullmatch(r"(each [\w ]+?) and (each [\w ]+)", m2)
    if both and not m3 and _object(m2, source) is None:
        m2, m3, m4 = both[1], m[1], both[2]         # "each creature and each player": the same amount to both
    obj1 = _object(m2, source)
    parts = [_part(first[0], first[1], obj1, source, False)]
    if m3:
        second = _amount(m3)
        if second is None:
            return None
        distinct = re.fullmatch(r"any other target", m4)
        if distinct and not re.fullmatch(r"any target", m2):
            return None
        obj2 = _object("any target" if distinct else m4, source)
        parts.append(_part(second[0], second[1], obj2, source, _targeted(obj1)))
        if distinct and all(parts):         # "any other target": not the first one (the source may be either)
            for p in parts:
                p.data = dict(p.data, distinct=True)
    return None if any(p is None for p in parts) else parts
