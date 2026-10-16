"""A simplified two-player Magic rules engine.

Covered: lands and mana (mana creatures, Sol Ring-style sources, Treasure),
the stack with priority passing, instant-speed play (counterspells, removal and
flash permanents on the opponent's turn), triggered abilities (enters, attacks,
dies, combat damage to a player, "whenever you cast", "whenever you draw",
upkeep, end step, landfall, ward, prowess), modal spells, sagas, planeswalkers
(loyalty abilities, attacking and burning them), tokens (creatures, Treasure,
Clue, Blood), +1/+1 counters, transforming cards, adventures, flashback,
foretell, spectacle, blitz, channel, manlands and vehicles, combat with
flying/reach/haste/vigilance/defender/menace/trample/first strike/double strike/
deathtouch/lifelink, hexproof, indestructible, the London mulligan, decking, and
the seven-card hand limit.

Priority windows: after anything is put on the stack, and with an empty stack in
the declare attackers, declare blockers and end steps. Decisions the heuristic
AI doesn't make are taken by the default policies at the bottom of this file;
an AI can override each one by defining the hook of the same name (see README).
"""
from __future__ import annotations

import dataclasses
import json
import random
import re

from .cards import BASIC_MANA, COLORS, Activated, AltCost, CardDef, Effect, add_mana, make_token

TARGETED = ("any", "creature", "creature_pw", "creature_mine", "nonland_perm", "artifact", "artifact_enchantment",
            "player", "spell")


class Permanent:
    def __init__(self, card: CardDef, controller: "Player"):
        self.card = card
        self.front = card             # the card that goes to the graveyard (transformed cards)
        self.controller = controller
        self.tapped = card.enters_tapped
        self.sick = True
        self.damage = 0
        self.deathtouched = False
        self.pump_p = 0
        self.pump_t = 0
        self.counters: dict[str, int] = {}
        self.temp_kw: set[str] = set()     # until end of turn
        self.perm_kw: set[str] = set()     # from keyword counters
        self.animated = None               # Activated: a manland that is a creature until end of turn
        self.crewed = False
        self.blitz = False
        self.loyalty_used = False
        self.entered_turn = 0
        self.chosen_type = ""              # Cavern of Souls
        self.produces_now = None           # set by Game.mana_sources: the colours usable right now
        self.ability_turns: dict = {}      # activated ability index -> turn it was last activated
        self.attached_to: "Permanent | None" = None    # Equipment: the creature it is attached to
        self.spent_color = ""              # "if {U}{U} was spent to cast it"
        self.exiled_cards: list = []       # (card, owner) exiled until this leaves the battlefield
        self.warped = False
        self.was_cast = False              # "if you cast it"
        self.impending = False             # cast for its impending cost: not a creature while it has time counters

    @property
    def equipment(self):
        return [x for x in self.controller.battlefield if x.attached_to is self] if self.is_creature else []

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
        return sum(1 for x in self.controller.battlefield
                   if (x.is_creature if what == "creature" else what.capitalize() in x.card.types))

    @property
    def power(self):
        base = self.animated.power if self.animated and self.animated.kind == "animate" else (self.card.power or 0)
        return base + self.pump_p + self.p1 - self.m1 + (self.anthem[0] if self.is_creature else 0) + \
            sum(e.card.equip_bonus[0] for e in self.equipment) + self.per_bonus

    @property
    def toughness(self):
        base = self.animated.toughness if self.animated and self.animated.kind == "animate" else (self.card.toughness or 0)
        return base + self.pump_t + self.p1 - self.m1 + (self.anthem[1] if self.is_creature else 0) + \
            sum(e.card.equip_bonus[1] for e in self.equipment) + self.per_bonus

    @property
    def m1(self): return self.counters.get("-1/-1", 0)

    @property
    def loyalty(self): return self.counters.get("loyalty", 0)

    def has(self, kw):
        if kw in self.card.keywords or kw in self.temp_kw or kw in self.perm_kw:
            return True
        if self.animated and kw in self.animated.keywords:
            return True
        if any(kw in e.card.equip_keywords for e in self.equipment):
            return True
        for k, cond in self.card.cond_keywords:
            if k == kw and self.condition(cond):
                return True
        if self.card.keyword_at_counters and self.p1 >= self.card.keyword_at_counters[0]:
            return kw == self.card.keyword_at_counters[1]
        return kw == "haste" and self.blitz

    def condition(self, cond: str) -> bool:
        if cond.startswith("another:"):
            kind = cond[8:]
            return any(kind in x.card.subtypes for x in self.controller.battlefield if x is not self)
        if cond.startswith("opp_life<="):
            opp = getattr(self.controller, "opponent", None)
            return opp is not None and opp.life <= int(cond[10:])
        return False

    @property
    def is_creature(self):
        if self.impending and self.counters.get("time"):
            return False
        return self.card.is_creature or self.animated is not None or self.crewed

    @property
    def is_planeswalker(self): return self.card.is_planeswalker

    @property
    def triggers(self):
        return list(self.card.triggers) + (list(self.animated.triggers) if self.animated else [])

    @property
    def ward(self) -> int:
        if self.animated and self.animated.ward:
            return self.animated.ward
        if self.card.ward_untapped_only and self.tapped:
            return 0
        return max([self.card.ward] + [e.card.equip_ward for e in self.equipment])

    def can_attack(self):
        return (self.is_creature and not self.tapped and not self.has("defender")
                and (not self.sick or self.has("haste")))

    def can_tap_for_mana(self):
        return bool(self.card.produces or self.card.restricted_produces) and not self.tapped and \
            not (self.is_creature and self.sick)

    def __repr__(self):
        if self.is_creature:
            return f"{self.card.name}({self.power}/{self.toughness})"
        if self.is_planeswalker:
            return f"{self.card.name}[{self.loyalty}]"
        return self.card.name


class Player:
    def __init__(self, name: str, deck: list[CardDef], ai):
        self.name = name
        self.deck = deck
        self.ai = ai
        self.library: list[CardDef] = []
        self.hand: list[CardDef] = []
        self.battlefield: list[Permanent] = []
        self.graveyard: list[CardDef] = []
        self.exile: list[CardDef] = []
        self.on_adventure: list[CardDef] = []
        self.foretold: list[CardDef] = []
        self.plotted: list[CardDef] = []
        self.warp_exile: list[CardDef] = []
        self.exiled_turn: dict = {}        # card name -> turn it was plotted or exiled after warp
        self._life = 20
        self.lost = False
        self.lands_played = 0
        self.sacrificed_turn = 0
        self.milled_last: list[CardDef] = []     # the cards the last mill put into the graveyard
        self.picked_last: CardDef | None = None   # the card mill_pick returned to hand
        self.discarded_last: list[CardDef] = []
        self.mulligans = 0
        self.lost_life_turn = False
        self.perm_left_turn = False
        self.attacked_with = 0
        self.next_creature_counters = 0
        self.life_gained_turn = 0

    @property
    def life(self): return self._life

    @property
    def land_played(self) -> bool:
        """Whether this turn's land drops are used up (Icetill Explorer gives another)."""
        return self.lands_played > sum(x.card.extra_lands for x in self.battlefield)

    @land_played.setter
    def land_played(self, value):
        self.lands_played = 99 if value else 0

    @life.setter
    def life(self, value):
        if value < self._life:
            self.lost_life_turn = True
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
        self.kind = kind or ("spell" if card else "trigger")   # spell, copy, trigger, chapter, loyalty
        self.snow_spent = 0
        self.mana_spent = 0

    @property
    def is_spell(self): return self.kind in ("spell", "copy")

    def __repr__(self):
        return self.name if self.is_spell else f"{self.name} {self.kind}"


def can_block(blocker: Permanent, attacker: Permanent) -> bool:
    if not blocker.is_creature or blocker.tapped:
        return False
    if blocker.card.cant_block or attacker.has("unblockable"):
        return False
    if attacker.has("flying") and not (blocker.has("flying") or blocker.has("reach")):
        return False
    if attacker.card.min_blocker_power and blocker.power < attacker.card.min_blocker_power:
        return False
    return True


def _mana_of(s) -> frozenset:
    now = getattr(s, "produces_now", None)
    return s.card.produces if now is None else now


def find_payment(sources: list[Permanent], cost: dict):
    """Pick which mana sources to tap for a cost, or None if it can't be paid."""
    pips = [c for c in COLORS + ("C",) for _ in range(cost.get(c, 0))]
    generic = cost.get("generic", 0)
    # A source that makes several mana (Sol Ring) fills several slots.
    slots = [s for s in sources for _ in range(max(1, getattr(s.card, "mana_amount", 1)))]
    if len(pips) + generic > len(slots):
        return None
    # Mana that can only be spent on some spells goes first when it is allowed at all.
    slots = sorted(slots, key=lambda s: (not s.card.mana_restriction, s.card.token_kind == "treasure",
                                         len(_mana_of(s)), s.is_creature, -getattr(s.card, "mana_amount", 1)))
    pips.sort(key=lambda c: sum(c in _mana_of(s) for s in slots))
    used = [False] * len(slots)

    def assign(i):
        if i == len(pips):
            return True
        for j, s in enumerate(slots):
            if not used[j] and pips[i] in _mana_of(s):
                used[j] = True
                if assign(i + 1):
                    return True
                used[j] = False
        return False

    if not assign(0):
        return None
    chosen = [s for j, s in enumerate(slots) if used[j]]
    # Generic mana: first use leftover slots of sources already being tapped, then multi-mana ones.
    rest = [s for j, s in enumerate(slots) if not used[j]]
    rest.sort(key=lambda s: (s not in chosen, not s.card.mana_restriction, s.card.token_kind == "treasure",
                             -getattr(s.card, "mana_amount", 1), len(_mana_of(s)), s.is_creature))
    if len(rest) < generic:
        return None
    out = []
    for s in chosen + rest[:generic]:
        if s not in out:
            out.append(s)
    return out


def add_costs(*costs) -> dict:
    out = {"generic": 0}
    for c in costs:
        for k, v in c.items():
            out[k] = out.get(k, 0) + v
    return out


