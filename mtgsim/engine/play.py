"""Game methods for player actions: lands, casting, abilities, equip, entering the battlefield, tokens."""
from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from .. import auras, cast_triggers, copies, counters_r3, proliferate
from ..cards import Activated, CardDef, Effect, make_token
from .. import modal, rules_events
from ..identity import CardInstance, instance
from ..actions import atomic_action
from .mana import payable
from .policy import choose_color, default_choose_target, perm_value, saddle_creatures
from .state import OUTLAWS, Permanent, StackItem, TARGETED, can_block, is_basic_land

if TYPE_CHECKING:
    from .state import Player


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
        provided_targets = len(targets) if targets is not None else 0
        targets = list(targets or [])
        targets += [None] * (len(effects) - len(targets))
        if card.tapped_discount and not card.is_permanent:
            tapped = self.tapped_targets(p, card)
            idx = next((i for i, e in enumerate(effects) if e.target in TARGETED), None)
            if tapped and idx is not None and targets[idx] not in tapped:
                targets[idx] = max(tapped, key=perm_value)
        missing = [i for i, e in enumerate(effects) if e.target in TARGETED and targets[i] is None
                   and (i >= provided_targets or not e.data.get("optional"))]
        if missing:   # targets the AI didn't pick (effects it doesn't know about)
            filled = self.auto_targets(p, [effects[i] for i in missing])
            for i, t in zip(missing, filled):
                targets[i] = t
        if not self.valid_action_targets(p, effects, targets):
            return False
        sacrifice_required = bool(card.extra_sacrifice and self.extra_sac_candidates(p, card))
        cost = self.cost_of(p, card, assist=False)
        convoked = self.convoke_pool(p)[:self._convoke_k] if card.convoke else []
        assisted = card.improvise or card.delve
        x = 0
        if assisted and "X" in card.mana_cost:
            for n in range(1, 21):
                trial = dict(cost, generic=cost.get("generic", 0) + n)
                remaining, tapped, _ = self.assist_payment(p, card, trial)
                if not payable([s for s in self.mana_sources(p, spell=card) if s not in tapped], remaining):
                    break
                x = n
            cost["generic"] = cost.get("generic", 0) + x
        cost, improvised, delved = self.assist_payment(p, card, cost) if assisted else (cost, [], [])
        payment = self.pay(p, cost, spell=card, exclude_many=improvised)
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
            while x < 20 and payable(self.mana_sources(p, spell=card), {"generic": x + 1}):
                x += 1
            if x:
                payment += self.pay(p, {"generic": x}, spell=card)
        if alt is not None and alt.life:
            self.change_life(p, -alt.life, f"{card.name}: alternative cost")
        if card.extra_life_cost:
            self.change_life(p, -card.extra_life_cost, f"{card.name}: additional cost")
        if sacrifice_required and not self.extra_sac_candidates(p, card):
            return False
        if sacrifice_required:
            victim = self.extra_sac_candidates(p, card)[0]
            self.log(f"sacrifices {victim.card.name} for {card.name}", p)
            self.sacrifice(victim)
        if kind == "prepared":
            next(x for x in p.battlefield if x.card is base and x.prepared).prepared = False
        elif kind in ("rebound", "cascade", "cascade_adventure", "rebound_adventure"):
            del p.exile[next(i for i, c in enumerate(p.exile) if c is base)]
        else:
            self._zone(p, kind).remove(base)
        if card.extra_discard and not card.discard_or_pay and not p.hand:
            return False
        if card.extra_discard and p.hand:
            pitched = p.ai.choose_discard(self, p)
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
            mode_effects = modal.pick(self, p, card.modes, n=card.modes_choose, flags=flags)
            effects = mode_effects + effects
            mode_targets = self.auto_targets(p, mode_effects)
            if not self.valid_action_targets(p, mode_effects, mode_targets):
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
        item.cast_from_graveyard = zone is p.graveyard and kind not in ("gy_ability", "channel")
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
                    if flt.startswith("spell:") and not (flt[6:] in card.subtypes or
                                                         flt[6:].capitalize() in card.types or
                                                         (flt[6:].lower() == "outlaw" and any(
                                                             o in card.subtypes for o in OUTLAWS))):
                        continue
                    if trig.event == "cast_cmc" and card.cmc < int(trig.filter[5:]):
                        continue
                    if flt == "targets_creature" and not any(isinstance(t, Permanent) and t.is_creature
                                                            for t in targets):
                        continue
                    if (trig.event in ("cast_spell", "cast_cmc") or
                            (trig.event == "cast_noncreature" and not card.is_creature) or
                            (trig.event == "cast_instant_sorcery" and (card.is_instant or card.is_sorcery))):
                        self.queue_trigger(p, trig.effects, perm, perm.card.name, modes=trig.modes,
                                           context=item if copies.wants_spell(trig.effects) else None)
            from .. import cost_mana
            cost_mana.on_cast(self, p, card)
            copies.on_cast(self, p, item)
            cast_triggers.on_cast(self, p, item)
            if self.spells_cast.get(p.name) == 2:
                self.fire(p, "cast_second")
            for pl in self.players:
                self.fire(pl, "any_cast", context=p, subject=card)
        self.check_ward(item)
        self.settle()
        return True

    @atomic_action
    def activate_loyalty(self, p: Player, pw: Permanent, idx: int, targets=None) -> bool:
        if pw not in p.battlefield or pw.loyalty_used or idx < 0 or idx >= len(pw.card.loyalty_abilities):
            return False
        if self.activations_stopped():
            return False
        cost, effects = pw.card.loyalty_abilities[idx]
        if pw.loyalty + cost < 0:
            return False
        instant_ok = pw.card.pw_instant_on_entry and pw.entered_turn == self.turn
        if not instant_ok and not (p is self.active and self.step in ("main1", "main2") and not self.stack):
            return False
        targets = self.auto_targets(p, effects, pw) if targets is None else list(targets)
        if not self.valid_action_targets(p, effects, targets, source=pw):
            return False
        pw.counters["loyalty"] = pw.loyalty + cost
        pw.loyalty_used = True
        if targets is None:
            targets = self.auto_targets(p, effects, pw)
        item = StackItem(p, list(effects), list(targets), source=pw, name=f"{pw.card.name} [{cost:+d}]",
                         kind="loyalty")
        self.stack.append(item)
        self.log(f"activates {item}" + (f" -> {targets}" if any(targets) else ""), p)
        if self.commits_crime(p, targets):
            self.fire(p, "crime")
        self.check_ward(item)
        self.state_based_actions()
        self.settle()
        return True

    @atomic_action
    def activate(self, p: Player, perm: Permanent, what: str, target=None) -> bool:
        """Non-loyalty activated abilities: Clue, Blood, Bloodtithe Harvester, manlands, crew, and
        "ability:N" for the card's Nth activated ability (see activate_ability)."""
        if perm not in p.battlefield:
            return False
        if what.startswith("ability:"):
            return self.activate_ability(p, perm, int(what[8:]), targets=target)
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
            if card not in p.hand:
                return False
            self.discard_card(p, card)
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
        elif what == "saddle":
            crew = saddle_creatures(self, p, perm)
            if not crew:
                return False
            for c in crew:
                c.tapped = True
                self.fire(p, "becomes_tapped", c)
            perm.saddled = True
            self.log(f"saddles {perm.card.name} with {crew}", p)
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

    @atomic_action
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
                creature is equipment.attached_to or not self.targetable(creature, p):
            return False
        if self.pay(p, self.equip_cost(equipment, creature)) is None:
            return False
        item = StackItem(p, [Effect("equip", target="creature_mine")], [creature],
                         source=equipment, name=f"{equipment.card.name} equip", kind="ability")
        self.stack.append(item)
        self.log(f"activates {item} -> {creature.card.name}", p)
        self.check_ward(item)
        self.settle()
        return True

    def force_blocks(self, me: Player, attackers: list, blocks: dict) -> dict:
        """Add the blocks "must be blocked if able" and "blocks this turn if able" demand to the AI's choice."""
        blocks = {a: list(bl) for a, bl in blocks.items()}
        taken = {b for bl in blocks.values() for b in bl}
        for a in sorted(attackers, key=lambda x: -x.power):
            if not (a.card.must_be_blocked or a.has("must_be_blocked_now")) or blocks.get(a):
                continue
            free = [b for b in me.creatures if b not in taken and can_block(b, a)]
            if free:
                pick = max(free, key=lambda b: (b.toughness > a.power, b.toughness))
                blocks.setdefault(a, []).append(pick)
                taken.add(pick)
        for b in me.creatures:
            if b.has("must_block_now") and b not in taken:
                able = [a for a in attackers if can_block(b, a)]
                if able:
                    blocks.setdefault(max(able, key=lambda a: a.power), []).append(b)
                    taken.add(b)
        return blocks

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

    def ability_cost(self, p: Player, perm: Permanent, act) -> dict:
        cost = act.cost
        if act.power_up and perm.entered_turn == self.turn:
            cost = {k: max(0, v - perm.card.mana_cost.get(k, 0)) if isinstance(v, int) else v for k, v in cost.items()}
        if perm.card.is_token and perm.card.is_artifact and cost.get("generic"):
            n = sum(x.card.token_ability_discount for x in p.battlefield)
            if n:
                cost = dict(cost, generic=max(0, cost["generic"] - n))
        return cost

    def can_activate(self, p: Player, perm: Permanent, idx: int) -> bool:
        """Whether perm's activated ability idx (kind "ability") can be activated now."""
        acts = perm.card.activated
        if perm not in p.battlefield or idx < 0 or idx >= len(acts) or acts[idx].kind != "ability":
            return False
        act, c = acts[idx], acts[idx].extra_costs
        if perm.card.is_land and any(x.card.chosen_land_lock and x.chosen_land == perm.card.name
                                     for pl in self.players for x in pl.battlefield):
            return False
        if self.activations_stopped() and (perm.card.is_artifact or perm.is_creature or perm.is_planeswalker):
            return False
        if c.get("tap") and (perm.tapped or (perm.is_creature and perm.sick)):
            return False
        if act.sorcery and not (p is self.active and self.step in ("main1", "main2") and not self.stack):
            return False
        if act.once and perm.ability_turns.get(idx) == self.turn:
            return False
        if act.condition == "opp_lost_life" and not self.opponent(p).lost_life_turn:
            return False
        if act.condition == "coven" and len({x.power for x in p.creatures}) < 3:
            return False
        if act.once_game and ("game", idx) in perm.ability_turns:
            return False
        if perm.net_locked and perm.tapped:
            return False
        if c.get("level_from") is not None and perm.counters.get("level", 1) != c["level_from"]:
            return False
        if c.get("life") and p.life <= c["life"]:
            return False
        if c.get("discard") and len(p.hand) < c["discard"]:
            return False
        if c.get("remove_counter") and not perm.counters.get(c["remove_counter"]):
            return False
        if c.get("sacrifice") and len(self.sacrifice_candidates(p, perm, c["sacrifice"])) < c.get("sac_n", 1):
            return False
        if c.get("craft") and not self.craft_materials(p, perm):
            return False
        if act.needs_max_speed and p.speed < 4:
            return False
        if act.min_charge and perm.counters.get("charge", 0) < act.min_charge:
            return False
        return payable(self.mana_sources(p, perm if c.get("tap") else None, "ability"), self.ability_cost(p, perm, act))

    def valid_action_targets(self, p, effects, targets, source=None):
        return all(e.target not in TARGETED or (i < len(targets) and
                   self.legal_target(p, e, targets[i]) and
                   not (e.data.get("other") and targets[i] is source)) for i, e in enumerate(effects))

    @atomic_action
    def activate_ability(self, p: Player, perm: Permanent, idx: int, targets=None) -> bool:
        """Pay for and put on the stack a general activated ability ("{2}, {T}: Draw a card.")."""
        if not self.can_activate(p, perm, idx):
            return False
        act, c = perm.card.activated[idx], perm.card.activated[idx].extra_costs
        targets = self.auto_targets(p, act.effects, perm) if targets is None else list(targets)
        if not self.valid_action_targets(p, act.effects, targets, source=perm):
            return False
        if self.pay(p, self.ability_cost(p, perm, act), exclude=perm if c.get("tap") else None) is None:
            return False
        perm.ability_turns[idx] = self.turn
        if perm.card.activated[idx].once_game:
            perm.ability_turns[("game", idx)] = self.turn
        if c.get("tap"):
            perm.tapped = True
        if c.get("life"):
            self.change_life(p, -c["life"], f"{perm.card.name}: ability cost")
        for _ in range(c.get("discard", 0)):
            card = p.ai.choose_discard(self, p)
            if card not in p.hand:
                return False
            self.discard_card(p, card)
            self.log(f"discards {card.name}", p)
        if c.get("remove_counter"):
            perm.counters[c["remove_counter"]] -= 1
        for _ in range(c.get("sac_n", 1) if c.get("sacrifice") else 0):
            candidates = self.sacrifice_candidates(p, perm, c["sacrifice"])
            if not candidates:
                return False
            victim = candidates[0]
            self.log(f"sacrifices {victim.card.name}", p)
            perm.last_sacrificed_cmc = victim.card.cmc
            self.sacrifice(victim)
        if c.get("craft"):
            materials = self.craft_materials(p, perm)
            if not materials:
                return False
            material = materials[0]
            if material in p.graveyard:
                p.graveyard.remove(material)
                p.exile.append(material)
                name = material.name
            else:
                self.leave_battlefield(material, "exile")
                name = material.card.name
            self.log(f"exiles {name} to craft", p)
        if c.get("sac_self"):
            self.sacrifice(perm)
        elif c.get("exile_self"):
            self.leave_battlefield(perm, "exile")
        effects = list(act.effects)
        if targets is None:
            targets = self.auto_targets(p, act.effects, perm)
        if act.modes:
            mode_effects = modal.pick(self, p, act.modes, perm)
            effects += mode_effects
            targets = list(targets) + self.auto_targets(p, mode_effects, perm)
            if not self.valid_action_targets(p, mode_effects, targets[-len(mode_effects):], source=perm):
                return False
        item = StackItem(p, effects, list(targets), source=perm, name=f"{perm.card.name} ability",
                         kind="ability")
        self.stack.append(item)
        self.log(f"activates {item}" + (f" -> {targets}" if any(targets) else ""), p)
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

    def enter_battlefield(self, p: Player, card: CardDef, tapped_attacking: bool = False, x: int = 0,
                          *, tapped: bool = False, counters: dict | None = None,
                          physical_card: CardDef | None = None) -> Permanent:
        if card.is_token:
            # Reusable token blueprints create a new physical token each time.
            card = CardInstance(card)
        card, front = copies.clone_on_enter(self, p, card)
        perm = Permanent(card, p)
        perm.front = instance(physical_card if physical_card is not None else front, p)
        perm.owner = perm.front.owner
        pending = perm.front.pending_move
        before = pending[0] if pending is not None else rules_events.card_snapshot(perm.front, p)
        source_zone = pending[1] if pending is not None else perm.front.last_zone
        if isinstance(perm.front.zone, StackItem):
            source_zone = "stack"
        perm.front.pending_move = None
        perm.front.generation += 1
        perm.front.zone = perm
        perm.entered_turn = self.turn
        if card.start_engines and p.speed == 0:
            p.speed = 1
        perm.entered_x = x
        perm.prepared = bool(card.prepared and card.back is not None)
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
        elif cond == "unless_pw":
            perm.tapped = not p.planeswalkers
        elif cond.startswith("unless_player_life<="):
            perm.tapped = not any(pl.life <= int(cond[20:]) for pl in self.players)
        elif cond == "shock":
            if self.hook(p, "pay_shock")(self, p, card):
                self.change_life(p, -2, f"{card.name}: shock land cost")
            else:
                perm.tapped = True
        if card.chosen_land_lock:
            names: dict = {}
            for c in self.opponent(p).deck:
                if c.is_land and not is_basic_land(c):
                    names[c.name] = names.get(c.name, 0) + 1
            perm.chosen_land = max(names, key=names.get, default="")
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
        if card.etb_counters_if and self._etb_cond(p, card.etb_counters_if[0]):
            perm.counters["+1/+1"] = perm.p1 + card.etb_counters_if[1]
        if card.etb_named_counters:
            perm.counters[card.etb_named_counters[0]] = card.etb_named_counters[1]
        for kind, n in (counters or {}).items():
            perm.counters[kind] = perm.counters.get(kind, 0) + n
        if perm.is_creature and (bonus := counters_r3.enter_bonus(self, p, perm)):
            perm.counters["+1/+1"] = perm.p1 + bonus
        perm.tapped |= tapped
        p.battlefield.append(perm)
        self.rule_events.emit(rules_events.RulesEvent("zone_change", p, source=perm,
            before=before, source_zone=source_zone, destination="battlefield", reason="enter_battlefield"))
        host = getattr(self, "_aura_host", None)
        if host is not None and card.aura:
            auras.attach(self, perm, host)
            self._aura_host = None
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
        old = saga.counters.get("lore", 0)
        saga.counters["lore"] = old + 1
        self.lore_triggers(saga, old, old + 1)

    def lore_triggers(self, saga: Permanent, old: int, new: int):
        for n in range(old + 1, min(new, len(saga.card.chapters)) + 1):
            effects = saga.card.chapters[n - 1]
            self.queue_trigger(saga.controller, effects, saga, f"{saga.card.name} chapter {n}", kind="chapter")

    def proliferate(self, p: Player, selected=None):
        proliferate.apply(self, p, selected)

    def finish_chapter(self, saga: Permanent):
        if saga in saga.controller.battlefield and saga.card.is_saga and \
                saga.counters.get("lore", 0) >= len(saga.card.chapters):
            self.log(f"{saga.card.name} is sacrificed", saga.controller)
            self.leave_battlefield(saga, "graveyard")

    def create_token(self, p: Player, eff: Effect, n: int | None = None):
        d = eff.data
        count = n if n is not None else eff.amount
        if any(x.card.token_double for x in p.battlefield):
            count *= 2
        for _ in range(count):
            card = make_token(d.get("name", ""), d.get("power", 0), d.get("toughness", 0), d.get("keywords", ()),
                              d.get("triggers"), d.get("kind", ""), d.get("artifact", False), d.get("pt_per", ""),
                              colors=d.get("colors", ()))
            if d.get("crew_bonus"):
                card = dataclasses.replace(card, crew_bonus=d["crew_bonus"])
            if d.get("mercenary"):
                card = dataclasses.replace(card, activated=[Activated("ability", {"generic": 0}, effects=[
                    Effect("pump", 1, 0, target="creature_mine")], extra_costs={"tap": True}, sorcery=True,
                    text="{T}: Target creature you control gets +1/+0 until end of turn.")])
            perm = self.enter_battlefield(p, card, tapped_attacking=d.get("attacking", False) and self.step in
                                          ("declare_attackers", "declare_blockers"))
            if d.get("tapped"):
                perm.tapped = True
        self.log(f"creates {n if n is not None else eff.amount} {d.get('kind') or d.get('name')} token(s)", p)

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
