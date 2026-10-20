"""Turn Scryfall card JSON into the simplified CardDef the engine understands.

Oracle text is matched sentence by sentence against a small set of templates.
Anything that does not match is recorded in CardDef.unsupported so reports can
say which cards are only partially simulated.
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field

from . import modal

COLORS = ("W", "U", "B", "R", "G")
KEYWORDS = {
    "flying", "reach", "haste", "trample", "first strike", "double strike",
    "deathtouch", "lifelink", "vigilance", "defender", "menace",
    "flash", "hexproof", "indestructible", "prowess",
}
BASIC_MANA = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}
NUMBERS = {
    "zero": 0, "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20,
}
COLOR_WORDS = r"(?:white|blue|black|red|green|colorless)"


NO_MATCH = object()      # returned by a template builder: "not this template after all"


def _distinct_bounce():
    return Effect("bounce", target="nonland_perm", filter="opp", data={"distinct": True})


def _distinct_pump(m):
    return Effect("pump", int(m[1]), int(m[2]), target="creature_mine", data={"distinct": True})


def _num(word: str) -> int:
    value = NUMBERS.get(word.lower())
    return value if value is not None else int(word)


@dataclass
class Effect:
    # damage, destroy, draw, gain_life, drain, pump, counter, lose_life, debuff, wrath, wrath_pw,
    # bounce, bounce_spell, scry, surveil, dig, dig_put, discard, discard_choice, rummage, token,
    # p1_counters, grant, add_counter, transform, regrow, reanimate_snow, gy_hate, copy_token,
    # draw_up_to, next_creature_counter, adversary, debuff_blood
    kind: str
    amount: int = 0
    amount2: int = 0
    # any, creature, creature_pw, creature_mine, nonland_perm, artifact, player, spell, opp_spell,
    # self, prev (the previous effect's target), that_player, that_controller, each_opponent,
    # each_creature, opp_creatures, each_opp_and_pw, none
    target: str = "none"
    # counter: "noncreature" / "creature" / "instant_sorcery"; destroy: "max_cmc:2", "revolt",
    # "plains", "tapped", "attacking_blocking", "nonartifact"
    filter: str = ""
    cond: str = ""           # attacked2, not_attacked2, counters3, target_player, modified
    data: dict = field(default_factory=dict)


# Trigger events: etb, attacks, dies, combat_damage_player, cast_noncreature, cast_spell,
# any_cast, upkeep, end_step, opp_creature_dies, other_creature_enters, other_creature_dies,
# land_enters, you_draw, opp_draw, targeted_by_spell.
@dataclass
class Trigger:
    event: str
    effects: list
    filter: str = ""                 # "cmc<=3", "greater_power", "self|other|creature or artifact" (permanent_enters)
    modes: list | None = None        # "choose up to one" triggers: a list of effect lists
    once: bool = False               # "This ability triggers only once each turn."
    once_game: bool = False          # "This ability triggers only once."


@dataclass
class AltCost:
    """Another way to cast a card: flashback, foretell, spectacle, blitz, channel, Baleful Mastery."""
    kind: str                        # flashback, foretell, spectacle, blitz, channel, alt, kicker, warp, evoke,
    cost: dict                       # offspring (extra cost on top of the mana cost), plot
    zone: str = "hand"               # hand, graveyard, foretold
    effects: list | None = None      # channel / kicker: these effects instead of the card's
    extra: list = field(default_factory=list)    # extra effects (Baleful: an opponent draws)
    life: int = 0
    hybrid: tuple = ()               # hybrid pips in cost, e.g. ("UB", "UB") for {U/B}{U/B}
    counters: int = 0                # impending: time counters it enters with


@dataclass
class EquipCost:
    """One independent Equip ability, including all its supported payment components."""
    mana: dict
    sacrifice: bool = False           # sacrifice one creature
    target_filter: str = ""           # legendary, token, or subtype:TYPE|TYPE


@dataclass
class Activated:
    kind: str                        # animate, barrens, sac_debuff, ability
    cost: dict
    power: int = 0
    toughness: int = 0
    keywords: frozenset = frozenset()
    ward: int = 0
    triggers: list = field(default_factory=list)
    # kind "ability": a general "COSTS: EFFECTS" ability. extra_costs holds the non-mana costs:
    # tap, sac_self, exile_self, sacrifice (what to sacrifice: token, artifact, creature, ...),
    # discard (cards), life, remove_counter (counter name).
    effects: list = field(default_factory=list)
    extra_costs: dict = field(default_factory=dict)
    sorcery: bool = False            # "Activate only as a sorcery."
    once: bool = False               # "Activate only once each turn."
    min_charge: int = 0              # under "STATION N+": needs N charge counters
    needs_max_speed: bool = False    # "Max speed — COST: EFFECT"
    once_game: bool = False          # Exhaust / Power-up: each such ability is activated only once
    power_up: bool = False           # Power-up: costs its mana cost less if the creature entered this turn
    text: str = ""
    modes: list = field(default_factory=list)    # "COST: Choose one —": a modal.Modes


@dataclass
class CardDef:
    name: str
    mana_cost: dict
    cmc: int
    types: frozenset
    subtypes: frozenset = frozenset()                   # creature, land and artifact types: Dragon, Plains, Equipment
    power: int | None = None
    toughness: int | None = None
    keywords: frozenset = frozenset()
    produces: frozenset = frozenset()
    enters_tapped: bool = False
    spell_effects: list = field(default_factory=list)
    etb_effects: list = field(default_factory=list)
    unsupported: list = field(default_factory=list)
    approximations: list = field(default_factory=list)  # text the engine plays in a simplified way
    oracle: str = ""
    triggers: list = field(default_factory=list)       # Trigger, including the ETB one
    mana_amount: int = 1                                # Sol Ring makes 2
    tapped_condition: str = ""                          # "unless_2_lands" / "if_2_lands" / "shock"
    ward: int = 0
    ward_untapped_only: bool = False
    ward_discard: bool = False
    uncounterable: bool = False
    protects_spells: bool = False                       # "instant and sorcery spells you control can't be countered"
    cost_reduction: str = ""                            # "instant_sorcery_gy" (Tolarian Terror), "power" (Ghalta)
    snow: bool = False
    legendary: bool = False
    modes: list = field(default_factory=list)           # modal spells: one effect list per mode
    modes_choose: int = 1
    loyalty: int = 0
    loyalty_abilities: list = field(default_factory=list)   # (cost, effects)
    pw_instant_on_entry: bool = False                   # The Wandering Emperor
    chapters: list = field(default_factory=list)        # saga chapters: one effect list each
    back: "CardDef | None" = None                       # transformed face
    adventure: "CardDef | None" = None
    land_face: "CardDef | None" = None                  # a modal double-faced card's land back face
    alt_costs: list = field(default_factory=list)
    activated: list = field(default_factory=list)
    anthem: tuple = ()                                  # (power, toughness) for creatures you control
    crew: int = 0
    convoke: bool = False                               # creatures can be tapped to help pay the generic cost
    prepared: bool = False                              # enters prepared: may cast a copy of its spell (card.back) once
    changeling: bool = False                            # is every creature type
    cycling: dict | None = None                         # {"cost": mana, "land": "" | basic | any | Plains...}
    saddle: int = 0                                     # Mounts: tap creatures with total power N or more to saddle
    min_blocker_power: int = 0
    keyword_at_counters: tuple = ()                     # (n, keyword): Pelt Collector
    token_kind: str = ""                                # treasure, clue, blood
    is_token: bool = False
    is_ability: bool = False                            # a channel ability cast like a spell
    etb_counters: int = 0                               # "enters with N +1/+1 counters on it"
    teamwork: int = 0                                   # "Teamwork N": may tap creatures with total power N or more as an additional cost
    extra_life_cost: int = 0                            # "As an additional cost to cast ~, pay N life"
    wither_noncombat: bool = False                      # Soul-Scar Mage: noncombat damage becomes -1/-1 counters
    exile_damaged: bool = False                         # Etching of Kumano: damaged creatures are exiled instead
    # Mana that may only be spent on some spells: creature, artifact, instant_sorcery, chosen_type
    # (Cavern of Souls), or subtype:Dragon|Omen. restricted_produces is the colours it limits.
    mana_restriction: str = ""
    restricted_produces: frozenset = frozenset()
    choose_type: str = ""                               # "creature" (Cavern of Souls), "basic_land"
    cant_block: bool = False
    stops_activations: bool = False                     # Clarion Conqueror
    # Equipment: independent abilities, and what the equipped creature gets.
    equip_costs: tuple = ()
    # Compatibility fields for definitions constructed without equip_costs.
    equip_cost: dict | None = None
    equip_sacrifice: bool = False
    equip_bonus: tuple = (0, 0)
    equip_keywords: frozenset = frozenset()
    equip_ward: int = 0
    equip_discount: int = 0                             # Dwarven Mauler: equip abilities targeting it cost less
    leyline: bool = False                               # may begin the game on the battlefield
    cond_keywords: tuple = ()                           # ((keyword, condition), ...): "another:Dwarf", "opp_life<=10"
    hybrid: tuple = ()                                  # hybrid pips of the mana cost: ("UB", "UB")
    spent_colors: frozenset = frozenset()               # colours in "if {U}{U} was spent to cast it" triggers
    spree: list = field(default_factory=list)           # spree modes: (extra cost, effects)
    gy_triggers: list = field(default_factory=list)     # triggers that work from the graveyard (Bloodghast)
    ward_life: int = 0                                  # "Ward—Pay N life."
    etb_named_counters: tuple = ()                      # ("net", 3): "enters with three net counters on it"
    station: bool = False                               # Station (tap another creature: charge counters)
    extra_lands: int = 0                                # "You may play an additional land on each of your turns."
    lands_from_gy: bool = False                         # "You may play lands from your graveyard."
    etb_counters_if: tuple = ()                         # ("opp_lost_life", n): "enters with a +1/+1 counter if ..."
    team_keywords: frozenset = frozenset()              # "Creatures you control have haste."
    collect_evidence: int = 0                           # "you may collect evidence N" (exile graveyard cards worth N mana value)
    chosen_land_lock: bool = False                      # Petrified Hamlet: choose a land name, stifle it and make it tap for {C}
    gift: str = ""                                      # "Gift a card/Food/Treasure/tapped Fish": what an opponent gets
    gy_return: dict | None = None                       # "{1}{B}: Return this card from your graveyard to your hand."
    gy_exile_draw: dict | None = None                   # "Max speed — {3}, Exile this card from your graveyard: Draw a card."
    bargain: bool = False                               # "Bargain": may sacrifice an artifact, enchantment or token as an additional cost
    gift: str = ""                                      # "Gift a card/Food/Treasure/tapped Fish/Octopus": what an opponent gets if promised
    token_double: bool = False                          # "If one or more tokens would be created ..., twice that many"
    anthem_chosen: tuple = ()                           # "Creatures you control of the chosen type get +1/+1"
    must_be_blocked: bool = False                       # "~ must be blocked if able."
    blocker_power_rel: bool = False                     # "Creatures with power less than ~'s power can't block it."
    max_blocker_power: int = 0                          # "can't be blocked by creatures with power N or greater"
    no_max_hand: bool = False                           # "You have no maximum hand size."
    must_attack: bool = False                           # "~ attacks each combat if able."
    gy_needs_speed: bool = False
    start_engines: bool = False                         # "Start your engines!": speed starts at 1 when it enters or is cast
    anthem_kw: tuple = ()                               # (("flying", 1, 1), ...): "Creatures you control with flying get +1/+1"
    keyword_sub: tuple = ()                             # (("Rhino", "menace", other), ...): "Rhinos you control have menace"
    discount_if: tuple = ()                             # (("Wizard", 1), ...): "~ costs {1} less to cast if you control a Wizard"
    anthem_sub: tuple = ()                              # (("Elf", 1, 1, other), ...): "Other Elf creatures you control get +1/+1"
    counter_team_keywords: frozenset = frozenset()      # "Creatures you control with +1/+1 counters on them have trample"
    second_spell_discount: int = 0                      # "The second spell you cast each turn costs {1} less"
    tapped_discount: int = 0                            # "~ costs {3} less to cast if it targets a tapped creature"
    extra_discard: int = 0                              # "As an additional cost to cast ~, discard a card" (1 = or pay {2}: see discard_or_pay)
    behold_or_pay: tuple = ()                           # ("Elf", 2): "behold an Elf or pay {2}" as an additional cost
    discard_or_pay: int = 0                             # "... discard a card or pay {2}"
    untap_each_untap: bool = False                      # "Untap ~ during each other player's untap step"
    anthem_enchanted: tuple = ()                        # "Enchanted creatures you control get +N/+N"
    token_ability_discount: int = 0                     # "Activated abilities of artifact tokens you control cost {1} less"
    grant_mana: tuple = ()                              # ((scope, colours), ...): 'Creatures you control have "{T}: Add ..."'
    cost_discount: tuple = ()                           # ((filter, n), ...): "Red spells you cast cost {1} less"
    opp_no_cast: bool = False                           # "Your opponents can't cast spells during your turn."
    pt_if: tuple = ()                                   # ((condition, power, toughness), ...) conditional pump
    host_triggers: list = field(default_factory=list)   # Role tokens: triggers of the enchanted creature
    mana_filter: str = ""                               # "tap": {1},{T}: add any colour; "once": {1}: add .... once each turn
    mana_tap_other: str = ""                            # "creature"/"permanent": also tap an untapped one as a cost
    mana_sac: bool = False                              # "{T}, Sacrifice ~: Add one mana of any color."
    mana_cond: str = ""                                 # "Dragon": only while you control one
    pt_scale: tuple = (1, 1)                            # (power, toughness) gained per counted permanent
    pt_per: str = ""                                    # "~ gets +1/+1 for each artifact you control": "artifact"
    extra_sacrifice: str = ""                           # "As an additional cost to cast ~, sacrifice an artifact or creature"
    extra_sac_or_pay: int = 0                           # "... pay {4} or sacrifice ...": the generic alternative
    aura: str = ""                                      # "Enchant creature" (what it enchants; mtgsim.auras)
    aura_flags: frozenset = frozenset()                 # no_untap, cant_attack_block
    aura_hostile: bool = False                          # goes on an opponent's permanent
    clone: dict | None = None                           # "You may have ~ enter as a copy of ..." (mtgsim.copies)
    cast_copy: dict | None = None                       # "When you cast ~, copy it." (mtgsim.copies)

    @property
    def is_land(self): return "Land" in self.types

    @property
    def is_creature(self): return "Creature" in self.types

    @property
    def is_instant(self): return "Instant" in self.types

    @property
    def is_sorcery(self): return "Sorcery" in self.types

    @property
    def is_planeswalker(self): return "Planeswalker" in self.types

    @property
    def is_artifact(self): return "Artifact" in self.types

    @property
    def is_saga(self): return bool(self.chapters)

    @property
    def equip_abilities(self):
        """Supported choices, including legacy hand-built card definitions."""
        if self.equip_costs:
            return self.equip_costs
        return () if self.equip_cost is None else (EquipCost(self.equip_cost, self.equip_sacrifice),)

    @property
    def instant_speed(self): return self.is_instant or "flash" in self.keywords

    @property
    def is_permanent(self): return not ("Instant" in self.types or "Sorcery" in self.types)

    @property
    def fully_supported(self): return not self.unsupported

    def __hash__(self): return hash(self.name)

    def __eq__(self, other): return isinstance(other, CardDef) and other.name == self.name

    def __repr__(self): return f"<{self.name}>"


def parse_mana_cost(cost: str) -> dict:
    out = {"generic": 0}
    for sym in re.findall(r"\{([^}]+)\}", cost or ""):
        if sym.isdigit():
            out["generic"] += int(sym)
        elif sym == "X":
            out["X"] = out.get("X", 0) + 1
        else:
            # Hybrid / Phyrexian: pay with the first coloured half (simplification).
            parts = [p for p in sym.split("/") if p in COLORS or p == "C"]
            if parts:
                out[parts[0]] = out.get(parts[0], 0) + 1
            elif sym.split("/")[0].isdigit():
                out["generic"] += int(sym.split("/")[0])
    return out


def add_mana(*costs) -> dict:
    out: dict = {}
    for c in costs:
        for k, v in c.items():
            out[k] = out.get(k, 0) + v
    return out


def _parse_mana_ability(rest: str) -> tuple[set, int]:
    """Colours a {T} ability can make, and how much mana it makes ({C}{C} is 2)."""
    if "any color" in rest:
        return set(COLORS), 1
    syms = re.findall(r"\{([WUBRGC])\}", rest)
    amount = 1 if " or " in rest else max(1, len(syms))
    return set(syms), amount


def _token(m_count, power, toughness, desc, with_kw="", attacking=False, ability=""):
    words = desc.split()
    subtypes = [w for w in words if not re.fullmatch(COLOR_WORDS, w, re.I)]
    kws = frozenset(k.strip().lower() for k in re.split(r",| and ", with_kw or "") if k.strip().lower() in KEYWORDS)
    triggers, pt_per = [], ""
    if ability:
        per = re.fullmatch(r"(?:This (?:token|creature)|~) gets \+1/\+1 for each (\w+?)s? you control\.?", ability)
        parsed = None if per else _parse_trigger(ability.rstrip("."). replace("this creature", "~") + ".")
        triggers = parsed[0] if parsed else []
        pt_per = per[1] if per else ""
    artifact = "artifact" in subtypes
    subtypes = [w for w in subtypes if w != "artifact"]
    return Effect("token", _num(m_count), data={"name": " ".join(subtypes) or "Token", "power": int(power),
                                                "toughness": int(toughness), "keywords": kws,
                                                "attacking": attacking, "triggers": triggers,
                                                "artifact": artifact, "pt_per": pt_per})


def _distinct_cant_block():
    return Effect("cant_block_turn", target="creature", data={"distinct": True})


_TENS = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _tapped(eff):
    eff.data["tapped"] = True
    return eff


_SRC = r"(?:~|it|he|she)"
_EFFECT_PATTERNS = [
    (_SRC + r" deals (\d+) damage to any target", lambda m: Effect("damage", int(m[1]), target="any")),
    (_SRC + r" deals X damage to any target", lambda m: Effect("damage", 0, target="any", data={"x": True})),
    (_SRC + r" deals (\d+) damage to target attacking or blocking creature",
     lambda m: Effect("damage", int(m[1]), target="creature", filter="attacking_blocking")),
    (_SRC + r" deals (\d+) damage to target tapped creature(?: an opponent controls)?",
     lambda m: Effect("damage", int(m[1]), target="creature", filter="tapped")),
    (_SRC + r" deals (\d+) damage to target creature without flying",
     lambda m: Effect("damage", int(m[1]), target="creature", filter="nonflying")),
    (_SRC + r" deals (\d+) damage to (?:up to one )?target (?:creature or planeswalker|creature)"
     r"(?: an opponent controls| you don't control)?",
     lambda m: Effect("damage", int(m[1]), target="creature")),
    (_SRC + r" deals (\d+) damage to (?:target player or planeswalker|target player|target opponent"
     r"(?: or planeswalker)?|each opponent)",
     lambda m: Effect("damage", int(m[1]), target="player")),
    (_SRC + r" deals (\d+) damage to each opponent and each planeswalker they control",
     lambda m: Effect("damage", int(m[1]), target="each_opp_and_pw")),
    (_SRC + r" deals (\d+) damage to (?:that player|that spell's controller)",
     lambda m: Effect("damage", int(m[1]), target="that_player")),
    (_SRC + r" deals (\d+) damage to you", lambda m: Effect("lose_life", int(m[1]))),
    (r"~ also deals (\d+) damage to that permanent's controller if you control a modified creature",
     lambda m: Effect("damage", int(m[1]), target="that_controller", cond="modified")),
    (r"~ deals (\d+) damage to each creature", lambda m: Effect("damage", int(m[1]), target="each_creature")),
    (r"destroy target creature with mana value (\d+) or less",
     lambda m: Effect("destroy", target="creature", filter=f"max_cmc:{m[1]}")),
    (r"destroy target creature if it has mana value (\d+) or less",
     lambda m: Effect("destroy", target="creature", filter=f"max_cmc:{m[1]}")),
    (r"revolt — destroy that creature if it has mana value (\d+) or less instead if a permanent you "
     r"controlled left the battlefield this turn",
     lambda m: Effect("revolt", int(m[1]), target="prev")),
    (r"exile target creature with mana value less than or equal to the number of plains you control",
     lambda m: Effect("destroy", target="creature", filter="plains")),
    (r"(?:destroy|exile) target tapped creature(?: an opponent controls| you don't control)?",
     lambda m: Effect("destroy", target="creature", filter="tapped")),
    (r"(?:destroy|exile) target attacking or blocking creature",
     lambda m: Effect("destroy", target="creature", filter="attacking_blocking")),
    (r"(?:destroy|exile) target untapped creature(?: an opponent controls| you don't control)?",
     lambda m: Effect("destroy", target="creature", filter="untapped")),
    (r"destroy target nonartifact creature", lambda m: Effect("destroy", target="creature", filter="nonartifact")),
    # "non-Angel, non-Demon, non-Dragon" style restrictions are parsed but not enforced.
    (r"(?:destroy|exile) target (?:[\w-]+,? )*?creature(?:, enchantment,)? or planeswalker",
     lambda m: Effect("destroy", target="creature_pw")),
    (r"(?:destroy|exile) target (?:[\w-]+,? )*?creature(?: an opponent controls| you don't control)?",
     lambda m: Effect("destroy", target="creature")),
    (r"destroy target artifact", lambda m: Effect("destroy", target="artifact")),
    (r"(?:destroy|exile) target artifact or enchantment(?: an opponent controls)?",
     lambda m: Effect("destroy", target="artifact_enchantment", filter="opp")),
    (r"you may put a permanent card from among the (?:cards milled this way|milled cards) into your hand",
     lambda m: Effect("mill_pick")),
    (r"if you control a Squirrel or returned a Squirrel card to your hand this way, create a food token",
     lambda m: Effect("token", 1, data={"kind": "food"}, cond="squirrel")),
    (r"(?:you may )?return (?:a|up to one) (?:non-\w+ )?creature card(?: or a planeswalker card)? from your "
     r"graveyard to your hand", lambda m: Effect("regrow")),
    (r"DISCARDTUTOR", lambda m: Effect("discard_tutor", data={"desc": "a creature card"})),
    (r"when you discard one or more nonland cards this way, tap up to that many target creatures and put a stun "
     r"counter on each of them", lambda m: Effect("stun_discarded")),
    (_SRC + r" deals damage equal to that creature's power to any target",
     lambda m: Effect("damage", 0, target="any", data={"subject_power": True})),
    (r"shuffle ~ and target creature with a stun counter on it into their owners' libraries",
     lambda m: Effect("shuffle_away", target="creature", filter="stunned")),
    (r"RETURNENCHANT", lambda m: Effect("return_as_enchantment")),
    (r"LASTGIFT", lambda m: Effect("last_gift")),
    (r"target opponent exiles a creature they control and their graveyard",
     lambda m: [Effect("edict", 1, data={"exile": True}), Effect("exile_gy")]),
    (r"untap another target permanent", lambda m: Effect("untap_other")),
    (r"draw a card for each (artifact|creature|land) you control",
     lambda m: Effect("draw", 0, data={"x_count": m[1]})),
    (r"put ~ into its owner's library third from the top", lambda m: Effect("tuck_self", 3)),
    (r"(?:you )?draw (a|one|two|three|four|\d+) cards?", lambda m: Effect("draw", _num(m[1]))),
    (r"(?:then )?if you have fewer than (three) cards in hand, draw cards equal to the difference",
     lambda m: Effect("draw_up_to", _num(m[1]))),
    (r"you gain (\d+) life", lambda m: Effect("gain_life", int(m[1]))),
    (r"its controller gains (\d+) life", lambda m: Effect("gain_life", int(m[1]), target="that_controller")),
    (r"(?:each|target) opponent loses (\d+) life", lambda m: Effect("drain", int(m[1]), target="each_opponent")),
    (r"each opponent loses (\d+) life and you gain (\d+) life",
     lambda m: [Effect("drain", int(m[1]), target="each_opponent"), Effect("gain_life", int(m[2]))]),
    (r"DEVOTIONDRAIN ([WUBRG])", lambda m: Effect("drain_devotion", data={"color": m[1]})),
    (r"target creature(?: you control)? gets \+(\d+)/\+(\d+) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="creature")),
    (r"~ gets ([+-]\d+)/([+-]\d+) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="self")),
    (r"~ gets \+(\d+)/\+(\d+) and gains (flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="self", data={"keyword": m[3].lower()})),
    (r"enchanted creature gains (flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach) until end of turn",
     lambda m: Effect("grant", target="none", data={"keyword": m[1].lower(), "host": True})),
    (r"destroy target creature or enchantment", lambda m: Effect("destroy", target="nonland_perm", filter="creature_or_ench")),
    (r"destroy target creature an opponent controls that was dealt damage this turn",
     lambda m: Effect("destroy", target="creature", filter="opp_damaged")),
    (r"exile target (artifact or creature|tapped creature) an opponent controls until ~ leaves the battlefield",
     lambda m: Effect("oring", target="nonland_perm", filter="opp_tapped_creature" if m[1].startswith("tapped")
                      else "opp_artifact_creature")),
    (r"counter target artifact or enchantment spell", lambda m: Effect("counter", target="spell", filter="artifact_ench")),
    (r"destroy target noncreature, nonland permanent", lambda m: Effect("destroy", target="nonland_perm", filter="noncreature")),
    (r"return target card from your graveyard to your hand", lambda m: Effect("regrow_any", target="graveyard_card")),
    (r"return up to two target creatures to their owners' hands",
     lambda m: [_distinct_bounce(), _distinct_bounce()]),
    (r"one or two target creatures each get \+(\d+)/\+(\d+) until end of turn",
     lambda m: [_distinct_pump(m), _distinct_pump(m)]),
    (r"untap target artifact or creature", lambda m: Effect("untap_target", target="creature_mine")),
    (r"exile (?:each opponent's|target player's) graveyard", lambda m: Effect("exile_gy")),
    (r"exile target card from an opponent's graveyard", lambda m: Effect("exile_gy", 1)),
    (r"target player draws (a|two|three) cards?", lambda m: Effect("draw", _num(m[1]))),
    (r"target player draws (a|two|three) cards? and loses (\d+) life",
     lambda m: [Effect("draw", _num(m[1])), Effect("lose_life", int(m[2]))]),
    (r"~ deals (\d+) damage to each player", lambda m: Effect("damage_each_player", int(m[1]))),
    (r"put (a|one|two|three|four|five|six) \+1/\+1 counters? on it", lambda m: Effect("p1_counters", _num(m[1]), target="prev")),
    (r"put (a|one|two|three|four) -1/-1 counters? on (?:up to one )?target creature",
     lambda m: Effect("shrink", _num(m[1]), target="creature", filter="opp")),
    (r"put (a|one|two) -1/-1 counters? on each creature", lambda m: Effect("shrink_all", _num(m[1]))),
    (r"return all attacking creatures to their owner's hand", lambda m: Effect("mass_bounce", data={"only": "attacking"})),
    (r"tap target permanent", lambda m: Effect("tap", 1, target="nonland_perm")),
    (r"each player draws a card", lambda m: Effect("draw_each", 1)),
    (r"target creature(?: an opponent controls)? can't block this turn", lambda m: Effect("cant_block_turn", target="creature")),
    (r"(up to (?:one|two|three)|one or two|up to two) target creatures can't block this turn",
     lambda m: [_distinct_cant_block() for _ in range({"one": 1, "two": 2, "three": 3, "one or two": 2}.get(
         m[1].split()[-1] if m[1].startswith("up to") else m[1], 2))]),
    (r"(?:it|that creature|the other) can't block this turn", lambda m: Effect("cant_block_turn", target="prev")),
    (r"target creature blocks this turn if able", lambda m: Effect("force_block", target="creature")),
    (r"target creature attacks or blocks this turn if able",
     lambda m: Effect("force_block", target="creature", data={"attack": True})),
    (r"(?:it|~) must be blocked (?:this turn|each combat this turn) if able",
     lambda m: Effect("force_blocked", target="prev" if m[0].lower().startswith("it") else "self")),
    (r"target opponent exiles a card from their hand", lambda m: Effect("opp_exile_hand")),
    (r"return target creature card from your graveyard to the battlefield", lambda m: Effect("reanimate_one", target="graveyard_card")),
    (r"return up to one target permanent card from your graveyard to your hand", lambda m: Effect("regrow_perm", target="graveyard_card", data={"upto": True})),
    (r"counter target spell with mana value (\d+)",
     lambda m: Effect("counter", target="spell", filter=f"cmc:{m[1]}")),
    (r"counter target artifact or creature spell",
     lambda m: Effect("counter", target="spell", filter="artifact_creature")),
    (r"discover x, where x is that spell's mana value",
     lambda m: Effect("discover", 0, target="prev", data={"x_of": "spell"})),
    (r"if the discovered card's mana value is less than 10, create a number of tapped treasure tokens equal to "
     r"the difference", lambda m: Effect("discover_treasures")),
    (r"exile all creatures", lambda m: Effect("exile_all_creatures")),
    (r"empower jace x, where x is the number of creatures exiled this way",
     lambda m: Effect("empower", 0, data={"count": "exiled"})),
    (r"counter target creature or enchantment spell",
     lambda m: Effect("counter", target="spell", filter="creature_ench")),
    (r"counter target (noncreature |creature |instant or sorcery )?spell"
     r"(?: unless its controller pays \{(\d+)\})?",
     lambda m: Effect("counter", int(m[2] or 0), target="spell",
                      filter=(m[1] or "").strip().replace("instant or sorcery", "instant_sorcery"))),
    (r"return target spell you don't control to its owner's hand", lambda m: Effect("bounce_spell", target="spell")),
    (r"you lose (\d+) life", lambda m: Effect("lose_life", int(m[1]))),
    (r"(?:that player|they) loses? (\d+) life", lambda m: Effect("lose_life", int(m[1]), target="that_player")),
    (r"creatures your opponents control get -(\d+)/-(\d+) until end of turn",
     lambda m: Effect("debuff", int(m[1]), int(m[2]), target="opp_creatures")),
    # Crippling Fear: approximated as "your creatures share the chosen type".
    (r"creatures that aren't of the chosen type get -(\d+)/-(\d+) until end of turn",
     lambda m: Effect("debuff", int(m[1]), int(m[2]), target="opp_creatures")),
    (r"target creature(?: an opponent controls| you don't control)? gets -(\d+)/-(\d+) until end of turn",
     lambda m: Effect("debuff_one", int(m[1]), int(m[2]), target="creature")),
    (r"(?:all creatures|each creature) gets? -(\d+)/-(\d+) until end of turn",
     lambda m: Effect("debuff", int(m[1]), int(m[2]), target="each_creature")),
    (r"choose a creature type", lambda m: None),
    (r"each player who controls a multicolored creature draws a card", lambda m: None),  # rarely matters
    (r"damage can't be prevented this turn", lambda m: None),
    (r"destroy all creatures", lambda m: Effect("wrath", target="each_creature")),
    (r"destroy all planeswalkers", lambda m: Effect("wrath_pw")),
    (r"return (?:up to one )?(?:other )?target (?:nonland permanent|creature|artifact, creature, enchantment, or "
     r"planeswalker)"
     r"(?: an opponent controls| you don't control)? to its owner's hand",
     lambda m: Effect("bounce", target="nonland_perm")),
    (r"scry (\d+)", lambda m: Effect("scry", int(m[1]))),
    (r"surveil (\d+)", lambda m: Effect("surveil", int(m[1]))),
    (r"put x \+1/\+1 counters on each creature you control, where x is the number of cards in your hand",
     lambda m: Effect("p1_counters", 0, target="my_creatures", data={"x": "hand"})),
    (r"for each opponent, return up to one target artifact or creature that player controls to its owner's hand",
     lambda m: Effect("bounce", target="nonland_perm", filter="opp")),
    (r"add ((?:\{[WUBRG]\})+)", lambda m: Effect("add_mana", data={"colors": re.findall(r"[WUBRG]", m[1])})),
    (r"transform ~", lambda m: Effect("transform", target="self")),
    (r"NETTAP", lambda m: Effect("tap", 1, target="nonland_perm", data={"net": True})),
    (r"OPTCOST (\S+) (\d+)", lambda m: Effect("opt_cost_draw", int(m[2]), data={"cost": m[1]})),
    (r"THREATEN", lambda m: Effect("threaten", target="creature", filter="opp")),
    (r"MERCENARY (\w+)", lambda m: Effect("token", 0 if m[1].lower() == "x" else _num(m[1]), data={
        "name": "Mercenary", "power": 1, "toughness": 1, "keywords": frozenset(), "mercenary": True,
        "x": m[1].lower() == "x"})),
    (r"IRENCRAG", lambda m: Effect("irencrag")),
    (r"harness ~", lambda m: Effect("harness")),
    (r"search your library for a card, put it into your graveyard, then shuffle", lambda m: Effect("tutor_gy")),
    (r"return up to two creature cards with total mana value 4 or less from your graveyard to the battlefield",
     lambda m: Effect("reanimate_total", 4)),
    (r"search your library for an artifact card with mana value equal to 1 plus the sacrificed artifact's mana value, "
     r"put that card onto the battlefield, then shuffle", lambda m: Effect("bay_search")),
    (r"STARCAGE", lambda m: Effect("starcage")),
    (r"COVERUP", lambda m: Effect("cover_up", cond="evidence")),
    (r"OBSESS", lambda m: Effect("add_counter", 0, target="creature_mine", data={"counter": "+1/+1", "x": "sacrificed"})),
    (r"SACDRAWTREASURE", lambda m: Effect("sac_draw_treasure")),
    (r"AZOG (\w+?)s?", lambda m: Effect("destroy", target="creature", data={"azog": m[1].capitalize()})),
    (r"DIGFLOW (\d+)", lambda m: Effect("dig", int(m[1]), 1, data={"instead_two": "instant+sorcery"})),
    (r"DIG (\d+) (\d+)", lambda m: Effect("dig", int(m[1]), int(m[2]))),
    (r"DIGPUT (\d+) (\d+)", lambda m: Effect("dig_put", int(m[1]), int(m[2]))),
    (r"DIGPUTNONCREATURE (\d+) (\d+) (\d+)",
     lambda m: Effect("dig_put", int(m[1]), int(m[2]), data={"count": int(m[3]), "noncreature": True})),
    (r"DIGFILTER (\d+) (.+)", lambda m: Effect("dig", int(m[1]), 1, data={"filter": m[2]})),
    (r"DIGLANDS (\d+)", lambda m: Effect("dig", 0, int(m[1]), data={"x_lands": True})),
    (r"DIGCOUNT (\w+) (\d+)", lambda m: Effect("dig", 0, int(m[2]), data={"x_count": m[1]})),
    (r"IMPULSE (\d+)", lambda m: Effect("draw", int(m[1]))),   # "exile the top N, you may play them"
    (r"TARGETDISCARD", lambda m: Effect("discard_choice", 1, target="player")),
    (r"TARGETDISCARDNONCREATURE", lambda m: Effect("discard_choice", 1, target="player", filter="noncreature")),
    (r"(?:target player|each opponent) mills (a|one|two|three|four|five|\d+) cards?",
     lambda m: Effect("mill", _num(m[1]), target="player")),
    (r"mill (a|one|two|three|four|five|\d+) cards?", lambda m: Effect("mill", _num(m[1]))),
    (r"(?:you may )?exile the top (card|one card|two cards|three cards|four cards|\d+ cards) of your library",
     lambda m: Effect("exile_top", _N_WORDS.get(m[1].split()[0], 1) if m[1] != "card" else 1)
     if not m[1][0].isdigit() else Effect("exile_top", int(m[1].split()[0]))),
    (r"(?:you may play (?:that card|those cards|it|them|the exiled cards?) (this turn|until the end of your next turn|"
     r"until your next end step)|until the end of your next turn, you may play (?:that card|those cards|it|them))",
     lambda m: Effect("may_play_exiled", 0 if m[1] == "this turn" else 2)),
    (r"tap (?:up to one )?target (?:creature|nonland permanent)(?: an opponent controls| you don't control)?",
     lambda m: Effect("tap", 1, target="creature")),
    (r"tap up to (two|three) target creatures", lambda m: Effect("tap", _num(m[1]), target="creature")),
    (r"tap target creature(?: an opponent controls)? and put (a|two|three) stun counters? on it",
     lambda m: [Effect("tap", 1, target="creature"), Effect("stun", _num(m[1]), target="prev")]),
    (r"put (a|two|three) stun counters? on it", lambda m: Effect("stun", _num(m[1]), target="prev")),
    (r"put (a|two|three) stun counters? on (?:up to one )?target tapped creature(?: an opponent controls)?",
     lambda m: Effect("stun", _num(m[1]), target="creature", filter="tapped")),
    (r"target creature(?: you control)? with power (\d+) or less can't be blocked this turn",
     lambda m: Effect("unblockable", target="creature_mine", filter=f"max_power:{m[1]}")),
    (r"(?:up to one )?target creature you control can't be blocked this turn",
     lambda m: Effect("unblockable", target="creature_mine")),
    (r"earthbend (\w+)", lambda m: Effect("earthbend", _num(m[1]))),
    (r"GOBLINGUIDE", lambda m: Effect("reveal_land", target="each_opponent")),
    (r"FETCHBASIC( UNTAP4)?", lambda m: Effect("fetch_basic", data={"untap4": bool(m[1])})),
    (r"double the number of \+1/\+1 counters on ~", lambda m: Effect("double_counters", target="self")),
    (r"double the power of target creature you control until end of turn",
     lambda m: Effect("double_power", target="creature_mine")),
    (r"(?:then )?draw a card for each opponent who lost life this turn",
     lambda m: Effect("draw", 1, cond="opp_lost_life")),
    (r"target player discards a card", lambda m: Effect("discard", 1, target="player")),
    (r"each opponent discards a card", lambda m: Effect("discard", 1, target="player")),
    (r"if (?:that|the) (?:creature|permanent|creature or planeswalker) would die this turn, exile it instead",
     lambda m: Effect("exile_instead", target="prev")),
    (r"discard your hand, then draw two cards", lambda m: Effect("wheel_self")),
    (r"return all non-(\w+) creatures to their owners' hands", lambda m: Effect("mass_bounce", data={"except": m[1]})),
    (r"return one or two target creatures and/or enchantments you own to your hand",
     lambda m: Effect("bounce_own", target="nonland_perm", filter="mine")),
    (r"(?:you )?recruit", lambda m: Effect("recruit")),
    (r"return up to (one|two) target creature cards? from your graveyard to your hand",
     lambda m: Effect("regrow", _num(m[1]), target="graveyard_card", data={"upto": True})),
    (r"return ~ to its owner's hand", lambda m: Effect("bounce_self")),
    (r"empower jace (\d+)", lambda m: Effect("empower", int(m[1]))),
    (r"empower jace x, where x is the number of (creatures|islands) you control",
     lambda m: Effect("empower", 0, data={"count": m[1].lower()})),
    (r"create x (mutagen) tokens", lambda m: Effect("token", 0, data={"kind": "mutagen", "x": True})),
    (r"discover (\d+)", lambda m: Effect("discover", int(m[1]))),
    (r"(?:~|it|he|she) connives", lambda m: Effect("connive", target="prev")),
    (r"(?:up to one )?target creature you control connives", lambda m: Effect("connive", target="creature_mine")),
    (r"create an? (royal|monster|wicked|cursed|sorcerer|young hero|virtuous) role token attached to "
     r"(it|that creature|(?:up to one )?(?:another |other )?target creature you control|target creature an opponent controls)",
     lambda m: Effect("role", target="prev" if m[2] in ("it", "that creature") else
                      "creature" if "opponent" in m[2] else "creature_mine",
                      filter="opp" if "opponent" in m[2] else "", data={"role": m[1].lower()})),
    (r"STUNLANDSWAP", lambda m: Effect("land_swap")),
    (r"(\w+) and (\w+)s you control gain (indestructible|hexproof|vigilance|trample|haste|lifelink|first strike|deathtouch) "
     r"until end of turn",
     lambda m: Effect("grant_types", data={"types": (m[1], m[2]), "keyword": m[3].lower()})),
    (r"amass (\w+) (\d+)", lambda m: Effect("amass", int(m[2]), data={"type": m[1].rstrip("s").capitalize()})),
    (r"(?:defending player|target opponent) loses (\d+) life and you gain (\d+) life",
     lambda m: [Effect("drain", int(m[1]), target="each_opponent"), Effect("gain_life", int(m[2]))]),
    (r"you draw a card and lose (\d+) life", lambda m: [Effect("draw", 1), Effect("lose_life", int(m[1]))]),
    (r"(?:target|each) opponent discards (a|two|three) cards?", lambda m: Effect("discard", _num(m[1]), target="player")),
    (r"(?:target|each) opponent sacrifices a creature(?: of their choice)?", lambda m: Effect("edict", 1)),
    (r"another target creature you control gains (deathtouch|first strike|lifelink|trample|haste|indestructible|"
     r"hexproof|vigilance|menace|reach|flying) until end of turn",
     lambda m: Effect("grant", target="creature_mine", data={"keyword": m[1].lower()})),
    (r"put (a|one|two|three) \+1/\+1 counters? on another target creature you control",
     lambda m: Effect("p1_counters", _num(m[1]), target="creature_mine")),
    (r"~ deals 1 damage to each of one or two targets", lambda m: Effect("damage", 1, target="any")),
    (r"investigate", lambda m: Effect("token", 1, data={"kind": "clue"})),
    (r"(?:~|it|this creature) endures (\d+)", lambda m: Effect("endure", int(m[1]))),
    (r"manifest dread(?:, then attach (?:~|this equipment) to that creature)?",
     lambda m: Effect("manifest_dread", data={"attach": "attach" in m[0].lower()})),
    (r"untap ~", lambda m: Effect("untap_self")),
    (r"untap it", lambda m: Effect("untap_prev", target="prev")),
    (r"it explores", lambda m: Effect("explore", target="prev")),
    (r"exile up to (one|two) target cards? from (?:a|a single) graveyard",
     lambda m: Effect("exile_gy_cards", _num(m[1]))),
    (r"put target card from (a|your) graveyard on the bottom of (?:its owner's|your) library",
     lambda m: Effect("gy_bottom", data={"mine": m[1] == "your"})),
    (r"you may mill (a|one|two|three|four|five|\d+) cards?", lambda m: Effect("mill", _num(m[1]))),
    (r"target creature(?: you control)? gets \+(\d+)/\+(\d+) and gains (flying|first strike|double strike|deathtouch|"
     r"lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="creature", data={"keyword": m[3].lower()})),
    (r"(?:then )?discard (a|one|two|three) cards? unless you discard an? basic land card",
     lambda m: Effect("discard", _num(m[1]), data={"unless": "basic_land"})),
    (r"(?:then )?discard (a|one|two|three) cards?(?: unless .*)?", lambda m: Effect("discard", _num(m[1]))),
    (r"RUMMAGE (\d+)", lambda m: Effect("rummage", int(m[1]))),
    (r"create (a|one|two|three|four|five) (\d+)/(\d+) ((?:\w+ )+?)creature tokens?(?: named [\w' ,-]+?)?(?: that's "
     r"(tapped and attacking))?(?: with ([\w ,]+))?",
     lambda m: _token(m[1], m[2], m[3], m[4], m[6], bool(m[5]))),
    (r'create (a) (\d+)/(\d+) ((?:\w+ )+?)creature token with "(.+)"',
     lambda m: _token(m[1], m[2], m[3], m[4], "", False, m[5])),
    (r"create (a|one|two|three) (treasure|clue|blood|map|lander|food|mutagen) tokens?",
     lambda m: Effect("token", _num(m[1]), data={"kind": m[2].lower()})),
    (r"create (a|one|two|three|four|five|six|seven|eight|nine|ten) tapped (treasure|clue|blood|map|lander|food|mutagen) "
     r"tokens?", lambda m: Effect("token", _TENS.get(m[1].lower(), 1), data={"kind": m[2].lower(), "tapped": True})),
    (r"create (a|one|two|three|four|five) tapped (\d+)/(\d+) ((?:\w+ )+?)creature tokens?(?: with ([\w ,]+))?",
     lambda m: _tapped(_token(m[1], m[2], m[3], m[4], m[5]))),
    (r"target player creates (a|one|two|three) (treasure|clue|blood|map|lander|food|mutagen) tokens?",
     lambda m: Effect("token", _num(m[1]), data={"kind": m[2].lower()})),
    (r"its controller creates (a|one|two|three) (treasure|clue|blood|map|lander|food|mutagen) tokens?",
     lambda m: Effect("token", _num(m[1]), target="that_controller", data={"kind": m[2].lower()})),
    (r"target creature you control explores", lambda m: Effect("explore", target="creature_mine")),
    (r"(?:you may )?return ~ from your graveyard to the battlefield", lambda m: Effect("return_self_gy")),
    (r"~ explores", lambda m: Effect("explore", target="self")),
    (r"its controller (?:may search their library|searches their library) for a basic land card, puts? it onto the "
     r"battlefield tapped, then shuffles?", lambda m: Effect("fetch_basic", target="that_controller")),
    (r"exile target nonland permanent(?: an opponent controls| you don't control)?(?: with mana value (\d+) or "
     r"less)? until ~ leaves the battlefield",
     lambda m: Effect("oring", target="nonland_perm", filter=f"max_cmc:{m[1]}" if m[1] else "opp")),
    (r"exile all artifacts and creatures with mana value (\d+) or less until ~ leaves the battlefield",
     lambda m: Effect("oring_all", int(m[1]))),
    (r"(?:destroy|exile) target nonland permanent(?: an opponent controls| you don't control)?",
     lambda m: Effect("destroy", target="nonland_perm")),
    (r"its controller loses (\d+) life and you gain (\d+) life",
     lambda m: [Effect("lose_life", int(m[1]), target="that_controller"), Effect("gain_life", int(m[2]))]),
    (_SRC + r" deals damage equal to the number of (treasures|artifacts|creatures|lands) you control to any target",
     lambda m: Effect("damage", 0, target="any", data={"count": m[1].lower()})),
    (r"its controller investigates", lambda m: Effect("token", 1, target="that_controller", data={"kind": "clue"})),
    (r"create a token that's a copy of target token you control", lambda m: Effect("copy_token")),
    (r"put (a|one|two|three) \+1/\+1 counters? on (?:up to one )?target creature(?: or Vehicle)?(?: you control)?",
     lambda m: Effect("p1_counters", _num(m[1]), target="creature_mine")),
    (r"put (a|one|two|three) \+1/\+1 counters? on ~", lambda m: Effect("p1_counters", _num(m[1]), target="self")),
    (r"ELSPETHPLUS", lambda m: Effect("p1_counters", 1, target="creature_mine", data={"keyword": "flying"})),
    (r"(?:it|~) deals (\d+) damage", lambda m: Effect("damage", int(m[1]), target="prev")),
    (r"that creature gets -(\d+)/-(\d+) until end of turn",
     lambda m: Effect("debuff_one", int(m[1]), int(m[2]), target="prev")),
    (r"that creature gets \+(\d+)/\+(\d+) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="prev")),
    (r"destroy that creature", lambda m: Effect("destroy", target="prev")),
    (r"(?:it|that creature) also gains ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach))(?: and ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)))? until end of turn",
     lambda m: [Effect("grant", target="prev", data={"keyword": k.lower()}) for k in m.groups() if k]),
    (r"~ also deals (\d+) damage to that creature's controller",
     lambda m: Effect("damage", int(m[1]), target="that_controller")),
    (r"(?:it|that creature) gets \+(\d+)/\+(\d+)(?: and gains ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach))(?: and ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)))?)? until end of turn",
     lambda m: [Effect("pump", int(m[1]), int(m[2]), target="prev")] +
     [Effect("grant", target="prev", data={"keyword": k.lower()}) for k in (m[3], m[4]) if k]),
    (r"(?:it|that creature) gains ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) and ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) until end of turn",
     lambda m: [Effect("grant", target="prev", data={"keyword": k.lower()}) for k in (m[1], m[2])]),
    (r"it gains (hexproof|first strike|haste|indestructible|trample|lifelink|flying|vigilance|menace) until end of turn",
     lambda m: Effect("grant", target="prev", data={"keyword": m[1].lower()})),
    (r"target creature gains ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) and ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) until end of turn",
     lambda m: [Effect("grant", target="creature", data={"keyword": m[1].lower()}),
                Effect("grant", target="prev", data={"keyword": m[2].lower()})]),
    (r"target creature gains your choice of ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) or (?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach) until end of turn",
     lambda m: Effect("grant", target="creature", data={"keyword": m[1].lower()})),
    (r"put (a|one|two) \+1/\+1 counters? on each creature target player controls",
     lambda m: Effect("p1_counters", _num(m[1]), target="my_creatures")),
    (r"that creature deals (\d+) damage to each opponent", lambda m: Effect("damage", int(m[1]), target="player")),
    (r"target attacking creature token( you control)? gains "
     r"(flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach) until end of turn",
     lambda m: Effect("grant", target="creature_mine" if m[1] else "creature", filter="attacking_token",
                      data={"keyword": m[2].lower()})),
    (r"target creature gains (double strike|first strike|trample|haste|hexproof|indestructible) until end of turn",
     lambda m: Effect("grant", target="creature", data={"keyword": m[1].lower()})),
    (r"return (all |(?:up to )?(?:one|two|three|four|five|six|x) (?:other )?target |(?:up to one )?target |an? )?"
     r"([\w ,/'-]+?) cards?(?: each)?(?: with mana value (\d+|x) or (less|greater))? from (your|a|an opponent's) "
     r"graveyard (to your hand|(?:onto|to) the battlefield)( tapped)?(?: under your control)?",
     lambda m: _gy_move(m)),
    (r"target instant or sorcery card in your graveyard gains flashback until end of turn"
     r"(?:, with a flashback cost equal to its mana cost)?",
     lambda m: Effect("grant_flashback", target="graveyard_spell")),
    (r"~ becomes prepared", lambda m: Effect("prepare", target="self")),
    (r"put (?:a|an) ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) counter on (target creature|~|it)",
     lambda m: Effect("grant", target=_kw_target(m[2]), data={"keyword": m[1].lower(), "perm": True})),
    (r"put (a|two) \+1/\+1 counters? and (?:a|an) ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) counter on (target creature|~|it)",
     lambda m: [Effect("p1_counters", _num(m[1]), target=_kw_target(m[3])),
                Effect("grant", target="prev" if m[3] != "~" else "self", data={"keyword": m[2].lower(), "perm": True})]),
    (r"put (?:a|an) ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) counter, (?:a|an) ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) counter, and (?:a|an) ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) counter on target creature",
     lambda m: [Effect("grant", target="creature_mine", data={"keyword": m[1].lower(), "perm": True})] +
     [Effect("grant", target="prev", data={"keyword": m[i].lower(), "perm": True}) for i in (2, 3)]),
    (r"put an? (\w+) counter on ~", lambda m: Effect("add_counter", 1, target="self", data={"counter": m[1].lower()})),
    (r"if you attacked with two or more creatures this turn, draw a card",
     lambda m: Effect("draw", 1, cond="attacked2")),
    (r"otherwise, create a (\d+)/(\d+) ((?:\w+ )+?)creature token",
     lambda m: Effect(**{**_token("a", m[1], m[2], m[3]).__dict__, "cond": "not_attacked2"})),
    (r"then if ~ has (three) or more \w+ counters on it, transform it",
     lambda m: Effect("transform", target="self", cond="counters3")),
    (r"exile this saga, then return it to the battlefield transformed under your control|exile ~, then return it "
     r"to the battlefield transformed under your control", lambda m: Effect("transform", target="self")),
    (r"if a player is dealt damage this way, scry (\d+)", lambda m: Effect("scry", int(m[1]), cond="target_player")),
    (r"return target creature card from your graveyard to your hand",
     lambda m: Effect("regrow", target="graveyard_card")),
    (r"REANIMATESNOW", lambda m: Effect("reanimate_snow")),
    (r"GYHATE (\d+)", lambda m: Effect("gy_hate", int(m[1]))),
    (r"when you cast your next creature spell this turn, that creature enters with an additional \+1/\+1 counter "
     r"on it", lambda m: Effect("next_creature_counter")),
    (r"ADVERSARY", lambda m: Effect("adversary", data={"cost": {"generic": 2, "R": 1}})),
    (r"~ gains ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach))(?: and ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)))? until end of turn",
     lambda m: [Effect("grant", target="self", data={"keyword": k.lower()}) for k in m.groups() if k]),
    (r"put (a|one|two|three) \+1/\+1 counters? on each (other )?creature you control",
     lambda m: Effect("p1_counters", _num(m[1]), target="my_creatures", data={"other": bool(m[2])})),
    (r"(other )?creatures you control get \+(\d+)/\+(\d+)(?: and gain ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)))? until end of turn",
     lambda m: Effect("pump_all", int(m[2]), int(m[3]), data={"other": bool(m[1]), "keyword": (m[4] or "").lower()})),
    (r"(other )?creatures you control gain (KW) and get \+(\d+)/\+(\d+) until end of turn".replace("KW", "(?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)"),
     lambda m: Effect("pump_all", int(m[3]), int(m[4]), data={"other": bool(m[1]), "keyword": m[2].lower()})),
    (r"(other )?creatures you control gain ((?:flying|first strike|double strike|deathtouch|lifelink|vigilance|trample|haste|hexproof|indestructible|menace|reach)) until end of turn",
     lambda m: Effect("pump_all", 0, 0, data={"other": bool(m[1]), "keyword": m[2].lower()})),
    (r"double the number of \+1/\+1 counters on each creature you control",
     lambda m: Effect("double_counters", target="my_creatures")),
    (r"search your library for (an? .+?), reveal it, put it into your hand, then shuffle",
     lambda m: Effect("tutor", data={"what": m[1]})),
    (r"search your library for (an? .+?), put it into your hand, then shuffle",
     lambda m: Effect("tutor", data={"what": m[1]})),
]

_SUBS = [
    # Bind this cost sentence to the grant it qualifies. The engine's granted
    # flashback variant pays the card's mana cost; unrelated cost text stays visible.
    (re.compile(r"(target instant or sorcery card in your graveyard gains flashback until end of turn)\.\s+"
                r"the flashback cost is equal to its mana cost\.", re.I),
     lambda m: f"{m[1]}, with a flashback cost equal to its mana cost."),
    (re.compile(r"tap another target nonland permanent\. its activated abilities can't be activated for as long as it "
                r"remains tapped\.", re.I), lambda m: "NETTAP."),
    (re.compile(r"you may discard a card\. if you do, draw (a card|two cards)\.", re.I),
     lambda m: f"OPTCOST discard {_num(m[1].split()[0])}."),
    (re.compile(r"you may sacrifice (another |an? )?(creature or artifact|artifact or creature|artifact|creature|"
                r"enchantment or creature|artifact or creature)\. if you do, draw (a card|two cards)\.", re.I),
     lambda m: f"OPTCOST sac{'other' if (m[1] or '').startswith('another') else ''}:{m[2].replace(' or ', '|')} "
               f"{_num(m[3].split()[0])}."),
    (re.compile(r"you may sacrifice an artifact or discard a card\. if you do, draw a card\.", re.I),
     lambda m: "OPTCOST either 1."),
    (re.compile(r"gain control of target creature until end of turn\. untap that creature\. it gains haste until end "
                r"of turn\.", re.I), lambda m: "THREATEN."),
    (re.compile(r"create (a|an|x|one|two|three) 1/1 red mercenary creature tokens? with \"\{t\}: target creature you "
                r"control gets \+1/\+0 until end of turn\.\s*activate only as a sorcery\.\"", re.I),
     lambda m: f"MERCENARY {m[1]}."),
    (re.compile(r"put each card exiled with ~ into its owner's graveyard, then create a 2/2 colorless robot artifact "
                r"creature token for each card put into a graveyard this way\. sacrifice ~\.", re.I),
     lambda m: "STARCAGE."),
    (re.compile(r"you may have ~ become a legendary equipment artifact named everflame, heroes' legacy\. if you do, "
                r"it gains equip \{3\} and \"equipped creature gets \+3/\+3\" and loses all other abilities\.", re.I),
     lambda m: "IRENCRAG."),
    (re.compile(r"if evidence was collected, exile a card from an opponent's graveyard\. then search its owner's "
                r"graveyard, hand, and library for any number of cards with that name and exile them\. that player "
                r"shuffles, then draws a card for each card exiled from their hand this way\.", re.I),
     lambda m: "COVERUP."),
    (re.compile(r"put x \+1/\+1 counters on target attacking creature, where x is the number of permanents you've "
                r"sacrificed this turn\. if x is three or greater, that creature gains lifelink until end of turn\.",
                re.I), lambda m: "OBSESS."),
    (re.compile(r"you may sacrifice another creature or artifact\. if you do, draw a card and create a treasure token\.",
                re.I), lambda m: "SACDRAWTREASURE."),
    (re.compile(r"destroy up to one other target creature\. its controller amasses (\w+) x, where x is that creature's "
                r"power\. if you controlled that creature, draw a card\.", re.I), lambda m: f"AZOG {m[1]}."),
    (re.compile(r"look at the top (\w+) cards of your library\. put (\w+) of them into your hand and the "
                r"rest on the bottom of your library(?: in (?:a random|any|any random) order)?\. if there is an "
                r"instant card and a sorcery card in your graveyard, instead put two of them into your hand and the "
                r"rest on the bottom of your library in any order\.", re.I),
     lambda m: f"DIGFLOW {_num(m[1])}."),
    (re.compile(r"(create a \d+/\d+ (?:\w+ )+?creature token) named [\w' ,-]+?\. it gains haste until end of turn\.",
                re.I), lambda m: f"{m[1]} with haste."),
    (re.compile(r"you may discard a card\. if you do, draw a card\.", re.I), lambda m: "RUMMAGE 1."),
    (re.compile(r"each opponent loses X life, where X is your devotion to (white|blue|black|red|green)\. you gain "
                r"life equal to the life lost this way\.", re.I),
     lambda m: f"DEVOTIONDRAIN {dict(white='W', blue='U', black='B', red='R', green='G')[m[1].lower()]}."),
    (re.compile(r"defending player reveals the top card of their library\. if it's a land card, that player puts "
                r"it into their hand\.", re.I), lambda m: "GOBLINGUIDE."),
    (re.compile(r"target (?:player|opponent) reveals their hand\. you choose a noncreature, nonland card from it\. "
                r"that player discards that card\.", re.I), lambda m: "TARGETDISCARDNONCREATURE."),
    (re.compile(r"look at the top (\w+) cards of your library\. put (one) of them into your hand and the (?:other|rest) "
                r"on the bottom of your library(?: in any order)?\.", re.I),
     lambda m: f"DIG {_num(m[1])} {_num(m[2])}."),
    (re.compile(r"search your library for a basic land card, put it onto the battlefield tapped, then shuffle\."
                r"( then if you control four or more lands, untap that land\.)?", re.I),
     lambda m: "FETCHBASIC UNTAP4." if m[1] else "FETCHBASIC."),
    (re.compile(r"you may discard up(?: to)? (\w+) cards\. if you do, draw that many cards\.", re.I),
     lambda m: f"RUMMAGE {_num(m[1])}."),
    (re.compile(r"destroy target nonbasic land an opponent controls\. its controller searches their library for a basic "
                r"land card, puts it (?:onto|on) the battlefield tapped with a stun counter on it, then shuffles\.", re.I),
     lambda m: "STUNLANDSWAP."),
    (re.compile(r"choose up to one target creature\. put a \+1/\+1 counter and a counter from among flying, first "
                r"strike, lifelink, or vigilance on it\.", re.I), lambda m: "ELSPETHPLUS."),
    (re.compile(r"exile up to one target card from a graveyard\. if a creature card was exiled this way, each "
                r"opponent loses (\d+) life and you gain \d+ life\.", re.I), lambda m: f"GYHATE {m[1]}."),
    (re.compile(r"look at the top (\w+) cards of your library\. put (\w+) of them into your hand and the "
                r"rest on the bottom of your library(?: in (?:a random|any|any random) order)?\.", re.I),
     lambda m: f"DIG {_num(m[1])} {_num(m[2])}."),
    (re.compile(r"look at the top (\w+) cards of your library\. you may reveal (an? .+? card) from among them and "
                r"put it into your hand\. put the rest on the bottom of your library in (?:a random|any) order\.",
                re.I), lambda m: f"DIGFILTER {_num(m[1])} {m[2]}."),
    (re.compile(r"look at the top \w+ cards of your library, where X is the number of lands you control\. put "
                r"(\w+) of those cards into your hand\. put the rest on the bottom of your library in (?:a random|"
                r"any) order\.", re.I), lambda m: f"DIGLANDS {_num(m[1])}."),
    (re.compile(r"look at the top \w+ cards of your library, where X is the number of (artifacts|creatures|lands) "
                r"you control\. put (\w+) of those cards into your hand and the rest on the bottom of your library "
                r"in (?:a random|any) order\.", re.I), lambda m: f"DIGCOUNT {m[1][:-1]} {_num(m[2])}."),
    (re.compile(r"look at the top (\w+) cards of your library\. put up to (two) noncreature, nonland permanent "
                r"cards with mana value (\d+) or less from among them onto the battlefield\. put the rest on the "
                r"bottom of your library in a random order\.", re.I),
     lambda m: f"DIGPUTNONCREATURE {_num(m[1])} {m[3]} {_num(m[2])}."),
    (re.compile(r"look at the top (\w+) cards of your library\. you may put a permanent card with mana value "
                r"(\d+) or less from among them onto the battlefield(?: with a shield counter on it)?\. put the rest "
                r"on the bottom of your library in a random order\.", re.I),
     lambda m: f"DIGPUT {_num(m[1])} {m[2]}."),
    (re.compile(r"exile the top (card|\w+ cards) of your library\. until (?:the end of your next turn|end of turn), you "
                r"may play (?:that card|those cards)(?: this turn)?\.", re.I),
     lambda m: f"IMPULSE {1 if m[1] == 'card' else _num(m[1].split()[0])}."),
    (re.compile(r"target (?:player|opponent) reveals their hand\. you choose a nonland card from it\. that player discards "
                r"that card\.", re.I), lambda m: "TARGETDISCARD."),
    (re.compile(r"then return a creature or planeswalker card with mana value X or less from your graveyard to "
                r"the battlefield, where X is the amount of \{S\} spent to cast ~\.", re.I),
     lambda m: "REANIMATESNOW."),
    (re.compile(r"each player sacrifices all other creatures they control\. then each player returns all creature "
                r"cards from their graveyard that weren't put there this way to the battlefield\.", re.I),
     lambda m: "LASTGIFT."),
    (re.compile(r"you may discard a card\. if you do, search your library for a creature card, reveal it, put it "
                r"into your hand, then shuffle\.", re.I), lambda m: "DISCARDTUTOR."),
    # Face-down permanents aren't modelled, so the "unless" clause never applies.
    (re.compile(r"you may draw a card\. if you do, discard a card unless a permanent entered the battlefield face "
                r"down under your control this turn or you turned a permanent face up this turn\.", re.I),
     lambda m: "Draw a card. Then discard a card."),
    (re.compile(r"return it to the battlefield under its owner's control\. it's an enchantment\.(?: \(It's not a "
                r"creature\.\))?", re.I), lambda m: "RETURNENCHANT."),
    (re.compile(r"you may pay \{2\}\{R\} any number of times\. when you pay this cost one or more times, .*",
                re.I | re.S), lambda m: "ADVERSARY."),
]

_TRIGGERS = [
    (r"When(?:ever)? ~ enters or attacks, (.+)", ("etb", "attacks")),
    (r"When ~ enters and at the beginning of your upkeep, (.+)", ("etb", "upkeep")),
    (r"When(?:ever)? ~ enters?(?: the battlefield)?, (.+)", ("etb",)),
    (r"Whenever ~ attacks, (.+)", ("attacks",)),
    (r"When(?:ever)? ~ dies, (?:if it was a creature, )?(.+)", ("dies",)),
    (r"Whenever ~ deals combat damage to a player, (.+)", ("combat_damage_player",)),
    (r"Whenever a creature you control deals combat damage to a player, (.+)", ("ally_combat_damage",)),
    (r"Whenever you cast a noncreature spell, (.+)", ("cast_noncreature",)),
    (r"Whenever you cast an instant or sorcery spell, (.+)", ("cast_instant_sorcery",)),
    (r"Whenever you cast an instant or sorcery spell that targets a creature, (.+)", ("cast_instant_sorcery",)),
    (r"Whenever ~ becomes the target of a spell or ability you control for the first time each turn, (.+)",
     ("targeted_mine",)),
    (r"Whenever you cast a spell, (.+)", ("cast_spell",)),
    (r"Whenever you cast an? ([A-Z]\w+|creature|artifact|enchantment|outlaw) spell, (.+)", ("cast_spell",)),
    (r"Whenever you gain life, (.+)", ("gain_life",)),
    (r"Whenever you attack, (.+)", ("you_attack",)),
    (r"Whenever you attack with one or more ([A-Z]\w+), (.+)", ("you_attack",)),
    (r"Whenever a creature you control attacks, (.+)", ("creature_attacks",)),
    (r"When(?:ever)? ~ enters or leaves the battlefield, (.+)", ("etb", "leaves")),
    (r"When(?:ever)? ~ leaves the battlefield, (.+)", ("leaves",)),
    (r"Whenever a player casts a spell with mana value (\d+) or less, (.+)", ("any_cast",)),
    (r"At the beginning of your upkeep, (.+)", ("upkeep",)),
    (r"At the beginning of each opponent's draw step, (.+)", ("opp_draw_step",)),
    (r"At the beginning of your end step, (.+)", ("end_step",)),
    (r"At the beginning of your first main phase, (.+)", ("main1_begin",)),
    (r"Survival — At the beginning of your second main phase, if ~ is tapped, (.+)", ("survival",)),
    (r"At the beginning of your second main phase, (.+)", ("main2_begin",)),
    (r"Whenever a creature an opponent controls dies, (.+)", ("opp_creature_dies",)),
    (r"Whenever another creature you control enters or dies, if that creature's power is greater than ~'s, (.+)",
     ("other_creature_enters", "other_creature_dies")),
    (r"Whenever a land you control enters, (.+)", ("land_enters",)),
    (r"When(?:ever)? (~ or )?(another|an?) ((?:[\w-]+(?:,? or |, | ))*?(?:creature|artifact|enchantment|planeswalker|"
     r"[A-Z]\w+)s?) you control( with mana value \d+ or greater)? enters(?: and whenever an? ([A-Z]\w+) you control "
     r"enters| and whenever you fully unlock a Room)?, (.+)",
     ("permanent_enters",)),
    (r"Whenever you draw a card, (.+)", ("you_draw",)),
    (r"Whenever you sacrifice (an? [\w ]+?), (.+)", ("sacrifice",)),
    (r"Whenever an opponent draws a card, (.+)", ("opp_draw",)),
    (r"Whenever ~ becomes the target of a spell, (.+)", ("targeted_by_spell",)),
    (r"When(?:ever)? ~ enters or dies, (.+)", ("etb", "dies")),
    (r"When ~ is put into a graveyard from the battlefield, (.+)", ("dies",)),
    (r"At the beginning of combat on your turn, (.+)", ("begin_combat",)),
    (r"Whenever you draw your second card each turn, (.+)", ("draw_second",)),
    (r"Whenever you cast your second spell each turn, (.+)", ("cast_second",)),
    (r"Whenever a creature you control attacks alone, (.+)", ("attacks_alone",)),
    (r"Whenever you commit a crime, (.+)", ("crime",)),
    (r"Whenever you scry or surveil, (.+)", ("scry_surveil",)),
    (r"Whenever (?:one or more|an?) (?:(.+?) )?cards? (?:leaves?|leave) your graveyard( during your turn)?, (.+)",
     ("gy_leave",)),
    (r"Whenever you discard (?:a card|one or more cards), (.+)", ("you_discard",)),
    (r"Whenever you cast a spell with mana value (\d+) or greater, (.+)", ("cast_cmc",)),
    (r"Whenever ~ attacks while saddled, (.+)", ("attacks",)),
    (r"Whenever ~ becomes tapped, (.+)", ("becomes_tapped",)),
    (r"Whenever ~ enters or becomes tapped, (.+)", ("etb", "becomes_tapped")),
    (r"Whenever you expend (\d+), (.+)", ("expend",)),
    (r"Whenever (a|another) ([\w, -]+?) you control( with (?:a|an|one or more) (?:\+1/\+1 )?counters? on it)? dies, "
     r"(.+)", ("ally_dies",)),
    (r"Whenever (a|an|another) ([\w, -]+?) you control is put into a graveyard from the battlefield, (.+)",
     ("perm_to_gy",)),
]


_OPT_RIDER = re.compile(r"(?:then )?if (?:~|it|the spell) was bargained, (.+)|(?:then )?if the gift (was|wasn't) promised, (.+)",
                        re.I)


def _opt_rider(s: str, effects: list):
    """"If ~ was bargained / the gift was promised, X [instead]": X's effects carry cond bargained / gifted (or !gifted).
    With "instead" the earlier effect of the same kind (else every unconditional one) only happens otherwise.
    Returns the new effects, or None when X doesn't parse."""
    m = _OPT_RIDER.fullmatch(s)
    if m is None:
        return None
    cond = "bargained" if m[1] else ("gifted" if m[2].lower() == "was" else "!gifted")
    rest = (m[1] or m[3]).strip()
    instead = bool(re.search(r"\binstead$", rest, re.I)) or re.match(r"instead,? ", rest, re.I) is not None
    rest = re.sub(r",? instead$|^instead,? ", "", rest, flags=re.I)
    new, bad = _parse_effects(rest[0].upper() + rest[1:] + ".")
    if bad or not new:
        return None
    if instead:
        same = [e for e in effects if not e.cond and e.kind == new[0].kind]
        for e in same or [e for e in effects if not e.cond]:
            e.cond = "!" + cond
    for e in new:
        e.cond = e.cond or cond
    return new


