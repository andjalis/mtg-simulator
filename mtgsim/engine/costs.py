"""Game methods for mana sources, costs and payment, and the ways a spell can be cast."""
from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from .. import alt_casts, auras, copies, counting, discounts, returns, costs, storage
from ..cards import AltCost, CardDef, Effect, add_mana, make_token
from .mana import find_payment, payable
from .policy import perm_value
from .state import COLOR_WORDS, Permanent, TARGETED, _gy_desc, card_matches

if TYPE_CHECKING:
    from .state import Player


FACE_DOWN = ("disguise", "morph", "megamorph")   # cast face down for {3} as a 2/2, turned face up for this cost


class CostsMixin:
    def mana_sources(self, p: Player, exclude=None, spell=None, *, reserved_counters=()):
        """p's untapped mana sources. ``spell`` decides what restricted mana (Cavern of Souls) can
        pay for: a CardDef, "ability" for activated abilities, or None to count it (AI estimates)."""
        out = []
        stopped = self.activations_stopped()
        from ..residual_templates import activation_blocked
        for perm in p.battlefield:
            if activation_blocked(self, perm, mana=True):
                continue
            if not perm.can_tap_for_mana() or perm is exclude:
                continue
            if stopped and (perm.card.is_artifact or perm.is_creature):
                continue
            produces = perm.card.produces | perm.granted_mana()
            c = perm.card
            if c.mana_fixer and any(x is not perm and x.card.produces & c.mana_fixer for x in p.battlefield):
                produces = produces | c.mana_fixer
            if c.mana_filter == "once" and perm.ability_turns.get("filter") == self.turn:
                continue
            if c.mana_cond and not any(c.mana_cond in x.card.subtypes for x in p.battlefield):
                continue
            if c.mana_tap_other and not any(x is not perm and not x.tapped and (x.is_creature or c.mana_tap_other == "permanent")
                                            for x in p.battlefield):
                continue
            perm.amount_now = None
            if perm.card.restricted_produces and self.mana_allowed(perm, spell):
                if perm.card.restricted_amount > max(1, perm.card.mana_amount):
                    produces, perm.amount_now = perm.card.restricted_produces, perm.card.restricted_amount
                else:
                    produces = produces | perm.card.restricted_produces
            if not produces:
                continue
            perm.produces_now = produces
            out.append(perm)
        for mana in p.pool:
            if not mana.tapped and mana is not exclude:
                mana.produces_now = mana.card.produces
                out.append(mana)
        stored = storage.stored_sources(p, exclude, lambda r: self.mana_allowed(None, spell, r),
                                        reserved_counters=reserved_counters)
        if stored:                                  # a storage land spends its counters instead of its own mana
            lands = {id(m.stored_in) for m in stored}
            out = [s for s in out if id(s) not in lands] + stored
        return out

    def mana_allowed(self, perm: Permanent, spell, restriction: str = "") -> bool:
        """Whether perm's restricted mana (or this restriction) may pay for spell (see mana_sources)."""
        if spell is None:
            return True
        if not isinstance(spell, CardDef):
            return False
        r = restriction or perm.card.mana_restriction
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

    def nonmana_locked(self, player):
        return player.action_lock_turn == self.turn

    def activations_stopped(self) -> bool:
        """Clarion Conqueror: activated abilities of artifacts, creatures and planeswalkers can't be activated."""
        return any(x.card.stops_activations for pl in self.players for x in pl.battlefield)

    def can_pay(self, p: Player, cost: dict, extra=None, spell=None) -> bool:
        sources = self.mana_sources(p, spell=spell) + ([extra] if extra else [])
        return payable(sources, cost)

    def spell_payable(self, p: Player, card: CardDef) -> bool:
        cost = self.cost_of(p, card, assist=False)
        convoked = self.convoke_pool(p)[:self._convoke_k] if card.convoke else []
        cost, improvised, _ = self.assist_payment(p, card, cost) if card.improvise or card.delve else (cost, [], [])
        return costs.spell_plan(self, p, card, cost, exclude=convoked + improvised) is not None

    @staticmethod
    def _needed_color(p, source, payment, cost) -> bool:
        """Whether the payment needs source's colored mana (it couldn't be paid with {C} from it)."""
        saved = getattr(source, "produces_now", None)
        source.produces_now = frozenset({"C"})
        try:
            return find_payment(list(payment), cost) is None
        finally:
            source.produces_now = saved

    def pay(self, p: Player, cost: dict, exclude=None, spell="ability", *, exclude_many=(), reserved_counters=()) -> list | None:
        """Tap sources for cost (sacrificing Treasure). Returns the sources, or None if unpayable."""
        payment = find_payment([s for s in self.mana_sources(p, exclude, spell, reserved_counters=reserved_counters)
                                if s not in exclude_many and getattr(s, 'stored_in', None) not in exclude_many], cost)
        if payment is None:
            return None
        for s in payment:
            if getattr(s, "stored_in", None) is not None:
                storage.spend(s)
                continue
            if s.card.color_skips_untap and self._needed_color(p, s, payment, cost):
                s.skip_untap = max(s.skip_untap, 1)   # its colored mana was spent: it skips its next untap
            if s.card.mana_filter == "once":
                s.ability_turns["filter"] = self.turn
            else:
                s.tapped = True
            if s.card.token_kind == "treasure" or s.card.mana_sac or s.card.mana_sac_only:
                self.sacrifice(s)
            if s.card.mana_tap_other:
                spare = [x for x in p.battlefield if x is not s and not x.tapped and x not in payment
                         and x not in exclude_many
                         and (x.is_creature or s.card.mana_tap_other == "permanent")]
                if spare:
                    min(spare, key=perm_value).tapped = True
        spent = getattr(p, "expend", (0, 0))
        old = spent[1] if spent[0] == self.turn else 0
        p.expend = (self.turn, old + len(payment))
        for n in range(old + 1, old + len(payment) + 1):
            self.fire(p, "expend", subject=n)
        return payment

    def x_quantity(self, p: Player, spec: tuple, item, prev) -> int:
        """The value of X in ", where X is ..." (see cards._xq)."""
        kind = spec[0]
        src = item.source if item is not None and isinstance(item.source, Permanent) else None
        if kind == "life":
            return max(0, p.life)
        if kind == "speed":
            return p.speed
        if kind == "gained":
            return p.life_gained_turn
        if kind == "hand":
            return len(p.hand)
        if kind == "stat":
            who = prev if spec[1] == "prev" else src
            if spec[2] == "mana value":
                return item.card.cmc if spec[1] == "self" and item is not None and item.card else 0
            return max(0, getattr(who, spec[2], 0)) if isinstance(who, Permanent) else 0
        if kind == "greatest":
            return max((getattr(x, spec[1]) for x in p.creatures), default=0)
        if kind == "counters":
            return src.counters.get(spec[1], 0) if src is not None else 0
        if kind == "gy":
            return counting.count(self, p, {"what": spec[1], "zone": "graveyard"}, src)
        return counting.count(self, p, {"what": spec[1], "zone": "battlefield"}, src)

    def gy_move(self, p: Player, eff: Effect, item):
        """"Return up to N target <description> cards from your/a graveyard to your hand/the battlefield"."""
        d = eff.data
        zones = {"mine": [p], "opp": [self.opponent(p)], "any": [p, self.opponent(p)]}[d["zone"]]
        cands = []
        for owner in zones:
            for c in owner.graveyard:
                if not copies.fits(c, _gy_desc(d["what"])):
                    continue
                if d["cmc"]:
                    lim, cmp = d["cmc"]
                    lim = getattr(item, "x", 0) if lim == "x" else lim
                    if (c.cmc > lim) if cmp == "less" else (c.cmc < lim):
                        continue
                cands.append((owner, c))
        n = eff.amount
        if d["x_n"]:
            n = getattr(item, "x", 0)
        if d["dest"] == "bf":
            cands = [(o, c) for o, c in cands if c.is_permanent]
        cands.sort(key=lambda oc: -oc[1].cmc)
        if eff.amount == 99:
            picked = list(cands)
        else:
            picked = []
            names = set()
            for o, c in cands:
                if len(picked) >= n:
                    break
                if d.get("distinct") and c.name in names:
                    continue
                names.add(c.name)
                picked.append((o, c))
        for owner, card in picked:
            owner.graveyard.remove(card)
        for owner, card in picked:
            if d["dest"] == "hand":
                p.hand.append(card)
                self.log(f"returns {card.name} to hand", p)
            else:
                self.enter_battlefield(p, card, tapped=d["tapped"], counters=returns.entry_counters(eff, item))
                self.log(f"returns {card.name} to the battlefield", p)

    def commits_crime(self, p: Player, targets) -> bool:
        """Whether a spell or ability with these targets is a crime: it targets an opponent, their permanent or
        a card in their graveyard."""
        opp = self.opponent(p)
        for t in targets or ():
            if t is opp or (isinstance(t, Permanent) and t.controller is opp) or \
                    (isinstance(t, CardDef) and t in opp.graveyard):
                return True
        return False

    def pay_gate_cost(self, p: Player, gate: tuple, item) -> bool:
        """Pay a "you may sacrifice / discard / forage / blight N. If you do, ..." cost when it is cheap for the AI."""
        kind, what = gate
        if kind == "may":
            return True
        if kind == "life":
            from ..residual_templates import life_locked
            if life_locked(p):
                return False
            # "you may pay N life": while it stays comfortable
            if p.life - int(what) < 8:
                return False
            self.change_life(p, -int(what), "paid life")
            return True
        src = item.source if item is not None and isinstance(item.source, Permanent) else None
        if kind == "sac":
            other = what.startswith("other ")
            kinds = tuple(what[6:].split(" or ")) if other else tuple(what.split(" or "))
            spare = [x for x in p.battlefield if not (other and x is src)
                     and any(card_matches(x.card, "a " + k.strip()) or (k.strip() == "token" and x.card.is_token)
                             for k in kinds)
                     and (x.card.is_token or perm_value(x) <= 2)]
            if not spare:
                return False
            self.sacrifice(min(spare, key=perm_value))
            return True
        if kind == "discard":
            if not p.hand or not (len(p.hand) >= 4 or (any(c.is_land for c in p.hand)
                                                       and sum(x.card.is_land for x in p.battlefield) >= 5)):
                return False
            self.discard_card(p, p.ai.choose_discard(self, p))
            return True
        if kind == "forage":
            if len(p.graveyard) >= 3:
                for c in list(p.graveyard)[:3]:
                    p.graveyard.remove(c)
                    p.exile.append(c)
                return True
            foods = [x for x in p.battlefield if x.card.token_kind == "food"]
            if foods:
                self.sacrifice(foods[0])
                return True
            return False
        if kind == "blight":
            n = int(what)
            victims = [x for x in p.creatures if x.toughness > n and (x.card.is_token or perm_value(x) <= 3)]
            if not victims:
                return False
            v = min(victims, key=perm_value)
            v.counters["-1/-1"] = v.m1 + n
            return True
        return False

    def pay_bargain(self, p: Player, card: CardDef) -> bool:
        """Sacrifice a spare artifact, enchantment or token (the cheapest) for Bargain; False if there is none worth it."""
        spare = [x for x in p.battlefield if (x.card.is_token or x.card.is_artifact or "Enchantment" in x.card.types)
                 and perm_value(x) <= 3]
        if not spare:
            return False
        self.sacrifice(min(spare, key=perm_value))
        self.log(f"bargains {card.name}", p)
        return True

    def give_gift(self, p: Player, kind: str):
        """The opponent receives the gift promised with a Gift spell."""
        opp = self.opponent(p)
        self.log(f"promises a gift ({kind})", p)
        if kind == "card":
            self.draw(opp, 1)
        elif kind in ("food", "treasure"):
            self.enter_battlefield(opp, make_token("", 0, 0, (), None, kind, True))
        elif kind == "tapped fish":
            self.enter_battlefield(opp, make_token("Fish", 1, 1)).tapped = True
        elif kind == "octopus":
            self.enter_battlefield(opp, make_token("Octopus", 8, 8))

    def collect_evidence(self, p: Player, card: CardDef) -> bool:
        """Exile graveyard cards worth card.collect_evidence mana value, if p can; False otherwise."""
        need = card.collect_evidence
        if not need or sum(c.cmc for c in p.graveyard) < need:
            return False
        total = 0
        for c in sorted(p.graveyard, key=lambda c: -c.cmc):
            if total >= need:
                break
            p.graveyard.remove(c)
            p.exile.append(c)
            total += c.cmc
        self.log(f"collects evidence {need}", p)
        return True

    def spare_cards(self, p: Player, card: CardDef) -> int:
        """Cards in hand that could be discarded to cast card (not card itself)."""
        return len(p.hand) - (1 if self._zone(p, self._origin(card)[1]) is p.hand else 0)

    def tapped_targets(self, p: Player, card: CardDef) -> list:
        """Tapped opposing creatures a "costs less if it targets a tapped creature" spell could aim at."""
        eff = next((e for e in card.spell_effects if e.target in TARGETED), None)
        if eff is None:
            return []
        return [t for t in self.legal_targets(p, eff)
                if isinstance(t, Permanent) and t.is_creature and t.tapped and t.controller is not p]

    def discount_targets(self, p: Player, card: CardDef) -> list:
        """Creatures a "costs less if it targets ..." spell could aim at."""
        eff = next((e for e in card.spell_effects if e.target in TARGETED), None)
        if eff is None:
            return []
        return [t for t in self.legal_targets(p, eff) if isinstance(t, Permanent) and t.is_creature]

    def cost_of(self, p: Player, card: CardDef, *, assist=True) -> dict:
        """The mana cost after cost reductions (Tolarian Terror, Ghalta)."""
        cost = dict(card.mana_cost)
        n = 0
        if card.cost_reduction == "instant_sorcery_gy":
            n = sum(c.is_instant or c.is_sorcery for c in p.graveyard)
        elif card.cost_reduction == "instant_sorcery_adventure_gy":
            n = sum(c.is_instant or c.is_sorcery or c.adventure is not None for c in p.graveyard)
        elif card.cost_reduction == "greatest_elemental":
            n = max((x.card.cmc for x in p.battlefield if "Elemental" in x.card.subtypes), default=0)
        elif card.cost_reduction == "power":
            n = sum(max(0, c.power) for c in p.creatures)
        elif card.cost_reduction.startswith("gy:"):
            n = sum(copies.fits(c, _gy_desc(card.cost_reduction[3:])) for c in p.graveyard)
        elif card.cost_reduction.startswith("affinity:"):
            n = sum(card_matches(x.card, "a " + card.cost_reduction[9:]) for x in p.battlefield)
        for x in p.battlefield:
            for flt, k in x.card.cost_discount:
                if flt.startswith("has_adventure:"):
                    scope = flt.split(":", 1)[1]
                    if card.adventure is not None and (scope == "all" or scope == "permanent" and card.is_permanent or
                                                      scope.capitalize() in card.types):
                        n += k
                    continue
                if (flt in ("instant and sorcery",) and (card.is_instant or card.is_sorcery)) or \
                        (flt in COLOR_WORDS and COLOR_WORDS[flt] in card.colors) or \
                        (flt in ("creature", "artifact") and flt.capitalize() in card.types) or \
                        (flt == "noncreature" and not card.is_creature and not card.is_land) or \
                        (flt not in COLOR_WORDS and flt.capitalize() in card.subtypes):
                    n += k
        counts = getattr(self, "spells_cast", {})
        if counts.get("turn") == self.turn and counts.get(p.name, 0) == 1:
            n += sum(x.card.second_spell_discount for x in p.battlefield)
        for sub, k in card.discount_if:
            if any(sub in x.card.subtypes for x in p.battlefield):
                n += k
        if card.tapped_discount and self.tapped_targets(p, card):
            n += card.tapped_discount
        for key, k in card.cond_discount:
            if discounts.holds(self, p, card, key):
                n += k
        for key, k in card.per_discount:
            n += k * discounts.count(self, p, key)
        cost["generic"] = max(0, cost.get("generic", 0) - n)
        if card.extra_discard and card.discard_or_pay and self.spare_cards(p, card) < 1:
            cost["generic"] += card.discard_or_pay
        if card.behold_or_pay:
            sub, tax = card.behold_or_pay
            if not (any(sub in x.card.subtypes for x in p.battlefield) or
                    any(sub in c.subtypes for c in p.hand if c is not card)):
                cost["generic"] += tax
        if card.convoke:
            self._convoke_k = min(len(self.convoke_pool(p)), cost.get("generic", 0))
            cost["generic"] -= self._convoke_k
        if card.extra_sac_or_pay and not self.extra_sac_candidates(p, card):
            cost["generic"] += card.extra_sac_or_pay
        if assist and (card.improvise or card.delve):
            cost = self.assist_payment(p, card, cost)[0]
        if getattr(card, "spell_copy", False):
            return {"generic": 0}
        if self._origin(card)[1].startswith("foreign_"):
            return {"generic": sum(v for k, v in cost.items() if k != "X")}
        return cost

    def assist_payment(self, p: Player, card: CardDef, cost: dict):
        """Plan generic payments without spending resources or sharing a tapped source."""
        cost = dict(cost)
        sources = self.mana_sources(p, spell=card)
        colored = find_payment(sources, {k: n for k, n in cost.items() if k not in ("generic", "X")})
        if colored is None:
            return cost, [], []
        reserved = self.convoke_pool(p)[:self._convoke_k] if card.convoke else []
        for mana in colored:
            if mana.card.mana_tap_other:
                helpers = [x for x in p.battlefield if not x.tapped and x not in colored and x not in reserved
                           and (x.is_creature or mana.card.mana_tap_other == "permanent")]
                if helpers:
                    reserved.append(min(helpers, key=perm_value))
        artifacts = sorted((x for x in p.battlefield if card.improvise and x.card.is_artifact
                            and not x.tapped and x not in colored and x not in reserved
                            and not (x in sources and (x.amount_now or x.card.mana_amount) > 1)),
                           key=lambda x: (x in sources, x.is_creature, x.card.cmc))
        improvised = artifacts[:cost.get("generic", 0)]
        cost["generic"] = cost.get("generic", 0) - len(improvised)
        grave = list(p.graveyard) if card.delve else []
        base, kind, _ = self._origin(card)
        if self._zone(p, kind) is p.graveyard and base in grave:
            grave.remove(base)  # the spell being cast cannot pay for itself
        grave.sort(key=lambda c: (bool(c.gy_activated or c.alt_costs), c.is_creature, c.cmc))
        delved = grave[:cost["generic"]]
        cost["generic"] -= len(delved)
        return cost, improvised, delved

    def _variant(self, card: CardDef, kind: str, alt: AltCost | None = None) -> CardDef:
        key = (getattr(card, "physical_id", id(card)), getattr(card, "generation", 0), kind)
        if key not in self._variants:
            if kind == "adventure":
                v = dataclasses.replace(card.adventure)
            elif kind == "prepared":
                v = dataclasses.replace(card.back, name=f"{card.name} (prepared)")
            elif kind in ("split", "aftermath"):
                v = dataclasses.replace(card.split_right, name=f"{card.name} ({card.split_right.name})")
            elif kind == "disturb":
                v = dataclasses.replace(card.back, name=f"{card.back.name} (disturb)", mana_cost=alt.cost)
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
            v.origin_generation = getattr(card, "generation", None)
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
        full = any(self.spell_payable(p, v) for v in out)
        for a in c.alt_costs:
            if a.kind == "offspring":
                out.append(self._variant(c, "offspring", AltCost("offspring", add_mana(c.mana_cost, a.cost))))
            elif a.kind in ("split", "fuse"):
                out.append(self._variant(c, a.kind, a))
            elif a.kind in FACE_DOWN and not full:
                out.append(self._variant(c, a.kind, AltCost(a.kind, {"generic": 3})))
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

    def spells_cast_turn(self, p: Player) -> int:
        counts = getattr(self, "spells_cast", {})
        return counts.get(p.name, 0) if counts.get("turn") == self.turn else 0

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
            out += alt_casts.variants(self, p, c)
            if c.adventure:
                out.append(self._variant(c, "adventure"))
            for a in c.alt_costs:
                if a.kind in ("alt", "kicker") or (a.kind == "spectacle" and opp.lost_life_turn) or \
                        (a.kind in ("blitz", "dash") and "hand" in a.zone):
                    out.append(self._variant(c, a.kind, a))
        out += [self._variant(x.front, "prepared") for x in p.battlefield if x.prepared and x.card.back is not None]
        out += [self._variant(c, "from_adventure") for c in p.on_adventure]
        out += [self._variant(c, "plotted", AltCost("plotted", {"generic": 0})) for c in p.plotted
                if p.exiled_turn.get(c.name, 0) < self.turn]
        out += [self._variant(c, "airbent", AltCost("airbent", {"generic": 2})) for c in p.airbent]
        out += [self._variant(c, "from_warp") for c in p.warp_exile if p.exiled_turn.get(c.name, 0) < self.turn]
        for c in p.foretold:
            a = next(a for a in c.alt_costs if a.kind == "foretell")
            out.append(self._variant(c, "foretold", a))
        for c in self.impulse_cards(p):
            if not c.is_land:
                out.append(self._variant(c, "impulse"))
        for c in p.granted_fb:
            if c in p.graveyard:
                out.append(self._variant(c, "flashback", AltCost("flashback", dict(c.mana_cost))))
        for c in p.graveyard:
            out += alt_casts.graveyard_variants(self, p, c)
            for a in c.alt_costs:
                if a.kind in ("flashback", "gy_ability", "unearth") or (a.kind == "disturb" and c.back is not None) or \
                        (a.kind == "blitz" and "graveyard" in a.zone) or \
                        (a.kind == "mayhem" and c in p.discarded_cards):
                    out.append(self._variant(c, "blitz_gy" if a.kind == "blitz" else a.kind, a))
        from ..advanced_templates import permission_options
        return out + permission_options(self, p)

    def impulse_cards(self, p: Player) -> list:
        """Exiled cards p may still play (drops the expired ones)."""
        p.impulse = [(c, t) for c, t in p.impulse if t >= self.turn and c in p.exile]
        return [c for c, _ in p.impulse]

    def _origin(self, card: CardDef):
        return getattr(card, "origin", None) or (card, "", None)

    def _zone(self, p: Player, kind: str) -> list:
        """The zone a spell_options() variant of this kind is cast from."""
        if kind.startswith("foreign_"):
            return getattr(self, "foreign_zones", {}).get((id(p), kind), p.exile)
        return {"grave_permission": p.graveyard, "aftermath": p.graveyard, "from_adventure": p.on_adventure, "foretold": p.foretold, "flashback": p.graveyard,
                "blitz_gy": p.graveyard, "gy_ability": p.graveyard, "plotted": p.plotted, "from_warp": p.warp_exile, "airbent": p.airbent,
                "mayhem": p.graveyard, "unearth": p.graveyard, "disturb": p.graveyard, "jump_start": p.graveyard,
                "retrace": p.graveyard,
                "escape": p.graveyard, "impulse": p.exile, "suspended": p.exile, "rebound": p.exile,
                "cascade": p.exile, "cascade_adventure": p.exile,
                "rebound_adventure": p.exile, "discover": p.exile}.get(kind, p.hand)

    def _available(self, p: Player, card: CardDef) -> bool:
        base, kind, _ = self._origin(card)
        from ..advanced_templates import permission_available
        if not permission_available(self, p, card, kind):
            return False
        generation = getattr(card, "origin_generation", None)
        if generation is not None and generation != getattr(base, "generation", None):
            return False
        if kind == "prepared":
            return any(x.front is base and x.prepared for x in p.battlefield)
        return base in self._zone(p, kind)

    def can_cast_now(self, p: Player, card: CardDef, *, during_resolution=False) -> bool:
        """Timing, mana, zone and (for counterspells) a spell to target."""
        if self.nonmana_locked(p) and (card.is_instant or card.is_sorcery):
            return False
        from ..advanced_templates import cast_allowed
        if not cast_allowed(self, p, card):
            return False
        if card.is_land or not self._available(p, card):
            return False
        base, kind, alt = self._origin(card)
        if self.nonmana_locked(p) and kind in ('channel', 'gy_ability', 'unearth'):
            return False
        if kind == "spectacle" and not self.opponent(p).lost_life_turn:
            return False
        from ..residual_templates import life_locked
        if life_locked(p) and (card.extra_life_cost or alt is not None and alt.life):
            return False
        if alt is not None and alt.life and p.life <= alt.life:
            return False
        if card.extra_life_cost and p.life <= card.extra_life_cost:
            return False
        if card.extra_discard and not card.discard_or_pay and self.spare_cards(p, card) < 1:
            return False
        if self.active is not p and any(x.card.opp_no_cast for x in self.opponent(p).battlefield):
            return False
        if card.extra_sacrifice and not card.extra_sac_or_pay and not self.extra_sac_candidates(p, card):
            return False
        if card.aura and not auras.hosts(self, p, card):
            return False
        if not during_resolution and not card.instant_speed and not (p is self.active and self.step in ("main1", "main2")
                                           and not self.stack):
            return False
        if any(e.target == "spell" for e in card.spell_effects):
            if not any(self.can_counter(e, item, p) for e in card.spell_effects if e.kind == "counter"
                       for item in self.stack):
                return False
        return self.spell_payable(p, card)
