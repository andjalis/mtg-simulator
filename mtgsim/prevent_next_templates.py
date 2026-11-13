"""Recipient shields: "Prevent the next N damage that would be dealt to <who> this turn" (#333 family).

cards/patterns.py already parses the plain recipients with a literal amount ("any target", "target
creature", "target player", "~", "you"). This module adds the remaining recipient selectors — a qualified
target ("target artifact creature", "target legendary creature", "target creature you control"), the bound
"it" of an ability's own source (Balduvian Hydra), "enchanted creature" (Fylgja's host), and the "each ..."
plurals (Kitsune Palliator, Samite Censer-Bearer) — plus the X-sized amounts (Alabaster Potion's mode,
Panacea, Festival of the Guildpact), where X is the X paid for the spell or ability (data ``x``; resolve's
shared amount rules size it from ``item.x``).

Everything becomes the existing ``prevent_next`` effect: the kind handler adds the shield to the recipient
(engine/kinds/stats.py), Game.deal_damage consumes it, the cleanup step expires it, and the damage_prevented
event carries the prevented amount for "... this way" riders.

Source filters are deliberately refused: "dealt by ~" (Barbed Wire) or "by a source of your choice" (Healing
Grace) pick out the damage's source, which a shield on the recipient cannot express. "Any number of targets,
divided as you choose" (Embolden) and granted abilities (Cautery Sliver) are separate mechanics and also stay
unmatched.
"""
from __future__ import annotations

import re

# (oracle phrase, target kind, extra effect data) — longest phrases first so the alternation prefers them.
_RECIPIENTS = [
    ("each creature and each player", "each_creature_and_player", {}),
    ("each creature you control", "each_creature", {"selector": {"types_all": ["creature"], "controller": "mine"}}),
    ("target artifact creature", "creature", {"selector": {"types_all": ["artifact", "creature"]}}),
    ("target legendary creature", "creature", {"selector": {"types_all": ["creature"], "traits": ["legendary"]}}),
    ("target creature you control", "creature_mine", {}),
    ("enchanted creature", "host", {}),
    ("target creature", "creature", {}),
    ("target player", "player", {}),
    ("any target", "any", {}),
    ("~", "self", {}),
    ("it", "self", {}),
    ("you", "none", {}),
]
_ALT = "|".join(re.escape(text) for text, _, _ in _RECIPIENTS)
# Both word orders: "dealt to <who> this turn" and "dealt this turn to <who>" (Samite Alchemist).
_NEXT = rf"prevent the next (?P<n>\d+|x) damage that would be dealt(?: to (?P<to>{_ALT}) this turn| this turn to (?P<to2>{_ALT}))"


def _shield(m):
    from .cards import Effect, NO_MATCH
    n = m["n"]
    amount = 0 if n.lower() == "x" else int(n)
    data = {"x": True} if n.lower() == "x" else {}
    phrase = (m["to"] or m["to2"] or "").lower()
    for text, kind, extra in _RECIPIENTS:
        if text == phrase:
            break
    else:
        return NO_MATCH
    if kind == "each_creature_and_player":      # Kitsune Palliator: one shield per creature and per player
        return [Effect("prevent_next", amount, target="each_creature", data=dict(data)),
                Effect("prevent_next", amount, target="each_player", data=dict(data))]
    return Effect("prevent_next", amount, target=kind, data=dict(data, **extra))


EFFECT_PATTERNS = [
    (_NEXT, _shield),
]
