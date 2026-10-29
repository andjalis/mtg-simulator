"""Game objects: permanents, players and stack items, plus shared rules constants."""
from __future__ import annotations

import dataclasses
import re

from .. import auras, counting
from ..cards import BASIC_MANA, KEYWORDS, CardDef, Effect, Trigger
from .. import continuous
from ..identity import CardInstance, CardZone, Graveyard, instance


TrackedZone = CardZone  # public compatibility alias

TEAM_KEYWORDS = frozenset({"haste", "trample", "vigilance", "lifelink", "menace", "flying", "reach"})
COLOR_WORDS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
PROTECTION = {c: f"protection from {w}" for w, c in COLOR_WORDS.items()}
TARGETED = ("graveyard_card", "permanent", "any", "creature", "creature_pw", "creature_mine", "nonland_perm", "land", "artifact", "artifact_enchantment",
            "artifact_land",
            "player", "spell", "creature_or_graveyard")


class PlayerCounters(dict):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def __setitem__(self, name, value):
        from ..residual_templates import player_counter_allowed
        old = self.get(name, 0)
        if value > old and not player_counter_allowed(self.owner, name):
            value = old
        super().__setitem__(name, value)


class Counters(dict):
    """A permanent's counters; putting +1/+1 counters on it fires "p1_added" ("whenever one or more +1/+1
    counters are put on ~"). Restoring a transaction (dict.update) doesn't fire."""
    __slots__ = ("owner",)

    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def __setitem__(self, key, value):
        old = self.get(key, 0)
        perm = self.owner
        from ..residual_templates import permanent_counter_allowed
        if value > old and not permanent_counter_allowed(perm, key):
            value = old
        if value > old:
            from ..advanced_templates import counter_amount
            value = old + counter_amount(perm, key, value - old)
        super().__setitem__(key, value)
        if key == "+1/+1" and value > old and perm in perm.controller.battlefield:
            game = getattr(perm.controller, "_game", None)
            if game is not None:
                game.fire(perm.controller, "p1_added", perm)


def protected_from(perm, source) -> bool:
    """Whether perm has protection from a color of source (a CardDef, Permanent or StackItem)."""
    if isinstance(source, StackItem):
        source = source.card or source.source
    card = source.card if isinstance(source, Permanent) else source
    if not isinstance(card, CardDef) or not isinstance(perm, Permanent):
        return False
    return any(perm.has(PROTECTION[c]) for c in card.colors) or \
        len(card.colors) >= 2 and perm.has("protection from multicolored") or \
        card.is_artifact and perm.has("protection from artifacts")


