"""Game methods for permanents entering and changing: enter the battlefield, sagas, tokens, transform."""
from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from .. import auras, copies, proliferate
from ..cards import Activated, CardDef, Effect, make_token
from .. import rules_events
from ..identity import CardInstance, instance
from .policy import choose_color
from .state import Permanent, StackItem, is_basic_land

if TYPE_CHECKING:
    from .state import Player


class BattlefieldMixin:
    def exile_until_leaves(self, src: Permanent, perms: list):
        """Exile perms until src leaves the battlefield (Seam Rip, Pinnacle Starcage)."""
        for x in perms:
            owner, card, token = x.controller, x.front, x.front.is_token
            if self.leave_battlefield(x, "exile"):
                self.log(f"exiles {x.card.name} until {src.card.name} leaves", src.controller)
                if not token:
                    src.exiled_cards.append((card, owner))

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
        perm.tapped |= tapped
        p.battlefield.append(perm)
        if card.turn_creature and p is self.active:
            self.animate_turn_creatures(p)
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
                              colors=d.get("colors", ()), enchantment=d.get("enchantment", False))
            if d.get("token_name") or d.get("legendary") or d.get("cant_block"):
                card = dataclasses.replace(card, name=d.get("token_name", card.name),
                                           legendary=d.get("legendary", False), cant_block=d.get("cant_block", False))
            if d.get("sacrifice_mana"):
                card = dataclasses.replace(card, produces=frozenset(d["sacrifice_mana"]),
                                           mana_sac=True, mana_sac_no_tap=True)
            if d.get("mercenary"):
                card = dataclasses.replace(card, activated=[Activated("ability", {"generic": 0}, effects=[
                    Effect("pump", 1, 0, target="creature_mine")], extra_costs={"tap": True}, sorcery=True,
                    text="{T}: Target creature you control gets +1/+0 until end of turn.")])
            perm = self.enter_battlefield(p, card, tapped_attacking=d.get("attacking", False) and self.step in
                                          ("declare_attackers", "declare_blockers"), tapped=d.get("tapped", False))
            perm.temp_kw.update(d.get("temp_keywords", ()))
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
