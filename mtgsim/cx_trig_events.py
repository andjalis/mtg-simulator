"""More events for the cx_events grammar (each one is fired by the engine, so any effect that follows works):

    you surveil | you win a coin flip | a creature you control explores
    you lose life during your turn | you lose life for the first time each turn | you gain or lose life during your turn
    an opponent / you / a player is dealt (non)combat damage

They extend the player-verb table of cx_events; ``player_ok`` adds the per-kind conditions that cx_events._match
calls before it accepts a player event.
"""
from __future__ import annotations

from . import cx_events

_VERBS = [
    (r"surveils?", "surveil"),
    (r"wins? a coin flip", "win_flip"),
    (r"loses? life during your turn", "lose_turn"),
    (r"loses? life for the first time each turn", "lose_first"),
    (r"gains? or loses? life during your turn", "gain_lose_turn"),
    (r"(?:is|are) dealt damage", "dealt"),
    (r"(?:is|are) dealt noncombat damage", "dealt_noncombat"),
    (r"(?:is|are) dealt combat damage", "dealt_combat"),
]
_RAW = {"surveil": ("you_surveil",), "win_flip": ("you_win_flip",), "lose_turn": ("opp_loses_life",),
        "lose_first": ("opp_loses_life",), "gain_lose_turn": ("gain_life", "opp_loses_life"),
        "dealt": ("player_damaged",), "dealt_noncombat": ("player_damaged",), "dealt_combat": ("player_damaged",)}

# the fixed verbs go first: "loses life during your turn" must not be read as a longer match of "loses life"
cx_events._PLAYER_VERBS[0:0] = _VERBS
cx_events._PLAYER_RAW.update(_RAW)
cx_events._OBSERVED.update({"you_surveil", "you_win_flip", "player_damaged", "explores"})


def player_ok(game, spec, actor, me, event) -> bool:
    kind = spec["kind"]
    if kind in ("lose_turn", "gain_lose_turn"):
        return game.active is me
    if kind == "lose_first":
        return actor.life_lost_amount == (getattr(game, "event_amount", None) or 0)
    if kind == "dealt_noncombat":
        return not getattr(game, "event_combat", False)
    if kind == "dealt_combat":
        return bool(getattr(game, "event_combat", False))
    return True
