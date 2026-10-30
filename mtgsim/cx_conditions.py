"""Conditional self statics: "~ gets +2/+2 as long as you have 25 or more life", "~ has flying as long as you control an
artifact", "~ has vigilance as long as there are four or more card types among cards in your graveyard".

The pump or keyword rides the existing ``pt_if`` / ``cond_keywords`` card fields; the condition is a ``cx:`` code
evaluated by ``holds``, called from ``Permanent.condition`` for codes it doesn't know."""
from __future__ import annotations

import re

_N = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_KEYWORDS = "flying|first strike|double strike|trample|haste|lifelink|vigilance|menace|deathtouch|reach|indestructible|hexproof|flash|defender"

# (pattern, code template); groups are substituted into the template.
_CONDS = [
    (rf"there are {_N} or more card types among cards in your graveyard", "cx:gy_types>={0}"),
    (rf"you have {_N} or more life", "cx:life>={0}"),
    (r"you have no cards in hand", "cx:hand=0"),
    (r"you have the city's blessing", "cx:blessing"),
    (r"it's untapped", "cx:untapped"),
    (r"it's enchanted", "cx:enchanted"),
    (r"it has an? (\+1/\+1|-1/-1) counter on it", "cx:counter:{0}"),
    (rf"you control {_N} or more (artifacts|creatures|lands|enchantments)", "cx:ctrl>={0}:{1}"),
    (r"you control no untapped lands", "cx:no_untapped_lands"),
    (r"you control (another )?an? (white|blue|black|red|green) (creature|permanent)", "cx:ctrl_color:{0}:{1}:{2}"),
    (r"you control (another )?an? ((?:artifact|[A-Z]\w+))( planeswalker)?", "cx:ctrl_kind:{0}:{1}:{2}"),
    (r"an opponent controls an? (Island|Swamp|Forest|Mountain|Plains)", "cx:opp_ctrl_kind:{0}"),
]
_COMPILED = [(re.compile(p), c) for p, c in _CONDS]
_LINE = re.compile(rf"(?:\w+ — )?~ (?:gets ([+-]\d+)/([+-]\d+)(?: and has ({_KEYWORDS}))?|has ({_KEYWORDS})) "
                   r"as long as (.+)\.")


def _code(text: str):
    from .cards.model import _num
    for pat, code in _COMPILED:
        m = pat.fullmatch(text)
        if m:
            return code.format(*[str(_num(g)) if g and g.lower() in _NUMS else (g or "") for g in m.groups()])
    return None


_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def parse_line(line: str, st) -> bool:
    m = _LINE.fullmatch(line)
    if m is None:
        return False
    code = _code(m[5])
    if code is None:
        return False
    if m[1] is not None:
        st.extra["pt_if"] = st.extra.get("pt_if", ()) + ((code, int(m[1]), int(m[2])),)
    keyword = m[3] or m[4]
    if keyword:
        st.extra["cond_keywords"] = st.extra.get("cond_keywords", ()) + ((keyword, code),)
    return True


def holds(perm, cond: str) -> bool:
    c = perm.controller
    name, _, rest = cond[3:].partition(":")
    if name.startswith("gy_types>="):
        return len({t for card in c.graveyard for t in card.types}) >= int(name[10:])
    if name.startswith("life>="):
        return c.life >= int(name[6:])
    if name == "hand=0":
        return not c.hand
    if name == "blessing":
        from .batch1_templates import has_blessing
        return has_blessing(getattr(c, "_game", None), c)
    if name == "untapped":
        return not perm.tapped
    if name == "enchanted":
        return bool(perm.auras)
    if name == "counter":
        return perm.counters.get(rest, 0) > 0
    if name.startswith("ctrl>="):
        kind = rest[:-1].capitalize()
        return sum(kind in x.card.types for x in c.battlefield) >= int(name[6:])
    if name == "no_untapped_lands":
        return not any(x.card.is_land and not x.tapped for x in c.battlefield)
    others = [x for x in c.battlefield]
    if name == "ctrl_color":
        other, color, kind = rest.split(":")
        return any((x is not perm or not other) and _COLORS[color] in x.card.colors
                   and (kind == "permanent" or x.is_creature) for x in others)
    if name == "ctrl_kind":
        other, kind, pw = rest.split(":")
        kind = kind.capitalize() if kind == "artifact" else kind
        return any((x is not perm or not other) and (kind in x.card.types or kind in x.card.subtypes)
                   and (not pw or x.is_planeswalker) for x in others)
    if name == "opp_ctrl_kind":
        game = getattr(c, "_game", None)
        return game is not None and any(rest in x.card.subtypes for x in game.opponent(c).battlefield)
    return False
