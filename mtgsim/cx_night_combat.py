"""Self-referential combat riders: "you may untap it and remove it from combat" and "you may have it deal N damage to
any target" (Gustcloak Harrier / Runner / Sentinel, Goblin Arsonist, Jund Sojourners, Karplusan Wolverine).

Both are optional in the text and always taken here: removing a blocked creature from combat is a free dodge, and the
damage has no drawback. ``remove_from_combat`` (engine/kinds/cx_night_combat.py) keeps the attacker "blocked" with no
blockers left, so it neither hits the player nor takes damage."""
from __future__ import annotations


def _remove(m):
    from .cards.model import Effect
    return Effect("remove_from_combat", target="self")


def _damage(m):
    from .cards.model import Effect
    return Effect("damage", int(m[1]), target="any")


def _power_to_opponents(m):
    from .cards.model import Effect
    return Effect("damage_power_opp", target="none")


EFFECT_PATTERNS = [
    # Heartfire Hero, Flaming Tyrannosaurus: "When ~ dies, it deals damage equal to its power to each opponent."
    (r"(?:it|~) deals damage equal to its power to each opponent", _power_to_opponents),
    (r"(?:it|~) deals damage to each opponent equal to its power", _power_to_opponents),
    (r"you may untap it and remove it from combat", _remove),
    (r"you may have it deal (\d+) damage to any target", _damage),
]
