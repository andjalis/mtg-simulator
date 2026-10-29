"""Amounts that depend on the event: "that much" life or damage, and replacement effects that change an amount.

    Whenever ~ is dealt damage, it deals that much damage to any target.            (Boros Reckoner)
    Whenever ~ deals damage, you lose that much life.                               (Emberwilde Caliph)
    Whenever ~ is dealt combat damage, you gain that much life.                     (Pious Warrior)
    Whenever an opponent loses life, you gain that much life.                       (Bloodthirsty Conqueror)
    Whenever you gain life, target opponent loses that much life.                   (Sanguine Bond)
    If you would gain life, you gain twice that much life instead. / ... that much life plus 1 instead.
    If an opponent would lose life during your turn, they lose twice that much life instead.
    If a source you control would deal damage to an opponent or a permanent an opponent controls, it deals that
    much damage plus 1 instead.            (also: noncombat, "another red source", "a spell", "minus 1")

An effect with ``data["that_much"]`` takes its amount from the event that triggered it: ``Game.event_amount`` is set
around the typed events in deal_damage and change_life and copied into the trigger when it is queued. The
replacement statics are stored in ``advanced_rules`` as ``lifegain_mod`` / ``loselife_mod`` (steps of
("add", n) or ("mul", n)) and ``damage_mod`` (dicts), and applied by ``gain_amount``, ``loss_amount`` and
``damage_amount``.
"""
from __future__ import annotations

import re

_SRC = r"(?:~|it|he|she)"

_NUM = {"1": 1, "2": 2, "3": 3, "one": 1, "two": 2, "three": 3}


def _that_much(kind, **kw):
    def make(m):
        from .cards import Effect
        return Effect(kind, 0, data={"that_much": True}, **kw)
    return make


def _damage(m):
    from .cards import Effect
    who = m[1]
    if who == "each player":
        return Effect("damage_each_player", 0, data={"that_much": True})
    target = "any" if who == "any target" else "creature" if who == "target creature" else "player"
    return Effect("damage", 0, target=target, data={"that_much": True})


EFFECT_PATTERNS = [
    (r"you gain that much life", _that_much("gain_life")),
    (r"you lose that much life", _that_much("lose_life")),
    (r"(?:target|each) opponent loses that much life", _that_much("drain", target="each_opponent")),
    (_SRC + r" deals that much damage to (any target|target opponent|target player|each opponent|each player|target creature)", _damage),
]

TRIGGERS = [
    (r"Whenever ~ deals damage, (.+)", ("deals_damage",)),
    (r"Whenever ~ is dealt combat damage, (.+)", ("dealt_combat_damage",)),
    (r"Whenever an opponent loses life, (.+)", ("opp_loses_life",)),
]


def parse_line(line: str, st) -> bool:
    rules = st.extra.setdefault("advanced_rules", {})
    m = re.fullmatch(r"If you would gain life, you gain (twice that much life|that much life plus (\w+)) instead\.", line)
    if m:
        step = ("mul", 2) if m[2] is None else ("add", _NUM.get(m[2], 0))
        if step[1]:
            rules.setdefault("lifegain_mod", []).append(step)
            return True
    if line == "If an opponent would lose life during your turn, they lose twice that much life instead.":
        rules.setdefault("loselife_mod", []).append(("mul", 2))
        return True
    m = re.fullmatch(r"If (?P<src>a source you control|another (?P<color>red|blue|white|black|green) source you control|"
                     r"a source|a spell|~) would deal (?P<nc>noncombat )?damage to (?P<who>an opponent or a permanent "
                     r"an opponent controls|a permanent or player|a creature you control), it deals that much damage "
                     r"(?P<op>plus|minus) (?P<n>\w+)(?: to that (?:permanent or player|creature))? instead\.", line)
    if m and m["n"] in _NUM:
        sign = 1 if m["op"] == "plus" else -1
        rules.setdefault("damage_mod", []).append({
            "source": "self" if m["src"] == "~" else "yours" if m["src"] == "a source you control" else
                      "spell" if m["src"] == "a spell" else "any" if m["src"] == "a source" else "other_" + m["color"],
            "noncombat": bool(m["nc"]),
            "to": {"an opponent or a permanent an opponent controls": "opp", "a permanent or player": "any",
                   "a creature you control": "my_creature"}[m["who"]],
            "delta": sign * _NUM[m["n"]]})
        return True
    return False


def _apply(amount, steps):
    for op, n in steps:
        if op == "add":
            amount += n
    for op, n in steps:
        if op == "mul":
            amount *= n
    return amount


def gain_amount(game, player, amount: int) -> int:
    """Life gained, after "you gain twice that much / that much plus 1" statics (additions first, then doubling)."""
    steps = [s for x in player.battlefield for s in x.card.advanced_rules.get("lifegain_mod", ())]
    return _apply(amount, steps) if steps else amount


def loss_amount(game, player, amount: int) -> int:
    """Life lost, after "if an opponent would lose life during your turn, they lose twice that much"."""
    opp = game.opponent(player)
    if opp is not game.active:
        return amount
    steps = [s for x in opp.battlefield for s in x.card.advanced_rules.get("loselife_mod", ())]
    return _apply(amount, steps) if steps else amount


_COLOR = {"red": "R", "blue": "U", "white": "W", "black": "B", "green": "G"}


def damage_amount(game, target, amount: int, by, source, combat: bool) -> int:
    """Damage after "it deals that much damage plus N instead" statics (several stack; never below 0)."""
    from .engine.state import Permanent
    from .cards import CardDef
    controller = source.controller if isinstance(source, Permanent) else by
    victim = target.controller if isinstance(target, Permanent) else target
    colors = source.card.colors if isinstance(source, Permanent) else \
        source.colors if isinstance(source, CardDef) else frozenset()
    for pl in game.players:
        for x in pl.battlefield:
            for mod in x.card.advanced_rules.get("damage_mod", ()):
                kind = mod["source"]
                if mod["noncombat"] and combat:
                    continue
                if kind == "self" and source is not x:
                    continue
                if kind == "yours" and controller is not pl:
                    continue
                if kind == "spell" and isinstance(source, Permanent):
                    continue
                if kind.startswith("other_") and (controller is not pl or source is x
                                                  or _COLOR[kind[6:]] not in colors):
                    continue
                if mod["to"] == "opp" and victim is not game.opponent(pl):
                    continue
                if mod["to"] == "my_creature" and not (isinstance(target, Permanent) and target.is_creature
                                                       and target.controller is pl):
                    continue
                amount += mod["delta"]
    return max(0, amount)
