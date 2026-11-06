"""Untap the source and take it out of combat."""
from . import kind
from ..state import Permanent


@kind("remove_from_combat")
def remove_from_combat(game, p, item, **_):
    """The subject is the source ("Whenever ~ becomes blocked") or, for "Whenever a creature you control becomes
    blocked" (Nivea), the blocked attacker handed over as the trigger's context. A self-trigger's context is the
    blocker, which is never in ``game.attackers``, so it falls back to the source."""
    src = item.source if item is not None else None
    ctx = getattr(item, "context", None)
    if isinstance(ctx, Permanent) and ctx in game.attackers:
        src = ctx
    if not isinstance(src, Permanent) or src not in src.controller.battlefield:
        return
    src.tapped = False
    if src in game.attackers:
        game.attackers.remove(src)
    game.attack_targets.pop(src, None)
    if src in game.blocks:                      # an attacker stays blocked, with nobody left to hit or be hit by
        game.blocks[src] = []
    for blockers in game.blocks.values():
        if src in blockers:
            blockers.remove(src)
    game.log(f"untaps {src.card.name} and removes it from combat", p)