class Permanent:
    def __setattr__(self, name, value):
        if name == "card":
            object.__setattr__(self, "_card", value)
            object.__setattr__(self, "_characteristic_cache", None)
            if hasattr(self, "controller"):
                value = continuous.characteristics(self, value)
        object.__setattr__(self, name, value)
        if name == "card" and hasattr(self, "controller"):
            game = getattr(self.controller, "_game", None)
            if game is not None:
                game._residual_source_index = None

    @property
    def copiable_card(self):
        return self._card

    @property
    def crewed(self):
        return self._crewed

    @crewed.setter
    def crewed(self, value):
        self._crewed = value
        game = getattr(self.controller, "_game", None)
        if value and game is not None:
            self.crew_timestamp = game.next_effect_timestamp()
        continuous.refresh(self)

    @property
    def tapped(self):
        return self._tapped

    @tapped.setter
    def tapped(self, value):
        self._tapped = value
        if not value and getattr(self, "net_locked", False):
            self.net_locked = False

    @property
    def animated(self):
        return self._animated

    @animated.setter
    def animated(self, value):
        self._animated = value
        game = getattr(self.controller, "_game", None)
        if value is not None and game is not None:
            self.animation_timestamp = game.next_effect_timestamp()
        continuous.refresh(self)

    @property
    def front(self):
        return self._front

    @front.setter
    def front(self, card):
        self._front = instance(card, getattr(self, "controller", None))
        if self._front.owner is not None:
            self.owner = self._front.owner

    def __init__(self, card: CardDef, controller: "Player"):
        self.card = card
        self.front = instance(card, controller)  # physical card behind this battlefield object
        self.controller = controller
        self.owner = self.front.owner
        self.tapped = card.enters_tapped
        self.sick = True
        self.damage = 0
        self.deathtouched = False
        self.pump_p = 0
        self.pump_t = 0
        self.counters: dict[str, int] = Counters(self)
        self.temp_kw: set[str] = set()     # until end of turn
        self.perm_kw: set[str] = set()     # from keyword counters
        self.animated = None               # Activated: a manland that is a creature until end of turn
        self.crewed = False
        self.blitz = False
        self.dashed = False
        self.unearthed = False
        self.disturbed = False             # cast with disturb: exiled instead of going to a graveyard
        self.loyalty_used = False
        self.entered_turn = 0
        self.entered_x = 0
        self.exile_turn = -1
        self.chosen_land = ""
        self.chosen_type = ""              # Cavern of Souls
        self.silenced_by = None            # Tishana's Tidebinder: loses all abilities while it stays out
        self.net_locked = False            # Braided Net: no activated abilities while it stays tapped
        self.bargained = self.gifted = False   # cast with Bargain / the gift promised
        self.produces_now = None           # set by Game.mana_sources: the colours usable right now
        self.amount_now = None             # and how much mana it makes, when that differs from its card's
        self.temp_activated = []
        self.temp_triggers = []
        self.regeneration_shields = 0
        self.regeneration_blocked = False
        self.ability_turns: dict = {}      # activated ability index -> turn it was last activated
        self.auras: list["Permanent"] = []   # Auras on this permanent (they sit on their caster's battlefield)
        self.kicks = 0                                 # times a multikicker / squad cost was paid
        self.curse_target = None                       # a Curse: the player it enchants
        self.aura_host: "Permanent | None" = None      # the permanent this Aura enchants
        self.attached_to: "Permanent | None" = None    # Equipment: the creature it is attached to
        self.damaged_by: list = []                      # permanents that dealt it damage this turn
        self.prevent_next = 0                           # "prevent the next N damage ... this turn"
        self.skip_untap = 0                             # untap steps it skips ("doesn't untap during ... next untap step")
        self.spent_color = ""              # "if {U}{U} was spent to cast it"
        self.exiled_cards: list = []       # (card, owner) exiled until this leaves the battlefield
        self.exiled_to_hand: list = []     # (card, owner) exiled from a hand until this leaves (Kitesail Freebooter)
        self.warped = False
        self.was_cast = False              # "if you cast it"
        self.hidden = None                 # the real card of a face-down (disguised) creature
        self.prepared = False              # a prepared creature may cast a copy of its spell
        self.saddled = False               # a Mount saddled this turn
        self.copy_revert = None            # the card this permanent is while it is a copy until end of turn
        self.impending = False             # cast for its impending cost: not a creature while it has time counters

    @property
    def equipment(self):
        players = [self.controller] + ([self.controller.foe] if self.controller.foe is not None else [])
        return [x for p in players for x in p.battlefield if x.attached_to is self] if self.is_creature else []

    @property
    def p1(self): return self.counters.get("+1/+1", 0)

    @property
    def anthem(self):
        return [sum(x) for x in zip((0, 0), *(p.card.anthem for p in self.controller.battlefield if p.card.anthem))]

    @property
    def per_bonus(self) -> int:
        """"~ gets +1/+1 for each artifact you control"."""
        what = self.card.pt_per
        if not what:
            return 0
        return counting.count(None, self.controller, {"what": what, "zone": "battlefield"}, self)

    def _cda_count(self, what: str) -> int:
        c = self.controller
        if what == "cards in your hand":
            return len(c.hand)
        if what == "cards in your graveyard":
            return len(c.graveyard)
        kind = what.split()[0][:-1].capitalize()           # "creatures you control" -> Creature
        return sum(kind in x.card.types for x in c.battlefield)

    def _pt_bonus(self):
        """(power, toughness) from anthems, attached equipment and "for each" counts, in one pass
        over the battlefield; the same sums as anthem, equipment and per_bonus."""
        from ..residual_templates import anthem_bonus
        bp, bt = anthem_bonus(self)
        creature = self.is_creature
        what = self.card.pt_per
        sp, st = self.card.pt_scale
        for x in self.controller.battlefield:
            c = x.card
            if creature:
                a = c.anthem
                if a:
                    bp += a[0]
                    bt += a[1]
                if c.anthem_enchanted and self.auras:
                    bp += c.anthem_enchanted[0]
                    bt += c.anthem_enchanted[1]
        if creature and self.card.pt_cda:
            n = self._cda_count(self.card.pt_cda)
            bp += n
            bt += n
        if creature:
            for pl in (self.controller, self.controller.foe):
                for x in (pl.battlefield if pl is not None else ()):
                    a = x.card.anthem_all
                    if a and a[0] in self.card.subtypes:
                        bp += a[1]
                        bt += a[2]
        for equipment in self.equipment:
            bp += equipment.card.equip_bonus[0] + equipment.counters.get("hone", 0)
            bt += equipment.card.equip_bonus[1]
        if self.partner is not None:
            from ..batch1_templates import soulbond_bonus
            sb = soulbond_bonus(self)
            bp += sb[0]
            bt += sb[1]
        for cond, pp, tt in self.card.pt_if:
            if not cond.startswith(("gy", "lands", "speed")):
                if self.condition(cond):              # metalcraft, "as long as it's your turn / attacking"
                    bp += pp
                    bt += tt
                continue
            gy = self.controller.graveyard
            n = sum(c.is_permanent for c in gy) if cond.startswith("gy_perm") else len(gy)
            if cond.startswith("lands"):
                n = sum(x.card.is_land for x in self.controller.battlefield)
            elif cond.startswith("speed"):
                n = self.controller.speed
            if n >= int(cond.split(">=")[1]):
                bp += pp
                bt += tt
        if creature:
            from ..batch1_templates import curses_on
            for c in curses_on(self.controller._game, self.controller):
                pt = c.card.advanced_rules.get('curse_pt')
                if pt:
                    bp += pt[0]
                    bt += pt[1]
        for x in self.controller.battlefield:
            for kw, pp, tt, *other in x.card.anthem_kw:
                if creature and self.has(kw) and not (other and x is self):
                    bp += pp
                    bt += tt
            if creature and x.card.anthem_chosen and x.chosen_type and x.chosen_type in self.card.subtypes:
                bp += x.card.anthem_chosen[0]
                bt += x.card.anthem_chosen[1]
            for sub, pp, tt, other in x.card.anthem_sub:
                if creature and (sub in self.card.subtypes or (sub == "Token" and self.card.is_token)
                                 or sub.startswith("color:") and sub[6:] in self.card.colors
                                 or sub.startswith("type:") and sub[5:] in self.card.types) \
                        and not (other and x is self):
                    bp += pp
                    bt += tt
        for sub, pp, tt in self.controller.emblems:
            if creature and sub in self.card.subtypes:
                bp += pp
                bt += tt
        if what:
            if what == "attached:aura":
                per = len(self.auras)
            elif what.startswith("gy:"):
                per = counting.count(None, self.controller, {"what": what[3:], "zone": "graveyard"}, self)
            else:
                per = counting.count(None, self.controller, {"what": what, "zone": "battlefield"}, self)
            bp += per * sp
            bt += per * st
        if creature:
            for a in self.auras:
                e = a.card.equip_bonus
                bp += e[0]
                bt += e[1]
                if "per_enchantment" in a.card.aura_flags:     # Virtuous Role
                    n = sum("Enchantment" in y.card.types for y in self.controller.battlefield)
                    bp += n
                    bt += n
        return bp, bt

    @property
    def power(self):
        if hasattr(self, "last_pt") and self not in self.controller.battlefield:
            return self.last_pt[0]
        return continuous.pt(self)[0]

    @property
    def toughness(self):
        if hasattr(self, "last_pt") and self not in self.controller.battlefield:
            return self.last_pt[1]
        return continuous.pt(self)[1]

    @property
    def m1(self): return self.counters.get("-1/-1", 0)

    @property
    def loyalty(self): return self.counters.get("loyalty", 0)

    @property
    def silenced(self):
        by = self.silenced_by
        return by is not None and by in by.controller.battlefield

    @property
    def abilities_suppressed(self):
        return self.silenced or any('loses_abilities' in a.card.aura_flags for a in self.auras)

    def has(self, kw):
        if self.silenced_by is not None and kw in KEYWORDS and self.silenced:
            return False
        if self.auras and kw in KEYWORDS and any("loses_abilities" in a.card.aura_flags for a in self.auras):
            return False
        return continuous.keyword(self, kw, self._has_unlayered(kw))

    def _has_unlayered(self, kw):
        game = getattr(self.controller, '_game', None)
        if game is not None:
            from ..permanent_templates import matches
            for player in game.players:
                for source in player.battlefield:
                    if not source.abilities_suppressed and any(kw in kws and matches(game, self, spec, source.controller, source)
                            for spec, kws in source.card.static_keyword_grants):
                        return True
        if self.card.level_blocks:
            from ..batch1_templates import level_block
            block = level_block(self)
            if block is not None and kw in block[1]:
                return True
        if kw in self.card.keywords or kw in self.temp_kw or kw in self.perm_kw or (kw in KEYWORDS and self.counters.get(kw, 0) > 0):
            return True
        if kw in ('training', 'dethrone') and self.is_creature and any(k == kw and not (other and source is self)
                                   for source in self.controller.battlefield
                                   for k, other in source.card.granted_attack_keywords
                                   if not source.silenced and not any('loses_abilities' in a.card.aura_flags for a in source.auras)):
            return True
        if self.animated and kw in self.animated.keywords:
            return True
        if self.is_creature:
            for x in self.equipment:
                if kw in x.card.equip_keywords:
                    return True
            for a in self.auras:
                if kw in a.card.equip_keywords:
                    return True
        if self.partner is not None:
            from ..batch1_templates import soulbond_has
            if soulbond_has(self, kw):
                return True
        for k, cond in self.card.cond_keywords:
            if k == kw and self.condition(cond):
                return True
        if any(sub in self.card.subtypes and k == kw and not (other and x is self)
               for x in self.controller.battlefield for sub, k, other in x.card.keyword_sub):
            return True
        if self.is_creature and self.p1 > 0 and any(kw in x.card.counter_team_keywords
                                                    for x in self.controller.battlefield):
            return True
        if kw in TEAM_KEYWORDS and self.is_creature:
            for x in self.controller.battlefield:
                if kw in x.card.team_keywords:
                    return True
        if self.card.keyword_at_counters and self.p1 >= self.card.keyword_at_counters[0]:
            return kw == self.card.keyword_at_counters[1]
        return kw == "haste" and (self.blitz or self.dashed or self.unearthed)

    partner = None      # Soulbond: the creature this one is paired with

    def condition(self, cond: str) -> bool:
        if cond.startswith("another:"):
            kind = cond[8:]
            return any(kind in x.card.subtypes for x in self.controller.battlefield if x is not self)
        if cond == "max_speed":
            return self.controller.speed >= 4
        if cond == "your_turn":
            return self.controller.my_turn
        if cond == "delirium":
            return len({t for c in self.controller.graveyard for t in c.types}) >= 4
        if cond.startswith("land:"):
            return any(cond[5:] in x.card.subtypes for x in self.controller.battlefield if x.card.is_land)
        if cond.startswith("artifacts>="):
            return sum(x.card.is_artifact for x in self.controller.battlefield) >= int(cond[11:])
        if cond == "attacking":
            game = getattr(self.controller, "_game", None)
            return game is not None and self in game.attackers
        if cond.startswith("gy"):
            gy = self.controller.graveyard
            n = sum(c.is_permanent for c in gy) if cond.startswith("gy_perm") else len(gy)
            return n >= int(cond.split(">=")[1])
        if cond.startswith("opp_life<="):
            opp = getattr(self.controller, "opponent", None)
            return opp is not None and opp.life <= int(cond[10:])
        return False

    @property
    def is_creature(self):
        if self.impending and self.counters.get("time"):
            return False
        return "Creature" in self.card.types

    @property
    def is_planeswalker(self): return self.card.is_planeswalker

    @property
    def exalted_count(self):
        return self.keyword_instances("exalted")

    def keyword_instances(self, keyword):
        """Count native and supported granted instances of a triggered keyword."""
        count = getattr(self.card, keyword, 0) or int(keyword in self.card.keywords)
        count += int(keyword in self.temp_kw) + int(keyword in self.perm_kw)
        count += sum(kw == keyword and self.condition(cond) for kw, cond in self.card.cond_keywords)
        count += int(self.animated is not None and keyword in self.animated.keywords)
        count += int(self.counters.get(keyword, 0) > 0)
        if self.is_creature:
            if keyword in ('training', 'dethrone'):
                count += sum(k == keyword and not (other and source is self)
                             for source in self.controller.battlefield
                             for k, other in source.card.granted_attack_keywords if not source.silenced
                             and not any('loses_abilities' in a.card.aura_flags for a in source.auras))
            count += sum(keyword in e.card.equip_keywords for e in self.equipment + self.auras)
            count += sum(sub in self.card.subtypes and kw == keyword and not (other and x is self)
                         for x in self.controller.battlefield for sub, kw, other in x.card.keyword_sub)
            if self.p1:
                count += sum(keyword in x.card.counter_team_keywords for x in self.controller.battlefield)
        if self.card.keyword_at_counters:
            n, kw = self.card.keyword_at_counters
            count += int(kw == keyword and self.p1 >= n)
        return count

    @property
    def triggers(self):
        if self.silenced_by is not None and self.silenced or any('loses_abilities' in a.card.aura_flags for a in self.auras):
            return []
        exalted = [Trigger("attacks_alone", [Effect("pump", 1, 1, target="trigger_subject")])
                   for _ in range(self.exalted_count)]
        mine = self.card.triggers
        if self.card.is_class:
            level = self.counters.get("level", 1)
            mine = [t for t in mine if t.min_level <= level]
        decayed = [Trigger("attacks", [Effect("decayed_delay", target="self")])] if self.has("decayed") else []
        attack_counters = [Trigger("attacks", [Effect("attack_counter", data={"training": kw == "training"})], filter=kw)
                           for kw in ("training", "dethrone") if self.has(kw)
                           for _ in range(max(1, self.keyword_instances(kw)))]
        return list(mine) + (list(self.animated.triggers) if self.animated else []) + exalted + decayed + attack_counters + list(self.temp_triggers)

    @property
    def ward(self) -> int:
        if self.animated and self.animated.ward:
            return self.animated.ward
        if self.card.ward_untapped_only and self.tapped:
            return 0
        return max([self.card.ward] + [e.card.equip_ward for e in self.equipment] +
                   [a.card.equip_ward for a in self.auras])

    def can_attack(self):
        return (self.is_creature and not self.tapped and not self.has("defender") and not (self.card.cant_attack and not self.abilities_suppressed)
                and not (self.auras and auras.stops_combat(self))
                and (not self.sick or self.has("haste")))

    @property
    def activated(self):
        from ..backlog_templates import grants
        return list(self.card.activated) + [a for a in grants(self) if a.kind == 'ability']

    def granted_mana(self) -> frozenset:
        """Colours other permanents let this one tap for (Enduring Vitality, Great Divide Guide)."""
        from ..backlog_templates import grants
        out = frozenset(k for a in grants(self) if a.kind == 'granted_mana' for k in a.keywords)
        c = self.card
        if c.is_land and any(x.card.chosen_land_lock and x.chosen_land == c.name
                             for pl in (self.controller, self.controller.foe) if pl is not None for x in pl.battlefield):
            out |= {"C"}                                  # Petrified Hamlet
        for src in self.controller.battlefield:
            for scope, cols in src.card.grant_mana:
                if scope == "creature" and self.is_creature or scope == "land" and c.is_land or \
                        scope == "creature_token" and self.is_creature and c.is_token or \
                        scope == "food" and "Food" in c.subtypes or \
                        scope == "other" and src is not self or \
                        scope == "land_or_ally" and (c.is_land or "Ally" in c.subtypes):
                    out |= cols
        return out

    def can_tap_for_mana(self):
        if self.card.mana_sac_only:
            return True
        return bool(self.card.produces or self.card.restricted_produces or self.granted_mana()) and not self.tapped and \
            not (self.is_creature and self.sick and self.card.mana_filter != "once")

    def __repr__(self):
        if self.is_creature:
            return f"{self.card.name}({self.power}/{self.toughness})"
        if self.is_planeswalker:
            return f"{self.card.name}[{self.loyalty}]"
        return self.card.name


