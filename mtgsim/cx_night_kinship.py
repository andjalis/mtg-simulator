"""Kinship (Lorwyn): "At the beginning of your upkeep, you may look at the top card of your library. If it shares a
creature type with ~, you may reveal it. If you do, <effects>."

One ``kinship`` effect carries the effects of the "If you do" sentence; the engine handler (engine/kinds/cx_night_kinship.py)
runs them when the top card shares a creature type with the source. Only untargeted effects are accepted."""
from __future__ import annotations

import re

_LINE = re.compile(r"(?:Kinship — )?At the beginning of your upkeep, you may look at the top card of your library\. "
                   r"If it shares a creature type with ~, you may reveal it\. If you do, (.+)")
_UNTARGETED = {"none", "self", "each_opponent", "each_player", "each_creature", "opp_creatures", "prev"}


def parse_line(line, st) -> bool:
    m = _LINE.fullmatch(line)
    if not m:
        return False
    from .cards.model import Effect, Trigger
    from .cards.parse import _parse_effects
    effects, unmatched = _parse_effects(m[1])
    if unmatched or not effects or "target" in m[1] or any(e.target not in _UNTARGETED | {"player"} for e in effects):
        return False
    st.triggers.append(Trigger("upkeep", [Effect("kinship", data={"effects": effects})]))
    return True
