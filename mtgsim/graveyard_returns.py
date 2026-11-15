"""Dies, exile the dead source, then return other graveyard cards (#508).

The whole trigger is read together: an unrelated "exile it" must not be
interpreted as exiling a dead source. Targets are chosen when the trigger is
stacked; random/top-card choices happen after the source is exiled.
"""
from __future__ import annotations

import dataclasses
import re


def _repeated_subtypes(m):
    from .cards import Effect, NO_MATCH
    from .permanent_templates import _CREATURE_SUBTYPES
    types = [m[1].lower()] + re.split(r",? and |, ", m[2].lower())
    if len(types) < 2 or any(t not in _CREATURE_SUBTYPES for t in types):
        return NO_MATCH
    return Effect("gy_return_each_subtype", data={"subtypes": types})


EFFECT_PATTERNS = [
    (r"return a ([a-z]+) card from your graveyard to your hand, then do the same for (.+)",
     _repeated_subtypes),
    (r"return any number of cards with different mana values from your graveyard to your hand",
     lambda m: _distinct_values()),
    (r"return target equipment card from your graveyard to the battlefield attached to ~",
     lambda m: _attached_equipment()),
    (r"return up to three target creature cards with total mana value (\d+) or less from your graveyard to the battlefield",
     lambda m: _budget_returns(int(m[1]), 3)),
    (r"return any number of target ally creature cards with total mana value (\d+) or less from your graveyard to the battlefield",
     lambda m: _budget_returns(int(m[1]), None, "ally")),
]


def _distinct_values():
    from .cards import Effect
    return Effect("gy_return_distinct_mana_values")


def _attached_equipment():
    from .cards import Effect
    return Effect("gy_return_equipment_to_source", target="graveyard_card",
                  data={"cx_card": {"types": [], "subtypes_exact": ["equipment"]},
                        "zone": "you", "side": "mine"})


def spree_return_mode(text):
    """Recognize targeted graveyard-return modes without losing target timing."""
    from .cards import Effect
    creature = re.fullmatch(r"Return target creature card from your graveyard to the battlefield\.", text, re.I)
    vehicles = re.fullmatch(r"Return target Mount or Vehicle card from your graveyard to the battlefield\.", text, re.I)
    attached = re.fullmatch(r"Return target Aura or Equipment card from your graveyard to the battlefield "
                            r"attached to a creature you control\.", text, re.I)
    if not (creature or vehicles or attached):
        return None
    spec = ({"types": ["creature"]} if creature else
            {"types": [], "subtypes_any": ["mount", "vehicle"]} if vehicles else
            {"types": [], "subtypes_exact": ["aura", "equipment"]})
    data = {"cx_card": spec, "zone": "you", "side": "mine"}
    if attached:
        return [Effect("gy_return_attachment_choice", target="graveyard_card", data=data)]
    data.update(to="battlefield", under="you")
    return [Effect("cx_card_move", target="graveyard_card", data=data)]


def _budget_returns(limit, maximum, subtype=None):
    from .cards import Effect
    spec = {"types": ["creature"]}
    if subtype:
        spec["subtypes_any"] = [subtype]
    probe = Effect("gy_budget_probe", target="graveyard_card",
                   data={"cx_card": spec, "zone": "you", "side": "mine"})
    return Effect("gy_budget_return", target="multi", data={"probe": probe, "budget": limit, "cap": maximum})


def budget_legal(eff, targets):
    cap = eff.data["cap"]
    return (cap is None or len(targets) <= cap) and sum(c.cmc for c in targets) <= eff.data["budget"]


def budget_choose(game, player, eff):
    pool = sorted(game.legal_targets(player, eff.data["probe"]), key=lambda c: c.cmc, reverse=True)
    picks = []
    for candidate in pool:
        if budget_legal(eff, picks + [candidate]):
            picks.append(candidate)
    return tuple(picks)


def budget_member_legal(game, player, eff, member):
    refs = eff.data.get("graveyard_refs", {})
    ref = refs.get(id(member))
    return (ref is None or ref[0].find(ref[1]) is member) and game.legal_target(player, eff.data["probe"], member)


def _noun(text):
    from .cx_grammar_zones import card_noun
    from .permanent_templates import _CREATURE_SUBTYPES
    spec = card_noun(text)
    if spec is not None:
        return spec
    m = re.fullmatch(r"([a-z]+(?: and/or [a-z]+)*) (permanent|creature) cards?", text)
    if m is None:
        return None
    subtypes = m[1].split(" and/or ")
    if not all(t in _CREATURE_SUBTYPES for t in subtypes):
        return None
    return {"types": [m[2]], "subtypes_any": subtypes}


def _return_effects(text):
    from .cards.model import Effect
    m = re.fullmatch(r"return (?:(up to) (one|two|three) )?(another )?target (.+?) "
                     r"from your graveyard to (your hand|the battlefield)", text)
    if m:
        spec = _noun(m[4])
        n = {"one": 1, "two": 2, "three": 3}.get(m[2], 1)
        if spec is None or (n > 1) != m[4].endswith("cards"):
            return None
        if m[5] == "the battlefield" and (not spec["types"] or
                                           any(t in ("instant", "sorcery") for t in spec["types"])):
            return None
        data = {"cx_card": spec, "zone": "you", "side": "mine", "other": bool(m[3]),
                "to": "hand" if m[5] == "your hand" else "battlefield"}
        if m[1]:
            data["optional_target"] = True
        if n > 1:
            data.update(distinct=True, group="dies_return")
        # Mark legal targets first, then execute their one simultaneous return
        # instruction. A final untargeted effect also runs if the last slot is illegal.
        return [Effect("gy_return_mark", target="graveyard_card", data=dict(data)) for _ in range(n)] + [
            Effect("gy_return_finish")]
    m = re.fullmatch(r"return (one|two|three) creature cards? at random from your graveyard to the battlefield", text)
    if m:
        n = {"one": 1, "two": 2, "three": 3}[m[1]]
        if (n > 1) != ("creature cards " in text):
            return None
        return [Effect("gy_return_random", n)]
    if text == "return the top creature card of your graveyard to the battlefield":
        return [Effect("gy_return_top")]
    return None


def face_line(st, line):
    from .cards.model import Effect, Trigger
    m = re.fullmatch(r"When ~ dies, exile it(?:, then| and) (return .+)\.", line)
    if m is None:
        return line
    effects = _return_effects(m[1].lower())
    if effects is None:
        return line
    st.triggers.append(Trigger("dies", [Effect("exile_dead_source")] + effects))
    return None


def bind_death(effects, source):
    """Freeze the just-dead object before opponents get priority (even before flush)."""
    if not any(e.kind == "exile_dead_source" for e in effects):
        return effects
    zone, card = source.owner.graveyard, source.front
    ref = zone.reference(card) if card in zone else None
    return [dataclasses.replace(e, data=dict(e.data, dead_zone=zone, dead_ref=ref))
            if e.kind == "exile_dead_source" else e for e in effects]
