"""Counted target lists in any effect (#312, #391): "up to one target X", "up to two target Xs", "three target Xs".

    Destroy up to two target creatures.                     -> two optional, distinct "destroy" slots
    Attach up to one target Equipment you control to it.    -> one optional slot
    Exile up to three target lands you control, then return them to the battlefield tapped under their
    owner's control.                                         -> three optional chains (exile, return "it")

A sentence nothing else matched is rewritten with one singular target ("target creature", "it" for "them") and
parsed by the whole effect parser, so every verb a template or the grammar knows gets counted targets for free.
The one targeted Effect of that parse, with the Effects that act on it ("prev"), is the chain for one target:

- "up to one": the chain with ``optional_target`` (no target chosen: the chain does nothing, and the spell
  doesn't fizzle for it);
- "N" / "up to N": N copies of the chain, their targets distinct (``distinct`` within a group of their own),
  each optional for "up to".

Each target is then an ordinary slot: chosen by the AI's per-kind policy, checked on resolution, counted for
fizzling, wardable. Rejected: a sentence with another target, plural references the rewrite can't make
singular ("they", "each of them"), or a parse where other Effects don't act on the target.
"""
from __future__ import annotations

import dataclasses
import re

_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_COUNTED = re.compile(r"\b(up to )?(one|two|three|four|five|six|seven) (other |another )?target\b", re.I)
_PLURAL = re.compile(r"\b(creature|permanent|artifact|land|enchantment|planeswalker|player|opponent|card|spell|"
                     r"Equipment|Aura|Vehicle|token)s\b|\b([A-Z][a-z]+)s\b")
_IRREGULAR = {"Elves": "Elf", "Dwarves": "Dwarf", "Wolves": "Wolf"}


def _singular_np(rest: str):
    """The text after "target": plural nouns of the noun phrase made singular, up to where it ends."""
    end = re.search(r"\b(?:you|an opponent|your opponents|target|that|from|to|on|onto|with|without|and gain|"
                    r"into|in|at|each|until|then|this)\b|[,.]", rest)
    np, tail = (rest[:end.start()], rest[end.start():]) if end else (rest, "")
    for plural, single in _IRREGULAR.items():
        np = re.sub(rf"\b{plural}\b", single, np)
    np = _PLURAL.sub(lambda m: m[1] or m[2], np)
    return np + tail


def _rewrite(s: str, n: int):
    """s with the counted target made a single target and its plural references singular, or None."""
    m = _COUNTED.search(s)
    head, rest = s[:m.start()], s[m.end():]
    other = m[3] or ""
    if n > 1:
        rest = _singular_np(rest)
        rest = re.sub(r"\btheir owners'", "its owner's", rest)
        rest = re.sub(r"\btheir owner's\b", "its owner's", rest)
        rest = re.sub(r"\bthem\b", "it", rest)
        rest = re.sub(r"\bthose (creature|permanent|land|artifact|card)s\b", r"that \1", rest)
        if re.search(r"\b(?:they|their|them|those|each|these)\b", rest, re.I):
            return None
    return head + other + "target" + rest


def lift(s: str, effects: list) -> bool:
    """Parse s, a sentence with one counted target ("up to two target creatures"), into effects. True if it did."""
    from .cards.parse import _parse_effects
    from .engine.state import TARGETED
    found = list(_COUNTED.finditer(s))
    if len(found) != 1 or len(re.findall(r"\btarget\b", s, re.I)) != 1:
        return False
    m = found[0]
    n, upto = _NUM[m[2].lower()], bool(m[1])
    if n == 1 and not upto:
        return False                          # "one target creature" is just "target creature"
    text = _rewrite(s, n)
    if text is None:
        return False
    new, bad = _parse_effects(text[0].upper() + text[1:] + ".")
    if bad or not new:
        return False
    targeted = [i for i, e in enumerate(new) if e.target in TARGETED]
    if len(targeted) != 1 or targeted[0] != 0:
        return False
    # the chain on one target: the targeted Effect and Effects on "it"; for one target, untargeted Effects too
    # ("destroy up to one target artifact and you gain 2 life"), which several copies would repeat
    if any(e.target != "prev" and not (n == 1 and e.target == "none") for e in new[1:]):
        return False
    if any(e.data.get("distinct") or e.data.get("optional_target") for e in new):
        return False                          # already a counted target of its own
    group = "cx_multi:" + text.lower()           # the same for every parse of this sentence
    for _ in range(n):
        first = dataclasses.replace(new[0], data=dict(new[0].data, **({"optional_target": True} if upto else {}),
                                                      **({"distinct": True, "group": group} if n > 1 else {})))
        effects.append(first)
        effects.extend(dataclasses.replace(e, data=dict(e.data)) for e in new[1:])
    return True

