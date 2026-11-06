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


@kind("damage_power_opp")
def damage_power_opp(game, p, item, opp, cause, **_):
    """"It deals damage equal to its power to each opponent". "It" is the creature the trigger is about: its context
    (the Elemental that entered for Champion of the Path), else the source itself (a creature that dies)."""
    ctx = getattr(item, "context", None)
    subject = ctx if isinstance(ctx, Permanent) else (item.source if item is not None else None)
    if isinstance(subject, Permanent):
        game.deal_damage(opp, max(0, subject.power), by=p, cause=cause, source=subject)