_N_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "x": 0}


def _gy_move(m):
    head = (m[1] or "").lower()
    what = m[2]
    if re.search(r"\b(this|named|that)\b", what) or what.lower().startswith("up to"):
        return NO_MATCH
    w = re.search(r"(one|two|three|four|five|six|x)", head)
    n = 99 if head.startswith("all") else (_N_WORDS[w[1]] if w else 1)
    return Effect("gy_move", n, target="graveyard_card" if "target" in head else "none",
                  data={"upto": "up to" in head, "what": what, "dest": "hand" if m[6].endswith("hand") else "bf",
                                      "tapped": bool(m[7]), "zone": {"your": "mine", "a": "any"}.get(m[5], "opp"),
                                      "x_n": bool(w and w[1] == "x"),
                                      "cmc": ((m[3].lower() if m[3].lower() == "x" else int(m[3])), m[4]) if m[3] else None})


def _kw_target(what: str) -> str:
    return {"~": "self", "it": "prev"}.get(what, "creature_mine")


def _xq(text: str):
    """The quantity in ", where X is ...": a tuple the engine evaluates, or None when it isn't a known one."""
    t = text.strip().rstrip(".")
    tl = t.lower()
    from .counting import _singular
    if tl in ("your life total", "your speed", "the amount of life you gained this turn",
             "the number of cards in your hand"):
        return ({"your life total": ("life",), "your speed": ("speed",),
                 "the amount of life you gained this turn": ("gained",),
                 "the number of cards in your hand": ("hand",)}[tl])
    m = re.fullmatch(r"(~|its|that creature|that spell)'s? (power|toughness|mana value)", t, re.I) or \
        re.fullmatch(r"(its) (power|toughness)", t, re.I)
    if m:
        return ("stat", "prev" if m[1] == "that creature" else "self", m[2])
    m = re.fullmatch(r"the greatest (power|toughness) among creatures you control", t, re.I)
    if m:
        return ("greatest", m[1])
    m = re.fullmatch(r"the number of ([\w+/ -]+?) counters on ~", t, re.I)
    if m:
        return ("counters", m[1])
    m = re.fullmatch(r"the number of ([\w -]+?) cards? in your graveyard", t, re.I)
    if m:
        return ("gy", _singular(m[1]))
    if tl == "the number of cards in your graveyard":
        return ("gy", "")
    m = re.fullmatch(r"the number of ([\w -]+?) you control", t, re.I)
    if m and " with " not in m[1] and " that " not in m[1]:
        return ("count", _singular(m[1]))
    return None


