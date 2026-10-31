"""Turn-limited locks, base P/T and player flags (see mtgsim.cx_next_turn)."""
from ..state import Permanent
from . import kind


@kind("cx_temp_kw")
def temp_keywords(game, target, eff, **_):
    if isinstance(target, Permanent):
        target.temp_kw.update(eff.data["keywords"])


@kind("cx_lose_kw")
def lose_keyword(game, target, eff, **_):
    if isinstance(target, Permanent):
        game.add_continuous_effect(target, "remove", keyword=eff.data["keyword"], until_eot=True)


@kind("cx_set_base")
def set_base(game, p, target, eff, opp, **_):
    if eff.data.get("group"):       # "creatures target player controls have base power and toughness 1/1"
        victims = list(target.creatures) if target in game.players else []
    else:
        victims = [target] if isinstance(target, Permanent) else []
    for v in victims:
        game.add_continuous_effect(v, "set_base", power=eff.amount, toughness=eff.amount2, until_eot=True)


@kind("cx_player_flag")
def player_flag(game, p, eff, opp, **_):
    from ...cx_next_turn import add_flag
    who = opp if eff.data.get("who") == "opp" else p
    add_flag(game, p, who, eff)


@kind("cx_controller_creatures_damage")
def controller_creatures_damage(game, p, target, eff, item, cause, **_):
    """Damage to each creature the previous target (a player, or a planeswalker's controller) controls."""
    who = target.controller if isinstance(target, Permanent) else target
    if who not in game.players:
        return
    src = (item.source if item.source is not None else item.card) if item is not None else None
    for c in list(who.creatures):
        game.deal_damage(c, eff.amount, by=p, cause=cause, source=src)