FIREBEND_MANA = CardDef(name="Firebending mana", mana_cost={"generic": 0}, cmc=0, types=frozenset({"Artifact"}),
                        produces=frozenset({"R"}), is_token=True)


_POOL_MANA: dict = {}


def _gy_desc(desc: str) -> str:
    """A graveyard-card description in the form copies.fits reads ("noncreature, nonland permanent" is one
    description; "artifact, creature, or land" lists alternatives)."""
    desc = desc.replace("and/or", "or").replace(" cards", "").replace(" card", "")
    return desc if " or " in desc else desc.replace(", ", " ")


def pool_mana(color: str) -> CardDef:
    """The CardDef of one floating mana of a colour (see Player.pool)."""
    if color not in _POOL_MANA:
        _POOL_MANA[color] = dataclasses.replace(FIREBEND_MANA, name=f"{color} mana", produces=frozenset({color}))
    return _POOL_MANA[color]


OUTLAWS = ("Assassin", "Mercenary", "Pirate", "Rogue", "Warlock")


class Player:
    CARD_ZONES = frozenset({"library", "hand", "graveyard", "exile", "sideboard",
                            "on_adventure", "foretold", "plotted", "warp_exile", "airbent"})

    def __setattr__(self, name, value):
        if name in self.CARD_ZONES:
            cls = Graveyard if name == "graveyard" else CardZone
            if not isinstance(value, cls) or value.owner is not self:
                value = cls(value, owner=self, name=name)
        object.__setattr__(self, name, value)

    my_turn = False
    prevent_next = 0          # "prevent the next N damage that would be dealt to target player this turn"
    extra_lands_turn = 0      # "you may play an additional land this turn"
    foe = None
    speed = 0
    speed_turn = -1

    def __init__(self, name: str, deck: list[CardDef], ai, *, sideboard=()):
        self.name = name
        self.deck = deck
        self.ai = ai
        self.library: list[CardDef] = []
        self.pool: list = []                 # Firebending: one-use red mana until end of combat
        self.emblems: list = []              # (creature type, +power, +toughness): "Ninjas you control get +1/+1"
        self.hand: list[CardDef] = []
        self.battlefield: list[Permanent] = []
        self.graveyard: list[CardDef] = Graveyard()
        self.exile: list[CardDef] = TrackedZone()
        self.sideboard: list[CardDef] = list(sideboard or ())
        self.on_adventure: list[CardDef] = []
        self.foretold: list[CardDef] = []
        self.suspended: list = []          # [card, time counters] for suspended cards in exile
        self.plotted: list[CardDef] = []
        self.airbent: list[CardDef] = []   # exiled by airbend: its owner may cast it for {2}
        self.warp_exile: list[CardDef] = []
        self.exiled_turn: dict = {}        # card name -> turn it was plotted or exiled after warp
        self.creature_died_turn = False    # one of our creatures died this turn
        self.impulse: list = []            # (card, last turn it may be played): "exile the top card, you may play it"
        self.impulse_new: list = []        # cards the latest exile_top effect exiled
        self._life = 20
        self.lost = False
        self.lands_played = 0
        self.sacrificed_turn = 0
        self.milled_last: list[CardDef] = []     # the cards the last mill put into the graveyard
        self.counters: dict[str, int] = PlayerCounters(self)     # poison, energy, experience, and other player counters
        self.picked_last: CardDef | None = None   # the card mill_pick returned to hand
        self.discarded_last: list[CardDef] = []
        self.discarded_cards: list[CardDef] = []      # discarded this turn (Mayhem)
        self.action_lock_turn = None
        self.granted_fb: list[CardDef] = []           # graveyard cards that gained flashback this turn
        self.mulligans = 0
        self.lost_life_turn = False
        self.life_lost_amount = 0         # life lost this turn (damage and loss alike)
        self.perm_left_turn = False
        self.entered_nonland_turn = 0     # nonland permanents that entered under this player's control this turn
        self.attacked_with = 0
        self.next_creature_counters = 0
        self.life_gained_turn = 0

    @property
    def life(self): return self._life

    @property
    def land_played(self) -> bool:
        """Whether this turn's land drops are used up (Icetill Explorer gives another)."""
        return self.lands_played > sum(x.card.extra_lands for x in self.battlefield) + self.extra_lands_turn

    @land_played.setter
    def land_played(self, value):
        self.lands_played = 99 if value else 0

    @life.setter
    def life(self, value):
        from ..residual_templates import life_locked
        if life_locked(self):
            return
        if value < self._life:
            self.lost_life_turn = True
            self.life_lost_amount += self._life - value
        self._life = value

    @property
    def creatures(self): return [p for p in self.battlefield if p.is_creature]

    @property
    def planeswalkers(self): return [p for p in self.battlefield if p.is_planeswalker]

    def __repr__(self): return self.name


