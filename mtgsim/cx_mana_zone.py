"""Restricted mana by where the spell is cast from (#644):

    Spend this mana only to cast spells from exile.                                  (Interdimensional Web Watch)
    Spend this mana only to cast a spell from your graveyard.                        (Lord of the Forsaken)
    Spend this mana only to cast a spell from anywhere other than your hand.         (Mm'menon, the Right Hand)
    Spend this mana only to cast spells with flashback from a graveyard.             (Altar of the Lost)

``code`` turns the wording into a ``zone:<where>`` mana_restriction; ``allowed`` is checked by Game.mana_allowed with
the spell being paid for: the zone it is cast from is the one its spell_options() variant names (Game._origin /
Game._zone), the same zone Game.cast records as ``item.cast_zone``. The adventure, foretell, plot, warp and airbend
zones are exile. Only spells: none of these lets the mana pay for an ability.
"""
from __future__ import annotations

_CODES = {
    "to cast spells from exile": "exile",
    "to cast a spell from exile": "exile",
    "to cast a spell from your graveyard": "graveyard",
    "to cast spells from your graveyard": "graveyard",
    "to cast a spell from anywhere other than your hand": "nothand",
    "to cast spells with flashback from a graveyard": "flashback",
}


def code(text: str):
    where = _CODES.get(text.strip().lower())
    return "zone:" + where if where else None


def _exile_zones(p):
    return (p.exile, p.on_adventure, p.foretold, p.plotted, p.warp_exile, p.airbent)


def allowed(game, perm, spell, where: str) -> bool:
    from .cards.model import CardDef
    if not isinstance(spell, CardDef):
        return False
    p = perm.controller
    _, kind, _ = game._origin(spell)
    zone = game._zone(p, kind)
    if where == "exile":
        return any(zone is z for z in _exile_zones(p))
    if where == "graveyard":
        return zone is p.graveyard
    if where == "flashback":
        return kind == "flashback"
    return zone is not p.hand                                  # "nothand"
