"""Ripple: templates and engine behavior (chonk/vert batch 2)."""
import random
import unittest

from tests.test_templates import card
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, MOUNTAIN

SURGING_FLAME = card("Surging Flame", "{1}{R}", "Instant", "Ripple 4\n~ deals 2 damage to any target.")
SURGING_SENTINELS = card("Surging Sentinels", "{2}{W}", "Creature — Human Soldier",
                         "First strike\nRipple 4")
THRUMMING = card("Thrumming Stone", "{5}", "Legendary Artifact",
                 "Spells you cast have ripple 4.")
BOLT = card("Test Bolt", "{1}{R}", "Instant", "~ deals 3 damage to any target.")


class ParseRipple(unittest.TestCase):
    def test_ripple_keyword_is_a_cast_trigger(self):
        for c in (SURGING_FLAME, SURGING_SENTINELS):
            self.assertEqual(c.unsupported, [])
            self.assertEqual([(t.event, t.effects[0].kind, t.effects[0].amount)
                              for t in c.cast_self_triggers], [("cast_self", "ripple", 4)])

    def test_thrumming_stone_grants_ripple_on_cast(self):
        self.assertEqual(THRUMMING.unsupported, [])
        self.assertEqual([(t.event, t.effects[0].kind) for t in THRUMMING.triggers],
                         [("cast_spell", "ripple")])


class RippleEngine(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(3))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None
        for _ in range(6):
            self.g.enter_battlefield(self.a, MOUNTAIN)
        self.g.settle()

    def cast(self, definition, library):
        self.a.hand = [definition]
        self.a.library = [ISLAND] * 20 + list(library)   # the list end is the top
        ok = self.g.cast(self.a, definition)
        self.g.settle()
        return ok

    def test_ripple_casts_revealed_copies_for_free(self):
        # four copies on top: all are cast for free (b takes 2 damage each)
        self.assertTrue(self.cast(SURGING_FLAME, [SURGING_FLAME] * 4))
        self.assertEqual(self.b.life, 20 - 2 * 5)         # the original plus four free copies

    def test_ripple_bottoms_the_rest(self):
        # one match on top of four Mountains: the Mountains are revealed and bottomed
        self.assertTrue(self.cast(SURGING_FLAME, [MOUNTAIN] * 3 + [SURGING_FLAME]))
        # the Mountains (and the Islands the free copy's own ripple revealed) went to the bottom
        self.assertLessEqual(max(i for i, c in enumerate(self.a.library) if c.name == "Mountain"), 10)
        self.assertEqual(sum(1 for c in self.a.library if c.name == "Mountain"), 3)
        self.assertEqual(self.b.life, 20 - 2 * 2)          # original + one free copy
        self.assertEqual(self.b.life, 20 - 2 * 2)          # original + one free copy

    def test_ripple_only_casts_the_same_name(self):
        self.assertTrue(self.cast(SURGING_FLAME, [SURGING_SENTINELS, SURGING_SENTINELS,
                                                  SURGING_SENTINELS, SURGING_SENTINELS]))
        self.assertEqual(self.b.life, 20 - 2)              # only the original resolved

    def test_ripple_copies_ripple_in_turn(self):
        # a chain: each free copy reveals further copies and casts them too
        self.assertTrue(self.cast(SURGING_FLAME, [SURGING_FLAME] * 8))
        self.assertEqual(self.b.life, 20 - 2 * 9)          # the original plus all eight copies

    def test_thrumming_stone_ripples_any_spell(self):
        self.g.enter_battlefield(self.a, THRUMMING)
        self.g.settle()
        self.assertTrue(self.cast(BOLT, [BOLT] * 4))
        self.assertEqual(self.b.life, 20 - 3 * 5)          # bolt + four rippled bolts


if __name__ == "__main__":
    unittest.main()
