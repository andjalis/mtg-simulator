"""Divided damage, split on resolution."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, DRAGON3, ISLAND, card

BOLT = card("Test Forked Bolt", "{R}", "Sorcery", "Test Forked Bolt deals 2 damage divided as you choose among one "
            "or two targets.")
VOLLEY = card("Test Volley", "{2}{R}", "Sorcery", "Test Volley deals 3 damage divided as you choose among one, two, or "
              "three target creatures.")


class DividedDamage(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        x = Permanent(c, owner)
        owner.battlefield.append(x)
        return x

    def cast(self, c):
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [None] * len(c.spell_effects), card=c,
                                         name=c.name))
        self.game.resolve_top()

    def test_parses(self):
        self.assertEqual((BOLT.unsupported, VOLLEY.unsupported), ([], []))

    def test_kills_a_bear_then_face(self):
        bear = self.perm(BEAR, self.b)
        life = self.b.life
        self.cast(BOLT)
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(self.b.life, life)
        self.cast(BOLT)
        self.assertEqual(self.b.life, life - 2)

    def test_creature_only_scope_never_hits_face(self):
        big = self.perm(DRAGON3, self.b)
        life = self.b.life
        self.cast(VOLLEY)
        self.assertEqual(self.b.life, life)
        self.assertEqual(big.damage, 3)


class DivisionAtCast(DividedDamage):
    def test_division_fixed_when_put_on_stack(self):
        self.assertEqual(BOLT.approximations, [])
        bear = self.perm(BEAR, self.b)
        item = StackItem(self.a, list(BOLT.spell_effects), [None], card=BOLT, name=BOLT.name)
        self.game.stack.append(item)
        planned = item.divided[id(item.effects[0])]
        self.assertEqual([(v, n) for v, n in planned], [(bear, 2)])     # chosen now, not on resolution
        self.perm(DRAGON3, self.b)                                      # a better target appears afterwards
        self.game.resolve_top()
        self.assertNotIn(bear, self.b.battlefield)

    def test_illegal_target_share_is_lost(self):
        bear = self.perm(BEAR, self.b)
        item = StackItem(self.a, list(BOLT.spell_effects), [None], card=BOLT, name=BOLT.name)
        self.game.stack.append(item)
        life = self.b.life
        self.b.battlefield.remove(bear)                                 # the target is gone before resolution
        self.game.resolve_top()
        self.assertEqual(self.b.life, life)


STRIKE = card("Test Strike", "{1}{R}", "Instant", "Test Strike deals 2 damage to target creature and 2 damage to target "
              "player or planeswalker.\nDraw a card.")


class TwoTargets(DividedDamage):
    def test_two_independent_targets(self):
        self.assertEqual(STRIKE.unsupported, [])
        bear = self.perm(BEAR, self.b)
        life = self.b.life
        self.game.stack.append(StackItem(self.a, list(STRIKE.spell_effects), [bear, self.b, None], card=STRIKE,
                                         name=STRIKE.name))
        self.game.resolve_top()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(self.b.life, life - 2)


if __name__ == "__main__":
    unittest.main()


class DividedQualified(DividedDamage):
    """#626 DMG-DIVIDED: X, "up to N", and qualified recipients."""
    def test_parses_real_shapes(self):
        for text in ("deals X damage divided as you choose among any number of target creatures.",
                     "deals 3 damage divided as you choose among one, two, or three target attacking or blocking creatures.",
                     "deals 3 damage divided as you choose among one, two, or three target creatures with flying.",
                     "deals 3 damage divided as you choose among one, two, or three target white and/or blue creatures.",
                     "deals 5 damage divided as you choose among up to five targets.",
                     "deals X damage divided as you choose among any number of target attacking or blocking creatures "
                     "without flying."):
            c = card("Test Spell", "{X}{R}", "Sorcery", "Test Spell " + text)
            self.assertEqual(c.unsupported, [], text)
        c = card("Test Spell", "{2}{R}", "Sorcery", "Test Spell deals 3 damage divided as you choose among up to X targets.")
        self.assertTrue(c.unsupported)

    def test_x_damage_is_divided_by_the_x_paid(self):
        spell = card("Test Fire Covenant", "{X}{R}", "Instant", "Test Fire Covenant deals X damage divided as you choose "
                     "among any number of target creatures.")
        bear = self.perm(BEAR, self.b)
        big = self.perm(DRAGON3, self.b)
        item = StackItem(self.a, list(spell.spell_effects), [None], card=spell, name=spell.name)
        item.x = 2
        self.game.stack.append(item)
        self.game.resolve_top()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(big.damage, 0)

    def test_attacking_or_blocking_only(self):
        spell = card("Test Roil", "{3}{R}", "Instant", "Test Roil deals 5 damage divided as you choose among any number "
                     "of target attacking or blocking creatures.")
        idle = self.perm(BEAR, self.b)
        attacker = self.perm(BEAR, self.b)
        self.game.attackers = [attacker]
        self.cast(spell)
        self.assertIn(idle, self.b.battlefield)
        self.assertNotIn(attacker, self.b.battlefield)