class Game:
    def __init__(self, p1: Player, p2: Player, rng: random.Random, max_turns: int = 60, log: bool = False):
        self.players = [p1, p2]       # p1 is on the play
        p1.opponent, p2.opponent = p2, p1
        self.rng = rng
        self.max_turns = max_turns
        self.turn = 0
        self.active_idx = 0
        self.winner: Player | None = None
        self.log_enabled = log
        self.events: list[str] = []
        self.step = "main1"
        self.stack: list[StackItem] = []
        self.pending: list[tuple] = []   # triggered abilities waiting to be put on the stack
        self.attackers: list[Permanent] = []
        self.attack_targets: dict = {}   # attacker -> Player or planeswalker Permanent
        self.blocks: dict = {}
        self._priority_depth = 0
        self._variants: dict = {}

    # ------------------------------------------------------------------ utils
    def log(self, msg, who: "Player | None" = None):
        if self.log_enabled:
            self.events.append(f"T{self.turn} {(who or self.players[self.active_idx]).name}: {msg}")

    def audit(self, event, **fields):
        """Machine-readable records alongside prose; seats are indices in players."""
        if self.log_enabled:
            self.events.append("AUDIT " + json.dumps(
                {"event": event, "player_turn": self.turn, **fields}, ensure_ascii=False))

    def change_life(self, player, delta, cause):
        before = player.life
        player.life += delta
        if delta > 0:
            player.life_gained_turn += delta
            self.fire(player, "gain_life")
        if delta and self.log_enabled:
            self.audit("life", seat=self.players.index(player), before=before,
                       delta=delta, after=player.life, cause=cause)

    def opponent(self, p: Player) -> Player:
        return self.players[1] if p is self.players[0] else self.players[0]

    @property
    def active(self) -> Player: return self.players[self.active_idx]

    @property
    def over(self): return any(p.lost for p in self.players)

    def hook(self, p: Player, name: str):
        """p's AI hook ``name`` if it defines one, else the default policy below."""
        return getattr(p.ai, name, None) or (lambda game, me, *a: DEFAULTS[name](game, me, *a))

    def mana_sources(self, p: Player, exclude=None, spell=None):
        """p's untapped mana sources. ``spell`` decides what restricted mana (Cavern of Souls) can
        pay for: a CardDef, "ability" for activated abilities, or None to count it (AI estimates)."""
        out = []
        stopped = self.activations_stopped()
        for perm in p.battlefield:
            if not perm.can_tap_for_mana() or perm is exclude:
                continue
            if stopped and (perm.card.is_artifact or perm.is_creature):
                continue
            produces = perm.card.produces
            if perm.card.restricted_produces and self.mana_allowed(perm, spell):
                produces = produces | perm.card.restricted_produces
            if not produces:
                continue
            perm.produces_now = produces
            out.append(perm)
        return out

    def mana_allowed(self, perm: Permanent, spell) -> bool:
        """Whether perm's restricted mana may pay for spell (see mana_sources)."""
        if spell is None:
            return True
        if not isinstance(spell, CardDef):
            return False
        r = perm.card.mana_restriction
        if r == "creature":
            return spell.is_creature
        if r == "artifact":
            return spell.is_artifact
        if r == "instant_sorcery":
            return spell.is_instant or spell.is_sorcery
        if r == "chosen_type":
            return spell.is_creature and perm.chosen_type in spell.subtypes
        if r.startswith("subtype:"):
            return bool(set(r[8:].split("|")) & spell.subtypes)
        return False

    def activations_stopped(self) -> bool:
        """Clarion Conqueror: activated abilities of artifacts, creatures and planeswalkers can't be activated."""
        return any(x.card.stops_activations for pl in self.players for x in pl.battlefield)

    def can_pay(self, p: Player, cost: dict, extra=None, spell=None) -> bool:
        sources = self.mana_sources(p, spell=spell) + ([extra] if extra else [])
        return find_payment(sources, cost) is not None

    def pay(self, p: Player, cost: dict, exclude=None, spell="ability") -> list | None:
        """Tap sources for cost (sacrificing Treasure). Returns the sources, or None if unpayable."""
        payment = find_payment(self.mana_sources(p, exclude, spell), cost)
        if payment is None:
            return None
        for s in payment:
            s.tapped = True
            if s.card.token_kind == "treasure":
                self.sacrifice(s)
        return payment

    def cost_of(self, p: Player, card: CardDef) -> dict:
        """The mana cost after cost reductions (Tolarian Terror, Ghalta)."""
        cost = dict(card.mana_cost)
        n = 0
        if card.cost_reduction == "instant_sorcery_gy":
            n = sum(c.is_instant or c.is_sorcery for c in p.graveyard)
        elif card.cost_reduction == "power":
            n = sum(max(0, c.power) for c in p.creatures)
        elif card.cost_reduction.startswith("affinity:"):
            n = sum(card_matches(x.card, "a " + card.cost_reduction[9:]) for x in p.battlefield)
        cost["generic"] = max(0, cost.get("generic", 0) - n)
        if card.extra_sac_or_pay and not self.extra_sac_candidates(p, card):
            cost["generic"] += card.extra_sac_or_pay
        return cost

    # ------------------------------------------------------- casting options
    def _variant(self, card: CardDef, kind: str, alt: AltCost | None = None) -> CardDef:
        key = (card.name, kind)
        if key not in self._variants:
            if kind == "adventure":
                v = dataclasses.replace(card.adventure)
            elif kind in ("channel", "gy_ability"):
                v = CardDef(name=f"{card.name} ({kind})", mana_cost=alt.cost, cmc=card.cmc,
                            types=frozenset({"Instant"}), spell_effects=list(alt.effects), is_ability=True)
            else:
                v = dataclasses.replace(card, name=f"{card.name} ({kind})")
                if alt is not None:
                    v.mana_cost = alt.cost
                    v.spell_effects = list(alt.effects if alt.effects is not None else card.spell_effects) + \
                        list(alt.extra)
                    v.cost_reduction = ""
            v.origin = (card, kind, alt)
            self._variants[key] = v
        return self._variants[key]

    @staticmethod
    def _hybrid_cost(cost: dict, hybrid: tuple, col: str) -> dict:
        """cost (hybrid pips counted as their first colour) with the hybrid pips paid in col where they can be."""
        out = dict(cost)
        for pair in hybrid:
            out[pair[0]] = out.get(pair[0], 0) - 1
            c = col if col in pair else pair[0]
            out[c] = out.get(c, 0) + 1
        return {k: v for k, v in out.items() if v or k == "generic"}

    def _hand_options(self, p: Player, c: CardDef) -> list[CardDef]:
        """The ways to cast hand card c: itself, or one variant per colour for "if {U}{U} was spent"
        cards, plus offspring, spree modes, and warp / evoke when the full cost can't be paid."""
        out = []
        cols = sorted({x for pair in c.hybrid for x in pair}) if c.spent_colors and c.hybrid else []
        if cols:
            out += [self._variant(c, f"spent_{col}", AltCost("spent", self._hybrid_cost(c.mana_cost, c.hybrid, col)))
                    for col in cols]
        else:
            out.append(c)
        full = any(self.can_pay(p, self.cost_of(p, v), spell=v) for v in out)
        for a in c.alt_costs:
            if a.kind == "offspring":
                out.append(self._variant(c, "offspring", AltCost("offspring", add_mana(c.mana_cost, a.cost))))
            elif a.kind == "impending" and not full:
                out.append(self._variant(c, "impending", AltCost("impending", a.cost, counters=a.counters)))
            elif a.kind in ("warp", "evoke") and not full:
                acols = sorted({x for pair in a.hybrid for x in pair}) if a.hybrid and c.spent_colors else []
                for col in acols or [""]:
                    kind = f"{a.kind}_{col}" if col else a.kind
                    out.append(self._variant(c, kind, AltCost(a.kind, self._hybrid_cost(a.cost, a.hybrid, col)
                                                              if col else a.cost)))
        for mask in range(1, 2 ** len(c.spree)):
            modes = [m for i, m in enumerate(c.spree) if mask >> i & 1]
            cost = add_mana(c.mana_cost, *(m[0] for m in modes))
            effects = [e for m in modes for e in m[1]]
            out.append(self._variant(c, f"spree_{mask}", AltCost("spree", cost, effects=effects)))
        if c.spree:
            out.remove(c)     # a spree spell needs at least one mode
        return out

    def spell_options(self, p: Player) -> list[CardDef]:
        """Every nonland spell p could cast from any zone: hand cards plus adventures, cards on an
        adventure, foretold cards, flashback, blitz, spectacle, alternative costs and channel."""
        out = []
        opp = self.opponent(p)
        for c in p.hand:
            if c.is_land:
                for a in c.alt_costs:
                    if a.kind == "channel":
                        out.append(self._variant(c, "channel", a))
                continue
            out += self._hand_options(p, c)
            if c.adventure:
                out.append(self._variant(c, "adventure"))
            for a in c.alt_costs:
                if a.kind in ("alt", "kicker") or (a.kind == "spectacle" and opp.lost_life_turn) or \
                        (a.kind == "blitz" and "hand" in a.zone):
                    out.append(self._variant(c, a.kind, a))
        out += [self._variant(c, "from_adventure") for c in p.on_adventure]
        out += [self._variant(c, "plotted", AltCost("plotted", {"generic": 0})) for c in p.plotted
                if p.exiled_turn.get(c.name, 0) < self.turn]
        out += [self._variant(c, "from_warp") for c in p.warp_exile if p.exiled_turn.get(c.name, 0) < self.turn]
        for c in p.foretold:
            a = next(a for a in c.alt_costs if a.kind == "foretell")
            out.append(self._variant(c, "foretold", a))
        for c in p.graveyard:
            for a in c.alt_costs:
                if a.kind in ("flashback", "gy_ability") or (a.kind == "blitz" and "graveyard" in a.zone):
                    out.append(self._variant(c, "blitz_gy" if a.kind == "blitz" else a.kind, a))
        return out

    def _origin(self, card: CardDef):
        return getattr(card, "origin", None) or (card, "", None)

    def _zone(self, p: Player, kind: str) -> list:
        """The zone a spell_options() variant of this kind is cast from."""
        return {"from_adventure": p.on_adventure, "foretold": p.foretold, "flashback": p.graveyard,
                "blitz_gy": p.graveyard, "gy_ability": p.graveyard, "plotted": p.plotted, "from_warp": p.warp_exile}.get(kind, p.hand)

    def _available(self, p: Player, card: CardDef) -> bool:
        base, kind, _ = self._origin(card)
        return base in self._zone(p, kind)

    def can_cast_now(self, p: Player, card: CardDef) -> bool:
        """Timing, mana, zone and (for counterspells) a spell to target."""
        if card.is_land or not self._available(p, card):
            return False
        base, kind, alt = self._origin(card)
        if kind == "spectacle" and not self.opponent(p).lost_life_turn:
            return False
        if alt is not None and alt.life and p.life <= alt.life:
            return False
        if card.extra_life_cost and p.life <= card.extra_life_cost:
            return False
        if card.extra_sacrifice and not card.extra_sac_or_pay and not self.extra_sac_candidates(p, card):
            return False
        if not card.instant_speed and not (p is self.active and self.step in ("main1", "main2")
                                           and not self.stack):
            return False
        if any(e.target == "spell" for e in card.spell_effects):
            if not any(self.can_counter(e, item, p) for e in card.spell_effects if e.kind == "counter"
                       for item in self.stack):
                return False
        return self.can_pay(p, self.cost_of(p, card), spell=card)

    # ---------------------------------------------------------------- targets
    def targetable(self, obj, by: Player) -> bool:
        """Whether ``by`` may target obj (hexproof, still on the battlefield / stack)."""
        if isinstance(obj, Permanent):
            return obj in obj.controller.battlefield and not (obj.has("hexproof") and obj.controller is not by)
        if isinstance(obj, StackItem):
            return obj in self.stack
        return isinstance(obj, Player)

    def passes_filter(self, eff: Effect, perm: Permanent, by: Player) -> bool:
        f = eff.filter
        if f.startswith("max_cmc:"):
            limit = int(f.split(":")[1])
            if by.perm_left_turn and eff.kind == "destroy":
                limit = max(limit, 4)  # Fatal Push's revolt
            return perm.card.cmc <= limit
        if f == "plains":
            return perm.card.cmc <= sum(1 for x in by.battlefield if x.card.name.endswith("Plains"))
        if f == "tapped":
            return perm.tapped
        if f == "attacking_blocking":
            return perm in self.attackers or any(perm in bl for bl in self.blocks.values())
        if f == "nonartifact":
            return not perm.card.is_artifact
        if f == "nonflying":
            return not perm.has("flying")
        if f == "untapped":
            return not perm.tapped
        if f == "opp":
            return perm.controller is not by
        if f == "stunned":
            return bool(perm.counters.get("stun"))
        if f.startswith("max_power:"):
            return perm.power <= int(f[10:])
        return True

    def legal_targets(self, p: Player, eff: Effect) -> list:
        everything = [x for pl in self.players for x in pl.battlefield if self.targetable(x, p)]
        creatures = [c for c in everything if c.is_creature and self.passes_filter(eff, c, p)]
        t = eff.target
        if t == "creature":
            return creatures
        if t == "creature_pw":
            return creatures + [x for x in everything if x.is_planeswalker]
        if t == "creature_mine":
            return [c for c in creatures if c.controller is p]
        if t == "nonland_perm":
            return [x for x in everything if (not x.card.is_land or x.is_creature) and self.passes_filter(eff, x, p)]
        if t == "artifact":
            return [x for x in everything if x.card.is_artifact]
        if t == "artifact_enchantment":
            return [x for x in everything if (x.card.is_artifact or "Enchantment" in x.card.types)
                    and self.passes_filter(eff, x, p)]
        if t == "any":
            return creatures + [x for x in everything if x.is_planeswalker] + list(self.players)
        if t == "player":
            return list(self.players)
        if t == "spell":
            return [i for i in self.stack if self.can_counter(eff, i, p)]
        return []

    def legal_target(self, p: Player, eff: Effect, tgt) -> bool:
        if tgt is None or not self.targetable(tgt, p):
            return False
        if isinstance(tgt, Permanent):
            return self.passes_filter(eff, tgt, p)
        return True

    def can_counter(self, eff: Effect, item: StackItem, by: Player | None = None) -> bool:
        if eff.kind not in ("counter", "bounce_spell") or not item.is_spell or item not in self.stack:
            return False
        if by is not None and item.controller is by:
            return False
        card = item.card
        if eff.filter == "creature" and not card.is_creature:
            return False
        if eff.filter == "noncreature" and card.is_creature:
            return False
        if eff.filter == "instant_sorcery" and not (card.is_instant or card.is_sorcery):
            return False
        if eff.filter.startswith("cmc:") and card.cmc != int(eff.filter[4:]):
            return False
        return True

    def counterable(self, item: StackItem) -> bool:
        if not item.is_spell or item.card.uncounterable or getattr(item, "uncounterable", False):
            return False
        if item.card.is_instant or item.card.is_sorcery:
            if any(perm.card.protects_spells for perm in item.controller.battlefield):
                return False
        return True

    def auto_targets(self, p: Player, effects: list, source=None) -> list:
        """Targets for effects nobody chose targets for (triggers, modes, copies)."""
        out = []
        for e in effects:
            if e.target not in TARGETED:
                out.append(None)
                continue
            tgt = self.hook(p, "choose_target")(self, p, e)
            if tgt is None or not self.legal_target(p, e, tgt):
                tgt = default_choose_target(self, p, e)
            out.append(tgt)
        return out

    # --------------------------------------------------------------- setup
    def draw(self, p: Player, n: int = 1):
        for _ in range(n):
            if not p.library:
                if not p.lost:
                    self.audit("loss", seat=self.players.index(p), cause="drew from empty library")
                p.lost = True
                self.log("loses by drawing from an empty library", p)
                return
            p.hand.append(p.library.pop())
            self.fire(p, "you_draw")
            opp = self.opponent(p)
            self.fire(opp, "opp_draw", context=p)

    def setup(self):
        self.audit("start", players=[p.name for p in self.players], first_player=0,
                   life=[p.life for p in self.players], turn_unit="player-turn")
        for p in self.players:
            while True:
                p.library = list(p.deck)
                self.rng.shuffle(p.library)
                p.hand = []
                self.draw(p, 7)
                if p.mulligans >= 2 or p.ai.keep_hand(p.hand, p.mulligans):
                    break
                self.audit("mulligan", seat=self.players.index(p),
                           hand=[c.name for c in p.hand], mulligans=p.mulligans + 1)
                p.mulligans += 1
            for card in p.ai.cards_to_bottom(p.hand, p.mulligans):
                p.hand.remove(card)
                p.library.insert(0, card)
            self.audit("keep", seat=self.players.index(p), mulligans=p.mulligans,
                       hand=[c.name for c in p.hand])
        for p in self.players:
            for card in [c for c in p.hand if c.leyline]:
                p.hand.remove(card)
                self.log(f"begins the game with {card.name} on the battlefield", p)
                self.enter_battlefield(p, card)
        self.pending = []   # opening hands don't trigger "whenever you draw"

    # ----------------------------------------------------------- game loop
    def play(self) -> Player | None:
        self.setup()
        while not self.over and self.turn < self.max_turns:
            self.turn += 1
            self.take_turn(self.players[self.active_idx])
            self.active_idx = 1 - self.active_idx
        losers = [p for p in self.players if p.lost]
        if len(losers) == 1:
            self.winner = self.opponent(losers[0])
        self.log(f"game over, winner: {self.winner}")
        self.audit("result", winner=self.players.index(self.winner) if self.winner else None,
                   life=[p.life for p in self.players], lost=[p.lost for p in self.players],
                   reason="loss" if losers else "player-turn cap", player_turns=self.turn)
        return self.winner

    def main_phase(self, p: Player):
        p.ai.main_phase(self, p)
        if not self.over:
            self.hook(p, "use_abilities")(self, p)

    def take_turn(self, p: Player):
        opp = self.opponent(p)
        for pl in self.players:
            pl.lost_life_turn = pl.perm_left_turn = False
            pl.life_gained_turn = 0
            pl.attacked_with = 0
        self.step = "untap"
        for perm in p.battlefield:
            if perm.tapped and perm.counters.get("stun"):
                perm.counters["stun"] -= 1   # a stun counter is removed instead of untapping
            else:
                perm.tapped = False
            perm.sick = False
            perm.loyalty_used = False
        p.land_played = False
        p.sacrificed_turn = 0
        self.step = "upkeep"
        self.fire(p, "upkeep")
        self.settle()
        if self.over:
            return
        self.step = "draw"
        if self.turn > 1:
            self.draw(p)
            self.settle()
            if self.over:
                return
        self.step = "main1"
        for perm in list(p.battlefield):
            if perm.card.is_saga:
                self.add_lore(perm)
        self.settle()
        if self.over:
            return
        self.main_phase(p)
        if self.over:
            return
        self.combat(p, opp)
        if self.over:
            return
        self.step = "main2"
        self.main_phase(p)
        if self.over:
            return
        self.step = "end_step"
        self.fire(p, "end_step")
        for perm in list(p.battlefield):
            if perm.impending and perm.counters.get("time"):
                perm.counters["time"] -= 1
            if perm.blitz:
                self.log(f"sacrifices blitzed {perm.card.name}", p)
                self.sacrifice(perm)
            if perm.warped and self.leave_battlefield(perm, "exile"):
                p.exile.remove(perm.front)
                p.warp_exile.append(perm.front)
                p.exiled_turn[perm.front.name] = self.turn
                self.log(f"exiles warped {perm.card.name}", p)
        self.run_priority(until_empty_stack=False)
        if self.over:
            return
        self.step = "cleanup"
        while len(p.hand) > 7:
            card = p.ai.choose_discard(self, p)
            p.hand.remove(card)
            p.graveyard.append(card)
        for perm in p.battlefield + opp.battlefield:
            perm.damage = 0
            perm.deathtouched = False
            perm.pump_p = perm.pump_t = 0
            perm.temp_kw.clear()
            if not (perm.animated and perm.animated.text in ("earthbend", "permanent")):
                perm.animated = None
            perm.crewed = False
        p.next_creature_counters = 0
        self.state_based_actions()

    # ------------------------------------------------------- stack/priority
    def settle(self):
        """Outside a priority loop: let players respond to whatever was just put on the
        stack (or triggered) and resolve until the stack is empty."""
        if self._priority_depth == 0 and (self.stack or self.pending) and not self.over:
            self.run_priority(until_empty_stack=True)

    def run_priority(self, until_empty_stack: bool = True):
        """Pass priority back and forth, starting with the active player. When both pass in
        succession the top of the stack resolves. Ends when the stack is empty and, for an
        empty-stack window (until_empty_stack=False), both players have passed."""
        self._priority_depth += 1
        try:
            holder, passes = self.active, 0
            while not self.over:
                self.state_based_actions()
                if self.flush_triggers():
                    holder, passes = self.active, 0
                if until_empty_stack and not self.stack:
                    break
                if passes >= 2:
                    if not self.stack:
                        break
                    self.resolve_top()
                    holder, passes = self.active, 0
                    continue
                if self.give_priority(holder):
                    passes = 0
                else:
                    passes += 1
                    holder = self.opponent(holder)
        finally:
            self._priority_depth -= 1

    def give_priority(self, p: Player) -> bool:
        """Ask p's AI what to do with priority. Returns True if it did something. When an AI
        with its own ``respond`` passes, ``respond_extras`` covers what it may not know about
        (instant-speed loyalty abilities, Clues, flashback / adventure / modal instants)."""
        action = self.hook(p, "respond")(self, p)
        if not action and getattr(p.ai, "respond", None):
            action = self.hook(p, "respond_extras")(self, p)
        return self.do_action(p, action)

    def do_action(self, p: Player, action) -> bool:
        """Carry out ``(card, targets)`` (cast a spell) or ``("loyalty", permanent, index, targets)``
        or ``("activate", permanent, what)`` with what in clue/blood/sac_debuff/animate/barrens."""
        if not action:
            return False
        if action[0] == "loyalty":
            return self.activate_loyalty(p, action[1], action[2], action[3] if len(action) > 3 else None)
        if action[0] == "activate":
            return self.activate(p, action[1], action[2], *action[3:])
        card, targets = action
        if not self.can_cast_now(p, card):
            return False
        return self.cast(p, card, targets)

    def queue_trigger(self, controller: Player, effects: list, source: Permanent | None = None,
                      name: str = "", context=None, targets: list | None = None, kind: str = "trigger",
                      modes=None):
        self.pending.append((controller, effects, source, name, context, targets, kind, modes))

    def fire(self, p: Player, event: str, source: Permanent | None = None, context=None, subject=None):
        """Queue the triggers for event: of ``source`` if given, else of p's permanents."""
        perms = [source] if source is not None else list(p.battlefield)
        for perm in perms:
            for i, trig in enumerate(perm.triggers):
                if trig.event != event:
                    continue
                if event == "permanent_enters":
                    me_ok, other, desc = trig.filter.split("|", 2)
                    if subject is perm and me_ok == "self":
                        pass
                    elif subject is perm and other == "other":
                        continue
                    elif not card_matches(subject.card, "a " + re.sub(r",? or (?!greater)|, ", " or a ", desc)):
                        continue
                if trig.filter.startswith("with:") and \
                        not any(trig.filter[5:] in a.card.subtypes for a in self.attackers):
                    continue
                if trig.once:
                    if perm.ability_turns.get(("trigger", i)) == self.turn:
                        continue
                    perm.ability_turns[("trigger", i)] = self.turn
                if trig.filter.startswith("cmc<=") and subject is not None and \
                        subject.cmc > int(trig.filter[5:]):
                    continue
                if trig.filter == "greater_power" and (subject is None or subject is perm
                                                       or subject.power <= perm.power):
                    continue
                effects = trig.effects
                if subject is not None and any(e.data.get("subject_power") for e in effects):
                    effects = [dataclasses.replace(e, amount=max(0, subject.power)) if e.data.get("subject_power")
                               else e for e in effects]
                self.queue_trigger(perm.controller, effects, perm, perm.card.name, context, modes=trig.modes)
        if source is None:      # abilities that trigger from the graveyard (Bloodghast)
            for card in list(p.graveyard):
                for trig in card.gy_triggers:
                    if trig.event == event:
                        self.queue_trigger(p, trig.effects, None, card.name, context=card)

    def flush_triggers(self) -> bool:
        """Put pending triggers on the stack, active player's first (so they resolve last)."""
        if not self.pending:
            return False
        pending, self.pending = self.pending, []
        order = [self.active, self.opponent(self.active)]
        pending.sort(key=lambda t: order.index(t[0]))
        for controller, effects, source, name, context, targets, kind, modes in pending:
            if modes:
                chosen = self.hook(controller, "choose_modes")(self, controller, modes, 1, True)
                if not chosen:
                    continue
                effects = [e for i in chosen for e in modes[i]]
            if targets is None:
                targets = self.auto_targets(controller, effects, source)
            item = StackItem(controller, effects, targets, source=source, name=name, context=context, kind=kind)
            self.stack.append(item)
            self.log(f"{item} goes on the stack" + (f" -> {targets}" if any(targets) else ""), controller)
            self.check_ward(item)
        return True

    def check_ward(self, item: StackItem):
        for tgt in item.targets:
            if isinstance(tgt, Permanent) and tgt.controller is not item.controller:
                if tgt.ward:
                    self.queue_trigger(tgt.controller, [Effect("counter", tgt.ward, target="spell")], tgt,
                                       f"{tgt.card.name} ward", targets=[item])
                elif tgt.card.ward_life:
                    self.queue_trigger(tgt.controller, [Effect("counter", 1, target="spell",
                                                               data={"life": tgt.card.ward_life})], tgt,
                                       f"{tgt.card.name} ward", targets=[item])
                elif tgt.card.ward_discard:
                    self.queue_trigger(tgt.controller, [Effect("counter", 1, target="spell",
                                                               data={"discard": True})], tgt,
                                       f"{tgt.card.name} ward", targets=[item])
                if item.is_spell:
                    self.fire(tgt.controller, "targeted_by_spell", tgt, context=item.controller)

    def resolve_top(self):
        item = self.stack.pop()
        p = item.controller
        if item.is_spell and item.card.is_permanent:
            self.log(f"{item.card.name} resolves", p)
            base, kind, _ = self._origin(item.card)
            if kind.startswith(("spent_", "evoke_")):
                self._spent = kind.split("_")[1]
            perm = self.enter_battlefield(p, base, x=getattr(item, "x", 0))
            self._spent = ""
            if kind in ("blitz", "blitz_gy"):
                perm.blitz = True
            if kind == "warp":
                perm.warped = True
            perm.was_cast = True
            if kind == "impending":
                perm.impending = True
                perm.counters["time"] = next(a.counters for a in base.alt_costs if a.kind == "impending")
            if kind == "offspring":
                token = dataclasses.replace(base, name=f"{base.name} token", power=1, toughness=1, is_token=True,
                                            alt_costs=[])
                self.queue_trigger(p, [Effect("token_copy", data={"card": token})], perm, f"{base.name} offspring")
            if kind.startswith("evoke"):
                self.log(f"sacrifices evoked {base.name}", p)
                self.sacrifice(perm)
            if perm.is_creature and p.next_creature_counters:
                perm.counters["+1/+1"] = perm.p1 + p.next_creature_counters
                p.next_creature_counters = 0
            return
        targeted = [(e, t) for e, t in zip(item.effects, item.targets) if e.target in TARGETED]
        if targeted and all(not self.legal_target(p, e, t) for e, t in targeted):
            self.log(f"{item} fizzles (no legal target)", p)
        else:
            self.log(f"{item} resolves", p)
            prev = None
            for eff, tgt in zip(item.effects, item.targets):
                if eff.target in TARGETED:
                    if not self.legal_target(p, eff, tgt):
                        prev = None
                        continue
                    prev = tgt
                elif eff.target == "prev":
                    tgt = prev
                if not self.check_cond(p, eff, item, prev):
                    continue
                self.resolve(p, eff, tgt, item, prev)
                if self.over:
                    break
        if item.kind == "chapter":
            self.finish_chapter(item.source)
        if item.is_spell:
            self.to_graveyard_after_resolving(item)
        self.state_based_actions()

    def to_graveyard_after_resolving(self, item: StackItem):
        if item.kind == "copy":
            return
        base, kind, _ = self._origin(item.card)
        owner = item.controller
        if kind == "adventure":
            owner.on_adventure.append(base)
        elif kind == "flashback":
            owner.exile.append(base)
        elif kind != "channel":
            owner.graveyard.append(base)

    def check_cond(self, p: Player, eff: Effect, item: StackItem, prev) -> bool:
        c = eff.cond
        if not c:
            return True
        if c == "attacked2":
            return p.attacked_with >= 2
        if c == "not_attacked2":
            return p.attacked_with < 2
        if c == "counters3":
            return item.source is not None and max(item.source.counters.values(), default=0) >= 3
        if c == "target_player":
            return isinstance(prev, Player)
        if c == "modified":
            return any(x.counters.get("+1/+1") for x in p.creatures)
        if c == "opp_lost_life":
            return self.opponent(p).lost_life_turn
        if c == "gained_life":
            return p.life_gained_turn > 0
        if c.startswith("gained_life>="):
            return p.life_gained_turn >= int(c[13:])
        if c == "gained_and_lost":
            return p.life_gained_turn > 0 and p.lost_life_turn
        if c == "cast":
            return item.source is not None and item.source.was_cast
        if c == "squirrel":
            return any("Squirrel" in x.card.subtypes for x in p.battlefield) or \
                (p.picked_last is not None and "Squirrel" in p.picked_last.subtypes)
        if c.startswith("counters:"):
            name, n = c[9:].split(">=")
            return item.source is not None and item.source.counters.get(name, 0) >= int(n)
        if c.startswith("spent:"):
            return item.source is not None and getattr(item.source, "spent_color", "") == c[6:]
        return True

    # -------------------------------------------------------------- actions
    def play_land(self, p: Player, card: CardDef, back: bool = False):
        """Play a land from hand; with back=True, a modal double-faced card's land face."""
        face = card.land_face if back else card
        assert face is not None and face.is_land and not p.land_played
        if card in p.hand:
            p.hand.remove(card)
        else:   # "You may play lands from your graveyard."
            assert any(x.card.lands_from_gy for x in p.battlefield)
            p.graveyard.remove(card)
        p.lands_played += 1
        self.log(f"plays {face.name}", p)
        perm = self.enter_battlefield(p, face)
        perm.front = card    # the whole card goes to the graveyard
        self.settle()

    def cast(self, p: Player, card: CardDef, targets: list | None = None) -> bool:
        """Pay for card and put it on the stack. ``card`` may be a hand card or one of
        spell_options() (adventure, flashback, ...). Outside a priority loop (an AI's main
        phase) the stack is then resolved, with the opponent able to respond, before
        returning. Timing isn't checked here; AIs should use can_cast_now."""
        base, kind, alt = self._origin(card)
        if not self._available(p, card):
            return False
        cost = self.cost_of(p, card)
        payment = self.pay(p, cost, spell=card)
        if payment is None:
            return False
        x = 0
        if "X" in card.mana_cost:     # X: as much as the remaining mana allows
            while x < 20 and find_payment(self.mana_sources(p, spell=card), {"generic": x + 1}) is not None:
                x += 1
            if x:
                payment += self.pay(p, {"generic": x}, spell=card)
        if alt is not None and alt.life:
            self.change_life(p, -alt.life, f"{card.name}: alternative cost")
        if card.extra_life_cost:
            self.change_life(p, -card.extra_life_cost, f"{card.name}: additional cost")
        if card.extra_sacrifice and self.extra_sac_candidates(p, card):
            victim = self.extra_sac_candidates(p, card)[0]
            self.log(f"sacrifices {victim.card.name} for {card.name}", p)
            self.sacrifice(victim)
        self._zone(p, kind).remove(base)
        if kind == "channel":
            p.graveyard.append(base)
        elif kind == "gy_ability":
            p.exile.append(base)
        effects = [] if card.is_permanent else list(card.spell_effects)
        targets = list(targets or [])
        targets += [None] * (len(effects) - len(targets))
        missing = [i for i, e in enumerate(effects) if e.target in TARGETED and targets[i] is None]
        if missing:   # targets the AI didn't pick (effects it doesn't know about)
            filled = self.auto_targets(p, [effects[i] for i in missing])
            for i, t in zip(missing, filled):
                targets[i] = t
        if card.modes:
            chosen = self.hook(p, "choose_modes")(self, p, card.modes, card.modes_choose, False)
            mode_effects = [e for i in chosen for e in card.modes[i]]
            effects = mode_effects + effects
            targets = self.auto_targets(p, mode_effects) + targets
        item = StackItem(p, effects, targets, card=card, kind="spell")
        item.snow_spent = sum(1 for s in payment if s.card.snow)
        item.x = x
        item.uncounterable = any(s.card.mana_restriction == "chosen_type" and self.mana_allowed(s, card)
                                 for s in payment)
        item.mana_spent = sum(v for k, v in cost.items() if k != "X")
        if card.is_ability:
            item.kind = "channel"
            item.card = None
            item.name = card.name
        self.stack.append(item)
        self.log(f"casts {card.name}" + (f" -> {targets}" if any(targets) else ""), p)
        if not card.is_ability:
            for perm in list(p.battlefield):
                for trig in perm.triggers:
                    flt = trig.filter
                    if flt.startswith("spell:") and not (flt[6:] in card.subtypes or
                                                         flt[6:].capitalize() in card.types):
                        continue
                    if (trig.event == "cast_spell" or
                            (trig.event == "cast_noncreature" and not card.is_creature) or
                            (trig.event == "cast_instant_sorcery" and (card.is_instant or card.is_sorcery))):
                        self.queue_trigger(p, trig.effects, perm, perm.card.name, modes=trig.modes)
            for pl in self.players:
                self.fire(pl, "any_cast", context=p, subject=card)
        self.check_ward(item)
        self.settle()
        return True

    def activate_loyalty(self, p: Player, pw: Permanent, idx: int, targets=None) -> bool:
        if pw not in p.battlefield or pw.loyalty_used or idx >= len(pw.card.loyalty_abilities):
            return False
        if self.activations_stopped():
            return False
        cost, effects = pw.card.loyalty_abilities[idx]
        if pw.loyalty + cost < 0:
            return False
        instant_ok = pw.card.pw_instant_on_entry and pw.entered_turn == self.turn
        if not instant_ok and not (p is self.active and self.step in ("main1", "main2") and not self.stack):
            return False
        pw.counters["loyalty"] = pw.loyalty + cost
        pw.loyalty_used = True
        if targets is None:
            targets = self.auto_targets(p, effects, pw)
        item = StackItem(p, list(effects), list(targets), source=pw, name=f"{pw.card.name} [{cost:+d}]",
                         kind="loyalty")
        self.stack.append(item)
        self.log(f"activates {item}" + (f" -> {targets}" if any(targets) else ""), p)
        self.check_ward(item)
        self.state_based_actions()
        self.settle()
        return True

    def activate(self, p: Player, perm: Permanent, what: str, target=None) -> bool:
        """Non-loyalty activated abilities: Clue, Blood, Bloodtithe Harvester, manlands, crew, and
        "ability:N" for the card's Nth activated ability (see activate_ability)."""
        if perm not in p.battlefield:
            return False
        if what.startswith("ability:"):
            return self.activate_ability(p, perm, int(what[8:]))
        if what.startswith("equip"):
            return self.equip(p, perm, target)
        if self.activations_stopped() and (perm.card.is_artifact or perm.is_creature):
            return False
        if what == "clue":
            if self.pay(p, {"generic": 2}) is None:
                return False
            self.leave_battlefield(perm, "graveyard")
            self.log("cracks a Clue", p)
            self.draw(p)
        elif what == "blood":
            if not p.hand or self.pay(p, {"generic": 1}, exclude=perm) is None:
                return False
            card = p.ai.choose_discard(self, p)
            p.hand.remove(card)
            p.graveyard.append(card)
            self.leave_battlefield(perm, "graveyard")
            self.log(f"uses a Blood token, discarding {card.name}", p)
            self.draw(p)
        elif what == "sac_debuff":
            blood = sum(1 for x in p.battlefield if x.card.token_kind == "blood")
            effect = Effect("debuff_one", 2 * blood, 2 * blood, target="creature")
            tgt = default_choose_target(self, p, effect)
            if not blood or perm.tapped or perm.sick or tgt is None:
                return False
            perm.tapped = True
            self.leave_battlefield(perm, "graveyard")
            item = StackItem(p, [effect], [tgt], source=perm, name=f"{perm.card.name} ability", kind="ability")
            self.stack.append(item)
            self.check_ward(item)
        elif what in ("animate", "barrens"):
            act = next((a for a in perm.card.activated if a.kind == what), None)
            if act is None or self.pay(p, act.cost, exclude=perm) is None:
                return False
            if what == "barrens":
                perm.counters["+1/+1"] = perm.p1 + 2
            perm.animated = act
            self.log(f"animates {perm}", p)
        elif what == "crew":
            crew = self.hook(p, "choose_crew")(self, p, perm)
            if not crew:
                return False
            for c in crew:
                c.tapped = True
            perm.crewed = True
            self.log(f"crews {perm.card.name} with {crew}", p)
        else:
            return False
        self.settle()
        return True

    def equip_cost(self, equipment: Permanent, creature: Permanent) -> dict:
        cost = dict(equipment.card.equip_cost or {})
        cost["generic"] = max(0, cost.get("generic", 0) - creature.card.equip_discount)
        return cost

    def equip(self, p: Player, equipment: Permanent, creature: Permanent | None = None) -> bool:
        """Equip {N}: attach equipment to a creature p controls, at sorcery speed."""
        if equipment not in p.battlefield or equipment.card.equip_cost is None:
            return False
        if not (p is self.active and self.step in ("main1", "main2") and not self.stack):
            return False
        if self.activations_stopped():
            return False
        if creature is None:
            creature = self.hook(p, "choose_equip_target")(self, p, equipment)
        if creature is None or creature not in p.battlefield or not creature.is_creature or \
                creature is equipment.attached_to:
            return False
        if self.pay(p, self.equip_cost(equipment, creature)) is None:
            return False
        equipment.attached_to = creature
        self.log(f"equips {equipment.card.name} to {creature.card.name}", p)
        return True

    def exile_until_leaves(self, src: Permanent, perms: list):
        """Exile perms until src leaves the battlefield (Seam Rip, Pinnacle Starcage)."""
        for x in perms:
            owner, card, token = x.controller, x.front, x.front.is_token
            if self.leave_battlefield(x, "exile"):
                self.log(f"exiles {x.card.name} until {src.card.name} leaves", src.controller)
                if not token:
                    src.exiled_cards.append((card, owner))

    def sacrifice_candidates(self, p: Player, perm: Permanent, what: str) -> list:
        """Permanents p could sacrifice to pay "Sacrifice a/another WHAT" for perm's ability."""
        other = what.startswith("other ")
        what = what[6:] if other else what
        out = []
        for x in p.battlefield:
            if other and x is perm:
                continue
            kinds = {"token": x.card.is_token, "artifact": x.card.is_artifact, "creature": x.is_creature,
                     "treasure": x.card.token_kind == "treasure", "food": x.card.token_kind == "food",
                     "land": x.card.is_land, "enchantment": "Enchantment" in x.card.types}
            if any(kinds.get(k.strip()) for k in what.split(" or ")):
                out.append(x)
        return sorted(out, key=perm_value)

    def can_activate(self, p: Player, perm: Permanent, idx: int) -> bool:
        """Whether perm's activated ability idx (kind "ability") can be activated now."""
        acts = perm.card.activated
        if perm not in p.battlefield or idx >= len(acts) or acts[idx].kind != "ability":
            return False
        act, c = acts[idx], acts[idx].extra_costs
        if self.activations_stopped() and (perm.card.is_artifact or perm.is_creature or perm.is_planeswalker):
            return False
        if c.get("tap") and (perm.tapped or (perm.is_creature and perm.sick)):
            return False
        if act.sorcery and not (p is self.active and self.step in ("main1", "main2") and not self.stack):
            return False
        if act.once and perm.ability_turns.get(idx) == self.turn:
            return False
        if c.get("life") and p.life <= c["life"]:
            return False
        if c.get("discard") and len(p.hand) < c["discard"]:
            return False
        if c.get("remove_counter") and not perm.counters.get(c["remove_counter"]):
            return False
        if c.get("sacrifice") and not self.sacrifice_candidates(p, perm, c["sacrifice"]):
            return False
        return find_payment(self.mana_sources(p, perm if c.get("tap") else None, "ability"), act.cost) is not None

    def activate_ability(self, p: Player, perm: Permanent, idx: int, targets=None) -> bool:
        """Pay for and put on the stack a general activated ability ("{2}, {T}: Draw a card.")."""
        if not self.can_activate(p, perm, idx):
            return False
        act, c = perm.card.activated[idx], perm.card.activated[idx].extra_costs
        if self.pay(p, act.cost, exclude=perm if c.get("tap") else None) is None:
            return False
        perm.ability_turns[idx] = self.turn
        if c.get("tap"):
            perm.tapped = True
        if c.get("life"):
            self.change_life(p, -c["life"], f"{perm.card.name}: ability cost")
        for _ in range(c.get("discard", 0)):
            card = p.ai.choose_discard(self, p)
            p.hand.remove(card)
            p.graveyard.append(card)
            self.log(f"discards {card.name}", p)
        if c.get("remove_counter"):
            perm.counters[c["remove_counter"]] -= 1
        if c.get("sacrifice"):
            victim = self.sacrifice_candidates(p, perm, c["sacrifice"])[0]
            self.log(f"sacrifices {victim.card.name}", p)
            self.sacrifice(victim)
        if c.get("sac_self"):
            self.sacrifice(perm)
        elif c.get("exile_self"):
            self.leave_battlefield(perm, "exile")
        if targets is None:
            targets = self.auto_targets(p, act.effects, perm)
        item = StackItem(p, list(act.effects), list(targets), source=perm, name=f"{perm.card.name} ability",
                         kind="ability")
        self.stack.append(item)
        self.log(f"activates {item}" + (f" -> {targets}" if any(targets) else ""), p)
        self.check_ward(item)
        self.settle()
        return True

    def plot(self, p: Player, card: CardDef) -> bool:
        """Plot: pay the plot cost and exile the card from hand, to cast free on a later turn."""
        alt = next((a for a in card.alt_costs if a.kind == "plot"), None)
        if card not in p.hand or alt is None or not (p is self.active and self.step in ("main1", "main2")
                                                     and not self.stack):
            return False
        if self.pay(p, alt.cost) is None:
            return False
        p.hand.remove(card)
        p.plotted.append(card)
        p.exiled_turn[card.name] = self.turn
        self.log(f"plots {card.name}", p)
        return True

    def foretell(self, p: Player, card: CardDef) -> bool:
        if card not in p.hand or not any(a.kind == "foretell" for a in card.alt_costs):
            return False
        if self.pay(p, {"generic": 2}) is None:
            return False
        p.hand.remove(card)
        p.foretold.append(card)
        self.log("foretells a card", p)
        return True

    def enter_battlefield(self, p: Player, card: CardDef, tapped_attacking: bool = False, x: int = 0) -> Permanent:
        perm = Permanent(card, p)
        perm.entered_turn = self.turn
        perm.spent_color = getattr(self, "_spent", "")
        others = sum(x.card.is_land for x in p.battlefield)
        cond = card.tapped_condition
        if cond == "unless_2_lands":
            perm.tapped = others < 2
        elif cond == "if_2_lands":
            perm.tapped = others >= 2
        elif cond == "unless_le_2_lands":
            perm.tapped = others > 2
        elif cond == "after_turn3":
            perm.tapped = self.turn > 6    # each player's first three turns are game turns 1-6
        elif cond == "not_your_turn":
            perm.tapped = p is not self.active
        elif cond.startswith("unless_control:"):
            kinds = cond.split(":", 1)[1].split("|")
            perm.tapped = not any(is_basic_land(x.card) if k == "basic" else k in x.card.subtypes
                                  for x in p.battlefield for k in kinds)
        elif cond.startswith("behold:"):
            kind = cond.split(":", 1)[1]
            perm.tapped = not any(kind in c.subtypes for c in [x.card for x in p.battlefield] + p.hand)
        elif cond == "shock":
            if self.hook(p, "pay_shock")(self, p, card):
                self.change_life(p, -2, f"{card.name}: shock land cost")
            else:
                perm.tapped = True
        if card.choose_type == "creature":
            types: dict = {}
            for c in p.deck:
                if c.is_creature:
                    for t in c.subtypes:
                        types[t] = types.get(t, 0) + 1
            perm.chosen_type = max(types, key=types.get, default="")
        elif card.choose_type == "basic_land":
            perm.card = dataclasses.replace(card, produces=frozenset({choose_color(self, p)}))
        if card.loyalty:
            perm.counters["loyalty"] = card.loyalty
        if card.etb_counters:
            n = x if card.etb_counters == -1 else card.etb_counters
            if n:
                perm.counters["+1/+1"] = n
        p.battlefield.append(perm)
        if tapped_attacking:
            perm.tapped = True
            self.attackers.append(perm)
            self.attack_targets[perm] = self.opponent(p)
        if card.etb_effects and not any(t.event == "etb" for t in card.triggers):
            self.queue_trigger(p, card.etb_effects, perm, card.name)  # a hand-built CardDef
        else:
            self.fire(p, "etb", perm)
        if card.is_saga:
            self.add_lore(perm)
        if perm.is_creature:
            self.fire(p, "other_creature_enters", subject=perm)
        self.fire(p, "permanent_enters", subject=perm)
        if card.is_land:
            self.fire(p, "land_enters")
        self.state_based_actions()
        return perm

    def add_lore(self, saga: Permanent):
        n = saga.counters.get("lore", 0) + 1
        saga.counters["lore"] = n
        if n <= len(saga.card.chapters):
            effects = saga.card.chapters[n - 1]
            self.queue_trigger(saga.controller, effects, saga, f"{saga.card.name} chapter {n}", kind="chapter")

    def finish_chapter(self, saga: Permanent):
        if saga in saga.controller.battlefield and saga.card.is_saga and \
                saga.counters.get("lore", 0) >= len(saga.card.chapters):
            self.log(f"{saga.card.name} is sacrificed", saga.controller)
            self.leave_battlefield(saga, "graveyard")

    def create_token(self, p: Player, eff: Effect, n: int | None = None):
        d = eff.data
        for _ in range(n if n is not None else eff.amount):
            card = make_token(d.get("name", ""), d.get("power", 0), d.get("toughness", 0), d.get("keywords", ()),
                              d.get("triggers"), d.get("kind", ""), d.get("artifact", False), d.get("pt_per", ""))
            self.enter_battlefield(p, card, tapped_attacking=d.get("attacking", False) and self.step in
                                   ("declare_attackers", "declare_blockers"))
        self.log(f"creates {eff.amount} {d.get('kind') or d.get('name')} token(s)", p)

    def transform(self, perm: Permanent):
        back = perm.card.back
        if back is None or perm not in perm.controller.battlefield:
            return
        self.log(f"{perm.card.name} transforms into {back.name}", perm.controller)
        was_saga = perm.card.is_saga
        perm.card = back
        perm.counters.pop("lore", None)
        if was_saga:   # exiled and returned: a new object
            perm.sick = True
            perm.entered_turn = self.turn
            self.fire(perm.controller, "etb", perm)

    def resolve(self, p: Player, eff: Effect, target, item: StackItem | None = None, prev=None):
        opp = self.opponent(p)
        if eff.target == "self" and item is not None:
            target = item.source
        if eff.target == "that_player" and item is not None:
            target = item.context
        if eff.target == "that_controller":
            target = prev.controller if isinstance(prev, Permanent) else prev
        k = eff.kind
        source = (item.card.name if item and item.card else
                  item.source.card.name if item and isinstance(item.source, Permanent) else "effect")
        cause = f"{source}: {k}"
        if k == "damage" and eff.data.get("x"):
            eff = dataclasses.replace(eff, amount=getattr(item, "x", 0))
        if k == "damage" and eff.data.get("count"):
            what = eff.data["count"]
            n = sum(x.card.token_kind == "treasure" if what == "treasures" else x.card.is_artifact
                    if what == "artifacts" else x.is_creature if what == "creatures" else x.card.is_land
                    for x in p.battlefield)
            eff = dataclasses.replace(eff, amount=n)
        if k == "damage":
            if eff.target == "each_creature":
                for perm in p.creatures + opp.creatures:
                    self.deal_damage(perm, eff.amount, by=p, cause=cause)
            elif eff.target == "each_opp_and_pw":
                self.change_life(opp, -eff.amount, cause)
                for pw in opp.planeswalkers:
                    pw.counters["loyalty"] = pw.loyalty - eff.amount
            else:
                self.deal_damage(target, eff.amount, by=p, cause=cause)
        elif k == "destroy":
            if isinstance(target, Permanent) and target in target.controller.battlefield:
                self.destroy(target)
        elif k == "draw":
            who = opp if eff.target == "each_opponent" else p
            self.draw(who, eff.amount)
        elif k == "draw_up_to":
            self.draw(p, max(0, eff.amount - len(p.hand)))
        elif k == "gain_life":
            who = target if eff.target == "that_controller" and isinstance(target, Player) else p
            self.change_life(who, eff.amount, cause)
        elif k == "drain":
            self.change_life(opp, -eff.amount, cause)
        elif k == "pump":
            if isinstance(target, Permanent) and target in target.controller.battlefield:
                target.pump_p += eff.amount
                target.pump_t += eff.amount2
        elif k in ("counter", "bounce_spell"):
            self.counter(p, eff, target)
        elif k == "lose_life":
            who = target if eff.target in ("that_player", "that_controller") and isinstance(target, Player) else p
            self.change_life(who, -eff.amount, cause)
        elif k == "debuff":
            victims = opp.creatures if eff.target == "opp_creatures" else p.creatures + opp.creatures
            for perm in victims:
                perm.pump_p -= eff.amount
                perm.pump_t -= eff.amount2
        elif k == "debuff_one":
            if isinstance(target, Permanent):
                target.pump_p -= eff.amount
                target.pump_t -= eff.amount2
        elif k == "wrath":
            for perm in p.creatures + opp.creatures:
                self.destroy(perm)
        elif k == "wrath_pw":
            for perm in p.planeswalkers + opp.planeswalkers:
                self.destroy(perm)
        elif k == "bounce":
            if isinstance(target, Permanent) and target in target.controller.battlefield:
                self.log(f"{target.card.name} returns to hand", p)
                self.leave_battlefield(target, "hand")
        elif k == "scry":
            self.scry(p, eff.amount)
        elif k == "surveil":
            self.scry(p, eff.amount, to_graveyard=True)
        elif k == "dig":
            n = item.mana_spent if eff.data.get("x_mana") and item is not None and item.mana_spent else eff.amount
            if eff.data.get("x_lands"):
                n = sum(x.card.is_land for x in p.battlefield)
            if eff.data.get("x_count"):
                n = sum(card_matches(x.card, "a " + eff.data["x_count"]) for x in p.battlefield)
            self.dig(p, n, eff.amount2, eff.data.get("filter"))
        elif k == "dig_put":
            self.dig_put(p, eff.amount, eff.amount2, eff.data.get("count", 1), eff.data.get("noncreature", False))
        elif k == "discard":
            who = target if isinstance(target, Player) else p
            basics = [c for c in who.hand if is_basic_land(c)] if eff.data.get("unless") == "basic_land" else []
            if basics:
                # One basic land instead of the larger discard (Thirst for Discovery); for an
                # AI that is nearly always the cheaper option.
                card = max(basics, key=lambda c: sum(c.name == x.name for x in who.hand))
                who.hand.remove(card)
                who.graveyard.append(card)
                self.log(f"discards {card.name}", who)
            who.discarded_last = []
            for _ in range(0 if basics else min(eff.amount, len(who.hand))):
                card = who.ai.choose_discard(self, who)
                who.hand.remove(card)
                who.graveyard.append(card)
                who.discarded_last.append(card)
                self.log(f"discards {card.name}", who)
        elif k == "discard_choice":
            if isinstance(target, Player):
                card = self.hook(p, "choose_discard_from")(self, p, target)
                if eff.filter == "noncreature":    # Duress: a noncreature, nonland card
                    legal = [c for c in target.hand if not c.is_land and not c.is_creature]
                    if card not in legal:
                        card = max(legal, key=lambda c: c.cmc, default=None)
                if card is not None:
                    target.hand.remove(card)
                    target.graveyard.append(card)
                    self.log(f"makes {target} discard {card.name}", p)
        elif k == "rummage":
            cards = self.hook(p, "choose_rummage")(self, p, eff.amount)
            for c in cards:
                p.hand.remove(c)
                p.graveyard.append(c)
            self.draw(p, len(cards))
        elif k == "token":
            who = target if eff.target == "that_controller" and isinstance(target, Player) else p
            self.create_token(who, eff)
        elif k == "copy_token":
            tokens = [x for x in p.creatures if x.card.is_token]
            if tokens:
                best = max(tokens, key=lambda t: t.power + t.toughness)
                self.enter_battlefield(p, best.card)
                self.log(f"copies {best.card.name}", p)
        elif k == "p1_counters" and eff.target == "my_creatures":
            src = item.source if item is not None else None
            for c in p.creatures:
                if not (eff.data.get("other") and c is src):
                    c.counters["+1/+1"] = c.p1 + eff.amount
        elif k == "pump_all":
            src = item.source if item is not None else None
            for c in p.creatures:
                if eff.data.get("other") and c is src:
                    continue
                c.pump_p += eff.amount
                c.pump_t += eff.amount2
                if eff.data.get("keyword"):
                    c.temp_kw.add(eff.data["keyword"])
        elif k == "tutor":
            cands = [c for c in p.library if card_matches(c, eff.data["what"])]
            if cands:
                card = choose_tutor(self, p, cands)
                p.library.remove(card)
                p.hand.append(card)
                self.log(f"searches for {card.name}", p)
            self.rng.shuffle(p.library)
        elif k == "p1_counters":
            if isinstance(target, Permanent) and target in target.controller.battlefield:
                target.counters["+1/+1"] = target.p1 + eff.amount
                if eff.data.get("keyword"):
                    target.perm_kw.add(eff.data["keyword"])
        elif k == "grant":
            if isinstance(target, Permanent):
                target.temp_kw.add(eff.data["keyword"])
        elif k == "add_counter":
            if isinstance(target, Permanent):
                name = eff.data.get("counter", "+1/+1")
                target.counters[name] = target.counters.get(name, 0) + eff.amount
        elif k == "transform":
            if isinstance(target, Permanent):
                self.transform(target)
        elif k == "regrow":
            cands = [c for c in p.graveyard if c.is_creature]
            if cands:
                card = max(cands, key=lambda c: c.cmc)
                p.graveyard.remove(card)
                p.hand.append(card)
                self.log(f"returns {card.name} to hand", p)
        elif k == "reanimate_snow":
            x = item.snow_spent if item else 0
            cands = [c for c in p.graveyard if (c.is_creature or c.is_planeswalker) and c.cmc <= x]
            if cands:
                card = max(cands, key=lambda c: c.cmc)
                p.graveyard.remove(card)
                self.log(f"returns {card.name} to the battlefield", p)
                self.enter_battlefield(p, card)
        elif k == "gy_hate":
            creatures = [c for c in opp.graveyard if c.is_creature]
            if creatures:
                card = max(creatures, key=lambda c: c.cmc)
                opp.graveyard.remove(card)
                opp.exile.append(card)
                self.change_life(opp, -eff.amount, cause)
                self.change_life(p, eff.amount, cause)
            elif opp.graveyard:
                card = max(opp.graveyard, key=lambda c: c.is_instant or c.is_sorcery)
                opp.graveyard.remove(card)
                opp.exile.append(card)
        elif k == "drain_devotion":
            color = eff.data["color"]
            n = sum(x.card.mana_cost.get(color, 0) for x in p.battlefield)
            self.change_life(opp, -n, cause)
            self.change_life(p, n, cause)
            self.log(f"drains {n} (devotion)", p)
        elif k == "mill":
            who = target if isinstance(target, Player) else p
            who.milled_last = []
            for _ in range(min(eff.amount, len(who.library))):
                who.milled_last.append(who.library.pop())
                who.graveyard.append(who.milled_last[-1])
        elif k == "mill_pick":
            cands = [c for c in p.milled_last if c.is_permanent and c in p.graveyard]
            p.picked_last = None
            if cands:
                card = choose_tutor(self, p, cands)
                p.graveyard.remove(card)
                p.hand.append(card)
                p.picked_last = card
                self.log(f"puts milled {card.name} into hand", p)
        elif k == "discard_tutor":
            cands = [c for c in p.library if card_matches(c, eff.data["desc"])]
            if p.hand and cands:
                card = p.ai.choose_discard(self, p)
                p.hand.remove(card)
                p.graveyard.append(card)
                found = choose_tutor(self, p, cands)
                p.library.remove(found)
                p.hand.append(found)
                self.rng.shuffle(p.library)
                self.log(f"discards {card.name} and searches for {found.name}", p)
        elif k == "stun_discarded":
            n = sum(not c.is_land for c in p.discarded_last)
            for _ in range(n):
                tgt = max((c for c in opp.creatures if not c.counters.get("stun") and self.targetable(c, p)),
                          key=perm_value, default=None)
                if tgt is None:
                    break
                tgt.tapped = True
                tgt.counters["stun"] = 1
                self.log(f"taps and stuns {tgt.card.name}", p)
        elif k == "shuffle_away":
            for perm in (target, item.source if item else None):
                if isinstance(perm, Permanent) and perm in perm.controller.battlefield:
                    owner = perm.controller
                    if self.leave_battlefield(perm, "graveyard") and not perm.front.is_token:
                        owner.graveyard.remove(perm.front)
                        owner.library.append(perm.front)
                        self.rng.shuffle(owner.library)
                    self.log(f"shuffles {perm.card.name} into its owner's library", p)
        elif k == "return_as_enchantment":
            card = item.source.front if item and item.source else None
            if card is not None and card in p.graveyard:
                p.graveyard.remove(card)
                ench = dataclasses.replace(card, types=card.types - {"Creature"}, power=None, toughness=None)
                perm = self.enter_battlefield(p, ench)
                perm.front = card
                self.log(f"returns {card.name} as an enchantment", p)
        elif k == "edict":
            victims = sorted(opp.creatures, key=perm_value)[:eff.amount]
            for v in victims:
                if eff.data.get("exile"):
                    self.leave_battlefield(v, "exile")
                    self.log(f"{opp} exiles {v.card.name}", p)
                else:
                    self.sacrifice(v)
        elif k == "last_gift":
            src = item.source if item else None
            before = {pl.name: [c for c in pl.graveyard if c.is_creature] for pl in self.players}
            for pl in self.players:
                for c in [x for x in pl.creatures if x is not src]:
                    self.sacrifice(c)
            for pl in self.players:
                for card in before[pl.name]:
                    if card in pl.graveyard:
                        pl.graveyard.remove(card)
                        self.enter_battlefield(pl, card)
                self.log(f"{pl} returns {len(before[pl.name])} creatures", p)
        elif k == "exile_gy":
            opp.exile += opp.graveyard
            opp.graveyard.clear()
            self.log(f"{opp} exiles their graveyard", p)
        elif k == "untap_other":
            tapped = [x for x in p.battlefield if x.tapped and x is not (item.source if item else None)]
            best = max(tapped, key=lambda x: (x.card.is_land or bool(x.card.produces), perm_value(x) if x.is_creature
                                             else x.card.cmc), default=None)
            if best is not None:
                best.tapped = False
        elif k == "tap":
            if isinstance(target, Permanent):
                target.tapped = True
            for _ in range(eff.amount - 1):   # "tap up to two target creatures": the next best ones
                extra = default_choose_target(self, p, eff)
                if extra is not None:
                    extra.tapped = True
        elif k == "unblockable":
            if isinstance(target, Permanent):
                target.temp_kw.add("unblockable")
        elif k == "earthbend":
            land = choose_earthbend(self, p)
            if land is not None:
                # Target land you control becomes a 0/0 creature with haste that's still a land.
                land.animated = Activated("animate", {}, 0, 0, frozenset({"haste"}), text="earthbend")
                land.counters["+1/+1"] = land.p1 + eff.amount
                self.log(f"earthbends {land.card.name} ({eff.amount})", p)
        elif k == "stun":
            if isinstance(target, Permanent) and target in target.controller.battlefield:
                target.counters["stun"] = target.counters.get("stun", 0) + eff.amount
        elif k == "reveal_land":
            if opp.library and opp.library[-1].is_land:
                opp.hand.append(opp.library.pop())
                self.log(f"{opp} puts a revealed land into their hand", p)
        elif k == "fetch_basic":
            if eff.data.get("sacrifice"):
                if item is None or item.source not in p.battlefield:
                    return
                self.sacrifice(item.source)
            who = target if eff.target == "that_controller" and isinstance(target, Player) else p
            land = choose_basic(self, who)
            if land is not None:
                who.library.remove(land)
                self.log(f"fetches {land.name}", who)
                perm = self.enter_battlefield(who, land)
                lands = sum(x.card.is_land for x in who.battlefield)
                perm.tapped = not (eff.data.get("untap4") and lands >= 4)
            self.rng.shuffle(who.library)
        elif k == "double_power":
            if isinstance(target, Permanent) and target.power > 0:
                target.pump_p += target.power
        elif k == "double_counters" and eff.target == "my_creatures":
            for c in p.creatures:
                c.counters["+1/+1"] = c.p1 * 2
        elif k == "double_counters":
            if isinstance(target, Permanent) and target.p1:
                target.counters["+1/+1"] = target.p1 * 2
        elif k == "next_creature_counter":
            p.next_creature_counters += 1
        elif k == "adversary":
            self.adversary(p, item, eff)
        elif k == "explore":
            if isinstance(target, Permanent) and target in target.controller.battlefield and p.library:
                top = p.library[-1]
                if top.is_land:
                    p.hand.append(p.library.pop())
                else:
                    target.counters["+1/+1"] = target.p1 + 1
                    if self.hook(p, "scry")(self, p, [top]):
                        p.graveyard.append(p.library.pop())
                self.log(f"{target.card.name} explores", p)
        elif k == "oring":
            src = item.source if item is not None else None
            if isinstance(target, Permanent) and isinstance(src, Permanent) and src in src.controller.battlefield:
                self.exile_until_leaves(src, [target])
        elif k == "oring_all":
            src = item.source if item is not None else None
            if isinstance(src, Permanent) and src in src.controller.battlefield:
                self.exile_until_leaves(src, [x for pl in self.players for x in pl.battlefield if x is not src and
                                              (x.is_creature or x.card.is_artifact) and x.card.cmc <= eff.amount])
        elif k == "return_self_gy":
            card = item.context if item is not None else None
            if isinstance(card, CardDef) and card in p.graveyard:
                p.graveyard.remove(card)
                self.log(f"returns {card.name} from the graveyard", p)
                self.enter_battlefield(p, card)
        elif k == "token_copy":
            self.enter_battlefield(p, eff.data["card"])
            self.log(f"creates {eff.data['card'].name}", p)
        self.state_based_actions()

    def deal_damage(self, target, amount: int, by: Player | None = None, cause="noncombat damage"):
        """Noncombat damage; ``by`` is the controller of the source."""
        if isinstance(target, Player):
            self.change_life(target, -amount, cause)
        elif isinstance(target, Permanent) and target in target.controller.battlefield:
            if target.is_planeswalker and not target.is_creature:
                target.counters["loyalty"] = target.loyalty - amount
            elif by is not None and target.controller is not by and \
                    any(x.card.wither_noncombat for x in by.battlefield):
                target.counters["-1/-1"] = target.m1 + amount   # Soul-Scar Mage
            else:
                target.damage += amount

    def adversary(self, p: Player, item, eff: Effect):
        """Bloodthirsty Adversary: pay {2}{R} once (if the AI wants), get a +1/+1 counter and cast a
        copy of an instant or sorcery with mana value 3 or less from the graveyard."""
        cards = [c for c in p.graveyard if (c.is_instant or c.is_sorcery) and c.cmc <= 3 and c.spell_effects]
        if not cards or not self.can_pay(p, eff.data["cost"]):
            return
        if not self.hook(p, "pay_optional")(self, p, eff.data["cost"], "adversary"):
            return
        self.pay(p, eff.data["cost"])
        src = item.source if item else None
        if src is not None and src in p.battlefield:
            src.counters["+1/+1"] = src.p1 + 1
        card = max(cards, key=lambda c: c.cmc)
        p.graveyard.remove(card)
        p.exile.append(card)
        targets = self.auto_targets(p, card.spell_effects)
        copy = StackItem(p, list(card.spell_effects), targets, card=card, name=f"copy of {card.name}", kind="copy")
        self.stack.append(copy)
        self.log(f"casts a copy of {card.name} -> {targets}", p)
        self.check_ward(copy)

    def counter(self, p: Player, eff: Effect, target):
        if not isinstance(target, StackItem) or target not in self.stack:
            return
        if eff.kind == "bounce_spell":
            self.stack.remove(target)
            if target.kind == "spell":
                base, _, _ = self._origin(target.card)
                target.controller.hand.append(base)
            self.log(f"{target} is returned to its owner's hand", p)
            return
        if target.is_spell and not self.counterable(target):
            self.log(f"{target} can't be countered", p)
            return
        if eff.amount:
            payer = target.controller
            if eff.data.get("life"):
                n = eff.data["life"]
                if payer.life > n + 2 and self.hook(payer, "pay_unless")(self, payer, 0, target):
                    self.change_life(payer, -n, f"ward: pay {n} life")
                    return
            elif eff.data.get("discard"):
                if payer.hand and self.hook(payer, "pay_unless")(self, payer, 0, target):
                    card = payer.ai.choose_discard(self, payer)
                    payer.hand.remove(card)
                    payer.graveyard.append(card)
                    self.log(f"discards {card.name} for ward", payer)
                    return
            else:
                payment = find_payment(self.mana_sources(payer, spell="ability"), {"generic": eff.amount})
                if payment is not None and self.hook(payer, "pay_unless")(self, payer, eff.amount, target):
                    self.pay(payer, {"generic": eff.amount})
                    self.log(f"pays {eff.amount} for {target}", payer)
                    return
        self.stack.remove(target)
        if target.kind == "spell":
            base, kind, _ = self._origin(target.card)
            (target.controller.exile if kind == "flashback" else target.controller.graveyard).append(base)
        self.log(f"{target} is countered", p)

    def scry(self, p: Player, n: int, to_graveyard: bool = False):
        cards = [p.library.pop() for _ in range(min(n, len(p.library)))]
        bottom = self.hook(p, "scry")(self, p, list(cards))
        for c in reversed(cards):
            if c not in bottom:
                p.library.append(c)
        for c in bottom:
            if to_graveyard:
                p.graveyard.append(c)
            else:
                p.library.insert(0, c)

    def dig(self, p: Player, n: int, keep: int, desc: str | None = None):
        cards = [p.library.pop() for _ in range(min(n, len(p.library)))]
        allowed = [c for c in cards if card_matches(c, desc.replace(" or ", " or a "))] if desc else cards
        chosen = list(self.hook(p, "choose_dig")(self, p, list(allowed), keep))[:keep] if allowed else []
        rest = list(cards)
        for c in chosen:
            rest.remove(c)
            p.hand.append(c)
        self.rng.shuffle(rest)
        for c in rest:
            p.library.insert(0, c)
        self.log(f"digs {n}, keeps {chosen}", p)

    def dig_put(self, p: Player, n: int, max_cmc: int, count: int = 1, noncreature: bool = False):
        cards = [p.library.pop() for _ in range(min(n, len(p.library)))]
        cands = [c for c in cards if c.is_permanent and not c.is_land and c.cmc <= max_cmc
                 and not (noncreature and c.is_creature)]
        rest = list(cards)
        for card in sorted(cands, key=lambda c: -c.cmc)[:count]:
            rest.remove(card)
            self.log(f"puts {card.name} onto the battlefield", p)
            self.enter_battlefield(p, card)
        self.rng.shuffle(rest)
        for c in rest:
            p.library.insert(0, c)

    def destroy(self, perm: Permanent):
        if perm.has("indestructible"):
            return
        self.dies(perm)

    def leave_battlefield(self, perm: Permanent, to: str):
        """Move a permanent off the battlefield (to graveyard / hand / exile). Tokens vanish."""
        if perm not in perm.controller.battlefield:
            return False
        owner = perm.controller
        owner.battlefield.remove(perm)
        owner.perm_left_turn = True
        perm.attached_to = None
        for x in owner.battlefield:
            if x.attached_to is perm:
                x.attached_to = None
        self.fire(owner, "leaves", perm)
        returning, perm.exiled_cards = perm.exiled_cards, []
        for card, card_owner in returning:
            if card in card_owner.exile:
                card_owner.exile.remove(card)
                self.log(f"{card.name} returns from exile", card_owner)
                self.enter_battlefield(card_owner, card)
        if perm in self.attackers:
            self.attackers.remove(perm)
        if not perm.front.is_token:
            {"graveyard": owner.graveyard, "hand": owner.hand, "exile": owner.exile}[to].append(perm.front)
        return True

    def extra_sac_candidates(self, p: Player, card: CardDef) -> list:
        """What p could sacrifice for card's additional cost, least valuable first."""
        return sorted((x for x in p.battlefield if card_matches(x.card, card.extra_sacrifice.replace(" or ", " or a "))
                       or (x.is_creature and "creature" in card.extra_sacrifice)),
                      key=lambda x: (not x.card.is_token, perm_value(x) if x.is_creature else x.card.cmc))

    def sacrifice(self, perm: Permanent):
        """Sacrifice perm, firing "whenever you sacrifice" triggers."""
        p = perm.controller
        p.sacrificed_turn += 1
        for other in list(p.battlefield):
            for trig in other.triggers:
                if trig.event == "sacrifice" and card_matches(perm.card, trig.filter):
                    self.queue_trigger(p, trig.effects, other, other.card.name)
        self.dies(perm) if perm.is_creature else self.leave_battlefield(perm, "graveyard")

    def dies(self, perm: Permanent):
        was_creature = perm.is_creature
        if was_creature and (perm.damage or perm.deathtouched) and \
                any(x.card.exile_damaged for x in self.opponent(perm.controller).battlefield):
            if self.leave_battlefield(perm, "exile"):   # Etching of Kumano
                self.log(f"{perm.card.name} is exiled instead of dying", perm.controller)
            return
        if not self.leave_battlefield(perm, "graveyard"):
            return
        self.log(f"{perm.card.name} dies", perm.controller)
        if was_creature:
            self.fire(perm.controller, "dies", perm)
            if perm.blitz:
                self.queue_trigger(perm.controller, [Effect("draw", 1)], perm, f"{perm.card.name} blitz")
            self.fire(perm.controller, "other_creature_dies", subject=perm)
            opp = self.opponent(perm.controller)
            for other in opp.battlefield:
                self.fire(opp, "opp_creature_dies", other, context=perm.controller)

    def state_based_actions(self):
        changed = True
        while changed:
            changed = False
            for p in self.players:
                for perm in list(p.battlefield):
                    if perm.is_creature:
                        if perm.toughness <= 0:
                            self.dies(perm)
                            changed = True
                        elif (perm.damage >= perm.toughness or perm.deathtouched) and not perm.has("indestructible"):
                            self.dies(perm)
                            changed = True
                    elif perm.is_planeswalker and perm.loyalty <= 0:
                        self.dies(perm)
                        changed = True
        for p in self.players:
            if p.life <= 0:
                if not p.lost:
                    self.audit("loss", seat=self.players.index(p), cause="life total 0 or less")
                p.lost = True

    # --------------------------------------------------------------- combat
    def combat(self, p: Player, opp: Player):
        self.step = "declare_attackers"
        self.attackers, self.blocks, self.attack_targets = [], {}, {}
        self.hook(p, "before_attacks")(self, p)
        if self.over:
            return
        attackers = [a for a in p.ai.choose_attackers(self, p, opp) if a.can_attack()]
        self.attackers = list(attackers)
        if not attackers:
            return
        targets = self.hook(p, "choose_attack_targets")(self, p, attackers) or {}
        for a in attackers:
            t = targets.get(a, opp)
            self.attack_targets[a] = t if (t is opp or (isinstance(t, Permanent) and t.is_planeswalker
                                                         and t in opp.battlefield)) else opp
            if not a.has("vigilance"):
                a.tapped = True
        p.attacked_with = len(attackers)
        self.log(f"attacks with {attackers}" + (
            f" ({ {a: t for a, t in self.attack_targets.items() if t is not opp} })"
            if any(t is not opp for t in self.attack_targets.values()) else ""), p)
        for a in attackers:
            self.fire(p, "attacks", a)
            self.fire(p, "creature_attacks")
        self.fire(p, "you_attack")
        self.run_priority(until_empty_stack=False)
        attackers = [a for a in self.attackers if a in p.battlefield]
        self.attackers = attackers
        if self.over or not attackers:
            return

        self.step = "declare_blockers"
        blocks = opp.ai.choose_blocks(self, opp, p, attackers)
        used = set()
        legal = {}
        for a in attackers:
            bl = [b for b in blocks.get(a, []) if b not in used and b in opp.battlefield and can_block(b, a)]
            if a.has("menace") and len(bl) == 1:
                bl = []
            if bl:
                legal[a] = bl
                used.update(bl)
        blocks = legal
        self.blocks = blocks
        if blocks:
            self.log(f"blocks {blocks}", opp)
        p.ai.after_blocks(self, p, attackers, blocks)
        if self.over:
            return
        self.run_priority(until_empty_stack=False)
        if self.over:
            return

        self.step = "combat_damage"
        attackers = self.attackers
        first = any(c.has("first strike") or c.has("double strike")
                    for c in attackers + [b for bl in blocks.values() for b in bl])
        if first:
            self.combat_damage(p, opp, attackers, blocks,
                               lambda c: c.has("first strike") or c.has("double strike"))
            if self.over:
                return
        self.combat_damage(p, opp, attackers, blocks,
                           lambda c: not first or c.has("double strike") or not c.has("first strike"))

    def combat_damage(self, p, opp, attackers, blocks, deals_now):
        hits = []  # (source, target, amount)
        for a in attackers:
            if a not in p.battlefield:
                continue
            target = self.attack_targets.get(a, opp)
            if isinstance(target, Permanent) and target not in opp.battlefield:
                target = None   # its planeswalker is gone: no damage
            if a in blocks:
                alive = [b for b in blocks[a] if b in opp.battlefield]
                if deals_now(a) and a.power > 0:
                    remaining = a.power
                    for i, b in enumerate(alive):
                        lethal = 1 if a.has("deathtouch") else max(0, b.toughness - b.damage)
                        last = i == len(alive) - 1
                        amt = remaining if (last and not a.has("trample")) else min(remaining, lethal)
                        if amt:
                            hits.append((a, b, amt))
                        remaining -= amt
                    if remaining > 0 and a.has("trample") and target is not None:
                        hits.append((a, target, remaining))
                for b in alive:
                    if deals_now(b) and b.power > 0:
                        hits.append((b, a, b.power))
            elif deals_now(a) and a.power > 0 and target is not None:
                hits.append((a, target, a.power))
        for src, tgt, amt in hits:
            if isinstance(tgt, Player):
                self.change_life(tgt, -amt, f"{src.card.name}: combat damage")
                self.fire(src.controller, "combat_damage_player", src)
                self.fire(src.controller, "ally_combat_damage")
            elif tgt.is_planeswalker and not tgt.is_creature:
                tgt.counters["loyalty"] = tgt.loyalty - amt
            else:
                tgt.damage += amt
                if src.has("deathtouch"):
                    tgt.deathtouched = True
            if src.has("lifelink"):
                self.change_life(src.controller, amt, f"{src.card.name}: lifelink")
        self.state_based_actions()
        self.settle()


