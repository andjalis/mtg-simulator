"""Edict wordings: "each player sacrifices a creature" and "target player sacrifices a creature" (real card DB)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, DRAGON3, ISLAND

DB = CardDB(offline=True)


def effects(card):
    return list(card.spell_effects) + [e for t in card.triggers for e in t.effects]


class EdictTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        p = Permanent(c, owner)
        owner.battlefield.append(p)
        return p

    def resolve(self, card):
        for eff in effects(card):
            self.game.resolve(self.a, eff, None)

    def test_parse(self):
        for name in ("Fleshbag Marauder", "Innocent Blood", "Abyssal Gatekeeper", "Chainer's Edict", "Diabolic Edict"):
            with self.subTest(card=name):
                card = DB.get(name)
                self.assertEqual(card.unsupported, [])
                self.assertEqual(len(effects(card)), 1)
                self.assertIn(effects(card)[0].kind, ("edict", "edict_each", "edict_player"))

    def test_each_player_sacrifices_their_worst_creature(self):
        mine, big_mine = self.perm(BEAR, self.a), self.perm(DRAGON3, self.a)
        theirs, big_theirs = self.perm(BEAR, self.b), self.perm(DRAGON3, self.b)
        self.resolve(DB.get("Innocent Blood"))
        self.assertNotIn(mine, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)
        self.assertIn(big_mine, self.a.battlefield)
        self.assertIn(big_theirs, self.b.battlefield)

    def test_target_player_edict_only_hits_the_opponent(self):
        mine, theirs = self.perm(BEAR, self.a), self.perm(BEAR, self.b)
        self.resolve(DB.get("Diabolic Edict"))
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)


if __name__ == "__main__":
    unittest.main()
