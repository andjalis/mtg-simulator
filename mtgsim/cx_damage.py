"""Divided damage: "~ deals N damage divided as you choose among one, two, or three targets." (Forked Bolt, Arc
Lightning, Pyrotechnics, Inferno Titan, Fury, Flameshot).

The division is chosen when the spell or ability is put on the stack (a Stack list that plans it on append): lethal
damage goes to the opponent's most valuable creatures and planeswalkers first, and what is left goes to the opponent's
face when players are legal targets, otherwise to the best creature still standing. On resolution each chosen
target that is still legal takes its share; shares for illegal targets are not dealt.
"""
from __future__ import annotations

import re


KINDS = {"divided_damage"}

_SCOPES = {"targets": "any", "target creatures": "creature", "target creatures and/or planeswalkers": "creature_pw"}
_COUNTS = {"one or two": 2, "one, two, or three": 3, "any number of": 99}



def _divided(m):
    from .cards import Effect
    return Effect("divided_damage", int(m[1]), target="none", data={"scope": _SCOPES[m[3]], "max": _COUNTS[m[2]]})


def _two_targets(first, second, flip=False):
    """Two damage effects with their own targets: (creature, player) or the reverse; "player or planeswalker" is
    played as the opponent."""
    def make(m):
        from .cards import Effect
        pair = {"creature": Effect("damage", int(m[1]), target="creature", filter="opp"),
                "player": Effect("damage", int(m[2]), target="player", filter="opp"),
                "mine": Effect("damage", int(m[2]), target="creature_mine")}
        if flip:
            pair["creature"] = Effect("damage", int(m[2]), target="creature", filter="opp")
            pair["player"] = Effect("damage", int(m[1]), target="player", filter="opp")
        return [pair[first], pair[second]]
    return make


EFFECT_PATTERNS = [
    (r"(?:~|it) deals (\d+) damage to target creature and (\d+) damage to target player or planeswalker",
     _two_targets("creature", "player")),
    (r"(?:~|it) deals (\d+) damage to target player or planeswalker and (\d+) damage to target creature",
     _two_targets("player", "creature", flip=True)),
    (r"(?:~|it) deals (\d+) damage to target creature you don't control and (\d+) damage to target creature you "
     r"control", _two_targets("creature", "mine")),
    (r"(?:~|it|he|she) deals (\d+) damage divided as you choose among (one or two|one, two, or three|any number of) "
     r"(targets|target creatures|target creatures and/or planeswalkers)", _divided),
]


def _note():
    from .cards import clauses
    clauses._SUB_NOTES.append((re.compile(r"damage to target creature and \d+ damage to target player or planeswalker|"
                                          r"damage to target player or planeswalker and \d+ damage to target creature",
                                          re.I),
                               "the player-or-planeswalker target is always the opponent"))


_note()


class Stack(list):
    """The game stack; a divided-damage item has its division chosen as it goes on the stack."""

    def __init__(self, game):
        super().__init__()
        self.game = game

    def append(self, item):
        super().append(item)
        for eff in item.effects:
            if eff.kind == "divided_damage":
                if not hasattr(item, "divided"):
                    item.divided = {}
                item.divided[id(eff)] = plan(self.game, item.controller, eff)


def plan(game, p, eff):
    """[[victim, amount], ...]: the chosen targets and how the damage is divided among them."""
    opp = game.opponent(p)
    scope = eff.data["scope"]
    pool = [x for x in opp.battlefield if game.targetable(x, p) and
            (x.is_creature or x.is_planeswalker and scope in ("any", "creature_pw"))]
    if scope == "creature":
        pool = [x for x in pool if x.is_creature]
    from .engine.policy import perm_value
    pool.sort(key=perm_value, reverse=True)
    left, limit, chosen = eff.amount, eff.data["max"], []
    for perm in pool:
        need = max(1, (perm.toughness - perm.damage) if perm.is_creature else perm.loyalty)
        if need <= left and len(chosen) < limit:
            chosen.append([perm, need])
            left -= need
    if left > 0:
        if scope == "any" and game.targetable(opp, p) and (len(chosen) < limit or not chosen):
            chosen.append([opp, left])
        elif chosen:
            chosen[0][1] += left
        elif pool and limit:
            chosen.append([pool[0], left])
        elif scope == "any":
            chosen.append([opp, left])
    return chosen


def resolve(game, p, eff, target, item):
    src = (item.source if item.source is not None else item.card) if item is not None else None
    chosen = getattr(item, "divided", {}).get(id(eff)) if item is not None else None
    if chosen is None:
        chosen = plan(game, p, eff)          # not put on the stack through game.stack: choose now
    from .engine.state import Permanent
    for victim, amount in chosen:
        if isinstance(victim, Permanent) and (victim not in victim.controller.battlefield or
                                               not game.targetable(victim, p)):
            continue                          # an illegal target: its share is not dealt
        game.deal_damage(victim, amount, by=p, cause=f"{getattr(src, 'name', None) or src.card.name}: damage",
                         source=src)
