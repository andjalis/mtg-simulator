"""Empower (Jace token), Discover, Mayhem and Sneak."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

EMPOWER = card("Test Ascent", "{U}", "Sorcery", "Draw a card.\nEmpower Jace 2.")
DISCOVER = card("Test Discovery", "{2}{G}", "Sorcery", "Discover 3.")
MAYHEM = card("Test Bolt", "{3}{R}", "Instant", "~ deals 4 damage to target creature.\nMayhem {1}{R}")
SNEAKER = card("Test Ninja", "{3}{B}", "Creature — Ninja", "Sneak {B}", 4, 4)
BIG = card("Big Spell", "{6}", "Creature — Giant", "", 6, 6)
CHEAP = card("Cheap Spell", "{1}", "Creature — Giant", "", 2, 2)


class Base(unittest.TestCase):
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


class EmpowerDiscover(Base):
    def test_templates(self):
        for c in (EMPOWER, DISCOVER, MAYHEM, SNEAKER):
            self.assertEqual(c.unsupported, [], c.name)

    def test_empower_makes_then_grows_one_jace(self):
        for _ in range(2):
            self.perm(ISLAND)
            self.a.hand.append(EMPOWER)
            self.assertTrue(self.game.cast(self.a, EMPOWER, []))
            self.game.settle()
        jaces = [x for x in self.a.battlefield if "Jace" in x.card.subtypes]
        self.assertEqual(len(jaces), 1)
        self.assertEqual(jaces[0].loyalty, 4)
        self.assertEqual(len(jaces[0].card.loyalty_abilities), 2)

    def test_discover_casts_first_small_nonland_for_free(self):
        spell = card("Test Discovery", "{3}", "Sorcery", "Discover 3.")
        for _ in range(3):
            self.perm(MOUNTAIN)
        self.a.library = [BIG, CHEAP, ISLAND, ISLAND]            # the top of the library is the end of the list
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, []))
        self.game.settle()
        self.assertIn("Cheap Spell", [x.card.name for x in self.a.battlefield])
        self.assertEqual(len(self.a.library), 3)                 # Big Spell plus the two skipped Islands
        self.assertEqual(self.a.library[-1].name, "Big Spell")


class MayhemSneak(Base):
    def test_mayhem_only_after_discard(self):
        self.a.hand.append(MAYHEM)
        self.perm(MOUNTAIN)
        self.perm(MOUNTAIN)
        self.assertEqual([c for c in self.game.spell_options(self.a) if c.name.endswith("(mayhem)")], [])
        self.game.discard_card(self.a, MAYHEM)
        opts = [c for c in self.game.spell_options(self.a) if c.name.endswith("(mayhem)")]
        self.assertEqual(len(opts), 1)
        self.perm(BEAR, self.b)
        self.assertTrue(self.game.cast(self.a, opts[0], [self.b.battlefield[0]]))
        self.game.settle()
        self.assertEqual(self.b.battlefield, [])

    def test_sneak_returns_unblocked_attacker(self):
        att = self.perm(BEAR)
        self.game.attackers, self.game.blocks, self.game.attack_targets = [att], {}, {att: self.b}
        self.a.hand.append(SNEAKER)
        self.perm(card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)"))
        self.game.step = "declare_blockers"
        from mtgsim.engine import default_sneak
        default_sneak(self.game, self.a, [att], {})
        self.assertIn(BEAR, self.a.hand)
        ninja = next(x for x in self.a.battlefield if x.card.name == "Test Ninja")
        self.assertTrue(ninja.tapped)
        self.assertIn(ninja, self.game.attackers)


if __name__ == "__main__":
    unittest.main()
