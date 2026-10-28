"""Kicker riders: build the paid mode without changing the ordinary spell.

Only mana kicker costs are currently offered by the parser. Nonmana kicker and
riders requiring other rules layers stay visible in unsupported text.
"""
from __future__ import annotations

import copy
import dataclasses
import re


_NUMBER = r"(?:an?|one|two|three|four|five|six|seven|eight|nine|ten|\d+)"


def build_mode(cost, kicker_cost, spell, riders, *, permanent=False):
    """Return a kicker AltCost and the riders that could not be implemented."""
    from .cards.model import AltCost, _num, add_mana
    from .cards.parse import _parse_effects

    effects = copy.deepcopy(spell)
    unsupported = []
    counters = 0
    for rider in riders:
        m = re.fullmatch(rf"it enters with ({_NUMBER}) \+1/\+1 counters? on it\.", rider)
        if m and permanent:
            counters += _num(m[1])
            continue
        m = re.fullmatch(r"it deals (\d+) damage(?: to that creature)? instead\.", rider)
        damage = [e for e in effects if e.kind == "damage"]
        if m and damage:
            e = damage[0]
            effects[effects.index(e)] = dataclasses.replace(e, amount=int(m[1]))
            continue
        m = re.fullmatch(r"that creature gets ([+-]\d+)/([+-]\d+) until end of turn instead\.", rider)
        pumps = [e for e in effects if e.kind in ("pump", "debuff_one") and e.target == "creature"]
        if m and pumps:
            e = pumps[0]
            effects[effects.index(e)] = dataclasses.replace(e, kind="pump", amount=int(m[1]), amount2=int(m[2]))
            continue
        m = re.fullmatch(rf"that player discards ({_NUMBER}) cards? instead\.", rider)
        discards = [e for e in effects if e.kind == "discard" and e.target == "player"]
        if m and discards:
            e = discards[0]
            effects[effects.index(e)] = dataclasses.replace(e, amount=_num(m[1]))
            continue
        m = re.fullmatch(r"put (\w+) of those cards into your hand instead\.", rider)
        digs = [e for e in effects if e.kind == "dig"]
        if m and digs:
            e = digs[0]
            effects[effects.index(e)] = dataclasses.replace(e, amount2=_num(m[1]))
            continue
        if rider.startswith("instead "):
            body = rider[len("instead "):]
            new, bad = _parse_effects(body)
            if new and not bad:
                effects = new
                continue
            unsupported.append(f"if kicked: {rider}")
            continue
        # An unrecognized replacement must not become an additional effect.
        if "instead" in rider:
            unsupported.append(f"if kicked: {rider}")
            continue
        new, bad = _parse_effects(rider)
        effects += new
        unsupported += [f"if kicked: {b}" for b in bad]
    return AltCost("kicker", add_mana(cost, kicker_cost), effects=effects, counters=counters), unsupported


def entry_counters(kind, alt):
    """Initial counters, supplied before entry events and state-based actions."""
    return {"+1/+1": alt.counters} if kind == "kicker" and alt is not None and alt.counters else None
