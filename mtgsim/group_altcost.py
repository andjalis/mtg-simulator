"""#625: alternative costs a permanent gives a group of spells.

    You may pay {W}{U}{B}{R}{G} rather than pay the mana cost for spells you cast.          (Fist of Suns, Jodah)
    You may pay {0} rather than pay the mana cost for Zombie creature spells you cast.      (Rooftop Storm)
    You may pay {X} rather than pay the mana cost for Samurai spells you cast, where X is that spell's mana value.
    Once each turn, you may pay {0} rather than pay the mana cost for a colorless spell you cast from your hand.
    You may cast spells from your hand without paying their mana costs.                     (Omniscience)
    You may cast Dragon spells without paying their mana costs.                             (Dracogenesis)

Each line adds ``(cost or "mv", filter specs, once)`` to the permanent's ``advanced_rules["group_alt"]`` (the
condition library's filter dialect, as cx_flash_perm reads it). ``variants`` offers every matching hand card a
``group_alt_<n>`` variant with that cost (CR 118.9: an alternative cost; additional costs and taxes still apply, X is
0), and ``note_cast`` uses up a once-each-turn permission when a cast took it. Only spells cast from the hand are
offered: a wording without "from your hand" also allows other zones (a card cast from exile or the graveyard), which
these variants don't model, so such a line is recorded as a simplification. Conditions, counts ("with mana value X or less, where X is ..."),
energy and other non-mana costs keep the line unmatched.
"""
from __future__ import annotations

import re

_PAY = re.compile(r"(?P<once>Once each turn, )?You may pay (?P<m>(?:\{[0-9WUBRGC]\})+|\{X\}) rather than pay the mana "
                  r"cost for (?:(?P<one>an? (?P<d1>[\w ]+?) ?spell) you cast(?P<hand1> from your hand)?|(?P<d2>[\w ]*?) ?"
                  r"spells you cast)(?P<x>, where X is that spell's mana value)?\.", re.I)
_FREE = re.compile(r"You may cast (?P<d>[\w ]*?) ?spells(?P<hand> from your hand)? without paying their mana costs\.")


def parse_line(line: str, st) -> bool:
    from .cards.model import parse_mana_cost
    from .cx_flash_perm import specs_for
    m = _PAY.fullmatch(line)
    if m:
        once = bool(m["once"])
        if once != bool(m["one"]) or bool(m["x"]) != (m["m"].upper() == "{X}"):
            return False            # "once" goes with "a spell"; {X} only as "that spell's mana value"
        desc = (m["d1"] if m["one"] else m["d2"]) or ""
        if desc.lower() == "a":
            desc = ""
        cost = "mv" if m["x"] else parse_mana_cost(m["m"])
    else:
        m = _FREE.fullmatch(line)
        if not m:
            return False
        once, desc, cost = False, m["d"], {"generic": 0}
    specs = specs_for(desc)
    if specs is None:
        return False
    rules = st.extra.setdefault("advanced_rules", {})
    rules["group_alt"] = tuple(rules.get("group_alt", ())) + ((cost, specs, once),)
    if not (m["hand"] if "hand" in m.groupdict() else m["hand1"]):
        st.approximations.append("the alternative cost is offered only for spells cast from the hand")
    return True


def _rules(game, p):
    for x in p.battlefield:
        if x.abilities_suppressed:
            continue
        for i, rule in enumerate(x.card.advanced_rules.get("group_alt", ())):
            if not rule[2] or getattr(x, "group_alt_turn", {}).get(i) != game.turn:
                yield x, i, rule


def variants(game, p, card) -> list:
    """The hand card's group_alt variants (one per distinct cost)."""
    from .cards import AltCost
    from .cx_condlib import _card_ok
    if card.is_land or card not in p.hand:
        return []
    out, seen = [], set()
    for x, i, (cost, specs, once) in _rules(game, p):
        if not any(_card_ok(card, s) for s in specs):
            continue
        cost = {"generic": card.cmc} if cost == "mv" else dict(cost)
        key = tuple(sorted(cost.items()))
        if key in seen:
            continue
        seen.add(key)
        kind = "group_alt_" + "_".join(f"{k}{n}" for k, n in key)
        out.append(game._variant(card, kind, AltCost(kind, cost)))
    return out


def note_cast(game, p, card, kind):
    """A group_alt cast: a once-each-turn permission giving that cost is used up, unless an unlimited one gave it."""
    from .cx_condlib import _card_ok
    key = kind[len("group_alt_"):]
    fitting = []
    for x, i, (cost, specs, once) in _rules(game, p):
        cost = {"generic": card.cmc} if cost == "mv" else cost
        if any(_card_ok(card, s) for s in specs) and "_".join(f"{k}{n}" for k, n in sorted(cost.items())) == key:
            fitting.append((x, i, once))
    if fitting and all(once for _, _, once in fitting):
        x, i, _ = fitting[0]
        used = dict(getattr(x, "group_alt_turn", {}))
        used[i] = game.turn
        x.group_alt_turn = used
