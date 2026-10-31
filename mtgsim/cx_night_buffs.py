"""Auras and Equipment that give a bonus and an activated ability in one line:
"Enchanted creature gets +2/+2 and has "{T}: ~ deals 1 damage to any target."" (Arcane Teachings, Citizen's Crowbar).

The bonus is the card's equip_bonus and the quoted ability a host grant (backlog_templates.ability_grants), the same two
pieces that "Enchanted creature gets +2/+2." and "Enchanted creature has "{T}: Add {G}."" already parse into.
"""
from __future__ import annotations

import re

_LINE = re.compile(r'(Enchanted|Equipped) creature gets ([+−-])(\d+)/([+−-])(\d+) and has "(.+)"\.?')
_SIGN = {"+": 1, "-": -1, "−": -1}


def parse_line(line, st) -> bool:
    m = _LINE.fullmatch(line)
    if not m:
        return False
    extra = st.extra
    if m[1] == "Enchanted":
        if not extra.get("aura"):
            return False
    elif "Equipment" not in st.type_line:
        return False
    from .backlog_templates import ability
    act = ability(m[6].rstrip(".") + ".")
    if act is None:
        return False
    extra["equip_bonus"] = (_SIGN[m[2]] * int(m[3]), _SIGN[m[4]] * int(m[5]))
    extra["ability_grants"] = extra.get("ability_grants", ()) + (({"host": True}, act),)
    return True
