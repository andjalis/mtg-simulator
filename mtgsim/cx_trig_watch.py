"""Delayed trigger on a target: "<Spell effect on target creature>. When that creature dies this turn, <effects>."

The rider becomes ``cx_watch``; as the spell resolves it records (turn, the targeted permanent, the effects) on
``game.cx_watchers``. ``observe`` (called from ``Game.fire``) queues the effects once when that permanent dies
before the turn ends. The payoff may only use effects that need nothing from the dead creature (no "its
controller's ..."), so each parses on its own.
"""
from __future__ import annotations

import re

_RIDER = re.compile(r"when (?:that creature|it) dies this turn, (?P<body>.+)", re.I)
_BUSY = False


def _effect(*args, **kwargs):
    from .cards.model import Effect
    return Effect(*args, **kwargs)


def parse_rider(sentence: str, effects: list) -> bool:
    global _BUSY
    m = _RIDER.fullmatch(sentence.strip().rstrip("."))
    if not m or _BUSY or not any(e.target not in ("none", "self", "you", "") for e in effects):
        return False
    from .cards.parse import _parse_effects
    body = m["body"]
    if re.search(r"\b(?:its|that|their)\b", body, re.I):
        return False            # refers to the dead creature or its controller: not carried by the watcher
    _BUSY = True
    try:
        new, bad = _parse_effects(body[0].upper() + body[1:] + ".")
    finally:
        _BUSY = False
    if bad or not new or any(e.target not in ("none", "self", "you", "") for e in new):
        return False
    effects.append(_effect("cx_watch", data={"effects": new}))
    return True


def watch(game, p, eff, prev, item):
    from .engine.state import Permanent
    if not isinstance(prev, Permanent):
        return
    game.cx_watchers.append((game.turn, prev, p, list(eff.data["effects"]),
                             item.source if item is not None else None))


def observe(game, p, event, source):
    """Queue the payoff of every watcher whose creature just died this turn."""
    if event != "dies" or source is None or not game.cx_watchers:
        return
    keep = []
    for turn, perm, controller, effects, origin in game.cx_watchers:
        if turn != game.turn:
            continue                  # expired
        if perm is source:
            game.queue_trigger(controller, effects, origin, "when that creature dies this turn")
        else:
            keep.append((turn, perm, controller, effects, origin))
    game.cx_watchers = keep
