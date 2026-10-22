"""Countering activated and triggered abilities: Stifle, Disallow, and the AI answering a valuable trigger."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Effect, Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

STIFLE = card("Test Stifle", "{U}", "Instant", "Counter target activated or triggered ability.")
DISALLOW = card("Test Disallow", "{1}{U}{U}", "Instant", "Counter target spell, activated ability, or triggered ability.")
SHOCK = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to any target.")
TITAN = card("Test Titan", "{4}{R}{R}", "Creature — Giant", "When ~ enters, it deals 3 damage to any target.", 6, 6)


class CounterAbilities(unittest.TestCase):
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
        return perm

    def test_templates(self):
        for c in (STIFLE, DISALLOW):
            self.assertEqual((c.unsupported, c.approximations), ([], []), c.name)

    def test_filters(self):
        titan = self.put(self.b, TITAN)
        trigger = StackItem(self.b, [Effect("damage", 3, target="any")], [self.a], source=titan, kind="trigger")
        spell = StackItem(self.b, list(SHOCK.spell_effects), [self.a], card=SHOCK, kind="spell")
        self.game.stack.extend([spell, trigger])
        stifle, disallow = STIFLE.spell_effects[0], DISALLOW.spell_effects[0]
        self.assertTrue(self.game.can_counter(stifle, trigger, self.a))
        self.assertFalse(self.game.can_counter(stifle, spell, self.a))
        self.assertTrue(self.game.can_counter(disallow, trigger, self.a))
        self.assertTrue(self.game.can_counter(disallow, spell, self.a))
        self.game.counter(self.a, stifle, trigger)
        self.assertNotIn(trigger, self.game.stack)
        self.assertIn(spell, self.game.stack)

    def test_ai_stifles_a_valuable_trigger(self):
        self.a.ai = HeuristicAI()
        self.game.active_idx = 1
        self.put(self.a, ISLAND)
        self.a.hand[:] = [STIFLE]
        self.game.enter_battlefield(self.b, TITAN)
        self.game.run_priority()
        self.assertIn(STIFLE, self.a.graveyard)
        self.assertEqual(self.a.life, 20)


if __name__ == "__main__":
    unittest.main()
