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


def parse_line(line: str, st) -> bool:
    m = re.fullmatch(r"Cast (?:this spell|~) only (.+)", line)
    if not m:
        return False
    window = parse_window(m[1])
    if window is None:
        return False
    st.extra.setdefault("advanced_rules", {})["cast_window"] = window
    return True


def window_ok(game, p, card) -> bool:
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
