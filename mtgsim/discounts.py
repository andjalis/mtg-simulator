"""Conditional and per-count cost reductions: "~ costs {2} less to cast if a creature died this turn",
"~ costs {1} less to cast for each attacking creature", "~ costs {1} less to cast if it targets a blocking creature".

parse_condition / parse_per turn the oracle clause into a key stored on the CardDef (`cond_discount`,
`per_discount`); `holds` / `count` evaluate the key when the cost is computed (costs.cost_of).
Only generic reductions are modelled; colored reductions and "more to cast" are left to the ignored lines.
"""
from __future__ import annotations

import re

_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}

_CONDS = [
    (r"a creature died this turn", "creature_died"),
    (r"you've cast another spell this turn", "cast_other_spell"),
    (r"you control a legendary creature", "legendary_creature"),
    (r"you control a creature with (flying|trample|deathtouch|reach)", lambda m: f"ctl_kw:{m[1]}"),
    (r"your opponents control (\w+) or more creatures", lambda m: f"opp_creatures>={_NUM[m[1]]}" if m[1] in _NUM else None),
    (r"there are four or more card types among cards in your graveyard", "delirium"),
    (r"it targets an? (attacking|blocking|tapped) creature", lambda m: f"targets:{m[1]}"),
    (r"it targets a creature with (flying)", lambda m: f"targets:{m[1]}"),
    (r"it targets an? (white|blue|black|red|green) (?:creature|permanent)", lambda m: f"targets:color:{m[1]}"),
    (r"it targets an? ([A-Z][a-z]+)", lambda m: f"targets:sub:{m[1]}"),
]

_PER = [
    (r"attacking creature", "attacking"),
    (r"creature that attacked this turn", "attacked"),
    (r"creature you control with power (\d+) or greater", lambda m: f"power>={m[1]}"),
    (r"color among permanents you control", "colors"),
    (r"creature in your party", "party"),
]


def _match(table, text):
    for rx, key in table:
        m = re.fullmatch(rx, text.strip())
        if m:
            return key(m) if callable(key) else key
    return None


def parse_condition(text: str):
    return _match(_CONDS, text)


def parse_per(text: str):
    return _match(_PER, text)


def holds(game, p, card, key: str) -> bool:
    if key == "creature_died":
        return game.creature_died_turn
    if key == "cast_other_spell":
        counts = getattr(game, "spells_cast", {})
        return counts.get("turn") == game.turn and counts.get(p.name, 0) >= 1
    if key.startswith("ctl_kw:"):
        return any(c.has(key[7:]) for c in p.creatures)
    if key == "legendary_creature":
        return any(c.card.legendary for c in p.creatures)
    if key.startswith("opp_creatures>="):
        return len(game.opponent(p).creatures) >= int(key.split(">=")[1])
    if key == "delirium":
        kinds = set()
        for c in p.graveyard:
            kinds |= set(c.types)
        return len(kinds) >= 4
    if key.startswith("targets:"):
        return any(_target_fits(game, t, key[8:]) for t in game.discount_targets(p, card))
    return False


def _target_fits(game, t, what: str) -> bool:
    if what.startswith("sub:"):
        return what[4:] in t.card.subtypes
    if what.startswith("color:"):
        return {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}[what[6:]] in t.card.colors
    return (what == "attacking" and t in game.attackers) or \
        (what == "blocking" and any(t in bl for bl in game.blocks.values())) or \
        (what == "tapped" and t.tapped) or (what == "flying" and t.has("flying"))


def count(game, p, key: str) -> int:
    if key == "attacking":
        return len(game.attackers)
    if key == "attacked":
        return p.attacked_with
    if key.startswith("power>="):
        return sum(c.power >= int(key[7:]) for c in p.creatures)
    if key == "colors":
        seen = set()
        for x in p.battlefield:
            seen |= set(x.card.colors)
        return len(seen)
    if key == "party":
        return party_size(p)
    return 0


def party_size(p) -> int:
    """Up to one each of Cleric, Rogue, Warrior and Wizard among p's creatures (a changeling fills any one slot)."""
    roles = ("Cleric", "Rogue", "Warrior", "Wizard")
    fits = [set(roles) if c.card.changeling else {r for r in roles if r in c.card.subtypes} for c in p.creatures]
    fits = [f for f in fits if f]

    def best(i, used):
        if i == len(roles):
            return 0
        out = best(i + 1, used)
        for j, f in enumerate(fits):
            if roles[i] in f and j not in used:
                out = max(out, 1 + best(i + 1, used | {j}))
                if out == len(roles) - i:
                    break
        return out
    return best(0, frozenset())
