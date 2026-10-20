"""Game methods for game events that effects and rules cause: damage, destroy, sacrifice, dying, state-based actions."""
from __future__ import annotations

from .. import continuous

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
        def has(keyword):
            return (source.has(keyword) if isinstance(source, Permanent)
                    else isinstance(source, CardDef) and keyword in source.keywords)
        fog = getattr(self, "fog", None)
        if combat and fog and fog[0] == self.turn and (fog[1] is None or getattr(source, "controller", None) is fog[1]):
            return
        if protected_from(target, source):
            self.log(f"{target.card.name}'s protection prevents {amount} damage", target.controller)
            return
        shield = getattr(target, "prevent_next", 0)
        if shield:
            prevented = min(shield, amount)
            target.prevent_next -= prevented
            amount -= prevented
            if amount <= 0:
                return
        infect = has("infect")
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
        else:
            return
        if has("lifelink"):
            controller = source.controller if isinstance(source, Permanent) else by
            if controller is not None:
                name = source.card.name if isinstance(source, Permanent) else source.name
                self.change_life(controller, amount, f"{name}: lifelink")

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
            (target.controller.exile if kind == "flashback" else target.controller.graveyard).append(base)
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

    def destroy(self, perm: Permanent, *, no_regen=False):
        if perm not in perm.controller.battlefield:
            return False
        if perm.has("indestructible"):
            return False
        intent = rules_events.destruction(self, perm, no_regen)
        if intent.prevented:
            before = rules_events.snapshot(perm)
            rules_events.regenerate(self, perm)
            self.rule_events.emit(rules_events.RulesEvent("destruction_replaced", perm.controller,
                source=perm, before=before, reason="destroy", replacements=intent.applied))
            return True
        self.dies(perm)
        return True

    def leave_battlefield(self, perm: Permanent, to: str):
        """Move a permanent off the battlefield (to graveyard / hand / exile). Tokens vanish."""
        if perm not in perm.controller.battlefield:
            return False
        intent = rules_events.zone_destination(self, perm, to)
        to = intent.destination
        if perm.unearthed:
            to = "exile"                     # unearth: exiled if it would leave the battlefield
        before = rules_events.snapshot(perm)
        perm.last_card = perm.card
        controller, owner = perm.controller, perm.owner
        perm.last_pt = before.power or 0, before.toughness or 0
        perm.front.pending_move = (before, "battlefield", controller, perm, intent.applied)
        controller.battlefield.remove(perm)
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
            self.leave_battlefield(a, "graveyard")
        self.fire(controller, "leaves", perm)
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

    def sacrifice(self, perm: Permanent):
        """Sacrifice perm, firing "whenever you sacrifice" triggers."""
        p = perm.controller
        p.sacrificed_turn += 1
        for other in list(p.battlefield):
            for trig in other.triggers:
                if trig.event == "sacrifice" and card_matches(perm.card, trig.filter):
                    self.queue_trigger(p, trig.effects, other, other.card.name)
        self.dies(perm) if perm.is_creature else self.leave_battlefield(perm, "graveyard")

    def discard_card(self, p: Player, card: CardDef):
        card = self.move_card(card, p.hand, p.graveyard, reason="discard")
        p.discarded_cards.append(card)
        self.fire(p, "you_discard")

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

    def dies(self, perm: Permanent):
        if perm not in perm.controller.battlefield:
            return
        was_creature = perm.is_creature
        death_returns = [keyword for keyword, count in (("undying", perm.p1), ("persist", perm.m1))
                         if was_creature and perm.has(keyword) and count == 0 and not perm.front.is_token]
        if not self.leave_battlefield(perm, "graveyard"):
            return
        if perm.last_destination != "graveyard":
            self.log(f"{perm.card.name} is exiled instead of dying", perm.controller)
            return
        if was_creature:
            self.creature_died_turn = True
            perm.controller.creature_died_turn = True
        self.log(f"{perm.card.name} dies", perm.controller)
        if was_creature:
            for keyword in death_returns:
                self.queue_trigger(perm.controller, [Effect(f"{keyword}_return")], perm,
                                   f"{perm.card.name}: {keyword}", context=(perm.owner, perm.front,
                                   perm.owner.graveyard.version(perm.front)))
            self.fire(perm.controller, "dies", perm)
            self.fire(perm.controller, "ally_dies", subject=perm)
            self.fire(perm.controller, "ally_dies", perm, subject=perm)
            if perm.blitz:
                self.queue_trigger(perm.controller, [Effect("draw", 1)], perm, f"{perm.card.name} blitz")
            self.fire(perm.controller, "other_creature_dies", subject=perm)
            opp = self.opponent(perm.controller)
            for other in opp.battlefield:
                self.fire(opp, "opp_creature_dies", other, context=perm.controller)

    def state_based_actions(self):
        for pl in self.players:
            left = getattr(pl.graveyard, "left", None)
            if left:
                pl.graveyard.left = []
                self.fire(pl, "gy_leave", subject=left)
        changed = True
        while changed:
            changed = False
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
                    if perm.card.aura and perm.aura_host is not None and protected_from(perm.aura_host, perm):
                        auras.detach(perm)
                        self.leave_battlefield(perm, "graveyard")
                        changed = True
                        continue
                    if perm.attached_to is not None and protected_from(perm.attached_to, perm):
                        perm.attached_to = None
                        changed = True
                    if perm.is_planeswalker and perm.loyalty <= 0:
                        self.dies(perm)
                        changed = True
                    elif perm.is_creature:
                        if perm.toughness <= 0:
                            self.dies(perm)
                            changed = True
                        elif (perm.damage >= perm.toughness or perm.deathtouched) and not perm.has("indestructible"):
                            self.destroy(perm)
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
                    self.dies(perm)
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
