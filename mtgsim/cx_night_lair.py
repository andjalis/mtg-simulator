"""Lair lands: "sacrifice it unless you return a non-Lair land you control to its owner's hand."

Read as one ``sac_unless_bounce`` effect; the handler in engine/kinds/cx_night_lair.py bounces the cheapest
non-Lair land (never the source) or sacrifices the source when there is none."""
from __future__ import annotations


def _lair(m):
    from .cards.model import Effect
    return [Effect("sac_unless_bounce", data={"not_subtype": "Lair"})]


EFFECT_PATTERNS = [(r"sacrifice (?:it|~) unless you return a non-lair land you control to its owner's hand", _lair)]