# ---------------------------------------------------------------------------
# Default decisions, used when an AI doesn't define the hook of the same name.

def perm_value(x: Permanent) -> float:
    if x.is_planeswalker and not x.is_creature:
        return 4 + x.loyalty
    if x.card.token_kind:
        return 0.5
    return x.card.cmc + (x.power + x.toughness) / 2 + 0.5 * len(x.card.keywords)


def _threat(game: Game, me: Player, item: StackItem) -> float:
    """How much I want to counter an opponent's stack item."""
    score = item.card.cmc if item.card else 0
    for eff, tgt in zip(item.effects, item.targets):
        if tgt is me or (isinstance(tgt, Permanent) and tgt.controller is me):
            score += 2
        if isinstance(tgt, StackItem) and tgt.controller is me:
            score += 2 + (tgt.card.cmc if tgt.card else 0)
        if eff.kind == "damage" and tgt is me and eff.amount >= me.life:
            score += 100
        if eff.kind == "wrath" and me.creatures:
            score += 2 * len(me.creatures)
    if item.card and (item.card.is_creature or item.card.is_planeswalker):
        score += ((item.card.power or 0) + (item.card.toughness or 0)) / 4 + item.card.loyalty / 2
    return score


def default_choose_target(game: Game, me: Player, eff: Effect):
    """A reasonable target for eff, respecting hexproof and targeting restrictions."""
    opp = game.opponent(me)
    legal = game.legal_targets(me, eff)
    theirs = [x for x in legal if isinstance(x, Permanent) and x.controller is opp]
    mine = [x for x in legal if isinstance(x, Permanent) and x.controller is me]
    k = eff.kind
    if k == "damage":
        if eff.target == "player":
            return opp
        if eff.target == "any" and eff.amount >= opp.life:
            return opp
        killable = [x for x in theirs if (x.is_creature and x.toughness - x.damage <= eff.amount and
                                          not x.has("indestructible")) or (x.is_planeswalker and not x.is_creature
                                                                           and x.loyalty <= eff.amount)]
        if killable:
            return max(killable, key=perm_value)
        return opp if eff.target == "any" else None
    if k == "mill":
        return opp
    if k == "tap":
        theirs = [x for x in theirs if not x.tapped]
        return max(theirs, key=perm_value, default=None)
    if k in ("destroy", "debuff_one", "bounce"):
        if k == "debuff_one":
            theirs = [x for x in theirs if x.toughness <= eff.amount2]
        theirs = [x for x in theirs if not (k == "destroy" and x.has("indestructible"))]
        return max(theirs, key=perm_value, default=None)
    if k in ("pump", "p1_counters", "double_power", "grant", "explore"):
        return max(mine, key=perm_value, default=None)
    if k == "oring":
        return max(theirs, key=perm_value, default=None)
    if k in ("stun", "shuffle_away"):
        return max(theirs, key=perm_value, default=None)
    if k == "unblockable":
        ready = [x for x in mine if x.can_attack() and x.power > 0]
        return max(ready, key=lambda x: x.power, default=None)
    if k in ("counter", "bounce_spell"):
        return next((i for i in reversed(game.stack) if i in legal), None)
    if k in ("discard", "discard_choice"):
        return opp if opp.hand else None
    return None


