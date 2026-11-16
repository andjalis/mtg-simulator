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

from .cx_grammar import Part, ai_value, object_phrase, verb

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


# ---------------------------------------------------------------- "chooses N ..., then sacrifices the rest"
#
#   Each player chooses up to two creatures they control, then sacrifices the rest.        (Covetous Elegy)
#   Each player chooses from among the permanents they control an artifact, a creature, an enchantment, and a land,
#   then sacrifices the rest.                                                              (Cataclysm)
#   Each player sacrifices all lands they control except for three.                        (Keldon Firebombers)
#
# The sentence is rewritten (SUBS) to one private verb, "<players> keepsacrifices <keep> | <scope>", so the chain
# splitter doesn't cut it at ", then". ``cx_keep`` (engine/kinds/cx_grammar_edicts.py): each player keeps the most
# valuable permanents that match (their own interest), one per listed noun or N of one noun, and sacrifices every other
# permanent of the scope at once.

_SUBJ = r"(each player|each opponent|that player|target player|target opponent|defending player)"
_PERMANENT_TYPES = "artifact, creature, enchantment, land, planeswalker, battle"
_BASICS = "plains, island, swamp, mountain, forest"


def _items(text: str) -> str:
    return ", ".join(re.sub(r"^(?:an?|one) ", "", i.strip()) for i in re.split(r",\s*(?:and\s+)?|\s+and\s+", text)
                     if i.strip())


SUBS = [
    (re.compile(rf"\b{_SUBJ} chooses (up to )?(two|three|four|five|six|seven) ([a-z ]+?) they control,? "
                r"(?:then|and) sacrifices the rest", re.I),
     lambda m: f"{m[1]} keepsacrifices {m[2] or ''}{m[3]} {m[4]} | {m[4]}"),
    (re.compile(rf"\b{_SUBJ} chooses from among the (permanents|nonland permanents) they control "
                r"((?:an? [a-z]+, )+and an? [a-z]+), then sacrifices the rest", re.I),
     lambda m: f"{m[1]} keepsacrifices {_items(m[3])} | {m[2]}"),
    (re.compile(rf"\b{_SUBJ} chooses ((?:an? [a-z]+, )+and an? [a-z]+) from among the (permanents|nonland permanents) "
                r"they control, then sacrifices the rest", re.I),
     lambda m: f"{m[1]} keepsacrifices {_items(m[2])} | {m[3]}"),
    (re.compile(rf"\b{_SUBJ} chooses a permanent they control of each permanent type and sacrifices the rest", re.I),
     lambda m: f"{m[1]} keepsacrifices {_PERMANENT_TYPES} | permanents"),
    (re.compile(rf"\b{_SUBJ} chooses from the lands they control a land of each basic land type, then sacrifices "
                r"the rest", re.I),
     lambda m: f"{m[1]} keepsacrifices {_BASICS} | lands"),
    (re.compile(rf"\b{_SUBJ} sacrifices all lands they control except for (two|three|four|five|six|seven)", re.I),
     lambda m: f"{m[1]} keepsacrifices {m[2]} lands | lands"),
]

_SUBTYPE_NOUNS = {"plains": "Plains", "island": "Island", "swamp": "Swamp", "mountain": "Mountain", "forest": "Forest"}


def _noun(word: str):
    """A battlefield group for one singular noun of a keep list ("artifact", "planeswalker", "swamp")."""
    if word.lower() in _SUBTYPE_NOUNS:
        return {"selector": {"subtypes": [word.lower()], "types_all": ["land"]}}
    return _group(word, 1)


@verb(r"keepsacrifices (.+?) \| (.+)", heads=("keepsacrifices",), subjects=("player",))
def keep_sacrifice(m, clause):
    keep_text, scope_text = m[1].strip(), m[2].strip()
    scope = object_phrase("all " + scope_text)
    if clause.duration or scope is None or scope.kind != "group":
        return None
    counted = re.fullmatch(r"(up to )?(two|three|four|five|six|seven) (.+)", keep_text, re.I)
    keep = []
    if counted:
        group = _group(counted[3], _NUM[counted[2].lower()])
        if group is None:
            return None
        keep.append([group, _NUM[counted[2].lower()]])
    else:
        for word in [w.strip() for w in keep_text.split(",") if w.strip()]:
            group = _noun(word)
            if group is None:
                return None
            keep.append([group, 1])
    return [Part("cx_keep", data={"keep": keep, "scope": scope.group})]


@ai_value("cx_keep")
def _keep_value(game, me, eff, obj):
    """What that player would sacrifice (everything of the scope but its most valuable keeps), signed by who loses it."""
    from .cx_grammar import group_members
    from .engine.policy import perm_value
    from .engine.state import Player
    if not isinstance(obj, Player):
        return 0.0
    scope = group_members(game, obj, {"group": eff.data["scope"]}, None, obj)
    kept: list = []
    for group, n in sorted(eff.data["keep"], key=lambda k: len(group_members(game, obj, {"group": k[0]}, None, obj))):
        free = sorted((x for x in group_members(game, obj, {"group": group}, None, obj) if x not in kept),
                      key=perm_value, reverse=True)
        kept += free[:n]
    lost = sum(perm_value(x) for x in scope if x not in kept)
    return lost if obj is not me else -lost


# ---------------------------------------------------------------- "half the creatures they control, rounded up"

_FRACTIONS = {"half": (1, 2), "a third of": (1, 3), "a tenth of": (1, 10)}


@verb(r"sacrifices? (half|a third of|a tenth of) the (.+?) (?:they|that player) controls?, rounded (up|down)",
      heads=("sacrifice", "sacrifices"), subjects=("player",))
def sacrifice_fraction(m, clause):
    """"Each opponent sacrifices half the creatures they control, rounded up": the count is that player's own,
    worked out when the edict resolves (the cx_edict handler)."""
    noun = m[2]
    if clause.duration or _BAD.search(noun) or not _plural_ok(noun, 2):
        return None
    group = _group(noun, 2)
    if group is None:
        return None
    num, den = _FRACTIONS[m[1].lower()]
    return [Part("cx_edict", 0, data={"noun": group, "scales": False, "fraction": [num, den, m[3].lower() == "up"]})]


# "<players> sacrifice X <nouns>" is not read: X there is often not the mana X the grammar wrapper hands over (an
# additional cost's X, a trigger's X, a number the player chooses: Devastating Dreams, Gluttonous Hellkite,
# Campsite Cuisine), so a reading would sacrifice nothing.
