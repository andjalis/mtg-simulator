"""Effect wordings common on activated abilities, mapped onto existing effect kinds.

    Switch ~'s power and toughness until end of turn.          (switch_pt on the source)
    Target creature doesn't untap during its controller's next untap step.
    Add three mana of any one color.                           (Black Lotus)
    ~ deals damage equal to its power to target creature.      It deals damage equal to its power to target creature.
    Put ~ on top of its owner's library.     Exile enchanted creature.     Exile target creature card from a graveyard.
"""
from __future__ import annotations

_NUMS = {"two": 2, "three": 3, "four": 4, "five": 5}


def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


def _any_one_color(m):
    return _effect("add_mana", _NUMS[m["n"].lower()], data={"colors": [], "choice": ["W", "U", "B", "R", "G"]})


EFFECT_PATTERNS = [
    (r"switch ~'s power and toughness until end of turn", lambda m: _effect("switch_pt", target="self")),
    (r"target creature doesn't untap during its controller's next untap step",
     lambda m: _effect("skip_untap", target="creature")),
    (r"add (?P<n>two|three|four|five) mana of any one color", _any_one_color),
    (r"(?:~|it) deals damage equal to its power to target creature",
     lambda m: _effect("damage", target="creature", data={"source_power": True})),
    (r"put ~ on top of its owner's library", lambda m: _effect("tuck_top", target="self")),
    (r"exile enchanted creature", lambda m: _effect("exile_permanent", target="host")),
    (r"exile target creature card from a graveyard", lambda m: _effect("exile_gy", 1)),
]
