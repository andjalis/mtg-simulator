"""Durations tied to the source ("for as long as you control ~ / ~ remains tapped"): see mtgsim/cx_statics.py."""
from __future__ import annotations

from . import kind
from ..state import Permanent


def _source(item):
    src = getattr(item, "source", None) if item is not None else None
    return src if isinstance(src, Permanent) else None


@kind("control_linked")
def control_linked(game, p, target, eff, item, **_):
    from ...counter_mechanics import add_control
    from ...cx_statics import linked_ok
    source = _source(item)
    mode = eff.data["duration"]
    if not isinstance(target, Permanent) or not linked_ok(source, mode, p):
        return
    if not hasattr(game, "_control_modes"):
        game._control_modes = {}
    game._control_modes[(id(target), id(source))] = (mode, p)
    add_control(game, target, p, source=source)


@kind("linked_pump")
def linked_pump(game, p, target, eff, item, **_):
    from ...cx_statics import LinkedStatic, linked_ok
    source = _source(item)
    mode = eff.data["duration"]
    if not isinstance(target, Permanent) or not linked_ok(source, mode, p):
        return
    if not hasattr(game, "_linked_statics"):
        game._linked_statics = []
    game._linked_statics.append(LinkedStatic(source, target, mode, p, tuple(eff.data["pt"]), tuple(eff.data["kws"])))


@kind("linked_restrict")
def linked_restrict(game, p, target, eff, item, **_):
    """"Can't attack / block for as long as you control ~": a keyword-style grant with no stat change (cx_statics._linked)."""
    from ...cx_statics import LinkedStatic, linked_ok
    source = _source(item)
    mode = eff.data["duration"]
    if not isinstance(target, Permanent) or not linked_ok(source, mode, p):
        return
    if not hasattr(game, "_linked_statics"):
        game._linked_statics = []
    game._linked_statics.append(LinkedStatic(source, target, mode, p, kws=tuple(eff.data["kws"])))


@kind("hand_to_battlefield")
def hand_to_battlefield(game, p, eff, item, **_):
    """"You may put a creature card from your hand onto the battlefield" (Elvish Piper) and its qualified
    forms (dynamic mana value, chosen type, tapped / attacking / attached entry): see mtgsim/hand_put.py."""
    from ...hand_put import resolve
    resolve(game, p, eff, item)
