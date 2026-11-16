"""Conditions in the positions the leading "If C, B." reader doesn't see (#397).

    Then if you control three or more Bears, draw two cards.          -> If you control three or more Bears, draw ...
    Draw a card if you control an enchantment.                        -> If you control an enchantment, draw a card.
    Then destroy ~ if it has five or more hunger counters on it.      (refused: "it" is a referent, see below)

A sentence is moved to the leading form only when the condition library (``cx_condlib.parse`` or the fixed
``_if_cond`` table) reads C and the rewritten sentence parses with nothing left over; otherwise the Oracle text
stays as it was, so a template that reads the whole sentence keeps it. The condition is checked as B resolves, so
"Then if" sees the state after the effects before it.

Refused here: a condition or an effect naming a referent ("it", "its", "that creature", "that player", "they",
...). The leading reader binds those to the source, while in these positions they usually mean the trigger's object
or the effect's target (Ordeal of Thassa's "it" is the enchanted creature), and "that player" after a targeted
permanent doesn't bind at all yet (Compelling Deterrence). Also refused: "even if" / "only if" / "as if" and
"if able".
"""
from __future__ import annotations

import re

_REFERENT = re.compile(r"\b(?:it|its|it's|that|those|this|they|them|their|he|she|his|her)\b", re.I)
_BUSY: list = []


def _known(cond: str) -> bool:
    from .cards.clauses import _if_cond
    from .cx_condlib import parse
    return bool(parse(cond) or _if_cond(cond))


def _parses(sentence: str) -> bool:
    from .cards import _parse_effects
    _BUSY.append(1)
    try:
        effects, bad = _parse_effects(sentence)
    finally:
        _BUSY.pop()
    return bool(effects) and not bad


def _lead(cond: str, body: str, original: str):
    if _REFERENT.search(cond) or _REFERENT.search(body) or re.search(r"\bable\b", cond, re.I) or not _known(cond):
        return original
    body = body.strip()
    sentence = f"If {cond}, {body[0].lower() + body[1:] if not body.startswith('~') else body}."
    if not _parses(sentence) or _parses(original):
        return original
    return sentence


def _then_if(m):
    if _BUSY:
        return m[0]
    return _lead(m[1], m[2], m[0])


def _suffix(m):
    if _BUSY:
        return m[0]
    body, cond = re.sub(r"^then ", "", m[2], flags=re.I), m[3]
    if re.search(r"\b(?:even|only|as)$", body, re.I) or " if " in body.lower():
        return m[0]
    return (m[1] or "") + _lead(cond, body, m[2] + " if " + cond + ".")


SUBS = [
    (re.compile(r"(?:^|(?<=\. ))then if ([^,.]+?), ([^.]+)\.", re.I), _then_if),
    (re.compile(r"(^|(?<=\. ))((?!if |when |whenever |as long as |then if )(?:then )?[A-Z~][^.]*?) if ([^.,]+)\.",
                re.I), _suffix),
]