_IF_CONDS = [
    (r"you attacked this turn", "attacked_turn"),
    (r"an opponent controls more lands than you", "opp_more_lands"),
    (r"a creature died this turn", "creature_died"),
    (r"a creature died under an opponent's control this turn", "opp_creature_died"),
    (r"you control another (outlaw|\w+)", None),
    (r"you control (two|three|four) or more tapped creatures", None),
    (r"you control a creature with power (\d+) or greater", None),
    (r"you sacrificed a permanent this turn", "sacrificed_turn"),
]


def _if_cond(phrase: str) -> str:
    """The engine condition name for the "if <phrase>," of a sentence, or ""."""
    phrase = phrase.strip()
    for rx, name in _IF_CONDS:
        m = re.fullmatch(rx, phrase, re.I)
        if not m:
            continue
        if name:
            return name
        if "another" in rx:
            return f"ctl_other:{m[1].capitalize() if m[1].lower() != 'outlaw' else 'outlaw'}"
        if "tapped" in rx:
            return f"tapped_creatures>={_N_WORDS.get(m[1].lower(), 2)}"
        return f"power_ge:{m[1]}"
    return ""


def _parse_effects(text: str, opts: bool = False):
    """Parse a run of sentences into effects. Returns (effects, unmatched_sentences)."""
    effects, unmatched = [], []
    for rx, rep in _SUBS:
        text = rx.sub(rep, text)
    gated = False
    for sentence in re.split(r"(?<=\.)\s+", text.strip()):
        s = sentence.strip().rstrip(".").strip()
        if not s:
            continue
        if not unmatched and _delayed.continuation(effects, s):
            continue
        mp = re.fullmatch(r"you may pay ((?:\{[WUBRGC0-9]+\})+)", s, re.I)
        if mp:
            effects.append(Effect("pay_gate", data={"cost": parse_mana_cost(mp[1])}))
            gated = True
            continue
        mg = re.fullmatch(r"you may (?:(sacrifice (?:another |an? )(?:artifact, enchantment, or token|[a-z]+(?: or [a-z]+)?))"
                          r"|(discard a card)|(forage)|blight (\d+))", s, re.I)
        if mg:
            if mg[1]:
                what = mg[1].lower().split(" ", 1)[1]
                other = what.startswith("another ")
                kinds = re.sub(r"^(?:another|an?) ", "", what).replace(", or ", " or ").replace(", ", " or ")
                gate = ("sac", ("other " if other else "") + kinds)
            elif mg[2]:
                gate = ("discard", "")
            elif mg[3]:
                gate = ("forage", "")
            else:
                gate = ("blight", mg[4])
            effects.append(Effect("pay_gate", data={"gate": gate}))
            gated = True
            continue
        mx = re.fullmatch(r"(.+?),? where X is (.+)", s, re.I)
        if mx and re.search(r"\bX\b", mx[1]) and _xq(mx[2]):
            spec = _xq(mx[2])
            new, bad = [], True
            for one in ("1", "one", "a"):
                body = re.sub(r"\bX\b", one, mx[1])
                if one != "1":
                    body = re.sub(r"\b(creature |artifact )?tokens\b", r"\1token", body)
                new, bad = _parse_effects(body + ".")
                if new and not bad:
                    break
            if new and not bad:
                for e in new:
                    e.data["xq"] = spec
                    e.data["xq_size"] = bool(re.search(r"\bX/X\b", mx[1]))
                effects += new
                continue
        if opts:
            new = _opt_rider(s, effects)
            if new is not None:
                effects += new
                continue
        mi = re.fullmatch(r"if (.+?), (.+)", s, re.I)
        if mi:
            cond = _if_cond(mi[1])
            if cond:
                for body in (mi[2], re.sub(r"^you ", "", mi[2])):
                    new, bad = _parse_effects(body[0].upper() + body[1:] + ".")
                    if new and not bad:
                        effects += [dataclasses.replace(e, cond=e.cond or cond) for e in new]
                        break
                else:
                    unmatched.append(sentence.strip())
                continue
        first = len(effects)
        paid = False
        reflexive = False
        if gated:
            g = re.fullmatch(r"(?:if you do|when you do), (.+)", s, re.I)
            if g:
                reflexive = s.lower().startswith("when you do")
                s, paid = g[1], True
        for pat, build in _EFFECT_PATTERNS:
            m = re.fullmatch(pat, s, flags=re.IGNORECASE)
            if m is None and s.lower().startswith("then "):
                m = re.fullmatch(pat, s[5:], flags=re.IGNORECASE)
            if m:
                eff = build(m)
                if eff is NO_MATCH:
                    continue
                if isinstance(eff, list):
                    effects += eff
                elif eff is not None:
                    effects.append(eff)
                break
        else:
            parts = _split_compound(s)
            if parts:
                effects += parts
            else:
                unmatched.append(sentence.strip())
        if paid and reflexive and any(e.target == "graveyard_card" for e in effects[first:]):
            effects[first:] = [Effect("reflexive", cond="paid", data={"effects": effects[first:]})]
        elif paid:
            for eff in effects[first:]:
                eff.cond = eff.cond or "paid"
    return effects, unmatched