def is_basic_land(c) -> bool:
    return c.is_land and (c.name in BASIC_MANA or c.name.startswith("Snow-Covered ") or c.name == "Wastes")


def choose_basic(game: Game, me: Player):
    """The basic land to fetch: one making the colour the hand needs most and the battlefield has least."""
    basics = [c for c in me.library if is_basic_land(c)]
    if not basics:
        return None
    have = {col: sum(col in x.card.produces for x in me.battlefield if x.card.is_land) for col in COLORS}
    need = {col: sum(c.mana_cost.get(col, 0) for c in me.hand + me.library) for col in COLORS}
    return max(basics, key=lambda c: max((need[col] / (1 + have[col]) for col in c.produces), default=0))


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
            if w[0].isupper() and w not in card.subtypes and w != card.name:
                ok = False
        if ok:
            return True
    return False


def choose_earthbend(game: Game, me: Player):
    """The land to earthbend: one already earthbent, else a tapped land, else any land."""
    lands = [x for x in me.battlefield if x.card.is_land]
    return max(lands, key=lambda x: (bool(x.animated), x.tapped, not is_basic_land(x.card)), default=None)


def play_extra_lands(game: Game, me: Player):
    """Land drops the AI doesn't make: additional lands (Icetill Explorer) and lands from the graveyard."""
    for _ in range(3):
        if me.land_played:
            return
        lands = [c for c in me.hand if c.is_land]
        if any(x.card.lands_from_gy for x in me.battlefield):
            lands += [c for c in me.graveyard if c.is_land]
        if not lands:
            return
        game.play_land(me, min(lands, key=lambda c: (c.enters_tapped, c in me.hand)))


