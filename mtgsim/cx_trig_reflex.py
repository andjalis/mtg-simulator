"""Reflexive triggers: "<Action>. When you do, <payoff>." for any action the effect templates parse.

cx_links only links actions that are costs (sacrifice, discard, ...). "When you do" also follows plain actions
("Create two Faerie tokens. When you do, tap target creature", "Return target creature card from your graveyard to
the battlefield. When you do, it fights ..."). The same link_start / link_check pair decides whether the action
changed the game; the payoff then rides item.gate_paid like every "if you do" reward.
"""
from __future__ import annotations

import dataclasses
import re

_WHEN_DO = re.compile(r"\s*when you do\b", re.I)
# A payoff about "it" / "that creature" needs the action's object remembered; the engine doesn't carry that
# across the link, so those stay unsupported instead of acting on the wrong object.
_BACKREF = re.compile(r"\s*when you do, (?:attach\b|it|they|he|she|that [\w ]+?|those [\w ]+?|~ deals that much)\b", re.I)


def parse_reflex(s: str, following: str):
    """Effects for an action sentence whose next sentence is "When you do, ...", else None."""
    if not _WHEN_DO.match(following or "") or _BACKREF.match(following):
        return None
    from .cards import _parse_effects
    from .cx_links import TAKEN, Effect
    s = re.sub(r"^then ", "", s, flags=re.I)
    m = re.fullmatch(r"you may (.+)", s, re.I)
    forced = m is None
    body = s if forced else m[1]
    new, bad = _parse_effects(body[0].upper() + body[1:] + ".")
    if (bad or not new) and not forced:
        new, bad = _parse_effects("You " + body + ".")
    if bad or not new or any(e.cond or e.kind in ("pay_gate", "link_start", "link_check") for e in new):
        return None
    kinds = tuple(e.kind for e in new)
    if {"die_roll", "add_mana"} & set(kinds):
        return None         # dice and mana abilities have their own handling (dungeon_mechanics, mana abilities)
    return ([Effect("link_start", data={"kinds": kinds, "forced": forced})]
            + [dataclasses.replace(e, cond=TAKEN) for e in new] + [Effect("link_check")])
