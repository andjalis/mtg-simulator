"""Damage and life: damage, drain, life gain and loss."""
from __future__ import annotations

import dataclasses

from ..state import Permanent, Player
from . import kind


@kind("damage")
def damage(game, p, eff, target, item, opp, cause, **_):
    src = (item.source if item.source is not None else item.card) if item is not None else None
    victims = _damage(game, p, eff, target, item, opp, cause)
    if eff.data.get("exile_dying") or (isinstance(src, Permanent) and src.card.exile_damaged):
        from ...batch1_templates import mark_exile_dying
        for v in victims:
            if isinstance(v, Permanent) and v.is_creature and v.damage > 0 and v in v.controller.battlefield:
                mark_exile_dying(game, v)


def _damage(game, p, eff, target, item, opp, cause):
    """Deal the effect's damage; return the permanents and players it was dealt to."""
    src = (item.source if item.source is not None else item.card) if item is not None else None
    victims = []
    if eff.data.get("source_power"):
        eff = dataclasses.replace(eff, amount=max(0, src.power) if isinstance(src, Permanent) else 0)
    if eff.target == "each_creature":
        for perm in p.creatures + opp.creatures:
            if eff.filter == "nonflying" and perm.has("flying"):
                continue
            if eff.filter == "flying" and not perm.has("flying"):
                continue
            if eff.data.get("no_regen") and eff.amount > 0:
                perm.regeneration_blocked = True
            game.deal_damage(perm, eff.amount, by=p, cause=cause, source=src)
            victims.append(perm)
    elif eff.target == "each_opp_and_pw":
        game.deal_damage(opp, eff.amount, by=p, cause=cause, source=src)
        victims.append(opp)
        for pw in opp.planeswalkers:
            game.deal_damage(pw, eff.amount, by=p, cause=cause, source=src)
            victims.append(pw)
    else:
        if eff.data.get("no_regen") and eff.amount > 0 and isinstance(target, Permanent) and target.is_creature:
            target.regeneration_blocked = True
        game.deal_damage(target, eff.amount, by=p, cause=cause, source=src)
        victims.append(target)
    return victims


@kind("gain_life")
def gain_life(game, p, eff, target, cause, **_):
    who = target if eff.target == "that_controller" and isinstance(target, Player) else p
    game.change_life(who, eff.amount, cause)


@kind("drain")
def drain(game, p, eff, opp, cause, **_):
    game.change_life(opp, -eff.amount, cause)
    if eff.data.get("gain"):
        game.change_life(p, eff.amount, cause)


@kind("lose_life")
def lose_life(game, p, eff, target, cause, **_):
    who = target if eff.target in ("that_player", "that_controller") and isinstance(target, Player) else p
    game.change_life(who, -eff.amount, cause)


@kind("gain_prev_toughness")
def gain_prev_toughness(game, p, prev, cause, **_):
    """"You gain life equal to that creature's toughness": the previous effect's target, as it last existed."""
    if isinstance(prev, Permanent):
        game.change_life(p, max(0, prev.last_pt[1] if prev not in prev.controller.battlefield else prev.toughness), cause)


@kind("lose_each")
def lose_each(game, eff, cause, **_):
    for pl in game.players:
        game.change_life(pl, -eff.amount, cause)


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
