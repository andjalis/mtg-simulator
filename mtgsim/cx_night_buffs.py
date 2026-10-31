"""Auras and Equipment that give a bonus and an activated ability in one line:
"Enchanted creature gets +2/+2 and has "{T}: ~ deals 1 damage to any target."" (Arcane Teachings, Citizen's Crowbar).

The bonus is the card's equip_bonus and the quoted ability a host grant (backlog_templates.ability_grants), the same two
pieces that "Enchanted creature gets +2/+2." and "Enchanted creature has "{T}: Add {G}."" already parse into.
"""
from __future__ import annotations

import re

_KW = ("flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|shroud|indestructible|"
       "menace|reach|fear|intimidate|infect|wither|skulk|shadow|horsemanship")
_LINE = re.compile(rf'(Enchanted|Equipped) creature (?:gets ([+−-])(\d+)/([+−-])(\d+)(?:,? and |, | ))?'
                   rf'has (?:((?:{_KW})(?:(?:, | and |, and )(?:{_KW}))*)(?:,? and | ))?"(.+)"\.?')
_SIGN = {"+": 1, "-": -1, "−": -1}


def parse_line(line, st) -> bool:
    m = _LINE.fullmatch(line)
    if not m or not (m[2] or m[6]):
        return False
    extra = st.extra
    if m[1] == "Enchanted":
        if not extra.get("aura"):
            return False
    elif "Equipment" not in st.type_line:
        return False
    text = m[7].rstrip(".") + "."
    act, hosted = None, []
    if re.match(r"(?:Whenever|When|At the beginning of) ", text):
        # a granted trigger is the card's own host trigger: "Whenever ~ attacks" is "Whenever equipped creature attacks"
        from .cards.parse import _parse_trigger
        parsed = _parse_trigger(re.sub(r"(?:~|\bthis creature\b)", m[1].lower() + " creature", text))
        if parsed is not None and parsed[0] and not parsed[1] and parsed[2] is None and \
                all(t.event.startswith("host:") for t in parsed[0]):
            hosted = parsed[0]
    else:
        from .backlog_templates import ability
        act = ability(text)
    if act is None and not hosted:
        return False
    if m[2]:
        extra["equip_bonus"] = (_SIGN[m[2]] * int(m[3]), _SIGN[m[4]] * int(m[5]))
    if m[6]:
        extra["equip_keywords"] = extra.get("equip_keywords", frozenset()) | \
            frozenset(k.strip() for k in re.split(r", and |, | and ", m[6]))
    if act is not None:
        extra["ability_grants"] = extra.get("ability_grants", ()) + (({"host": True}, act),)
    st.triggers.extend(hosted)
    return True
