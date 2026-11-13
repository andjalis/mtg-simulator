""""it" in a self-headed trigger is the trigger's own permanent (#356).

    Whenever ~ deals combat damage to a player, put a +1/+1 counter on it.
    Whenever ~ becomes untapped, put two +1/+1 counters on it.

The effect parser reads "it" as target ``prev``. In a trigger, ``prev`` starts as the event object (the trigger
item's context when that is a permanent): the damaged player above is not one, and "becomes untapped" has none,
so the counter went nowhere. For heads "When(ever) ~ <combat, untap or damage event>" (``_EVENTS``), the leading
``prev`` Effects, before anything but a cost gate ("you may pay {E}{E}. If you do, ..."), are bound to ``self``.
Left alone: entering / turning face up (``prev`` already starts at ~ there, and "create a token, then attach ~ to
it" reads ``prev`` specially), dies / leaves heads (``prev`` tracks the card), triggers whose conditions read
``prev`` ("if its toughness is 3 or less"), abilities the parser split over several Triggers or only partly
matched (an unmatched sentence may hold the antecedent).
"""
from __future__ import annotations

import dataclasses
import re

_HEAD = re.compile(r"(?:When|Whenever) ~ ([^,]+),")
# Events whose trigger context is not ~ itself (a damaged player, a blocker, nothing). Entering, turning face up
# and mutating already start "prev" at ~, and some kinds read "prev" specially there ("create a token, then attach
# ~ to it": auras.py), so those heads are left alone.
_EVENTS = re.compile(r"(?:attacks|blocks|becomes blocked|blocks or becomes blocked|attacks or blocks|attacks while saddled|"
                     r"becomes (?:un)?tapped|is dealt damage|deals (?:combat )?damage(?: to (?:a player|an opponent))?)")
# Effects that may come before "it" without giving it another antecedent: costs and their "if you do" gates.
_GATES = {"pay_gate", "pay_energy", "link_start", "link_check", "sac_filtered"}


def bind(line: str, triggers) -> list:
    """The triggers with leading "it" Effects bound to the permanent itself, where the head allows it."""
    head = _HEAD.match(line)
    if not head or not _EVENTS.fullmatch(head[1]):
        return triggers
    body = line[head.end():]
    if not re.search(r"\b(?:it|he|she)\b", body) or re.search(r"\bthat (?:creature|permanent|card)\b", body):
        return triggers          # "~ deals 1 damage to that creature" is the other combatant, also "prev"
    if len({tuple(e.kind for e in t.effects) for t in triggers}) > 1:
        # one ability split over several Triggers ("gain control of target land ... Untap it."): in the later
        # parts "it" is an earlier object, not ~. Only an event fan-out ("attacks or blocks") is safe.
        return triggers
    return [_bind(t) for t in triggers]


def _bind(trigger):
    if "prev" in trigger.intervening_if or any("prev" in e.cond for e in trigger.effects):
        return trigger
    effects, changed = [], False
    for i, e in enumerate(trigger.effects):
        lead = all(x.target in ("prev", "self") or x.target == "none" and x.kind in _GATES
                   for x in trigger.effects[:i])
        if e.target == "prev" and lead:
            effects.append(dataclasses.replace(e, target="self"))
            changed = True
        else:
            effects.append(e)
    return dataclasses.replace(trigger, effects=effects) if changed else trigger
