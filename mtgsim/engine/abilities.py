"""Game methods for activated abilities: loyalty, equip, costs, activation and targets."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import Effect
from .. import modal, costs
from ..actions import atomic_action
from .policy import default_choose_target, perm_value, saddle_creatures
from .state import Permanent, StackItem, TARGETED, can_block

if TYPE_CHECKING:
    from .state import Player


class AbilitiesMixin:
    @atomic_action
    def activate_loyalty(self, p: Player, pw: Permanent, idx: int, targets=None) -> bool:
        if pw not in p.battlefield or pw.loyalty_used or idx < 0 or idx >= len(pw.card.loyalty_abilities):
            return False
        if self.activations_stopped() or pw.silenced:
            return False
        cost, effects = pw.card.loyalty_abilities[idx]
        if pw.loyalty + cost < 0:
            return False
        instant_ok = pw.card.pw_instant_on_entry and pw.entered_turn == self.turn
        if not instant_ok and not (p is self.active and self.step in ("main1", "main2") and not self.stack):
            return False
        targets = self.auto_targets(p, effects, pw) if targets is None else list(targets)
        if not self.valid_action_targets(p, effects, targets):
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
        if perm.silenced:
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
        return costs.ability_plan(self, p, perm, act, self.ability_cost(p, perm, act)) is not None

    def valid_action_targets(self, p, effects, targets):
        return all(e.target not in TARGETED or (i < len(targets) and
                   self.legal_target(p, e, targets[i])) for i, e in enumerate(effects))

    @atomic_action
    def activate_ability(self, p: Player, perm: Permanent, idx: int, targets=None) -> bool:
        """Pay for and put on the stack a general activated ability ("{2}, {T}: Draw a card.")."""
        if not self.can_activate(p, perm, idx):
            return False
        act, c = perm.card.activated[idx], perm.card.activated[idx].extra_costs
        targets = self.auto_targets(p, act.effects, perm) if targets is None else list(targets)
        if not self.valid_action_targets(p, act.effects, targets):
            return False
        plan = costs.ability_plan(self, p, perm, act, self.ability_cost(p, perm, act))
        if plan is None or self.pay(p, plan.cost, exclude_many=plan.exclude) is None:
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
        for victim in plan.victims:
            if victim not in p.battlefield:
                return False
            self.log(f"sacrifices {victim.card.name}", p)
            perm.last_sacrificed_cmc = victim.card.cmc
            self.sacrifice(victim)
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
            if not self.valid_action_targets(p, mode_effects, targets[-len(mode_effects):]):
                return False
        item = StackItem(p, effects, list(targets), source=perm, name=f"{perm.card.name} ability",
                         kind="ability")
        self.stack.append(item)
        self.log(f"activates {item}" + (f" -> {targets}" if any(targets) else ""), p)
        self.check_ward(item)
        self.settle()
        return True
