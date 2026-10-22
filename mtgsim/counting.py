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
    m = re.fullmatch(r"~ gets \+(\d+)/\+(\d+) for each (Aura|Equipment|Aura and Equipment|Aura and/or Equipment|Aura or "
                     r"Equipment) attached to it\.", line)
    if m:
        extra["pt_per"] = "attached " + "|".join(k for k in ("Aura", "Equipment") if k in m[3])
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
    (re.compile(r"for each creature in your party", re.I), lambda m: "for each party creature you control"),
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
    (r"(?:it|~) gets \+(\d+)/\+(\d+) until end of turn for each other attacking (?P<what>[\w -]+?)",
     lambda m: _pump_per(m, "attacking")),
    (r"(?P<who>it|~|target creature(?: you control)?) gets (?P<p>[+-]\d+)/(?P<t>[+-]\d+) until end of turn for each "
     r"(?P<what>[\w -]+?) you control", lambda m: _pump_each(m)),
    (r"until end of turn, (?P<who>target creature(?: you control)?) gets (?P<p>[+-]\d+)/(?P<t>[+-]\d+) for each "
     r"(?P<what>[\w -]+?) you control(?: and gains (?P<kw>trample|flying|haste|first strike|vigilance|menace))?",
     lambda m: _pump_each(m) if not m["kw"] else [_pump_each(m), _grant_prev(m["kw"])]),
    (r"~ deals damage to (?P<who>target creature|any target|target creature or planeswalker) equal to the number of "
     r"(?P<what>[\w -]+?) you control", lambda m: _damage_each(m)),
    (r"(?:it|~) gets \+(\d+)/\+(\d+) until end of turn for each creature blocking it",
     lambda m: _pump_blockers(m)),
    (r"put a \+1/\+1 counter on (?:it|that creature) for each (?P<what>[\w -]+?) you control",
     lambda m: _scaled(_per("p1_counters", target="prev")(m), 1)),
    (r"put a \+1/\+1 counter on ~ for each (?P<what>[\w -]+?) you control",
     lambda m: _scaled(_per("p1_counters", target="self")(m), 1)),
]


def _pump_per(m, zone):
    from .cards import Effect
    return Effect("pump", int(m[1]), int(m[2]), target="self",
                  data={"per": {"what": "other " + _singular(m["what"]), "zone": zone}})


def _pump_each(m):
    from .cards import Effect
    who = m["who"].lower()
    target = "self" if who in ("it", "~") else "creature_mine" if "you control" in who else "creature"
    per = {"per": {"what": _singular(m["what"]), "zone": "battlefield"}}
    if int(m["p"]) <= 0 and int(m["t"]) < 0 and target == "creature":      # "gets -1/-1 ... for each Swamp you control"
        return Effect("debuff_one", -int(m["p"]), -int(m["t"]), target="creature", data=per)
    return Effect("pump", int(m["p"]), int(m["t"]), target=target, data=per)


def _damage_each(m):
    from .cards import Effect
    target = {"target creature": "creature", "any target": "any", "target creature or planeswalker": "creature"}[m["who"].lower()]
    return Effect("damage", 1, target=target, data={"per": {"what": _singular(m["what"]), "zone": "battlefield"}})


def _pump_blockers(m):
    from .cards import Effect
    return Effect("pump", int(m[1]), int(m[2]), target="self", data={"per": {"what": "creature", "zone": "blocking"}})


def _grant_prev(kw):
    from .cards import Effect
    return Effect("grant", target="prev", data={"keyword": kw})


def _scaled(eff, n):
    eff.amount = n
    return eff


def count(game, p, per: dict, source=None) -> int:
    from .copies import fits
    what = per["what"]
    if what.startswith("attached "):        # "for each Aura and Equipment attached to it"
        kinds = what[9:].split("|")
        return sum(1 for x in (source.auras + source.equipment if source is not None else [])
                   if any(k in x.card.subtypes for k in kinds))
    if what.startswith("counter:"):         # "for each charge counter on ~"
        return source.counters.get(what[8:], 0) if source is not None else 0
    if what == "party creature":            # up to one each of Cleric, Rogue, Warrior and Wizard
        from .discounts import party_size
        return party_size(p)
    other = what.startswith("other ")
    what = what[6:] if other else what
    if per["zone"] == "graveyard":
        return sum(fits(c, what) for c in p.graveyard)
    if per["zone"] == "blocking":           # "for each creature blocking it"
        return len(game.blocks.get(source, ())) if game is not None and source is not None else 0
    if per["zone"] == "attacking":          # "for each other attacking Aurochs"
        return sum(1 for x in game.attackers if x.controller is p and not (other and x is source)
                   and (what == "creature" or fits(x.card, what, x)))
    return sum(1 for x in p.battlefield if not (other and x is source) and fits(x.card, what, x))
