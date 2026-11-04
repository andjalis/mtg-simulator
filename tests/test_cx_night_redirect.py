"""Change the target of target spell with a single target."""
import random
import unittest

from mtgsim import cards
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem
from mtgsim.engine.kinds.cx_night_redirect import redirect_spell

from tests.test_templates import BEAR, card

BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to target creature.")
SWERVE = card("Test Swerve", "{U}{U}", "Instant", "Change the target of target spell with a single target.")


class Redirect(unittest.TestCase):
    def test_parses(self):
        effects, unmatched = cards._parse_effects("Change the target of target spell with a single target.")
        self.assertEqual((unmatched, effects[0].kind), ([], "counter"))
        self.assertEqual(SWERVE.unsupported, [])

    def _game(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        game.turn, game.step = 1, "main1"
        return game, a, b

    def test_single_target_spell_is_redirected(self):
        game, a, b = self._game()
        mine, theirs = Permanent(BEAR, a), Permanent(BEAR, b)
        a.battlefield.append(mine)
        b.battlefield.append(theirs)
        eff = BOLT.spell_effects[0]
        spell = StackItem(card=BOLT, controller=b, effects=[eff], targets=[theirs])
        game.stack.append(spell)
        self.assertTrue(redirect_spell(game, a, spell))
        self.assertIsNot(spell.targets[0], theirs)

    def test_not_on_stack_is_left_alone(self):
        game, a, b = self._game()
        eff = BOLT.spell_effects[0]
        spell = StackItem(card=BOLT, controller=b, effects=[eff], targets=[None])
        self.assertFalse(redirect_spell(game, a, spell))


if __name__ == "__main__":
    unittest.main()
