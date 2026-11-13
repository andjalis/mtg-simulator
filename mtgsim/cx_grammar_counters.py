"""Counter placement composed with selectors, conditions and coordinated clauses.

The plain "put N <kind> counters on <obj>" forms live in ``permanent_templates`` and
``cx_counters``; this module owns the compositional shapes around them:

* coordinated clauses: "Put a +1/+1 counter on that creature and a +1/+1 counter on ~",
  "Put five +1/+1 counters on each creature you control and five loyalty counters on each
  other planeswalker you control", "Put a +1/+1 counter on target creature, two +1/+1
  counters on another target creature, and three +1/+1 counters on a third target creature".
  The verb and the quantity may be elided after the first clause ("and five loyalty
  counters on each other ..."); every clause keeps its own counter kind, recipient and
  amount. Targeted clauses get distinct targets, as "another target" demands.
* a single choice from a group without the word "target": "put a vigilance counter on a
  creature you control" (the engine picks the permanent the same way it picks a target).
* a trailing condition: "put a +1/+1 counter on equipped creature if it's blue",
  "put two +1/+1 counters on that permanent if you control an artifact and an
  enchantment", "put a +1/+1 counter on it if it's a creature". The condition is kept on
  the effect (``Effect.cond``) and evaluated by the usual condition library; "it's
  <color>" on an equipped/enchanted object is read on that object (``host_is``).

The "if <condition>, <body>" prefix form is handled by ``cards.parse._parse_effects``
itself; the condition phrases it needs ("~ has fewer than three charge counters on it",
"~ didn't attack this turn", "~ dealt damage to an opponent this turn") are read by
``cx_condlib``.
"""
from __future__ import annotations

import dataclasses
import re

_NUMBER = r"(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+)"
_COUNTER = r"(?:[+-]\d+/[+-]\d+|[a-z]+(?:-[a-z]+)?)"
_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}

# one placement clause: "[N <kind> counters? on] <object>" (the quantity may be elided)
_CLAUSE = re.compile(rf"(?:(?P<n>{_NUMBER}) (?P<k>{_COUNTER}) counters? on )?(?P<obj>.+)", re.I)
# "a third target creature" / "one other target creature" is "another target creature"
_ORDINAL = re.compile(r"^(?:a |one )?(?:second|third|fourth|fifth) ", re.I)


def _num(word: str) -> int:
    from .cards.model import _num as num
    return num(word)


_CHOSEN = "chosen:"      # _obj's mark for an article object: a choice on resolution, picked like a target


def _obj(text: str):
    """The object of a placement clause, normalised: an article in front of a group noun
    ("a creature you control") is a choice from that group, read as "target <group>" and marked _CHOSEN."""
    from .permanent_templates import subject
    text = _ORDINAL.sub("another ", text)
    bare = re.sub(r"^(?:a|an) ", "", text, flags=re.I)
    for cand in (text, bare):
        if subject(cand) is not None:
            return cand
    if bare != text and subject("target " + bare) is not None:
        return _CHOSEN + "target " + bare
    return None


def _place(obj, n, kind):
    """The add_counter for one clause. An article object ("a planeswalker you control", #360) is not a target:
    the slot may stay empty (the spell is cast and its other effects happen without one) and it doesn't keep the
    spell from fizzling (``data["chosen"]``)."""
    from .cards.model import NO_MATCH
    from .permanent_templates import build
    chosen = obj.startswith(_CHOSEN)
    eff = build("add_counter", obj[len(_CHOSEN):] if chosen else obj, amount=n, data={"counter": kind})
    if eff is None:
        return NO_MATCH
    if chosen:
        eff = dataclasses.replace(eff, data=dict(eff.data, optional_target=True, chosen=True))
    return eff


def _coordinated(m):
    """"Put N <kind> counters on <obj1>[,] [and] [N <kind> counters on] <obj2> ...": one
    add_counter per clause; the first clause carries the sentence's quantity, later ones
    their own or inherit it."""
    from .cards.model import NO_MATCH
    rest = m["rest"]
    if re.search(r"\b if \b|\b unless \b", rest, re.I):
        return NO_MATCH                      # a condition rider owns this sentence
    out = []
    n, kind = _num(m["n"]), m["k"].lower()
    for clause in re.split(r", and |, | and ", rest):
        cm = _CLAUSE.fullmatch(clause.strip())
        if cm is None:
            return NO_MATCH
        if cm["n"]:
            n, kind = _num(cm["n"]), cm["k"].lower()
        obj = _obj(cm["obj"])
        if obj is None:
            return NO_MATCH
        eff = _place(obj, n, kind)
        if eff is NO_MATCH:
            return NO_MATCH
        if eff.target == "permanent":         # targeted clauses name distinct permanents
            eff = dataclasses.replace(eff, data=dict(eff.data, distinct=True, group="cx_place"))
        out.append(eff)
    return out or NO_MATCH


def _suffix_if(m):
    """"Put N <kind> counters on <obj> if <cond>": the trailing condition gates the
    placement (kept as Effect.cond)."""
    from .cards.model import NO_MATCH
    from .cards.clauses import _if_cond
    from .cx_condlib import _code
    obj = _obj(m["obj"])
    if obj is None:
        return NO_MATCH
    eff = _place(obj, _num(m["n"]), m["k"].lower())
    if eff is NO_MATCH:
        return NO_MATCH
    cond = m["cond"].strip()
    cm = re.fullmatch(r"(?:it's|it is) (white|blue|black|red|green)", cond, re.I)
    if cm and eff.target == "host":           # "equipped creature if it's blue": the host's colour
        cond = _code("host_is", {"colors": [_COLORS[cm[1].lower()]]})
    else:
        pm = re.fullmatch(r"(?:it's|it is) (?:a|an) (.+)", cond, re.I)
        if eff.target == "prev" and pm:
            # "put a +1/+1 counter on it if it's a creature": "it" is the object just named (prev),
            # not the trigger's referent the generic "it's a ..." alias reads
            from .cx_condlib import _filter
            f = _filter(pm[1].replace(",", ""), plural=False)
            cond = _code("prev_is", f) if f is not None else ""
        else:
            cond = _if_cond(cond)
    if not cond:
        return NO_MATCH
    return dataclasses.replace(eff, cond=eff.cond or cond)


EFFECT_PATTERNS = [
    (rf"put (?P<n>{_NUMBER}) (?P<k>{_COUNTER}) counters? on (?P<obj>.+?) if (?P<cond>.+)", _suffix_if),
    (rf"put (?P<n>{_NUMBER}) (?P<k>{_COUNTER}) counters? on (?P<rest>.+)", _coordinated),
]
