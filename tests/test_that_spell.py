"""'That spell's' references (mana value, colors, controller) in cast triggers and counterspell riders."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

CYCLOPS = card("Test Cyclops", "{2}{R}", "Creature — Cyclops",
               "Whenever you cast an instant or sorcery spell, this creature gets +X/+0 until end of turn, where X is that spell's mana value.", 1, 1)
THRULLS = card("Test Breeder", "{2}{B}", "Creature — Thrull",
               "Whenever you cast a creature spell, create X 1/1 black Thrull creature tokens, where X is that spell's mana value.", 1, 1)
KAERVEK = card("Test Kaervek", "{2}{R}", "Creature — Human",
               "Whenever an opponent casts a spell, ~ deals damage equal to that spell's mana value to any target.", 1, 1)
ARSONIST = card("Test Arsonist", "{2}{R}", "Creature — Human",
                "Whenever you cast a spell, ~ gets +1/+1 until end of turn for each of that spell's colors.", 1, 1)
DENIED = card("Test Denied", "{1}{U}", "Instant",
              "Counter target spell. Create X 1/1 colorless Thopter artifact creature tokens with flying, where X is that spell's mana value.")
WHELK = card("Test Whelk", "{1}{U}", "Instant",
             "Counter target spell. Target creature you control gets +X/+X until end of turn, where X is that spell's mana value.")
VORTEX = card("Test Vortex", "{2}", "Artifact",
              "Whenever an opponent casts a noncreature spell, that spell's controller loses life equal to that spell's mana value.")
BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")
BIG = card("Test Big", "{4}{R}", "Creature — Giant", "", 5, 5)
SHOCK = card("Test Shock", "{R}{U}", "Instant", "Test Shock deals 1 damage to any target.")


class ThatSpellTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        for _ in range(6):
            self.perm(MOUNTAIN, self.a)
            self.perm(ISLAND, self.a)
            self.perm(MOUNTAIN, self.b)

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def test_templates_match(self):
        for c in (CYCLOPS, THRULLS, KAERVEK, ARSONIST, DENIED, WHELK):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])

    def test_pump_by_the_spells_mana_value_not_the_hosts(self):
        cy = self.perm(CYCLOPS, self.a)
        self.a.hand = [BOLT]
        self.game.cast(self.a, BOLT, [self.b])
        self.game.settle()
        self.assertEqual(cy.power, 1 + BOLT.cmc)

    def test_tokens_equal_to_spell_mana_value(self):
        self.perm(THRULLS, self.a)
        self.a.hand = [BIG]
        self.game.cast(self.a, BIG)
        self.game.settle()
        self.assertEqual(len([x for x in self.a.battlefield if x.card.is_token]), 5)

    def test_the_spells_controller_loses_life(self):
        c = card("Test Rule", "{2}", "Artifact", "Whenever an opponent casts a spell, that spell's controller loses 3 life.")
        self.assertEqual(c.unsupported, [])
        self.perm(c, self.a)
        self.b.hand = [BIG]
        self.game.cast(self.b, BIG)
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (20, 17))

    def test_the_spells_controller_loses_its_mana_value(self):
        self.assertEqual(VORTEX.unsupported, [])
        self.perm(VORTEX, self.a)
        self.b.hand = [BOLT]
        self.game.cast(self.b, BOLT, [self.a])
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (20 - 3, 20 - BOLT.cmc))

    def test_colors_of_the_spell(self):
        ar = self.perm(ARSONIST, self.a)
        self.a.hand = [SHOCK]
        self.game.cast(self.a, SHOCK, [self.b])
        self.game.settle()
        self.assertEqual(ar.power, 1 + 2)

    def _counter(self, counter_card, spell_card, *extra):
        spell = StackItem(card=spell_card, controller=self.b, effects=[], targets=[])
        self.game.stack.append(spell)
        self.a.hand = [counter_card]
        self.assertTrue(self.game.cast(self.a, counter_card, [spell, *extra]))
        self.game.settle()
        return spell

    def test_counterspell_rider_reads_the_countered_spell(self):
        spell = self._counter(DENIED, BIG)
        self.assertNotIn(spell, self.game.stack)
        thopters = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual(len(thopters), 5)

    def test_rider_pump_reads_the_countered_spell(self):
        mine = self.perm(BEAR, self.a)
        self._counter(WHELK, BIG, mine)
        self.assertEqual(mine.power, 2 + 5)

    def test_counter_then_damage_to_that_spells_controller(self):
        zap = card("Test Zap", "{1}{U}", "Instant", "Counter target spell. ~ deals 2 damage to that spell's controller.")
        self.assertEqual(zap.unsupported, [])
        self._counter(zap, BIG)
        self.assertEqual((self.a.life, self.b.life), (20, 18))

    def test_becoming_the_target_of_a_spell_hurts_its_controller(self):
        giant = card("Test Giant", "{2}{R}", "Creature — Giant",
                     "Whenever this creature becomes the target of a spell, ~ deals 2 damage to that spell's controller.", 4, 3)
        self.assertEqual(giant.unsupported, [])
        mine = self.perm(giant, self.a)
        self.b.hand = [BOLT]
        self.game.cast(self.b, BOLT, [mine])
        self.game.settle()
        self.assertEqual(self.b.life, 18)

    def test_opponents_spell_deals_its_mana_value(self):
        self.perm(KAERVEK, self.a)
        self.b.hand = [BIG]
        self.game.cast(self.b, BIG)
        self.game.settle()
        self.assertEqual(40 - self.a.life - self.b.life + len(self.b.battlefield) * 0, 5)


if __name__ == "__main__":
    unittest.main()
