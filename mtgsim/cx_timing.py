"""Casting windows: "Cast this spell only during the declare attackers step and only if you've been attacked this
step." (Assassin's Blade, Heavy Fog), "only during combat before blockers are declared", "only before the combat
damage step", "only after combat", "only during your end step", "only during an opponent's turn".

The restriction is stored in ``advanced_rules["cast_window"]`` as ``(steps, turn, attacked)``: the steps the spell may
be cast in (None for any), whose turn ("mine", "theirs" or None) and whether the caster must be under attack.
``window_ok`` is checked by ``advanced_templates.cast_allowed``. Wordings that need other state ("only if a creature
died this turn", "only if you control two or more Vampires") stay unparsed.
"""
from __future__ import annotations

import re

_ALL = ("untap", "upkeep", "draw", "main1", "declare_attackers", "declare_blockers", "combat_damage", "end_combat",
        "main2", "end_step")
_COMBAT = ("declare_attackers", "declare_blockers", "combat_damage", "end_combat")
_PRE_ATTACK = ("untap", "upkeep", "draw", "main1")
_PRE_BLOCK = _PRE_ATTACK + ("declare_attackers",)

# (phrase, steps, turn, attacked); phrases are removed from the text as they match, longest first
_PHRASES = [
    (r"during combat after blockers are declared", ("declare_blockers", "combat_damage"), None, False),
    (r"during combat before blockers are declared", ("declare_attackers",), None, False),
    (r"before combat or during combat before blockers are declared", _PRE_BLOCK, None, False),
    (r"during the declare attackers step", ("declare_attackers",), None, False),
    (r"during your declare attackers step", ("declare_attackers",), "mine", False),
    (r"during the declare blockers step", ("declare_blockers",), None, False),
    (r"before the combat damage step", _PRE_BLOCK + ("declare_blockers",), None, False),
    (r"before blockers are declared", _PRE_BLOCK, None, False),
    (r"before attackers are declared", _PRE_ATTACK, None, False),
    (r"during an opponent's turn after their upkeep step", _ALL[2:], "theirs", False),
    (r"during an opponent's upkeep", ("upkeep",), "theirs", False),
    (r"during your end step", ("end_step",), "mine", False),
    (r"during combat", _COMBAT, None, False),
    (r"after combat", ("main2", "end_step"), None, False),
    (r"during an opponent's turn", None, "theirs", False),
    (r"on an opponent's turn", None, "theirs", False),
    (r"during your turn", None, "mine", False),
    (r"if you've been attacked this step", None, None, True),
]


def parse_window(text: str):
    """``(steps, turn, attacked)`` for the text after "Cast this spell only ", or None if any of it is unknown."""
    rest = text.lower().rstrip(". ")
    steps, turn, attacked = None, None, False
    for phrase, st, who, att in _PHRASES:
        if phrase not in rest:
            continue
        rest = rest.replace(phrase, "", 1)
        if st is not None:
            steps = tuple(s for s in st if steps is None or s in steps)
        if who is not None:
            if turn not in (None, who):
                return None
            turn = who
        attacked = attacked or att
    if re.sub(r"\b(?:and|only|the|,)\b|[\s,]", "", rest):
        return None
    if steps is None and turn is None and not attacked:
        return None
    return steps, turn, attacked


_N = {"two": 2, "three": 3, "four": 4}


def parse_condition(text: str):
    """The state test behind "Cast this spell only if <text>.", or None."""
    t = text.strip().rstrip(".")
    if t == "you control a snow land":
        return ("snow_land",)
    if t == "a creature is attacking you":
        return ("attacked_now",)
    if t == "you control fewer creatures than each opponent":
        return ("fewer_creatures",)
    if t == "you've cast another spell this turn":
        return ("another_spell",)
    m = re.fullmatch(r"you control (two|three|four) or more ([A-Z][a-z]+)s", t)
    if m:
        return ("tribe", m[2], _N[m[1]])
    m = re.fullmatch(r"no permanents named (.+) are on the battlefield", t)
    if m:
        return ("no_named", m[1])
    return None


def parse_line(line: str, st) -> bool:
    cond = re.fullmatch(r"Cast (?:this spell|~) only if (.+)", line)
    if cond and parse_condition(cond[1]) is not None:
        rules = st.extra.setdefault("advanced_rules", {})
        rules["cast_if"] = rules.get("cast_if", ()) + (parse_condition(cond[1]),)
        return True
    m = re.fullmatch(r"Cast (?:this spell|~) only (.+)", line)
    if not m:
        return False
    window = parse_window(m[1])
    if window is None:
        return False
    st.extra.setdefault("advanced_rules", {})["cast_window"] = window
    return True


def _condition_ok(game, p, card, cond) -> bool:
    kind = cond[0]
    if kind == "snow_land":
        return any(x.card.is_land and x.card.snow for x in p.battlefield)
    if kind == "attacked_now":
        return game.active is not p and any(game.attack_targets.get(a) is p for a in game.attackers)
    if kind == "fewer_creatures":
        return all(len(p.creatures) < len(o.creatures) for o in game.players if o is not p)
    if kind == "another_spell":
        return game.spells_cast_turn(p) >= 1
    if kind == "tribe":
        return sum(cond[1] in x.card.subtypes for x in p.battlefield) >= cond[2]
    if kind == "no_named":
        return not any(x.card.name == cond[1] or x.card.name == card.name for pl in game.players
                       for x in pl.battlefield)
    return True


def window_ok(game, p, card) -> bool:
    if any(not _condition_ok(game, p, card, c) for c in card.advanced_rules.get("cast_if", ())):
        return False
    window = card.advanced_rules.get("cast_window")
    if window is None:
        return True
    steps, turn, attacked = window
    if steps is not None and game.step not in steps:
        return False
    if turn == "mine" and game.active is not p or turn == "theirs" and game.active is p:
        return False
    if attacked and not (game.active is not p and any(game.attack_targets.get(a) is p for a in game.attackers)):
        return False
    return True
