"""Damage prevention: shields on players and on permanents, applied before damage is dealt (deal_damage).

    {1}: The next time a black source of your choice would deal damage to you this turn, prevent that damage.
    If a white source would deal damage to you, prevent 2 of that damage.       (the Spheres, Orbs of Warding)
    If damage would be dealt to ~, prevent that damage. Remove a +1/+1 counter from ~.        (the Phantoms)
    If damage would be dealt to ~ while it has a +1/+1 counter on it, prevent that damage and remove that many
    +1/+1 counters from it.
    Prevent all (combat) damage that would be dealt to ~ (by creatures).
    The next time a source of your choice would deal damage to you this turn, prevent that damage.   (a spell)

A Circle of Protection is played as a reaction: when a matching source would deal damage to its controller and
they can pay the cost, they pay it and the damage is prevented (recorded as an approximation). The fields are
``CardDef.prevention``: a tuple of (kind, desc, n, cost).
"""
from __future__ import annotations

import re

KINDS = {"shield_you"}
_COLOR = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_DESC = r"(?:white|blue|black|red|green|black or red|artifact|creature)"


def parse_line(line: str, st) -> bool:
    from .cards.model import parse_mana_cost
    out = None
    m = re.fullmatch(rf"((?:\{{\d+\}}|\{{[WUBRG]\}})+): The next time an? ({_DESC} )?source of your choice would deal damage "
                     r"to you this turn, prevent that damage\.", line)
    if m:
        out = ("cop", (m[2] or "").strip(), 0, parse_mana_cost(m[1]))
        st.approximations.append("damage shield: paid automatically when a matching source would deal damage to you")
    m = m or re.fullmatch(rf"If an? (?:({_DESC}) )?(source|creature|artifact)( an opponent controls)? would deal damage to "
                          r"you, prevent (\d) of that damage\.", line)
    if m and out is None:
        desc = m[1] or ("" if m[2] == "source" else m[2])
        out = ("reduce", desc + ("|opp" if m[3] else ""), int(m[4]), None)
    if out is None:
        self_kind = _SELF.get(line)
        if self_kind:
            out = (self_kind, "", 0, None)
    if out is None:
        return False
    st.extra["prevention"] = st.extra.get("prevention", ()) + (out,)
    return True


_SELF = {
    "If damage would be dealt to ~, prevent that damage. Remove a +1/+1 counter from ~.": "phantom",
    "If damage would be dealt to ~ while it has a +1/+1 counter on it, prevent that damage and remove that many +1/+1 "
    "counters from it.": "counters_many",
    "If damage would be dealt to ~ while it has a +1/+1 counter on it, prevent that damage and remove a +1/+1 counter "
    "from it.": "counters_one",
    "Prevent all damage that would be dealt to ~.": "all",
    "Prevent all combat damage that would be dealt to ~.": "combat",
    "Prevent all damage that would be dealt to ~ by creatures.": "creatures",
    "If a creature would deal combat damage to ~, prevent that damage and put a +1/+1 counter on ~.": "hydra",
}
for _pronoun in ("it", "him", "her"):
    _SELF[f"If damage would be dealt to ~, prevent that damage and put that many +1/+1 counters on {_pronoun}."] = "grow"


EFFECT_PATTERNS = [
    (r"the next time a source of your choice would deal damage to you this turn, prevent that damage",
     lambda m: _effect("shield_you")),
]


def _effect(kind):
    from .cards import Effect
    return Effect(kind, target="none")


def resolve(game, p, eff, target, item):
    if eff.kind == "shield_you":
        p.damage_shields = getattr(p, "damage_shields", []) + [game.turn]


def _matches(source, desc: str, victim) -> bool:
    """Whether a damage source fits a description such as "black", "black or red", "artifact" or "creature|opp"."""
    desc, _, opp = desc.partition("|")
    card = getattr(source, "card", source)
    controller = getattr(source, "controller", None)
    if opp and controller is victim:
        return False
    if not desc:
        return source is not None
    if card is None:
        return False
    if desc in ("artifact", "creature"):
        return desc.capitalize() in getattr(card, "types", ())
    return bool(set(_COLOR[w] for w in desc.split(" or ")) & set(getattr(card, "colors", ())))


def adjust(game, target, amount: int, source, combat: bool) -> int:
    """The damage left after the prevention shields that apply to target."""
    from .engine.state import Permanent, Player
    if isinstance(target, Player):
        shields = getattr(target, "damage_shields", [])
        if game.turn in shields:
            shields.remove(game.turn)
            game.log(f"prevents {amount} damage", target)
            return 0
        for perm in list(target.battlefield):
            for kind, desc, n, cost in perm.card.prevention:
                if kind == "reduce" and _matches(source, desc, target):
                    amount -= n
                elif kind == "cop" and amount > 0 and _matches(source, desc, target) and game.can_pay(target, cost):
                    game.pay(target, cost)
                    game.log(f"{perm.card.name} prevents {amount} damage", target)
                    return 0
        return max(0, amount)
    if not isinstance(target, Permanent):
        return amount
    if getattr(target, "combat_shield_turn", None) == game.turn and combat:
        return 0
    for kind, _desc, _n, _cost in target.card.prevention:
        from_creature = isinstance(source, Permanent) and source.is_creature
        if kind == "all" or kind == "combat" and combat or kind == "creatures" and from_creature:
            return 0
        if kind == "phantom":
            if target.p1:
                target.counters["+1/+1"] = target.p1 - 1
            return 0
        if kind in ("counters_many", "counters_one") and target.p1:
            target.counters["+1/+1"] = max(0, target.p1 - (amount if kind == "counters_many" else 1))
            return 0
        if kind == "hydra" and combat and from_creature:
            target.counters["+1/+1"] = target.p1 + 1
            return 0
        if kind == "grow":
            target.counters["+1/+1"] = target.p1 + amount
            return 0
    return amount