class StackItem:
    """A spell, copy, or ability waiting to resolve. ``card`` is None for abilities."""

    def __init__(self, controller: Player, effects: list, targets: list, card: CardDef | None = None,
                 source: Permanent | None = None, name: str = "", context=None, kind: str = ""):
        self.controller = controller
        self.effects = effects
        self.targets = targets
        self.card = card
        self.source = source
        self.name = name or (card.name if card else "ability")
        self.context = context      # e.g. the player whose creature died, for "that player loses 2 life"
        self.intervening_if = ""    # gate the entire trigger once when resolution starts
        self.context_ref = (context.zone.reference(context) if isinstance(context, CardInstance)
                            and isinstance(context.zone, CardZone) and context in context.zone else None)
        self.kind = kind or ("spell" if card else "trigger")   # spell, copy, trigger, chapter, loyalty
        self.snow_spent = 0
        self.mana_spent = 0

    @property
    def is_spell(self): return self.kind in ("spell", "copy")

    def __repr__(self):
        return self.name if self.is_spell or self.name.endswith(self.kind) else f"{self.name} {self.kind}"


def can_block(blocker: Permanent, attacker: Permanent) -> bool:
    if not blocker.is_creature or blocker.tapped:
        return False
    if blocker.card.unleash and blocker.p1 > 0:
        return False
    if (blocker.card.cant_block and not blocker.abilities_suppressed) or blocker.has("cant_block_now") or blocker.has("decayed") or attacker.has("unblockable") or (blocker.auras and auras.stops_combat(blocker)):
        return False
    if any(attacker.has(keyword) and any(x.card.is_land and subtype in x.card.subtypes
                                        for x in blocker.controller.battlefield)
           for keyword, subtype in (("swampwalk", "Swamp"), ("forestwalk", "Forest"),
                                    ("mountainwalk", "Mountain"), ("islandwalk", "Island"),
                                    ("plainswalk", "Plains"))):
        return False
    if blocker.card.block_only_flying and not attacker.has("flying"):
        return False
    if attacker.has("nonbasic landwalk") and any(x.card.is_land and not is_basic_land(x.card)
                                                for x in blocker.controller.battlefield):
        return False
    if attacker.has("legendary landwalk") and any(x.card.is_land and x.card.legendary
                                                 for x in blocker.controller.battlefield):
        return False
    if protected_from(attacker, blocker):
        return False
    if attacker.has("skulk") and blocker.power > attacker.power:
        return False
    if attacker.has("flying") and not (blocker.has("flying") or blocker.has("reach")):
        return False
    if attacker.has("fear") and not (blocker.card.is_artifact or "B" in blocker.card.colors):
        return False
    if attacker.has("horsemanship") and not blocker.has("horsemanship"):
        return False
    if attacker.has("shadow") != blocker.has("shadow"):
        return False
    if attacker.has("intimidate") and not (blocker.card.is_artifact or blocker.card.colors & attacker.card.colors):
        return False
    if attacker.card.blocker_power_rel and blocker.power < attacker.power:
        return False
    if attacker.card.min_blocker_power and blocker.power < attacker.card.min_blocker_power:
        return False
    if attacker.card.max_blocker_power and blocker.power >= attacker.card.max_blocker_power:
        return False
    from ..batch1_templates import block_restricted
    return not block_restricted(blocker, attacker)



