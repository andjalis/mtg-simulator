"""Game.resolve: carrying out one effect. Add new effect kinds here or in a template module."""
from __future__ import annotations

import dataclasses

from .. import auras, cast_triggers, copies, counting, learning, milling, removal, returns, search, xspells
from ..cards import Activated, CardDef, Effect, jace_token, make_token, role_token
from ..identity import Graveyard
from .policy import choose_basic, choose_earthbend, choose_tutor, default_choose_target, perm_value
from .state import FIREBEND_MANA, Permanent, Player, StackItem, TrackedZone, card_matches, is_basic_land, pool_mana


class ResolveMixin:
    def resolve(self, p: Player, eff: Effect, target, item: StackItem | None = None, prev=None):
        opp = self.opponent(p)
        if eff.target == "self" and item is not None:
            target = item.source
        if eff.target == "that_player" and item is not None:
            target = item.context
        if eff.target == "trigger_subject" and item is not None:
            target = item.context if isinstance(item.context, Permanent) and item.context in item.context.controller.battlefield \
                else None
        if eff.target == "that_controller":
            target = prev.controller if isinstance(prev, Permanent) else prev
        k = eff.kind
        source = (item.card.name if item and item.card else
                  item.source.card.name if item and isinstance(item.source, Permanent) else "effect")
        cause = f"{source}: {k}"
        if eff.data.get("per"):    # "for each X you control"
            src = item.source if item is not None else None
            eff = dataclasses.replace(eff, amount=eff.amount * counting.count(self, p, eff.data["per"], src))
        if eff.data.get("xq"):     # ", where X is the number of ..."
            n = self.x_quantity(p, eff.data["xq"], item, prev)
            if eff.data.get("xq_size"):
                eff = dataclasses.replace(eff, data=dict(eff.data, power=n, toughness=n))
            else:
                eff = dataclasses.replace(eff, amount=eff.amount * n,
                                          amount2=eff.amount2 * n if k in ("pump", "debuff", "debuff_one", "pump_all") else eff.amount2)
        if eff.data.get("x"):      # X is the X paid for the spell
            n = getattr(item, "x", 0)
            eff = dataclasses.replace(eff, amount=n, amount2=n if eff.data.get("x2") else eff.amount2)
        if k == "damage" and eff.data.get("count"):
            what = eff.data["count"]
            n = sum(x.card.token_kind == "treasure" if what == "treasures" else x.card.is_artifact
                    if what == "artifacts" else x.is_creature if what == "creatures" else x.card.is_land
                    for x in p.battlefield)
            eff = dataclasses.replace(eff, amount=n)
        if k == "proliferate":
            for _ in range(eff.amount):
                self.proliferate(p)
        elif k == "damage":
            src = (item.source if item.source is not None else item.card) if item is not None else None
            if eff.target == "each_creature":
                for perm in p.creatures + opp.creatures:
                    if eff.data.get("no_regen") and eff.amount > 0:
                        perm.regeneration_blocked = True
                    self.deal_damage(perm, eff.amount, by=p, cause=cause, source=src)
            elif eff.target == "each_opp_and_pw":
                self.deal_damage(opp, eff.amount, by=p, cause=cause, source=src)
                for pw in opp.planeswalkers:
                    self.deal_damage(pw, eff.amount, by=p, cause=cause, source=src)
            else:
                if eff.data.get("no_regen") and eff.amount > 0 and isinstance(target, Permanent) and target.is_creature:
                    target.regeneration_blocked = True
                self.deal_damage(target, eff.amount, by=p, cause=cause, source=src)
        elif k == "destroy":
            if isinstance(target, Permanent) and target in target.controller.battlefield:
                src = item.source if item is not None else None
                if eff.data.get("azog") and target is src:
                    return
                ctl, power = target.controller, max(0, target.power)
                self.destroy(target, no_regen=eff.data.get("no_regen", False))
                if eff.data.get("azog"):
                    if power:
                        self.resolve(ctl, Effect("amass", power, data={"type": eff.data["azog"]}), None, item)
                    if ctl is p:
                        self.draw(p)
        elif k == "draw":
            who = opp if eff.target == "each_opponent" else p
            n = eff.amount
            if eff.data.get("x_count"):
                n = sum(card_matches(x.card, "a " + eff.data["x_count"]) for x in p.battlefield)
            self.draw(who, n)
        elif k == "draw_delayed":
            src = item.source if item is not None else None
            self.delayed_upkeep.append((p, eff.amount, src, f"{source}: delayed draw", eff.data["upkeep"]))
        elif k == "craft":
            card = item.source.front if item and item.source else None
            if card is not None and card in p.exile and card.back is not None:
                p.exile.remove(card)
                self.enter_battlefield(p, card.back, physical_card=card)
                self.log(f"crafts {card.back.name}", p)
        elif k == "tuck_self":
            src = item.source if item else None
            if src is not None and src in p.battlefield and self.leave_battlefield(src, "graveyard"):
                if not src.front.is_token:
                    p.graveyard.remove(src.front)
                    p.library.insert(max(0, len(p.library) - (eff.amount - 1)), src.front)
        elif k == "draw_up_to":
            self.draw(p, max(0, eff.amount - len(p.hand)))
        elif k == "gain_life":
            who = target if eff.target == "that_controller" and isinstance(target, Player) else p
            self.change_life(who, eff.amount, cause)
        elif k == "drain":
            self.change_life(opp, -eff.amount, cause)
        elif k == "equip":
            equipment = item.source if item is not None else None
            if equipment is not None and equipment in equipment.controller.battlefield and \
                    "Equipment" in equipment.card.subtypes and not equipment.is_creature and \
                    isinstance(target, Permanent) and self.legal_target(p, eff, target) and target is not equipment:
                equipment.attached_to = target
                self.log(f"equips {equipment.card.name} to {target.card.name}", p)
        elif k == "pump":
            if isinstance(target, Permanent) and target in target.controller.battlefield:
                target.pump_p += eff.amount
                target.pump_t += eff.amount2
                if eff.data.get("keyword"):
                    target.temp_kw.add(eff.data["keyword"])
        elif k in ("counter", "bounce_spell"):
            if eff.data.get("tw") and getattr(item, "teamwork", False):
                eff = dataclasses.replace(eff, amount=eff.data["tw"])
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
                self.destroy(perm, no_regen=eff.data.get("no_regen", False))
        elif k == "wrath_pw":
            for perm in p.planeswalkers + opp.planeswalkers:
                self.destroy(perm, no_regen=eff.data.get("no_regen", False))
        elif k == "bounce":
            if isinstance(target, Permanent) and target in target.controller.battlefield:
                self.log(f"{target.card.name} returns to hand", p)
                self.leave_battlefield(target, "hand")
        elif k == "scry":
            self.scry(p, eff.amount)
            self.fire(p, "scry_surveil")
        elif k == "surveil":
            self.scry(p, eff.amount, to_graveyard=True)
            self.fire(p, "scry_surveil")
        elif k == "dig":
            n = item.mana_spent if eff.data.get("x_mana") and item is not None and item.mana_spent else eff.amount
            if eff.data.get("x_lands"):
                n = sum(x.card.is_land for x in p.battlefield)
            if eff.data.get("x_count"):
                n = sum(card_matches(x.card, "a " + eff.data["x_count"]) for x in p.battlefield)
            keep = eff.amount2
            if eff.data.get("instead_two") and any(c.is_instant for c in p.graveyard) and \
                    any(c.is_sorcery for c in p.graveyard):
                keep = 2
            self.dig(p, n, keep, eff.data.get("filter"))
        elif k == "dig_put":
            self.dig_put(p, eff.amount, eff.amount2, eff.data.get("count", 1), eff.data.get("noncreature", False))
        elif k == "discard":
            who = target if isinstance(target, Player) else p
            basics = [c for c in who.hand if is_basic_land(c)] if eff.data.get("unless") == "basic_land" else []
            if basics:
                # One basic land instead of the larger discard (Thirst for Discovery); for an
                # AI that is nearly always the cheaper option.
                card = max(basics, key=lambda c: sum(c.name == x.name for x in who.hand))
                self.discard_card(who, card)
                self.log(f"discards {card.name}", who)
            who.discarded_last = []
            for _ in range(0 if basics else min(eff.amount, len(who.hand))):
                card = who.ai.choose_discard(self, who)
                self.discard_card(who, card)
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
                    self.discard_card(target, card)
                    self.log(f"makes {target} discard {card.name}", p)
        elif k == "regenerate":
            victims = (p.creatures if eff.target == "creatures_mine" else p.creatures + opp.creatures
                       if eff.target == "each_creature" else [target])
            for perm in victims:
                if isinstance(perm, Permanent) and perm in perm.controller.battlefield:
                    perm.regeneration_shields += eff.amount
        elif k == "learn":
            learning.resolve(self, p)
        elif k == "rummage":
            cards = self.hook(p, "choose_rummage")(self, p, eff.amount)
            for c in cards:
                p.hand.remove(c)
                p.graveyard.append(c)
            self.draw(p, len(cards))
        elif k == "token":
            who = target if eff.target == "that_controller" and isinstance(target, Player) else p
            n = None
            if eff.data.get("x"):
                n = (getattr(item.source, "entered_x", 0) if item.source is not None else getattr(item, "x", 0)) \
                    if item is not None else 0
            self.create_token(who, eff, n)
        elif k == "copy_token":
            tokens = [x for x in p.creatures if x.card.is_token]
            if tokens:
                best = max(tokens, key=lambda t: t.power + t.toughness)
                self.enter_battlefield(p, best.card)
                self.log(f"copies {best.card.name}", p)
        elif k == "p1_counters" and eff.target == "my_creatures":
            src = item.source if item is not None else None
            n = len(p.hand) if eff.data.get("x") == "hand" else eff.amount
            for c in p.creatures:
                if not (eff.data.get("other") and c is src):
                    c.counters["+1/+1"] = c.p1 + n
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
            p.library.shuffle(self.rng)
        elif k == "p1_counters":
            if isinstance(target, Permanent) and target in target.controller.battlefield:
                target.counters["+1/+1"] = target.p1 + eff.amount
                if eff.data.get("keyword"):
                    target.perm_kw.add(eff.data["keyword"])
        elif k == "grant":
            if eff.data.get("host") and item is not None and isinstance(item.source, Permanent):
                target = item.source.attached_to
            if isinstance(target, Permanent):
                if eff.data.get("perm"):
                    name = eff.data["keyword"]
                    target.counters[name] = target.counters.get(name, 0) + 1
                else:
                    target.temp_kw.add(eff.data["keyword"])
        elif k == "add_counter":
            if isinstance(target, Permanent):
                name = eff.data.get("counter", "+1/+1")
                n = eff.amount
                if eff.data.get("x") == "sacrificed":
                    n = p.sacrificed_turn
                    if n >= 3:
                        target.temp_kw.add("lifelink")
                target.counters[name] = target.counters.get(name, 0) + n
        elif k == "transform":
            if isinstance(target, Permanent):
                self.transform(target)
        elif k == "regrow":
            for _ in range(max(1, eff.amount)):
                cands = [c for c in p.graveyard if c.is_creature]
                if not cands:
                    break
                card = max(cands, key=lambda c: c.cmc)
                p.graveyard.remove(card)
                p.hand.append(card)
                self.log(f"returns {card.name} to hand", p)
        elif k == "recruit":
            self.draw(p)
            if p.hand:
                card = p.ai.choose_discard(self, p)
                self.discard_card(p, card)
                self.log(f"recruits, discarding {card.name}", p)
                if not card.is_land:
                    self.create_token(p, Effect("token", 1, data={"name": "Human Soldier", "power": 1,
                                                                  "toughness": 1, "keywords": frozenset()}))
        elif k == "bounce_self":
            src = item.source if item is not None else None
            if src is not None and src in src.controller.battlefield:
                self.log(f"{src.card.name} returns to hand", p)
                self.leave_battlefield(src, "hand")
        elif k == "increment":
            src = item.source if item is not None else None
            if isinstance(src, Permanent) and src in src.controller.battlefield and isinstance(item.context, StackItem):
                if item.context.mana_spent + item.context.x > min(src.power, src.toughness):
                    src.counters["+1/+1"] = src.p1 + 1
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
            players = self.players if eff.target == "each_player" else [opp] if eff.target == "each_opponent" else \
                [target] if isinstance(target, Player) else [p]
            for who in players:
                who.milled_last = []
                for _ in range(min(eff.amount, len(who.library))):
                    who.milled_last.append(who.library.pop())
                    who.graveyard.append(who.milled_last[-1])
                if item is not None:
                    if not hasattr(item, "milled"):
                        item.milled = {}
                    item.milled[who] = list(who.milled_last)
        elif k == "exile_top":
            p.impulse_new = []
            for _ in range(min(eff.amount, len(p.library))):
                c = p.library.pop()
                p.exile.append(c)
                p.impulse_new.append(c)
            self.log(f"exiles the top {len(p.impulse_new)} card(s) of their library", p)
        elif k == "may_play_exiled":
            p.impulse += [(c, self.turn + eff.amount) for c in p.impulse_new]
            p.impulse_new = []
        elif k == "mill_pick":
            milling.resolve_pick(self, p, eff, item)
        elif k == "mill_repeat":
            milling.resolve_repeat(self, p, eff, item)
        elif k == "discard_tutor":
            cands = [c for c in p.library if card_matches(c, eff.data["desc"])]
            if p.hand and cands:
                card = p.ai.choose_discard(self, p)
                self.discard_card(p, card)
                found = choose_tutor(self, p, cands)
                p.library.remove(found)
                p.hand.append(found)
                p.library.shuffle(self.rng)
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
                        owner.library.shuffle(self.rng)
                    self.log(f"shuffles {perm.card.name} into its owner's library", p)
        elif k == "return_as_enchantment":
            card = item.source.front if item and item.source else None
            if card is not None and card in p.graveyard:
                p.graveyard.remove(card)
                ench = dataclasses.replace(card, types=card.types - {"Creature"}, power=None, toughness=None)
                self.enter_battlefield(p, ench, physical_card=card)
                self.log(f"returns {card.name} as an enchantment", p)
        elif k == "role":
            host = target if isinstance(target, Permanent) else (item.source if item is not None else None)
            if isinstance(host, Permanent) and host in host.controller.battlefield and host.is_creature:
                for old in [a for a in host.auras if "Role" in a.card.subtypes and a.controller is p]:
                    self.leave_battlefield(old, "graveyard")
                self._aura_host = host
                self.enter_battlefield(p, role_token(eff.data["role"]))
                self._aura_host = None
        elif k == "connive":
            who = target if isinstance(target, Permanent) else (item.source if item is not None else None)
            if isinstance(who, Permanent) and who in who.controller.battlefield:
                ctl = who.controller
                self.draw(ctl)
                if ctl.hand:
                    card = ctl.ai.choose_discard(self, ctl)
                    self.discard_card(ctl, card)
                    self.log(f"{who.card.name} connives, discarding {card.name}", ctl)
                    if not card.is_land:
                        who.counters["+1/+1"] = who.p1 + 1
        elif k == "exile_instead":
            if isinstance(target, Permanent):
                target.exile_turn = self.turn
        elif k == "empower":
            amount = eff.amount
            cnt = eff.data.get("count")
            if cnt == "creatures":
                amount = len(p.creatures)
            elif cnt == "exiled":
                amount = getattr(self, "exiled_creatures", 0)
            elif cnt == "islands":
                amount = sum("Island" in x.card.subtypes for x in p.battlefield)
            eff = dataclasses.replace(eff, amount=amount)
            jace = next((x for x in p.battlefield if x.is_planeswalker and x.card.is_token and "Jace" in x.card.subtypes),
                        None)
            if jace is not None:
                jace.counters["loyalty"] = jace.loyalty + eff.amount
            else:
                self.enter_battlefield(p, jace_token(eff.amount))
            self.log(f"empowers Jace by {eff.amount}", p)
        elif k == "add_mana":
            for color in eff.data["colors"]:
                p.pool.append(Permanent(pool_mana(color), p))
            self.log(f"adds {''.join(eff.data['colors'])}", p)
        elif k == "firebend":
            src = item.source if item is not None else None
            n = eff.amount
            if eff.data.get("x") == "power" and isinstance(src, Permanent):
                n = max(0, src.power)
            elif eff.data.get("x") == "creatures":
                n = len(p.creatures)
            for _ in range(n):
                mana = Permanent(FIREBEND_MANA, p)
                p.pool.append(mana)
            self.log(f"adds {n} red mana (firebending)", p)
        elif k == "sac_draw_treasure":
            src = item.source if item is not None else None
            spare = [x for x in p.battlefield if x is not src and (x.card.is_artifact or x.is_creature)
                     and (x.card.is_token or x.card.token_kind) and not (x.card.token_kind == "treasure" and False)]
            if spare:
                victim = min(spare, key=perm_value)
                self.sacrifice(victim)
                self.draw(p)
                self.enter_battlefield(p, make_token("", 0, 0, (), None, "treasure", True))
        elif k == "cover_up":
            if opp.graveyard:
                pick = max(opp.graveyard, key=lambda c: c.cmc)
                opp.graveyard.remove(pick)
                opp.exile.append(pick)
                from_hand = 0
                for zone in (opp.graveyard, opp.hand, opp.library):
                    for c in [x for x in zone if x.name == pick.name]:
                        zone.remove(c)
                        opp.exile.append(c)
                        if zone is opp.hand:
                            from_hand += 1
                opp.library.shuffle(self.rng)
                self.draw(opp, from_hand)
                self.log(f"exiles every {pick.name} of {opp}", p)
        elif k == "tutor_gy":
            if p.library:
                card = max(p.library, key=lambda c: (c.is_creature, c.cmc))
                p.library.remove(card)
                p.graveyard.append(card)
                p.library.shuffle(self.rng)
                self.log(f"puts {card.name} from library into graveyard", p)
        elif k == "reanimate_total":
            budget, count = eff.amount, 0
            for card in sorted((c for c in p.graveyard if c.is_creature), key=lambda c: -c.cmc):
                if count < 2 and card.cmc <= budget:
                    p.graveyard.remove(card)
                    budget -= card.cmc
                    count += 1
                    self.enter_battlefield(p, card)
                    self.log(f"returns {card.name} to the battlefield", p)
        elif k == "bay_search":
            src = item.source if item is not None else None
            want = getattr(src, "last_sacrificed_cmc", None)
            if want is not None:
                cands = [c for c in p.library if c.is_artifact and c.cmc == want + 1]
                if cands:
                    card = max(cands, key=lambda c: c.cmc)
                    p.library.remove(card)
                    self.enter_battlefield(p, card)
                    self.log(f"fetches {card.name}", p)
                p.library.shuffle(self.rng)
        elif k == "starcage":
            src = item.source if item is not None else None
            if src is not None:
                exiled, src.exiled_cards = src.exiled_cards, []
                for card, owner in exiled:
                    if card in owner.exile:
                        owner.exile.remove(card)
                        owner.graveyard.append(card)
                for _ in exiled:
                    self.enter_battlefield(p, dataclasses.replace(make_token("Robot", 2, 2, artifact=True),
                                                                  subtypes=frozenset({"Robot"})))
                if src in p.battlefield:
                    self.sacrifice(src)
        elif k == "harness":
            src = item.source if item is not None else None
            if src is not None:
                src.harnessed = True
        elif k == "blink_own":
            src = item.source if item is not None else None
            cands = [x for x in p.battlefield if x is not src and not x.card.is_land and not x.card.is_token
                     and (x.card.etb_effects or any(t.event == "etb" for t in x.card.triggers))]
            if cands:
                best = max(cands, key=perm_value)
                card = best.front
                if self.leave_battlefield(best, "exile"):
                    p.exile.remove(card)
                    self.enter_battlefield(p, card)
        elif k == "irencrag":
            src = item.source if item is not None else None
            if src is not None and src in p.battlefield and not src.card.name.startswith("Everflame"):
                src.card = dataclasses.replace(src.card, name="Everflame, Heroes' Legacy", produces=frozenset(),
                                               types=frozenset({"Artifact"}),
                                               subtypes=frozenset({"Equipment"}), equip_cost={"generic": 3},
                                               equip_bonus=(3, 3), triggers=[], activated=[])
                self.log("The Irencrag becomes Everflame", p)
        elif k == "draw_each":
            for pl in self.players:
                self.draw(pl, eff.amount)
        elif k == "cant_block_turn":
            if isinstance(target, Permanent):
                target.temp_kw.add("cant_block_now")
        elif k in ("force_block", "force_blocked"):
            if isinstance(target, Permanent):
                target.temp_kw.add("must_block_now" if k == "force_block" else "must_be_blocked_now")
                if eff.data.get("attack"):
                    target.temp_kw.add("must_attack_now")
        elif k == "opp_exile_hand":
            if opp.hand:
                card = opp.ai.choose_discard(self, opp)
                opp.hand.remove(card)
                opp.exile.append(card)
                self.log(f"{opp} exiles {card.name} from hand", p)
        elif k == "reanimate_one":
            cands = [c for c in p.graveyard if c.is_creature]
            if cands:
                card = max(cands, key=lambda c: c.cmc)
                p.graveyard.remove(card)
                self.enter_battlefield(p, card, counters=returns.entry_counters(eff, item))
                self.log(f"reanimates {card.name}", p)
        elif k == "regrow_perm":
            cands = [c for c in p.graveyard if c.is_permanent]
            if cands:
                card = max(cands, key=lambda c: c.cmc)
                p.graveyard.remove(card)
                p.hand.append(card)
                self.log(f"returns {card.name} to hand", p)
        elif k == "gy_move":
            self.gy_move(p, eff, item)
        elif k == "grant_flashback":
            cands = [c for c in p.graveyard if (c.is_instant or c.is_sorcery) and c.alt_costs is not None]
            if cands:
                best = max(cands, key=lambda c: c.cmc)
                p.granted_fb.append(best)
                self.log(f"{best.name} gains flashback", p)
        elif k == "regrow_any":
            if p.graveyard:
                card = max(p.graveyard, key=lambda c: c.cmc)
                p.graveyard.remove(card)
                p.hand.append(card)
        elif k == "exile_gy":
            if eff.amount:
                if opp.graveyard:
                    card = max(opp.graveyard, key=lambda c: c.cmc)
                    opp.graveyard.remove(card)
                    opp.exile.append(card)
            else:
                for card in list(opp.graveyard):
                    self.move_card(card, opp.graveyard, opp.exile, reason="exile_graveyard")
        elif k == "damage_each_player":
            for pl in self.players:
                self.change_life(pl, -eff.amount, cause)
        elif k == "shrink":
            if isinstance(target, Permanent) and target in target.controller.battlefield:
                target.counters["-1/-1"] = target.m1 + eff.amount
        elif k == "shrink_all":
            for v in p.creatures + opp.creatures:
                v.counters["-1/-1"] = v.m1 + eff.amount
        elif k == "pay_gate":
            if item is not None:
                item.gate_paid = False
                if "gate" in eff.data:
                    item.gate_paid = self.pay_gate_cost(p, eff.data["gate"], item)
                elif self.can_pay(p, eff.data["cost"]) and self.hook(p, "pay_optional")(self, p, eff.data["cost"], "gate"):
                    self.pay(p, eff.data["cost"])
                    item.gate_paid = True
        elif k == "opt_cost_draw":
            src = item.source if item is not None else None
            cost = eff.data["cost"]
            paid = False
            if cost in ("discard", "either") and p.hand:
                card = p.ai.choose_discard(self, p)
                if cost == "discard" or (card.is_land and sum(x.card.is_land for x in p.battlefield) >= 5):
                    self.discard_card(p, card)
                    paid = True
            if not paid and cost != "discard":
                kinds = ("artifact",) if cost == "either" else tuple(cost.split(":", 1)[1].split("|"))
                spare = [x for x in p.battlefield
                         if not (cost.startswith("sacother") and x is src)
                         and any(card_matches(x.card, "a " + k) for k in kinds)
                         and (x.card.is_token or perm_value(x) <= 2)]
                if spare:
                    self.sacrifice(min(spare, key=perm_value))
                    paid = True
                elif cost == "either" and p.hand:
                    self.discard_card(p, p.ai.choose_discard(self, p))
                    paid = True
            if paid:
                self.draw(p, eff.amount)
        elif k == "job_select":
            src = item.source if item is not None else None
            hero = self.enter_battlefield(p, dataclasses.replace(make_token("Hero", 1, 1), subtypes=frozenset({"Hero"})))
            if src is not None and src in p.battlefield and src.card.equip_cost is not None:
                src.attached_to = hero
                self.log(f"{src.card.name} attaches to the Hero", p)
        elif k == "threaten":
            if isinstance(target, Permanent) and target in target.controller.battlefield:
                victim, owner = target, target.controller
                owner.battlefield.remove(victim)
                victim.controller = p
                p.battlefield.append(victim)
                victim.tapped = False
                victim.sick = False
                self.stolen.append((victim, owner))
                self.log(f"gains control of {victim.card.name}", p)
        elif k == "wheel_self":
            for c in list(p.hand):
                self.discard_card(p, c)
            self.draw(p, 2)
        elif k == "mass_bounce":
            keep = eff.data.get("except", "")
            only = eff.data.get("only")
            for v in [x for pl in self.players for x in pl.creatures if keep not in x.card.subtypes
                      and (only != "attacking" or x in self.attackers)]:
                self.log(f"{v.card.name} returns to hand", p)
                self.leave_battlefield(v, "hand")
        elif k == "exile_all_creatures":
            victims = [x for pl in self.players for x in pl.creatures]
            for v in victims:
                self.leave_battlefield(v, "exile")
            self.exiled_creatures = len(victims)
            self.log(f"exiles {len(victims)} creatures", p)
        elif k == "discover_treasures":
            found = getattr(p, "discovered_cmc", None)
            if found is not None and found < 10:
                for _ in range(10 - found):
                    perm = self.enter_battlefield(p, make_token("", 0, 0, (), None, "treasure", True))
                    perm.tapped = True
        elif k == "discover":
            skipped = []
            found = None
            limit = eff.amount
            if eff.data.get("x_of"):
                limit = target.card.cmc if isinstance(target, StackItem) and target.card else 0
            p.discovered_cmc = None
            while p.library:
                c = p.library.pop()
                p.exile.append(c)
                if not c.is_land and c.cmc <= limit:
                    found = c
                    break
                skipped.append(c)
            if found is not None:
                p.discovered_cmc = found.cmc
                self.log(f"discovers {found.name}", p)
                if not self.cast_free(p, found):
                    self.log(f"puts {found.name} into their hand", p)
            self.rng.shuffle(skipped)
            for c in skipped:
                p.exile.remove(c)
            p.library[0:0] = skipped
        elif k == "land_swap":
            lands = [x for x in opp.battlefield if x.card.is_land and not is_basic_land(x.card) and self.targetable(x, p)]
            if lands:
                victim = max(lands, key=perm_value)
                self.destroy(victim)
                land = choose_basic(self, opp)
                if land is not None:
                    opp.library.remove(land)
                    self.log(f"fetches {land.name}", opp)
                    perm = self.enter_battlefield(opp, land)
                    perm.tapped = True
                    perm.counters["stun"] = 1
                    opp.library.shuffle(self.rng)
        elif k == "grant_types":
            for x in p.battlefield:
                if any(t in x.card.subtypes for t in eff.data["types"]):
                    x.temp_kw.add(eff.data["keyword"])
        elif k == "amass":
            kind = eff.data["type"]
            army = next((x for x in p.creatures if "Army" in x.card.subtypes), None)
            if army is None:
                self.enter_battlefield(p, dataclasses.replace(make_token(f"{kind} Army", 0, 0), etb_counters=eff.amount))
            else:
                if kind not in army.card.subtypes:
                    army.card = dataclasses.replace(army.card, subtypes=army.card.subtypes | {kind})
                army.counters["+1/+1"] = army.p1 + eff.amount
            self.log(f"amasses {kind} {eff.amount}", p)
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
            for card in list(opp.graveyard):
                self.move_card(card, opp.graveyard, opp.exile, reason="exile_graveyard")
            self.log(f"{opp} exiles their graveyard", p)
        elif k == "endure":
            src = target if isinstance(target, Permanent) else (item.source if item is not None else None)
            if src is not None and src in src.controller.battlefield and src.is_creature:
                src.counters["+1/+1"] = src.p1 + eff.amount
                self.log(f"{src.card.name} endures {eff.amount} (counters)", p)
            else:
                self.create_token(p, Effect("token", 1, data={"name": "Spirit", "power": eff.amount,
                                                              "toughness": eff.amount, "keywords": frozenset()}))
        elif k == "manifest_dread":
            top = [p.library.pop() for _ in range(min(2, len(p.library)))]
            if top:
                top.sort(key=lambda c: copies.score(c))
                keep, rest = top[0], top[1:]       # manifest the cheaper card, the other goes to the graveyard
                perm = self.enter_battlefield(p, CardDef(name="Manifest", mana_cost={"generic": 0}, cmc=0,
                                                         types=frozenset({"Creature"}), power=2, toughness=2,
                                                         is_token=False), physical_card=keep)
                for c in rest:
                    p.graveyard.append(c)
                self.log("manifests dread", p)
        elif k == "untap_prev":
            if isinstance(target, Permanent):
                target.tapped = False
        elif k == "exile_gy_cards":
            pool = [(c, pl) for pl in (opp, p) for c in pl.graveyard]
            pool.sort(key=lambda t: (t[1] is p, -(t[0].cmc + (3 if t[0].is_creature else 0))))
            first_owner = pool[0][1] if pool else None
            for c, pl in [t for t in pool if t[1] is first_owner][:eff.amount]:
                pl.graveyard.remove(c)
                pl.exile.append(c)
                self.log(f"exiles {c.name} from {pl}'s graveyard", p)
        elif k == "gy_bottom":
            pl = p if eff.data.get("mine") else opp
            if pl.graveyard:
                c = max(pl.graveyard, key=lambda x: x.cmc + (3 if x.is_creature else 0))
                pl.graveyard.remove(c)
                pl.library.insert(0, c)
                self.log(f"puts {c.name} on the bottom of {pl}'s library", p)
        elif k == "untap_self":
            src = item.source if item is not None else None
            if src is not None and src in src.controller.battlefield:
                src.tapped = False
        elif k == "untap_other":
            tapped = [x for x in p.battlefield if x.tapped and x is not (item.source if item else None)]
            best = max(tapped, key=lambda x: (x.card.is_land or bool(x.card.produces), perm_value(x) if x.is_creature
                                             else x.card.cmc), default=None)
            if best is not None:
                best.tapped = False
        elif k == "tap":
            if isinstance(target, Permanent):
                target.tapped = True
                if eff.data.get("net"):
                    target.net_locked = True
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
            who.library.shuffle(self.rng)
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
        elif k == "level_up":
            src = item.source if item is not None else None
            if isinstance(src, Permanent) and src in src.controller.battlefield:
                src.counters["level"] = eff.data["to"]
                self.log(f"{src.card.name} becomes level {eff.data['to']}", p)
                self.fire(p, "class_level", src, subject=eff.data["to"])
        elif k == "return_self_gy":
            card = item.context if item is not None else None
            if item is not None and item.context_ref is not None:
                card = item.context_ref.find(p.graveyard)
            if isinstance(card, CardDef) and card in p.graveyard:
                p.graveyard.remove(card)
                self.log(f"returns {card.name} from the graveyard", p)
                self.enter_battlefield(p, card, tapped=eff.data.get("tapped", False),
                                       counters=returns.entry_counters(eff, item))
        elif k in ("undying_return", "persist_return"):
            owner, card, version = item.context
            grave = owner.graveyard
            index = next((i for i, c in enumerate(grave) if c is card), None)
            if index is not None and isinstance(grave, Graveyard) and grave.version(card) == version:
                del grave[index]
                self.enter_battlefield(owner, card, counters={"-1/-1" if k == "persist_return" else "+1/+1": 1})
        elif k == "rebound_cast":
            card, version = item.context
            if not isinstance(p.exile, TrackedZone) or p.exile.version(card) != version:
                return
            if not any(c is card for c in p.exile) or not self.hook(p, "choose_rebound")(self, p, card):
                return
            cast_triggers.cast_exiled(self, p, card, "rebound")
        elif k in cast_triggers.KINDS:
            cast_triggers.resolve(self, p, eff, item)
        elif k == "token_copy":
            self.enter_battlefield(p, eff.data["card"])
            self.log(f"creates {eff.data['card'].name}", p)
        elif k in copies.KINDS:
            copies.resolve(self, p, eff, target, item)
        elif k in xspells.KINDS:
            xspells.resolve(self, p, eff, target, item)
        elif k in search.KINDS:
            search.resolve(self, p, eff, target, item)
        elif k in auras.KINDS:
            auras.resolve(self, p, eff, target, item)
        elif k in removal.KINDS:
            removal.resolve(self, p, eff, target, item)
        self.state_based_actions()
