"""#633: keywords a permanent gives cards in its controller's graveyard or hand.

    Merfolk and Druid cards in your graveyard have retrace.                 (Deeproot Historian)
    Each Sliver creature card in your graveyard has unearth {2}.            (Dregscape Sliver)
    Each creature card in your hand has cycling {1}{U}.                     (Rhet-Tomb Mystic)
    During your turn, nonland permanent cards in your graveyard have retrace. (Six)

Each line adds ``(zone, filter specs, keyword, cost or None, during your turn)`` to the permanent's
``advanced_rules["zone_grants"]``. ``alts(game, p, card, zone)`` turns the grants that apply to a card into the same
``AltCost`` objects a printed keyword makes (retrace and jump-start pay the card's own mana cost; flashback its own
cost or the stated one; unearth the stated cost), and the graveyard loops of ``Game.spell_options`` and
``alt_casts.graveyard_variants`` read them next to the printed ones. ``cycling`` gives a hand card a cycling cost
when it has none. Keywords the engine doesn't read from these zones (miracle, warp, encore, escape) stay unmatched.
"""
from __future__ import annotations

import re

_LINE = re.compile(r"(?P<turn>During your turn, )?(?:[Ee]ach )?(?P<d>[\w ,/-]+?) cards? in your (?P<z>graveyard|hand) "
                   r"(?:has|have) (?P<k>retrace|jump-start|flashback|unearth|cycling)(?: (?P<c>(?:\{[0-9WUBRGC]\})+))?\.")


def parse_line(line: str, st) -> bool:
    m = _LINE.fullmatch(line)
    if not m:
        return False
    from .cards.model import parse_mana_cost
    from .cx_flash_perm import specs_for
    kw, zone = m["k"].replace("-", "_"), m["z"]
    if (zone == "hand") != (kw == "cycling") or (kw in ("unearth", "cycling")) != bool(m["c"]) or \
            kw in ("retrace", "jump_start") and m["c"]:
        return False
    desc = m["d"]
    if desc.split()[0].lower() in ("instant", "sorcery", "creature", "land", "nonland", "artifact", "enchantment",
                                   "permanent", "historic", "legendary"):
        desc = desc[0].lower() + desc[1:]
    specs = specs_for(desc)
    if not specs:
        return False
    cost = parse_mana_cost(m["c"]) if m["c"] else None
    rules = st.extra.setdefault("advanced_rules", {})
    rules["zone_grants"] = tuple(rules.get("zone_grants", ())) + ((zone, specs, kw, cost, bool(m["turn"])),)
    return True


def _grants(game, p, card, zone):
    from .cx_condlib import _card_ok
    for x in p.battlefield:
        if x.abilities_suppressed:
            continue
        for z, specs, kw, cost, my_turn in x.card.advanced_rules.get("zone_grants", ()):
            if z == zone and (not my_turn or game.active is p) and any(_card_ok(card, s) for s in specs):
                yield kw, cost


def alts(game, p, card, zone="graveyard") -> list:
    """The AltCosts a graveyard card has from grants (none it already has printed)."""
    from .cards.model import AltCost
    have = {a.kind for a in card.alt_costs}
    out = []
    for kw, cost in _grants(game, p, card, zone):
        if kw == "cycling" or kw in have:
            continue
        have.add(kw)
        out.append(AltCost(kw, dict(cost) if cost is not None else dict(card.mana_cost), zone="graveyard"))
    return out


def cycling(game, p, card):
    """A cycling spec for a hand card that only has cycling from a grant, or None."""
    for kw, cost in _grants(game, p, card, "hand"):
        if kw == "cycling":
            return {"cost": dict(cost), "land": ""}
    return None
