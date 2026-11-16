"""Protection from a card type or a subtype (#326): "protection from Demons and from Dragons" (Baneslayer Angel),
"protection from instants and from sorceries" (Sword of Wealth and Power), "protection from planeswalkers and from
Wizards" (Greensleeves), "protection from Spirits and from Arcane" (Kitsune Riftwalker), "protection from creatures".

The keywords are registered in cards.model.KEYWORDS (lower case, the plural as printed), so every keyword reader
(keyword lines, "has ...", "gains ... until end of turn", equipment bonuses) accepts them. The rules themselves are
engine.state.protected_from's: a permanent with protection from a quality can't be dealt damage, enchanted / equipped,
blocked or targeted by anything with that quality (DEBT). ``protected`` answers the type part of that question for a
source's card: its card types ("instants", "creatures") and subtypes ("Demons", "Arcane"); a changeling source has
every creature type.
"""
from __future__ import annotations

from .permanent_templates import _CREATURE_SUBTYPES

_TYPES = {"Creature": "creatures", "Instant": "instants", "Sorcery": "sorceries", "Planeswalker": "planeswalkers",
          "Enchantment": "enchantments", "Land": "lands"}          # "artifacts" is an older keyword with its own check
_SPELL_SUBTYPES = {"arcane": "arcane"}
_IRREGULAR = {"elf": "elves", "dwarf": "dwarves", "wolf": "wolves", "werewolf": "werewolves", "fungus": "fungi",
              "mouse": "mice", "ally": "allies", "faerie": "faeries", "sphinx": "sphinxes", "fox": "foxes",
              "thief": "thieves", "leech": "leeches", "octopus": "octopuses", "samurai": "samurai",
              "merfolk": "merfolk", "kithkin": "kithkin", "myr": "myr", "eldrazi": "eldrazi", "moonfolk": "moonfolk",
              "vedalken": "vedalken", "kor": "kor", "viashino": "viashino", "cyclops": "cyclopes", "ox": "oxen",
              "dryad": "dryads", "harpy": "harpies", "fish": "fish", "sheep": "sheep", "elk": "elk",
              "jellyfish": "jellyfish", "homunculus": "homunculi", "lammasu": "lammasu", "manticore": "manticores",
              "pegasus": "pegasi", "nephilim": "nephilim", "aetherborn": "aetherborn", "azra": "azra",
              "kavu": "kavu", "noggle": "noggles", "ouphe": "ouphes", "sliver": "slivers", "zubera": "zubera",
              "orochi": "orochi", "ninja": "ninjas", "djinn": "djinn", "efreet": "efreets"}


def _plural(sub: str) -> str:
    if sub in _IRREGULAR:
        return _IRREGULAR[sub]
    if sub.endswith(("s", "x", "ch", "sh")):
        return sub + "es"
    if sub.endswith("y") and sub[-2:-1] not in "aeiou":
        return sub[:-1] + "ies"
    return sub + "s"


_SUBTYPE_WORDS = {s: _plural(s) for s in _CREATURE_SUBTYPES}
KEYWORDS = frozenset({f"protection from {w}" for w in _TYPES.values()}
                     | {f"protection from {w}" for w in _SUBTYPE_WORDS.values()}
                     | {f"protection from {w}" for w in _SPELL_SUBTYPES.values()})


def protected(perm, card, source) -> bool:
    """Whether perm has protection from one of card's types or subtypes."""
    from .engine.state import Permanent
    words = [_TYPES[t] for t in card.types if t in _TYPES]
    if "creatures" in words and not (isinstance(source, Permanent) and source.is_creature):
        words.remove("creatures")       # the older keyword's rule: creatures on the battlefield (Holy Mantle)
    subs = {s.lower() for s in card.subtypes}
    if getattr(card, "changeling", False):
        subs |= set(_CREATURE_SUBTYPES)
    words += [_SUBTYPE_WORDS[s] for s in subs if s in _SUBTYPE_WORDS]
    words += [_SPELL_SUBTYPES[s] for s in subs if s in _SPELL_SUBTYPES]
    from .protection_qualities import protected as by_quality       # each color, legendary / modified creatures (#643)
    return any(perm.has(f"protection from {w}") for w in words) or by_quality(perm, card, source)
