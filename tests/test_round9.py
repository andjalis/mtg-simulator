"""Round 9: graveyard return/draw abilities, token doubling, blocker-power evasion."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, can_block

from tests.test_templates import BEAR, card

RECUR = card("Test Recur", "{B}", "Creature — Zombie", "{1}{B}: Return this card from your graveyard to your hand.", 1, 1)
SNEAK = card("Test Sneak", "{2}", "Creature — Rogue", "~ can't be blocked by creatures with power 3 or greater.", 2, 2)
DOUBLER = card("Test Doubler", "{3}", "Enchantment", "If one or more tokens would be created under your control, "
               "twice that many of those tokens are created instead.")
MAKER = card("Test Maker", "{1}", "Sorcery", "Create a 1/1 white Soldier creature token.")
SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")


class Round9(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"

    def perm(self, c, who=None):
        p = Permanent(c, who or self.a)
        p.sick = False
        p.controller.battlefield.append(p)
        return p

    def test_templates(self):
        for c in (RECUR, SNEAK, DOUBLER):
            self.assertEqual(c.unsupported, [], c.name)

    def test_graveyard_return(self):
        self.perm(SWAMP), self.perm(SWAMP)
        self.a.graveyard.append(RECUR)
        self.game.graveyard_abilities(self.a)
        self.assertIn(RECUR, self.a.hand)

    def test_max_blocker_power(self):
        atk = self.perm(SNEAK)
        small = self.perm(BEAR, self.b)
        big = self.perm(card("Ogre", "{3}", "Creature — Ogre", "", 3, 3), self.b)
        self.assertTrue(can_block(small, atk))
        self.assertFalse(can_block(big, atk))

    def test_token_doubling(self):
        self.perm(DOUBLER)
        self.game.create_token(self.a, MAKER.spell_effects[0] if hasattr(MAKER, "spell_effects") else
                               MAKER.effects[0])
        self.assertEqual(sum(x.card.is_token for x in self.a.battlefield), 2)


if __name__ == "__main__":
    unittest.main()
