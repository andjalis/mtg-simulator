"""Activation restrictions beyond "as a sorcery": "Activate only during your turn, before attackers are
declared", "only if ~ is attacking", "only if there are seven or more cards in your graveyard", and so on.

`strip` peels one "Activate only ..." sentence off an ability body; the restrictions it recognises become
`Activated.restrictions` codes, checked by `allowed` whenever the ability is activated."""
from __future__ import annotations

import re

from .cards.model import _num

_N = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
_PRE_ATTACK = ("untap", "upkeep", "draw", "main1")
_COMBAT = ("declare_attackers", "declare_blockers", "combat_damage", "end_combat")

# (pattern, code). Matched against one "and only"-separated atom with "Activate only" removed.
_ATOMS = [
    (r"during your turn, before attackers are declared", "pre_attack:mine"),
    (r"before attackers are declared", "pre_attack"),
    (r"before blockers are declared", "pre_blockers"),
    (r"during your turn", "your_turn"),
    (r"during your upkeep", "my_upkeep"),
    (r"during any upkeep step", "upkeep"),
    (r"during combat", "combat"),
    (r"during the declare blockers step", "step:declare_blockers"),
    (r"during the end of combat step", "step:end_combat"),
    (r"if (?:~|this creature) is attacking", "attacking"),
    (rf"if there are {_N} or more cards in your graveyard", "gy>={0}"),
    (rf"if there are {_N} or more card types among cards in your graveyard", "gy_types>={0}"),
    (rf"if creatures you control have total power {_N} or greater", "total_power>={0}"),
    (rf"if you control {_N} or more (artifacts|lands|creatures|enchantments|snow permanents)", "control>={0}:{1}"),
    (r"if you control an? (Swamp|Island|Forest|Mountain|Plains)", "control>=1:{0}"),
    (r"if you control a legendary creature", "control>=1:legendary creature"),
    (r"if you control a creature with flying", "control>=1:flying creature"),
    (rf"if you control a creature with power {_N} or greater", "power_creature>={0}"),
    (r"if a creature died this turn", "creature_died"),
    (rf"if an opponent has {_N} or more poison counters", "opp_poison>={0}"),
    (r"if you have no cards in hand", "empty_hand"),
    (rf"if (?:~|this creature)'s power is {_N} or greater", "self_power>={0}"),
    (r"if you attacked this turn", "attacked"),
    (r"as an? instant", None),
]
_COMPILED = [(re.compile(p, re.I), c) for p, c in _ATOMS]
_SENTENCE = re.compile(r"(.+?\.) Activate only (.+?)\.", re.S)


def strip(body: str):
    """(body without the restriction, restriction codes, sorcery, once, once_game) or None."""
    m = _SENTENCE.fullmatch(body)
    if m is None:
        return None
    codes, sorcery, once, once_game = [], False, False, False
    for atom in re.split(r" and only ", m[2]):
        if atom == "as a sorcery":
            sorcery = True
        elif atom == "once each turn":
            once = True
        elif atom == "once":
            once_game = True
        else:
            for pat, code in _COMPILED:
                a = pat.fullmatch(atom)
                if a:
                    if code is not None:
                        codes.append(code.format(*[str(_num(g)) if g.isalpha() and g.lower() in _WORDS else g
                                                   for g in a.groups()]))
                    break
            else:
                return None
    return m[1], tuple(codes), sorcery, once, once_game


_WORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"}


def _control(p, noun: str) -> int:
    if noun == "snow permanents":
        return sum(x.card.snow for x in p.battlefield)
    if noun == "legendary creature":
        return sum(x.is_creature and x.card.legendary for x in p.battlefield)
    if noun == "flying creature":
        return sum(x.is_creature and x.has("flying") for x in p.battlefield)
    if noun in ("Swamp", "Island", "Forest", "Mountain", "Plains"):
        return sum(noun in x.card.subtypes for x in p.battlefield)
    kind = noun[:-1].capitalize()
    return sum(kind in x.card.types for x in p.battlefield)


def allowed(game, p, perm, codes) -> bool:
    for code in codes:
        name, _, rest = code.partition(">=")
        n = int(rest.split(":")[0]) if rest else 0
        if name == "pre_attack:mine":
            ok = p is game.active and game.step in _PRE_ATTACK
        elif name == "pre_attack":
            ok = game.step in _PRE_ATTACK
        elif name == "pre_blockers":
            ok = game.step in _PRE_ATTACK + ("declare_attackers",)
        elif name == "your_turn":
            ok = p is game.active
        elif name == "my_upkeep":
            ok = p is game.active and game.step == "upkeep"
        elif name == "upkeep":
            ok = game.step == "upkeep"
        elif name == "combat":
            ok = game.step in _COMBAT
        elif name.startswith("step:"):
            ok = game.step == name[5:]
        elif name == "attacking":
            ok = perm in game.attackers
        elif name == "gy":
            ok = len(p.graveyard) >= n
        elif name == "gy_types":
            ok = len({t for c in p.graveyard for t in c.types}) >= n
        elif name == "total_power":
            ok = sum(x.power for x in p.creatures) >= n
        elif name == "control":
            ok = _control(p, rest.split(":", 1)[1]) >= n
        elif name == "power_creature":
            ok = any(x.power >= n for x in p.creatures)
        elif name == "creature_died":
            ok = bool(getattr(game, "creature_died_turn", False))
        elif name == "opp_poison":
            ok = any(o.counters.get("poison", 0) >= n for o in game.players if o is not p)
        elif name == "empty_hand":
            ok = not p.hand
        elif name == "self_power":
            ok = perm.power >= n
        elif name == "attacked":
            ok = p.attacked_with > 0
        else:
            ok = True
        if not ok:
            return False
    return True
