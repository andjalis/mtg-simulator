"""You control enchanted permanent; goaded Auras."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.batch1_templates import player_targetable
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, card

CONFISCATE = card("Test Confiscate", "{4}{U}{U}", "Enchantment — Aura", "Enchant permanent\nYou control enchanted permanent.")
IMPETUS = card("Test Impetus", "{1}{R}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1 and is goaded.")
GHOUL = card("Test Ghoul", "{1}{B}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1, has deathtouch, and is goaded.")
MASK = card("Test Mask", "{3}", "Artifact", "You have shroud. (You can't be the target of spells or abilities.)")
PLAIN = card("Test Plain", "{1}{R}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1 and attacks each combat if able.")


class AuraLines(unittest.TestCase):
    def test_control_enchanted_permanent(self):
        self.assertEqual(CONFISCATE.unsupported, [])
        self.assertTrue(CONFISCATE.advanced_rules.get("aura_control"))

    def test_goaded_reads_as_attacks_each_combat(self):
        self.assertEqual(IMPETUS.unsupported, [])
        self.assertEqual(IMPETUS.equip_keywords, PLAIN.equip_keywords)
        self.assertEqual(GHOUL.unsupported, [])
        self.assertIn("must_attack_now", repr(GHOUL.advanced_rules))
        self.assertIn("deathtouch", repr(GHOUL.advanced_rules))


class Shroud(unittest.TestCase):
    def test_shroud_blocks_every_player_target_even_your_own(self):
        self.assertEqual(MASK.unsupported, [])
        a = Player("a", [BEAR] * 10, HeuristicAI())
        b = Player("b", [BEAR] * 10, HeuristicAI())
        game = Game(a, b, random.Random(0), log=False)
        self.assertTrue(player_targetable(game, a, b))
        a.battlefield.append(Permanent(MASK, a))
        self.assertFalse(player_targetable(game, a, b))
        self.assertFalse(player_targetable(game, a, a))
        self.assertTrue(player_targetable(game, b, a))


if __name__ == "__main__":
    unittest.main()
