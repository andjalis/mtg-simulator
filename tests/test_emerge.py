"""Emerge: sacrifice a creature, pay the emerge cost reduced by its mana value."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

MAW = card("Test Maw", "{8}", "Creature — Eldrazi", "Emerge {6}{B}\nWhen you cast this spell, target opponent loses 3 life "
           "and you gain 3 life.", 7, 8)
OFFSPRING = card("Test Offspring", "{3}{W}", "Creature — Alien", "Emerge {5}{W}\nWhen ~ enters, create a 2/2 white Alien "
                 "creature token. If ~'s emerge cost was paid, instead create X of those tokens, where X is the "
                 "sacrificed creature's toughness.", 3, 3)
EMISSARY = card("Test Emissary", "{2}{G}", "Creature — Human Horror", "When you sacrifice ~ while casting a spell with "
                "emerge, create a 3/2 colorless Eldrazi Horror creature token.", 2, 2)
CRAB = card("Test Crab", "{9}", "Creature — Eldrazi", "Emerge from artifact {5}{B}{B}", 8, 8)
HERIGAST = card("Test Herigast", "{9}", "Creature — Eldrazi Dragon", "Flying\nEach creature spell you cast has emerge. "
                "The emerge cost is equal to its mana cost.", 6, 6)
BIG = card("Test Big", "{5}{G}", "Creature — Beast", "", 5, 5)
SWAMP = card("Test Swamp", "", "Basic Land — Swamp", "{T}: Add {B}.")
PLAINS = card("Test Plains", "", "Basic Land — Plains", "{T}: Add {W}.")
ROCK = card("Test Rock", "{3}", "Artifact", "")


class Emerge(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, c, n=1, who=None):
        for _ in range(n):
            perm = self.game.enter_battlefield(who or self.a, c)
            perm.sick = False
        self.game.settle()
        return perm

    def emerge_option(self, kind="emerge"):
        return next((o for o in self.game.spell_options(self.a) if self.game._origin(o)[1] == kind
                     and self.game.can_cast_now(self.a, o)), None)

    def test_templates(self):
        for c in (MAW, OFFSPRING, EMISSARY, CRAB, HERIGAST):
            self.assertEqual(c.unsupported, [], c.name)

    def test_reduces_cost_by_mana_value(self):
        self.put(SWAMP)
        self.put(ISLAND, 3)                  # four lands: {6}{B} - 3 = {3}{B}
        victim = self.put(BIG)               # mana value 6
        self.a.hand = [MAW]
        self.assertTrue(self.game.cast(self.a, self.emerge_option()))
        self.game.settle()
        self.assertNotIn(victim, self.a.battlefield)
        self.assertIn("Test Maw", [x.card.name for x in self.a.battlefield])
        self.assertEqual(self.b.life, 17)    # the cast trigger

    def test_not_offered_when_hard_castable_or_unpayable(self):
        self.put(SWAMP)
        self.put(BEAR)
        self.a.hand = [MAW]
        self.assertIsNone(self.emerge_option())      # {6}{B} - 2 = {4}{B}: only one land
        self.put(ISLAND, 4)
        self.assertIsNotNone(self.emerge_option())
        self.put(ISLAND, 4)
        self.assertIsNone(self.emerge_option())      # eight lands pay the full {8}

    def test_adipose_makes_tokens_equal_to_toughness(self):
        self.put(PLAINS)
        victim = self.put(BIG)                       # 5/5, mana value 6: {5}{W} reduced to {W}
        self.a.hand = [OFFSPRING]
        self.assertTrue(self.game.cast(self.a, self.emerge_option()))
        self.game.settle()
        aliens = [x for x in self.a.battlefield if x.card.name == "Alien token"]
        self.assertEqual(len(aliens), 5)
        self.assertNotIn(victim, self.a.battlefield)

    def test_adipose_hardcast_makes_one_token(self):
        self.put(PLAINS, 4)
        self.a.hand = [OFFSPRING]
        self.assertTrue(self.game.cast(self.a, OFFSPRING))
        self.game.settle()
        self.assertEqual(len([x for x in self.a.battlefield if x.card.name == "Alien token"]), 1)

    def test_foul_emissary_makes_a_horror(self):
        self.put(SWAMP)
        self.put(ISLAND, 3)
        self.put(EMISSARY)
        self.a.hand = [MAW]
        # sacrifice the cheapest candidate that works: the 2/2 (mana value 3): {3}{B} needs four lands
        self.assertTrue(self.game.cast(self.a, self.emerge_option()))
        self.game.settle()
        self.assertTrue(any(x.card.is_token and x.power == 3 for x in self.a.battlefield))

    def test_emerge_from_artifact_only_sacrifices_artifacts(self):
        self.put(SWAMP, 2)
        self.put(ISLAND, 2)
        self.put(BEAR)
        self.a.hand = [CRAB]
        self.assertIsNone(self.emerge_option("emerge"))
        self.assertIsNone(self.emerge_option())
        self.put(ROCK)
        self.assertIsNotNone(self.emerge_option())

    def test_herigast_gives_creatures_emerge(self):
        self.put(HERIGAST)
        self.put(ISLAND, 3)
        self.put(BEAR)
        self.a.hand = [BIG]                  # {5}{G} - 2... needs G: no green source
        self.assertIsNone(self.emerge_option())
        self.put(card("Test Forest", "", "Basic Land — Forest", "{T}: Add {G}."), 1)
        self.a.hand = [BIG]
        opt = self.emerge_option()
        self.assertIsNotNone(opt)


if __name__ == "__main__":
    unittest.main()
