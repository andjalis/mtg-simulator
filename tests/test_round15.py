"""Round 15: forced blocks, can't-block effects, relative blocker power, waterbend abilities, firebending lists."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, can_block

from tests.test_templates import BEAR, ISLAND, card

LURE = card("Test Lure", "{3}", "Creature — Beast", "~ must be blocked if able.", 3, 3)
BULLY = card("Test Bully", "{3}", "Creature — Giant", "Creatures with power less than ~'s power can't block it.", 4, 4)
SMALL = card("Test Small", "{1}", "Creature — Human", "", 2, 2)
BIG = card("Test Big", "{4}", "Creature — Giant", "", 5, 5)
ROAR = card("Test Roar", "{1}{R}", "Sorcery", "Up to two target creatures can't block this turn.")
DARE = card("Test Dare", "{R}", "Sorcery", "Target creature blocks this turn if able.")
WATER = card("Test Tide", "{2}{U}", "Enchantment", "Waterbend {4}: Draw a card, then discard a card.")
FIRE = card("Test Flame", "{2}{R}", "Creature — Human Monk", "Flying, firebending 2", 2, 2)
MOUNTAIN = card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)")


class Round15(unittest.TestCase):
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
        for c in (LURE, BULLY, ROAR, DARE, WATER, FIRE):
            self.assertEqual(c.unsupported, [], c.name)

    def test_lure_forces_a_block(self):
        lure = self.perm(LURE)
        blocker = self.perm(SMALL, self.b)
        self.assertEqual(self.game.force_blocks(self.b, [lure], {}), {lure: [blocker]})

    def test_relative_power(self):
        bully = self.perm(BULLY)
        self.assertFalse(can_block(self.perm(SMALL, self.b), bully))
        self.assertTrue(can_block(self.perm(BIG, self.b), bully))

    def test_cant_block_up_to_two(self):
        x, y, z = (self.perm(card(f"Test Guard {i}", "{1}", "Creature — Human", "", 2, 2), self.b) for i in range(3))
        self.a.hand.append(ROAR)
        for _ in range(2):
            self.perm(MOUNTAIN)
        self.assertTrue(self.game.cast(self.a, ROAR, []))
        self.game.settle()
        self.assertEqual(sum(p.has("cant_block_now") for p in (x, y, z)), 2)

    def test_dare_forces_the_creature_to_block(self):
        att = self.perm(BIG)
        blk = self.perm(SMALL, self.b)
        self.perm(MOUNTAIN)
        self.a.hand.append(DARE)
        self.assertTrue(self.game.cast(self.a, DARE, []))
        self.game.settle()
        self.assertTrue(blk.has("must_block_now"))
        self.assertEqual(self.game.force_blocks(self.b, [att], {}), {att: [blk]})

    def test_waterbend_is_an_activated_ability(self):
        self.assertEqual([a.cost for a in WATER.activated], [{"generic": 4}])

    def test_firebending_with_other_keywords(self):
        self.assertIn("flying", FIRE.keywords)
        self.assertTrue(any(t.event == "attacks" and t.effects[0].kind == "firebend" for t in FIRE.triggers))


if __name__ == "__main__":
    unittest.main()
