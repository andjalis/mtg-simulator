"""#345 slice: counter removal from "that creature", the amount "removed this way", and "remove ... and put ..."."""
import random
import unittest

from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")
ISLAND = card("Island", types="Basic Land — Island", text="({T}: Add {U}.)")
LEECH = card("Test Leech", "{2}{B}", "Creature — Leech",
             "Flash\nWhen this creature enters, target creature an opponent controls gets -2/-2 until end of turn. "
             "Remove all counters from that creature.", 1, 1)
MENTALITY = card("Test Mentality", "{U}", "Instant",
                 "Remove all counters from target nonland permanent you control. Draw a card for each counter "
                 "removed this way.")
BEETLE = card("Test Beetle", "{3}{B}", "Creature — Insect",
              "Whenever this creature attacks, remove a -1/-1 counter from target creature you control and put a "
              "-1/-1 counter on up to one target creature defending player controls.", 4, 4)


def game(ai=None, lands=SWAMP):
    a, b = Player("a", [], ai or Scripted()), Player("b", [], Scripted())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [lands] * 10
    for _ in range(4):
        g.enter_battlefield(a, lands).sick = False
    g.settle()
    return g, a, b


def put(g, p, c, **counters):
    x = g.enter_battlefield(p, c)
    x.sick = False
    x.counters.update(counters)
    g.settle()
    return x


class Parse(unittest.TestCase):
    def test_that_creature(self):
        effects, bad = _parse_effects("Target creature gets -2/-2 until end of turn. Remove all counters from that "
                                      "creature.")
        self.assertEqual(bad, [])
        self.assertEqual([(e.kind, e.target) for e in effects][-1], ("cx_remove_counters", "prev"))

    def test_removed_this_way(self):
        effects, bad = _parse_effects(MENTALITY.oracle)
        self.assertEqual(bad, [])
        self.assertEqual(effects[1].data["xq"], ("this_way", "removed", "counter"))

    def test_compound_needs_both_halves(self):
        self.assertEqual(len(BEETLE.triggers[0].effects), 2)
        _, bad = _parse_effects("Remove a -1/-1 counter from target creature you control and put a -1/-1 counter on "
                                "up to one target creature with flying that dances.")
        self.assertTrue(bad)


class Play(unittest.TestCase):
    def test_leech_strips_the_counters_of_its_target(self):
        g, a, b = game()
        foe = put(g, b, card("Foe", "{3}", "Creature — Ogre", "", 3, 3), **{"+1/+1": 2, "flying": 1})
        put(g, a, LEECH)                      # its ETB: -2/-2 on the only opposing creature, then strip it (#377)
        self.assertEqual({k: v for k, v in foe.counters.items() if v}, {})
        self.assertEqual((foe.power, foe.toughness), (1, 1))          # 3/3 base, counters gone, -2/-2

    def test_mentality_draws_one_per_counter_removed(self):
        g, a, b = game(lands=ISLAND)
        rock = put(g, a, card("Rock", "{2}", "Artifact", ""), charge=2, oil=1)
        a.library = [ISLAND] * 10
        hand = len(a.hand)
        a.hand.append(MENTALITY)
        self.assertTrue(g.cast(a, MENTALITY, targets=[rock]))
        g.settle()
        self.assertEqual(len(a.hand), hand + 3)
        self.assertEqual({k: v for k, v in rock.counters.items() if v}, {})

    def test_mentality_with_no_counters_draws_nothing(self):
        g, a, b = game(lands=ISLAND)
        rock = put(g, a, card("Rock", "{2}", "Artifact", ""))
        hand = len(a.hand)
        a.hand.append(MENTALITY)
        g.cast(a, MENTALITY, targets=[rock])
        g.settle()
        self.assertEqual(len(a.hand), hand)

    def test_beetle_moves_a_weakness_counter_on_attack(self):
        g, a, b = game()
        beetle = put(g, a, BEETLE)
        mine = put(g, a, card("Mine", "{1}", "Creature — Human", "", 3, 3), **{"-1/-1": 1})
        foe = put(g, b, card("Foe", "{3}", "Creature — Ogre", "", 3, 3))
        a.ai.attack = [beetle]
        g.combat(a, b)
        g.settle()
        self.assertEqual(mine.counters.get("-1/-1", 0), 0)
        self.assertEqual(foe.counters.get("-1/-1", 0), 1)


if __name__ == "__main__":
    unittest.main()
