"""Replicate, dredge, filter lands, slow duals, "+1/+1 counters are put on ~" and blocking several attackers."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, PLAINS, card

SIEGE = card("Test Siege", "{1}{R}", "Sorcery", "Replicate {1}{R}\n~ deals 1 damage to any target.")
BROWNSCALE = card("Test Brownscale", "{1}{G}{G}", "Creature — Lizard", "Dredge 2", 2, 3)
GATE = card("Test Gate", "", "Land", "{T}: Add {C}.\n{W/U}, {T}: Add {W}{W}, {W}{U}, or {U}{U}.")
LANTERN = card("Test Lantern", "", "Land", "{T}: Add {C}.\n{T}: Add {B} or {R}. ~ doesn't untap during your next untap step.")
OAK = card("Test Oak", "{3}{G}", "Creature — Treefolk",
           "Whenever one or more +1/+1 counters are put on ~, you gain 1 life.", 2, 3)
GROWTH = card("Test Growth", "{G}", "Instant", "Put a +1/+1 counter on target creature.")
GIANT = card("Test Giant", "{2}{R}{R}", "Creature — Giant", "~ can block an additional creature each combat.", 3, 7)


class ManaAndBlocks(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c, n=1):
        for _ in range(n):
            perm = self.game.enter_battlefield(who, c)
            perm.sick = False
        self.game.settle()
        return perm

    def option(self, p, kind):
        return next((o for o in self.game.spell_options(p) if self.game._origin(o)[1] == kind), None)

    def test_templates(self):
        for c in (SIEGE, BROWNSCALE, GATE, LANTERN, OAK, GIANT):
            self.assertEqual(c.unsupported, [], c.name)

    def test_replicate_copies_per_payment(self):
        self.put(self.a, MOUNTAIN, 6)
        self.a.hand.append(SIEGE)
        twice = self.option(self.a, "replicate_2")
        self.assertEqual(twice.mana_cost, {"generic": 3, "R": 3})
        self.assertTrue(self.game.cast(self.a, twice, [self.b]))
        self.game.settle()
        self.assertEqual(self.b.life, 17)

    def test_dredge_replaces_a_draw(self):
        self.a.graveyard.append(BROWNSCALE)
        self.game.draw(self.a)
        self.assertIn(BROWNSCALE, self.a.hand)
        self.assertEqual(len(self.a.graveyard), 2)
        self.assertEqual(len(self.a.library), 18)

    def test_filter_land_needs_another_source(self):
        gate = self.put(self.a, GATE)
        self.assertNotIn("W", self.game.mana_sources(self.a)[0].produces_now)
        self.put(self.a, PLAINS)
        self.assertIn("U", next(s for s in self.game.mana_sources(self.a) if s is gate).produces_now)

    def test_slow_dual_skips_untap_only_for_colored_mana(self):
        lantern = self.put(self.a, LANTERN)
        self.assertIsNotNone(self.game.pay(self.a, {"generic": 1}))
        self.assertEqual(lantern.skip_untap, 0)
        lantern.tapped = False
        self.assertIsNotNone(self.game.pay(self.a, {"generic": 0, "B": 1}))
        self.assertEqual(lantern.skip_untap, 1)
        self.game.take_turn(self.a)
        self.assertTrue(lantern.tapped or lantern.skip_untap == 0)

    def test_counters_put_on_it(self):
        oak = self.put(self.a, OAK)
        oak.counters["+1/+1"] = oak.p1 + 2
        self.game.settle()
        self.assertEqual(self.a.life, 21)
        oak.counters["+1/+1"] = 0
        self.game.settle()
        self.assertEqual(self.a.life, 21)              # removing counters doesn't trigger

    def test_blocks_two_attackers_and_splits_damage(self):
        giant = self.put(self.b, GIANT)
        bears = [self.put(self.a, BEAR), self.put(self.a, BEAR)]
        self.a.ai.attack = bears
        self.b.ai.block = {bears[0]: [giant]}
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(self.b.life, 20)               # the AI pass blocked the second bear too
        self.assertEqual(sum(x in self.a.battlefield for x in bears), 1)   # 3 power: one bear dies, not two
        self.assertIn(giant, self.b.battlefield)


if __name__ == "__main__":
    unittest.main()
