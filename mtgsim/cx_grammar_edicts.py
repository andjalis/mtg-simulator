"""Grammar verbs: edicts the plain "sacrifices N <noun>" verb (cx_grammar_zones) doesn't read (#631).

    Target opponent sacrifices a creature with the greatest power among creatures they control.   (Consumed by Greed)
    Each opponent sacrifices a creature or planeswalker with the greatest mana value among creatures and
    planeswalkers they control.                                                                    (Soul Shatter)
    Defending player sacrifices a creature with the least power among creatures they control.     (Witch-king)
    Target player sacrifices an artifact and a land.                                               (Structural Collapse)
    Each player sacrifices an artifact, a creature, an enchantment, a land, and a planeswalker.   (Catch // Release)
    Each player sacrifices six creatures.                                                          (Necrotic Hex)

All of them are ``cx_edict`` (the sacrificing player picks, the least valuable first, which is that player's own
interest; the controller of the effect never chooses for them):
- "with the greatest / least <stat> among <the same noun> they control": ``data["extreme"] = (stat, "max"|"min")``;
  the sacrificing player picks among the permanents tied for that value (engine/kinds/cx_grammar_zones.edict).
- a list "an X and a Y" / "an X, a Y, and a Z": one cx_edict per item, in order (each an earlier pick can't satisfy
  again: it is gone).
- counts six to ten (the plain verb reads up to five).
This module sorts before cx_grammar_zones, so its parsers are tried first; anything else falls through to it.
"""
from __future__ import annotations

import re

from .cx_grammar import Part, object_phrase, verb

_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
        "nine": 9, "ten": 10}
_STATS = {"power": "power", "toughness": "toughness", "mana value": "mana value"}
_BAD = re.compile(r"\b(?:you|other|than|named|until|unless|if|instead|card|cards|from|then|for each|that|"
                  r"of their choice|this turn|attacked|blocked)\b", re.I)


def _group(noun: str, n: int):
    obj = object_phrase(("each " if n == 1 else "all ") + noun)
    return obj.group if obj is not None and obj.kind == "group" else None


def _plural_ok(noun: str, n: int) -> bool:
    plural = bool(re.fullmatch(r".*s", noun)) and not re.fullmatch(r".*(?:ss)", noun)
    return plural == (n > 1)


@verb(r"sacrifices? (a|an|one) (.+?) with the (greatest|least) (power|toughness|mana value) among (.+?) "
      r"(?:they|that player|he or she) controls?", heads=("sacrifice", "sacrifices"), subjects=("player",))
def sacrifice_extreme(m, clause):
    noun, among = m[2], m[5]
    if clause.duration or _BAD.search(noun) or _BAD.search(among):
        return None
    group = _group(noun, 1)
    # "among creatures and planeswalkers they control": the set of either type, as "creatures or planeswalkers"
    among_group = object_phrase("all " + re.sub(r"^(\w+) and (\w+)$", r"\1 or \2", among))
    if group is None or among_group is None or among_group.kind != "group" or among_group.group != group:
        return None             # "a creature with the greatest power among creatures": the same set both times
    return [Part("cx_edict", 1, data={"noun": group, "scales": False,
                                      "extreme": [_STATS[m[4].lower()], "max" if m[3].lower() == "greatest" else "min"]})]


@verb(r"sacrifices? ((?:an?|one) [\w -]+?(?:, (?:an?|one) [\w -]+?)*,? and (?:an?|one) [\w -]+?)",
      heads=("sacrifice", "sacrifices"), subjects=("player",))
def sacrifice_list(m, clause):
    if clause.duration or _BAD.search(m[1]):
        return None
    items = [i.strip() for i in re.split(r",\s*(?:and\s+)?|\s+and\s+", m[1]) if i.strip()]
    parts = []
    for item in items:
        im = re.fullmatch(r"(?:an?|one) (.+)", item)
        if im is None or not _plural_ok(im[1], 1):
            return None
        group = _group(im[1], 1)
        if group is None:
            return None
        parts.append(Part("cx_edict", 1, data={"noun": group, "scales": False}))
    return parts if len(parts) >= 2 else None


@verb(r"sacrifices? (six|seven|eight|nine|ten) (.+)", heads=("sacrifice", "sacrifices"), subjects=("player",))
def sacrifice_many(m, clause):
    n, noun = _NUM[m[1].lower()], m[2]
    if clause.duration or _BAD.search(noun) or not _plural_ok(noun, n):
        return None
    group = _group(noun, n)
    return [Part("cx_edict", n, data={"noun": group, "scales": True})] if group else None
