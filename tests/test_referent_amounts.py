"""#313: "its controller gains / loses life (mills cards) equal to its <stat>" after a destroy or a counter, and
"you gain life equal to target creature's power"."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from mtgsim.engine.policy import default_choose_target
from tests.test_templates import ISLAND, card


class Amounts(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0))
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [ISLAND] * 10

    def spell(self, text):
        c = card("Test Spell", "{1}", "Instant", text)
        self.assertEqual(c.unsupported, [], text)
        return c

    def cast(self, c, targets):
        effects = list(c.spell_effects)
        self.g.stack.append(StackItem(self.a, effects, targets + [None] * (len(effects) - len(targets)),
                                      card=c, name=c.name))
        self.g.resolve_top()

    def test_destroyed_creatures_controller_loses_power_plus_toughness(self):
        ogre = self.g.enter_battlefield(self.b, card("Ogre", "{2}", "Creature — Ogre", "", 3, 2))
        ogre.counters["+1/+1"] = 1
        self.cast(self.spell("Destroy target creature. Its controller loses life equal to its power plus its "
                             "toughness."), [ogre])
        self.assertNotIn(ogre, self.b.battlefield)
        self.assertEqual((self.a.life, self.b.life), (20, 13))       # last known 4/3

    def test_destroyed_artifacts_controller_gains_its_mana_value(self):
        relic = self.g.enter_battlefield(self.b, card("Relic", "{4}", "Artifact", ""))
        self.cast(self.spell("Destroy target artifact. That artifact's controller gains life equal to its mana "
                             "value."), [relic])
        self.assertEqual(self.b.life, 24)

    def test_destroyed_creatures_controller_mills(self):
        ogre = self.g.enter_battlefield(self.b, card("Ogre", "{2}", "Creature — Ogre", "", 3, 2))
        self.cast(self.spell("Destroy target creature. Its controller mills cards equal to that creature's power."),
                  [ogre])
        self.assertEqual(len(self.b.library), 7)

    def test_gain_life_equal_to_target_creatures_power(self):
        big = self.g.enter_battlefield(self.b, card("Big", "{5}", "Creature — Beast", "", 6, 6))
        self.g.enter_battlefield(self.a, card("Small", "{1}", "Creature — Elf", "", 1, 1))
        c = self.spell("You gain life equal to target creature's power.")
        with self.g.targeting(c):
            self.assertIs(default_choose_target(self.g, self.a, c.spell_effects[0]), big)    # the biggest, anyone's
        self.cast(c, [big])
        self.assertEqual((self.a.life, big.damage), (26, 0))


if __name__ == "__main__":
    unittest.main()
