"""Split second, skulk, Lure, "can't be blocked by more than one creature", afflict, "attacks and isn't blocked",
"creatures without flying can't block", attacker pumps, "during your turn", horizon lands and land sacrifice."""
import random
import unittest

from mtgsim.engine import Game, Player, StackItem, can_block
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, MOUNTAIN, card

SUDDEN = card("Test Sudden Shock", "{1}{R}", "Instant", "Split second\n~ deals 2 damage to any target.")
SNAKESKIN = card("Test Veil", "{G}", "Instant", "Target creature you control gets +1/+1 until end of turn.")
RIDER = card("Test Skulker", "{B}", "Creature — Spirit", "Skulk", 1, 1)
GIANT = card("Test Giant", "{4}", "Creature — Giant", "", 3, 3)
BARD = card("Test Lure", "{1}{G}", "Creature — Elf Shaman", "All creatures able to block ~ do so.", 2, 2)
TIGER = card("Test Tiger", "{3}{G}", "Creature — Cat", "~ can't be blocked by more than one creature.", 3, 3)
ETERNAL = card("Test Eternal", "{2}{U}", "Creature — Zombie Cleric",
               "Afflict 2\nWhenever ~ attacks and isn't blocked, draw a card.", 1, 3)
STOMP = card("Test Stomp", "{1}{R}", "Sorcery", "Creatures without flying can't block this turn.")
INSPIRATION = card("Test Inspiration", "{2}{W}", "Instant", "Attacking creatures get +2/+0 until end of turn.")
REAVER = card("Test Reaver", "{1}{R}", "Creature — Minotaur Warrior", "During your turn, ~ gets +2/+0.", 2, 3)
GROVE = card("Test Grove", "", "Land", "{T}, Pay 1 life: Add {G} or {U}.")
HARROW = card("Test Harrow", "{2}{G}", "Instant", "As an additional cost to cast this spell, sacrifice a land.\n"
                                                  "Draw a card.")
BIRD = card("Test Bird", "{U}", "Creature — Bird", "Flying", 1, 1)


class BlockingRules(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c, n=1):
        for _ in range(n):
            perm = self.game.enter_battlefield(who, c)
            perm.sick = False
        self.game.settle()
        return perm

    def fight(self, attackers, blocks=None):
        self.a.ai.attack = attackers
        self.b.ai.block = blocks or {}
        self.game.combat(self.a, self.b)
        self.game.settle()

    def test_templates(self):
        for c in (SUDDEN, RIDER, BARD, TIGER, ETERNAL, STOMP, INSPIRATION, REAVER, HARROW):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(GROVE.produces, {"G", "U"})

    def test_split_second_stops_responses(self):
        bear = self.put(self.b, BEAR)
        self.put(self.b, FOREST)
        self.b.hand.append(SNAKESKIN)
        self.game.stack.append(StackItem(self.a, list(SUDDEN.spell_effects), [bear], card=SUDDEN))
        self.assertFalse(self.game.give_priority(self.b))
        self.game.settle()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertIn(SNAKESKIN, self.b.hand)

    def test_skulk(self):
        rider = self.put(self.a, RIDER)
        self.assertFalse(can_block(self.put(self.b, GIANT), rider))
        self.assertTrue(can_block(self.put(self.b, RIDER), rider))

    def test_lure_and_one_blocker_max(self):
        bard = self.put(self.a, BARD)
        bears = [self.put(self.b, BEAR) for _ in range(2)]
        self.fight([bard])
        self.assertEqual(sorted(map(id, self.game.blocks.get(bard, []))), sorted(map(id, bears)))
        tiger = self.put(self.a, TIGER)
        self.b.ai.block = {}
        self.fight([tiger], {tiger: [self.put(self.b, BEAR), self.put(self.b, BEAR)]})
        self.assertEqual(len(self.game.blocks[tiger]), 1)

    def test_afflict_and_unblocked_draw(self):
        eternal = self.put(self.a, ETERNAL)
        hand = len(self.a.hand)
        self.fight([eternal])
        self.assertEqual(len(self.a.hand), hand + 1)
        eternal.tapped = False
        self.fight([eternal], {eternal: [self.put(self.b, BEAR)]})
        self.assertEqual(self.b.life, 20 - 1 - 2)

    def test_stomp_and_attacker_pump(self):
        bear, bird = self.put(self.b, BEAR), self.put(self.b, BIRD)
        self.put(self.a, MOUNTAIN, 2)
        self.a.hand.append(STOMP)
        self.assertTrue(self.game.cast(self.a, STOMP))
        self.game.settle()
        attacker = self.put(self.a, BEAR)
        self.assertFalse(can_block(bear, attacker))
        self.assertTrue(can_block(bird, attacker))
        self.game.attackers = [attacker]
        self.game.resolve(self.a, INSPIRATION.spell_effects[0], None)
        self.assertEqual(attacker.power, 4)

    def test_during_your_turn(self):
        reaver = self.put(self.a, REAVER)
        self.a.my_turn = True
        self.assertEqual(reaver.power, 4)
        self.a.my_turn = False
        self.assertEqual(reaver.power, 2)

    def test_land_sacrifice_cost(self):
        self.put(self.a, FOREST, 3)
        self.a.hand.append(HARROW)
        self.assertTrue(self.game.cast(self.a, HARROW))
        self.game.settle()
        self.assertEqual(sum(x.card.is_land for x in self.a.battlefield), 2)


if __name__ == "__main__":
    unittest.main()
