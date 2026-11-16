"""Compound trigger heads (#399): one ability with two heads and one body.

    When ~ enters and whenever you cast a spell with mana value 5 or greater, draw a card.
    At the beginning of your upkeep and whenever you cast a green spell, put a charge counter on ~.
    When you cycle this card and when ~ dies, you may tap or untap target permanent.

Each head is its own trigger event with the same effects (CR 603.2: the ability triggers on either event). The line
is split into "<head A>, <body>" and "<head B>, <body>" and each half goes through the ordinary trigger parser; the
compound is accepted only when both halves parse completely (no unmatched sentence, no modal header), so nothing a
half can't read is dropped. In the second head "it" is the permanent itself ("whenever it attacks", "when you
sacrifice it"), written as "~" before parsing. The body is shared, so its "it" means the same object under both
heads: after "When ~ enters" (where it is ~) the other half's "it" Effects are bound to ~ too ("When ~ enters and
whenever you expend 4, put a stash counter on it"). Any other "it" (target ``prev``, the event object) outside an
enters or dies half is refused: the two events need not give it the same object.

Not compounds: "Whenever ~ and at least one other Warrior attack" (one event with a condition) and "you and/or a
permanent you control" (one subject): neither has a second "when"/"whenever"/"at" head.
"""
from __future__ import annotations

import re

# "<A> and <when|whenever|at the beginning of> <B>, <body>": A starts the line, B starts after " and ".
_SPLIT = re.compile(r"((?:When|Whenever|At) .+?) and ((?:when|whenever|at the beginning of) .+)")


def split(line: str, parse):
    """(triggers, [], None) for a compound-head line whose halves both parse fully with ``parse``, else None."""
    m = _SPLIT.fullmatch(line)
    if not m or "," in m[1]:
        return None
    a, tail = m[1], m[2]
    # B's head ends at one of the commas that follow it; try each, shortest first (heads rarely hold commas).
    for comma in (i for i, ch in enumerate(tail) if ch == ","):
        b, body = tail[:comma], tail[comma + 2:]
        if not body:
            continue
        b = re.sub(r"\bit\b", "~", b[0].upper() + b[1:])
        halves = [parse(f"{a}, {body}"), parse(f"{b}, {body}")]
        if all(h is not None and h[0] and not h[1] and h[2] is None for h in halves):
            return _shared_it(a, list(halves[0][0]), list(halves[1][0]))
    return None


def _shared_it(a: str, first: list, second: list):
    from .cx_trig_self_it import _bind
    if re.fullmatch(r"When ~ enters", a):
        second = [_bind(t) for t in second]
    if any(e.target == "prev" for t in first + second if t.event not in ("etb", "dies") for e in t.effects):
        return None
    return (first + second, [], None)
