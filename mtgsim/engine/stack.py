"""Game methods for the stack and priority: actions, triggers, ward and resolving the top object."""
from __future__ import annotations

import dataclasses
import re

from .. import auras, copies, milling
from ..cards import CardDef, Effect
from .. import modal, rules_events
from ..identity import CardInstance, CardZone
from ..actions import perform, can_perform
from .state import Permanent, Player, StackItem, TARGETED, TrackedZone, _gy_desc, card_matches


class StackMixin:
    def settle(self):
        """Outside a priority loop: let players respond to whatever was just put on the
        stack (or triggered) and resolve until the stack is empty."""
        if not getattr(self, "_action_depth", 0) and self._priority_depth == 0 and (self.stack or self.pending) and not self.over:
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
        return perform(self, p, action)

    def can_perform(self, p: Player, action) -> bool:
        return can_perform(self, p, action)

    def queue_trigger(self, controller: Player, effects: list, source: Permanent | None = None,
                      name: str = "", context=None, targets: list | None = None, kind: str = "trigger",
                      modes=None):
        ref = (context.zone.reference(context) if isinstance(context, CardInstance)
               and isinstance(context.zone, CardZone) and context in context.zone else None)
        self.pending.append((controller, effects, source, name, context, targets, kind, modes, ref))

    def fire(self, p: Player, event: str, source: Permanent | None = None, context=None, subject=None):
        """Deliver a typed event, then queue the existing supported trigger listeners."""
        before = rules_events.snapshot(source) if source is not None and (self.rule_events.history is not None
            or self.rule_events.listeners) else None
        self.rule_events.emit(rules_events.RulesEvent(event, p, source, context, subject, before))
        self._dispatch_trigger_event(p, event, source, context, subject)

    def _dispatch_trigger_event(self, p, event, source=None, context=None, subject=None):
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
                if event == "class_level" and trig.filter != str(subject):
                    continue
                if event == "expend" and trig.filter != str(subject):
                    continue
                if event == "gy_leave":
                    desc, during = trig.filter.split("|")
                    if (during and not perm.controller.my_turn) or \
                            not any(not desc or copies.fits(c, _gy_desc(desc)) for c in subject):
                        continue
                if event in ("ally_dies", "perm_to_gy"):
                    scope, ctr, desc = trig.filter.split("|", 2)
                    if (subject is perm and scope == "other") or (ctr and not subject.counters) or \
                            not copies.fits(subject.card, desc, subject):
                        continue
                if trig.filter == "saddled" and not perm.saddled:
                    continue
                if trig.filter.startswith("with:") and \
                        not any(trig.filter[5:] in a.card.subtypes for a in self.attackers):
                    continue
                if event == "survival" and not perm.tapped:
                    continue
                if trig.once_game:
                    if ("tg", i) in perm.ability_turns:
                        continue
                    perm.ability_turns[("tg", i)] = self.turn
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
        if source is not None:      # Role tokens give the enchanted creature triggers
            for aura in list(source.auras):
                for trig in aura.card.host_triggers:
                    if trig.event == event:
                        self.queue_trigger(aura.controller, trig.effects, source, aura.card.name, context)
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
        for controller, effects, source, name, context, targets, kind, modes, ref in pending:
            if modes:
                effects = list(effects) + modal.pick(self, controller, modes, source, least=0)
                if not effects:
                    continue
            if targets is None:
                targets = self.auto_targets(controller, effects, source)
            item = StackItem(controller, effects, targets, source=source, name=name, context=context, kind=kind)
            item.context_ref = ref
            self.stack.append(item)
            self.log(f"{item} goes on the stack" + (f" -> {targets}" if any(targets) else ""), controller)
            self.check_ward(item)
        return True

    def check_ward(self, item: StackItem):
        for tgt in item.targets:
            if isinstance(tgt, Permanent) and tgt.controller is item.controller and tgt in tgt.controller.battlefield:
                self.fire(tgt.controller, "targeted_mine", source=tgt)      # Valiant
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
            self._aura_host = None
            if base.aura:
                self._aura_host = auras.choose_host(self, p, base)
                if self._aura_host is None:
                    self.log(f"{base.name} has nothing to enchant", p)
                    p.graveyard.append(base)
                    return
            perm = self.enter_battlefield(p, base, x=getattr(item, "x", 0))
            self._aura_host = None
            self._spent = ""
            if kind == "disguise":
                perm.hidden = base
                perm.card = CardDef(name="Face-down creature", mana_cost={"generic": 0}, cmc=0,
                                    types=frozenset({"Creature"}), power=2, toughness=2, ward=2)
            if kind in ("blitz", "blitz_gy"):
                perm.blitz = True
            if kind == "warp":
                perm.warped = True
            perm.was_cast = True
            perm.bargained = getattr(item, "bargained", False)
            perm.gifted = getattr(item, "gifted", False)
            if perm.gifted:
                self.give_gift(p, base.gift)
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
        item.resolved = not (targeted and all(not self.legal_target(p, e, t) for e, t in targeted))
        if not item.resolved:
            self.log(f"{item} fizzles (no legal target)", p)
        else:
            self.log(f"{item} resolves", p)
            if getattr(item, "gifted", False) and item.card is not None:
                self.give_gift(p, item.card.gift)
            prev = None
            done: list = []
            for i, (eff, tgt) in enumerate(zip(item.effects, item.targets)):   # "would die this turn" must precede the damage
                if eff.kind == "exile_instead" and i and isinstance(item.targets[i - 1], Permanent):
                    item.targets[i - 1].exile_turn = self.turn
            for eff, tgt in zip(item.effects, item.targets):
                if eff.target in TARGETED:
                    if not self.legal_target(p, eff, tgt):
                        prev = None
                        continue
                    prev = tgt
                elif eff.target == "prev":
                    tgt = prev
                if eff.data.get("distinct") and any(t is tgt for e2, t in zip(item.effects, item.targets)
                                                    if e2 is not eff and e2.data.get("distinct") and e2.kind == eff.kind
                                                    and e2 in done):
                    continue
                done.append(eff)
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
        if kind in ("adventure", "cascade_adventure", "rebound_adventure"):
            owner.on_adventure.append(base)
        elif kind == "flashback":
            owner.exile.append(base)
        elif ("rebound" in item.card.keywords and getattr(item, "cast_from_hand", False)
              and getattr(item, "resolved", False)):
            exiled = base
            if not isinstance(owner.exile, TrackedZone):
                owner.exile = TrackedZone(owner.exile)
            owner.exile.append(exiled)
            self.rebound_upkeep.append((owner, exiled, owner.exile.version(exiled)))
        elif kind not in ("channel", "prepared"):
            owner.graveyard.append(base)

    def check_cond(self, p: Player, eff: Effect, item: StackItem, prev) -> bool:
        if eff.data.get("milled_condition") and not milling.condition_met(p, eff, item):
            return False
        c = eff.cond
        if not c:
            return True
        if c[0] == "!":
            sub = Effect(eff.kind, cond=c[1:])
            return not self.check_cond(p, sub, item, prev)
        if c in ("bargained", "gifted"):
            src = item.source if getattr(item, "kind", "") != "spell" else None
            return bool(getattr(item, c, False) or (src is not None and getattr(src, c, False)))
        if c == "host_toughness<=3":
            return item.source is not None and item.source.toughness <= 3
        if c == "max_speed":
            return p.speed >= 4
        if c == "paid":
            return bool(getattr(item, "gate_paid", False))
        if c == "harnessed":
            return bool(getattr(item.source, "harnessed", False))
        if c == "evidence":
            return bool(getattr(item, "evidence", False))
        if c in ("mana>=5", "mana<5"):
            spell = item.context
            big = isinstance(spell, StackItem) and spell.mana_spent >= 5
            return big if c == "mana>=5" else not big
        if c == "attacked_turn":
            return p.attacked_with > 0
        if c == "creature_died":
            return self.creature_died_turn
        if c == "opp_creature_died":
            return self.opponent(p).creature_died_turn
        if c == "opp_more_lands":
            return sum(x.card.is_land for x in self.opponent(p).battlefield) > sum(x.card.is_land for x in p.battlefield)
        if c == "sacrificed_turn":
            return p.sacrificed_turn > 0
        if c.startswith("ctl_other:"):
            sub = c[10:]
            group = ("Assassin", "Mercenary", "Pirate", "Rogue", "Warlock") if sub == "outlaw" else (sub,)
            src = item.source if item is not None else None
            return any(x is not src and any(g in x.card.subtypes for g in group) for x in p.battlefield)
        if c.startswith("tapped_creatures>="):
            return sum(x.tapped for x in p.creatures) >= int(c[18:])
        if c.startswith("power_ge:"):
            return any(x.power >= int(c[9:]) for x in p.creatures)
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
        if c == "descended":
            return getattr(p.graveyard, "descents", 0) > 0
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
