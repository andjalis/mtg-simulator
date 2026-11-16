"""#643: protection and hexproof from qualities beyond one colour or one type.

    Protection from each color                     (Iridescent Angel; CR 702.16: from white, blue, black, red and green)
    Protection from legendary creatures            (Tsabo Tavoc)
    Protection from modified creatures             (Louvaq, the Aberrant: equipped, enchanted by an Aura its controller
                                                    controls, or with a counter on it, CR 700.9)
    Hexproof from each color                       (Breaker of Creation)
    Hexproof from planeswalkers / artifacts / creatures / enchantments   (Eradicator Valkyrie, Nevinyrral)
    [Void Shields — ]Protection from mana value 3 or greater / or less   (Mistmeadow Skulk, Reaver Titan: the card's own)

The keyword forms are registered in cards.model.KEYWORDS (cards/__init__.py), so every keyword reader accepts them, and
kw_lines rewrites the comma lists "Protection from blue, from black, and from red" / "Hexproof from artifacts,
creatures, and enchantments" into one keyword per item. "Protection from mana value N ..." is read on the card itself
only (``advanced_rules["protection_mv"]``), so a grant of it stays ignored rather than unchecked.

The rules are the existing ones: ``protected`` is asked by protection_types.protected (so engine.state.protected_from
covers damage, enchanting / equipping, blocking and targeting, DEBT, as for every protection), ``hexproof`` by
cx_mech.hexproof_from (an opponent's spells, and abilities from sources, with that quality can't target it). Each
check costs at most one keyword lookup, and only when the source could have the quality.
"""
from __future__ import annotations

import re

_HEX_TYPES = {"artifacts": "Artifact", "creatures": "Creature", "enchantments": "Enchantment",
              "planeswalkers": "Planeswalker"}
KEYWORDS = frozenset({"protection from each color", "hexproof from each color", "protection from legendary creatures",
                      "protection from modified creatures", "protection from colorless",
                      "protection from spells that are one or more colors"}
                     | {f"hexproof from {w}" for w in _HEX_TYPES})

_MV = re.compile(r"(?:[A-Z][\w' ]* — )?Protection from mana value (\d+) or (greater|less)")


_NON = re.compile(r"Protection from non-([A-Z][a-z]+?)(s| creatures)")


def parse_line(line: str, st) -> bool:
    n = _NON.fullmatch(line.strip())
    if n:
        from .permanent_templates import _SUBTYPE_TYPES
        sub = n[1] if n[2] == " creatures" else _singular(n[1] + "s")
        if sub is None or sub.lower() not in _SUBTYPE_TYPES:
            return False
        st.extra.setdefault("advanced_rules", {})["protection_non"] = (sub, n[2] == " creatures")
        return True
    m = _MV.fullmatch(line.strip())
    if not m:
        return False
    st.extra.setdefault("advanced_rules", {})["protection_mv"] = (int(m[1]), m[2])
    return True


def _modified(perm) -> bool:
    """CR 700.9: equipped, enchanted by an Aura its controller controls, or with a counter on it."""
    return bool(perm.equipment or any(a.controller is perm.controller for a in perm.auras)
                or any(n > 0 for n in perm.counters.values()))


def protected(perm, card, source) -> bool:
    """Whether perm has protection from card (the source's characteristics) for one of these qualities."""
    from .engine.state import Permanent
    mv = perm.card.advanced_rules.get("protection_mv") if perm.card.advanced_rules else None
    if mv and not perm.abilities_suppressed and (card.cmc >= mv[0] if mv[1] == "greater" else card.cmc <= mv[0]):
        return True
    if card.colors and perm.has("protection from each color") or not card.colors and \
            perm.has("protection from colorless"):
        return True
    if not isinstance(source, Permanent) and card.colors and not getattr(card, "is_ability", False) and \
            perm.has("protection from spells that are one or more colors"):
        return True                 # Emrakul, the Aeons Torn: a coloured spell (a card, not a permanent's ability)
    non = perm.card.advanced_rules.get("protection_non") if perm.card.advanced_rules else None
    if non and not perm.abilities_suppressed and (not non[1] or isinstance(source, Permanent) and source.is_creature) \
            and non[0] not in card.subtypes and not (getattr(card, "changeling", False) and card.is_creature):
        return True                 # "protection from non-Spirit creatures" / "from non-Squirrels"
    if isinstance(source, Permanent) and source.is_creature:
        if card.legendary and perm.has("protection from legendary creatures"):
            return True
        if _modified(source) and perm.has("protection from modified creatures"):
            return True
    return False


def hexproof(perm, card) -> bool:
    """Whether perm has hexproof from card's quality (the caller has checked it is an opponent's)."""
    if card.colors and perm.has("hexproof from each color"):
        return True
    return any(t in card.types and perm.has(f"hexproof from {w}") for w, t in _HEX_TYPES.items())


def _singular(plural: str):
    """"Squirrels" -> "Squirrel" (protection_types' plural table, reversed)."""
    from .protection_types import _SUBTYPE_WORDS
    low = plural.lower()
    return next((s.capitalize() for s, p in _SUBTYPE_WORDS.items() if p == low), None)
