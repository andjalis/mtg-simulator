"""Life totals as numbers (#629): double, set, exchange, and "that player loses the game".

    Double target player's life total.                       (Beacon of Immortality)
    Double your life total.
    Your life total becomes 1.  /  Target player's life total becomes 10.
    Exchange life totals with target player.                 (Psychic Transfer-like single exchanges)
    Target player loses the game.

Setting a life total is gaining or losing the difference (rule 119.5), so it goes through Game.change_life and its
replacement effects. "Exchange" with a player target is the same two moves, one each way.
"""
from __future__ import annotations

import re

_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "twenty": 20}
_WHO = {"your": ("you", "none", ""), "target player's": ("target", "player", ""),
        "target opponent's": ("target", "player", "opp"), "each player's": ("each", "none", ""),
        "each opponent's": ("opponents", "none", ""),
        "its controller's": ("target", "that_controller", "")}     # Celestial Mantle: the enchanted creature's controller


def _double(m):
    from .cards.model import Effect
    who, target, flt = _WHO[m[1].lower()]
    return Effect("life_total", target=target, filter=flt, data={"op": "double", "who": who})


def _become(m):
    from .cards.model import Effect
    who, target, flt = _WHO[m[1].lower()]
    extreme = re.fullmatch(r"the (lowest|highest) life total among all players", m[2], re.I)
    if extreme:     # Repay in Kind, The Darkhold, Arbiter of Knollridge: read as the effect resolves
        return Effect("life_total", target=target, filter=flt, data={"op": extreme[1].lower(), "who": who})
    if who in ("each", "opponents"):
        from .cards.model import NO_MATCH
        return NO_MATCH
    n = int(m[2]) if m[2].isdigit() else _NUM[m[2].lower()]
    return Effect("life_total", n, target=target, filter=flt, data={"op": "set", "who": who})


def _exchange(m):
    from .cards.model import Effect
    return Effect("life_total", target="player", filter="opp" if m[1].lower() == "opponent" else "",
                  data={"op": "exchange", "who": "target"})


def _exchange_more(m):
    """"[You may] exchange life totals with target opponent" (Mister Negative) and "[you may have] two target players
    exchange life totals" (Soul Conduit, Axis of Mortality): with two players the two targets are you and the other
    player, so you must be a legal target too ("both"); "you may": only when it gains you life ("may")."""
    from .cards.model import Effect
    both = m["two"] is not None
    return Effect("life_total", target="player", filter="" if both else ("opp" if m["who"] == "opponent" else ""),
                  data={"op": "exchange", "who": "target", "both": both, "may": bool(m["may"])})


def _loses(m):
    from .cards.model import Effect
    return Effect("player_loses", target="player", filter="opp" if m[1].lower() == "opponent" else "")


def _loses_ref(m):
    """"That player / its controller / defending player loses the game": the player the trigger is about (Vorpal
    Sword's granted "... that player loses the game")."""
    from .cards.model import Effect
    return Effect("player_loses", target={"that player": "that_player", "its controller": "that_controller",
                                          "defending player": "that_player"}[m[1].lower()])


EFFECT_PATTERNS = [
    (r"double (your|target player's|target opponent's|each player's|each opponent's|its controller's) life total",
     _double),
    (r"(your|target player's|target opponent's) life total becomes (\d+|one|two|three|four|five|six|seven|eight|"
     r"nine|ten|twenty)", _become),
    (r"(each player's) life total becomes (the (?:lowest|highest) life total among all players)", _become),
    (r"exchange life totals with target (player|opponent)", _exchange),
    (r"(?P<may>you may (?:have )?)?(?:exchange life totals with target (?P<who>player|opponent)|"
     r"(?P<two>two target players exchange life totals))", _exchange_more),
    (r"target (player|opponent) loses the game", _loses),
    (r"(that player|its controller|defending player) loses the game", _loses_ref),
]
