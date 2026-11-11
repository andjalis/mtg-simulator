"""Blink templates: "Exile <target>, then return it to the battlefield under its owner's control".

The exiled card comes back as a new object (counters, Auras and damage are gone, enters-the-battlefield
triggers fire) and a token is gone for good. The ``blink`` kind (engine/kinds/permanents.py) does the
exile and the return. Optional modifiers: ``tapped``, ``yours`` (under your control instead of its
owner's), ``counter`` (a +1/+1 counter on it) and ``delayed`` (at the beginning of the next end step).
Joined at the end of ``cards/__init__.py``.
"""
from __future__ import annotations

import re

_COUNT = {"one": 1, "two": 2}
_RETURN = (r"to the battlefield( tapped)? under (its owner's|their owners'|their owner's|your) control"
           r"( with a \+1/\+1 counter on it)?")


def _singular(phrase):
    """"creatures you control" -> "creature you control" (the selector reads one noun)."""
    return re.sub(r"\b(\w+?)s\b(?= you control| an opponent controls|$)", r"\1", phrase, count=1)


def _build(count_word, other, phrase, tapped, who, counter, delayed):
    from . import permanent_templates as pt
    from .cards import Effect, NO_MATCH
    n = _COUNT.get((count_word or "").lower(), 1)
    text = ("up to one " if count_word else "") + (other or "") + "target " + (_singular(phrase) if n > 1 else phrase)
    subj = pt.subject(text)
    if subj is None or subj[0] != "permanent":
        return NO_MATCH          # None would mean "matched, no effect": the sentence would be dropped silently
    target, data = subj
    data = dict(data, tapped=bool(tapped), yours=who.lower() == "your", counter=bool(counter), delayed=delayed)
    effects = []
    for i in range(n):
        d = dict(data)
        if n > 1:
            d["distinct"] = True
        effects.append(Effect("blink", target=target, data=d))
    return effects


def _self(tapped, who, counter):
    from .cards import Effect
    return Effect("blink", target="self", data={"tapped": bool(tapped), "yours": who.lower() == "your",
                                                "counter": bool(counter), "delayed": False})


EFFECT_PATTERNS = [
    (r"exile (?:up to (one|two) )?(another |other )?target (.+?)(, then| and then) return (?:it|that card|those cards|them) "
     + _RETURN, lambda m: _build(m[1], m[2], m[3], m[5], m[6], m[7], False)),
    (r"exile ~(, then| and then) return it " + _RETURN.replace("( with", "( with"),
     lambda m: _self(m[2], m[3], m[4])),
    (r"BLINKLATER (?:up to (one|two) )?(another |other )?target (.+?)\|" + _RETURN,
     lambda m: _build(m[1], m[2], m[3], m[4], m[5], m[6], True)),
]

SUBS = [
    (re.compile(r"exile (?:up to (one|two) )?(another |other )?target ([^.,]+?)\. return (?:it|that card|those cards|them) "
                + _RETURN + r" at the beginning of the next end step\.", re.I),
     lambda m: "BLINKLATER " + (f"up to {m[1]} " if m[1] else "") + (m[2] or "") + "target " + m[3] + "|"
               + "to the battlefield" + (m[4] or "") + " under " + m[5] + " control" + (m[6] or "") + "."),
]
