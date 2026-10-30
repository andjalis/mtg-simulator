"""Casting windows ("Cast this spell only during ...")."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cx_timing import parse_window
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, card

BLADE = card("Test Blade", "{1}{B}", "Instant", "Cast this spell only during the declare attackers step and only if "
             "you've been attacked this step.\nDestroy target nonblack attacking creature.")
BERSERK = card("Test Frenzy", "{G}", "Instant", "Cast this spell only before the combat damage step.\nTarget "
               "creature gets +2/+2 until end of turn.")
GLYPH = card("Test Glyph", "{U}", "Instant", "Cast this spell only after combat.\nDraw a card.")
TURN = card("Test Turn", "{U}", "Instant", "Cast this spell only during your turn.\nDraw a card.")
COND = card("Test Cond", "{1}{U}", "Creature — Bird", "Cast this spell only if you've cast another spell this turn.", 2, 2)
TRIBE = card("Test Tribe", "{B}", "Instant", "Cast this spell only if you control two or more Vampires.\nDraw a card.")
UNKNOWN = card("Test Unknown", "{U}", "Instant", "Cast this spell only if a creature died this turn.\nDraw a card.")


class CastWindows(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_parse(self):
        for c in (BLADE, BERSERK, GLYPH, TURN):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertTrue(UNKNOWN.unsupported)
        self.assertEqual(parse_window("during combat on an opponent's turn."),
                         (("declare_attackers", "declare_blockers", "combat_damage", "end_combat"), "theirs", False))
        self.assertIsNone(parse_window("if you control a snow land."))

    def window(self, c):
        from mtgsim.cx_timing import window_ok
        return window_ok(self.game, self.a, c)

    def test_attacked_this_step(self):
        self.game.active_idx = 1
        self.game.step = "declare_attackers"
        self.assertFalse(self.window(BLADE))
        atk = Permanent(BEAR, self.b)
        self.game.attackers = [atk]
        self.game.attack_targets = {atk: self.a}
        self.assertTrue(self.window(BLADE))
        self.game.step = "declare_blockers"
        self.assertFalse(self.window(BLADE))

    def test_before_combat_damage(self):
        for step, ok in (("main1", True), ("declare_blockers", True), ("combat_damage", False), ("main2", False)):
            self.game.step = step
            self.assertEqual(self.window(BERSERK), ok, step)

    def test_after_combat_and_turn(self):
        self.game.step = "main2"
        self.assertTrue(self.window(GLYPH))
        self.game.step = "main1"
        self.assertFalse(self.window(GLYPH))
        self.game.active_idx = 0
        self.assertTrue(self.window(TURN))
        self.game.active_idx = 1
        self.assertFalse(self.window(TURN))

    def test_conditions(self):
        from mtgsim.cx_timing import window_ok
        self.assertEqual(COND.unsupported + TRIBE.unsupported, [])
        self.game.step = "main1"
        self.assertFalse(window_ok(self.game, self.a, COND))
        self.game.spells_cast = {"turn": self.game.turn, self.a.name: 1}
        self.assertTrue(window_ok(self.game, self.a, COND))
        vamp = card("Test Vampire", "{B}", "Creature — Vampire", "", 1, 1)
        self.assertFalse(window_ok(self.game, self.a, TRIBE))
        self.a.battlefield += [Permanent(vamp, self.a), Permanent(vamp, self.a)]
        self.assertTrue(window_ok(self.game, self.a, TRIBE))


if __name__ == "__main__":
    unittest.main()
