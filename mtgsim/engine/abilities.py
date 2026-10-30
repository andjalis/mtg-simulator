"""Game methods for activated abilities: loyalty, equip, costs, activation and targets."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import Effect
from .. import modal, costs, counter_mechanics
from ..actions import atomic_action
from .policy import any_player_ability, any_player_window, default_choose_target, perm_value, saddle_creatures
from .state import Permanent, StackItem, TARGETED, can_block

if TYPE_CHECKING:
    from .state import Player


class AbilitiesMixin:
    @atomic_action
    def activate_loyalty(self, p: Player, pw: Permanent, idx: int, targets=None) -> bool:
        if pw not in p.battlefield or pw.loyalty_used or idx < 0 or idx >= len(pw.card.loyalty_abilities):
            return False
        from ..residual_templates import activation_blocked
        if activation_blocked(self, pw) or self.nonmana_locked(p) or self.activations_stopped() or pw.silenced:
            return False
        cost, effects = pw.card.loyalty_abilities[idx]
        if pw.loyalty + cost < 0:
            return False
        instant_ok = pw.card.pw_instant_on_entry and pw.entered_turn == self.turn
        if not instant_ok and not (p is self.active and self.step in ("main1", "main2") and not self.stack):
            return False
        targets = self.auto_targets(p, effects, pw) if targets is None else list(targets)
        if not self.valid_action_targets(p, effects, targets, pw):
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
        "ability:N" for the card's Nth activated ability (see activate_ability). An "any player
        may activate" ability may be used through here by a player who doesn't control perm."""
        if what.startswith("ability:"):
            idx = int(what[8:])
            if perm not in p.battlefield and not (0 <= idx < len(perm.activated)
                                                   and any_player_ability(perm.activated[idx])):
                return False
            return self.activate_ability(p, perm, idx, targets=target)
        if perm not in p.battlefield:
            return False
        if what.startswith("equip"):
            return self.equip(p, perm, target)
        from ..residual_templates import activation_blocked
        if activation_blocked(self, perm) or self.nonmana_locked(p) or self.activations_stopped() and (perm.card.is_artifact or perm.is_creature):
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
            act = next((a for a in perm.activated if a.kind == what), None)
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
        from ..residual_templates import activation_blocked
        if activation_blocked(self, equipment) or self.nonmana_locked(p) or self.activations_stopped():
            return False
        if creature is None:
            creature = self.hook(p, "choose_equip_target")(self, p, equipment)
        if creature is None or creature not in p.battlefield or not creature.is_creature or \
                creature is equipment.attached_to or creature is equipment or not self.targetable(creature, p, equipment):
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
        for a in attackers:             # Lure: all creatures able to block it do so
            if a.card.lure:
                for b in me.creatures:
                    if b not in taken and can_block(b, a):
                        blocks.setdefault(a, []).append(b)
                        taken.add(b)
        for b, a in list(getattr(self, "provoked", {}).items()):
            if b in me.creatures and a in attackers and b not in taken and can_block(b, a):
                blocks.setdefault(a, []).append(b)
                taken.add(b)
        for b in me.creatures:
            if b.has("must_block_now") and b not in taken:
                able = [a for a in attackers if can_block(b, a)]
                if able:
                    blocks.setdefault(max(able, key=lambda a: a.power), []).append(b)
                    taken.add(b)
        return blocks

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
            from ..permanent_templates import selector, matches
            spec = selector(what)
            if (spec is not None and matches(self, x, spec, p, perm)) or any(kinds.get(k.strip()) for k in what.split(" or ")):
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
        from ..advanced_templates import activation_cost
        return activation_cost(self, p, perm, cost)

    def can_activate(self, p: Player, perm: Permanent, idx: int, *, x=None, counter_choices=None) -> bool:
        """Whether perm's activated ability idx (kind "ability") can be activated now, by p.
        "Any player may activate" abilities may be used by players who don't control perm."""
        acts = perm.activated
        if idx < 0 or idx >= len(acts) or acts[idx].kind != "ability":
            return False
        act = acts[idx]
        if perm not in p.battlefield and not any_player_ability(act):
            return False
        window = any_player_window(act)
        if window == "their_turn" and p is not self.active:
            return False
        if window == "upkeep" and self.step != "upkeep":
            return False
        if window == "draw_step" and not (p is self.active and self.step == "draw"):
            return False
        if self.nonmana_locked(p) or perm.abilities_suppressed or any('cant_activate' in a.card.aura_flags for a in perm.auras):
            return False
        act, c = acts[idx], acts[idx].extra_costs
        if act.condition == "blessing":
            from ..batch1_templates import has_blessing
            if not has_blessing(self, p):
                return False
        from ..residual_templates import activation_blocked, mana_ability, life_locked
        if activation_blocked(self, perm, mana=mana_ability(act)) or c.get("life") and life_locked(p):
            return False
        if perm.card.is_land and any(x.card.chosen_land_lock and x.chosen_land == perm.card.name
                                     for pl in self.players for x in pl.battlefield):
            return False
        if self.activations_stopped() and (perm.card.is_artifact or perm.is_creature or perm.is_planeswalker):
            return False
        if c.get("tap") and (perm.tapped or (perm.is_creature and perm.sick)):
            return False
        if (act.sorcery or window == "sorcery") and not (p is self.active and self.step in ("main1", "main2") and not self.stack):
            return False
        if act.once and perm.ability_turns.get(idx) == self.turn:
            return False
        if act.once_game and ("game", idx) in perm.ability_turns:
            return False
        if act.max_per_turn:
            seen = perm.ability_turns.get(("count", idx), (None, 0))
            if seen[0] == self.turn and seen[1] >= act.max_per_turn:
                return False
        if perm.net_locked and perm.tapped:
            return False
        if c.get("level_from") is not None and perm.counters.get("level", 1) != c["level_from"]:
            return False
        if c.get("level_range") is not None and not c["level_range"][0] <= perm.counters.get("level", 0) <= c["level_range"][1]:
            return False
        if p.counters.get("energy", 0) < c.get("energy", 0):
            return False
        if c.get("life") and p.life <= c["life"]:
            return False
        if c.get("discard") and len(p.hand) < c["discard"]:
            return False
        if c.get("remove_counter") and perm.counters.get(c["remove_counter"], 0) < c.get("remove_counter_count", 1):
            return False
        if c.get("sacrifice") and len(self.sacrifice_candidates(p, perm, c["sacrifice"])) < c.get("sac_n", 1):
            return False
        if c.get("craft") and not self.craft_materials(p, perm):
            return False
        if act.needs_max_speed and p.speed < 4:
            return False
        if act.min_charge and perm.counters.get("charge", 0) < act.min_charge:
            return False
        return costs.ability_plan(self, p, perm, act, self.ability_cost(p, perm, act),
                                  x=x, counter_choices=counter_choices) is not None

    def valid_action_targets(self, p, effects, targets, source=None):
        with self.targeting(source if source is not None else self.target_source):
            previous = getattr(self, '_choosing_targets', [])
            self._choosing_targets = targets
            try:
                return all(e.target not in TARGETED or (i < len(targets) and
                           self.legal_target(p, e, targets[i])) for i, e in enumerate(effects))
            finally:
                self._choosing_targets = previous

    @atomic_action
    def activate_ability(self, p: Player, perm: Permanent, idx: int, targets=None, *, x=None, counter_choices=None) -> bool:
        """Pay for and put on the stack a general activated ability ("{2}, {T}: Draw a card.")."""
        if not self.can_activate(p, perm, idx, x=x, counter_choices=counter_choices):
            return False
        act, c = perm.activated[idx], perm.activated[idx].extra_costs
        plan = costs.ability_plan(self, p, perm, act, self.ability_cost(p, perm, act),
                                  x=x, counter_choices=counter_choices)
        if plan is None:
            return False
        targets = self.auto_targets(p, costs.counter_effects(act, plan), perm) if targets is None else list(targets)
        if not self.valid_action_targets(p, act.effects, targets, perm):
            return False
        if plan is None or self.pay(p, plan.cost, exclude_many=plan.exclude, reserved_counters=plan.counter_payments) is None:
            return False
        p.counters["energy"] = p.counters.get("energy", 0) - c.get("energy", 0)
        perm.ability_turns[idx] = self.turn
        if act.max_per_turn:
            seen = perm.ability_turns.get(("count", idx), (None, 0))
            perm.ability_turns[("count", idx)] = (self.turn, seen[1] + 1 if seen[0] == self.turn else 1)
        if act.once_game:
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
            count = c.get('remove_counter_count', 1)
            if perm not in p.battlefield or perm.counters.get(c['remove_counter'], 0) < count:
                return False
            perm.counters[c["remove_counter"]] -= count
        for donor, kind, n in plan.counter_payments:
            if donor not in p.battlefield or not donor.is_creature or donor.counters.get(kind, 0) < n:
                return False
            donor.counters[kind] -= n
            self.log(f"removes {n} {kind} counter(s) from {donor.card.name}", p)
        counter_sources = counter_mechanics.death_sources(self) if plan.victims else None
        for victim in plan.victims:
            if victim not in p.battlefield:
                return False
            self.log(f"sacrifices {victim.card.name}", p)
            perm.last_sacrificed_cmc = victim.card.cmc
            perm.last_sacrificed = (victim.power, victim.toughness, victim.card.cmc)
            self.sacrifice(victim, counter_sources=counter_sources)
        if c.get("craft"):
            material = plan.craft
            if material is None or material not in p.graveyard and material not in p.battlefield:
                return False
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
            if not self.valid_action_targets(p, mode_effects, targets[-len(mode_effects):], perm):
                return False
        item = StackItem(p, effects, list(targets), source=perm, name=f"{perm.card.name} ability",
                         kind="ability")
        item.counter_x = sum(n for _, _, n in plan.counter_payments)
        if c.get("remove_creature_counters") in ("x", "positive"):
            item.x = item.counter_x
        self.stack.append(item)
        self.log(f"activates {item}" + (f" -> {targets}" if any(targets) else ""), p)
        self.check_ward(item)
        self.settle()
        return True
