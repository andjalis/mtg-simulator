"""Damage and life: damage, drain, life gain and loss."""
from __future__ import annotations

from ..state import Permanent, Player
from . import kind


@kind("damage")
def damage(game, p, eff, target, item, opp, cause, **_):
    src = (item.source if item.source is not None else item.card) if item is not None else None
    if eff.target == "each_creature":
        for perm in p.creatures + opp.creatures:
            if eff.data.get("no_regen") and eff.amount > 0:
                perm.regeneration_blocked = True
            game.deal_damage(perm, eff.amount, by=p, cause=cause, source=src)
    elif eff.target == "each_opp_and_pw":
        game.deal_damage(opp, eff.amount, by=p, cause=cause, source=src)
        for pw in opp.planeswalkers:
            game.deal_damage(pw, eff.amount, by=p, cause=cause, source=src)
    else:
        if eff.data.get("no_regen") and eff.amount > 0 and isinstance(target, Permanent) and target.is_creature:
            target.regeneration_blocked = True
        game.deal_damage(target, eff.amount, by=p, cause=cause, source=src)


@kind("gain_life")
def gain_life(game, p, eff, target, cause, **_):
    who = target if eff.target == "that_controller" and isinstance(target, Player) else p
    game.change_life(who, eff.amount, cause)


@kind("drain")
def drain(game, eff, opp, cause, **_):
    game.change_life(opp, -eff.amount, cause)


@kind("lose_life")
def lose_life(game, p, eff, target, cause, **_):
    who = target if eff.target in ("that_player", "that_controller") and isinstance(target, Player) else p
    game.change_life(who, -eff.amount, cause)


@kind("drain_devotion")
def drain_devotion(game, p, eff, opp, cause, **_):
    color = eff.data["color"]
    n = sum(x.card.mana_cost.get(color, 0) for x in p.battlefield)
    game.change_life(opp, -n, cause)
    game.change_life(p, n, cause)
    game.log(f"drains {n} (devotion)", p)


@kind("damage_each_player")
def damage_each_player(game, eff, cause, **_):
    for pl in game.players:
        game.change_life(pl, -eff.amount, cause)
