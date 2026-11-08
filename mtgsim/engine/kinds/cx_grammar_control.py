"""Kinds for the control family (see mtgsim.cx_grammar_control)."""
from ... import counter_mechanics
from ..state import Permanent, Player
from . import kind


@kind("cx_control")
def control(game, p, eff, target, **_):
    if isinstance(target, Permanent) and target in target.controller.battlefield:
        counter_mechanics.add_control(game, target, p, until_eot=eff.data["eot"])
        if eff.data.get("untap"):
            target.tapped = False
        game.log(f"gains control of {target.card.name}" + (" until end of turn" if eff.data["eot"] else ""), p)


@kind("cx_give_control")
def give_control(game, p, eff, target, item=None, prev=None, **_):
    """The player (target, from cx_players) gains control of ~ or of the previous object."""
    victim = (item.source if item is not None else None) if eff.data["what"] == "self" else prev
    if isinstance(target, Player) and isinstance(victim, Permanent) and victim in victim.controller.battlefield \
            and victim.controller is not target:
        counter_mechanics.add_control(game, victim, target)
        game.log(f"{target.name} gains control of {victim.card.name}", p)
