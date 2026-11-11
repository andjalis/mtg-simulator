"""Attack and block restrictions with a condition:

    ~ can't attack unless you control another artifact.
    ~ can't attack unless there are seven or more cards in your graveyard.
    ~ can't attack unless you've cast a creature spell this turn.
    ~ can't attack unless defending player controls a creature with flying.
    ~ can't block unless you control a Vampire.
    ~ can't attack if defending player controls an untapped creature with power 3 or greater.
    ~ can't attack or block unless you control a Goblin or Orc.

The condition is a ``cx_condlib`` code read from the creature itself; with two players "defending player" is the
opponent. Stored as ``advanced_rules["cx_combat_unless"]`` = ((what, code), ...) with what "attack", "block" or
"both"; ``forbidden`` is called from ``Permanent.can_attack`` and ``can_block``. "Can't attack or block unless COND"
lines the older ``cx_conditions`` reader takes never reach this module. Restrictions with a price ("unless you pay
{N}", "unless you sacrifice a land") are left unparsed.
"""
from __future__ import annotations

import re

_LINE = re.compile(r"(?:[A-Z][\w' ]* — )?~ can't (attack|block|attack or block) (unless|if) (.+)\.")


def _phrase(text: str) -> str:
    text = text.replace("attacking player", "defending player")     # two players: either is the opponent
    text = re.sub(r"\bdefending player (controls|is|has)\b", r"an opponent \1", text)
    # "a Goblin or Orc", "another Wolf or Werewolf": the determiner carries over to the second noun
    return re.sub(r"\b(an?|another) ([A-Z]\w+) or ([A-Z]\w+)\b",
                  lambda m: f"{m[1]} {m[2]} or {m[1] if m[1] == 'another' else _art(m[3])} {m[3]}", text)


def _art(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def parse_line(line: str, st) -> bool:
    if "Creature" in st.types:
        group = _group_clause(line)
        if group:
            rules = st.extra.setdefault("advanced_rules", {})
            rules["cx_combat_group"] = rules.get("cx_combat_group", ()) + (group,)
            return True
    m = _LINE.fullmatch(line)
    if not m or "Creature" not in st.types:
        return False
    if re.match(r"(?:you|defending player|its controller) (?:pay|sacrifice|return|tap|discard)", m[3]):
        return False                    # a price, not a condition
    from .cx_condlib import as_static
    code = as_static(_phrase(m[3]))
    if not code:
        return False
    what = {"attack": "attack", "block": "block"}.get(m[1], "both")
    rules = st.extra.setdefault("advanced_rules", {})
    # a third item marks the "can't attack if COND" form: forbidden while COND holds
    entry = (what, code) if m[2] == "unless" else (what, code, True)
    rules["cx_combat_unless"] = rules.get("cx_combat_unless", ()) + (entry,)
    return True


def _group_clause(line):
    """Restrictions on the whole declaration, rather than on an eligible creature."""
    m = re.fullmatch(r"~ can (?:(?:attack|block) only|only (?:attack|block)) alone\.", line)
    if m:
        return ("attack" if "attack" in line else "block", ("alone",))
    m = re.fullmatch(r"~ can't (attack|block) unless at least (\w+) other creatures (?:attack|block)\.", line)
    if m:
        from .cards.model import NUMBERS
        n = int(m[2]) if m[2].isdigit() else NUMBERS.get(m[2])
        if n is not None and line.endswith(m[1] + "."):
            return m[1], ("others", n)
    m = re.fullmatch(r"~ can't (attack|block) unless a creature with greater power also (attacks|blocks)\.", line)
    if m and m[2] == m[1] + "s":
        return m[1], ("greater_power",)
    m = re.fullmatch(r"~ can't (attack|block) unless a (black|blue|green|red|white)(?: or (black|blue|green|red|white))? "
                     r"creature also (attacks|blocks)\.", line)
    if m and m[4] == m[1] + "s":
        colors = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
        return m[1], ("color", tuple(colors[c] for c in (m[2], m[3]) if c))
    return None


def declaration_group(creatures, action):
    """Drop illegal members until the proposed declaration satisfies its group restrictions.

    A companion must actually be declared, not merely be on the battlefield. For
    blocks this group contains distinct blockers across all attacking creatures.
    Removing one creature can invalidate the companions that depended on it.
    """
    group = list(dict.fromkeys(creatures))
    while True:
        legal = [c for c in group if _group_ok(c, group, action)]
        if legal == group:
            return legal
        group = legal


def _group_ok(perm, group, action):
    if perm.abilities_suppressed:
        return True
    rules = perm.card.advanced_rules
    if len(group) == 1 and (rules.get("no_solo") or action == "attack" and rules.get("no_solo_attack")):
        return False
    others = [c for c in group if c is not perm]
    for what, spec in rules.get("cx_combat_group", ()):
        if what != action:
            continue
        if spec[0] == "alone" and others:
            return False
        if spec[0] == "others" and len(others) < spec[1]:
            return False
        if spec[0] == "greater_power" and not any(c.power > perm.power for c in others):
            return False
        if spec[0] == "color" and not any(c.card.colors & set(spec[1]) for c in others):
            return False
    return True


def forbidden(perm, action: str) -> bool:
    """Whether a "can't <action> unless" condition stops perm now."""
    rules = perm.card.advanced_rules.get("cx_combat_unless")
    if not rules or perm.abilities_suppressed:
        return False
    from .cx_condlib import holds_for
    return any(r[0] in (action, "both") and holds_for(perm, r[1]) == (len(r) > 2) for r in rules)