def _split_compound(s: str):
    """Effects for "A, then B" / "A and B" when every part matches a template, else None."""
    for sep in (r",? then ", r" and "):
        pieces = re.split(sep, s, maxsplit=1, flags=re.I)
        if len(pieces) != 2:
            continue
        out = []
        for piece in pieces:
            effs, bad = _parse_effects(piece[0].upper() + piece[1:] + ".")
            if bad or not effs:
                break
            out += effs
        else:
            return out
    return None


def _apply_speed_gate(gate, triggers, activated):
    """Gate what a "Max speed — ..." line just added: its triggers' effects and its activated abilities."""
    for t in triggers[gate[0]:]:
        for eff in t.effects:
            eff.cond = eff.cond or "max_speed"
    for a in activated[gate[1]:]:
        a.needs_max_speed = True


def _face_types(type_line: str) -> frozenset:
    main_types = type_line.split("—")[0]
    return frozenset(t for t in ("Land", "Creature", "Instant", "Sorcery", "Artifact",
                                 "Enchantment", "Planeswalker", "Battle") if t in main_types)


def card_from_scryfall(data: dict) -> CardDef:
    faces = data.get("card_faces")
    if faces and not data.get("oracle_text"):
        card = _parse_face({**data, **faces[0]})
        if len(faces) > 1:
            back = faces[1]
            back_types = back.get("type_line", "")
            if "Adventure" in back_types:
                card.adventure = _parse_face(back)
            elif "Land" in back_types and not card.is_land:
                card.land_face = _parse_face(back)   # modal double-faced: may be played as this land
            elif re.search(r"Daybound|Nightbound", card.oracle):
                pass  # day/night isn't tracked; the day side stays
            else:
                card.back = _parse_face(back)
        return card
    return _parse_face(data)