def choose_tutor(game: Game, me: Player, cards: list[CardDef]) -> CardDef:
    """The card to search for: a land when short of lands, else the best spell we can soon cast."""
    lands = sum(x.card.is_land for x in me.battlefield)
    if _wants_land(game, me) and any(c.is_land for c in cards):
        return next(c for c in cards if c.is_land)
    spells = [c for c in cards if not c.is_land] or cards
    castable = [c for c in spells if c.cmc <= lands + 1] or spells
    return max(castable, key=lambda c: (c.cmc, (c.power or 0) + (c.toughness or 0)))


def choose_color(game: Game, me: Player) -> str:
    """The colour a land that enters as a chosen basic land type should make."""
    have = {col: sum(col in x.card.produces for x in me.battlefield if x.card.is_land) for col in COLORS}
    need = {col: sum(c.mana_cost.get(col, 0) for c in me.hand + me.library) for col in COLORS}
    return max(COLORS, key=lambda col: need[col] / (1 + have[col]))


def choose_target(game: Game, me: Player, eff: Effect):
    return default_choose_target(game, me, eff)


def _mode_value(game: Game, me: Player, effects: list) -> float:
    opp = game.opponent(me)
    total = 0.0
    for e in effects:
        if e.target in TARGETED:
            tgt = default_choose_target(game, me, e)
            if tgt is None:
                return -1
        else:
            tgt = None
        k = e.kind
        if k == "wrath":
            total += sum(map(perm_value, opp.creatures)) - sum(map(perm_value, me.creatures))
        elif k == "wrath_pw":
            total += sum(map(perm_value, opp.planeswalkers)) - sum(map(perm_value, me.planeswalkers))
        elif k == "damage":
            total += perm_value(tgt) if isinstance(tgt, Permanent) else (100 if e.amount >= opp.life else 1)
        elif k in ("discard", "discard_choice"):
            total += 2 if opp.hand else 0
        elif k == "regrow":
            total += max((c.cmc for c in me.graveyard if c.is_creature), default=-1)
        elif k in ("destroy", "bounce", "shuffle_away"):
            total += perm_value(tgt)
        elif k in ("bounce_spell", "counter"):
            total += tgt.card.cmc if isinstance(tgt, StackItem) and tgt.card else 1
        elif k == "unblockable":
            # Only worth it before combat, when the opponent has a blocker.
            if game.step != "main1" or not any(not c.tapped for c in opp.creatures):
                return -1
            total += tgt.power
        else:
            total += 1
    return total


