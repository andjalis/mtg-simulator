"""Round 10: Bargain and Gift riders, "where X is ..." amounts."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

BARGAIN = card("Test Bargain", "{1}{R}", "Instant", "Bargain\nTest Bargain deals 2 damage to target creature. "
               "If ~ was bargained, it deals 5 damage instead.")
GIFT = card("Test Gift", "{1}{W}", "Instant", "Gift a card\nTarget creature gets +1/+1 until end of turn. "
            "If the gift was promised, that creature also gains lifelink until end of turn.")
KRENKO = card("Test Krenko", "{2}{R}", "Creature — Goblin", "{T}: Create X 1/1 red Goblin creature tokens, "
              "where X is the number of Goblins you control.", 2, 2)
HOOF = card("Test Hoof", "{4}{G}", "Sorcery", "Creatures you control gain trample and get +X/+X until end of turn, "
            "where X is the number of creatures you control.")
OGRE = card("Ogre", "{3}", "Creature — Ogre", "", 5, 5)


class Round10(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, who=None):
        p = Permanent(c, who or self.a)
        p.sick = False
        p.controller.battlefield.append(p)
        return p

    def test_templates(self):
        for c in (BARGAIN, GIFT, KRENKO, HOOF):
            self.assertEqual(c.unsupported, [], c.name)

    def test_bargained_damage_replaces_base(self):
        for _ in range(2):
            self.perm(MOUNTAIN)
        self.perm(card("Token", "", "Artifact — Treasure", ""))      # something spare to sacrifice
        self.a.battlefield[-1].card = card("Clue", "", "Artifact — Clue", "")
        big = self.perm(OGRE, self.b)
        self.a.hand.append(BARGAIN)
        self.assertTrue(self.game.cast(self.a, BARGAIN, [big]))
        self.game.settle()
        self.assertNotIn(big, self.b.battlefield)               # 5 damage kills the 5/5

    def test_unbargained_damage_is_base(self):
        for _ in range(2):
            self.perm(MOUNTAIN)
        big = self.perm(OGRE, self.b)
        self.a.hand.append(BARGAIN)
        self.assertTrue(self.game.cast(self.a, BARGAIN, [big]))
        self.game.settle()
        self.assertIn(big, self.b.battlefield)

    def test_gift_card_goes_to_the_opponent(self):
        mine = self.perm(BEAR)
        for _ in range(2):
            self.perm(card("Plains", types="Basic Land — Plains", text="({T}: Add {W}.)"))
        self.a.hand.append(GIFT)
        before = len(self.b.hand)
        self.assertTrue(self.game.cast(self.a, GIFT, [mine]))
        self.game.settle()
        self.assertEqual(len(self.b.hand), before + 1)
        self.assertTrue(mine.has("lifelink"))

    def test_where_x_count_scales_tokens(self):
        k = self.perm(KRENKO)
        self.perm(card("Goblin", "", "Creature — Goblin", "", 1, 1))
        self.assertTrue(self.game.activate(self.a, k, "ability:0"))
        self.game.settle()
        self.assertGreaterEqual(sum("Goblin" in x.card.subtypes for x in self.a.battlefield), 4)

    def test_where_x_pump_uses_creature_count(self):
        for _ in range(3):
            self.perm(BEAR)
        for _ in range(5):
            self.perm(card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)"))
        self.a.hand.append(HOOF)
        self.assertTrue(self.game.cast(self.a, HOOF, []))
        self.game.settle()
        self.assertEqual(self.a.battlefield[0].power, 2 + 3)


if __name__ == "__main__":
    unittest.main()
