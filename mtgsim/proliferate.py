"""Non-targeting proliferation and a policy for choosing useful counter-bearing objects."""
from __future__ import annotations


def candidates(game):
    return [obj for p in game.players for obj in [p] + list(p.battlefield)
            if any(n > 0 for n in obj.counters.values())]


def counter_value(obj, kind):
    """Value to the object's controller; custom policies can handle unknown kinds."""
    from .engine import Player
    if isinstance(obj, Player):
        return -2.0 if kind in ("poison", "rad") else 1.0 if kind in ("energy", "experience") else 0.0
    if kind == "+1/+1":
        return 1.0
    if kind == "-1/-1":
        return -1.0
    if kind in ("stun", "finality", "age", "ice") or kind == "time" and obj.impending:
        return -0.5
    if kind in ("loyalty", "charge", "shield", "oil"):
        return 0.5
    if kind == "lore" and obj.card.is_saga:
        return 0.5 if obj.counters.get("lore", 0) < len(obj.card.chapters) else 0.0
    return 0.0


def object_value(game, me, obj):
    owner = obj if obj in game.players else obj.controller
    sign = 1 if owner is me else -1
    return sign * sum(counter_value(obj, kind) for kind, n in obj.counters.items() if n > 0)


def choose(game, me):
    # All counter types on an object are an inseparable choice, even if some hurt us.
    return [obj for obj in candidates(game) if object_value(game, me, obj) > 0]


def value(game, me):
    return sum(object_value(game, me, obj) for obj in choose(game, me))


def apply(game, me, selected=None):
    from .engine import Permanent
    legal = candidates(game)
    chosen = game.hook(me, "choose_proliferate")(game, me) if selected is None else selected
    seen, lore = set(), []
    for obj in chosen or []:
        if not any(obj is c for c in legal) or id(obj) in seen:
            continue
        seen.add(id(obj))
        old_lore = obj.counters.get("lore", 0)
        for kind, n in list(obj.counters.items()):
            if n > 0:
                obj.counters[kind] = n + 1
        if isinstance(obj, Permanent) and obj.card.is_saga and obj.counters.get("lore", 0) > old_lore:
            lore.append((obj, old_lore, obj.counters["lore"]))
    # Every selected object's counters change before chapter triggers are queued.
    for saga, old, new in lore:
        game.lore_triggers(saga, old, new)
    game.log(f"proliferates on {len(seen)} object(s)", me)
    game.fire(me, "proliferate")
