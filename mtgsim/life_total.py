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

_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "twenty": 20}
_WHO = {"your": ("you", "none", ""), "target player's": ("target", "player", ""),
        "target opponent's": ("target", "player", "opp"), "each player's": ("each", "none", ""),
        "each opponent's": ("opponents", "none", "")}


def _double(m):
    from .cards.model import Effect
    who, target, flt = _WHO[m[1].lower()]
    return Effect("life_total", target=target, filter=flt, data={"op": "double", "who": who})


def _become(m):
    from .cards.model import Effect
    who, target, flt = _WHO[m[1].lower()]
    if who in ("each", "opponents"):
        from .cards.model import NO_MATCH
        return NO_MATCH
    n = int(m[2]) if m[2].isdigit() else _NUM[m[2].lower()]
    return Effect("life_total", n, target=target, filter=flt, data={"op": "set", "who": who})


def _exchange(m):
    from .cards.model import Effect
    return Effect("life_total", target="player", filter="opp" if m[1].lower() == "opponent" else "",
                  data={"op": "exchange", "who": "target"})


def _loses(m):
    from .cards.model import Effect
    return Effect("player_loses", target="player", filter="opp" if m[1].lower() == "opponent" else "")


EFFECT_PATTERNS = [
    (r"double (your|target player's|target opponent's|each player's|each opponent's) life total", _double),
    (r"(your|target player's|target opponent's) life total becomes (\d+|one|two|three|four|five|six|seven|eight|"
     r"nine|ten|twenty)", _become),
    (r"exchange life totals with target (player|opponent)", _exchange),
    (r"target (player|opponent) loses the game", _loses),
]