def default_choose_modes(game: Game, me: Player, modes: list, n: int, up_to: bool) -> list[int]:
    """Pick the n most valuable modes (only worthwhile ones for "choose up to")."""
    scored = sorted(((_mode_value(game, me, m), i) for i, m in enumerate(modes)), reverse=True)
    if up_to:
        return [i for v, i in scored[:n] if v > 0]
    usable = [i for v, i in scored if v >= 0]
    return (usable or [i for _, i in scored])[:n]


def _targets_for(game: Game, me: Player, card: CardDef, stack_target=None):
    """Targets for each of card's effects, or None if a needed target is missing."""
    opp = game.opponent(me)
    out = []
    for eff in card.spell_effects:
        if eff.target == "spell":
            out.append(stack_target)
        elif eff.target in ("creature", "creature_pw", "nonland_perm") and \
                game.step in ("declare_attackers", "declare_blockers") and game.active is opp:
            pool = [a for a in game.attackers if a in game.legal_targets(me, eff)]
            if eff.kind == "damage":
                pool = [c for c in pool if c.toughness - c.damage <= eff.amount]
            tgt = max(pool, key=perm_value, default=None)
            if tgt is None:
                return None
            out.append(tgt)
        elif eff.target in TARGETED:
            tgt = default_choose_target(game, me, eff)
            if tgt is None or (eff.kind == "damage" and tgt is opp and eff.target != "player"):
                return None
            out.append(tgt)
        else:
            out.append(None)
    return out


