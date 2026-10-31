"""Conditional self statics: "~ gets +2/+2 as long as you have 25 or more life", "~ has flying as long as you control an
artifact", "~ has vigilance as long as there are four or more card types among cards in your graveyard".

The pump or keyword rides the existing ``pt_if`` / ``cond_keywords`` card fields; the condition is a ``cx:`` code
evaluated by ``holds``, called from ``Permanent.condition`` for codes it doesn't know."""
from __future__ import annotations

import re

_N = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_KEYWORDS = ("flying|first strike|double strike|trample|haste|lifelink|vigilance|menace|deathtouch|reach|indestructible|"
             "hexproof|flash|defender|shroud|shadow|fear|intimidate|wither|persist|undying|infect|skulk|horsemanship")

# (pattern, code template); groups are substituted into the template.
_CONDS = [
    (rf"there are {_N} or more card types among cards in your graveyard", "cx:gy_types>={0}"),
    (rf"you have {_N} or more life", "cx:life>={0}"),
    (r"you have no cards in hand", "cx:hand=0"),
    (r"you have one or fewer cards in hand", "cx:hand<=1"),
    (r"a creature died under your control this turn", "cx:creature_died"),
    (r"a player has no cards in hand", "cx:any_empty_hand"),
    (r"you have the city's blessing", "cx:blessing"),
    (r"it's untapped", "cx:untapped"),
    (r"it's enchanted", "cx:enchanted"),
    (r"it has an? (\+1/\+1|-1/-1) counter on it", "cx:counter:{0}"),
    (rf"you control {_N} or more (artifacts|creatures|lands|enchantments)", "cx:ctrl>={0}:{1}"),
    (r"you control no untapped lands", "cx:no_untapped_lands"),
    (r"you control (another )?(?:an? )?(white|blue|black|red|green) (creature|permanent)", "cx:ctrl_color:{0}:{1}:{2}"),
    (r"you control (another )?(?:an? )?((?:artifact|[A-Z]\w+))( planeswalker)?", "cx:ctrl_kind:{0}:{1}:{2}"),
    (r"an opponent controls an? (?:nontoken )?(white|blue|black|red|green) permanent", "cx:opp_ctrl_color:{0}"),
    (r"you have " + _N + r" or more cards in (?:your )?hand", "cx:hand>={0}"),
    (r"(?:~|it) is attacking|it's attacking", "attacking"),
    (r"it's your turn", "your_turn"),
    (r"(?:~|it) is equipped", "cx:equipped"),
    (r"there are " + _N + r" or more cards in your graveyard", "cx:gy>={0}"),
    (r"there are " + _N + r" or more mana values among cards in your graveyard", "cx:gy_cmcs>={0}"),
    (r"an opponent has " + _N + r" or more cards in their graveyard", "cx:opp_gy>={0}"),
    (r"an opponent controls an? (Island|Swamp|Forest|Mountain|Plains)", "cx:opp_ctrl_kind:{0}"),
]
_COMPILED = [(re.compile(p), c) for p, c in _CONDS]
_KWS = rf"(?:{_KEYWORDS})(?:(?:, | and |, and )(?:{_KEYWORDS}))*"
_CLAUSE = rf"(?:gets ([+-]\d+)/([+-]\d+)(?: and has ({_KWS}))?|has ({_KWS}|can't be blocked))"
_LINE = re.compile(rf"(?:\w+ — )?~ {_CLAUSE} as long as (.+)\.")
_LEADING = re.compile(rf"(?:\w+ — )?As long as (.+?), (?:~|it) {_CLAUSE}\.")


def _code(text: str):
    from .cards.model import _num
    for pat, code in _COMPILED:
        m = pat.fullmatch(text)
        if m:
            return code.format(*[str(_num(g)) if g and g.lower() in _NUMS else (g or "") for g in m.groups()])
    from .cx_condlib import as_static
    return as_static(text) or None


_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def parse_line(line: str, st) -> bool:
    if parse_restriction(line, st):
        return True
    line = re.sub(r"(~|, ~|, it) can't be blocked( as long as|\.$)", r"\1 has can't be blocked\2", line)
    m = _LINE.fullmatch(line)
    if m is not None:
        cond, clause = m[5], m.groups()[:4]
    else:
        m = _LEADING.fullmatch(line)
        if m is None:
            return False
        cond, clause = m[1], m.groups()[1:5]
    code = _code(cond)
    if code is None:
        return False
    if clause[0] is not None:
        st.extra["pt_if"] = st.extra.get("pt_if", ()) + ((code, int(clause[0]), int(clause[1])),)
    for keyword in re.split(r", and |, | and ", clause[2] or clause[3] or ""):
        keyword = "unblockable" if keyword == "can't be blocked" else keyword
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
    if name == "hand<=1":
        return len(c.hand) <= 1
    if name == "creature_died":
        return bool(getattr(c, "creature_died_turn", False))
    if name == "any_empty_hand":
        game = getattr(c, "_game", None)
        return game is not None and any(not pl.hand for pl in game.players)
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
    if name.startswith("hand>="):
        return len(c.hand) >= int(name[6:])
    if name.startswith("gy>="):
        return len(c.graveyard) >= int(name[4:])
    if name.startswith("gy_cmcs>="):
        return len({card.cmc for card in c.graveyard}) >= int(name[9:])
    if name.startswith("opp_gy>="):
        game = getattr(c, "_game", None)
        return game is not None and len(game.opponent(c).graveyard) >= int(name[8:])
    if name == "equipped":
        return any(x.attached_to is perm for x in c.battlefield)
    if name == "opp_ctrl_color":
        game = getattr(c, "_game", None)
        return game is not None and any(_COLORS[rest] in x.card.colors for x in game.opponent(c).battlefield)
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


_UNLESS = re.compile(r"~ can't attack or block unless (.+)\.")


def parse_restriction(line: str, st) -> bool:
    """"~ can't attack or block unless COND." (Bast, Kefnet the Mindful): stored as ``advanced_rules['combat_unless']``."""
    m = _UNLESS.fullmatch(line)
    code = _code(m[1]) if m else None
    if code is None:
        return False
    st.extra.setdefault("advanced_rules", {})["combat_unless"] = code
    return True


def combat_blocked(perm) -> bool:
    """True when ~'s "can't attack or block unless" condition isn't met."""
    code = perm.card.advanced_rules.get("combat_unless")
    return bool(code) and not perm.condition(code)
