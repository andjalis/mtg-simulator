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
_COUNTS = {"one or two": 2, "one, two, or three": 3, "any number of": 99, "up to two": 2, "up to three": 3,
           "up to four": 4, "up to five": 5, "up to six": 6, "up to seven": 7, "up to eight": 8}
_STATES = {"attacking": ("attacking",), "attacking or blocking": ("attacking", "blocking")}
_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def _who(text):
    """The recipients' words after "target": "creatures with flying", "attacking or blocking creatures without
    flying", "white and/or blue creatures", "creatures your opponents control" -> (scope, predicate) or None."""
    pred = {}
    text = text.strip()
    if text.endswith(" your opponents control"):
        text = text[:-len(" your opponents control")]
    m = re.fullmatch(r"(.+?) (with|without) flying", text)
    if m:
        pred["flying"] = m[2] == "with"
        text = m[1]
    m = re.fullmatch(r"(attacking or blocking|attacking) (.+)", text)
    if m:
        pred["states"] = _STATES[m[1]]
        text = m[2]
    m = re.fullmatch(r"(white|blue|black|red|green) and/or (white|blue|black|red|green) (.+)", text)
    if m:
        pred["colors"] = (_COLORS[m[1]], _COLORS[m[2]])
        text = m[3]
    scope = {"creatures": "creature", "creatures and/or planeswalkers": "creature_pw"}.get(text)
    if scope is None or (pred and scope != "creature"):
        return None
    return scope, pred


def _matches(game, perm, pred) -> bool:
    if "flying" in pred and bool(perm.has("flying")) != pred["flying"]:
        return False
    if "states" in pred:
        now = {"attacking": perm in game.attackers,
               "blocking": any(perm in bl for bl in game.blocks.values())}
        if not any(now[st] for st in pred["states"]):
            return False
    if "colors" in pred and not any(c in perm.card.colors for c in pred["colors"]):
        return False
    return True


def _divided(m):
    from .cards import Effect
    from .cards.model import NO_MATCH
    amount, count, recipients = m["n"].lower(), m["cnt"].lower(), m["who"]
    if recipients in _SCOPES:
        scope, pred = _SCOPES[recipients], {}
    else:
        who = _who(recipients[len("target "):]) if recipients.startswith("target ") else None
        if who is None:
            return NO_MATCH
        scope, pred = who
    data = {"scope": scope, "max": _COUNTS[count]}
    if pred:
        data["pred"] = pred
    if amount == "x":
        data["x"] = True
    plus = m.groupdict().get("plus")
    if plus:
        if amount != "x":
            return NO_MATCH
        data["plus"] = _PLUS[plus.lower()]      # "X plus 1 damage" (Meteor Shower): added to the X paid
    return Effect("divided_damage", 0 if amount == "x" else int(amount), target="none", data=data)


_PLUS = {"1": 1, "one": 1, "2": 2, "two": 2, "3": 3, "three": 3}


def _as_you_cast(m):
    """"..., where X is <quantity> as you cast ~": the division and its total are fixed when the spell goes on the
    stack (Stack.append plans it), which is when "as you cast" reads the quantity."""
    import dataclasses
    from .cards.clauses import _xq
    from .cards.model import NO_MATCH
    spec = _xq(m["q"])
    eff = _divided(m)
    if spec is None or eff is NO_MATCH or not eff.data.get("x") or eff.data.get("plus") or \
            not isinstance(spec, tuple) or spec[0] in ("this_way", "prev", "spell", "sac"):
        return NO_MATCH
    data = {k: v for k, v in eff.data.items() if k != "x"}
    return dataclasses.replace(eff, amount=1, data=dict(data, xq=spec))


def _equal_to(m):
    """"<source> deals damage equal to <quantity> divided as you choose among ...": the same as "deals X damage
    divided as you choose among ..., where X is <quantity>" (Orca, Siege Demon)."""
    from .cards import _parse_effects
    from .cards.model import NO_MATCH
    if re.search(r"\bX\b", m[0]):
        return NO_MATCH
    new, bad = _parse_effects(f"{m['s']} deals X damage divided as you choose among {m['rest']}, where X is {m['q']}.")
    if bad or len(new) != 1 or new[0].kind != "divided_damage" or not new[0].data.get("xq"):
        return NO_MATCH
    return new[0]


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
    (r"(?:~|it|he|she) deals (?P<n>\d+|x)(?: plus (?P<plus>1|one|2|two|3|three))? damage divided as you choose among "
     r"(?P<cnt>one or two|one, two, or three|any number of|up to (?:two|three|four|five|six|seven|eight)) "
     r"(?P<who>targets|target [^,.]+?)", _divided),
    (r"(?:~|it|he|she) deals (?P<n>x) damage divided as you choose among (?P<cnt>one or two|one, two, or three|any "
     r"number of|up to (?:two|three|four|five|six|seven|eight)) (?P<who>targets|target [^,.]+?), where x is "
     r"(?P<q>.+?) as you cast ~", _as_you_cast),
    (r"(?P<s>~|it|he|she) deals damage equal to (?P<q>(?:(?!divided).)+?) divided as you choose among (?P<rest>.+)",
     _equal_to),
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
                item.divided[id(eff)] = plan(self.game, item.controller, eff, item)
        if any(eff.kind == "divided_prevent" for eff in item.effects):
            from .divided_prevent import plan_item          # "... divided as you choose" shields (#333)
            plan_item(self.game, item)


