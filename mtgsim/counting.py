"""Amounts that count things: "~ gets +1/+1 for each Mountain you control", "~'s power and toughness are each
equal to the number of lands you control", "draw a card for each artifact you control", "you gain 1 life for each
creature you control", "discard up to two cards, then draw that many cards".

``pt_per`` on a card is (what, scale): what is a description such as "Mountain", "other artifact", "creature";
scale is (power, toughness) per counted permanent. An effect with ``data["per"]`` = {"what", "zone"} multiplies its
amount by the count when it resolves (zone battlefield counts the controller's permanents, graveyard their cards).
"""
from __future__ import annotations

import re

_PT = r"[+-]?\d+"


def parse_line(line: str, extra: dict) -> bool:
    """Consume a static "gets +N/+N for each ..." or "power (and toughness) ... equal to the number of ..." line."""
    m = re.fullmatch(r"~ gets \+(\d+)/\+(\d+) for each (other )?([\w -]+?) you control\.", line)
    if m:
        extra["pt_per"] = ("other " if m[3] else "") + m[4]
        extra["pt_scale"] = (int(m[1]), int(m[2]))
        return True
    m = re.fullmatch(r"~'s (power and toughness are each|power is|toughness is) equal to the number of "
                     r"([\w -]+?) you control\.", line)
    if m:
        extra["pt_per"] = _singular(m[2])
        extra["pt_scale"] = (1, 1) if "and" in m[1] else (1, 0) if m[1].startswith("power") else (0, 1)
        return True
    return False


SUBS = [
    (re.compile(r"discard (up to )?(\w+) cards?, then draw that many cards?\.", re.I),
     lambda m: f"RUMMAGE {_n(m[2])}."),
]


def _singular(what: str) -> str:
    if what.endswith("ies"):
        return what[:-3] + "y"
    return what[:-1] if what.endswith("s") and not what.endswith("ss") else what


def _n(w: str) -> int:
    from .cards import _num
    return _num(w)


def _per(kind, scope="battlefield", **kw):
    def build(m):
        from .cards import Effect  # at match time: this module loads before cards
        what = _singular(m["what"])
        return Effect(kind, kw.get("amount", 1), target=kw.get("target", "none"),
                      data={"per": {"what": what, "zone": scope}})
    return build


EFFECT_PATTERNS = [
    (r"draw a card for each (?P<what>[\w -]+?) you control", _per("draw")),
    (r"draw a card for each (?P<what>[\w -]+?) card in your graveyard", _per("draw", "graveyard")),
    (r"you gain (\d+) life for each (?P<what>[\w -]+?) you control",
     lambda m: _scaled(_per("gain_life")(m), int(m[1]))),
    (r"you lose (\d+) life for each (?P<what>[\w -]+?) you control",
     lambda m: _scaled(_per("lose_life")(m), int(m[1]))),
    (r"put a \+1/\+1 counter on ~ for each (?P<what>[\w -]+?) you control",
     lambda m: _scaled(_per("p1_counters", target="self")(m), 1)),
]


def _scaled(eff, n):
    eff.amount = n
    return eff


def count(game, p, per: dict, source=None) -> int:
    from .copies import fits
    what = per["what"]
    other = what.startswith("other ")
    what = what[6:] if other else what
    if per["zone"] == "graveyard":
        return sum(fits(c, what) for c in p.graveyard)
    return sum(1 for x in p.battlefield if not (other and x is source) and fits(x.card, what, x))
