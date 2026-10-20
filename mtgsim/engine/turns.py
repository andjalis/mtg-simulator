"""Game methods for zones, continuous-effect bookkeeping, setup and the turn structure."""
from __future__ import annotations

from typing import TYPE_CHECKING
from .. import alt_casts, auras, copies, creature_keywords, graveyard
from ..cards import Activated, CardDef, Effect
from .. import rules_events, continuous
from ..identity import CardInstance, Graveyard
from .state import is_basic_land

if TYPE_CHECKING:
    from .state import Player


class TurnsMixin:
    def animate_turn_creatures(self, p: Player):
        """"During your turn, as long as ~ has loyalty counters, it's a 3/4 Ninja creature" (Kaito)."""
        for perm in p.battlefield:
            if perm.card.turn_creature and perm.animated is None and perm.loyalty > 0:
                power, toughness, subs, kws = perm.card.turn_creature
                perm.animated = Activated("animate", {}, power, toughness, frozenset(kws), subtypes=frozenset(subs))

    def zone_arrived(self, card, destination):
        """One event boundary for legacy list moves and explicit movement helpers."""
        pending = card.pending_move
        if pending is None:
            return  # a fixture/blueprint insertion has no source zone
        before, origin, actor, source, replacements = pending
        card.pending_move = None
        self.rule_events.emit(rules_events.RulesEvent("zone_change", actor, source=source,
            subject=card, before=before, destination=destination.name,
            source_zone=origin, reason=getattr(self, "_zone_reason", "move"), replacements=replacements))

    def next_effect_timestamp(self):
        self.effect_clock += 1
        return self.effect_clock

    def add_continuous_effect(self, target, operation, **options):
        return continuous.add(self, target, operation, **options)

    def expire_continuous_effects(self):
        expired = [e for e in self.continuous_effects if e.until_eot]
        self.continuous_effects[:] = [e for e in self.continuous_effects if not e.until_eot]
        for effect in expired:
            continuous.refresh(effect.target)

    def move_card(self, card, source, destination, *, reason="move"):
        """Move one exact physical card between nonbattlefield zones."""
        card = source.get(card)
        previous = getattr(self, "_zone_reason", "move")
        self._zone_reason = reason
        try:
            source.remove(card)
            destination.append(card)
        finally:
            self._zone_reason = previous
        return card

    def draw(self, p: Player, n: int = 1):
        for _ in range(n):
            if not p.library:
                if not p.lost:
                    self.audit("loss", seat=self.players.index(p), cause="drew from empty library")
                p.lost = True
                self.log("loses by drawing from an empty library", p)
                return
            self.move_card(p.library[-1], p.library, p.hand, reason="draw")
            self.fire(p, "you_draw")
            drawn = getattr(p, "drawn_turn", (0, 0))
            p.drawn_turn = (self.turn, drawn[1] + 1 if drawn[0] == self.turn else 1)
            if p.drawn_turn[1] == 2:
                self.fire(p, "draw_second")
            opp = self.opponent(p)
            self.fire(opp, "opp_draw", context=p)

    def setup(self):
        self.audit("start", players=[p.name for p in self.players], first_player=0,
                   life=[p.life for p in self.players], turn_unit="player-turn")
        for p in self.players:
            while True:
                p.library = [CardInstance(c) for c in p.deck]
                p.library.shuffle(self.rng)
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

    def play(self) -> Player | None:
        self.setup()
        while not self.over and self.turn < self.max_turns:
            counts = getattr(self, "spells_cast", {})
            self.last_turn_spells = {k: v for k, v in counts.items() if k != "turn"} \
                if counts.get("turn") == self.turn else {}       # werewolves: spells cast in the turn that ends
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
            self.cycle_spare(p)
            self.turn_face_up(p)
            self.graveyard_abilities(p)
            self.level_up_classes(p)

    def level_up_classes(self, p: Player):
        """Gain the next level of a Class with the mana left after the main phase."""
        for perm in list(p.battlefield):
            for idx, act in enumerate(perm.card.activated):
                if act.extra_costs.get("level_from") is not None and not self.over and self.can_activate(p, perm, idx):
                    self.activate_ability(p, perm, idx)

    def graveyard_abilities(self, p: Player):
        """Return-from-graveyard and exile-to-draw abilities, with the mana left after the main phase."""
        for card in list(p.graveyard):
            if self.over or card not in p.graveyard:
                continue
            for idx in range(len(card.gy_activated)):
                if self.activate_graveyard(p, card, idx):
                    break
            if card not in p.graveyard:
                continue
            if card.gy_return and len(p.hand) < 7 and self.pay(p, card.gy_return) is not None:
                p.graveyard.remove(card)
                p.hand.append(card)
                self.log(f"returns {card.name} from the graveyard to hand", p)
            elif card.gy_exile_draw and (not card.gy_needs_speed or p.speed >= 4) and p.library \
                    and self.pay(p, card.gy_exile_draw) is not None:
                p.graveyard.remove(card)
                p.exile.append(card)
                self.log(f"exiles {card.name} from the graveyard to draw", p)
                self.draw(p, 1)

    def can_activate_graveyard(self, p: Player, card: CardDef, idx: int = 0) -> bool:
        return graveyard.can_activate(self, p, card, idx)

    def activate_graveyard(self, p: Player, card: CardDef, idx: int = 0) -> bool:
        return graveyard.activate(self, p, card, idx)

    def turn_face_up(self, p: Player):
        """Turn face-down creatures (disguise, morph, megamorph) face up when their cost can be paid with the
        mana that's left."""
        for perm in list(p.battlefield):
            if perm.hidden is None:
                continue
            alt = next((a for a in perm.hidden.alt_costs if a.kind in ("disguise", "morph", "megamorph")), None)
            if alt is not None and self.pay(p, alt.cost) is not None:
                self.log(f"turns {perm.hidden.name} face up", p)
                perm.card, perm.hidden = perm.hidden, None
                if alt.kind == "megamorph":
                    perm.counters["+1/+1"] = perm.p1 + 1
                self.fire(p, "turned_face_up", perm)

    def cycle_spare(self, p: Player):
        """Cycle (and landcycle) cards that aren't going to be cast, with the mana left after the main phase:
        a card with a landcycling cost while the land drops are short, a cycling card that costs more than we
        can reach soon, or any cycling card when the hand is full."""
        for card in list(p.hand):
            spec = card.cycling
            if not spec or card not in p.hand or self.over:
                continue
            lands = sum(x.card.is_land for x in p.battlefield)
            if spec["land"]:
                if lands + sum(c.is_land for c in p.hand) >= 5:
                    continue
            elif not (card.cmc > lands + 2 or len(p.hand) > 7):
                continue
            if self.pay(p, spec["cost"]) is None:
                continue
            self.discard_card(p, card)
            self.log(f"cycles {card.name}", p)
            for trig in card.cycle_self_triggers:
                self.queue_trigger(p, trig.effects, None, f"{card.name}: cycled")
            if spec["land"]:
                want = spec["land"]
                found = next((c for c in p.library if c.is_land and (
                    want == "any" or (want == "basic" and is_basic_land(c)) or want in c.subtypes)), None)
                if found is not None:
                    p.library.remove(found)
                    p.hand.append(found)
                    self.log(f"fetches {found.name}", p)
                p.library.shuffle(self.rng)
            else:
                self.draw(p)
            self.settle()

    def take_turn(self, p: Player):
        opp = self.opponent(p)
        for pl in self.players:
            pl.lost_life_turn = pl.perm_left_turn = False
            pl.entered_nonland_turn = 0
            pl.my_turn = pl is p
            pl.discarded_cards = []
            pl.life_gained_turn = 0
            pl.attacked_with = 0
            pl.creature_died_turn = False
            if isinstance(pl.graveyard, Graveyard):
                pl.graveyard.descents = 0
        self.creature_died_turn = False
        self.step = "untap"
        for perm in self.opponent(p).battlefield:
            if perm.card.untap_each_untap:
                perm.tapped = False
        for perm in p.battlefield:
            if perm.skip_untap:
                perm.skip_untap -= 1        # "doesn't untap during its controller's next untap step"
            elif perm.tapped and perm.counters.get("stun"):
                perm.counters["stun"] -= 1   # a stun counter is removed instead of untapping
            elif perm.tapped and perm.auras and auras.blocks_untap(perm):
                pass
            elif perm.tapped and perm.card.no_untap:
                pass                        # "~ doesn't untap during your untap step."
            else:
                perm.tapped = False
            perm.sick = False
            perm.loyalty_used = False
        p.land_played = False
        p.sacrificed_turn = 0
        self.animate_turn_creatures(p)
        self.step = "upkeep"
        self.begin_upkeep(p)
        self.settle()
        if self.over:
            return
        self.step = "draw"
        self.fire(opp, "opp_draw_step")
        self.fire(p, "draw_step")
        for pl in self.players:
            self.fire(pl, "each_draw_step", context=p)
        if self.turn > 1:
            self.draw(p)
            self.settle()
            if self.over:
                return
        self.step = "main1"
        for perm in list(p.battlefield):
            if perm.card.is_saga:
                self.add_lore(perm)
        self.fire(p, "main1_begin")
        self.settle()
        if self.over:
            return
        self.main_phase(p)
        if self.over:
            return
        self.combat(p, opp)
        p.pool.clear()                       # Firebending mana lasts until end of combat
        if self.over:
            return
        self.step = "main2"
        self.fire(p, "main2_begin")
        self.fire(p, "survival")
        self.settle()
        if self.over:
            return
        self.main_phase(p)
        if self.over:
            return
        self.step = "end_step"
        leaving, self.end_cleanup = self.end_cleanup, []
        for perm, how in leaving:
            if perm in perm.controller.battlefield:
                self.log(f"{perm.card.name} is {'sacrificed' if how == 'sacrifice' else 'exiled'} at end of turn", perm.controller)
                if how == "sacrifice":
                    self.sacrifice(perm)
                else:
                    self.leave_battlefield(perm, "exile")
        self.fire(p, "end_step")
        waiting, self.blinked = self.blinked, []
        for card, owner in waiting:
            self.enter_battlefield(owner, card)
            self.log(f"{card.name} returns to the battlefield", owner)
        for perm in list(p.battlefield):
            if perm.impending and perm.counters.get("time"):
                perm.counters["time"] -= 1
            if perm.blitz:
                self.log(f"sacrifices blitzed {perm.card.name}", p)
                self.sacrifice(perm)
            if perm.dashed:
                self.log(f"returns dashed {perm.card.name} to hand", p)
                self.leave_battlefield(perm, "hand")
            if perm.unearthed:
                self.leave_battlefield(perm, "exile")
            if perm.warped and self.leave_battlefield(perm, "exile"):
                p.exile.remove(perm.front)
                p.warp_exile.append(perm.front)
                p.exiled_turn[perm.front.name] = self.turn
                self.log(f"exiles warped {perm.card.name}", p)
        self.run_priority(until_empty_stack=False)
        if self.over:
            return
        self.step = "cleanup"
        for victim, owner in self.stolen:
            if victim in victim.controller.battlefield:
                victim.controller.battlefield.remove(victim)
                victim.controller = owner
                owner.battlefield.append(victim)
        self.stolen = []
        while len(p.hand) > 7 and not any(x.card.no_max_hand for x in p.battlefield):
            card = p.ai.choose_discard(self, p)
            self.discard_card(p, card)
        for perm in p.battlefield + opp.battlefield:
            perm.damage = 0
            perm.deathtouched = False
            perm.pump_p = perm.pump_t = 0
            perm.temp_kw.clear()
            perm.regeneration_shields = 0
            perm.prevent_next = 0
            perm.damaged_by = []
            perm.regeneration_blocked = False
            copies.revert(perm)
            if not (perm.animated and perm.animated.text in ("earthbend", "permanent")):
                perm.animated = None
            perm.crewed = False
            perm.saddled = False
        p.next_creature_counters = 0
        p.prevent_next = opp.prevent_next = 0
        self.expire_continuous_effects()
        for pl in self.players:
            pl.granted_fb = []
        self.state_based_actions()

    def begin_upkeep(self, p: Player):
        """Queue one-shot delayed draws before any upkeep ability can create new ones."""
        waiting, self.delayed_upkeep = self.delayed_upkeep, []
        for controller, amount, source, name, scope in waiting:
            if scope == "you" and p is not controller:
                self.delayed_upkeep.append((controller, amount, source, name, scope))
            else:
                self.queue_trigger(controller, [Effect("draw", amount)], source, name)
        rebounds, self.rebound_upkeep = self.rebound_upkeep, []
        for controller, card, version in rebounds:
            if p is not controller:
                self.rebound_upkeep.append((controller, card, version))
            else:
                self.queue_trigger(controller, [Effect("rebound_cast")], name=f"{card.name}: rebound",
                                   context=(card, version))
        creature_keywords.upkeep(self, p)
        alt_casts.upkeep(self, p)
        self.fire(p, "upkeep")
