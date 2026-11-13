"""Static abilities found on Pilot and Spirit tokens (#375), also printed on cards:

    ~ can't block or be blocked by non-Spirit creatures.        both evasion rules of cx_grammar_evasion
    ~ saddles Mounts and crews Vehicles as though its power were 2 greater.
    ~ crews Vehicles as though its power were 2 greater.

The crew/saddle line is a face-line parser (``parse_line``, hooked in cards/face_lines.py) recording
``advanced_rules["crew_bonus"]`` / ``["saddle_bonus"]``; ``crew_power(perm, saddle)`` is the power the crew and
saddle choices in engine/policy.py count. It is not a P/T change: the creature's power is unchanged otherwise.
"""
from __future__ import annotations

import re

from .cx_grammar import verb
from .cx_grammar_evasion import _SUBJECTS, _part, _spec

_CREW = re.compile(r"~ (saddles Mounts and )?crews Vehicles as though its power were (\d+) greater\.")


@verb(r"can't block or be blocked by (.+)", heads=("can't",), subjects=_SUBJECTS)
def cant_block_or_be_blocked(m, clause):
    spec = _spec(m[1])
    if spec is None:
        return None
    evade, limit = _part(clause, "cx_evade", ("by", spec)), _part(clause, "cx_block_limit", spec)
    return None if evade is None or limit is None else evade + limit


def parse_line(line: str, st) -> bool:
    m = _CREW.fullmatch(line)
    if not m:
        return False
    rules = st.extra.setdefault("advanced_rules", {})
    if "crew_bonus" in rules:
        return False
    rules["crew_bonus"] = int(m[2])
    if m[1]:
        rules["saddle_bonus"] = int(m[2])
    return True


def crew_power(perm, saddle: bool = False) -> int:
    """The power perm counts with when it crews a Vehicle (or saddles a Mount)."""
    if perm.abilities_suppressed:
        return perm.power
    return perm.power + perm.card.advanced_rules.get("saddle_bonus" if saddle else "crew_bonus", 0)
