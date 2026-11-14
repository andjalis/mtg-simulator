"""Conditions for statics that the shared condition library (cx_condlib) didn't know, and the self-statics they gate:

    As long as your devotion to blue is less than five, ~ isn't a creature.             (Thassa, God of the Sea)
    As long as your devotion to white and black is less than seven, ~ isn't a creature. (Athreos, God of Passage)
    ~ gets -2/-2 as long as black is the most common color among all permanents or is tied for most common.

The conditions are ``RULES`` that ``cx_condlib`` appends to its phrase rules, so every "as long as" / "if" reader of the library gets them;
``check`` evaluates their codes (called from ``cx_condlib.check`` for kinds it doesn't own). Devotion counts the
colored mana symbols among the mana costs of permanents you control: a hybrid symbol counts once toward each of its
colors, and once in all toward "devotion to A and B".

"~ isn't a creature" is ``advanced_rules["not_creature_if"]`` (a condition code), read by ``Permanent.is_creature``.
"""
from __future__ import annotations

import re

_COLORS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_NUM = r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|twenty)"    # cx_condlib's number words

_COLOR = r"(?:white|blue|black|red|green)"


def _devotion_cmp(m):
    from .cx_condlib import _code, _n
    op = {"less than": "<", "greater than": ">", "at least": ">="}[m["op"].lower()]
    return _code("devotion", sorted(_COLORS[c.lower()] for c in (m["a"], m["b"]) if c), op, _n(m["n"]))


def _devotion_or(m):
    from .cx_condlib import _code, _n
    op = "<=" if m["op"].lower() == "less" else ">="
    return _code("devotion", sorted(_COLORS[c.lower()] for c in (m["a"], m["b"]) if c), op, _n(m["n"]))


def _common_color(m):
    from .cx_condlib import _code
    return _code("common_color", _COLORS[m["c"].lower()], bool(m["tie"]))


def _host_is(m):
    """"enchanted creature is black", "equipped creature is a Human or an Angel", "enchanted land is a basic
    Mountain": the Aura's / Equipment's host now (cx_condlib's ``host_is``)."""
    from .cx_condlib import _code, _filter
    alts = re.split(r" or ", m["f"])
    if len(alts) > 2:
        return ""
    codes = []
    for alt in alts:
        spec = _filter(re.sub(r"^(?:a|an) ", "", alt.strip()), plural=False)
        if not spec or set(spec) - {"sub", "colors", "legendary", "basic", "types"} \
                or spec.get("types", ["creature"]) != ["creature"]:
            return ""           # what the host is now, by its card: not states, counters or animated types
        codes.append(_code("host_is", spec))
    return codes[0] if len(codes) == 1 else _code("or", *codes)


def _src_flag(m):
    from .cx_condlib import _code
    return _code("src_flag", m[1].lower())


RULES = [   # (pattern, builder): appended to cx_condlib's phrase rules
    (r"(?:enchanted|equipped) (?:creature|land) is (?P<f>[\w /-]+)", _host_is),
    (r"~ is (monstrous|renowned)", _src_flag),
    (r"you've lost life this turn", lambda m: 'lib:["lost_life"]'),
    (rf"your devotion to (?P<a>{_COLOR})(?: and (?P<b>{_COLOR}))? is (?P<op>less than|greater than|at least) "
     rf"(?P<n>{_NUM})", _devotion_cmp),
    (rf"your devotion to (?P<a>{_COLOR})(?: and (?P<b>{_COLOR}))? is (?P<n>{_NUM}) or (?P<op>greater|more|less)",
     _devotion_or),
    (rf"(?P<c>{_COLOR}) is the most common color among all permanents(?P<tie> or is tied for most common)?",
     _common_color),
]


def devotion_spec(text: str):
    """The quantity tuple for "your devotion to <color>[ and <color>]", or None."""
    m = re.fullmatch(rf"your devotion to ({_COLOR})(?: and ({_COLOR}))?", text.strip().rstrip("."), re.I)
    if not m:
        return None
    return "devotion", tuple(sorted(_COLORS[c.lower()] for c in m.groups() if c))


def devotion(player, colors) -> int:
    n = 0
    for x in player.battlefield:
        card = x.card
        n += sum(card.mana_cost.get(c, 0) for c in colors)
        # mana_cost files a hybrid symbol under its first color; count the ones filed under another color too
        n += sum(1 for pip in card.hybrid if pip[0] not in colors and any(c in pip for c in colors))
    return n


def _common(game, color, tie) -> bool:
    counts = dict.fromkeys(_COLORS.values(), 0)
    for pl in game.players:
        for x in pl.battlefield:
            for c in x.card.colors:
                if c in counts:
                    counts[c] += 1
    best = max(v for c, v in counts.items() if c != color)
    return counts[color] > best or tie and counts[color] == best


def check(game, p, kind, args, item=None, source=None):
    """cx_condlib.check for the kinds registered here; False for any other kind."""
    from .cx_condlib import _cmp
    if kind == "devotion":
        colors, op, n = args
        return _cmp(devotion(p, colors), op, n)
    if kind == "common_color":
        return game is not None and _common(game, *args)
    if kind == "src_flag":          # "~ is monstrous / renowned": set by the monstrosity / renown actions
        return bool(getattr(source, args[0], False))
    if kind == "lost_life":
        return bool(p.lost_life_turn)
    return False


# ---------------------------------------------------------------------------
# Self-statics
# ---------------------------------------------------------------------------

_NOT_CREATURE = re.compile(r"(?:[A-Z][\w' ]* — )?As long as (?P<c>.+?), ~ isn't a creature\.")


def parse_line(line: str, st) -> bool:
    m = _NOT_CREATURE.fullmatch(line)
    if not m or "Creature" not in st.types:
        return False
    from .cx_condlib import as_static
    code = as_static(m["c"])
    if not code:
        return False
    st.extra.setdefault("advanced_rules", {})["not_creature_if"] = code
    return True


_ACTIVE: set = set()      # permanents whose condition is being read: a condition that counts creatures doesn't recurse


def not_creature(perm) -> bool:
    """Permanent.is_creature: whether a "~ isn't a creature" condition holds now."""
    if id(perm) in _ACTIVE:
        return False
    _ACTIVE.add(id(perm))
    try:
        if perm.abilities_suppressed:
            return False
        from .cx_condlib import holds
        return holds(perm, perm.card.advanced_rules["not_creature_if"])
    finally:
        _ACTIVE.discard(id(perm))