def _cost_line(m):
    return parse_mana_cost(m)


def _parse_face(data: dict) -> CardDef:
    name = data["name"].split(" // ")[0]
    type_line = data.get("type_line", "").split(" // ")[0]
    types = _face_types(type_line)
    cost = parse_mana_cost(data.get("mana_cost", "").split(" // ")[0])

    def stat(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0 if v is not None else None

    oracle = data.get("oracle_text", "") or ""
    text = re.sub(r"\([^)]*\)", "", oracle)
    text = text.replace(name, "~")
    if "," in name and "Legendary" in type_line:
        text = re.sub(rf"\b{re.escape(name.split(',')[0])}\b", "~", text)  # "Iymrith" for "Iymrith, Desert Doom"
    elif "Legendary" in type_line and " " in name and " the " not in name and len(name.split()[0]) >= 4 and \
            name.split()[0] not in ("The", "Lord", "Lady", "King", "Queen", "Sir") and \
            re.search(rf"\b{re.escape(name.split()[0])}\b", text):
        text = re.sub(rf"\b{re.escape(name.split()[0])}\b", "~", text)  # "Ajani" for "Ajani Resolute"
    elif " the " in name and "Legendary" in type_line:
        text = re.sub(rf"\b{re.escape(name.split(' the ')[0])}\b", "~", text)  # "Smaug the Magnificent"
    text = re.sub(r"\bthis (creature|land|spell|enchantment|artifact|permanent|token|vehicle|saga|aura|equipment)\b", "~",
                  text, flags=re.I)
    text = re.sub(r", where X is the amount of mana spent to cast ~\.", ".", text).replace(
        "the top X cards", f"the top {int(data.get('cmc', 0) or 0)} cards")

    text = re.sub(r"(?m)^((?:Exhaust — )?)Waterbend (\{\d+\}(?:, \{T\})?:)", r"\1\2", text)    # waterbend {N} pays like {N} here
    text = re.sub(r"(?m)^Ward—Waterbend (\{\d+\})", r"Ward \1", text)
    text = re.sub(r"(?m)^([A-Za-z ,]*[Ff]irebending \d+[A-Za-z ,]*)$", lambda m: "\n".join(x[0].upper() + x[1:] for x in m[1].split(", ")), text)
    keywords, produces, etb, spell, unsupported, approximations = set(), set(), [], [], [], []
    triggers: list[Trigger] = []
    extra: dict = {"snow": "Snow" in type_line, "legendary": "Legendary" in type_line.split("—")[0].split()}
    modes: list = []
    chapters: list = []
    loyalty_abilities: list = []
    alt_costs: list = []
    activated: list = []
    enters_tapped = False
    mode_sink = None     # where bullet lines go: modes of the spell or of the last trigger
    for sub in type_line.split("—")[-1].split():
        if sub in BASIC_MANA and "Land" in types:
            produces.add(BASIC_MANA[sub])
    raw_cost = data.get("mana_cost", "").split(" // ")[0]
    extra["hybrid"] = tuple(a + b for a, b in re.findall(r"\{([WUBRG])/([WUBRG])\}", raw_cost))
    if data.get("loyalty"):
        extra["loyalty"] = stat(data["loyalty"]) or 0

    kicked: list = []
    station_min = 0
    gate = None            # set while parsing a "Max speed — ..." line: what the line added is gated on speed 4
    for line in (l.strip() for l in text.split("\n")):
        if gate is not None:
            _apply_speed_gate(gate, triggers, activated)
            gate = None
        if not line:
            continue
        gm = re.fullmatch(r"Max speed — (.+)", line)
        if gm:
            gate = len(triggers), len(activated)
            line = gm[1]
            m = re.fullmatch(r"~ gets \+(\d+)/\+(\d+)(?: and has ([a-z ]+))?\.", line)
            if m:
                extra["pt_if"] = extra.get("pt_if", ()) + (("speed>=4", int(m[1]), int(m[2])),)
                if m[3] and m[3] in KEYWORDS:
                    extra["cond_keywords"] = extra.get("cond_keywords", ()) + ((m[3], "max_speed"),)
                continue
            m = re.fullmatch(r"~ has ([a-z ]+?)(?: and ([a-z ]+))?\.", line)
            if m and m[1] in KEYWORDS and (m[2] is None or m[2] in KEYWORDS):
                for kw in (m[1], m[2]):
                    if kw:
                        extra["cond_keywords"] = extra.get("cond_keywords", ()) + ((kw, "max_speed"),)
                continue
        if line == "Bargain":
            extra["bargain"] = True
            continue
        m = re.fullmatch(r"Gift (a card|a Food|a Treasure|a tapped Fish|an Octopus)", line)
        if m:
            extra["gift"] = m[1].split(" ", 1)[1].lower()
            continue
        m = re.fullmatch(r"((?:\{[WUBRGC0-9/]+\})+): Return (?:this card|~) from your graveyard to your hand\.", line)
        if m:
            extra["gy_return"] = parse_mana_cost(m[1])
            continue
        m = re.fullmatch(r"((?:\{[WUBRGC0-9/]+\})+), Exile this card from your graveyard: Draw a card\.", line)
        if m:
            extra["gy_exile_draw"] = parse_mana_cost(m[1])
            extra["gy_needs_speed"] = gate is not None
            continue
        if re.fullmatch(r"If one or more tokens would be created under your control, twice that many of those tokens "
                        r"are created instead\.", line):
            extra["token_double"] = True
            continue
        m = re.fullmatch(r"Creatures you control of the chosen type get \+(\d+)/\+(\d+)\.", line)
        if m:
            extra["anthem_chosen"] = (int(m[1]), int(m[2]))
            continue
        m = re.fullmatch(r"~ can't be blocked by creatures with power (\d+) or greater\.", line)
        if m:
            extra["max_blocker_power"] = int(m[1])
            continue
        if line == "~ can't be blocked.":
            keywords.add("unblockable")
            continue
        if line == "You have no maximum hand size.":
            extra["no_max_hand"] = True
            continue
        if line == "~ attacks each combat if able.":
            extra["must_attack"] = True
            continue
        m = re.fullmatch(r"~ enters with (\w+) -1/-1 counters on it\.", line)
        if m:
            extra["etb_named_counters"] = ("-1/-1", _num(m[1]))
            continue
        if line == "Job select":
            triggers.append(Trigger("etb", [Effect("job_select")]))
            continue
        if line == "Start your engines!":
            extra["start_engines"] = True
            continue
        if any(a.startswith("never paid: As an additional cost") for a in approximations):
            line = re.sub(r"\s*If ~'s additional cost was paid, [^.]+\.", "", line).strip()
            if not line:
                continue
        kicked += re.findall(r"If ~ was kicked, (.+?\.)", line)
        line = re.sub(r"\s*If ~ was kicked, .+?\.", "", line).strip()
        line = re.sub(r"^(?:Landfall|Revolt|Raid|Morbid|Eerie|Opus|Repartee|Valiant) — (?=When|At|If)", "", line)
        parts = [p.strip().lower() for p in line.split(",")]
        if all(p in KEYWORDS or re.fullmatch(r"ward \{\d+\}", p) for p in parts):
            for p in parts:
                if p.startswith("ward"):
                    extra["ward"] = int(re.search(r"\d+", p)[0])
                else:
                    keywords.add(p)
            continue
        bullet = modal.parse_bullet(line) if mode_sink is not None else None
        if bullet is not None:
            effs, bad = _parse_effects(bullet[1])
            if bad or not effs:
                unsupported.append(line)
            else:
                modal.add_mode(mode_sink, effs, bullet[0])
            continue
        mode_sink = None
        m = re.fullmatch(r"Ward—Pay (\d+) life\.", line)
        if m:
            extra["ward_life"] = int(m[1])
            continue
        if re.fullmatch(r"Ward—Discard a card\.", line):
            extra["ward_discard"] = True
            continue
        m = re.fullmatch(r"~ has ward \{(\d+)\} as long as it's untapped\.", line, flags=re.I)
        if m:
            extra.update(ward=int(m[1]), ward_untapped_only=True)
            continue
        m = re.fullmatch(r"\{T\}(, Pay 1 life)?: Add (one mana of any color|\{[WUBRGC]\}+)\. Spend this mana only "
                         r"(.+)\.", line)
        if m:
            restriction = _mana_restriction(m[3])
            if restriction is None:
                produces |= set(COLORS) if "any color" in m[2] else set(re.findall(r"[WUBRGC]", m[2]))
                unsupported.append(f"mana restriction ignored: Spend this mana only {m[3]}.")
                continue
            cols, amount = _parse_mana_ability(m[2])
            extra["mana_restriction"] = restriction
            extra["restricted_produces"] = frozenset(cols)
            if amount > 1:
                extra["mana_amount"] = amount
            if m[1]:
                approximations.append("the 1 life for restricted mana isn't paid")
            continue
        if re.fullmatch(r"As ~ enters(?: the battlefield)?, choose a creature type\.", line):
            extra["choose_type"] = "creature"
            continue
        if re.fullmatch(r"As ~ enters(?: the battlefield)?, choose a basic land type\. Then you may pay 2 life\. If you "
                        r"don't, it enters tapped\.", line):
            extra.update(choose_type="basic_land", tapped_condition="shock")
            continue
        if line == "~ is the chosen type." and extra.get("choose_type") == "basic_land":
            continue
        m = re.fullmatch(r"~ enters(?: the battlefield)? tapped unless you control (an? .+?)\.", line)
        if m and all(re.fullmatch(r"an? (basic land|[A-Z]\w+)", part) for part in m[1].split(" or ")):
            kinds = [re.fullmatch(r"an? (basic land|[A-Z]\w+)", part)[1] for part in m[1].split(" or ")]
            extra["tapped_condition"] = "unless_control:" + "|".join("basic" if k == "basic land" else k for k in kinds)
            continue
        if re.fullmatch(r"~ enters(?: the battlefield)? tapped unless you control a planeswalker\.", line):
            extra["tapped_condition"] = "unless_pw"
            continue
        if re.fullmatch(r"~ enters(?: the battlefield)? tapped unless a player has (\d+) or less life\.", line):
            extra["tapped_condition"] = "unless_player_life<=" + re.search(r"(\d+)", line)[1]
            continue
        m = re.fullmatch(r"As ~ enters(?: the battlefield)?, you may behold an? ([A-Z]\w+)\. If you don't, ~ enters "
                         r"(?:the battlefield )?tapped\.", line)
        if m:
            extra["tapped_condition"] = f"behold:{m[1]}"
            continue
        if line == "~ must be blocked if able.":
            extra["must_be_blocked"] = True
            continue
        if line == "Creatures with power less than ~'s power can't block it.":
            extra["blocker_power_rel"] = True
            continue
        if re.fullmatch(r"~ can't block\.", line):
            extra["cant_block"] = True
            continue
        m = re.fullmatch(r"Equipped creature (?:(?:gets|has) \+(\d+)/\+(\d+))?(?: and )?(?:has (.+?))?\.", line)
        if m and (m[1] or m[3]):
            kws, ward, ok = set(), 0, True
            for k in re.split(r", (?:and )?| and ", m[3] or ""):
                k = k.strip().lower()
                if not k:
                    continue
                if re.fullmatch(r"ward \{(\d+)\}", k):
                    ward = int(re.search(r"\d+", k)[0])
                elif k in KEYWORDS:
                    kws.add(k)
                elif k == "hexproof from monocolored":
                    kws.add("hexproof")
                    approximations.append("hexproof from monocolored is played as hexproof")
                else:
                    ok = False
            if ok:
                extra.update(equip_bonus=(int(m[1] or 0), int(m[2] or 0)), equip_keywords=frozenset(kws),
                             equip_ward=ward)
                continue
        # Match whole abilities so target/payment restrictions never disappear. In particular,
        # parse_mana_cost alone would silently drop energy/snow or mishandle X/hybrid costs.
        mana = r"(?:\{(?:\d+|[WUBRGC])\})+"
        # Explicit supported target grammar: commander, worthy and other restrictions stay visible.
        equip_type = r"(?:Citizen|Detective|Elf|Halfling|Hero|Human|Knight|Pirate|Shaman|Soldier|Warlock|Wizard)"
        equip_target = rf"legendary creature|creature token|{equip_type}(?:(?:, |, or | or ){equip_type})*"
        m = re.fullmatch(rf"Equip (?:(?P<target>{equip_target}) )?(?P<mana>{mana})"
                         rf"(?P<reduction>\. This ability costs [^.]+ less to activate[^.]*\.)?\.?", line)
        mixed = re.fullmatch(rf"Equip\s*—\s*(?:(?P<before>{mana}), )?Sacrifice a creature"
                             rf"(?:, (?P<after>{mana}))?\.?", line)
        if m or mixed:
            if mixed and mixed["before"] and mixed["after"]:
                unsupported.append(line)
                continue
            cost_text = m["mana"] if m else mixed["before"] or mixed["after"]
            target = m["target"] if m else None
            target_filter = {"legendary creature": "legendary", "creature token": "token"}.get(target, "")
            if target and not target_filter:
                target_filter = "subtype:" + "|".join(re.split(r", or |, | or ", target))
            ability = EquipCost(parse_mana_cost(cost_text) if cost_text else {}, bool(mixed), target_filter)
            if "equip_cost" not in extra:
                extra.update(equip_cost=ability.mana, equip_sacrifice=ability.sacrifice)
            extra["equip_costs"] = extra.get("equip_costs", ()) + (ability,)
            if m and m["reduction"]:
                approximations.append(f"cost reduction ignored:{m['reduction']}")
            continue
        m = re.fullmatch(r"Equip abilities you activate that target ~ cost \{(\d+)\} less to activate\.", line)
        if m:
            extra["equip_discount"] = int(m[1])
            continue
        if re.fullmatch(r"If (?:~|this card) is in your opening hand, you may begin the game with it on the "
                        r"battlefield\.", line):
            extra["leyline"] = True
            continue
        m = re.fullmatch(r"~ has ([\w ]+?) as long as (you control another ([A-Z]\w+)|an opponent has (\d+) or less "
                         r"life)\.", line)
        if m and m[1].lower() in KEYWORDS:
            cond = f"another:{m[3]}" if m[3] else f"opp_life<={m[4]}"
            extra["cond_keywords"] = extra.get("cond_keywords", ()) + ((m[1].lower(), cond),)
            continue
        if line == "Activated abilities of artifacts, creatures, and planeswalkers can't be activated.":
            extra["stops_activations"] = True
            continue
        if re.fullmatch(r"\{1\}, \{T\}: Add one mana of any color\.", line):
            produces |= set(COLORS)
            extra["mana_filter"] = "tap"
            continue
        m = re.fullmatch(r"\{1\}: Add (one mana of any color|\{[WUBRG]\}, \{[WUBRG]\}, or \{[WUBRG]\})\. (?:~ becomes that "
                         r"color until end of turn\. )?Activate only once each turn\.", line)
        if m:
            produces |= set(COLORS) if "any color" in m[1] else set(re.findall(r"[WUBRG]", m[1]))
            extra["mana_filter"] = "once"
            continue
        m = re.fullmatch(r"\{T\}, Tap an untapped (creature|permanent) you control: Add one mana of any color\.", line)
        if m:
            produces |= set(COLORS)
            extra["mana_tap_other"] = m[1]
            continue
        if line == "{T}, Sacrifice ~: Add one mana of any color.":
            produces |= set(COLORS)
            extra["mana_sac"] = True
            continue
        m = re.fullmatch(r"\{T\}: Add one mana of any color\. Activate only if you control an? (\w+)\.", line)
        if m:
            produces |= set(COLORS)
            extra["mana_cond"] = m[1]
            continue
        m = re.fullmatch(r"\{T\}: Add (\{[WUBRG]\}(?: or \{[WUBRG]\})?)\. (Activate only if [^.]+\.)", line)
        if m:
            produces |= set(re.findall(r"[WUBRG]", m[1]))
            approximations.append(f"condition ignored: {m[2]}")
            continue
        if re.fullmatch(r"\{T\}, Pay 1 life: Add one mana of any color\.", line):
            produces |= set(COLORS)
            approximations.append("the 1 life for coloured mana isn't paid")
            continue
        if re.fullmatch(r"~ enters tapped unless it's your first, second, or third turn of the game\.", line):
            extra["tapped_condition"] = "after_turn3"
            continue
        if re.fullmatch(r"~ enters tapped if it's not your turn\.", line):
            extra["tapped_condition"] = "not_your_turn"
            continue
        m = re.fullmatch(r"\{T\}: Add ([^.]+)\.(?: ~ deals 1 damage to you\.)?", line)
        if m:
            cols, amount = _parse_mana_ability(m[1])
            produces |= cols
            extra["mana_amount"] = max(amount, extra.get("mana_amount", 1))
            continue
        if re.fullmatch(r"~ enters(?: the battlefield)? tapped\.", line):
            enters_tapped = True
            continue
        if re.fullmatch(r"~ enters(?: the battlefield)? tapped unless you control two or more other lands\.", line):
            extra["tapped_condition"] = "unless_2_lands"
            continue
        if re.fullmatch(r"~ enters(?: the battlefield)? tapped unless you control two or fewer other lands\.", line):
            extra["tapped_condition"] = "unless_le_2_lands"
            continue
        m = re.fullmatch(r"~ enters(?: the battlefield)? with (a|one|two|three|four|five) \+1/\+1 counters? on it\.",
                         line)
        if m:
            extra["etb_counters"] = _num(m[1])
            continue
        m = re.fullmatch(r"~ enters with (a|one|two|three|four|five) (\w+) counters? on it\.", line)
        if m:
            extra["etb_named_counters"] = (m[2].lower(), _num(m[1]))
            continue
        m = re.fullmatch(r"Craft with artifact (\{[^ (]+\})(?: \(.*\))?", line)
        if m:
            activated.append(Activated("ability", parse_mana_cost(m[1]), effects=[Effect("craft")],
                                       extra_costs={"exile_self": True, "craft": "artifact"}, sorcery=True,
                                       text=line))
            continue
        if re.fullmatch(r"Station(?: \(.*\))?", line):
            extra["station"] = True
            continue
        m = re.fullmatch(r"STATION (\d+)\+", line)
        if m:
            station_min = int(m[1])
            continue
        m = re.fullmatch(r"\{T\}, Sacrifice ~: (Search your library for a basic land card, put it onto the battlefield "
                         r"tapped, then shuffle\.(?: Then if you control four or more lands, untap that land\.)?)", line)
        if m and "Land" in types:
            effs, _ = _parse_effects(m[1])
            approximations.append("cracked as soon as it enters")
            effs[0].data["sacrifice"] = True
            triggers.append(Trigger("etb", effs))
            etb += effs
            continue
        if re.fullmatch(r"If a source you control would deal noncombat damage to a creature an opponent controls, put "
                        r"that many -1/-1 counters on that creature instead\.", line):
            extra["wither_noncombat"] = True
            continue
        if re.fullmatch(r"If a creature dealt damage this turn by a source you controlled would die, exile it "
                        r"instead\.", line):
            extra["exile_damaged"] = True
            continue
        if line in ("Daybound", "Nightbound"):
            approximations.append("day/night isn't tracked: it stays on its front face")
            continue
        if re.fullmatch(r"Casualty \d+", line):
            approximations.append(f"never paid: {line}")
            continue
        m = re.fullmatch(r"Impending (\d+)—(\{[^ ]+\})", line)
        if m:
            alt_costs.append(AltCost("impending", parse_mana_cost(m[2]), counters=int(m[1])))
            continue
        m = re.fullmatch(r"Spells your opponents cast that target ~ cost an additional (\d+) life to cast\.", line)
        if m:
            approximations.append(f"as ward (pay {m[1]} life): {line}")
            extra["ward_life"] = int(m[1])
            continue
        m = re.fullmatch(r"(Warp|Evoke|Offspring|Plot) (\{[^ ]+\})", line)
        if m:
            alt_costs.append(AltCost(m[1].lower(), parse_mana_cost(m[2]), hybrid=tuple(
                a + b for a, b in re.findall(r"\{([WUBRG])/([WUBRG])\}", m[2]))))
            continue
        m = re.fullmatch(r"(?:Renew — )?(\{[^:]+\}), Exile (?:~|this card) from your graveyard: (.+?)"
                         r"(?: Activate only as a sorcery\.)?", line)
        if m:
            effs, bad = _parse_effects(m[2])
            if effs and not bad:
                alt_costs.append(AltCost("gy_ability", parse_mana_cost(m[1]), zone="graveyard", effects=effs))
                continue
        m = re.fullmatch(r"Harmonize (\{[^ ]+\})", line)
        if m:
            alt_costs.append(AltCost("flashback", parse_mana_cost(m[1]), zone="graveyard"))
            approximations.append("harmonize: tapping a creature to reduce the cost isn't used")
            continue
        if line == "Spree":
            extra["is_spree"] = True
            continue
        m = re.fullmatch(r"\+ (\{[^ ]+\}) — (.+)", line)
        if m and extra.get("is_spree"):
            effs, bad = _parse_effects(m[2])
            if effs and not bad:
                extra.setdefault("spree", []).append((parse_mana_cost(m[1]), effs))
            else:
                unsupported.append(line)
            continue
        m = re.fullmatch(r"~ enters(?: the battlefield)? with X \+1/\+1 counters on it\.", line)
        if m:
            extra["etb_counters"] = -1
            continue
        m = re.fullmatch(r"Kicker (\{[^ ]+\})", line)
        if m:
            extra["kicker"] = parse_mana_cost(m[1])
            continue
        m = re.fullmatch(r"Teamwork (\d+)(?: \(.*\))?", line)
        if m:
            extra["teamwork"] = int(m[1])
            continue
        m = re.fullmatch(r"As an additional cost to cast ~, you may collect evidence (\d+)\.", line)
        if m:
            extra["collect_evidence"] = int(m[1])
            continue
        if re.fullmatch(r"As an additional cost to cast ~, you may [^.]+\.", line):
            approximations.append(f"never paid: {line}")
            continue
        if re.fullmatch(r"If ~'s additional cost was paid, [^.]+\.", line) and approximations:
            continue
        m = re.fullmatch(r"As an additional cost to cast ~, (?:discard a card or )?pay (\d+) life\.", line)
        if m:
            extra["extra_life_cost"] = int(m[1])
            continue
        if re.fullmatch(r"If you control two or more other lands, ~ enters(?: the battlefield)? tapped\.", line):
            extra["tapped_condition"] = "if_2_lands"
            continue
        if re.fullmatch(r"As ~ enters(?: the battlefield)?, you may pay 2 life\. If you don't, it enters "
                        r"(?:the battlefield )?tapped\.", line):
            extra["tapped_condition"] = "shock"
            continue
        if re.fullmatch(r"~ can't be countered\.", line):
            extra["uncounterable"] = True
            continue
        if re.fullmatch(r"Instant and sorcery spells you control can't be countered\.", line):
            extra["protects_spells"] = True
            continue
        m = re.fullmatch(r"~ costs \{1\} less to cast for each ([\w, /-]+?) cards? in your graveyard\.", line)
        if m and m[1] != "instant and sorcery":
            extra["cost_reduction"] = "gy:" + m[1].replace("and/or", "or")
            continue
        if re.fullmatch(r"~ costs \{1\} less to cast for each instant and sorcery card in your graveyard\.", line):
            extra["cost_reduction"] = "instant_sorcery_gy"
            continue
        if re.fullmatch(r"~ costs \{X\} less to cast, where X is the number of cards in your graveyard that are instant "
                        r"cards, sorcery cards, and/or have an Adventure\.", line):
            extra["cost_reduction"] = "instant_sorcery_adventure_gy"
            continue
        if re.fullmatch(r"~ costs \{X\} less to cast, where X is the greatest mana value among Elementals you control\.",
                        line):
            extra["cost_reduction"] = "greatest_elemental"
            continue
        if re.fullmatch(r"~ costs \{X\} less to cast, where X is the total power of creatures you control\.", line):
            extra["cost_reduction"] = "power"
            continue
        m = re.fullmatch(r"Affinity for (\w+?)s", line)
        if m:
            extra["cost_reduction"] = "affinity:" + m[1]
            continue
        if re.fullmatch(r"You may play an additional land on each of your turns\.", line):
            extra["extra_lands"] = 1
            continue
        if re.fullmatch(r"You may play lands from your graveyard\.", line):
            extra["lands_from_gy"] = True
            continue
        if _counting.parse_line(line, extra):
            continue
        m = re.fullmatch(r"As an additional cost to cast ~, (?:pay \{(\d+)\} or )?sacrifice (an? (?:artifact|creature)"
                         r"(?: or (?:artifact|creature))?)\.", line)
        if m:
            extra["extra_sacrifice"] = m[2]
            extra["extra_sac_or_pay"] = int(m[1] or 0)
            continue
        m = re.fullmatch(r"~ can't be blocked by creatures with power (\d+) or less\.", line)
        if m:
            extra["min_blocker_power"] = int(m[1]) + 1
            continue
        m = re.fullmatch(r"As long as ~ has (three) or more \+1/\+1 counters on it, it has (\w+)\.", line)
        if m:
            extra["keyword_at_counters"] = (_num(m[1]), m[2].lower())
            continue
        m = re.fullmatch(r"Creatures you control have (haste|trample|vigilance|lifelink|menace|flying|reach)\.", line)
        if m:
            extra["team_keywords"] = extra.get("team_keywords", frozenset()) | {m[1]}
            continue
        m = re.fullmatch(r"(Red|White|Blue|Black|Green|Instant and sorcery|Creature|Artifact|Noncreature|[A-Z][a-z]+) "
                         r"spells you cast cost \{(\d+)\} less to cast\.", line)
        if m:
            extra["cost_discount"] = extra.get("cost_discount", ()) + ((m[1].lower(), int(m[2])),)
            continue
        m = re.fullmatch(r"(Creatures|Lands|Creature tokens|Foods|Other permanents|Each land and Ally) you control "
                         r"(?:have|has) \"\{T\}: Add (one mana of any color|\{[WUBRGC]\})\.\"", line)
        if m:
            scope = {"creatures": "creature", "lands": "land", "creature tokens": "creature_token", "foods": "food",
                     "other permanents": "other", "each land and ally": "land_or_ally"}[m[1].lower()]
            cols = frozenset(COLORS) if "any color" in m[2] else frozenset(re.findall(r"[WUBRGC]", m[2]))
            extra["grant_mana"] = extra.get("grant_mana", ()) + ((scope, cols),)
            continue
        if line in ("When this land enters, choose a land card name.", "When ~ enters, choose a land card name.") or \
                line.startswith("Activated abilities of sources with the chosen name can't be activated") or \
                line == 'Lands with the chosen name have "{T}: Add {C}."':
            extra["chosen_land_lock"] = True
            continue
        if line == "∞ — At the beginning of your end step, exile up to one other target nonland permanent you control, "\
                   "then return that card to the battlefield under its owner's control.":
            triggers.append(Trigger("end_step", [Effect("blink_own", cond="harnessed")]))
            continue
        m = re.fullmatch(r"Creatures you control with (flying|trample|menace|first strike|lifelink|deathtouch) get "
                         r"\+(\d+)/\+(\d+)\.", line)
        if m:
            extra["anthem_kw"] = extra.get("anthem_kw", ()) + ((m[1], int(m[2]), int(m[3])),)
            continue
        m = re.fullmatch(r"Creature tokens you control get \+(\d+)/\+(\d+)\.", line)
        if m:
            extra["anthem_sub"] = extra.get("anthem_sub", ()) + (("Token", int(m[1]), int(m[2]), False),)
            continue
        m = re.fullmatch(r"(Other )?(Merfolk|[A-Z][a-z]+?)s? you control get \+(\d+)/\+(\d+)\.", line)
        if m and m[2] != "Creature":
            extra["anthem_sub"] = extra.get("anthem_sub", ()) + ((m[2], int(m[3]), int(m[4]), bool(m[1])),)
            continue
        m = re.fullmatch(r"(Other )?([A-Z][a-z]+?)s you control have (menace|trample|flying|vigilance|haste|lifelink|"
                         r"first strike|double strike|deathtouch|reach|indestructible)\.", line)
        if m and m[2] != "Creature":
            extra["keyword_sub"] = extra.get("keyword_sub", ()) + ((m[2], m[3], bool(m[1])),)
            continue
        m = re.fullmatch(r"~ costs \{(\d+)\} less to cast if you control an? ([A-Z]\w+)\.", line)
        if m:
            extra["discount_if"] = extra.get("discount_if", ()) + ((m[2], int(m[1])),)
            continue
        m = re.fullmatch(r"(Other )?(?!Enchanted)([A-Z][\w-]+) creatures you control get \+(\d+)/\+(\d+)\.", line)
        if m:
            extra["anthem_sub"] = extra.get("anthem_sub", ()) + ((m[2], int(m[3]), int(m[4]), bool(m[1])),)
            continue
        m = re.fullmatch(r"Creatures you control with \+1/\+1 counters on them have (trample|flying|vigilance|haste|lifelink|"
                         r"first strike|deathtouch|menace|reach|indestructible)\.", line)
        if m:
            extra["counter_team_keywords"] = extra.get("counter_team_keywords", frozenset()) | {m[1]}
            continue
        m = re.fullmatch(r"The second spell you cast each turn costs \{(\d+)\} less to cast\.", line)
        if m:
            extra["second_spell_discount"] = int(m[1])
            continue
        m = re.fullmatch(r"As long as you control seven or more lands, ~ gets \+(\d+)/\+(\d+)\.", line)
        if m:
            extra["pt_if"] = extra.get("pt_if", ()) + (("lands>=7", int(m[1]), int(m[2])),)
            continue
        m = re.fullmatch(r"~ costs \{(\d+)\} less to cast if it targets a tapped creature\.", line)
        if m:
            extra["tapped_discount"] = int(m[1])
            continue
        m = re.fullmatch(r"As an additional cost to cast ~, behold an? (\w+) or pay \{(\d+)\}\.", line)
        if m:
            extra["behold_or_pay"] = (m[1], int(m[2]))
            continue
        m = re.fullmatch(r"As an additional cost to cast ~, discard a card(?: or pay \{(\d+)\})?\.", line)
        if m:
            extra["extra_discard"] = 1
            extra["discard_or_pay"] = int(m[1] or 0)
            continue
        if line == "Untap ~ during each other player's untap step.":
            extra["untap_each_untap"] = True
            continue
        m = re.fullmatch(r"Enchanted creatures you control get \+(\d+)/\+(\d+)\.", line)
        if m:
            extra["anthem_enchanted"] = (int(m[1]), int(m[2]))
            continue
        if line in ("~ enters tapped. As it enters, choose a color.", "As ~ enters, choose a color."):
            extra["choose_type"] = "basic_land"
            produces |= set(COLORS)
            if line.startswith("~ enters"):
                enters_tapped = True
            continue
        m = re.fullmatch(r"Activated abilities of artifact tokens you control cost \{(\d+)\} less to activate\.", line)
        if m:
            extra["token_ability_discount"] = int(m[1])
            continue
        if line == "Your opponents can't cast spells during your turn.":
            extra["opp_no_cast"] = True
            continue
        m = re.fullmatch(r"During your turn, ~ has (\w+(?: \w+)?)\.", line)
        if m and m[1].lower() in KEYWORDS:
            extra["cond_keywords"] = extra.get("cond_keywords", ()) + ((m[1].lower(), "your_turn"),)
            continue
        m = re.fullmatch(r"(?:Descend \d+ — |Threshold — )?~ (?:gets \+(\d+)/\+(\d+) and has ([a-z ]+?)|has ([a-z ]+?)|"
                         r"(can't be blocked)) as long as there are (\w+) or more (permanent )?cards in your graveyard\.",
                         line)
        if m and m[6].lower() in NUMBERS:
            kw = "unblockable" if m[5] else (m[3] or m[4])
            if kw in KEYWORDS or kw == "unblockable":
                cond = ("gy_perm>=" if m[7] else "gy>=") + str(_num(m[6]))
                if m[1]:
                    extra["pt_if"] = extra.get("pt_if", ()) + ((cond, int(m[1]), int(m[2])),)
                extra["cond_keywords"] = extra.get("cond_keywords", ()) + ((kw, cond),)
                continue
        m = re.fullmatch(r"(?:Descend \d+ — |Threshold — )?~ gets \+(\d+)/\+(\d+) as long as there are (four|seven) or more (permanent )?cards in your "
                         r"graveyard\.", line)
        if m:
            cond = ("gy_perm>=" if m[4] else "gy>=") + str(_num(m[3]))
            extra["pt_if"] = extra.get("pt_if", ()) + ((cond, int(m[1]), int(m[2])),)
            continue
        m = re.fullmatch(r"(?:Raid — )?~ enters with a \+1/\+1 counter on it if (an opponent lost life|a creature died|you attacked) "
                         r"this turn\.", line)
        if m:
            extra["etb_counters_if"] = ({"an opponent lost life": "opp_lost_life", "a creature died": "creature_died",
                                         "you attacked": "attacked"}[m[1]], 1)
            continue
        m = re.fullmatch(r"Creatures you control get \+(\d+)/\+(\d+)\.", line)
        if m:
            extra["anthem"] = (int(m[1]), int(m[2]))
            continue
        m = re.fullmatch(r"Firebending (\d+|X)(?:, where X is (~'s power|the number of creatures you control))?\.?", line)
        if m:
            what = "" if m[1] != "X" else ("power" if "power" in m[2] else "creatures")
            triggers.append(Trigger("attacks", [Effect("firebend", 0 if what else int(m[1]), data={"x": what})]))
            continue
        if line == "Increment":
            triggers.append(Trigger("cast_spell", [Effect("increment")]))
            continue
        m = re.fullmatch(r"Mobilize (\d+|X)(?:, where X is the number of creature cards in your graveyard)?", line)
        if m:
            sac = Trigger("end_step", [Effect("copy_sac", target="self")])
            eff = Effect("token", 1 if m[1] == "X" else int(m[1]), data={
                "name": "Warrior", "power": 1, "toughness": 1, "keywords": frozenset(), "attacking": True,
                "triggers": [sac], "artifact": False, "pt_per": ""})
            if m[1] == "X":
                eff.data["per"] = {"what": "creature", "zone": "graveyard"}
            triggers.append(Trigger("attacks", [eff]))
            continue
        m = re.fullmatch(r"Disguise (\{[^ ]+\})", line)
        if m:
            alt_costs.append(AltCost("disguise", parse_mana_cost(m[1])))
            continue
        if line == "Convoke":
            extra["convoke"] = True
            continue
        if line == "~ enters prepared.":
            extra["prepared"] = True
            continue
        if line == "Changeling":
            extra["changeling"] = True
            continue
        m = re.fullmatch(r"(Cycling|Basic landcycling|Landcycling|(?:Plains|Island|Swamp|Mountain|Forest)cycling) "
                         r"(\{[^ ]+\})", line)
        if m:
            kind = m[1].lower()
            extra["cycling"] = {"cost": parse_mana_cost(m[2]), "land": "" if kind == "cycling" else
                                "basic" if kind == "basic landcycling" else "any" if kind == "landcycling" else
                                m[1][:-7]}
            continue
        m = re.fullmatch(r"Saddle (\d+)", line)
        if m:
            extra["saddle"] = int(m[1])
            continue
        m = re.fullmatch(r"Crew (\d+)", line)
        if m:
            extra["crew"] = int(m[1])
            continue
        m = re.fullmatch(r"(Flashback|Foretell|Spectacle) (\{[^ ]+\})", line)
        if m:
            kind = m[1].lower()
            alt_costs.append(AltCost(kind, parse_mana_cost(m[2]),
                                     zone={"flashback": "graveyard", "foretell": "foretold"}.get(kind, "hand")))
            continue
        m = re.fullmatch(r"(Mayhem|Sneak) (\{[^ ]+\})", line)
        if m:
            alt_costs.append(AltCost(m[1].lower(), parse_mana_cost(m[2]), zone="graveyard" if m[1] == "Mayhem" else "hand"))
            continue
        m = re.fullmatch(r"Blitz—(\{[^,]+\}), Pay (\d+) life\.", line)
        if m:
            alt_costs.append(AltCost("blitz", parse_mana_cost(m[1]), zone="hand", life=int(m[2])))
            continue
        if re.fullmatch(r"You may cast ~ from your graveyard using its blitz ability\.", line):
            for a in alt_costs:
                if a.kind == "blitz":
                    a.zone = "hand+graveyard"
            continue
        m = re.fullmatch(r"You may pay (\{[^ ]+\}) rather than pay ~'s mana cost\.", line)
        if m:
            alt_costs.append(AltCost("alt", parse_mana_cost(m[1])))
            continue
        m = re.fullmatch(r"If the \{[^ ]+\} cost was paid, an opponent draws a card\.", line)
        if m and alt_costs and alt_costs[-1].kind == "alt":
            alt_costs[-1].extra.append(Effect("draw", 1, target="each_opponent"))
            continue
        m = re.fullmatch(r"Channel — (\{[^,]+\}), Discard ~: (.+?)(?: This ability costs \{1\} less to activate "
                         r"for each legendary creature you control\.)?", line)
        if m:
            effs, bad = _parse_effects(m[2])
            if effs and not bad:
                alt_costs.append(AltCost("channel", parse_mana_cost(m[1]), effects=effs))
                continue
        if re.fullmatch(r"As long as ~ entered this turn, you may activate (?:her|his|its) loyalty abilities any "
                        r"time you could cast an instant\.", line):
            extra["pw_instant_on_entry"] = True
            continue
        m = re.fullmatch(r"\[([+−-]?\d+)\]: ?(.+)", line) or \
            ("Planeswalker" in types and re.fullmatch(r"([+−-]?\d+): ?(.+)", line))
        if m:
            effs, bad = _parse_effects(m[2])
            if effs:
                loyalty_abilities.append((int(m[1].replace("−", "-")), effs))
            unsupported += [f"[{m[1]}]: {b}" for b in bad]
            continue
        m = re.fullmatch(r"((?:I|II|III|IV|V)(?:, (?:I|II|III|IV|V))*) — (.+)", line)
        if m:
            effs, bad = _parse_effects(m[2])
            for numeral in m[1].split(", "):
                idx = ["I", "II", "III", "IV", "V"].index(numeral)
                while len(chapters) <= idx:
                    chapters.append([])
                chapters[idx] += effs
            unsupported += [f"{m[1]} — {b}" for b in bad]
            continue
        m = re.fullmatch(r"(\{[^:]+\}): Until end of turn, ~ becomes an? (\d+)/(\d+) [\w ]*? creature"
                         r"(?: with (ward \{\d+\}|[\w ,]+|\"[^\"]+\"))?\.? It's still a land\.", line)
        if m:
            act = Activated("animate", parse_mana_cost(m[1]), int(m[2]), int(m[3]))
            ability = m[4] or ""
            if ability.startswith("ward"):
                act.ward = int(re.search(r"\d+", ability)[0])
            elif ability.startswith('"'):
                inner = ability.strip('"')
                trig = _parse_trigger(inner)
                if trig:
                    act.triggers = trig[0]
            elif ability:
                act.keywords = frozenset(k.strip().lower() for k in ability.split(",") if k.strip().lower() in KEYWORDS)
            activated.append(act)
            continue
        m = re.fullmatch(r"(\{[^:]+\}): ~ becomes an? (\d+)/(\d+) creature with (\w+) and all creature types\. "
                         r"It's still a land\.", line)
        if m:   # permanently (Soulstone Sanctuary)
            activated.append(Activated("animate", parse_mana_cost(m[1]), int(m[2]), int(m[3]),
                                       keywords=frozenset({m[4].lower()}) & KEYWORDS, text="permanent"))
            continue
        m = re.fullmatch(r"(\{[^:]+\}): ~ becomes an? (\d+)/(\d+) [\w ]*? creature(?: with ([\w ,]+))? until end of "
                         r"turn\. It's still a land\.", line)
        if m:
            kws = frozenset(k.strip().lower() for k in re.split(r",| and ", m[4] or "") if k.strip().lower() in KEYWORDS)
            activated.append(Activated("animate", parse_mana_cost(m[1]), int(m[2]), int(m[3]), keywords=kws))
            continue
        m = re.fullmatch(r"(\{[^:]+\}): Put two \+1/\+1 counters on ~\. Then you may have it become a 0/0 \w+ "
                         r"creature until end of turn\. It's still a land\.", line)
        if m:
            activated.append(Activated("barrens", parse_mana_cost(m[1])))
            continue
        if re.fullmatch(r"\{T\}, Sacrifice ~: Target creature gets -X/-X until end of turn, where X is twice the "
                        r"number of Blood tokens you control\. Activate only as a sorcery\.", line):
            activated.append(Activated("sac_debuff", {"generic": 0}))
            continue
        extra["_subtypes"] = type_line
        if _auras.parse_line(line, extra, types):
            continue
        clone = _copies.parse_line(line)
        if clone is not None:
            extra.update(clone)
            continue
        mp = re.fullmatch(r"(Power-up|Exhaust) — (.+)", line)
        act = _parse_ability(mp[2] if mp else line, approximations)
        if act is not None and mp:
            act.once_game, act.power_up, act.text = True, mp[1] == "Power-up", line
        if act is not None:
            act.min_charge = station_min
            activated.append(act)
            if isinstance(act.modes, modal.Modes):
                mode_sink = act.modes
            continue
        opt_cond = ""
        mo = re.fullmatch(r"(When ~ enters), if (it was bargained|the gift was promised), (.+)", line)
        if mo and (extra.get("bargain") or extra.get("gift")):
            line = f"{mo[1]}, {mo[3]}"
            opt_cond = "bargained" if "bargained" in mo[2] else "gifted"
        trig = _parse_trigger(line)
        if trig is not None:
            new, bad, choose_modes = trig
            if opt_cond:
                for t in new:
                    for e in t.effects:
                        e.cond = e.cond or opt_cond
            triggers += new
            if choose_modes is not None:
                mode_sink = choose_modes
            for t in new:
                if t.event == "etb":
                    etb += t.effects
            unsupported += bad
            continue
        if not types.isdisjoint({"Instant", "Sorcery"}):
            head = modal.parse_header(line)
            if head is not None and not modes:
                modes = modal.Modes(spec=head[0])
                extra["modes_choose"] = min(head[0].most, 9)
                approximations += head[1]
                mode_sink = modes
                continue
            effs, bad = _parse_effects(line, opts=bool(extra.get("bargain") or extra.get("gift")))
            spell += effs
            unsupported += bad
            continue
        unsupported.append(line)
    if "X is the amount of mana spent to cast" in oracle:
        for e in spell:
            if e.kind == "dig":
                e.data["x_mana"] = True
    if "kicker" in extra:
        kicked_effects = [dataclasses.replace(e) for e in spell]
        for k in kicked:
            m = re.fullmatch(r"it deals (\d+) damage instead\.", k)
            dmg = [e for e in kicked_effects if e.kind == "damage"]
            if m and dmg:
                dmg[0].amount = int(m[1])
                continue
            m = re.fullmatch(r"put (\w+) of those cards into your hand instead\.", k)
            dig = [e for e in kicked_effects if e.kind == "dig"]
            if m and dig:
                kicked_effects[kicked_effects.index(dig[0])] = dataclasses.replace(dig[0], amount2=_num(m[1]))
                continue
            effs, bad = _parse_effects(k)
            kicked_effects += effs
            unsupported += [f"if kicked: {b}" for b in bad]
        alt_costs.append(AltCost("kicker", add_mana(cost, extra.pop("kicker")), effects=kicked_effects))
    elif kicked:
        unsupported += [f"if kicked: {k}" for k in kicked]
    if gate is not None:
        _apply_speed_gate(gate, triggers, activated)
    extra.pop("is_spree", None)
    extra.pop("_subtypes", None)
    _auras.finish(extra)
    extra["gy_triggers"] = [t for t in triggers if any(e.kind == "return_self_gy" for e in t.effects)]
    triggers = [t for t in triggers if t not in extra["gy_triggers"]]
    extra["spent_colors"] = frozenset(t.effects[0].cond[6:] for t in triggers
                                      if t.effects and t.effects[0].cond.startswith("spent:"))
    if "prowess" in keywords:
        triggers.append(Trigger("cast_noncreature", [Effect("pump", 1, 1, target="self")]))
    # Triggers with "choose up to one" get their bullet modes; drop ones that ended up empty.
    triggers = [t for t in triggers if t.effects or t.modes]

    return CardDef(
        name=name, mana_cost=cost, cmc=int(data.get("cmc", 0) or 0), types=types,
        subtypes=frozenset(type_line.split("—")[1].split()) if "—" in type_line else frozenset(),
        power=stat(data.get("power")), toughness=stat(data.get("toughness")),
        keywords=frozenset(keywords), produces=frozenset(produces), enters_tapped=enters_tapped,
        spell_effects=spell, etb_effects=etb, unsupported=unsupported, approximations=approximations, oracle=oracle,
        triggers=triggers, modes=modes, chapters=chapters, loyalty_abilities=loyalty_abilities,
        alt_costs=alt_costs, activated=activated, **extra,
    )


def _mana_restriction(text: str):
    """What "Spend this mana only ..." allows, or None if the wording isn't one we model."""
    text = text.lower()
    if text == "to cast a creature spell of the chosen type, and that spell can't be countered":
        return "chosen_type"
    if re.fullmatch(r"to cast (?:a creature spell|creature spells)", text):
        return "creature"
    if re.fullmatch(r"to cast (?:an artifact spell|artifact spells)", text):
        return "artifact"
    if re.fullmatch(r"to cast (?:an instant or sorcery spell|instant and sorcery spells)", text):
        return "instant_sorcery"
    m = re.fullmatch(r"to cast an? (\w+) spell(?: or an? (\w+) spell)?", text)
    if m:
        return "subtype:" + "|".join(t.capitalize() for t in m.groups() if t)
    return None


_SACRIFICE_KINDS = {"token", "artifact", "creature", "creature or artifact", "artifact or creature", "treasure",
                    "food", "land", "enchantment", "other creature", "other artifact"}


def _parse_ability_cost(text: str):
    """(mana cost, other costs) for an activated ability's cost, or None if a part isn't modelled."""
    mana, extra = {"generic": 0}, {}
    for part in text.split(", "):
        m = None
        if part == "{T}":
            extra["tap"] = True
        elif re.fullmatch(r"(\{[0-9WUBRGC/]+\})+", part):
            mana = add_mana(mana, parse_mana_cost(part))
        elif part == "Sacrifice ~":
            extra["sac_self"] = True
        elif part == "Exile ~":
            extra["exile_self"] = True
        elif part == "Discard a card":
            extra["discard"] = 1
        elif (m := re.fullmatch(r"Pay (\d+) life", part)):
            extra["life"] = int(m[1])
        elif (m := re.fullmatch(r"Remove an? ([\w/+-]+) counter from ~", part)):
            extra["remove_counter"] = m[1]
        elif (m := re.fullmatch(r"Sacrifice (?:a|an|another) (.+)", part)) and \
                m[1].lower() in _SACRIFICE_KINDS:
            what = m[1].lower()
            extra["sacrifice"] = ("other " + what if part.startswith("Sacrifice another") else what)
        else:
            return None
    return mana, extra


def _parse_ability(line: str, approximations: list):
    """A general activated ability ("{2}, {T}: Draw a card."), or None."""
    m = re.fullmatch(r"([^:\"•]+?): (.+)", line)
    if not m or not (m[1].startswith("{") or m[1].split()[0] in ("Sacrifice", "Discard", "Pay", "Remove", "Exile")):
        return None
    cost = _parse_ability_cost(m[1])
    if cost is None:
        return None
    body, sorcery, once, approx = m[2], False, False, []
    while True:
        r = re.fullmatch(r"(.+?\.) (Activate only as a sorcery|Activate only once each turn|This ability costs [^.]+ "
                         r"less to activate[^.]*)\.", body)
        if not r:
            break
        body = r[1]
        sorcery |= r[2] == "Activate only as a sorcery"
        once |= r[2] == "Activate only once each turn"
        if r[2].startswith("This ability costs"):
            approx.append(f"cost reduction ignored: {r[2]}.")
    head = modal.parse_header(body)
    if head is not None and not head[1]:
        approximations += approx
        return Activated("ability", cost[0], extra_costs=cost[1], sorcery=sorcery, once=once, text=line,
                         modes=modal.Modes(spec=head[0]))
    effects, bad = _parse_effects(body)
    if bad or not effects:
        return None
    approximations += approx
    return Activated("ability", cost[0], effects=effects, extra_costs=cost[1], sorcery=sorcery, once=once, text=line)


def _parse_trigger(line: str):
    """(triggers, unmatched, modes list to fill or None) for a triggered ability line, else None."""
    once = line.endswith(" This ability triggers only once each turn.")
    if once:
        line = line[:-len(" This ability triggers only once each turn.")]
    once_game = line.endswith(" This ability triggers only once.")
    if once_game:
        line = line[:-len(" This ability triggers only once.")]
    out = _parse_trigger_line(line)
    if out is not None and once:
        for t in out[0]:
            t.once = True
    if out is not None and once_game:
        for t in out[0]:
            t.once_game = True
    return out


def _parse_trigger_line(line: str):
    for pat, events in _TRIGGERS:
        m = re.fullmatch(pat, line)
        if not m:
            continue
        flt = ""
        rest = m[m.lastindex]
        if events == ("any_cast",):
            flt = f"cmc<={m[1]}"
        if "while saddled" in pat or events[-1] == "becomes_tapped":
            rest = re.sub(r"^it (gets|gains|deals)\b", r"~ \1", re.sub(r"\b(on|untap|to) it\b", r"\1 ~", rest))
        if events == ("expend",):
            flt = m[1]
        if events == ("gy_leave",):
            flt = f"{m[1] or ''}|{'turn' if m[2] else ''}"
        if events == ("ally_dies",):
            flt = f"{'other' if m[1] == 'another' else 'any'}|{'counter' if m[3] else ''}|{m[2]}"
        if events == ("perm_to_gy",):
            flt = f"{'other' if m[1] == 'another' else 'any'}||{m[2]}"
        if events == ("attacks",) and "while saddled" in pat:
            flt = "saddled"
        if events == ("cast_instant_sorcery",) and "that targets a creature" in pat:
            flt = "targets_creature"
        if events == ("targeted_mine",):
            rest = re.sub(r"^it (gets|gains|deals)\b", r"~ \1", re.sub(r"\b(on|untap|to) it\b", r"\1 ~", rest))
        if events == ("cast_cmc",):
            flt = f"cmc>={m[1]}"
        if events == ("cast_spell",) and m.lastindex == 2:
            flt = f"spell:{m[1]}"
        if events == ("sacrifice",):
            flt = m[1]
        if events == ("you_attack",) and m.lastindex == 2:
            flt = f"with:{m[1].rstrip('s')}"
        if events[0] == "other_creature_enters":
            flt = "greater_power"
        if events == ("permanent_enters",):
            desc = m[3] + (f" or {m[5]}" if m[5] else "") + (m[4] or "")
            flt = f"{'self' if m[1] else 'noself'}|{'other' if m[2] == 'another' else 'any'}|{desc}"
        head = modal.parse_header(rest)
        if head is not None and not head[1]:
            modes = modal.Modes(spec=head[0])
            return [Trigger(e, [], flt, modes) for e in events], [], modes
        spent = re.fullmatch(r"if \{([WUBRG])\}\{\1\} was spent to cast it, (.+)", rest, flags=re.S)
        cond = f"spent:{spent[1]}" if spent else ""
        if spent:
            rest = spent[2]
        if rest.startswith("if you cast it, "):
            cond, rest = "cast", rest[16:]
        c = re.fullmatch(r"if (you gained life|you gained and lost life|you descended|you've gained (\d+) or more life|an opponent "
                         r"lost life) this turn, (.+)", rest, flags=re.S) or \
            re.fullmatch(r"(.+?) if (you gained life|you've gained (\d+) or more life) this turn\.", rest, flags=re.S)
        if c:
            phrase, n, rest = (c[1], c[2], c[3]) if not c[1][0].isupper() and c.re.pattern.startswith("if") \
                else (c[2], c[3], c[1] + ".")
            cond = {"you gained life": "gained_life", "you gained and lost life": "gained_and_lost",
                    "an opponent lost life": "opp_lost_life", "you descended": "descended"}.get(phrase, f"gained_life>={n}")
        if cond:
            rest = rest[0].upper() + rest[1:]
        # "... When you do, if it has four or more quest counters on it, EFFECTS" (Earthbender Ascension)
        reflex = re.fullmatch(r"(.+?) When you do, if it has (\w+) or more (\w+) counters on it, (.+)", rest, flags=re.S)
        later: list = []
        if reflex:
            rest = reflex[1]
            later, bad2 = _parse_effects(reflex[4][0].upper() + reflex[4][1:])
            if bad2:
                return [], bad2, None
            later = [dataclasses.replace(e, cond=f"counters:{reflex[3]}>={_num(reflex[2])}") for e in later]
        opus = re.fullmatch(r"(.+?\.) If five or more mana was spent to cast that spell, (.+)", rest, flags=re.S)
        unless = re.fullmatch(r"(.+?\.) Then (.+?) unless five or more mana was spent to cast that spell\.?", rest, flags=re.S)
        if opus:
            instead = opus[2].rstrip(".").endswith(" instead")
            second = re.sub(r" instead$", "", opus[2].rstrip(".")).replace("~ also ", "~ ")
            first, bad = _parse_effects(opus[1])
            more, bad2 = _parse_effects(second[0].upper() + second[1:] + ".")
            bad += bad2
            effs = [dataclasses.replace(e, cond="mana<5") for e in first] if instead else first
            effs += [dataclasses.replace(e, cond="mana>=5") for e in more]
        elif unless:
            first, bad = _parse_effects(unless[1])
            more, bad2 = _parse_effects(unless[2][0].upper() + unless[2][1:] + ".")
            bad += bad2
            effs = first + [dataclasses.replace(e, cond="mana<5") for e in more]
        else:
            effs, bad = _parse_effects(rest)
            if cond:
                effs = [dataclasses.replace(e, cond=cond) for e in effs]
        effs += later
        if events == ("attacks_alone",):
            for e in effs:
                if e.target == "prev":
                    e.target = "trigger_subject"
        if not effs:
            return [], bad or [line], None
        return [Trigger(e, effs, flt, once=events == ("targeted_mine",)) for e in events], bad, None
    return None


# Artifact tokens with an activated ability, as general abilities (see _parse_ability).
TOKEN_ABILITIES = {
    "map": "{1}, {T}, Sacrifice ~: Target creature you control explores. Activate only as a sorcery.",
    "lander": "{2}, {T}, Sacrifice ~: Search your library for a basic land card, put it onto the battlefield "
              "tapped, then shuffle.",
    "food": "{2}, {T}, Sacrifice ~: You gain 3 life.",
    "mutagen": "{1}, Sacrifice ~: Put a +1/+1 counter on target creature you control. Activate only as a sorcery.",
}


def make_token(name: str, power: int, toughness: int, keywords=frozenset(), triggers=None, kind: str = "",
               artifact: bool = False, pt_per: str = "") -> CardDef:
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
                   keywords=frozenset(keywords), triggers=list(triggers or []), is_token=True, pt_per=pt_per)


# Copy effects live in their own module; its templates join the ones above.
from . import auras as _auras, copies as _copies, removal as _removal, search as _search, xspells as _xspells, counting as _counting  # noqa: E402

from . import delayed as _delayed

_EFFECT_PATTERNS += _copies.EFFECT_PATTERNS + _removal.EFFECT_PATTERNS + _auras.EFFECT_PATTERNS + _search.EFFECT_PATTERNS + _xspells.EFFECT_PATTERNS + _counting.EFFECT_PATTERNS + _delayed.EFFECT_PATTERNS
_SUBS += _copies.SUBS + _counting.SUBS + _delayed.SUBS


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
