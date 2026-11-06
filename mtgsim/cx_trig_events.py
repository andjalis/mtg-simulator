"""More events for the cx_events grammar (each one is fired by the engine, so any effect that follows works):

    you surveil | you win a coin flip | a creature you control explores
    you lose life during your turn | you lose life for the first time each turn | you gain or lose life during your turn
    an opponent / you / a player is dealt (non)combat damage

They extend the player-verb table of cx_events; ``player_ok`` adds the per-kind conditions that cx_events._match
calls before it accepts a player event.
"""
from __future__ import annotations

import re

from . import cx_events

_N = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_COUNT = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)"
_VERBS = [
    (r"surveils?", "surveil"),
    (r"wins? a coin flip", "win_flip"),
    (r"loses? life during your turn", "lose_turn"),
    (r"loses? life for the first time each turn", "lose_first"),
    (r"gains? or loses? life during your turn", "gain_lose_turn"),
    (r"(?:is|are) dealt damage", "dealt"),
    (r"(?:is|are) dealt noncombat damage", "dealt_noncombat"),
    (r"(?:is|are) dealt combat damage", "dealt_combat"),
    (rf"attacks? with (?P<q>one or more|{_COUNT} or more|exactly {_COUNT}) (?P<d>.+)", "attack_with"),
    (r"attacks? while creatures you control have total power (?P<p>\d+) or greater", "attack_power"),
]
_RAW = {"surveil": ("you_surveil",), "win_flip": ("you_win_flip",), "lose_turn": ("opp_loses_life",),
        "lose_first": ("opp_loses_life",), "gain_lose_turn": ("gain_life", "opp_loses_life"),
        "dealt": ("player_damaged",), "dealt_noncombat": ("player_damaged",), "dealt_combat": ("player_damaged",),
        "attack_with": ("you_attack",), "attack_power": ("you_attack",)}

# the fixed verbs go first: "loses life during your turn" must not be read as a longer match of "loses life"
cx_events._PLAYER_VERBS[0:0] = _VERBS
cx_events._PLAYER_RAW.update(_RAW)
cx_events._OBSERVED.update({"you_surveil", "you_win_flip", "player_damaged", "explores"})


def extend_spec(kind, vm, spec) -> bool:
    """Parse the extra parts of the attack verbs into ``spec``; False when the wording isn't understood."""
    if kind == "attack_power":
        spec["power"] = int(vm["p"])
        return True
    if kind != "attack_with":
        return True
    q = vm["q"]
    if q == "one or more":
        spec["min"], spec["exact"] = 1, False
    else:
        n = q.split()[1] if q.startswith("exactly") else q.split()[0]
        n = _N.get(n) or int(n)
        spec["min"], spec["exact"] = n, q.startswith("exactly")
    desc = vm["d"]
    other = desc.startswith("other ")
    desc = desc[6:] if other else desc
    if "~" in desc or "commander" in desc or " and " in desc and "and/or" not in desc:
        return False
    subj = cx_events._object_subject("one or more " + ("other " if other else "") + desc + " you control")
    if subj is None:
        subj = cx_events._object_subject("one or more " + ("other " if other else "") + desc)
    if subj is None:
        return False
    subj["ctrl"] = "you"
    spec["subject"] = subj
    return True


_REFS = re.compile(r"\b(?:those|them|the attacking|each of|that creature|those creatures)\b", re.I)


def attack_rest_ok(rest: str) -> bool:
    """The payoff may not talk about the attacking set ("those creatures get +2/+2"): the engine doesn't carry it."""
    return not _REFS.search(rest)


def player_ok(game, spec, actor, me, event, perm=None) -> bool:
    kind = spec["kind"]
    if kind == "attack_power":
        return sum(c.power for c in me.creatures) >= spec["power"]
    if kind == "attack_with":
        hits = [a for a in game.attackers if a.controller is me and cx_events._subject_ok(game, spec["subject"], perm, a)]
        if len(hits) < spec["min"] or (spec["exact"] and len(game.attackers) != spec["min"]):
            return False
        game.event_amount = len(hits)          # "that many" (reset by the combat code after the event)
        return True
    if kind in ("lose_turn", "gain_lose_turn"):
        return game.active is me
    if kind == "lose_first":
        return actor.life_lost_amount == (getattr(game, "event_amount", None) or 0)
    if kind == "dealt_noncombat":
        return not getattr(game, "event_combat", False)
    if kind == "dealt_combat":
        return bool(getattr(game, "event_combat", False))
    return True
