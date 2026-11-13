"""Temporary grants of a quoted triggered ability (#338): "<subject> [gets +N/+N and] gains "When ..."" until end of turn.

    Until end of turn, target creature gets +2/+0 and gains "When this creature dies, return it to the battlefield
    tapped under its owner's control."                                                          (Abnormal Endurance)
    Until end of turn, up to two target creatures you control each gain "Whenever this creature deals combat
    damage to a player, draw a card."                                                              (Warriors' Lesson)
    Until end of turn, creatures you control gain "Whenever this creature deals damage to an opponent, ..."

The grammar core does not look inside quotes, so a rider first masks the quoted ability with a placeholder word
("qtrigN") and parses the rest of the sentence with the whole grammar; the ``gains qtrigN`` verb then hands the
recipient the parsed Triggers (``cx_trigger_grants.quoted_triggers``) with the existing ``grant_triggers`` kind
(the recipient's ``temp_triggers``, cleared at cleanup, kept in the departure snapshot for dies triggers). A group
subject is a one-shot ``cx_group``: the creatures it affects are fixed when the spell resolves, so a creature that
arrives later doesn't gain the ability. Only "until end of turn" is accepted; a quote that hurts its holder is
refused for now (the AI would give it to its own creature).
"""
from __future__ import annotations

import itertools
import re

from .cx_grammar import Part, rider, verb

_QUOTE = re.compile(r'"((?:When|Whenever|At) [^"]+)"', re.I)
_PENDING: dict = {}
_IDS = itertools.count()


@rider(r'(?P<s>[^"]*"(?:When|Whenever|At) [^"]+"[^"]*)')
def _mask(m, inner):
    from .cx_trigger_grants import hostile, quoted_triggers
    quote = _QUOTE.search(m["s"])
    triggers = quoted_triggers(quote[1])
    if triggers is None or hostile(quote[1]):
        return None
    key = f"qtrig{next(_IDS)}"
    _PENDING[key] = triggers
    try:
        return inner(m["s"][:quote.start()] + key + m["s"][quote.end():])
    finally:
        _PENDING.pop(key, None)


@verb(r"gains? (qtrig\d+)", heads=("gain", "gains"), subjects=("permanent", "group"))
def gains_quoted(m, clause):
    triggers = _PENDING.get(m[1])
    if triggers is None or clause.duration != "eot":
        return None
    return [Part("grant_triggers", data={"triggers": list(triggers)})]
