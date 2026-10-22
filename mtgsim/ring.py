"""The Ring tempts you (The Lord of the Rings: Tales of Middle-earth).

    The Ring tempts you.            Whenever the Ring tempts you, put a +1/+1 counter on each creature you control.

Each time the Ring tempts a player, their Ring level goes up (to four at most) and they choose a Ring-bearer: their
best creature (``policy.perm_value``), kept if it is still the best. The Ring's abilities, by level:

    1. Your Ring-bearer is legendary and can't be blocked by creatures with greater power (a skulk counter).
    2. Whenever your Ring-bearer attacks, draw a card, then discard a card.
    3. Whenever your Ring-bearer becomes blocked by a creature, that creature's controller sacrifices it at end
       of combat.
    4. Whenever your Ring-bearer deals combat damage to a player, each opponent loses 3 life.

The engine calls ``attacks``, ``blocked`` and ``combat_damage`` from combat. Not modelled: "is your Ring-bearer"
conditions and choosing a Ring-bearer other than the best creature; being legendary has no effect.
"""
from __future__ import annotations

KINDS = {"ring_tempts"}
_LOOT = None


def _effect(kind, amount=0, **kw):
    from .cards import Effect
    return Effect(kind, amount, **kw)


EFFECT_PATTERNS = [
    (r"the ring tempts you", lambda m: _effect("ring_tempts")),
]


def bearer(p):
    """p's Ring-bearer, if it is still on the battlefield."""
    b = getattr(p, "ring_bearer", None)
    return b if b is not None and b in p.battlefield and b.is_creature else None


def level(p) -> int:
    return getattr(p, "ring_level", 0)


def resolve(game, p, eff, target, item):
    from .engine.policy import perm_value
    p.ring_level = min(4, level(p) + 1)
    old = bearer(p)
    best = max(p.creatures, key=perm_value, default=None)
    if best is not None and (old is None or perm_value(best) > perm_value(old)):
        if old is not None:
            old.counters["skulk"] = max(0, old.counters.get("skulk", 0) - 1)
        best.counters["skulk"] = best.counters.get("skulk", 0) + 1
        p.ring_bearer = best
    game.log(f"the Ring tempts {p.name} (level {p.ring_level}"
             + (f", Ring-bearer {bearer(p).card.name})" if bearer(p) else ")"), p)
    game.fire(p, "ring_tempts")


def attacks(game, p, attacker) -> None:
    global _LOOT
    if attacker is bearer(p) and level(p) >= 2:
        if _LOOT is None:
            from .cards import _parse_effects
            _LOOT = _parse_effects("Draw a card, then discard a card.")[0]
        game.queue_trigger(p, list(_LOOT), attacker, "The Ring: loot")


def blocked(game, p, attacker, blockers) -> None:
    if attacker is bearer(p) and level(p) >= 3:
        for b in blockers:
            game.end_combat_effects.append((b.controller, [_effect("sacrifice_self", target="self")], b, None))


def combat_damage(game, p, source, player) -> None:
    if source is bearer(p) and level(p) >= 4:
        game.queue_trigger(p, [_effect("lose_life", 3, target="that_player")], source, "The Ring: drain",
                           context=player)
