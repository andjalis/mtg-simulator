"""Turn Scryfall card JSON into the simplified CardDef the engine understands.

Oracle text is matched sentence by sentence against a small set of templates.
Anything that does not match is recorded in CardDef.unsupported so reports can
say which cards are only partially simulated.
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field

COLORS = ("W", "U", "B", "R", "G")
KEYWORDS = {
    "flying", "reach", "haste", "trample", "first strike", "double strike",
    "deathtouch", "lifelink", "vigilance", "defender", "menace",
    "flash", "hexproof", "indestructible", "prowess",
}
BASIC_MANA = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}
NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
COLOR_WORDS = r"(?:white|blue|black|red|green|colorless)"


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


@dataclass
class AltCost:
    """Another way to cast a card: flashback, foretell, spectacle, blitz, channel, Baleful Mastery."""
    kind: str                        # flashback, foretell, spectacle, blitz, channel, alt, kicker
    cost: dict
    zone: str = "hand"               # hand, graveyard, foretold
    effects: list | None = None      # channel / kicker: these effects instead of the card's
    extra: list = field(default_factory=list)    # extra effects (Baleful: an opponent draws)
    life: int = 0


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
    text: str = ""


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
    pw_instant_on_entry: bool = False                   # The Wandering Emperor
    chapters: list = field(default_factory=list)        # saga chapters: one effect list each
    back: "CardDef | None" = None                       # transformed face
    adventure: "CardDef | None" = None
    land_face: "CardDef | None" = None                  # a modal double-faced card's land back face
    alt_costs: list = field(default_factory=list)
    activated: list = field(default_factory=list)
    anthem: tuple = ()                                  # (power, toughness) for creatures you control
    crew: int = 0
    min_blocker_power: int = 0
    keyword_at_counters: tuple = ()                     # (n, keyword): Pelt Collector
    token_kind: str = ""                                # treasure, clue, blood
    is_token: bool = False
    is_ability: bool = False                            # a channel ability cast like a spell
    etb_counters: int = 0                               # "enters with N +1/+1 counters on it"
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
    triggers = []
    if ability:
        parsed = _parse_trigger(ability.rstrip("."). replace("this creature", "~") + ".")
        triggers = parsed[0] if parsed else []
    return Effect("token", _num(m_count), data={"name": " ".join(subtypes) or "Token", "power": int(power),
                                                "toughness": int(toughness), "keywords": kws,
                                                "attacking": attacking, "triggers": triggers})


_SRC = r"(?:~|it|he|she)"
_EFFECT_PATTERNS = [
    (_SRC + r" deals (\d+) damage to any target", lambda m: Effect("damage", int(m[1]), target="any")),
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
    (r"(?:you )?draw (a|one|two|three|four|\d+) cards?", lambda m: Effect("draw", _num(m[1]))),
    (r"(?:then )?if you have fewer than (three) cards in hand, draw cards equal to the difference",
     lambda m: Effect("draw_up_to", _num(m[1]))),
    (r"you gain (\d+) life", lambda m: Effect("gain_life", int(m[1]))),
    (r"its controller gains (\d+) life", lambda m: Effect("gain_life", int(m[1]), target="that_controller")),
    (r"each opponent loses (\d+) life", lambda m: Effect("drain", int(m[1]), target="each_opponent")),
    (r"each opponent loses (\d+) life and you gain (\d+) life",
     lambda m: [Effect("drain", int(m[1]), target="each_opponent"), Effect("gain_life", int(m[2]))]),
    (r"DEVOTIONDRAIN ([WUBRG])", lambda m: Effect("drain_devotion", data={"color": m[1]})),
    (r"target creature(?: you control)? gets \+(\d+)/\+(\d+) until end of turn",
     lambda m: Effect("pump", int(m[1]), int(m[2]), target="creature")),
    (r"~ gets \+(\d+)/\+(\d+) until end of turn", lambda m: Effect("pump", int(m[1]), int(m[2]), target="self")),
    (r"counter target spell with mana value (\d+)",
     lambda m: Effect("counter", target="spell", filter=f"cmc:{m[1]}")),
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
    (r"return target (?:nonland permanent|creature|artifact, creature, enchantment, or planeswalker)"
     r"(?: an opponent controls| you don't control)? to its owner's hand",
     lambda m: Effect("bounce", target="nonland_perm")),
    (r"scry (\d+)", lambda m: Effect("scry", int(m[1]))),
    (r"surveil (\d+)", lambda m: Effect("surveil", int(m[1]))),
    (r"DIG (\d+) (\d+)", lambda m: Effect("dig", int(m[1]), int(m[2]))),
    (r"DIGPUT (\d+) (\d+)", lambda m: Effect("dig_put", int(m[1]), int(m[2]))),
    (r"DIGFILTER (\d+) (.+)", lambda m: Effect("dig", int(m[1]), 1, data={"filter": m[2]})),
    (r"DIGLANDS (\d+)", lambda m: Effect("dig", 0, int(m[1]), data={"x_lands": True})),
    (r"IMPULSE (\d+)", lambda m: Effect("draw", int(m[1]))),   # "exile the top N, you may play them"
    (r"TARGETDISCARD", lambda m: Effect("discard_choice", 1, target="player")),
    (r"TARGETDISCARDNONCREATURE", lambda m: Effect("discard_choice", 1, target="player", filter="noncreature")),
    (r"(?:target player|each opponent) mills (a|one|two|three|four|five|\d+) cards?",
     lambda m: Effect("mill", _num(m[1]), target="player")),
    (r"mill (a|one|two|three|four|five|\d+) cards?", lambda m: Effect("mill", _num(m[1]))),
    (r"tap (?:up to one )?target (?:creature|nonland permanent)(?: an opponent controls| you don't control)?",
     lambda m: Effect("tap", 1, target="creature")),
    (r"tap up to (two|three) target creatures", lambda m: Effect("tap", _num(m[1]), target="creature")),
    (r"tap target creature(?: an opponent controls)? and put (a|two|three) stun counters? on it",
     lambda m: [Effect("tap", 1, target="creature"), Effect("stun", _num(m[1]), target="prev")]),
    (r"put (a|two|three) stun counters? on it", lambda m: Effect("stun", _num(m[1]), target="prev")),
    (r"GOBLINGUIDE", lambda m: Effect("reveal_land", target="each_opponent")),
    (r"FETCHBASIC( UNTAP4)?", lambda m: Effect("fetch_basic", data={"untap4": bool(m[1])})),
    (r"double the number of \+1/\+1 counters on ~", lambda m: Effect("double_counters", target="self")),
    (r"double the power of target creature you control until end of turn",
     lambda m: Effect("double_power", target="creature_mine")),
    (r"(?:then )?draw a card for each opponent who lost life this turn",
     lambda m: Effect("draw", 1, cond="opp_lost_life")),
    (r"target player discards a card", lambda m: Effect("discard", 1, target="player")),
    (r"(?:then )?discard (a|one|two|three) cards? unless you discard an? basic land card",
     lambda m: Effect("discard", _num(m[1]), data={"unless": "basic_land"})),
    (r"(?:then )?discard (a|one|two|three) cards?(?: unless .*)?", lambda m: Effect("discard", _num(m[1]))),
    (r"RUMMAGE (\d+)", lambda m: Effect("rummage", int(m[1]))),
    (r"create (a|one|two|three|four|five) (\d+)/(\d+) ((?:\w+ )+?)creature tokens?(?: that's (tapped and "
     r"attacking))?(?: with ([\w ,]+))?",
     lambda m: _token(m[1], m[2], m[3], m[4], m[6], bool(m[5]))),
    (r'create (a) (\d+)/(\d+) ((?:\w+ )+?)creature token with "(.+)"',
     lambda m: _token(m[1], m[2], m[3], m[4], "", False, m[5])),
    (r"create (a|one|two) (treasure|clue|blood) tokens?", lambda m: Effect("token", _num(m[1]),
                                                                          data={"kind": m[2].lower()})),
    (r"its controller investigates", lambda m: Effect("token", 1, target="that_controller", data={"kind": "clue"})),
    (r"create a token that's a copy of target token you control", lambda m: Effect("copy_token")),
    (r"put (a|one|two|three) \+1/\+1 counters? on (?:up to one )?target creature(?: you control)?",
     lambda m: Effect("p1_counters", _num(m[1]), target="creature_mine")),
    (r"put (a|one|two|three) \+1/\+1 counters? on ~", lambda m: Effect("p1_counters", _num(m[1]), target="self")),
    (r"ELSPETHPLUS", lambda m: Effect("p1_counters", 1, target="creature_mine", data={"keyword": "flying"})),
    (r"it gains (hexproof|first strike|haste|indestructible) until end of turn",
     lambda m: Effect("grant", target="prev", data={"keyword": m[1].lower()})),
    (r"target creature gains (double strike|first strike|trample|haste|hexproof|indestructible) until end of turn",
     lambda m: Effect("grant", target="creature", data={"keyword": m[1].lower()})),
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
    (r"return target creature card from your graveyard to your hand", lambda m: Effect("regrow")),
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
    (re.compile(r"look at the top (\w+) cards of your library\. you may put a permanent card with mana value "
                r"(\d+) or less from among them onto the battlefield(?: with a shield counter on it)?\. put the rest "
                r"on the bottom of your library in a random order\.", re.I),
     lambda m: f"DIGPUT {_num(m[1])} {m[2]}."),
    (re.compile(r"exile the top (card|\w+ cards) of your library\. until (?:the end of your next turn|end of turn), you "
                r"may play (?:that card|those cards)(?: this turn)?\.", re.I),
     lambda m: f"IMPULSE {1 if m[1] == 'card' else _num(m[1].split()[0])}."),
    (re.compile(r"target player reveals their hand\. you choose a nonland card from it\. that player discards "
                r"that card\.", re.I), lambda m: "TARGETDISCARD."),
    (re.compile(r"then return a creature or planeswalker card with mana value X or less from your graveyard to "
                r"the battlefield, where X is the amount of \{S\} spent to cast ~\.", re.I),
     lambda m: "REANIMATESNOW."),
    (re.compile(r"you may pay \{2\}\{R\} any number of times\. when you pay this cost one or more times, .*",
                re.I | re.S), lambda m: "ADVERSARY."),
]

_TRIGGERS = [
    (r"When(?:ever)? ~ enters or attacks, (.+)", ("etb", "attacks")),
    (r"When ~ enters and at the beginning of your upkeep, (.+)", ("etb", "upkeep")),
    (r"When(?:ever)? ~ enters(?: the battlefield)?, (.+)", ("etb",)),
    (r"Whenever ~ attacks, (.+)", ("attacks",)),
    (r"When(?:ever)? ~ dies, (?:if it was a creature, )?(.+)", ("dies",)),
    (r"Whenever ~ deals combat damage to a player, (.+)", ("combat_damage_player",)),
    (r"Whenever you cast a noncreature spell, (.+)", ("cast_noncreature",)),
    (r"Whenever you cast an instant or sorcery spell, (.+)", ("cast_instant_sorcery",)),
    (r"Whenever you cast a spell, (.+)", ("cast_spell",)),
    (r"Whenever a player casts a spell with mana value (\d+) or less, (.+)", ("any_cast",)),
    (r"At the beginning of your upkeep, (.+)", ("upkeep",)),
    (r"At the beginning of your end step, (.+)", ("end_step",)),
    (r"Whenever a creature an opponent controls dies, (.+)", ("opp_creature_dies",)),
    (r"Whenever another creature you control enters or dies, if that creature's power is greater than ~'s, (.+)",
     ("other_creature_enters", "other_creature_dies")),
    (r"Whenever a land you control enters, (.+)", ("land_enters",)),
    (r"Whenever (~ or )?(another|an?) ((?:[\w-]+(?:,? or |, | ))*?(?:creature|artifact|enchantment|planeswalker|"
     r"[A-Z]\w+)s?) you control enters(?: and whenever an? ([A-Z]\w+) you control enters)?, (.+)",
     ("permanent_enters",)),
    (r"Whenever you draw a card, (.+)", ("you_draw",)),
    (r"Whenever an opponent draws a card, (.+)", ("opp_draw",)),
    (r"Whenever ~ becomes the target of a spell, (.+)", ("targeted_by_spell",)),
]


def _parse_effects(text: str):
    """Parse a run of sentences into effects. Returns (effects, unmatched_sentences)."""
    effects, unmatched = [], []
    for rx, rep in _SUBS:
        text = rx.sub(rep, text)
    for sentence in re.split(r"(?<=\.)\s+", text.strip()):
        s = sentence.strip().rstrip(".").strip()
        if not s:
            continue
        for pat, build in _EFFECT_PATTERNS:
            m = re.fullmatch(pat, s, flags=re.IGNORECASE)
            if m is None and s.lower().startswith("then "):
                m = re.fullmatch(pat, s[5:], flags=re.IGNORECASE)
            if m:
                eff = build(m)
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
    text = re.sub(r"\bthis (creature|land|spell|enchantment|artifact|permanent|token|vehicle|saga)\b", "~",
                  text, flags=re.I)
    text = re.sub(r", where X is the amount of mana spent to cast ~\.", ".", text).replace(
        "the top X cards", f"the top {int(data.get('cmc', 0) or 0)} cards")

    keywords, produces, etb, spell, unsupported, approximations = set(), set(), [], [], [], []
    triggers: list[Trigger] = []
    extra: dict = {"snow": "Snow" in type_line}
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
    if "X" in cost:
        unsupported.append("X costs are paid as X=0")
    if data.get("loyalty"):
        extra["loyalty"] = stat(data["loyalty"]) or 0

    kicked: list = []
    for line in (l.strip() for l in text.split("\n")):
        if not line:
            continue
        if any(a.startswith("never paid: As an additional cost") for a in approximations):
            line = re.sub(r"\s*If ~'s additional cost was paid, [^.]+\.", "", line).strip()
            if not line:
                continue
        kicked += re.findall(r"If ~ was kicked, (.+?\.)", line)
        line = re.sub(r"\s*If ~ was kicked, .+?\.", "", line).strip()
        line = re.sub(r"^(?:Landfall|Revolt|Raid|Morbid) — (?=When|At|If)", "", line)
        parts = [p.strip().lower() for p in line.split(",")]
        if all(p in KEYWORDS or re.fullmatch(r"ward \{\d+\}", p) for p in parts):
            for p in parts:
                if p.startswith("ward"):
                    extra["ward"] = int(re.search(r"\d+", p)[0])
                else:
                    keywords.add(p)
            continue
        if line.startswith("•") and mode_sink is not None:
            effs, bad = _parse_effects(line[1:].strip())
            if bad or not effs:
                unsupported.append(line)
            else:
                mode_sink.append(effs)
            continue
        mode_sink = None
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
        m = re.fullmatch(r"As ~ enters(?: the battlefield)?, you may behold an? ([A-Z]\w+)\. If you don't, ~ enters "
                         r"(?:the battlefield )?tapped\.", line)
        if m:
            extra["tapped_condition"] = f"behold:{m[1]}"
            continue
        if re.fullmatch(r"~ can't block\.", line):
            extra["cant_block"] = True
            continue
        m = re.fullmatch(r"Equipped creature (?:gets \+(\d+)/\+(\d+))?(?: and )?(?:has (.+?))?\.", line)
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
        m = re.fullmatch(r"Equip (\{[^ .]+\})(\. This ability costs [^.]+ less to activate[^.]*\.)?", line)
        if m:
            extra["equip_cost"] = parse_mana_cost(m[1])
            if m[2]:
                approximations.append(f"cost reduction ignored:{m[2]}")
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
        m = re.fullmatch(r"Kicker (\{[^ ]+\})", line)
        if m:
            extra["kicker"] = parse_mana_cost(m[1])
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
        if re.fullmatch(r"~ costs \{1\} less to cast for each instant and sorcery card in your graveyard\.", line):
            extra["cost_reduction"] = "instant_sorcery_gy"
            continue
        if re.fullmatch(r"~ costs \{X\} less to cast, where X is the total power of creatures you control\.", line):
            extra["cost_reduction"] = "power"
            continue
        m = re.fullmatch(r"~ can't be blocked by creatures with power (\d+) or less\.", line)
        if m:
            extra["min_blocker_power"] = int(m[1]) + 1
            continue
        m = re.fullmatch(r"As long as ~ has (three) or more \+1/\+1 counters on it, it has (\w+)\.", line)
        if m:
            extra["keyword_at_counters"] = (_num(m[1]), m[2].lower())
            continue
        m = re.fullmatch(r"Creatures you control get \+(\d+)/\+(\d+)\.", line)
        if m:
            extra["anthem"] = (int(m[1]), int(m[2]))
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
        act = _parse_ability(line, approximations)
        if act is not None:
            activated.append(act)
            continue
        trig = _parse_trigger(line)
        if trig is not None:
            new, bad, choose_modes = trig
            triggers += new
            if choose_modes is not None:
                mode_sink = choose_modes
            for t in new:
                if t.event == "etb":
                    etb += t.effects
            unsupported += bad
            continue
        if not types.isdisjoint({"Instant", "Sorcery"}):
            m = re.fullmatch(r"Choose (one|two) —", line)
            if m:
                extra["modes_choose"] = _num(m[1])
                mode_sink = modes
                continue
            effs, bad = _parse_effects(line)
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
    out = _parse_trigger_line(line)
    if out is not None and once:
        for t in out[0]:
            t.once = True
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
        if events[0] == "other_creature_enters":
            flt = "greater_power"
        if events == ("permanent_enters",):
            desc = m[3] + (f" or {m[4]}" if m[4] else "")
            flt = f"{'self' if m[1] else 'noself'}|{'other' if m[2] == 'another' else 'any'}|{desc}"
        if re.fullmatch(r"choose up to one —", rest, flags=re.I):
            modes: list = []
            return [Trigger(e, [], flt, modes) for e in events], [], modes
        effs, bad = _parse_effects(rest)
        if not effs:
            return [], bad or [line], None
        return [Trigger(e, effs, flt) for e in events], bad, None
    return None


def make_token(name: str, power: int, toughness: int, keywords=frozenset(), triggers=None, kind: str = "") -> CardDef:
    """A token's CardDef. kind is treasure/clue/blood for artifact tokens."""
    if kind:
        produces = frozenset(COLORS) if kind == "treasure" else frozenset()
        return CardDef(name=kind.capitalize(), mana_cost={"generic": 0}, cmc=0, types=frozenset({"Artifact"}),
                       produces=produces, token_kind=kind, is_token=True)
    return CardDef(name=f"{name} token", mana_cost={"generic": 0}, cmc=0, types=frozenset({"Creature"}),
                   power=power, toughness=toughness, keywords=frozenset(keywords), triggers=list(triggers or []),
                   is_token=True)
