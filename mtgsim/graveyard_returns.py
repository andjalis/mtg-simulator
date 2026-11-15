"""Dies, exile the dead source, then return other graveyard cards (#508).

The whole trigger is read together: an unrelated "exile it" must not be
interpreted as exiling a dead source. Targets are chosen when the trigger is
stacked; random/top-card choices happen after the source is exiled.
"""
from __future__ import annotations

import dataclasses
import re


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
