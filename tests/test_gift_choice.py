"""Promising a gift is a choice made while casting; the other mode is playable (#483)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_combat_triggers import Scripted
from tests.test_templates import card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")
ROCK = card("Rock", "{3}", "Artifact")
ROCK2 = card("Rock Two", "{3}", "Artifact")


@unittest.skipUnless(os.path.exists(DB), "card database not built")
class Gift(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def game(self, ai, land):
        a, b = Player("a", [], ai), Player("b", [], Scripted())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 2, "main1"
        a.library = b.library = [self.db.get(land)] * 10
        for _ in range(4):
            g.enter_battlefield(a, self.db.get(land)).sick = False
        return g, a, b

    def fish(self, p):
        return [x for x in p.battlefield if "Fish" in x.card.subtypes]

    # ------------------------------------------------ the engine: the mode decides which targets are needed
    def test_wear_down_with_one_target_is_cast_unpromised(self):
        g, a, b = self.game(Scripted(), "Forest")
        rock = g.enter_battlefield(b, ROCK)
        wear = self.db.get("Wear Down")
        a.hand.append(wear)
        self.assertTrue(g.cast(a, wear, targets=[rock]))      # before #483: the gifted mode's two targets were required
        g.settle()
        self.assertNotIn(rock, b.battlefield)
        self.assertEqual(b.hand, [])                           # no gift card

    def test_wear_down_with_two_targets_is_promised(self):
        g, a, b = self.game(Scripted(), "Forest")
        r1, r2 = g.enter_battlefield(b, ROCK), g.enter_battlefield(b, ROCK2)
        wear = self.db.get("Wear Down")
        a.hand.append(wear)
        self.assertTrue(g.cast(a, wear, targets=[None, r1, r2]))
        g.settle()
        self.assertNotIn(r1, b.battlefield)
        self.assertNotIn(r2, b.battlefield)
        self.assertEqual(len(b.hand), 1)                       # the gift: they drew

    def test_parting_gust_on_our_own_creature_is_a_blink(self):
        g, a, b = self.game(Scripted(), "Plains")
        mine = g.enter_battlefield(a, card("Mine", "{2}", "Creature — Human", "", 2, 2))
        gust = self.db.get("Parting Gust")
        a.hand.append(gust)
        self.assertTrue(g.cast(a, gust, targets=[mine]))
        g.settle()
        self.assertEqual(self.fish(b), [])                     # not promised
        g.begin_end_step(a)
        g.settle()
        back = [x for x in a.battlefield if x.card.name == "Mine"]
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0].counters.get("+1/+1"), 1)

    def test_parting_gust_on_theirs_is_promised(self):
        g, a, b = self.game(Scripted(), "Plains")
        foe = g.enter_battlefield(b, card("Foe", "{3}", "Creature — Ogre", "", 4, 4))
        gust = self.db.get("Parting Gust")
        a.hand.append(gust)
        self.assertTrue(g.cast(a, gust, targets=[foe]))
        g.settle()
        self.assertEqual(len(self.fish(b)), 1)
        g.begin_end_step(a)
        g.settle()
        self.assertFalse(any(x.card.name == "Foe" for x in b.battlefield))

    # ------------------------------------------------ HeuristicAI: promise only when it pays
    def test_ai_promises_wear_down_only_for_two_targets(self):
        g, a, b = self.game(HeuristicAI(), "Forest")
        rock = g.enter_battlefield(b, ROCK)
        wear = self.db.get("Wear Down")
        a.hand = [wear]
        g.main_phase(a)
        g.settle()
        self.assertNotIn(rock, b.battlefield)
        self.assertEqual(b.hand, [])
        g, a, b = self.game(HeuristicAI(), "Forest")
        r1, r2 = g.enter_battlefield(b, ROCK), g.enter_battlefield(b, ROCK2)
        a.hand = [self.db.get("Wear Down")]
        g.main_phase(a)
        g.settle()
        self.assertEqual((r1 in b.battlefield, r2 in b.battlefield, len(b.hand)), (False, False, 1))

    def test_flood_maw_promises_only_when_the_upgrade_pays(self):
        # an instant: HeuristicAI casts it from its response paths with both modes' targets; the engine's default
        # choice compares the modes' values
        g, a, b = self.game(HeuristicAI(), "Island")
        foe = g.enter_battlefield(b, card("Foe", "{3}", "Creature — Ogre", "", 4, 4))
        maw = self.db.get("Into the Flood Maw")
        a.hand.append(maw)
        self.assertTrue(g.cast(a, maw, targets=[foe, foe]))
        g.settle()
        self.assertEqual((foe in b.battlefield, self.fish(b)), (False, []))          # bounced, no Fish
        g, a, b = self.game(HeuristicAI(), "Island")
        rock = g.enter_battlefield(b, card("Big Rock", "{6}", "Artifact"))
        maw = self.db.get("Into the Flood Maw")
        a.hand.append(maw)
        self.assertTrue(g.cast(a, maw, targets=[None, rock]))   # only the gifted mode reaches an artifact
        g.settle()
        self.assertEqual((rock in b.battlefield, len(self.fish(b))), (False, 1))

if __name__ == "__main__":
    unittest.main()
