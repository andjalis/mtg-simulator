"""Game methods for game events that effects and rules cause: damage, destroy, sacrifice, dying, state-based actions."""
from __future__ import annotations

from .. import continuous, counter_mechanics, that_much

from .. import auras
from ..cards import AltCost, CardDef, Effect
from .. import rules_events
from .mana import find_payment
from .policy import perm_value
from .state import Permanent, Player, StackItem, card_matches, protected_from


class EffectsMixin:
    def deal_damage(self, target, amount: int, by: Player | None = None,
                    cause="noncombat damage", *, source=None, combat=False):
        """Damage with source abilities; infect changes its results rather than its amount."""
        if amount <= 0:
            return
        amount = that_much.damage_amount(self, target, amount, by, source, combat)
        if amount <= 0:
            return
        def has(keyword):
            return (source.has(keyword) if isinstance(source, Permanent)
                    else isinstance(source, CardDef) and keyword in source.keywords)
        preventable = not self.no_prevention_turn     # "damage can't be prevented this turn" (Skullcrack)
        fog = getattr(self, "fog", None)
        if preventable and combat and fog and fog[0] == self.turn and (fog[1] is None or getattr(source, "controller", None) is fog[1]):
            return
        if protected_from(target, source) and preventable:
            self.log(f"{target.card.name}'s protection prevents {amount} damage", target.controller)
            return
        from ..batch1_templates import phantom_prevents, damage_immune
        if preventable and isinstance(target, Permanent) and (phantom_prevents(target) or damage_immune(target, source, combat)):
            return
        if isinstance(target, Player):
            from ..batch1_templates import curses_on
            if any(c.card.advanced_rules.get('curse_double') for c in curses_on(self, target)):
                amount *= 2
        prevented = 0
        if preventable and isinstance(source, Permanent) and \
                any("prevent_source_damage" in a.card.aura_flags for a in source.auras):
            prevented = amount       # Defang: "Prevent all damage that would be dealt by enchanted creature"
            amount = 0
        shield = getattr(target, "prevent_next", 0)
        if preventable and shield:
            n = min(shield, amount)
            target.prevent_next -= n
            prevented += n
            amount -= n
        if prevented:
            # the prevented amount, for "If damage is prevented this way, ... that much ..." riders
            # (Acolyte's Reward); fired to whoever holds the prevention shield
            self.event_amount = prevented
            self.fire(target.controller if isinstance(target, Permanent) else target,
                      "damage_prevented", context=source)
            self.event_amount = None
        if amount <= 0:
            return
        infect = has("infect")
        self.event_amount = amount          # "that much" for the triggers fired below
        if isinstance(source, Permanent) and source in source.controller.battlefield:
            self.fire(source.controller, "deals_damage", source, context=target)
            if isinstance(target, Player):
                self.fire(source.controller, "damages_player", source, context=target)
            elif combat and isinstance(target, Permanent) and target.is_creature:
                self.fire(source.controller, "combat_damage_creature", source, context=target)
        if isinstance(target, Permanent) and target in target.controller.battlefield:
            self.fire(target.controller, "dealt_damage", target, context=source)
            if combat:
                self.fire(target.controller, "dealt_combat_damage", target, context=source)
        self.event_amount = None
        if isinstance(target, Player):
            if combat and isinstance(source, Permanent) and source.card.toxic:
                target.counters["poison"] = target.counters.get("poison", 0) + source.card.toxic
            if infect:
                target.counters["poison"] = target.counters.get("poison", 0) + amount
            else:
                self.change_life(target, -amount, cause)
        elif isinstance(target, Permanent) and target in target.controller.battlefield:
            if target.is_planeswalker:
                target.counters["loyalty"] = target.loyalty - amount
            wither = (has("wither") or
                      not combat and by is not None and target.controller is not by
                      and any(x.card.wither_noncombat for x in by.battlefield))
            if target.is_creature and (infect or wither):
                target.counters["-1/-1"] = target.m1 + amount
            elif target.is_creature or not target.is_planeswalker:
                target.damage += amount
            if target.is_creature and has("deathtouch"):
                target.deathtouched = True
            if target.is_creature and isinstance(source, Permanent):
                target.damaged_by.append(source)       # "a creature dealt damage by ~ this turn dies"
        else:
            return
        from ..batch1_templates import soul_link
        soul_link(self, source, target, amount)
        if has("lifelink"):
            controller = source.controller if isinstance(source, Permanent) else by
            if controller is not None:
                name = source.card.name if isinstance(source, Permanent) else source.name
                self.change_life(controller, amount, f"{name}: lifelink")

    def adversary(self, p: Player, item, eff: Effect):
        """Bloodthirsty Adversary: "you may pay {2}{R} any number of times. When you pay
        this cost one or more times, put that many +1/+1 counters on ~, then exile up to
        that many target instant and/or sorcery cards with mana value 3 or less from your
        graveyard and copy them." The payments go through phasing's pay_repeat plumbing
        (the Adversary cycle); the copies stay here."""
        from ..phasing import pay_repeat
        pay_repeat(self, p, eff, item)
        n = getattr(item, "pay_repeat", 0) if item is not None else 0
        src = item.source if item is not None else None
        if src is not None and src in p.battlefield and n:
            src.counters["+1/+1"] = src.p1 + n
        cards = sorted((c for c in p.graveyard
                        if (c.is_instant or c.is_sorcery) and c.cmc <= 3 and c.spell_effects),
                       key=lambda c: c.cmc, reverse=True)
        for card in cards[:n]:
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
                base, kind, _ = self._origin(target.card)
                owner = getattr(base, "owner", None) or target.controller
                (owner.exile if kind in ("aftermath", "flashback", "jump_start") else owner.hand).append(base)
            self.log(f"{target} is returned to its owner's hand", p)
            return
        if target.is_spell and not self.counterable(target):
            self.log(f"{target} can't be countered", p)
            return
        if eff.amount:
            payer = target.controller
            if eff.data.get("life"):
                n = eff.data["life"]
                from ..residual_templates import life_locked
                if not life_locked(payer) and payer.life > n + 2 and self.hook(payer, "pay_unless")(self, payer, 0, target):
                    self.change_life(payer, -n, f"ward: pay {n} life")
                    return
            elif eff.data.get("discard"):
                if payer.hand and self.hook(payer, "pay_unless")(self, payer, 0, target):
                    card = payer.ai.choose_discard(self, payer)
                    self.discard_card(payer, card)
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
            exiled = kind in ("flashback", "jump_start", "grave_permission", "aftermath") or eff.data.get("exile")    # "exile it instead of putting it into ... graveyard"
            owner = getattr(base, "owner", None) or target.controller
            (owner.exile if exiled else owner.graveyard).append(base)
        self.log(f"{target} is countered", p)

    def scry(self, p: Player, n: int, to_graveyard: bool = False):
        cards = list(reversed(p.library[-min(n, len(p.library)):])) if n else []
        bottom = self.hook(p, "scry")(self, p, list(cards))
        prefix = [c for c in p.library if c not in cards]
        if to_graveyard:
            for c in bottom:
                self.move_card(c, p.library, p.graveyard, reason="surveil")
        p.library.reorder(([] if to_graveyard else list(reversed(bottom))) + prefix +
                          [c for c in reversed(cards) if c not in bottom])

    def dig(self, p: Player, n: int, keep: int, desc: str | None = None):
        cards = list(reversed(p.library[-min(n, len(p.library)):])) if n else []
        allowed = [c for c in cards if card_matches(c, desc.replace(" or ", " or a "))] if desc else cards
        chosen = list(self.hook(p, "choose_dig")(self, p, list(allowed), keep))[:keep] if allowed else []
        rest = list(cards)
        for c in chosen:
            rest.remove(c)
            self.move_card(c, p.library, p.hand, reason="dig")
        self.rng.shuffle(rest)
        p.library.reorder(list(reversed(rest)) + [c for c in p.library if c not in rest])
        self.log(f"digs {n}, keeps {chosen}", p)
        # Dark Confidant: "reveal that card and lose life equal to its mana value" — record the
        # revealed card's mana value on the resolving item for the ("revealed", "mana value") xq.
        item = getattr(self, "resolving_item", None)
        if item is not None and chosen:
            item.revealed_cmc = chosen[-1].cmc

    def dig_put(self, p: Player, n: int, max_cmc: int, count: int = 1, noncreature: bool = False):
        cards = list(reversed(p.library[-min(n, len(p.library)):])) if n else []
        cands = [c for c in cards if c.is_permanent and not c.is_land and c.cmc <= max_cmc
                 and not (noncreature and c.is_creature)]
        rest = list(cards)
        for card in sorted(cands, key=lambda c: -c.cmc)[:count]:
            rest.remove(card)
            self.log(f"puts {card.name} onto the battlefield", p)
            p.library.remove(card)
            self.enter_battlefield(p, card)
        self.rng.shuffle(rest)
        p.library.reorder(list(reversed(rest)) + [c for c in p.library if c not in rest])

    def destroy(self, perm: Permanent, *, no_regen=False, counter_sources=None):
        if perm not in perm.controller.battlefield:
            return False
        if perm.has("indestructible"):
            return False
        umbra = next((a for a in perm.auras if a.card.umbra_armor), None)
        if umbra is not None:            # umbra armor: remove the damage and destroy the Aura instead
            perm.damage, perm.deathtouched = 0, False
            self.log(f"{umbra.card.name} is destroyed instead of {perm.card.name}", perm.controller)
            self.destroy(umbra)
            return True
        intent = rules_events.destruction(self, perm, no_regen)
        if intent.prevented:
            before = rules_events.snapshot(perm)
            rules_events.regenerate(self, perm)
            self.rule_events.emit(rules_events.RulesEvent("destruction_replaced", perm.controller,
                source=perm, before=before, reason="destroy", replacements=intent.applied))
            return True
        self.dies(perm, counter_sources=counter_sources)
        return True

    def leave_battlefield(self, perm: Permanent, to: str):
        """Move a permanent off the battlefield (to graveyard / hand / exile). Tokens vanish."""
        if perm not in perm.controller.battlefield:
            return False
        intent = rules_events.zone_destination(self, perm, to)
        to = intent.destination
        if perm.unearthed or ((perm.disturbed or perm.card.gy_to_exile) and to == "graveyard"):
            to = "exile"                     # unearth: exiled if it would leave the battlefield; disturb: not to a graveyard
        from ..residual_templates import grave_exiled
        if to == "graveyard" and grave_exiled(self, perm.owner, token=perm.card.is_token):
            to = "exile"
        before = rules_events.snapshot(perm)
        perm.last_triggers = list(perm.triggers)
        perm.last_card = perm.card
        controller, owner = perm.controller, perm.owner
        perm.last_pt = before.power or 0, before.toughness or 0
        perm.front.pending_move = (before, "battlefield", controller, perm, intent.applied)
        controller.battlefield.remove(perm)
        self._residual_source_index = None
        counter_mechanics.expire_source_control(self)
        for effect in self.continuous_effects:
            if effect.source is perm:
                continuous.refresh(effect.target)
        perm.last_destination = to
        perm.front.generation += 1
        perm.front.last_zone = "battlefield"
        perm.front.zone = None
        controller.perm_left_turn = True
        if perm.card.aura:
            auras.detach(perm)
        perm.attached_to = None
        for x in [x for player in self.players for x in player.battlefield]:
            if x.attached_to is perm:
                x.attached_to = None
        for a in list(perm.auras):
            auras.detach(a)
            from ..batch1_templates import unbestow
            if unbestow(self, a):
                self.log(f"{a.card.name} stays as a creature", a.controller)
                continue
            self.leave_battlefield(a, "graveyard")
        self.fire(controller, "leaves", perm)
        returning, perm.exiled_cards = perm.exiled_cards, []
        for card, card_owner in returning:
            if card in card_owner.exile:
                card_owner.exile.remove(card)
                self.log(f"{card.name} returns from exile", card_owner)
                self.enter_battlefield(card_owner, card)
        returning, perm.exiled_to_hand = perm.exiled_to_hand, []
        for card, card_owner in returning:
            if card in card_owner.exile:
                self.move_card(card, card_owner.exile, card_owner.hand, reason="return")
                self.log(f"{card.name} returns to {card_owner}'s hand", card_owner)
        if perm in self.attackers:
            self.attackers.remove(perm)
        if not perm.front.is_token:
            {"graveyard": owner.graveyard, "hand": owner.hand, "exile": owner.exile}[to].append(perm.front)
        if perm.front.is_token:
            self.rule_events.emit(rules_events.RulesEvent("zone_change", controller, source=perm,
                before=before, destination=to, reason="leave_battlefield", replacements=intent.applied,
                source_zone="battlefield"))
            perm.front.pending_move = None
        if to == "graveyard":
            self.fire(owner, "perm_to_gy", subject=perm)
            self.fire(owner, "perm_to_gy", perm, subject=perm)
        return True

    def extra_sac_candidates(self, p: Player, card: CardDef) -> list:
        """What p could sacrifice for card's additional cost, least valuable first."""
        return sorted((x for x in p.battlefield if card_matches(x.card, card.extra_sacrifice.replace(" or ", " or a "))
                       or (x.is_creature and "creature" in card.extra_sacrifice)),
                      key=lambda x: (not x.card.is_token, perm_value(x) if x.is_creature else x.card.cmc))

    def gy_exile_candidates(self, p: Player, desc: str) -> list:
        """Cards in p's graveyard that could be exiled for "Exile a(n) <desc> card from your
        graveyard" (a spell's or activated ability's additional cost), least valuable first."""
        d = desc if desc.startswith(("a ", "an ")) else "a " + desc
        return sorted((c for c in p.graveyard if card_matches(c, d.replace(" or ", " or a "))),
                      key=lambda c: (c.cmc, getattr(c, "power", 0) or 0))

    def sacrifice(self, perm: Permanent, *, counter_sources=None):
        """Sacrifice perm, firing "whenever you sacrifice" triggers."""
        p = perm.controller
        from ..advanced_templates import rules
        item = getattr(self, "resolving_item", None)
        if item is not None and item.controller is not p and any(rules(x).get("sac_protection") for x in p.battlefield):
            return False
        p.sacrificed_turn += 1
        for other in list(p.battlefield):
            for trig in other.triggers:
                if trig.event == "sacrifice" and (card_matches(perm.card, trig.filter) if not trig.filter.startswith("another ") else
                                                  other is not perm and card_matches(perm.card, "a " + trig.filter[8:])):
                    self.queue_trigger(p, trig.effects, other, other.card.name)
        self.dies(perm, counter_sources=counter_sources) if perm.is_creature else self.leave_battlefield(perm, "graveyard")

    def discard_card(self, p: Player, card: CardDef):
        card = self.move_card(card, p.hand, p.graveyard, reason="discard")
        p.discarded_cards.append(card)
        self.fire(p, "you_discard")
        # The subject lets typed listeners ("whenever an opponent discards a creature/land card",
        # Waste Not) filter on the discarded card's types.
        self.fire(self.opponent(p), "opp_discard", subject=card)

    def cast_free(self, p: Player, card: CardDef) -> bool:
        """Cast a discovered card from exile, or put it into hand if it cannot be cast."""
        if card not in p.exile:
            p.exile.append(card)
        if self.cast(p, self._variant(card, "discover", AltCost("discover", {"generic": 0}))):
            return True
        self.move_card(card, p.exile, p.hand, reason="discover-to-hand")
        return False

    def sneak(self, p: Player, card: CardDef, alt: AltCost, attacker: Permanent) -> bool:
        """Sneak: pay the sneak cost and return an unblocked attacker; the creature enters tapped and attacking."""
        target = self.attack_targets.get(attacker, self.opponent(p))
        if self.pay(p, alt.cost, spell=card) is None:
            return False
        self.leave_battlefield(attacker, "hand")
        self.log(f"sneaks in {card.name}, returning {attacker.card.name}", p)
        p.hand.remove(card)
        if card.is_creature or alt.kind == "ninjutsu":
            perm = self.enter_battlefield(p, card, tapped_attacking=True)
            self.attackers.append(perm)
            self.attack_targets[perm] = target
            self.settle()
        else:
            p.hand.append(card)
            self.cast(p, self._variant(card, "sneak", AltCost("sneak", {"generic": 0})))
        return True

    def _etb_cond(self, p: Player, cond: str) -> bool:
        if cond == "opp_lost_life":
            return self.opponent(p).lost_life_turn
        if cond == "creature_died":
            return self.creature_died_turn
        return p.attacked_with > 0

    def dies(self, perm: Permanent, *, counter_sources=None):
        if counter_sources is None:
            counter_sources = counter_mechanics.death_sources(self)
        previous = getattr(self, "_suppressed_death_object", None)
        if perm.is_creature and getattr(counter_sources, "suppresses_death", False):
            self._suppressed_death_object = perm
        try:
            return self._dies(perm, counter_sources=counter_sources)
        finally:
            self._suppressed_death_object = previous

    def _dies(self, perm: Permanent, *, counter_sources=None):
        if perm not in perm.controller.battlefield:
            return
        if counter_sources is None:
            counter_sources = counter_mechanics.death_sources(self)
        was_creature = perm.is_creature
        death_returns = [keyword for keyword, count in (("undying", perm.p1), ("persist", perm.m1))
                         if was_creature and perm.has(keyword) and count == 0 and not perm.front.is_token]
        attached = list(perm.auras) + perm.equipment if was_creature else []   # "when enchanted creature dies"
        if was_creature and getattr(perm, "exile_if_dies", None) == self.turn:
            self.log(f"{perm.card.name} is exiled instead of dying", perm.controller)
            self.leave_battlefield(perm, "exile")
            return
        if not self.leave_battlefield(perm, "graveyard"):
            return
        if perm.last_destination != "graveyard":
            self.log(f"{perm.card.name} is exiled instead of dying", perm.controller)
            return
        if was_creature and getattr(counter_sources, "suppresses_death", False):
            self.creature_died_turn = True
            perm.controller.creature_died_turn = True
            return
        from ..backlog_templates import filtered_death
        filtered_death(self, perm, counter_sources)
        if was_creature:
            counter_mechanics.queue_death_return(self, perm, counter_sources)
            self.creature_died_turn = True
            perm.controller.creature_died_turn = True
        self.log(f"{perm.card.name} dies", perm.controller)
        if was_creature:
            for keyword in death_returns:
                self.queue_trigger(perm.controller, [Effect(f"{keyword}_return")], perm,
                                   f"{perm.card.name}: {keyword}", context=(perm.owner, perm.front,
                                   perm.owner.graveyard.version(perm.front)))
            self.fire(perm.controller, "dies", perm)
            for owner, haunter in getattr(perm, "haunters", ()):
                for trig in haunter.triggers:
                    if trig.event == "haunt_dies":
                        self.queue_trigger(owner, trig.effects, None, f"{haunter.name} haunt", modes=trig.modes)
            for x in attached:
                for trig in x.card.host_triggers:
                    if trig.event == "dies":
                        self.queue_trigger(x.controller, trig.effects, x, x.card.name, context=perm)
            self.fire(perm.controller, "ally_dies", subject=perm)
            self.fire(perm.controller, "ally_dies", perm, subject=perm)
            if perm.blitz:
                self.queue_trigger(perm.controller, [Effect("draw", 1)], perm, f"{perm.card.name} blitz")
            self.fire(perm.controller, "other_creature_dies", subject=perm)
            for src in {id(s): s for s in perm.damaged_by}.values():
                if src in src.controller.battlefield:
                    self.fire(src.controller, "damaged_dies", src, context=perm)
            opp = self.opponent(perm.controller)
            for other in opp.battlefield:
                self.fire(opp, "opp_creature_dies", other, context=perm.controller)
            for pl in self.players:
                self.fire(pl, "creature_dies", subject=perm, context=perm)

    def state_based_actions(self):
        from ..advanced_templates import update_static
        update_static(self)
        for pl in self.players:
            left = getattr(pl.graveyard, "left", None)
            if left:
                pl.graveyard.left = []
                self.fire(pl, "gy_leave", subject=left)
        changed = True
        while changed:
            changed = False
            counter_sources = counter_mechanics.death_sources(self)
            # With a counter-death watcher, distinguish this wave's deaths from
            # creatures that only become lethal after a static source leaves.
            simultaneous_deaths = {x for p in self.players for x in p.battlefield
                                   if x.is_creature and (x.toughness <= 0 or
                                   (x.damage >= x.toughness or x.deathtouched) and not x.has('indestructible'))
                                   or x.is_planeswalker and x.loyalty <= 0} if counter_sources else set()
            # Choose from the pre-action state, before removing lethal creatures.
            # The legend rule is a graveyard move, neither destruction nor sacrifice.
            legend_losers = []
            for p in self.players:
                groups = {}
                for perm in p.battlefield:
                    if perm.card.legendary:
                        groups.setdefault(perm.card.name, []).append(perm)
                for group in groups.values():
                    if len(group) > 1:
                        keep = self.hook(p, "choose_legend")(self, p, tuple(group))
                        if not any(keep is candidate for candidate in group):
                            keep = group[0]
                        legend_losers.extend(perm for perm in group if perm is not keep)
            for p in self.players:
                for perm in list(p.battlefield):
                    # Protection: an Aura of that color is put into the graveyard, Equipment becomes unattached.
                    if perm.card.aura and perm.aura_host is not None and (protected_from(perm.aura_host, perm) or
                            perm.card.advanced_rules.get("aura_selector") and not auras.can_attach(self, perm.controller, perm.card, perm.aura_host, source=perm, targeting=False)):
                        auras.detach(perm)
                        self.leave_battlefield(perm, "graveyard")
                        changed = True
                        continue
                    if perm.attached_to is not None and protected_from(perm.attached_to, perm):
                        perm.attached_to = None
                        changed = True
                    if perm.card.needs_land and not any(perm.card.needs_land in x.card.subtypes or
                                                        perm.card.needs_land in x.card.types for x in p.battlefield):
                        self.sacrifice(perm)
                        changed = True
                        continue
                    if perm.is_planeswalker and perm.loyalty <= 0:
                        self.dies(perm, counter_sources=counter_sources if perm in simultaneous_deaths else None)
                        changed = True
                    elif perm.is_creature:
                        if perm.toughness <= 0:
                            self.dies(perm, counter_sources=counter_sources if perm in simultaneous_deaths else None)
                            changed = True
                        elif (perm.damage >= perm.toughness or perm.deathtouched) and not perm.has("indestructible"):
                            self.destroy(perm, counter_sources=counter_sources if perm in simultaneous_deaths else None)
                            changed = True
                    # Dying objects retain their counters as last-known information.
                    if perm in p.battlefield:
                        cancelled = min(perm.p1, perm.m1)
                        if cancelled > 0:
                            perm.counters["+1/+1"] -= cancelled
                            perm.counters["-1/-1"] -= cancelled
                            changed = True
            for perm in legend_losers:
                if perm in perm.controller.battlefield:
                    self.dies(perm, counter_sources=counter_sources)
                    changed = True
        for p in self.players:
            if p.counters.get("poison", 0) >= 10:
                if not p.lost:
                    self.audit("loss", seat=self.players.index(p), cause="ten or more poison counters")
                p.lost = True
            if p.life <= 0:
                if not p.lost:
                    self.audit("loss", seat=self.players.index(p), cause="life total 0 or less")
                p.lost = True
