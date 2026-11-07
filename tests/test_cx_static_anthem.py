"""Anthem group words read as colours, card types, states or (singular) subtypes (mtgsim/cx_static_anthem.py)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, card

KNIGHT = card("Test Knight", "{W}", "Creature — Human Knight", "", 2, 2)
ELF = card("Test Elf", "{G}", "Creature — Elf Warrior", "", 1, 1)
GOLEM = card("Test Golem", "{3}", "Artifact Creature — Golem", "", 2, 2)
HERO = card("Test Hero", "{W}{U}", "Legendary Creature — Human", "", 2, 2)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class AnthemGroups(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [BEAR] * 20, HeuristicAI())
        self.b = Player("b", [BEAR] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=False)
        for p in (self.a, self.b):
            p.library = list(p.deck)
        self.game.turn, self.game.step = 3, "main1"

    def put(self, c, who=None):
        if isinstance(c, str):
            c = self.db.get(c)
            self.assertEqual(c.unsupported, [], c.name)
        return self.game.enter_battlefield(who or self.a, c)

    def pt(self, perm):
        return perm.power, perm.toughness

    def test_colour_anthem_only_that_colour(self):
        self.put("Sylvan Anthem")                 # Green creatures you control get +1/+1
        bear, knight = self.put(BEAR), self.put(KNIGHT)
        their_bear = self.put(BEAR, self.b)
        self.assertEqual(self.pt(bear), (3, 3))
        self.assertEqual(self.pt(knight), (2, 2))
        self.assertEqual(self.pt(their_bear), (2, 2))

    def test_white_anthem(self):
        self.put("Honor of the Pure")
        self.assertEqual(self.pt(self.put(KNIGHT)), (3, 3))
        self.assertEqual(self.pt(self.put(BEAR)), (2, 2))

    def test_plural_subtype(self):
        self.put("Imperious Perfect")             # Other Elves you control get +1/+1
        self.assertEqual(self.pt(self.put(ELF)), (2, 2))
        self.assertEqual(self.pt(self.put(BEAR)), (2, 2))

    def test_card_type(self):
        self.put("Tempered Steel")                # Artifact creatures you control get +2/+2
        self.assertEqual(self.pt(self.put(GOLEM)), (4, 4))
        self.assertEqual(self.pt(self.put(BEAR)), (2, 2))

    def test_states(self):
        self.put("Castle")                        # Untapped creatures you control get +0/+2
        bear = self.put(BEAR)
        self.assertEqual(self.pt(bear), (2, 4))
        bear.tapped = True
        self.assertEqual(self.pt(bear), (2, 2))
        self.put("Day of Destiny")                # Legendary creatures you control get +2/+2
        self.assertEqual(self.pt(self.put(HERO)), (4, 6))

    def test_attacking_only_during_combat(self):
        self.put("War Horn")                      # Attacking creatures you control get +1/+0
        bear = self.put(BEAR)
        self.game.attackers = [bear]
        self.game.step = "declare_blockers"
        self.assertEqual(self.pt(bear), (3, 2))
        self.game.step = "main2"                  # the list outlives combat; nothing is attacking now
        self.assertEqual(self.pt(bear), (2, 2))

    def test_unknown_words_stay_unparsed(self):
        from mtgsim.cx_static_anthem import tag
        self.assertIsNone(tag("Purple"))                  # no such colour, type, state or subtype
        self.assertEqual(self.db.get("Secret Plans").anthem_sub, (("Face-down", 0, 1, False),))   # #248


if __name__ == "__main__":
    unittest.main()
