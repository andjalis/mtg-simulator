"""Actual combat declarations pay correctly scoped mana and Phyrexian taxes."""
import os
from dataclasses import replace
import random
import unittest

from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.cards import Effect, _parse_effects
from mtgsim.engine import Game, Player, StackItem
from mtgsim.cx_combat_costs import attack_cost, pay_attackers, pay_blockers
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, PLAINS, card


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class CombatCosts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0))
        self.g.turn, self.g.step = 3, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None
        self.a.ai.choose_attack_targets = lambda game, me, attackers: getattr(self, "targets", {})

    def put(self, c=BEAR, p=None):
        c = self.db.get(c) if isinstance(c, str) else c
        perm = self.g.enter_battlefield(p or self.a, c)
        perm.sick = False
        return perm

    def mana(self, n, p=None, land=ISLAND):
        return [self.put(land, p) for _ in range(n)]

    def walker(self):
        return self.put(replace(card("Test Walker", "{4}", "Planeswalker — Test", ""), loyalty=8), self.b)

    def attack(self, *creatures, target=None):
        self.a.ai.attack = creatures
        if target:
            self.targets = {c: target for c in creatures}
        self.g.combat(self.a, self.b)

    def test_real_oracle_tax_lines_match(self):
        for name in ("War Tax", "Archangel of Tithes", "Norn's Annex", "Onakke Oathkeeper", "Sphere of Safety",
                     "Collective Restraint", "Baird, Steward of Argive", "Archon of Absolution"):
            with self.subTest(name=name):
                self.assertEqual(self.db.get(name).unsupported, [])
        self.assertEqual(len(self.db.get("Nils, Discipline Enforcer").unsupported), 1)  # end-step trigger
        self.assertEqual(len(self.db.get("Oko, Lord of the Fae").unsupported), 2)  # unrelated loyalty abilities

    def test_player_tax_does_not_protect_planeswalkers(self):
        self.put("Ghostly Prison", self.b)
        walker, bear = self.walker(), self.put()
        self.assertEqual(attack_cost(self.g, bear, self.b).get("generic"), 2)
        self.assertEqual(attack_cost(self.g, bear, walker).get("generic"), 0)
        # The walker needs loyalty to stay on the battlefield at the begin-combat SBA.
        walker.counters["loyalty"] = 8
        self.attack(bear, target=walker)
        self.assertEqual(walker.loyalty, 6)
        self.assertEqual(self.b.life, 20)

    def test_baird_protects_planeswalkers_and_taxes_stack(self):
        self.put("Baird, Steward of Argive", self.b)
        self.put("Archon of Absolution", self.b)
        walker, bear = self.walker(), self.put()
        walker.counters["loyalty"] = 8
        self.assertEqual(attack_cost(self.g, bear, walker).get("generic"), 2)
        self.attack(bear, target=walker)
        self.assertFalse(bear.tapped)
        self.assertEqual(walker.loyalty, 8)
        self.mana(2)
        self.attack(bear, target=walker)
        self.assertEqual(walker.loyalty, 6)

    def test_planeswalker_only_tax(self):
        self.put("Onakke Oathkeeper", self.b)
        walker, bear = self.walker(), self.put()
        self.assertEqual(attack_cost(self.g, bear, self.b).get("generic"), 0)
        self.assertEqual(attack_cost(self.g, bear, walker).get("generic"), 1)

    def test_tithes_attack_tax_requires_untapped_source(self):
        angel, bear = self.put("Archangel of Tithes", self.b), self.put()
        self.assertEqual(attack_cost(self.g, bear, self.b).get("generic"), 1)
        angel.tapped = True
        self.assertEqual(attack_cost(self.g, bear, self.b).get("generic"), 0)
        angel.tapped = False
        angel.silenced_by = self.put(card("Silencer", "{2}", "Enchantment", ""))
        self.assertEqual(attack_cost(self.g, bear, self.b).get("generic"), 0)
        self.g.leave_battlefield(angel, "exile")
        self.assertEqual(attack_cost(self.g, bear, self.b).get("generic"), 0)

    def test_tithes_block_tax_only_while_attacking(self):
        angel, bear = self.put("Archangel of Tithes"), self.put(p=self.b)
        self.a.ai.attack = [angel]
        bear.card = card("Test Flier", "{2}", text="Flying", power=2, toughness=4)
        self.b.ai.block = {angel: [bear]}
        self.attack(angel)
        self.assertEqual(self.g.blocks, {})
        self.assertEqual(self.b.life, 17)
        angel.tapped = False
        self.mana(1, self.b)
        self.attack(angel)
        self.assertEqual(self.g.blocks, {angel: [bear]})

    def test_tithes_does_not_tax_blocks_when_it_stays_home(self):
        self.put("Archangel of Tithes")
        a, b = self.put(), self.put(p=self.b)
        self.attack(a)
        # Verify using the payment helper while no Archangel is attacking.
        self.assertEqual(pay_blockers(self.g, self.b, {a: [b]}), {a: [b]})

    def test_annex_prefers_white_mana_to_life(self):
        self.put("Norn's Annex", self.b)
        bear, land = self.put(), self.mana(1, land=PLAINS)[0]
        self.attack(bear)
        self.assertTrue(land.tapped)
        self.assertEqual(self.a.life, 20)
        self.assertEqual(self.b.life, 18)

    def test_annex_accepts_two_life_and_ignores_wrong_color(self):
        self.put("Norn's Annex", self.b)
        bear, land = self.put(), self.mana(1)[0]
        self.attack(bear)
        self.assertFalse(land.tapped)
        self.assertEqual(self.a.life, 18)
        self.assertEqual(self.b.life, 18)

    def test_annex_mixes_white_mana_and_life_per_creature(self):
        self.put("Norn's Annex", self.b)
        b1, b2 = self.put(), self.put()
        self.mana(1, land=PLAINS)
        self.attack(b1, b2)
        self.assertEqual(self.a.life, 18)
        self.assertEqual(self.b.life, 16)

    def test_annex_and_generic_costs_are_combined(self):
        self.put("Norn's Annex", self.b)
        self.put("Ghostly Prison", self.b)
        bear = self.put()
        self.mana(2, land=PLAINS)
        self.attack(bear)
        self.assertEqual(self.a.life, 18)
        self.assertEqual(self.b.life, 18)

    def test_unaffordable_declaration_does_not_spend_life_or_mana(self):
        self.put("Norn's Annex", self.b)
        self.put("Ghostly Prison", self.b)
        bear, land = self.put(), self.mana(1)[0]
        self.attack(bear)
        self.assertFalse(bear.tapped)
        self.assertFalse(land.tapped)
        self.assertEqual(self.a.life, 20)

    def test_annex_life_payment_prohibited_by_life_lock(self):
        self.put("Norn's Annex", self.b)
        self.put(card("Test Lock", "{2}", "Enchantment", "Your life total can't change."))
        bear = self.put()
        self.attack(bear)
        self.assertFalse(bear.tapped)
        self.mana(1, land=PLAINS)
        self.attack(bear)
        self.assertEqual(self.b.life, 18)

    def test_low_life_rejects_only_unpayable_annex_attacks(self):
        self.put("Norn's Annex", self.b)
        bear = self.put()
        self.a.life = 1
        self.attack(bear)
        self.assertFalse(bear.tapped)
        self.assertEqual(self.a.life, 1)

    def test_tax_removal_rechecks_companions_before_paying(self):
        self.put("Ghostly Prison", self.b)
        c, b1, b2 = self.put("Orcish Conscripts"), self.put(), self.put()
        lands = self.mana(4)
        self.attack(c, b1, b2)
        self.assertEqual(self.g.last_attackers, [b1])
        self.assertFalse(c.tapped)
        self.assertEqual(sum(land.tapped for land in lands), 2)

    def test_tax_removal_rechecks_menace_before_paying(self):
        angel = self.put("Archangel of Tithes")
        threat = self.put(card("Test Threat", "{2}", text="Menace", power=2, toughness=4))
        b1, b2 = self.put(p=self.b), self.put(p=self.b)
        land = self.mana(1, self.b)[0]
        self.a.ai.attack = [angel, threat]
        self.b.ai.block = {threat: [b1, b2]}
        self.attack(angel, threat)
        self.assertEqual(self.g.blocks, {})
        self.assertFalse(land.tapped)

    def test_block_tax_paid_once_per_distinct_blocker(self):
        angel, a1, a2 = self.put("Archangel of Tithes"), self.put(), self.put()
        self.g.attackers = [angel, a1, a2]
        blocker = self.put(p=self.b)
        land = self.mana(1, self.b)[0]
        self.assertEqual(pay_blockers(self.g, self.b, {a1: [blocker], a2: [blocker]}),
                         {a1: [blocker], a2: [blocker]})
        self.assertTrue(land.tapped)

    def test_war_tax_activation_uses_chosen_x_and_survives_source(self):
        source = self.put("War Tax", self.b)
        self.mana(3, self.b)
        self.assertTrue(self.g.activate_ability(self.b, source, 0, x=2))
        self.g.settle()
        self.g.leave_battlefield(source, "exile")
        bear, walker = self.put(), self.walker()
        self.assertEqual(attack_cost(self.g, bear, self.b).get("generic"), 2)
        self.assertEqual(attack_cost(self.g, bear, walker).get("generic"), 2)
        self.assertEqual(attack_cost(self.g, self.put(p=self.b), self.a).get("generic"), 2)
        self.g.turn += 1
        self.assertEqual(attack_cost(self.g, bear, self.b).get("generic"), 0)

    def test_multiple_war_tax_activations_stack(self):
        self.g.resolve(self.b, Effect("combat_tax", 2), None)
        self.g.resolve(self.a, Effect("combat_tax", 1), None)
        bear = self.put()
        self.assertEqual(attack_cost(self.g, bear, self.b).get("generic"), 3)
        self.assertEqual(pay_attackers(self.g, self.a, [bear], {bear: self.b}), [])
        self.assertFalse(bear.tapped)

    def test_until_next_turn_taxes_keep_defender_scope(self):
        effects, bad = _parse_effects("Until your next turn, creatures can't attack you or planeswalkers you control "
                                      "unless their controller pays {2} for each of those creatures.")
        self.assertEqual(bad, [])
        item = StackItem(self.b, effects, [None] * len(effects))
        for eff in effects:
            self.g.resolve(self.b, eff, None, item)
        bear, walker = self.put(), self.walker()
        self.assertEqual(attack_cost(self.g, bear, walker).get("generic"), 2)
        self.g.turn += 1
        self.assertEqual(attack_cost(self.g, bear, walker).get("generic"), 2)
        from mtgsim.advanced_templates import begin_turn
        begin_turn(self.g, self.b)
        self.assertEqual(attack_cost(self.g, bear, walker).get("generic"), 0)

    def test_variable_taxes_use_live_quantities(self):
        sphere = self.put("Sphere of Safety", self.b)
        bear, walker = self.put(), self.walker()
        self.assertEqual(attack_cost(self.g, bear, walker).get("generic"), 1)
        self.put("Ghostly Prison", self.b)
        self.assertEqual(attack_cost(self.g, bear, walker).get("generic"), 2)  # Prison doesn't protect PW
        self.g.leave_battlefield(sphere, "exile")
        restraint = self.put("Collective Restraint", self.b)
        self.mana(1, self.b)
        self.mana(1, self.b, land=PLAINS)
        self.assertEqual(attack_cost(self.g, bear, self.b).get("generic"), 4)  # domain 2 + Prison 2
        self.g.leave_battlefield(restraint, "exile")
        self.put("Nils, Discipline Enforcer", self.b)
        bear.counters.update({"+1/+1": 2, "charge": 1})
        self.assertEqual(attack_cost(self.g, bear, walker).get("generic"), 3)


if __name__ == "__main__":
    unittest.main()