def _removal(card: CardDef) -> bool:
    return any(e.kind in ("destroy", "bounce") or (e.kind == "damage" and e.target in ("creature", "any", "creature_pw"))
               for e in card.spell_effects)


def respond(game: Game, me: Player):
    """A simple instant-speed policy: counter opponents' meaningful spells, protect creatures
    from removal, kill attackers, flash in The Wandering Emperor to exile an attacker, and
    use leftover mana at the opponent's end step on removal, flash creatures, card draw and
    Clues. Returns an action (see Game.do_action) or None to pass."""
    opp = game.opponent(me)
    options = {c.name: c for c in game.spell_options(me) if c.instant_speed and game.can_cast_now(me, c)}
    top = game.stack[-1] if game.stack else None
    if top is not None:
        if top.controller is me:
            return None
        # Protect a creature targeted by removal (Snakeskin Veil).
        aimed = [t for t in top.targets if isinstance(t, Permanent) and t.controller is me]
        if aimed and any(e.kind in ("destroy", "damage", "bounce", "debuff_one") for e in top.effects):
            for c in options.values():
                if any(e.kind == "grant" and e.data.get("keyword") == "hexproof" for e in c.spell_effects):
                    return c, [aimed[0]] + [None] * (len(c.spell_effects) - 1)
        if not top.is_spell or not game.counterable(top) or _threat(game, me, top) < 3:
            return None
        counters = [c for c in options.values()
                    if any(game.can_counter(e, top, me) for e in c.spell_effects if e.kind == "counter")]
        if not counters:
            return None
        card = min(counters, key=lambda c: c.cmc)
        return card, _targets_for(game, me, card, top)
    # Empty stack.
    extra = respond_extras(game, me)
    if extra or me is game.active:
        return extra
    removal = [c for c in options.values() if _removal(c)]
    if game.step == "declare_attackers" and game.attackers:
        for card in sorted(removal, key=lambda c: c.cmc):
            targets = _targets_for(game, me, card)
            if targets:
                return card, targets
    if game.step == "end_step":
        for card in sorted(removal, key=lambda c: c.cmc):
            targets = _targets_for(game, me, card)
            if targets and any(isinstance(t, Permanent) and perm_value(t) >= 3 for t in targets):
                return card, targets
        flash = [c for c in options.values() if c.is_creature or c.is_planeswalker]
        if flash:
            return max(flash, key=lambda c: c.cmc), None
        draw = [c for c in options.values()
                if c.spell_effects and all(e.kind in ("draw", "dig", "scry", "surveil", "discard", "gain_life")
                                           for e in c.spell_effects)]
        if draw:
            card = max(draw, key=lambda c: c.cmc)
            return card, [None] * len(card.spell_effects)
    return None


