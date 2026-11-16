"""Kinds for exchanges of control (see mtgsim.cx_exchange)."""
from ... import counter_mechanics
from ...cx_exchange import pair_ok, swing
from ..state import Permanent
from . import kind


@kind("cx_exchange_mark")
def exchange_mark(game, p, **_):
    """The first object of an exchange: the following cx_exchange reads it from the stack item."""


def _present(perm) -> bool:
    return isinstance(perm, Permanent) and perm in perm.controller.battlefield


def _first(game, p, eff, item):
    """The first object: the source, or the preceding mark's target while it is still a legal target."""
    if item is None:
        return None
    if eff.data.get("first") == "self":
        return item.source
    idx = next((i for i, e in enumerate(item.effects) if e is eff), None)
    if idx is None:
        idx = next((i for i, e in enumerate(item.effects) if e == eff), None)
    if not idx or idx > len(item.targets) or item.effects[idx - 1].kind != "cx_exchange_mark":
        return None
    first = item.targets[idx - 1]
    with game.targeting(item):
        return first if first is not None and game.legal_target(p, item.effects[idx - 1], first) else None


@kind("cx_exchange")
def exchange(game, p, eff, target, item=None, **_):
    """Exchange control of two permanents in one step, or do nothing (rule 701.12)."""
    first = _first(game, p, eff, item)
    second = target
    if not (_present(first) and _present(second)) or first is second:
        game.log("no exchange of control (an object is gone or illegal)", p)
        return
    if first.controller is second.controller:
        game.log(f"no exchange: one player controls {first.card.name} and {second.card.name}", p)
        return
    if not pair_ok(first, second, eff.data.get("cx_pair", ())):
        game.log(f"no exchange: {first.card.name} and {second.card.name} no longer qualify", p)
        return
    if eff.data.get("optional") and swing(p, first, second) <= 0:
        game.log(f"declines to exchange {first.card.name} and {second.card.name}", p)
        return
    a, b = first.controller, second.controller
    counter_mechanics.add_control(game, first, b)
    counter_mechanics.add_control(game, second, a)
    if item is not None:
        item.cx_exchanged, item.cx_exchanged_pair = True, (first, second)
    game.log(f"exchanges control of {first.card.name} ({b.name} now) and {second.card.name} ({a.name} now)", p)


@kind("cx_exchange_else")
def exchange_else(game, p, eff, item=None, **_):
    """"If you don't or can't make an exchange, sacrifice ~." (Gilded Drake): after the item's exchange, when no
    exchange happened (no target chosen, the target illegal, or the exchange couldn't be made)."""
    if item is None or not any(e.kind == "cx_exchange" for e in item.effects):
        return
    if eff.data.get("if_exchanged") == "destroy_auras":
        for perm in getattr(item, "cx_exchanged_pair", ()) if getattr(item, "cx_exchanged", False) else ():
            for aura in list(perm.auras):
                game.destroy(aura)
        return
    if getattr(item, "cx_exchanged", False):
        return
    src = item.source
    if eff.data.get("sacrifice") == "self" and _present(src) and src.controller is p:
        game.sacrifice(src)
