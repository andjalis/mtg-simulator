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

A qualified single target the grammar's object reader understands ("target Cleric or Wizard creature", "target
green creature") becomes ``prevent_next`` on a creature with that selector. "Dealt by ~" (Barbed Wire) and "the next
N combat damage" (Decorated Griffin) pick out the damage's source or kind, which a shield on the recipient cannot
express: they become cx_shields rules with a budget instead. "By a source of your choice" (Healing Grace) is still
refused. "Any number of targets,
divided as you choose" (Embolden) and granted abilities (Cautery Sliver) are separate mechanics and also stay
unmatched.
"""
from __future__ import annotations

import dataclasses
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


# Any other single "target <qualified> creature" the grammar's object reader understands ("target Cleric or Wizard
# creature", "target green creature"): target "creature" with that selector / description (#333).
_QUALIFIED = (r"prevent the next (?P<n>\d+|x) damage that would be dealt(?: to target (?P<d>[\w' -]+? creature) this turn"
              r"| this turn to target (?P<d2>[\w' -]+? creature))")


def _qualified(m):
    from .cards import Effect, NO_MATCH
    from .cx_grammar import object_phrase
    obj = object_phrase("target " + (m["d"] or m["d2"]))
    if obj is None or obj.kind != "permanent" or obj.target != "permanent" or obj.copies != 1 \
            or not obj.data or set(obj.data) - {"selector", "cx_desc"}:
        return NO_MATCH
    spec = obj.data.get("selector")
    if spec is not None and ("creature" not in spec.get("types_all", ()) or spec.get("other")):
        return NO_MATCH
    n = m["n"]
    data = dict(obj.data, **({"x": True} if n.lower() == "x" else {}))
    return Effect("prevent_next", 0 if n.lower() == "x" else int(n), target="creature", data=data)


def _budget_shield(combat, to, by):
    """"Prevent the next N combat damage that would be dealt to you this turn" (Decorated Griffin), "Prevent the next
    N damage that would be dealt by ~ this turn" (Barbed Wire): a cx_shields rule with a budget, which filters on
    combat and on the damage's source, so neither needs a shield on the recipient (#333)."""
    def make(m):
        from .cards import Effect
        rule = {"combat": combat, "to": to, "by": by, "budget": int(m["n"])}
        return Effect("cx_shield", target="none", data={"rule": rule, "side": "mine"})
    return make


EFFECT_PATTERNS = [
    (_NEXT, _shield),
    (_QUALIFIED, _qualified),
    (r"prevent the next (?P<n>\d+) combat damage that would be dealt to you this turn", _budget_shield(True, ("you",),
                                                                                                    ("any",))),
    (r"prevent the next (?P<n>\d+) combat damage that would be dealt to ~ this turn", _budget_shield(True, ("self",),
                                                                                                  ("any",))),
    (r"prevent the next (?P<n>\d+) damage that would be dealt by ~ this turn", _budget_shield(None, ("any",),
                                                                                           ("self",))),
]


# ---------------------------------------------------------------- "instead" riders on a shield (#333)
# The shield side only: a different amount for the same shield, chosen by what it landed on or by the kicker. General
# replacement / "instead" machinery stays with cards.parse._kicker_instead and cx_grammar_cond.

_INSTEAD_IF = re.compile(r"if it's an? ([\w' -]+?), prevent the next (\d+) damage instead\.?", re.I)


def parse_rider(sentence: str, effects: list) -> bool:
    """"If it's a green creature, prevent the next 2 damage instead." right after a targeted prevent_next (Elvish
    Healer): the shield is that amount when its recipient fits the description as it resolves."""
    m = _INSTEAD_IF.fullmatch(sentence.strip())
    if not m or not effects or effects[-1].kind != "prevent_next" or effects[-1].target not in ("any", "creature") \
            or effects[-1].data.get("instead"):
        return False
    from .cx_grammar import object_phrase
    obj = object_phrase("target " + m[1])
    if obj is None or obj.kind != "permanent" or obj.target != "permanent" or obj.copies != 1 or not obj.data \
            or set(obj.data) - {"selector", "cx_desc"}:
        return False
    last = effects[-1]
    effects[-1] = dataclasses.replace(last, data=dict(last.data, instead={"if": dict(obj.data), "amount": int(m[2])}))
    return True


def kicked_instead(kicked_effects: list, text: str) -> bool:
    """"If this spell was kicked, prevent the next 4 damage that would be dealt to that permanent or player this turn
    instead." (Orim's Touch): the kicked copy's shield is that amount."""
    m = re.fullmatch(r"prevent the next (\d+) damage that would be dealt to (?:that permanent or player|that creature|"
                     r"that player|it) this turn instead\.?", text.strip(), re.I)
    shields = [e for e in kicked_effects if e.kind == "prevent_next" and e.target in ("any", "creature", "player")]
    if not m or len(shields) != 1:
        return False
    shields[0].amount = int(m[1])
    return True


def instead_amount(game, p, eff, who) -> int:
    """The shield prevent_next puts on who: the rider's amount when who fits its description."""
    rider = eff.data.get("instead")
    if not rider:
        return eff.amount
    from .engine.state import Permanent
    if not isinstance(who, Permanent):
        return eff.amount
    probe = dataclasses.replace(eff, data=dict(rider["if"]))
    return rider["amount"] if game.passes_filter(probe, who, p) and _types_ok(who, rider["if"]) else eff.amount


def _types_ok(perm, spec) -> bool:
    """passes_filter checks a selector's extra constraints; its card types are the target kind's job, done here."""
    types = (spec.get("selector") or {}).get("types_all", ())
    return all(t.capitalize() in perm.card.types for t in types if t != "permanent")
