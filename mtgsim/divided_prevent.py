"""Divided prevention shields (#333): "Prevent the next N damage that would be dealt this turn to any number of targets,
divided as you choose" (Embolden, Remedy, Angel of Salvation), with X read as a quantity ("..., where X is the number
of verse counters on ~": Serra's Hymn).

Like divided damage (cx_damage.py), the division is chosen as the spell or ability is put on the stack
(``cx_damage.Stack.append`` asks ``plan_item``): N is split among the controller's creatures and planeswalkers that
damage already on the stack or in combat would hurt, the most valuable ones it can save first, and what is left goes on
the controller. On resolution each chosen target that is still legal gets its share as an ordinary ``prevent_next``
shield (Game.deal_damage consumes it, cleanup expires it). The amount is fixed when the division is chosen.
"""
from __future__ import annotations

KINDS = {"divided_prevent"}


def _divided(m):
    from .cards.model import Effect, NO_MATCH
    n = m["n"].lower()
    data = {}
    if n == "x":
        if not m["q"]:
            data["x"] = True
        else:
            from .cards.clauses import _xq
            spec = _xq(m["q"])
            if spec is None:
                return NO_MATCH
            data["xq"] = spec
    elif m["q"]:
        return NO_MATCH
    return Effect("divided_prevent", 1 if n == "x" and m["q"] else 0 if n == "x" else int(n), data=data)


EFFECT_PATTERNS = [
    (r"prevent the next (?P<n>\d+|x) damage that would be dealt this turn to any number of targets, divided as you "
     r"choose(?:, where x is (?P<q>.+))?", _divided),
]


def _amount(game, p, eff, item) -> int:
    if eff.data.get("x"):
        return getattr(item, "x", 0) or 0
    if eff.data.get("xq"):
        return eff.amount * game.x_quantity(p, eff.data["xq"], item, None)
    return eff.amount


def _incoming(game, p, item):
    """{victim: damage} that pending damage of the opponent's (the stack below item, combat) would deal to p's things."""
    from .engine.state import Permanent
    hurt: dict = {}
    for other in game.stack:
        if other is item or other.controller is p:
            continue
        for e, t in zip(other.effects, other.targets):
            if e.kind == "damage" and (t is p or isinstance(t, Permanent) and t.controller is p):
                hurt[t] = hurt.get(t, 0) + e.amount
    blocks = getattr(game, "blocks", None) or {}           # attacker -> its blockers
    for attacker in getattr(game, "attackers", None) or ():
        blockers = list(blocks.get(attacker, ()))
        if attacker.controller is p:                        # our attacker takes its blockers' damage
            if blockers:
                hurt[attacker] = hurt.get(attacker, 0) + sum(max(0, b.power) for b in blockers)
            continue
        if blockers:                                        # their attacker hits our blockers (a rough share each)
            for b in blockers:
                hurt[b] = hurt.get(b, 0) + max(0, attacker.power)
        else:
            hurt[p] = hurt.get(p, 0) + max(0, attacker.power)
    return hurt


def plan(game, p, amount, item=None):
    """[[victim, share], ...] for amount of prevention."""
    from .engine.policy import perm_value
    from .engine.state import Permanent
    left, chosen = amount, []
    hurt = _incoming(game, p, item)
    saved = sorted((v for v in hurt if isinstance(v, Permanent) and v in p.battlefield and game.targetable(v, p)),
                   key=perm_value, reverse=True)
    for perm in saved:
        left_t = (perm.toughness - perm.damage) if perm.is_creature else perm.loyalty
        need = hurt[perm] - left_t + 1          # enough to survive
        if 0 < need <= left:
            chosen.append([perm, need])
            left -= need
    if left > 0:
        chosen.append([p, left])
    return chosen


def plan_item(game, item):
    """Choose the division of every divided_prevent effect of item as it goes on the stack."""
    plans = [plan(game, item.controller, _amount(game, item.controller, e, item), item)
             for e in item.effects if e.kind == "divided_prevent"]
    if plans:
        item.divided_prevent = plans


def resolve(game, p, eff, item):
    from .engine.state import Permanent
    from .cx_damage import _legal
    plans = getattr(item, "divided_prevent", None) if item is not None else None
    chosen = plans.pop(0) if plans else plan(game, p, _amount(game, p, eff, item), item)
    for victim, share in chosen:
        if share > 0 and _legal(game, p, victim):
            victim.prevent_next += share
            game.log(f"prevents the next {share} damage to "
                     f"{victim.card.name if isinstance(victim, Permanent) else victim.name}", p)


