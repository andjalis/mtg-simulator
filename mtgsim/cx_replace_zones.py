"""#407: "If it would leave the battlefield, exile it instead of putting it anywhere else" on a permanent an
effect just put onto the battlefield (reanimation), written as a sentence or as a granted quoted ability.

    Return target creature card from your graveyard to the battlefield. It gains haste. Exile it at the beginning
    of the next end step. If it would leave the battlefield, exile it instead of putting it anywhere else.
    Return target creature card from your graveyard to the battlefield. It gains "If this creature would leave the
    battlefield, exile it instead of putting it anywhere else."

A ``cx_bf_watch`` effect just before the instruction that puts the card onto the battlefield notes the effect
clock; ``cx_leave_exile`` at the end marks every permanent that entered since (``rules_timestamp``) with
``exile_on_leave``. ``rules_events.zone_destination`` then turns any move off the battlefield into exile for a
marked permanent. A new object (it left and came back) carries no mark.
"""
from __future__ import annotations

import re

_RX = re.compile(r"(?:if (?:that creature|it|the creature|that permanent) would leave the battlefield, exile it instead "
                 r"of putting it anywhere else|(?:it|that creature|the creature) gains \"if (?:this creature|this "
                 r"permanent|this land|~) would leave the battlefield, exile it instead of putting it anywhere else\.?\")",
                 re.I)


def _puts_onto_battlefield(eff) -> bool:
    if eff.kind in ("reanimate_temp", "reanimate_one", "reanimate", "return_self_gy", "reanimate_target"):
        return True
    if eff.kind == "gy_move":
        return eff.data.get("dest") == "bf"
    if eff.kind == "cx_card_move":
        return eff.data.get("to") in ("battlefield", "bf")
    return False


def parse_rider(s: str, effects: list) -> bool:
    if not _RX.fullmatch(s.strip().rstrip(".")) or not effects:
        return False
    puts = [i for i, e in enumerate(effects) if _puts_onto_battlefield(e)]
    if len(puts) != 1 or effects[puts[0]].cond:
        return False                # no instruction, or several: which permanent "it" is would be a guess
    from .cards.model import Effect
    i = puts[0]
    effects[i:i] = [Effect("cx_bf_watch")]
    effects.append(Effect("cx_leave_exile"))
    return True


def watch(game, item):
    if item is not None:
        item.cx_bf_clock = game.effect_clock


def mark(game, item):
    clock = getattr(item, "cx_bf_clock", None)
    if clock is None:
        return
    item.cx_bf_clock = None
    for pl in game.players:
        for perm in pl.battlefield:
            if (getattr(perm, "rules_timestamp", 0) or 0) > clock:
                perm.exile_on_leave = True
                game.log(f"{perm.card.name} will be exiled if it would leave the battlefield", pl)
