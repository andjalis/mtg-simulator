"""Compound trigger heads: "When ~ enters and whenever <B>, <body>" (#399)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_trigger
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")


def heads(line):
    out = _parse_trigger(line)
    if out is None or out[1]:
        return None
    return [(t.event, [(e.kind, e.target) for e in t.effects]) for t in out[0]]


class Parsing(unittest.TestCase):
    def test_two_heads_share_the_body(self):
        self.assertEqual(heads("When ~ enters and whenever you cast a spell with mana value 5 or greater, draw a card."),
                         [("etb", [("draw", "none")]), ("cast_cmc", [("draw", "none")])])
        self.assertEqual([e for e, _ in heads("At the beginning of your upkeep and whenever you cast a green spell, "
                                              "put a charge counter on ~.")], ["upkeep", "cast_spell"])
        self.assertEqual([e for e, _ in heads("When you cycle ~ and when ~ dies, you may tap or untap target "
                                              "permanent.")], ["cycle_self", "dies"])

    def test_it_in_the_second_head_is_the_permanent(self):
        self.assertEqual([e for e, _ in heads("When ~ enters and whenever it deals combat damage to a player, "
                                              "create a Blood token.")], ["etb", "combat_damage_player"])

    def test_shared_it_after_enters_is_the_permanent(self):
        got = heads("When ~ enters and whenever you expend 4, put a stash counter on it.")
        self.assertEqual(got[1], ("expend", [("add_counter", "self")]))

    def test_refusals(self):
        for line in ("Whenever ~ and at least one other Warrior attack, put a +1/+1 counter on ~.",   # one event
                     # one half doesn't parse: nothing is dropped
                     "When ~ enters and whenever you activate a power-up ability, put a +1/+1 counter on ~.",
                     "When ~ enters and whenever an opponent draws a card except the first one they draw in each "
                     "of their draw steps, ~ deals 1 damage to any target.",
                     # "it" is the event object of an attack, not shared with the upkeep head
                     "At the beginning of your upkeep and whenever a creature attacks, tap it."):
            with self.subTest(line):
                self.assertIsNone(heads(line))


class Behaviour(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_both_heads_fire(self):
        beanstalk = card("Test Beanstalk", "{G}", "Enchantment",
                         "When ~ enters and whenever you cast a spell with mana value 5 or greater, draw a card.")
        hand = len(self.a.hand)
        self.game.enter_battlefield(self.a, beanstalk)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)                   # enters
        for _ in range(5):
            self.game.enter_battlefield(self.a, ISLAND)
        big = card("Test Big", "{4}{U}", "Sorcery", "You gain 1 life.")
        small = card("Test Small", "{U}", "Sorcery", "You gain 1 life.")
        self.a.hand += [small, big]
        hand = len(self.a.hand)
        self.assertTrue(self.game.cast(self.a, small))
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand - 1)                    # mana value 1: no draw
        for perm in self.a.battlefield:
            perm.tapped = False
        self.assertTrue(self.game.cast(self.a, big))
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand - 1)                    # cast (-1), drew (+1)

    @unittest.skipUnless(os.path.exists(DB), "card database not built")
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        shrine = self.game.enter_battlefield(self.a, db.get("Shrine of Burning Rage"))
        self.game.begin_upkeep(self.a)
        self.game.settle()
        self.assertEqual(shrine.counters.get("charge"), 1)
        overflow = self.game.enter_battlefield(self.a, db.get("Hoarder's Overflow"))
        self.game.settle()
        self.assertEqual(overflow.counters.get("stash"), 1)
        self.game.fire(self.a, "expend", subject=4)                        # as engine/costs.py fires it
        self.game.settle()
        self.assertEqual(overflow.counters.get("stash"), 2)
        sojourners = db.get("Bant Sojourners")
        self.assertEqual([t.event for t in sojourners.cycle_self_triggers], ["cycle_self"])
        self.assertEqual([t.event for t in sojourners.triggers], ["dies"])
        perm = self.game.enter_battlefield(self.a, sojourners)
        self.game.destroy(perm)
        self.game.settle()
        self.assertTrue(any("Soldier" in x.card.subtypes for x in self.a.battlefield))


if __name__ == "__main__":
    unittest.main()
