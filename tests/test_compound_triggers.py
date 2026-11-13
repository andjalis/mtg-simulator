"""Compound trigger heads: "When ~ enters and whenever <event>, <effects>" as two triggers (#399)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_trigger
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")


def events(line):
    out = _parse_trigger(line)
    return None if out is None else [(t.event, t.filter) for t in out[0]]


class Parsing(unittest.TestCase):
    def test_two_heads(self):
        self.assertEqual(events("When ~ enters and whenever you cast a spell with mana value 5 or greater, draw a card."),
                         [("etb", ""), ("cast_cmc", "cmc>=5")])
        self.assertEqual(events("At the beginning of your upkeep and whenever you cast a green spell, put a charge "
                                "counter on ~."), [("upkeep", ""), ("cast_spell", "spell:green")])
        self.assertEqual(events("When ~ enters and whenever it attacks while saddled, create a 3/3 green Elephant "
                                "creature token."), [("etb", ""), ("attacks", "saddled")])
        self.assertEqual(events("When you cycle this card and when ~ dies, you may tap or untap target permanent."),
                         [("cycle_self", ""), ("dies", "")])

    def test_refusals(self):
        # one event with a condition, not two heads
        self.assertIsNone(_parse_trigger("Whenever ~ and at least one other Warrior and a Frob attack, draw a card."))
        # a half that doesn't read on its own keeps the line ignored
        self.assertIsNone(_parse_trigger("When ~ enters and whenever you frobnicate a widget, draw a card."))
        # "triggers only once each turn" over two Trigger objects isn't representable
        self.assertIsNone(_parse_trigger("When ~ enters and whenever you gain life, surveil 1. This ability triggers "
                                         "only once each turn."))

    def test_effects_read_once_per_head(self):
        trigs, bad, _ = _parse_trigger("When ~ enters and whenever you cast a spell with mana value 5 or greater, "
                                       "draw a card.")
        self.assertEqual(bad, [])
        self.assertEqual([[e.kind for e in t.effects] for t in trigs], [["draw"], ["draw"]])


class Behaviour(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 5, HeuristicAI())
        self.b = Player("b", [BEAR] * 5, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.a.library = [ISLAND] * 10

    def settle(self):
        while self.game.pending or self.game.stack:
            self.game.flush_triggers()
            if self.game.stack:
                self.game.resolve_top()

    def test_both_heads_fire(self):
        beanstalk = card("Test Beanstalk", "{G}", "Enchantment", "When Test Beanstalk enters and whenever you cast a "
                         "spell with mana value 5 or greater, draw a card.")
        self.assertEqual(beanstalk.unsupported, [])
        self.game.enter_battlefield(self.a, beanstalk)
        self.settle()
        self.assertEqual(len(self.a.hand), 1)                     # the enters half
        big = card("Big Thing", "{4}{G}", "Creature — Beast", "", 5, 5)
        small = card("Small Thing", "{G}", "Creature — Elf", "", 1, 1)
        self.a.hand += [big, small]
        self.a.battlefield += [Permanent(FOREST, self.a) for _ in range(6)]
        self.assertTrue(self.game.cast(self.a, small))
        self.settle()
        self.assertEqual(len(self.a.hand), 2)                     # mana value 1: no draw
        self.assertTrue(self.game.cast(self.a, big))
        self.settle()
        self.assertEqual(len(self.a.hand), 2)                     # cast big (-1), drew (+1)
        self.assertEqual(len(self.a.library), 8)

    def test_upkeep_and_cast_shrine(self):
        shrine = card("Test Shrine", "{1}", "Artifact", "At the beginning of your upkeep and whenever you cast a green "
                      "spell, put a charge counter on Test Shrine.")
        self.assertEqual(shrine.unsupported, [])
        perm = Permanent(shrine, self.a)
        self.a.battlefield.append(perm)
        self.a.battlefield += [Permanent(FOREST, self.a) for _ in range(2)]
        elf = card("Small Thing", "{G}", "Creature — Elf", "", 1, 1)
        self.a.hand.append(elf)
        self.assertTrue(self.game.cast(self.a, elf))
        self.settle()
        self.assertEqual(perm.counters.get("charge", 0), 1)
        self.game.fire(self.a, "upkeep")
        self.settle()
        self.assertEqual(perm.counters.get("charge", 0), 2)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_statuses(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Up the Beanstalk", "Voice of Resurgence", "Ivora, Insatiable Heir", "Shrine of Burning Rage",
                     "Bant Sojourners", "Titans' Vanguard"):
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)
        for name in ("Paired Tactician", "MACH-1, Swooping Scoundrel"):
            self.assertEqual(card_coverage(db.get(name)).status, "partial", name)


if __name__ == "__main__":
    unittest.main()
