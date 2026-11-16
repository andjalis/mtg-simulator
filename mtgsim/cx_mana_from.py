"""Mana from certain sources only (#644):

    Spend only mana produced by basic lands to cast this spell.                 (Imperiosaur)
    Spend only mana produced by creatures to cast this spell.                   (Myr Superion)

``parse_line`` sets ``advanced_rules["mana_from"]`` ("basic_land" / "creature"); ``source_ok`` is checked in
``Game.mana_sources`` for that spell, so only those permanents' mana is offered for it, both when it is paid and when
the AI plans the cast. Mana already in the pool is refused for it (the pool doesn't record where it came from), and so
are stored mana and other sources (Treasures, rituals).
"""
from __future__ import annotations

import re

_LINE = re.compile(r"Spend only mana produced by (basic lands|creatures) to cast (?:this spell|~)\.", re.I)
_KIND = {"basic lands": "basic_land", "creatures": "creature"}


def parse_line(line: str, st) -> bool:
    m = _LINE.fullmatch(line)
    if not m:
        return False
    st.extra.setdefault("advanced_rules", {})["mana_from"] = _KIND[m[1].lower()]
    return True


def restriction(spell):
    """The spell's "mana_from" kind, or None."""
    rules = getattr(spell, "advanced_rules", None)
    return rules.get("mana_from") if rules else None


def source_ok(kind: str, perm) -> bool:
    from .engine.state import is_basic_land
    if kind == "basic_land":
        return perm.card.is_land and is_basic_land(perm.card)
    return perm.is_creature
