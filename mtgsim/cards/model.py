"""Card data model: CardDef, Effect, Trigger, Activated, AltCost, and mana-cost helpers."""
from __future__ import annotations

import re
from dataclasses import dataclass, field



COLORS = ("W", "U", "B", "R", "G")
KEYWORDS = {
    "flying", "reach", "haste", "trample", "first strike", "double strike",
    "deathtouch", "lifelink", "vigilance", "defender", "menace",
    "flash", "hexproof", "shroud", "indestructible", "prowess", "swampwalk", "forestwalk", "mountainwalk",
    "infect", "devoid", "exalted", "fear", "horsemanship", "undying", "persist", "wither", "rebound",
    "storm", "cascade", "islandwalk", "plainswalk", "shadow", "intimidate",
    "nonbasic landwalk", "legendary landwalk", "decayed",
}
BASIC_MANA = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}
NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
           "eight": 8, "nine": 9, "ten": 10}
COLOR_WORDS = r"(?:white|blue|black|red|green|colorless)"


NO_MATCH = object()      # returned by a template builder: "not this template after all"


def _distinct_bounce():
    return Effect("bounce", target="nonland_perm", filter="opp", data={"distinct": True})


def _distinct_pump(m):
    return Effect("pump", int(m[1]), int(m[2]), target="creature_mine", data={"distinct": True})


def _num(word: str) -> int:
    return NUMBERS.get(word.lower()) or int(word)


@dataclass
class Effect:
    # damage, destroy, draw, gain_life, drain, pump, counter, lose_life, debuff, wrath, wrath_pw,
    # bounce, bounce_spell, scry, surveil, dig, dig_put, discard, discard_choice, rummage, token,
    # p1_counters, grant, add_counter, transform, regrow, reanimate_snow, gy_hate, copy_token,
    # draw_up_to, next_creature_counter, adversary, debuff_blood
    kind: str
    amount: int = 0
    amount2: int = 0
    # any, creature, creature_pw, creature_mine, nonland_perm, land, artifact, player, spell, opp_spell,
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
    intervening_if: str = ""         # checked at triggering and resolution
    min_level: int = 0               # Class: the trigger works once the Class is at least this level


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
class Activated:
    kind: str                        # animate, barrens, sac_debuff, ability
    cost: dict
    power: int = 0
    toughness: int = 0
    keywords: frozenset = frozenset()
    subtypes: frozenset = frozenset()    # creature types it becomes (Kaito: Ninja)
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
    condition: str = ""              # graveyard activation restriction: delirium, gy8


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
    modes: list = field(default_factory=list)           # modal spells: one effect list per mode
    modes_choose: int = 1
    loyalty: int = 0
    loyalty_abilities: list = field(default_factory=list)   # (cost, effects)
    turn_creature: tuple = ()                           # Kaito: (power, toughness, subtypes, keywords) during your turn
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
    # Equipment: equip cost, and what the equipped creature gets.
    equip_cost: dict | None = None
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
    gy_activated: list = field(default_factory=list)    # Activated abilities that return this card to the battlefield
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
    mana_sac_no_tap: bool = False                       # sacrifice for mana without a tap cost (Spawn/Scion)
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
    color_override: frozenset | None = None             # explicit face colours / colour indicator
    exalted: int = 0                                    # native instances (they stack)
    block_only_flying: bool = False
    improvise: bool = False
    delve: bool = False
    cascade: int = 0
    storm: int = 0
    basic: bool = False
    legendary: bool = False

    @property
    def colors(self) -> frozenset:
        if "devoid" in self.keywords:
            return frozenset()
        if self.color_override is not None:
            return self.color_override
        return frozenset(c for c in COLORS if self.mana_cost.get(c) or any(c in pip for pip in self.hybrid))

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
    def is_class(self): return "Class" in self.subtypes

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
