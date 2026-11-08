"""The group word of an anthem or keyword grant ("Green creatures you control get +1/+1", "Elves you control get
+1/+1", "Attacking creatures you control get +1/+0", "Artifact creatures you control get +1/+1"), as an
``anthem_sub`` / ``keyword_sub`` tag:

    a creature subtype ("Elf", from "Elves")   "color:G"   "type:Artifact"   "Token"   "Face-down"
    "is:attacking", "is:untapped", "is:equipped", "is:legendary", "is:nonlegendary", "is:multicolored", "is:colorless"

``tag`` returns None for a word that is none of these, so the line stays unparsed instead of naming a subtype that
doesn't exist. ``fits`` is the engine side (``Permanent._pt_bonus``).
"""
from __future__ import annotations

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_TYPES = {"artifact": "Artifact", "enchantment": "Enchantment", "land": "Land"}
_STATES = ("attacking", "untapped", "equipped", "legendary", "nonlegendary", "multicolored", "colorless")
_COMBAT_STEPS = ("declare_attackers", "declare_blockers", "combat_damage", "end_combat")
_IRREGULAR = {"elves": "Elf", "dwarves": "Dwarf", "wolves": "Wolf", "werewolves": "Werewolf", "mice": "Mouse",
              "allies": "Ally", "armies": "Army", "heroes": "Hero", "fungi": "Fungus", "faeries": "Faerie",
              "zombies": "Zombie", "merfolk": "Merfolk", "sphinxes": "Sphinx", "foxes": "Fox", "lynxes": "Lynx",
              "mercenaries": "Mercenary", "harpies": "Harpy", "pegasi": "Pegasus"}


def _subtype(word: str, plural: bool):
    from .permanent_templates import _CREATURE_SUBTYPES
    low = word.lower()
    if low in _IRREGULAR:
        name = _IRREGULAR[low]
    elif plural and low.endswith("ies"):
        name = word[:-3] + "y"
    elif plural and low.endswith("s") and not low.endswith("ss"):
        name = word[:-1]
    else:
        name = word
    return name if name.lower() in {s.lower() for s in _CREATURE_SUBTYPES} else None


def tag(word: str, plural: bool = False, subtype_only: bool = False):
    """The tag for one group word, or None. plural: the word is the noun itself ("Elves"), not an adjective."""
    low = word.lower()
    if not subtype_only:
        if low in _COLORS:
            return "color:" + _COLORS[low]
        if low in _TYPES:
            return "type:" + _TYPES[low]
        if low in _STATES:
            return "is:" + low
        if low == "face-down":
            return "Face-down"        # face-down permanents (manifest, morph): fits reads Permanent.hidden
    return _subtype(word, plural)


def fits(perm, sub: str) -> bool:
    card = perm.card
    if sub == "Token":
        return bool(card.is_token)
    if sub == "Face-down":
        return getattr(perm, "hidden", None) is not None
    if sub.startswith("color:"):
        return sub[6:] in card.colors
    if sub.startswith("type:"):
        return sub[5:] in card.types
    if sub.startswith("is:"):
        state = sub[3:]
        if state == "attacking":
            game = getattr(perm.controller, "_game", None)       # attackers stay listed after combat: CR 506.4
            return game is not None and game.step in _COMBAT_STEPS and perm in game.attackers
        if state == "untapped":
            return not perm.tapped
        if state == "equipped":
            return bool(perm.equipment)
        if state in ("legendary", "nonlegendary"):
            return bool(card.legendary) == (state == "legendary")
        if state == "multicolored":
            return len(card.colors) >= 2
        if state == "colorless":
            return not card.colors
        return False
    return sub in card.subtypes
