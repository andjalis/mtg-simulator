"""Copying activated and triggered abilities.

    Whenever you activate an ability, if it isn't a mana ability, you may pay {2}. If you do, copy that ability.
        You may choose new targets for the copy.                                       (Rings of Brighthearth)
    Whenever you activate an ability of an artifact, if it isn't a mana ability, you may pay {R}. If you do, ...
                                                                                       (Kurkesh, Onakke Ancient)
    Whenever an ability of equipped creature is activated, if it isn't a mana ability, copy that ability. ...
                                                                                       (Illusionist's Bracers)
    {1}, {T}: Copy target activated or triggered ability you control from an artifact source. ...
                                                                                       (Tawnos, Abstruse Archaic)

``parse_line`` records ``advanced_rules["cx_copy_activated"]``; ``Game.activate`` calls ``on_activate`` after an
activated ability goes on the stack, which puts the copies straight above it (the trigger itself is not a
separate stack object: a recorded simplification, with the same resolution order). The AI pays an optional cost
whenever it can. The "from a <kind> source" copy effect is an EFFECT_PATTERN on the existing ``copy_ability``
kind with a ``source`` filter (copies.py checks it).
"""
from __future__ import annotations

import re

_DESC = {"an artifact": "Artifact", "a creature": "Creature", "an enchantment": "Enchantment",
         "a planeswalker": "Planeswalker", "a land": "Land"}


def parse_line(line: str, st) -> bool:
    m = re.fullmatch(r"Whenever (?:you activate an ability(?: of (an artifact|a creature|an enchantment|a planeswalker|"
                     r"a land))?|an ability of (equipped|enchanted) creature is activated), if it isn't a mana "
                     r"ability, (?:you may pay ((?:\{[^}]+\})+)\. If you do, )?copy that ability\. You may choose new "
                     r"targets for the copy\.", line)
    if not m:
        return False
    from .cards.model import parse_mana_cost
    entry = {"type": _DESC.get(m[1] or ""), "host": m[2] or "", "cost": parse_mana_cost(m[3]) if m[3] else None}
    st.extra.setdefault("advanced_rules", {}).setdefault("cx_copy_activated", []).append(entry)
    return True


def _fits(watcher, entry, item) -> bool:
    src = item.source
    if src is None:
        return False
    if entry["host"]:
        return getattr(watcher, "attached_to", None) is src or getattr(watcher, "aura_host", None) is src
    return entry["type"] is None or entry["type"] in src.card.types


def on_activate(game, p, item):
    """After p activated a (non-mana) ability that is now on the stack as item."""
    from .engine import StackItem
    for watcher in list(p.battlefield):
        if watcher.abilities_suppressed:
            continue
        for entry in watcher.card.advanced_rules.get("cx_copy_activated", ()):
            if item not in game.stack or not _fits(watcher, entry, item):
                continue
            if entry["cost"] is not None:
                if not game.can_pay(p, entry["cost"]) or game.pay(p, entry["cost"]) is None:
                    continue
            targets = game.auto_targets(p, item.effects, item.source)
            targets = [t if t is not None else old for t, old in zip(targets, item.targets)]
            cp = StackItem(p, list(item.effects), targets, source=item.source, name=item.name, context=item.context,
                           kind=item.kind)
            cp.x = getattr(item, "x", 0)
            game.stack.append(cp)
            game.log(f"{watcher.card.name} copies {item.name}", p)
