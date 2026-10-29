"""Token and emblem-like card definitions: tokens, the Empower Jace, Role tokens."""
from __future__ import annotations

import dataclasses

from .model import COLORS, CardDef, Effect, Trigger
from .parse import _parse_ability, card_from_scryfall


# Artifact tokens with an activated ability, as general abilities (see _parse_ability).
TOKEN_ABILITIES = {
    "map": "{1}, {T}, Sacrifice ~: Target creature you control explores. Activate only as a sorcery.",
    "lander": "{2}, {T}, Sacrifice ~: Search your library for a basic land card, put it onto the battlefield "
              "tapped, then shuffle.",
    "food": "{2}, {T}, Sacrifice ~: You gain 3 life.",
    "mutagen": "{1}, Sacrifice ~: Put a +1/+1 counter on target creature you control. Activate only as a sorcery.",
    "junk": "{T}, Sacrifice ~: Exile the top card of your library. You may play that card this turn.",
}


def make_token(name: str, power: int, toughness: int, keywords=frozenset(), triggers=None, kind: str = "",
               artifact: bool = False, pt_per: str = "", colors=frozenset()) -> CardDef:
    """A token's CardDef. kind is treasure/clue/blood for artifact tokens."""
    if kind:
        produces = frozenset(COLORS) if kind == "treasure" else frozenset()
        activated = [_parse_ability(TOKEN_ABILITIES[kind], [])] if kind in TOKEN_ABILITIES else []
        return CardDef(name=kind.capitalize(), mana_cost={"generic": 0}, cmc=0, types=frozenset({"Artifact"}),
                       subtypes=frozenset({kind.capitalize()}), produces=produces, token_kind=kind, is_token=True,
                       activated=activated)
    return CardDef(name=f"{name} token", mana_cost={"generic": 0}, cmc=0,
                   types=frozenset({"Creature", "Artifact"} if artifact else {"Creature"}),
                   subtypes=frozenset(name.split()) - {"Token"}, power=power, toughness=toughness,
                   keywords=frozenset(keywords), triggers=list(triggers or []), is_token=True, pt_per=pt_per, color_override=frozenset(colors))


def equipment_token(name: str, bonus: tuple, keywords=frozenset(), equip: int = 0, legendary: bool = False) -> CardDef:
    """A colorless Equipment artifact token: Dáin's Axe, Mabel's Cragflame."""
    return CardDef(name=f"{name} token", mana_cost={"generic": 0}, cmc=0, types=frozenset({"Artifact"}),
                   subtypes=frozenset({"Equipment"}), is_token=True, equip_bonus=bonus, equip_keywords=frozenset(keywords),
                   equip_cost={"generic": equip}, legendary=legendary)


_JACE = None


def jace_token(loyalty: int) -> CardDef:
    """The blue Jace planeswalker token that Empower creates."""
    global _JACE
    if _JACE is None:
        _JACE = card_from_scryfall({"name": "Jace", "mana_cost": "", "cmc": 0, "type_line": "Planeswalker — Jace",
                                    "oracle_text": "\u22121: Surveil 1.\n\u22123: Draw a card.", "loyalty": "0"})
        _JACE = dataclasses.replace(_JACE, is_token=True)
    return dataclasses.replace(_JACE, loyalty=loyalty)


_ROLES = {
    "royal": dict(equip_bonus=(1, 1), equip_ward=1),
    "monster": dict(equip_bonus=(1, 1), equip_keywords=frozenset({"trample"})),
    "wicked": dict(equip_bonus=(1, 1)),
    "cursed": dict(aura_flags=frozenset({"base_1_1"}), aura_hostile=True),
    "sorcerer": dict(host_triggers=[Trigger("attacks", [Effect("scry", 1)])]),
    "young hero": dict(host_triggers=[Trigger("attacks", [Effect("add_counter", 1, target="self", cond="host_toughness<=3",
                                                                    data={"counter": "+1/+1"})])]),
    "virtuous": dict(aura_flags=frozenset({"per_enchantment"})),
}


def role_token(role: str) -> CardDef:
    """A Role token: an Aura that gives the enchanted creature a bonus (Royal, Monster, Wicked, Cursed, ...)."""
    spec = dict(_ROLES[role])
    triggers = [Trigger("leaves", [Effect("drain", 1, target="each_opponent")])] if role == "wicked" else []
    return CardDef(name=f"{role.title()} Role", mana_cost={"generic": 0}, cmc=0, types=frozenset({"Enchantment"}),
                   subtypes=frozenset({"Aura", "Role"}), is_token=True, aura="creature", triggers=triggers, **spec)
