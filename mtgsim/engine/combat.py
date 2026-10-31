"""Game methods for combat: attacks, blocks and combat damage."""
from __future__ import annotations

from .. import ring
from ..cards import Effect
from .state import Permanent, Player, can_block
from ..cx_lures import extra_blocks as cx_extra_blocks, max_blockers as cx_max_blockers


def extra_blocks(me, attackers, blocks):
    """Give a creature that can block more than one attacker the unblocked attackers it survives, biggest first."""
    blocks = {a: list(bl) for a, bl in blocks.items()}
    for b in me.creatures:
        if not cx_extra_blocks(b):
            continue
        mine = [a for a, bl in blocks.items() if b in bl]
        if not mine:
            continue
        taken = sum(a.power for a in mine)
        for a in sorted((a for a in attackers if not blocks.get(a) and can_block(b, a)), key=lambda a: -a.power):
            if len(mine) > cx_extra_blocks(b) or taken + a.power >= b.toughness - b.damage:
                break
            blocks[a] = [b]
            mine.append(a)
            taken += a.power
    return blocks


class CombatMixin:
    def combat(self, p: Player, opp: Player):
        self._combat(p, opp)
        if not self.over:
            self.end_combat(p)
        while self.extra_combats and not self.over:
            self.extra_combats -= 1
            for player in self.players:
                player.pool.clear()
            self._combat(p, opp)
            if not self.over:
                self.end_combat(p)

    def end_combat(self, p: Player):
        self.step = "end_combat"
        waiting, self.delayed_end_combat = self.delayed_end_combat, []
        for controller, source in waiting:
            self.queue_trigger(controller, [Effect("sacrifice_self", target="self")], source,
                               f"{source.card.name}: decayed")
        waiting, self.end_combat_effects = self.end_combat_effects, []
        for controller, effects, source, subject in waiting:
            name = source.card.name if isinstance(source, Permanent) else "delayed"
            self.queue_trigger(controller, effects, source, f"{name}: at end of combat", context=subject)
        self.fire(p, "end_combat")
        self.run_priority(until_empty_stack=False)

    def _combat(self, p: Player, opp: Player):
        self.step = "declare_attackers"
        self.attackers, self.blocks, self.attack_targets = [], {}, {}
        self.provoked = {}
        self.fire(p, "begin_combat")
        for pl in self.players:
            self.fire(pl, "each_begin_combat")
        self.settle()
        if self.over:
            return
        self.hook(p, "before_attacks")(self, p)
        if self.over:
            return
        attackers = [a for a in p.ai.choose_attackers(self, p, opp) if a.can_attack()
                     and (not a.card.attack_needs or any(a.card.attack_needs in x.card.subtypes for x in opp.battlefield))]
        from ..batch1_templates import curses_on
        cursed_to_attack = any(c.card.advanced_rules.get('curse_must_attack') for c in curses_on(self, p))
        attackers += [a for a in p.creatures if (a.card.must_attack or a.has("must_attack_now") or cursed_to_attack)
                      and a.can_attack() and a not in attackers]
        from ..backlog_templates import combat_limit
        limit = combat_limit(self, 'attack')
        if limit is not None:
            attackers = attackers[:limit]
        from ..batch1_templates import drop_solo, drop_solo_blocks
        attackers = drop_solo(attackers)
        self.attackers = list(attackers)
        if not attackers:
            return
        targets = self.hook(p, "choose_attack_targets")(self, p, attackers) or {}
        for a in attackers:
            t = targets.get(a, opp)
            self.attack_targets[a] = t if (t is opp or (isinstance(t, Permanent) and t.is_planeswalker
                                                         and t in opp.battlefield)) else opp
            from ..advanced_templates import attack_tax
            tax = attack_tax(self, opp) if self.attack_targets[a] is opp else 0
            if tax and self.pay(p, {"generic": tax}) is None:
                self.attack_targets.pop(a, None)
                continue
            if not a.has("vigilance"):
                a.tapped = True
                self.fire(p, "becomes_tapped", a)
        attackers = [a for a in attackers if a in self.attack_targets]
        self.attackers = attackers
        if not attackers:
            return
        from ..batch1_templates import enlist
        enlist(self, p, attackers)
        if any(t is opp for t in self.attack_targets.values()):
            from ..batch1_templates import curse_event
            curse_event(self, opp, 'curse_attacked')
        p.attacked_with = len(attackers)
        self.log(f"attacks with {attackers}" + (
            f" ({ {a: t for a, t in self.attack_targets.items() if t is not opp} })"
            if any(t is not opp for t in self.attack_targets.values()) else ""), p)
        for a in attackers:
            self.fire(p, "attacks", a)
            self.fire(p, "creature_attacks", context=a)
            ring.attacks(self, p, a)
        if len(attackers) == 1:
            self.fire(p, "attacks_alone", context=attackers[0])
        self.fire(p, "you_attack")
        if len(attackers) >= 2:
            self.fire(p, "attack_two_plus")
        if len(attackers) >= 3:
            self.fire(p, "attack_three_plus")
        for a in attackers:
            if self.attack_targets.get(a) is opp or isinstance(self.attack_targets.get(a), Permanent):
                self.fire(opp, "opp_creature_attacks", context=a)
        self.run_priority(until_empty_stack=False)
        attackers = [a for a in self.attackers if a in p.battlefield]
        self.attackers = attackers
        if self.over or not attackers:
            return

        self.step = "declare_blockers"
        blocks = self.force_blocks(opp, attackers, opp.ai.choose_blocks(self, opp, p, attackers))
        blocks = extra_blocks(opp, attackers, blocks)
        used = {}                       # blocker -> attackers it blocks ("can block an additional creature")
        legal = {}
        block_limit = combat_limit(self, 'block')
        for a in attackers:
            bl = [b for b in blocks.get(a, []) if used.get(b, 0) <= cx_extra_blocks(b) and b in opp.battlefield
                  and can_block(b, a)]
            if block_limit is not None:
                available = max(0, block_limit - len(used))
                retained = []
                for blocker in bl:
                    if blocker in used or available > 0:
                        retained.append(blocker)
                        if blocker not in used:
                            available -= 1
                bl = retained
            if a.has("menace") and len(bl) == 1:
                bl = []
            if a.card.min_blockers and len(bl) < a.card.min_blockers:
                bl = []
            limit = cx_max_blockers(a)
            if limit and len(bl) > limit:
                bl = bl[:limit]
            if bl:
                legal[a] = bl
                for b in bl:
                    used[b] = used.get(b, 0) + 1
        blocks = drop_solo_blocks(legal)
        self.blocks = blocks
        if blocks:
            self.log(f"blocks {blocks}", opp)
        for a, bl in blocks.items():
            for b in bl:
                self.fire(opp, "blocks", b, context=a)
            self.fire(p, "becomes_blocked", a, context=bl[0])
            ring.blocked(self, p, a, bl)
        for a in attackers:
            if a not in blocks:
                self.fire(p, "unblocked", a)
        fighting = set(attackers) | {b for bl in blocks.values() for b in bl}
        for pl in (p, opp):            # a face-down creature in combat is turned up when that can be paid for
            self.turn_face_up(pl, only=fighting)
        p.ai.after_blocks(self, p, attackers, blocks)
        if self.over:
            return
        self.hook(p, "sneak")(self, p, attackers, blocks)
        self.run_priority(until_empty_stack=False)
        if self.over:
            return

        self.step = "combat_damage"
        attackers = self.attackers
        first = any(c.has("first strike") or c.has("double strike")
                    for c in attackers + [b for bl in blocks.values() for b in bl])
        if first:
            self.combat_damage(p, opp, attackers, blocks,
                               lambda c: c.has("first strike") or c.has("double strike"))
            if self.over:
                return
        self.combat_damage(p, opp, attackers, blocks,
                           lambda c: not first or c.has("double strike") or not c.has("first strike"))

    def combat_damage(self, p, opp, attackers, blocks, deals_now):
        hits = []  # (source, target, amount)
        budget = {}   # a blocker blocking several attackers divides its damage: lethal to each in turn
        for a in attackers:
            for b in blocks.get(a, ()):
                budget[b] = budget.get(b, 0) + 1
        budget = {b: b.power for b, n in budget.items() if n > 1}
        for a in attackers:
            if a not in p.battlefield:
                continue
            target = self.attack_targets.get(a, opp)
            if isinstance(target, Permanent) and target not in opp.battlefield:
                target = None   # its planeswalker is gone: no damage
            if a in blocks:
                alive = [b for b in blocks[a] if b in opp.battlefield]
                if deals_now(a) and a.power > 0 and target is not None and a.card.advanced_rules.get('assign_unblocked') \
                        and not a.abilities_suppressed and sum(max(0, b.toughness - b.damage) for b in alive) > a.power:
                    hits.append((a, target, a.power))     # can't kill its blockers: hit the defender instead
                elif deals_now(a) and a.power > 0:
                    remaining = a.power
                    for i, b in enumerate(alive):
                        lethal = 1 if a.has("deathtouch") else max(0, b.toughness - b.damage)
                        last = i == len(alive) - 1
                        amt = remaining if (last and not a.has("trample")) else min(remaining, lethal)
                        if amt:
                            hits.append((a, b, amt))
                        remaining -= amt
                    if remaining > 0 and a.has("trample") and target is not None:
                        hits.append((a, target, remaining))
                for b in alive:
                    if deals_now(b) and b.power > 0:
                        if b in budget:
                            amt = min(budget[b], 1 if b.has("deathtouch") else max(0, a.toughness - a.damage))
                            budget[b] -= amt
                        else:
                            amt = b.power
                        if amt:
                            hits.append((b, a, amt))
            elif deals_now(a) and a.power > 0 and target is not None:
                hits.append((a, target, a.power))
        if any(isinstance(tgt, Player) for _, tgt, _ in hits):
            self.fire(p, "allies_hit_player")
        for src, tgt, amt in hits:
            self.deal_damage(tgt, amt, by=src.controller, cause=f"{src.card.name}: combat damage", source=src, combat=True)
            if isinstance(tgt, Player):
                from ..batch1_templates import combat_hit
                combat_hit(self, src, tgt)
                from ..dungeon_mechanics import initiative_combat
                initiative_combat(self, src, tgt)
                self.fire(src.controller, "combat_damage_player", src, context=tgt)
                ring.combat_damage(self, src.controller, src, tgt)
                from ..advanced_templates import cipher_damage
                cipher_damage(self, src)
                self.fire(src.controller, "ally_combat_damage")
        self.state_based_actions()
        self.settle()
