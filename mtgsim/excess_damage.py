"""Excess damage (rule 120.4a): "~ deals 5 damage to target creature. Excess damage is dealt to that creature's
controller instead." (Flame Spill, Pigment Storm, Gandalf's Sanction). The damage beyond lethal (the creature's
toughness minus the damage already marked on it; 1 from a deathtouch source) goes to its controller instead."""
import dataclasses
import re

_RIDER = re.compile(r"(?P<trample>if the creature you control has trample, )?"
                    r"excess damage is dealt to (?:that creature's|its) controller instead\.?", re.I)


def parse(sentence: str, effects: list) -> bool:
    """The parse hook: mark the preceding single-creature damage effect, or a creature's "deals damage equal to its
    power to <creature>" (bite: Ravenous Tyrannosaurus; only if it has trample: Ram Through), or return False."""
    m = _RIDER.fullmatch(sentence.strip())
    if not m or not effects:
        return False
    last = effects[-1]
    if last.data.get("excess"):
        return False
    if m["trample"]:
        if last.kind != "bite":
            return False
        excess = "trample"
    elif last.kind == "damage" and last.target == "creature" or last.kind == "bite" and last.target == "creature":
        excess = "controller"
    else:
        return False
    effects[-1] = dataclasses.replace(last, data=dict(last.data, excess=excess))
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
