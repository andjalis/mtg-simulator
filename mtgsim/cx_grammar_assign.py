"""Grammar verb (#313): "assigns combat damage equal to its toughness / mana value rather than its power".

    ~ assigns combat damage equal to its toughness rather than its power.                     (Streetwise Negotiator)
    Enchanted creature gets +0/+2 and assigns combat damage equal to its toughness rather than its power.
    Each creature you control with toughness greater than its power assigns combat damage equal to its toughness
    rather than its power.                                                                     (Ancient Lumberknot)
    Until end of turn, target creature you control assigns combat damage equal to its toughness rather than its power.
    Each creature assigns combat damage equal to its mana value rather than its power.        (Narod, the Beige Flower)

The family rule ``cx_dmg_stat`` (value "toughness" or "mana value") is a static on ~, the host or a group, or a
one-shot for this turn; ``cx_night_aura.dmg_stat`` (asked by combat damage) reads it through
``cx_grammar.static_rules`` for the creature as damage is assigned. Only the amount changes: the creature still
deals the damage, so its lifelink, deathtouch, trample and first strike work as usual. See mtgsim/GRAMMAR.md."""
from __future__ import annotations

from .cx_grammar import Part, verb


@verb(r"assigns? combat damage equal to (?:its|their) (toughness|mana value) rather than (?:its|their) power",
      heads=("assign", "assigns"), subjects=("permanent", "group", "host"))
def assigns(m, clause):
    value = m[1].lower()
    if clause.duration == "static":
        return [Part("cx_static", data={"rule": "cx_dmg_stat", "value": value})]
    if clause.duration in ("eot", "turn") and clause.subject.kind != "host":
        return [Part("cx_rule_turn", data={"rule": "cx_dmg_stat", "value": value, "side": "mine"})]
    return None
