"""#345 slice: "Remove X <kind> counters from ~" as an activation cost. X is the number removed (all of them, or the
mana X when the cost also has {X}), and the ability's X effects use it (Arcbound Javelineer, Talon of Pain)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from mtgsim.engine.policy import ability_worth
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card

JAV = card("Test Javelin", "{2}", "Artifact Creature — Construct", "{T}, Remove X +1/+1 counters from ~: It deals X "
           "damage to target attacking or blocking creature.", 0, 1)
TALON = card("Test Talon", "{4}", "Artifact", "{X}, {T}, Remove X charge counters from ~: It deals X damage to any "
             "target.")
OGRE = card("Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)
MOUNTAIN = card("Mountain", "", "Basic Land — Mountain", "({T}: Add {R}.)")


def game():
    a, b = Player("a", [ISLAND] * 10, HeuristicAI()), Player("b", [ISLAND] * 10, HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    for p in (a, b):
        p.library = [ISLAND] * 20
    return g, a, b


class Parse(unittest.TestCase):
    def test_cost(self):
        self.assertEqual(JAV.unsupported, [])
        self.assertEqual(JAV.activated[0].extra_costs["remove_counter_count"], "x")
        self.assertEqual(TALON.unsupported, [])

    def test_x_must_be_used(self):
        for text in ("{T}, Remove X charge counters from ~: Draw a card.",
                     "{3}, {T}, Remove X charge counters from ~: Scry X."):     # a die-roll parse of "Scry X"
            self.assertTrue(card("Test Jar", "{2}", "Artifact", text).unsupported, text)


class Engine(unittest.TestCase):
    def test_removes_all_and_deals_that_much(self):
        g, a, b = game()
        jav = g.enter_battlefield(a, JAV)
        jav.sick = False
        jav.counters["+1/+1"] = 3
        ogre = g.enter_battlefield(b, OGRE)
        self.assertFalse(g.activate_ability(a, jav, 0, [ogre]))      # not attacking or blocking
        g.attackers = [ogre]
        self.assertTrue(g.activate_ability(a, jav, 0, [ogre]))
        g.settle()
        self.assertEqual(jav.counters.get("+1/+1", 0), 0)
        self.assertNotIn(ogre, b.battlefield)

    def test_no_counters_cannot_activate(self):
        g, a, b = game()
        jav = g.enter_battlefield(a, JAV)
        jav.sick = False
        self.assertFalse(g.can_activate(a, jav, 0))

    def test_mana_x_and_counters_match(self):
        g, a, b = game()
        for _ in range(5):
            g.enter_battlefield(a, MOUNTAIN).sick = False
        talon = g.enter_battlefield(a, TALON)
        talon.counters["charge"] = 2
        self.assertEqual(g.ability_x(a, talon, talon.activated[0]), 2)      # capped by the counters, not the mana
        self.assertTrue(g.activate_ability(a, talon, 0, [b]))
        g.settle()
        self.assertEqual(b.life, 18)
        self.assertEqual(talon.counters.get("charge", 0), 0)
        self.assertEqual(sum(not x.tapped for x in a.battlefield if x.card.is_land), 3)

    def test_ai_wants_it_on_an_attacker(self):
        g, a, b = game()
        jav = g.enter_battlefield(a, JAV)
        jav.sick = False
        jav.counters["+1/+1"] = 3
        ogre = g.enter_battlefield(b, OGRE)
        g.attackers = [ogre]
        self.assertTrue(ability_worth(g, a, jav, 0))
        self.assertTrue(g.activate_ability(a, jav, 0))          # the AI's own target choice, X previewed as 3
        g.settle()
        self.assertNotIn(ogre, b.battlefield)


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class Cards(unittest.TestCase):
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        self.assertEqual(db.get("Arcbound Javelineer").unsupported, [])
        talon = db.get("Talon of Pain")
        self.assertEqual(talon.activated[0].extra_costs["remove_counter_count"], "x")
        self.assertTrue(db.get("Brain in a Jar").unsupported)


if __name__ == "__main__":
    unittest.main()
