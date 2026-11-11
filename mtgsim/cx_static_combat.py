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


def forbidden(perm, action: str) -> bool:
    """Whether a "can't <action> unless" condition stops perm now."""
    rules = perm.card.advanced_rules.get("cx_combat_unless")
    if not rules or perm.abilities_suppressed:
        return False
    from .cx_condlib import holds_for
    return any(r[0] in (action, "both") and holds_for(perm, r[1]) == (len(r) > 2) for r in rules)
