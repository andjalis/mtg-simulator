"""Game methods for playing cards: lands, casting, plot, foretell and station."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .. import alt_casts, cast_triggers, copies, statics
from ..cards import CardDef
from .. import modal, rules_events, costs
from ..actions import atomic_action
from .mana import payable
from .policy import perm_value
from .state import OUTLAWS, Permanent, StackItem, TARGETED

if TYPE_CHECKING:
    from .state import Player


SPELL_KINDS = {   # "Whenever you cast a multicolored / historic / blue ... spell"
    "multicolored": lambda c: len(c.colors) >= 2,
    "colorless": lambda c: not c.colors,
    "historic": lambda c: c.is_artifact or c.legendary or c.is_saga,
    **{word: (lambda col: lambda c: col in c.colors)(col)
       for word, col in (("white", "W"), ("blue", "U"), ("black", "B"), ("red", "R"), ("green", "G"))},
}


class PlayMixin:
    def play_land(self, p: Player, card: CardDef, back: bool = False):
        """Play a land from hand; with back=True, a modal double-faced card's land face."""
        for zone in (p.hand, p.exile, p.graveyard):
            if card in zone:
                card = zone.get(card)
                break
        face = card.land_face if back else card
        assert face is not None and face.is_land and not p.land_played
        if card in p.hand:
            p.hand.remove(card)
        elif card in p.exile and card in self.impulse_cards(p):
            p.exile.remove(card)
        else:   # "You may play lands from your graveyard."
            assert any(x.card.lands_from_gy for x in p.battlefield)
            p.graveyard.remove(card)
        p.lands_played += 1
        self.log(f"plays {face.name}", p)
        self.enter_battlefield(p, face, physical_card=card)
        self.settle()

    def convoke_pool(self, p: Player) -> list:
        """Creatures that can be tapped to convoke without costing us an attack or block: summoning-sick ones,
        or any untapped creature once combat is over."""
        late = self.step in ("main2", "end_step")
        return [c for c in p.creatures if not c.tapped and (c.sick or late)]

    def pay_teamwork(self, p: Player, card: CardDef) -> bool:
        """Tap creatures with total power of card.teamwork or more (smallest first; summoning-sick ones are free
        to tap). Only done when the creatures can't usefully attack: they are sick, or it's after combat."""
        pool = [c for c in p.creatures if not c.tapped and (c.sick or self.step in ("main2", "end_step"))]
        pool.sort(key=lambda c: c.power)
        chosen, total = [], 0
        for c in pool:
            if total >= card.teamwork:
                break
            chosen.append(c)
            total += c.power
        if total < card.teamwork:
            return False
        for c in chosen:
            c.tapped = True
        self.log(f"taps {[c.card.name for c in chosen]} (teamwork {card.teamwork})", p)
        return True

    @atomic_action
    def cast(self, p: Player, card: CardDef, targets: list | None = None) -> bool:
        """Pay for card and put it on the stack. ``card`` may be a hand card or one of
        spell_options() (adventure, flashback, ...). Outside a priority loop (an AI's main
        phase) the stack is then resolved, with the opponent able to respond, before
        returning. Timing isn't checked here; AIs should use can_cast_now."""
        base, kind, alt = self._origin(card)
        if not self.can_cast_now(p, card, during_resolution=True):
            return False
        zone = self._zone(p, kind)
        if base in zone:
            actual = zone.get(base)
            if card is base:
                card = actual
            else:
                card.origin = (actual, kind, alt)
            base = actual
        effects = [] if card.is_permanent else list(card.spell_effects)
        targets = list(targets or [])
        targets += [None] * (len(effects) - len(targets))
        if card.tapped_discount and not card.is_permanent:
            tapped = self.tapped_targets(p, card)
            idx = next((i for i, e in enumerate(effects) if e.target in TARGETED), None)
            if tapped and idx is not None and targets[idx] not in tapped:
                targets[idx] = max(tapped, key=perm_value)
        missing = [i for i, e in enumerate(effects) if e.target in TARGETED and targets[i] is None]
        if missing:   # targets the AI didn't pick (effects it doesn't know about)
            filled = self.auto_targets(p, [effects[i] for i in missing], card)
            for i, t in zip(missing, filled):
                targets[i] = t
        if not self.valid_action_targets(p, effects, targets, card):
            return False
        cost = self.cost_of(p, card, assist=False)
        convoked = self.convoke_pool(p)[:self._convoke_k] if card.convoke else []
        assisted = card.improvise or card.delve
        x = 0
        if assisted and "X" in card.mana_cost:
            for n in range(1, 21):
                trial = dict(cost, generic=cost.get("generic", 0) + n)
                remaining, tapped, _ = self.assist_payment(p, card, trial)
                if costs.spell_plan(self, p, card, remaining, exclude=convoked + tapped) is None:
                    break
                x = n
            cost["generic"] = cost.get("generic", 0) + x
        cost, improvised, delved = self.assist_payment(p, card, cost) if assisted else (cost, [], [])
        plan = costs.spell_plan(self, p, card, cost, exclude=convoked + improvised)
        if plan is None:
            return False
        cost = plan.cost
        payment = self.pay(p, cost, spell=card, exclude_many=plan.exclude)
        if payment is None:
            return False
        for c in convoked:
            c.tapped = True
        for artifact in improvised:
            artifact.tapped = True
            self.fire(p, "becomes_tapped", artifact)
        for c in delved:
            p.graveyard.remove(c)
            p.exile.append(c)
        if "X" in card.mana_cost and not assisted:     # X: as much as the remaining mana allows
            while x < 20 and payable([s for s in self.mana_sources(p, spell=card) if s not in plan.exclude], {"generic": x + 1}):
                x += 1
            if x:
                payment += self.pay(p, {"generic": x}, spell=card, exclude_many=plan.exclude)
        if alt is not None and alt.life:
            self.change_life(p, -alt.life, f"{card.name}: alternative cost")
        if card.extra_life_cost:
            self.change_life(p, -card.extra_life_cost, f"{card.name}: additional cost")
        if plan.sacrifice is not None:
            victim = plan.sacrifice
            if victim not in p.battlefield:
                return False
            self.log(f"sacrifices {victim.card.name} for {card.name}", p)
            self.sacrifice(victim)
        if kind == "prepared":
            next(x for x in p.battlefield if x.front is base and x.prepared).prepared = False
        elif kind in ("rebound", "cascade", "cascade_adventure", "rebound_adventure"):
            del p.exile[next(i for i, c in enumerate(p.exile) if c is base)]
        else:
            self._zone(p, kind).remove(base)
        if card.extra_discard and not card.discard_or_pay and not p.hand:
            return False
        if kind == "escape":
            alt_casts.pay_escape(self, p, base, alt)
        if kind == "alt_sac":               # "You may sacrifice a Mountain rather than pay ~'s mana cost"
            pool = sorted((x for x in p.battlefield if statics.desc_matches(x, alt.cond)), key=lambda x: (not x.tapped, perm_value(x)))
            for x in pool[:alt.counters]:
                self.sacrifice(x)
        if card.extra_discard and p.hand:
            lands = [c for c in p.hand if c.is_land]
            pitched = (lands[-1] if lands else None) if kind == "retrace" else p.ai.choose_discard(self, p)
            if pitched not in p.hand:
                return False
            self.discard_card(p, pitched)
            self.log(f"discards {pitched.name} for {card.name}", p)
        if kind == "channel":
            p.graveyard.append(base)
        elif kind == "gy_ability":
            p.exile.append(base)
        flags = set()
        teamwork_paid = False
        if card.teamwork and (card.modes or any(e.data.get("tw") for e in effects)) and self.pay_teamwork(p, card):
            flags.add("teamwork")
            teamwork_paid = True
        if card.modes:
            if kind == "entwine":       # all of the modes: a plain list, without the printed "choose one" spec
                mode_effects = modal.pick(self, p, list(card.modes), n=len(card.modes), flags=flags)
            else:
                mode_effects = modal.pick(self, p, card.modes, n=card.modes_choose, flags=flags)
            effects = mode_effects + effects
            mode_targets = self.auto_targets(p, mode_effects, card)
            if not self.valid_action_targets(p, mode_effects, mode_targets, card):
                return False
            targets = mode_targets + targets
        item = StackItem(p, effects, targets, card=card, kind="spell")
        # Prepared spells are copies; channel/graveyard abilities leave their
        # physical source in its actual zone rather than moving it onto the stack.
        item.physical_card = base if kind not in ("prepared", "channel", "gy_ability") else None
        if item.physical_card is not None:
            item.move_origin = base.pending_move
            base.pending_move = None
            base.generation += 1
            base.zone = item
        item.cast_from_hand = self._zone(p, kind) is p.hand and kind not in ("free", "channel", "gy_ability", "prepared")
        item.snow_spent = sum(1 for s in payment if s.card.snow)
        item.x = x
        item.teamwork = teamwork_paid
        item.evidence = self.collect_evidence(p, card)
        item.bargained = bool(card.bargain) and self.pay_bargain(p, card)
        item.gifted = bool(card.gift)
        item.uncounterable = any(s.card.mana_restriction == "chosen_type" and self.mana_allowed(s, card)
                                 for s in payment)
        item.mana_spent = sum(v for k, v in cost.items() if k != "X")
        if card.is_ability:
            item.kind = "channel"
            item.card = None
            item.name = card.name
        self.stack.append(item)
        if item.physical_card is not None and item.move_origin is not None:
            before, origin, actor, _, _ = item.move_origin
            self.rule_events.emit(rules_events.RulesEvent("zone_change", p, subject=base,
                before=before, source_zone=origin, destination="stack", reason="cast"))
        self.log(f"casts {card.name}" + (f" -> {targets}" if any(targets) else ""), p)
        if self.commits_crime(p, targets):
            self.fire(p, "crime")
        if not card.is_ability:
            for perm in list(p.battlefield):
                for trig in perm.triggers:
                    flt = trig.filter
                    if flt.startswith("spell:") and flt[6:] in SPELL_KINDS:
                        if not SPELL_KINDS[flt[6:]](card):
                            continue
                    elif flt.startswith("spell:") and not (flt[6:] in card.subtypes or
                                                         flt[6:].capitalize() in card.types or
                                                         (flt[6:].lower() == "outlaw" and any(
                                                             o in card.subtypes for o in OUTLAWS))):
                        continue
                    if trig.event == "cast_cmc" and card.cmc < int(trig.filter[5:]):
                        continue
                    if flt == "opp_turn" and p is self.active:
                        continue
                    if flt == "targets_creature" and not any(isinstance(t, Permanent) and t.is_creature
                                                            for t in targets):
                        continue
                    if (trig.event in ("cast_spell", "cast_cmc") or
                            (trig.event == "cast_noncreature" and not card.is_creature) or
                            (trig.event == "cast_instant_sorcery" and (card.is_instant or card.is_sorcery))):
                        self.queue_trigger(p, trig.effects, perm, perm.card.name, modes=trig.modes,
                                           context=item if copies.wants_spell(trig.effects) else None)
            copies.on_cast(self, p, item)
            cast_triggers.on_cast(self, p, item)
            alt_casts.replicated(self, p, item, kind)
            for trig in card.cast_self_triggers:
                self.queue_trigger(p, trig.effects, None, f"{card.name}: cast trigger", context=item)
            if self.spells_cast.get(p.name) == 2:
                self.fire(p, "cast_second")
            for pl in self.players:
                self.fire(pl, "any_cast", context=p, subject=card)
        self.check_ward(item)
        self.settle()
        return True

    def craft_materials(self, p: Player, perm: Permanent) -> list:
        """What perm could exile to craft: artifact cards in the graveyard first, then artifact tokens,
        then the cheapest other artifacts."""
        gy = [c for c in p.graveyard if c.is_artifact]
        others = sorted((x for x in p.battlefield if x is not perm and x.card.is_artifact and not x.is_creature),
                        key=lambda x: (not x.card.is_token, x.card.cmc))
        return gy + others

    def station(self, p: Player, perm: Permanent, creature: Permanent) -> bool:
        """Station: tap another untapped creature to put charge counters equal to its power (sorcery speed)."""
        if not perm.card.station or creature is perm or creature.tapped or not creature.is_creature or \
                creature not in p.battlefield or not (p is self.active and self.step in ("main1", "main2")):
            return False
        creature.tapped = True
        perm.counters["charge"] = perm.counters.get("charge", 0) + max(0, creature.power)
        self.log(f"stations {perm.card.name} with {creature.card.name}", p)
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
