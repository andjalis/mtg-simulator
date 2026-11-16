"""Excess damage (rule 120.4a): "~ deals 5 damage to target creature. Excess damage is dealt to that creature's
controller instead." (Flame Spill, Pigment Storm, Gandalf's Sanction). The damage beyond lethal (the creature's
toughness minus the damage already marked on it; 1 from a deathtouch source) goes to its controller instead."""
import dataclasses
import re

_RIDER = re.compile(r"excess damage is dealt to (?:that creature's|its) controller instead\.?", re.I)


def parse(sentence: str, effects: list) -> bool:
    """The parse hook: mark the preceding single-creature damage effect, or return False."""
    if not _RIDER.fullmatch(sentence.strip()) or not effects:
        return False
    last = effects[-1]
    if last.kind != "damage" or last.target != "creature" or last.data.get("excess"):
        return False
    effects[-1] = dataclasses.replace(last, data=dict(last.data, excess="controller"))
    return True


def lethal(perm, source) -> int:
    """The damage still lethal to perm (rule 120.4a): a deathtouch source needs 1."""
    left = max(0, perm.toughness - perm.damage)
    deathtouch = getattr(source, "has", None) and source.has("deathtouch") or \
        "deathtouch" in getattr(source, "keywords", ())
    return min(left, 1) if deathtouch else left


def split(perm, amount: int, source) -> tuple:
    """(damage to the creature, excess for its controller)."""
    to_creature = min(amount, lethal(perm, source))
    return to_creature, amount - to_creature
