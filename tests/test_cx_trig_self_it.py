""""it" in a self-headed trigger is the permanent itself (#356)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_trigger
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")


def targets(line):
    out = _parse_trigger(line)
    return [[e.target for e in t.effects] for t in out[0]]


class Parsing(unittest.TestCase):
    def test_self_events_bind_it_to_self(self):
        self.assertEqual(targets("Whenever ~ deals combat damage to a player, put a +1/+1 counter on it."), [["self"]])
        self.assertEqual(targets("Whenever ~ becomes untapped, put two +1/+1 counters on it."), [["self"]])
        self.assertEqual(targets("Whenever ~ attacks or blocks, it gets +1/+1 until end of turn."), [["self"], ["self"]])
        got = targets("Whenever ~ attacks, you may pay {1}. If you do, it gains flying until end of turn.")[0]
        self.assertNotIn("prev", got)

    def test_other_antecedents_keep_prev(self):
        for line in ("When ~ dies, return it to the battlefield tapped under its owner's control.",   # graveyard card
                     "When ~ enters, create a 1/1 white Soldier creature token, then attach ~ to it.",   # the token
                     "Whenever ~ attacks, tap target creature. It doesn't untap during its controller's next untap step.",
                     "Whenever ~ blocks a creature, destroy it at end of combat."):
            with self.subTest(line):
                self.assertNotIn("self", [x for t in targets(line) for x in t])


class Behaviour(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_combat_damage_counter_and_untap_pump(self):
        slith = self.game.enter_battlefield(self.a, card("Test Slith", "{2}", "Artifact Creature — Slith",
                                            "Whenever ~ deals combat damage to a player, put a +1/+1 counter on it.",
                                            power=1, toughness=1))
        self.game.fire(self.a, "combat_damage_player", slith, context=self.b)     # as engine/combat.py fires it
        self.game.settle()
        self.assertEqual(slith.p1, 1)
        butcher = self.game.enter_battlefield(self.a, card("Test Butcher", "{2}", "Creature — Minotaur",
                                              "Whenever ~ becomes untapped, it gets +2/+0 until end of turn.",
                                              power=2, toughness=2))
        self.game.fire(self.a, "becomes_untapped", source=butcher)
        self.game.settle()
        self.assertEqual(butcher.power, 4)

    @unittest.skipUnless(os.path.exists(DB), "card database not built")
    def test_real_cards(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        veteran = self.game.enter_battlefield(self.a, db.get("Benalish Veteran"))
        self.game.fire(self.a, "attacks", veteran)
        self.game.settle()
        self.assertEqual((veteran.power, veteran.toughness), (3, 3))
        raider = self.game.enter_battlefield(self.a, db.get("Saprazzan Raider"))
        self.game.fire(self.a, "becomes_blocked", raider)
        self.game.settle()
        self.assertNotIn(raider, self.a.battlefield)
        self.assertTrue(any(c.name == "Saprazzan Raider" for c in self.a.hand))


if __name__ == "__main__":
    unittest.main()
