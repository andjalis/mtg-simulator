"""Game methods for combat: attacks, blocks and combat damage."""
from __future__ import annotations

from .state import Permanent, Player, can_block


class CombatMixin:
    def combat(self, p: Player, opp: Player):
        self.step = "declare_attackers"
        self.attackers, self.blocks, self.attack_targets = [], {}, {}
        self.fire(p, "begin_combat")
        self.settle()
        if self.over:
            return
        self.hook(p, "before_attacks")(self, p)
        if self.over:
            return
        attackers = [a for a in p.ai.choose_attackers(self, p, opp) if a.can_attack()]
        attackers += [a for a in p.creatures if (a.card.must_attack or a.has("must_attack_now")) and a.can_attack()
                      and a not in attackers]
        self.attackers = list(attackers)
        if not attackers:
            return
        targets = self.hook(p, "choose_attack_targets")(self, p, attackers) or {}
        for a in attackers:
            t = targets.get(a, opp)
            self.attack_targets[a] = t if (t is opp or (isinstance(t, Permanent) and t.is_planeswalker
                                                         and t in opp.battlefield)) else opp
            if not a.has("vigilance"):
                a.tapped = True
                self.fire(p, "becomes_tapped", a)
        p.attacked_with = len(attackers)
        self.log(f"attacks with {attackers}" + (
            f" ({ {a: t for a, t in self.attack_targets.items() if t is not opp} })"
            if any(t is not opp for t in self.attack_targets.values()) else ""), p)
        for a in attackers:
            self.fire(p, "attacks", a)
            self.fire(p, "creature_attacks")
        if len(attackers) == 1:
            self.fire(p, "attacks_alone", context=attackers[0])
        self.fire(p, "you_attack")
        self.run_priority(until_empty_stack=False)
        attackers = [a for a in self.attackers if a in p.battlefield]
        self.attackers = attackers
        if self.over or not attackers:
            return

        self.step = "declare_blockers"
        blocks = self.force_blocks(opp, attackers, opp.ai.choose_blocks(self, opp, p, attackers))
        used = set()
        legal = {}
        for a in attackers:
            bl = [b for b in blocks.get(a, []) if b not in used and b in opp.battlefield and can_block(b, a)]
            if a.has("menace") and len(bl) == 1:
                bl = []
            if bl:
                legal[a] = bl
                used.update(bl)
        blocks = legal
        self.blocks = blocks
        if blocks:
            self.log(f"blocks {blocks}", opp)
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
        for a in attackers:
            if a not in p.battlefield:
                continue
            target = self.attack_targets.get(a, opp)
            if isinstance(target, Permanent) and target not in opp.battlefield:
                target = None   # its planeswalker is gone: no damage
            if a in blocks:
                alive = [b for b in blocks[a] if b in opp.battlefield]
                if deals_now(a) and a.power > 0:
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
                        hits.append((b, a, b.power))
            elif deals_now(a) and a.power > 0 and target is not None:
                hits.append((a, target, a.power))
        for src, tgt, amt in hits:
            self.deal_damage(tgt, amt, by=src.controller, cause=f"{src.card.name}: combat damage", source=src, combat=True)
            if isinstance(tgt, Player):
                self.fire(src.controller, "combat_damage_player", src, context=tgt)
                self.fire(src.controller, "ally_combat_damage")
        self.state_based_actions()
        self.settle()
