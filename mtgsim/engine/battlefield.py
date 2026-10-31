"""Game methods for permanents entering and changing: enter the battlefield, sagas, tokens, transform."""
from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING

from .. import auras, copies, creature_keywords, proliferate
from ..cards import Activated, CardDef, Effect, make_token
from .. import rules_events
from ..identity import CardInstance, instance
from .policy import choose_color
from .state import Permanent, StackItem, is_basic_land

if TYPE_CHECKING:
    from .state import Player

# "As ~ enters, roll a d6/six-sided die. It enters with a number of +1/+1 counters on it
# equal to the result." (Hydradoodle, Jumbo Imp, Hammer Jammer, Temp of the Damned,
# Neverwinter Hydra). The roll happens during the enters event itself, not as a trigger:
# the counters land on the card before state-based actions run, so 0/0 bodies survive.
_AS_ENTERS_ROLL = re.compile(
    r"As [^\n]+? enters, roll (a |an |one |two |three |four |five |X )?"
    r"(?:d(\d+)|(\w+)-sided (?:die|dice))\. "
    r"(?:[^\n]+?) enters with a number of ([+\w/\-]+) counters? on it equal to the "
    r"(?:total of those results|result)")
_DIE_SIDES = {"four": 4, "six": 6, "eight": 8, "ten": 10, "twelve": 12, "twenty": 20}
_DIE_COUNT = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def as_enters_roll(card: CardDef, x: int = 0):
    """(sides, count, counter kind) when ``card`` is an "As ~ enters, roll ... enters with
    a number of counters on it equal to the result" creature, else None. ``x`` is the {X}
    paid for cards like Hydradoodle that roll X dice."""
    m = _AS_ENTERS_ROLL.search(card.oracle or "")
    if m is None:
        return None
    prefix = (m[1] or "").strip()
    count = max(0, x) if prefix == "X" else _DIE_COUNT.get(prefix, 1)
    sides = int(m[2]) if m[2] else _DIE_SIDES.get((m[3] or "six").lower(), 6)
    return sides, count, m[4].lower()


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
        from ..residual_templates import blocked_entry
        if blocked_entry(self, card, physical_card):
            return None
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
        perm.rules_timestamp = self.next_effect_timestamp()
        from ..advanced_templates import rules
        if card.is_land and not card.basic and any(rules(x).get("land_conversion") for pl in self.players for x in pl.battlefield):
            from ..continuous import refresh
            perm._mountain_conversion = True
            refresh(perm)
            card = perm.card
            perm.tapped = False
        if card.start_engines and p.speed == 0:
            p.speed = 1
        perm.entered_x = x
        perm.prepared = bool(card.prepared and card.back is not None)
        perm.spent_color = getattr(self, "_spent", "")
        cast = getattr(self, "_entry_cast", None)       # the spell this permanent resolved from (cx_condlib)
        if cast is not None:
            self._entry_cast = None
            perm.kicked = cast[0]
            perm.cast_from_hand = cast[1]
            perm.mana_spent = cast[2]
        others = sum(x.card.is_land for x in p.battlefield)
        cond = card.tapped_condition
        if cond.startswith("other_subtype:"):
            _, subtype, count = cond.split(":")
            perm.tapped = sum(subtype in x.card.subtypes for x in p.battlefield) < int(count)
        elif cond == "unless_2_lands":
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
        elif cond.startswith("reveal:"):     # "you may reveal a Giant card from your hand. If you don't, ... tapped"
            import json
            from ..cx_condlib import _card_ok
            specs = json.loads(cond[7:])
            perm.tapped = not any(_card_ok(c, spec) for c in p.hand for spec in specs)
        elif cond == "always":
            perm.tapped = True
        elif cond.startswith("unless_basics>="):
            perm.tapped = sum(is_basic_land(x.card) for x in p.battlefield) < int(cond[15:])
        elif cond.startswith("unless_opp_lands>="):
            perm.tapped = sum(x.card.is_land for x in self.opponent(p).battlefield) < int(cond[18:])
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
        elif card.choose_type == "land":
            # Shimmer: "As ~ enters, choose a land type. Each land of the chosen type has
            # phasing." The default pick is the opponent's most common basic land type.
            counts: dict = {}
            for pl in self.players:
                weight = 1 if pl is self.opponent(p) else 0
                for c in pl.deck:
                    if c.is_land and is_basic_land(c):
                        for t in c.subtypes:
                            counts[t] = counts.get(t, 0) + weight
            if not counts:
                for c in p.deck:
                    if c.is_land and is_basic_land(c):
                        for t in c.subtypes:
                            counts[t] = counts.get(t, 0) + 1
            perm.chosen_type = max(counts, key=counts.get, default="Island")
        elif card.choose_type == "basic_land":
            perm.card = dataclasses.replace(card, produces=frozenset({choose_color(self, p)}))
        if card.loyalty:
            perm.counters["loyalty"] = card.loyalty
        if card.advanced_rules.get("sunburst"):
            kind = "+1/+1" if card.is_creature else "charge"
            perm.counters[kind] = len(getattr(self, "_entry_mana_colors", ()))
        if card.etb_counters:
            n = x if card.etb_counters == -1 else card.etb_counters
            if n:
                perm.counters["+1/+1"] = n
        if card.etb_counters_if and self._etb_cond(p, card.etb_counters_if[0]):
            perm.counters["+1/+1"] = perm.p1 + card.etb_counters_if[1]
        if card.advanced_rules.get("cx_etb_if"):
            from .. import cx_replace
            cx_replace.entry_counters(self, p, perm)
        if card.entry_counter_quantity:
            from ..backlog_templates import amount
            kind, spec = card.entry_counter_quantity
            perm.counters[kind] = perm.counters.get(kind, 0) + amount(self, p, spec)
        if card.etb_named_counters:
            perm.counters[card.etb_named_counters[0]] = card.etb_named_counters[1]
        roll = as_enters_roll(card, perm.entered_x)
        if roll is not None:
            sides, n, kind = roll
            if n > 0:
                from ..dungeon_mechanics import roll as roll_dice
                roll_dice(self, p, Effect("die_roll", data={"sides": sides, "count": n}), None, None, None)
                total = self._die_rolls.get(p, 0)     # roll() records the total per player
                perm.counters[kind] = perm.counters.get(kind, 0) + total
                perm._etb_roll_consumed = True        # stack.py: the etb die_roll trigger is spent
        for kind, n in (counters or {}).items():
            perm.counters[kind] = perm.counters.get(kind, 0) + n
        from ..residual_templates import tapped_by_opponent
        perm.tapped |= tapped or tapped_by_opponent(self, perm)
        p.battlefield.append(perm)
        from ..batch1_templates import soulbond_pair
        soulbond_pair(self, p, perm)
        if perm.is_creature:
            from ..batch1_templates import curse_event
            curse_event(self, p, 'curse_creature_enters')
        self._residual_source_index = None
        if not card.is_land:
            p.entered_nonland_turn += 1
        if card.turn_creature and p is self.active:
            self.animate_turn_creatures(p)
        self.rule_events.emit(rules_events.RulesEvent("zone_change", p, source=perm,
            before=before, source_zone=source_zone, destination="battlefield", reason="enter_battlefield"))
        host = getattr(self, "_aura_host", None)
        if host is not None and card.aura:
            auras.attach(self, perm, host)
            self._aura_host = None
        equipment = getattr(self, "_equip_on_enter", None)
        if equipment is not None and perm.is_creature:
            equipment.attached_to = perm         # living weapon
            self._equip_on_enter = None
        creature_keywords.enters(self, p, perm)
        if perm.is_creature:
            for source in list(p.battlefield):
                grant = source.card.entry_counter_grant
                if grant and not source.silenced and not (grant[2] and source is perm):
                    perm.counters[grant[0]] = perm.counters.get(grant[0], 0) + grant[1]
        if tapped_attacking:
            perm.tapped = True
            self.attackers.append(perm)
            self.attack_targets[perm] = self.opponent(p)
        from ..residual_templates import suppressed
        if card.etb_effects and not any(t.event == "etb" for t in card.triggers):
            if not (perm.is_creature and suppressed(self, "entry")):
                self.queue_trigger(p, card.etb_effects, perm, card.name)  # a hand-built CardDef
        else:
            self.fire(p, "etb", perm)
        if card.is_saga:
            self.add_lore(perm)
        if perm.is_creature:
            self.fire(p, "other_creature_enters", subject=perm)
            for pl in self.players:
                self.fire(pl, "any_creature_enters", context=perm)
        from ..backlog_templates import filtered_entry
        filtered_entry(self, perm)
        self.fire(p, "permanent_enters", subject=perm)
        for pl in self.players:
            if pl is not p:
                # "~ or another Zombie enters" (Noxious Ghoul): flagged triggers hear any entry;
                # stack.py skips the controller-scoped ones.
                self.fire(pl, "permanent_enters", subject=perm)
        if card.is_land:
            self.fire(p, "land_enters", subject=perm)
        if getattr(self, '_entry_batch', None) is None:
            self.state_based_actions()
        return perm

    def enter_battlefield_many(self, player, cards, **kwargs):
        from ..backlog_templates import entry_batch
        from ..residual_templates import blocked_entry
        cards = list(cards)
        previous = getattr(self, "_batch_entry_suppressed", False)
        self._batch_entry_suppressed = previous or any((c.advanced_rules.get("suppress_entry") or c.advanced_rules.get("suppress_entry_death")) and not blocked_entry(self, c) for c in cards)
        try:
            with entry_batch(self):
                return [self.enter_battlefield(player, card, **kwargs) for card in cards]
        finally:
            self._batch_entry_suppressed = previous

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
        from ..advanced_templates import rules
        manufacturers = sum(bool(rules(x).get("manufactor")) for x in p.battlefield)
        if d.get("kind") in ("clue", "food", "treasure") and manufacturers and not d.get("manufactured"):
            count = (n if n is not None else eff.amount) * 3 ** (manufacturers - 1)
            from ..backlog_templates import entry_batch
            with entry_batch(self):
                for token_kind in ("clue", "food", "treasure"):
                    self.create_token(p, Effect("token", count, data={"kind": token_kind, "manufactured": True}))
            return
        count = n if n is not None else eff.amount
        count *= 2 ** sum(bool(x.card.token_double) for x in p.battlefield if not x.abilities_suppressed)
        from ..backlog_templates import entry_batch
        with entry_batch(self):
            for _ in range(count):
                card = make_token(d.get("name", ""), d.get("power", 0), d.get("toughness", 0), d.get("keywords", ()),
                                  d.get("triggers"), d.get("kind", ""), d.get("artifact", False), d.get("pt_per", ""),
                                  colors=d.get("colors", ()))
                if d.get('token_name'):
                    card = dataclasses.replace(card, name=d['token_name'])
                if d.get("activated"):
                    card = dataclasses.replace(card, activated=d["activated"])
                if d.get("spawn_mana"):     # Eldrazi Spawn / Scion: "Sacrifice this creature: Add {C}."
                    card = dataclasses.replace(card, produces=frozenset({"C"}), mana_sac_only=True)
                if d.get("mercenary"):
                    card = dataclasses.replace(card, activated=[Activated("ability", {"generic": 0}, effects=[
                        Effect("pump", 1, 0, target="creature_mine")], extra_costs={"tap": True}, sorcery=True,
                        text="{T}: Target creature you control gets +1/+0 until end of turn.")])
                perm = self.enter_battlefield(p, card, tapped_attacking=d.get("attacking", False) and self.step in
                                              ("declare_attackers", "declare_blockers"))
                if d.get("tapped"):
                    perm.tapped = True
                if d.get("end"):
                    self.end_cleanup.append((perm, d["end"]))
        self.log(f"creates {n if n is not None else eff.amount} {d.get('kind') or d.get('name')} token(s)", p)

    def transform(self, perm: Permanent):
        front = getattr(perm, "front_face", None)
        flip_back = front is not None and front.back is perm.card   # a transformed permanent turns face up again
        back = front if flip_back else perm.card.back
        if back is None or perm not in perm.controller.battlefield:
            return
        if not flip_back:
            perm.front_face = perm.card
        self.log(f"{perm.card.name} transforms into {back.name}", perm.controller)
        was_saga = perm.card.is_saga
        perm.card = back
        perm.counters.pop("lore", None)
        if was_saga:   # exiled and returned: a new object
            perm.sick = True
            perm.entered_turn = self.turn
            self.fire(perm.controller, "etb", perm)
