"""#313: "becomes an artifact creature with power and toughness each equal to its mana value until end of turn"."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from mtgsim.engine.policy import default_choose_target
from tests.test_templates import ISLAND, card

TEXT = ("Target noncreature artifact becomes an artifact creature with power and toughness each equal to its mana "
        "value until end of turn.")


class AnimateManaValue(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0))
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [ISLAND] * 10
        self.spell = card("Test Touch", "{U}", "Instant", TEXT)
        self.assertEqual(self.spell.unsupported, [])

    def cast(self, target):
        effects = list(self.spell.spell_effects)
        self.g.stack.append(StackItem(self.a, effects, [target], card=self.spell, name=self.spell.name))
        self.g.resolve_top()

    def test_size_is_its_mana_value_until_end_of_turn(self):
        relic = self.g.enter_battlefield(self.a, card("Relic", "{4}", "Artifact", ""))
        self.cast(relic)
        self.assertTrue(relic.is_creature)
        self.assertEqual((relic.power, relic.toughness), (4, 4))
        self.assertEqual(relic.animated.text, "")       # an end-of-turn animation (cleared in the cleanup step)

    def test_mana_value_zero_dies(self):
        bauble = self.g.enter_battlefield(self.a, card("Bauble", "{0}", "Artifact", ""))
        self.cast(bauble)
        self.assertNotIn(bauble, self.a.battlefield)      # a 0/0 creature (state-based action)

    def test_ai_aims_it_at_its_own_artifact(self):
        mine = self.g.enter_battlefield(self.a, card("Relic", "{4}", "Artifact", ""))
        self.g.enter_battlefield(self.b, card("Their Relic", "{5}", "Artifact", ""))
        with self.g.targeting(self.spell):
            self.assertIs(default_choose_target(self.g, self.a, self.spell.spell_effects[0]), mine)


if __name__ == "__main__":
    unittest.main()
