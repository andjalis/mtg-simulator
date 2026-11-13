"""Poison counters for a player named by context: see mtgsim/cx_counters.py."""
from __future__ import annotations

from . import kind
from ..state import Permanent, Player


@kind("cx_poison")
def cx_poison(game, p, eff, target, prev, **_):
    who = p if eff.data.get("who") == "you" else target
    if isinstance(who, Permanent):
        who = who.controller
    if isinstance(who, Player):
        who.counters["poison"] = who.counters.get("poison", 0) + eff.amount
        game.log(f"gets {eff.amount} poison counter(s)", who)


@kind("cx_distribute")
def cx_distribute(game, p, eff, item, **_):
    """The slot-0 effect splits ``amount`` counters over every target chosen for the group (see cx_counters)."""
    if eff.data.get("slot") or item is None:
        return
    group = [t for e, t in zip(item.effects, item.targets)
             if e.kind == "cx_distribute" and e.data.get("counter") == eff.data["counter"] and isinstance(t, Permanent)
             and t in t.controller.battlefield]
    chosen = []
    for t in group:
        if all(t is not c for c in chosen):
            chosen.append(t)
    if not chosen:
        return
    each, extra = divmod(eff.amount, len(chosen))
    for i, t in enumerate(chosen):
        t.counters[eff.data["counter"]] = t.counters.get(eff.data["counter"], 0) + each + (1 if i < extra else 0)


_BAD = ("-1/-1", "stun", "doom", "poison", "defense")   # defense: a Siege's controller wants it defeated


def _removal_helps(p, counter, owner):
    """Removing ``counter`` from a permanent of ``owner`` helps ``p`` when it is a bad counter on p's own permanent
    or a good counter on an opponent's."""
    return (counter in _BAD) == (owner is p)


@kind("cx_remove_counters")
def cx_remove_counters(game, p, eff, target, item=None, **_):
    """Remove counters of one kind (or "a counter" of any kind) from a permanent; "all" empties the kind or the card.
    Without a kind the controller's own permanent loses its worst counters first, an opponent's its best."""
    if not isinstance(target, Permanent):
        return
    kind_name = eff.data.get("counter", "")
    if kind_name:
        names = [kind_name]
    else:
        mine = target.controller is p
        names = sorted((n for n, c in target.counters.items() if c > 0),
                       key=lambda n: (n not in _BAD) if mine else (n in _BAD))
    if eff.data.get("optional"):               # "you may remove": the AI declines unless removal helps it
        names = [n for n in names if _removal_helps(p, n, target.controller)]
    left = 10 ** 6 if eff.data.get("all") else eff.amount
    taken = {}
    for name in names:
        if left <= 0:
            break
        have = target.counters.get(name, 0)
        take = min(have, left)
        if take:
            target.counters[name] = have - take
            left -= take
            taken[name] = taken.get(name, 0) + take
    from ..state import note_this_way           # "for each [<kind>] counter removed this way": the total (#345)
    note_this_way(item, "removed", list(taken) + ["counter"] if len(taken) == 1 else ["counter"],
                  sum(taken.values()))


@kind("time_counters")
def time_counters(game, p, eff, target, **_):
    """Time counters on a permanent or a suspended card, or on all of them (mtgsim/time_counters.py)."""
    from ...time_counters import apply
    apply(game, p, eff, target, eff.amount)


@kind("cx_move_src")
def cx_move_src(game, **_):
    """Names the first target of "move a counter from target X onto Y"; the move itself is cx_move_counters."""


@kind("cx_move_counters")
def cx_move_counters(game, p, eff, target, prev, item, **_):
    source = item.source if eff.data.get("from") == "self" and item is not None else prev
    if eff.data.get("from") == "prev" and item is not None:    # the stack's prev is already this effect's own target
        source = next((t for e, t in zip(item.effects, item.targets) if e.kind == "cx_move_src"), prev)
    dest = target
    if eff.target == "self":                 # "... onto ~": the card is the destination
        dest = item.source if item is not None else None
    if (not isinstance(source, Permanent) or not isinstance(dest, Permanent) or source is dest
            or source not in source.controller.battlefield or dest not in dest.controller.battlefield):
        return
    name = eff.data.get("counter", "")
    names = [name] if name else [n for n, c in source.counters.items() if c > 0]
    if eff.data.get("optional"):               # "you may move": the AI declines a move that leaves it worse off
        names = [n for n in names if _removal_helps(p, n, source.controller) or
                 not _removal_helps(p, n, dest.controller)]
    left = 10 ** 6 if eff.data.get("all") else eff.amount
    for n in names:
        take = min(source.counters.get(n, 0), left)
        if take > 0:
            source.counters[n] -= take
            dest.counters[n] = dest.counters.get(n, 0) + take
            left -= take
        if left <= 0:
            break