def is_basic_land(c) -> bool:
    return c.is_land and (c.basic or c.name in BASIC_MANA or c.name == "Wastes" or
                         c.name.startswith("Snow-Covered ") and c.name[len("Snow-Covered "):] in BASIC_MANA)



_TYPE_WORDS = {"creature", "land", "artifact", "enchantment", "planeswalker", "instant", "sorcery", "battle"}


def card_matches(card: CardDef, desc: str) -> bool:
    """Whether card fits a search description such as "a basic Plains card or a creature card with mana
    value 1 or less", "a Dragon card", "an instant or sorcery card" or "a card"."""
    for alt in re.split(r" or (?=an? )", desc.strip()):
        alt = re.sub(r"^an? ", "", alt)
        m = re.search(r" with mana value (\d+) or (less|greater)$", alt)
        if m:
            if (card.cmc > int(m[1])) if m[2] == "less" else (card.cmc < int(m[1])):
                continue
            alt = alt[:m.start()]
        kw = re.search(r" with (flying|reach|haste|trample|lifelink|deathtouch)$", alt)
        if kw:
            if kw[1] not in card.keywords:
                continue
            alt = alt[:kw.start()]
        words = [w for w in alt.replace(" card", "").split() if w not in ("or", "and/or")]
        ok = True
        if "token" in words:
            ok = card.is_token
            words.remove("token")
        types = [w for w in words if w in _TYPE_WORDS]
        if types and not any(t.capitalize() in card.types for t in types):
            ok = False
        if "basic" in words and not is_basic_land(card):
            ok = False
        for w in words:
            if w[0].isupper() and w not in card.subtypes and w != card.name and not \
                    (card.changeling and card.is_creature):
                ok = False
        if ok:
            return True
    return False