def _option_value(game: Game, me: Player, c: CardDef) -> float:
    if c.is_permanent:
        return 1
    best_modes = sorted((_mode_value(game, me, m) for m in c.modes), reverse=True)[:c.modes_choose]
    rest = _mode_value(game, me, c.spell_effects) if c.spell_effects else 0
    return sum(best_modes) + max(rest, 0) if c.modes else rest


def respond_extras(game: Game, me: Player):
    """Empty-stack actions for mechanics an AI may not handle: The Wandering Emperor (flash her
    in when attacked, use her abilities the turn she enters), and at the opponent's end step
    Clues plus instant-speed options cast from other zones or with modes (flashback, adventure,
    channel, Kolaghan's Command)."""
    if game.stack:
        return None
    for pw in me.planeswalkers:
        if pw.card.pw_instant_on_entry and pw.entered_turn == game.turn and not pw.loyalty_used:
            idx = default_loyalty_choice(game, me, pw)
            if idx is not None:
                return ("loyalty", pw, idx)
    if me is game.active:
        if game.step == "declare_blockers":
            return combat_pump(game, me)
        return None
    options = [c for c in game.spell_options(me) if c.instant_speed and game.can_cast_now(me, c)]
    if game.step == "declare_attackers" and game.attackers:
        flash_pw = [c for c in options if c.is_planeswalker]
        if flash_pw:
            return flash_pw[0], None
    if game.step == "end_step":
        for c in options:
            if c in me.hand and not c.modes:
                continue   # plain hand cards are the AI's call
            if _option_value(game, me, c) > 0:
                return c, None
        clues = [x for x in me.battlefield if x.card.token_kind == "clue"]
        if clues and game.can_pay(me, {"generic": 2}):
            return ("activate", clues[0], "clue")
        ability = choose_ability(game, me, instant=True)
        if ability is not None:
            return ability
    return None


def _self_pump(act) -> bool:
    return all(e.target == "self" and e.kind in ("pump", "grant", "p1_counters") for e in act.effects)


def ability_worth(game: Game, me: Player, perm: Permanent, idx: int, reserve: int = 0) -> bool:
    """Whether to activate perm's general ability idx now, outside combat."""
    act = perm.card.activated[idx]
    c = act.extra_costs
    if _self_pump(act) and not any(e.kind == "p1_counters" for e in act.effects):
        return False    # used in combat (combat_pump)
    if not game.can_activate(me, perm, idx):
        return False
    need = add_costs(act.cost, {"generic": reserve})
    if find_payment(game.mana_sources(me, perm if c.get("tap") else None, "ability"), need) is None:
        return False
    value = _mode_value(game, me, act.effects)
    if value <= 0:
        return False
    if c.get("sac_self") or c.get("exile_self"):
        if perm.is_creature or perm.is_planeswalker:
            return value >= perm_value(perm)
        if perm.card.is_land and sum(x.card.is_land for x in me.battlefield) < 6:
            return False
    if c.get("sacrifice"):
        victim = game.sacrifice_candidates(me, perm, c["sacrifice"])[0]
        if not victim.card.is_token and perm_value(victim) > 1:
            return False
    if c.get("discard") and not choose_rummage(game, me, 1) and len(me.hand) <= 4:
        return False
    if c.get("life") and me.life <= 10:
        return False
    return True


def choose_equip_target(game: Game, me: Player, equipment: Permanent):
    """The creature to equip: the best one that can attack this turn, else the best one."""
    cands = [c for c in me.creatures if not c.card.is_token or c.power > 0]
    if not cands:
        return None
    ready = [c for c in cands if not c.sick or c.has("haste") or "haste" in equipment.card.equip_keywords]
    pool = ready if ready and game.step == "main1" else cands
    return max(pool, key=lambda c: (c.card.equip_discount, perm_value(c) - len(c.equipment)))


def equip_all(game: Game, me: Player):
    """Attach unattached Equipment with spare mana (main phase 1, so it helps this combat)."""
    for eq in [x for x in me.battlefield if x.card.equip_cost is not None and x.attached_to is None]:
        tgt = game.hook(me, "choose_equip_target")(game, me, eq)
        if tgt is None:
            continue
        need = add_costs(game.equip_cost(eq, tgt), {"generic": _reserve(game, me)})
        if find_payment(game.mana_sources(me, spell="ability"), need) is not None:
            game.equip(me, eq, tgt)


def choose_ability(game: Game, me: Player, instant: bool):
    """An ("activate", permanent, "ability:N") action worth taking now, or None. With instant=True
    only abilities without "Activate only as a sorcery"."""
    for perm in list(me.battlefield):
        for i, act in enumerate(perm.card.activated):
            if act.kind != "ability" or (instant and act.sorcery):
                continue
            if ability_worth(game, me, perm, i, 0 if instant else _reserve(game, me)):
                return ("activate", perm, f"ability:{i}")
    return None


def combat_pump(game: Game, me: Player):
    """After blockers: pump unblocked attackers with their own "+N/+N until end of turn" abilities."""
    for a in game.attackers:
        if a.controller is not me or a in game.blocks or a not in me.battlefield:
            continue
        for i, act in enumerate(a.card.activated):
            if act.kind != "ability" or not _self_pump(act) or not game.can_activate(me, a, i):
                continue
            if act.extra_costs.get("life") and me.life <= 10:
                continue
            if any(e.kind == "pump" and e.amount > 0 for e in act.effects):
                return ("activate", a, f"ability:{i}")
    return None


def _wants_land(game: Game, me: Player) -> bool:
    lands = sum(p.card.is_land for p in me.battlefield) + sum(c.is_land for c in me.hand)
    return lands < 5


def scry(game: Game, me: Player, cards: list[CardDef]) -> list[CardDef]:
    """Cards to put on the bottom (or into the graveyard): lands when we have plenty,
    expensive spells when short."""
    want = _wants_land(game, me)
    return [c for c in cards if (c.is_land and not want) or (not c.is_land and want and c.cmc >= 5)]


def choose_dig(game: Game, me: Player, cards: list[CardDef], keep: int) -> list[CardDef]:
    want = _wants_land(game, me)
    score = lambda c: (2 if want else -1) if c.is_land else 1 + c.cmc / 10
    return sorted(cards, key=score, reverse=True)[:keep]


def pay_unless(game: Game, me: Player, amount: int, item: StackItem) -> bool:
    return True


def pay_optional(game: Game, me: Player, cost: dict, what: str) -> bool:
    return True


def pay_shock(game: Game, me: Player, card: CardDef) -> bool:
    return me.life > 8


def choose_discard_from(game: Game, me: Player, victim: Player):
    spells = [c for c in victim.hand if not c.is_land]
    return max(spells, key=lambda c: c.cmc, default=None)


def choose_rummage(game: Game, me: Player, n: int) -> list[CardDef]:
    lands_out = sum(x.card.is_land for x in me.battlefield)
    lands = [c for c in me.hand if c.is_land]
    out = lands[:max(0, len(lands) - 1)] if lands_out >= 4 else []
    out += [c for c in me.hand if not c.is_land and c.cmc > lands_out + 3]
    return out[:n]


def choose_crew(game: Game, me: Player, vehicle: Permanent):
    """Creatures to tap to crew vehicle: summoning-sick ones first, then the smallest."""
    if vehicle.sick or vehicle.tapped:
        return None
    cands = sorted((c for c in me.creatures if c is not vehicle and not c.tapped),
                   key=lambda c: (not c.sick, c.power))
    crew, total = [], 0
    for c in cands:
        if total >= vehicle.card.crew:
            break
        if not c.sick and c.power >= vehicle.card.power:
            break
        crew.append(c)
        total += c.power
    return crew if total >= vehicle.card.crew else None


def _reserve(game: Game, me: Player) -> int:
    """Mana to keep open for instant-speed cards in hand."""
    return min((c.cmc for c in me.hand if not c.is_land and c.instant_speed), default=0)


def before_attacks(game: Game, me: Player):
    """Crew vehicles and animate manlands with spare mana before attackers are chosen."""
    for v in [x for x in me.battlefield if x.card.crew and not x.is_creature]:
        game.activate(me, v, "crew")
    for land in [x for x in me.battlefield if x.card.activated and not x.sick and not x.tapped]:
        for act in land.card.activated:
            if act.kind not in ("animate", "barrens"):
                continue
            need = add_costs(act.cost, {"generic": _reserve(game, me)})
            if find_payment(game.mana_sources(me, exclude=land), need) is not None:
                game.activate(me, land, act.kind)
                break


def choose_attack_targets(game: Game, me: Player, attackers: list) -> dict:
    """Send attackers at opposing planeswalkers unless the player is dead on board."""
    opp = game.opponent(me)
    if not opp.planeswalkers or sum(a.power for a in attackers) >= opp.life:
        return {}
    out, free = {}, sorted(attackers, key=lambda a: a.power)
    for pw in sorted(opp.planeswalkers, key=lambda x: -x.loyalty):
        assigned = 0
        for a in list(free):
            if assigned >= pw.loyalty:
                break
            out[a] = pw
            assigned += a.power
            free.remove(a)
    return out


def default_loyalty_choice(game: Game, me: Player, pw: Permanent):
    """Index of the loyalty ability to use, or None."""
    abilities = pw.card.loyalty_abilities
    best, best_score = None, -1e9
    for i, (cost, effects) in enumerate(abilities):
        if pw.loyalty + cost < 0:
            continue
        value = _mode_value(game, me, effects)
        if value < 0:
            continue
        if cost <= -7:
            value += 20
        if cost < 0 and pw.loyalty + cost < 2:
            value -= 2
        score = value + cost * 0.5
        if score > best_score:
            best, best_score = i, score
    return best


def use_abilities(game: Game, me: Player):
    """Sorcery-speed choices the heuristic AI doesn't make: loyalty abilities, Bloodtithe
    Harvester, Blood tokens and (in the second main phase) foretelling."""
    for pw in list(me.planeswalkers):
        if not pw.loyalty_used:
            idx = default_loyalty_choice(game, me, pw)
            if idx is not None:
                game.activate_loyalty(me, pw, idx)
    blood = sum(1 for x in me.battlefield if x.card.token_kind == "blood")
    for h in [x for x in me.battlefield if any(a.kind == "sac_debuff" for a in x.card.activated)]:
        opp = game.opponent(me)
        kills = [c for c in opp.creatures if c.toughness <= 2 * blood and game.targetable(c, me)
                 and perm_value(c) > perm_value(h)]
        if blood and kills and not h.sick and not h.tapped:
            game.activate(me, h, "sac_debuff")
    play_extra_lands(game, me)
    equip_all(game, me)
    if game.step == "main1":    # "can't be blocked this turn" before combat
        for perm in list(me.battlefield):
            for i, act in enumerate(perm.card.activated):
                if act.kind == "ability" and act.effects and act.effects[0].kind == "unblockable" and \
                        perm in me.battlefield and ability_worth(game, me, perm, i):
                    game.activate(me, perm, f"ability:{i}")
    # Spells from other zones or with alternative costs the AI may not look at.
    for c in game.spell_options(me):
        if (c in me.hand and not c.modes) or c.instant_speed or not game.can_cast_now(me, c):
            continue
        need = add_costs(game.cost_of(me, c), {"generic": _reserve(game, me)})
        if find_payment(game.mana_sources(me), need) is None:
            continue
        if _option_value(game, me, c) > 0:
            game.cast(me, c, None)
    if game.step == "main2":
        for _ in range(10):     # general activated abilities, a few at most
            ability = choose_ability(game, me, instant=False)
            if ability is None or not game.do_action(me, ability):
                break
        for b in [x for x in me.battlefield if x.card.token_kind == "blood"]:
            if choose_rummage(game, me, 1) and game.can_pay(me, {"generic": 1 + _reserve(game, me)}):
                game.activate(me, b, "blood")
        for card in [c for c in me.hand if any(a.kind == "plot" for a in c.alt_costs)]:
            alt = next(a for a in card.alt_costs if a.kind == "plot")
            if game.can_pay(me, add_costs(alt.cost, {"generic": _reserve(game, me)}), spell="ability"):
                game.plot(me, card)
        for card in [c for c in me.hand if any(a.kind == "foretell" for a in c.alt_costs)]:
            if game.can_pay(me, {"generic": 2 + _reserve(game, me)}):
                game.foretell(me, card)


DEFAULTS = {
    "respond": respond, "choose_target": choose_target, "choose_modes": default_choose_modes,
    "scry": scry, "choose_dig": choose_dig, "pay_unless": pay_unless, "pay_optional": pay_optional,
    "pay_shock": pay_shock, "choose_discard_from": choose_discard_from, "choose_rummage": choose_rummage,
    "choose_crew": choose_crew, "before_attacks": before_attacks, "choose_attack_targets": choose_attack_targets,
    "use_abilities": use_abilities, "respond_extras": respond_extras, "choose_equip_target": choose_equip_target,
}
# Older names, kept for compatibility.
default_respond = respond
default_scry = scry
default_dig = choose_dig
