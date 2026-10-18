"""Round 17: Class levels, auras that remove abilities, ability-word prefixes."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import ISLAND, card

TALENT = card("Test Talent", "{1}{U}", "Enchantment — Class",
              "When ~ enters, you gain 1 life.\n{1}{U}: Level 2\nWhen this Class becomes level 2, you gain 3 life.\n"
              "{2}{U}: Level 3\nWhenever you cast a spell, you gain 5 life.")
CAGE = card("Test Cage", "{1}{W}", "Enchantment — Aura",
            "Enchant creature\nEnchanted creature gets -2/-0 and loses all abilities.")
FLIER = card("Test Flier", "{2}", "Creature — Bird", "Flying", 2, 2)
ALLY = card("Test Ally", "{2}", "Creature — Elf", "Alliance — Whenever another creature you control enters, ~ gets +1/+1 until end of turn.", 1, 1)
PLAINS = card("Plains", types="Basic Land — Plains", text="({T}: Add {W}.)")
UNDERSEA = card("Island", types="Basic Land — Island", text="({T}: Add {U}.)")


class Round17(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 10, HeuristicAI())
        self.b = Player("b", [ISLAND] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"

    def perm(self, c, who=None):
        p = Permanent(c, who or self.a)
        p.sick = False
        p.controller.battlefield.append(p)
        return p

    def test_templates(self):
        for c in (TALENT, CAGE, ALLY):
            self.assertEqual(c.unsupported, [], c.name)

    def test_class_levels_gate_triggers(self):
        self.assertEqual([t.min_level for t in TALENT.triggers if t.event == "cast_spell"], [3])
        talent = self.perm(TALENT)
        for _ in range(4):
            self.perm(UNDERSEA)
        self.assertFalse(self.game.can_activate(self.a, talent, 1))      # needs level 2 first
        life = self.a.life
        self.assertTrue(self.game.activate_ability(self.a, talent, 0))
        self.game.settle()
        self.assertEqual(talent.counters["level"], 2)
        self.assertEqual(self.a.life, life + 3)
        self.assertFalse(self.game.can_activate(self.a, talent, 0))      # already level 2
        for x in self.a.battlefield:
            x.tapped = False
        self.assertTrue(self.game.activate_ability(self.a, talent, 1))
        self.game.settle()
        self.assertEqual(talent.counters["level"], 3)
        self.assertTrue(any(t.event == "cast_spell" for t in talent.triggers))

    def test_aura_removes_keywords(self):
        bird = self.perm(FLIER, self.b)
        self.assertTrue(bird.has("flying"))
        cage = self.perm(CAGE)
        cage.attached_to = bird
        bird.auras.append(cage)
        self.assertFalse(bird.has("flying"))

    def test_ability_word_prefix(self):
        self.assertEqual([t.event for t in ALLY.triggers], ["permanent_enters"])


if __name__ == "__main__":
    unittest.main()
