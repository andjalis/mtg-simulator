"""Static "You may cast sorcery spells as though they had flash." (Gandalf, Hypersonic Dragon, Najal)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player
from tests.test_templates import BEAR, card

DRAGON = card("Test Dragon", "{4}{R}", "Creature — Dragon",
              "Flying\nYou may cast sorcery spells as though they had flash.", power="3", toughness="3")
RITUAL = card("Test Sorcery", "{R}", "Sorcery", "Test Sorcery deals 1 damage to any target.")


class SorceryFlash(unittest.TestCase):
    def test_parses_as_a_rule(self):
        self.assertEqual((DRAGON.unsupported, DRAGON.advanced_rules.get("sorcery_flash")), ([], True))

    def _game(self):
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        game.turn, game.step = 1, "combat"
        game.active_idx = 1                                # not my turn: a sorcery is normally uncastable
        a.hand.append(RITUAL)
        for _ in range(2):
            a.battlefield.append(Permanent(card("Test Mountain", "", "Basic Land — Mountain", ""), a))
        return game, a

    def test_sorcery_is_castable_at_instant_speed_only_with_the_permanent(self):
        game, a = self._game()
        self.assertFalse(game.can_cast_now(a, RITUAL))
        a.battlefield.append(Permanent(DRAGON, a))
        self.assertTrue(game.can_cast_now(a, RITUAL))

    def test_all_spells_flash_covers_creatures_too(self):
        game, a = self._game()
        orrery = card("Test Orrery", "{4}", "Artifact", "You may cast spells as though they had flash.")
        self.assertEqual((orrery.unsupported, orrery.advanced_rules.get("spells_flash")), ([], True))
        golem = card("Test Golem", "{1}", "Artifact Creature — Golem", "", power="1", toughness="1")
        a.hand.append(golem)
        self.assertFalse(game.can_cast_now(a, golem))
        a.battlefield.append(Permanent(orrery, a))
        self.assertTrue(game.can_cast_now(a, golem))
        self.assertTrue(game.can_cast_now(a, RITUAL))


if __name__ == "__main__":
    unittest.main()
