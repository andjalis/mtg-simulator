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
    game.log(f"exchanges control of {first.card.name} ({b.name} now) and {second.card.name} ({a.name} now)", p)