def plan(game, p, eff, item=None):
    """[[victim, amount], ...]: the chosen targets and how the damage is divided among them."""
    opp = game.opponent(p)
    scope = eff.data["scope"]
    total = eff.amount
    if eff.data.get("x"):                      # X paid for the spell or ability
        total = getattr(item, "x", 0) or 0
    elif eff.data.get("xq") and item is not None and "xq_base" not in eff.data:
        # ", where X is the number of Mountains you control" (once: Game.resolve has already applied it when it
        # marked xq_base)
        total = eff.amount * game.x_quantity(p, eff.data["xq"], item, None)
    total += eff.data.get("plus", 0)
    pred = eff.data.get("pred", {})
    pool = [x for x in opp.battlefield if game.targetable(x, p) and _matches(game, x, pred) and
            (x.is_creature or x.is_planeswalker and scope in ("any", "creature_pw"))]
    if scope == "creature":
        pool = [x for x in pool if x.is_creature]
    from .engine.policy import perm_value
    pool.sort(key=perm_value, reverse=True)
    left, limit, chosen = total, eff.data["max"], []
    for perm in pool:
        need = max(1, (perm.toughness - perm.damage) if perm.is_creature else perm.loyalty)
        if need <= left and len(chosen) < limit:
            chosen.append([perm, need])
            left -= need
    if left > 0:
        if scope == "any" and _legal(game, p, opp) and (len(chosen) < limit or not chosen):
            chosen.append([opp, left])
        elif chosen:
            chosen[0][1] += left
        elif pool and limit:
            chosen.append([pool[0], left])
        elif scope == "any" and _legal(game, p, opp):
            chosen.append([opp, left])
    return chosen


def _legal(game, p, victim) -> bool:
    """Whether p may still target victim: a permanent must be on the battlefield and targetable, a
    player must not have hexproof or shroud (CR 608.2b)."""
    from .engine.state import Permanent
    if isinstance(victim, Permanent):
        return victim in victim.controller.battlefield and game.targetable(victim, p)
    from .batch1_templates import player_targetable
    return player_targetable(game, victim, p)


def _planned(eff, item):
    """The effect as it was put on the stack: Game.resolve hands the handler a copy with its counted amount applied
    (data["xq_base"]), and the division chosen at cast is keyed on the original."""
    if any(e is eff for e in item.effects):
        return eff
    data = {k: v for k, v in eff.data.items() if k != "xq_base"}
    return next((e for e in item.effects if e.kind == eff.kind and e.data == data), eff)


def resolve(game, p, eff, target, item):
    src = (item.source if item.source is not None else item.card) if item is not None else None
    chosen = getattr(item, "divided", {}).get(id(_planned(eff, item))) if item is not None else None
    if chosen is None:
        chosen = plan(game, p, eff, item)    # not put on the stack through game.stack: choose now
    for victim, amount in chosen:
        if not _legal(game, p, victim):
            continue                          # an illegal target (a player with new hexproof too): its share is not dealt
        game.deal_damage(victim, amount, by=p, cause=f"{getattr(src, 'name', None) or src.card.name}: damage",
                         source=src)


def ai_worth(ai, game, me, eff, card, instant):
    """HeuristicAI's value of casting a divided-damage spell now: the creatures and planeswalkers its planned division
    kills plus what the damage to the opponent's face is worth, or None to hold it (nothing of theirs dies and no
    damage reaches them; at instant speed only when something dies)."""
    from types import SimpleNamespace
    from .engine.policy import perm_value
    stub = SimpleNamespace(source=None, card=card, x=0, context=None, controller=me, targets=[], effects=[eff])
    chosen = plan(game, me, eff, stub)
    opp, value, kills = game.opponent(me), 0.0, 0
    for victim, amount in chosen:
        if victim is opp:
            value += ai.face_value(game, me, amount)
        elif victim.controller is not me:
            dies = victim.toughness - victim.damage <= amount if victim.is_creature else victim.loyalty <= amount
            if dies and not victim.has("indestructible"):
                value, kills = value + perm_value(victim) + 1, kills + 1
    if value <= 0 or (instant and not kills and value < 1000.0):
        return None
    return value
