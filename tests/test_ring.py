"""The Ring tempts you: Ring levels, choosing the Ring-bearer, and the Ring's four abilities."""
import random
import unittest

from mtgsim import ring
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

TEMPT = card("Test Tempt", "{B}", "Sorcery", "The Ring tempts you.")
WATCHER = card("Test Watcher", "{1}{B}", "Creature — Human", "Whenever the Ring tempts you, you gain 1 life.", 1, 1)
OGRE = card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)
WALL = card("Test Wall", "{1}{W}", "Creature — Wall", "", 4, 4)


class Ring(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = False
        self.game.settle()
        return perm

    def tempt(self, n=1):
        for _ in range(n):
            self.game.resolve(self.a, TEMPT.spell_effects[0], None)
            self.game.settle()

    def test_templates(self):
        for c in (TEMPT, WATCHER):
            self.assertEqual(c.unsupported, [], c.name)

    def test_best_creature_becomes_ring_bearer_and_skulks(self):
        self.put(self.a, BEAR)
        ogre = self.put(self.a, OGRE)
        self.put(self.a, WATCHER)
        self.tempt()
        self.assertIs(ring.bearer(self.a), ogre)
        self.assertEqual((ring.level(self.a), self.a.life), (1, 21))
        self.assertTrue(ogre.has("skulk"))
        self.a.ai.attack = [ogre]
        self.b.ai.block = {ogre: [self.put(self.b, WALL)]}
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(self.b.life, 17)                   # the bigger Wall couldn't block it

    def test_loot_sacrifice_and_drain(self):
        ogre = self.put(self.a, OGRE)
        self.tempt(4)
        self.assertEqual(ring.level(self.a), 4)
        bear = self.put(self.b, BEAR)
        self.a.hand[:] = []
        self.a.ai.attack, self.b.ai.block = [ogre], {ogre: [bear]}
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(len(self.a.hand), 0)               # drew, then discarded
        self.assertEqual(len(self.a.graveyard), 1)          # the looted card
        ogre.tapped = False
        self.a.ai.attack, self.b.ai.block = [ogre], {}
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(self.b.life, 20 - 3 - 3)


if __name__ == "__main__":
    unittest.main()
