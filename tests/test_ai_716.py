"""#716: HeuristicAI uses one-sided group removal, X instants, tuck removal and tap+stun tempo spells, and aims them at
the opponent's side."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card

LANDS = {c: card(n, types=f"Basic Land — {n}", text=f"({{T}}: Add {{{c}}}.)")
         for c, n in [("U", "Island"), ("B", "Swamp"), ("R", "Mountain")]}
WURM = card("Test Wurm", "{4}{G}{G}", "Creature — Wurm", "", 6, 4)
ANGEL = card("Test Angel", "{3}{W}{W}", "Creature — Angel", "Flying, vigilance", 4, 4)


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB().get(name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def lands(self, color, n):
        for _ in range(n):
            self.game.enter_battlefield(self.a, LANDS[color])

    def their_end_step(self):
        self.game.active_idx = 1
        self.game.step = "end_step"

    def eot(self, name):
        c = db(name)
        self.a.hand = [c]
        choice = self.a.ai.end_of_turn(self.game, self.a, list(self.game.spell_options(self.a)))
        return c, choice


class RainOfDaggers(Base):
    def test_cast_into_their_creatures(self):
        self.lands("B", 6)
        bears = [self.game.enter_battlefield(self.b, BEAR) for _ in range(2)]
        mine = self.game.enter_battlefield(self.a, BEAR)
        self.a.hand = [db("Rain of Daggers")]
        self.a.ai.main_phase(self.game, self.a)
        self.game.settle()
        self.assertTrue(all(b not in self.b.battlefield for b in bears))
        self.assertIn(mine, self.a.battlefield)
        self.assertEqual(self.a.life, 16)

    def test_held_when_they_have_nothing(self):
        self.lands("B", 6)
        self.game.enter_battlefield(self.a, BEAR)
        plan = self.a.ai.plan_spell(self.game, self.a, db("Rain of Daggers"), True)
        self.assertTrue(plan is None or plan[0] <= 0)


class Electrodominance(Base):
    def test_x_burn_at_their_end_step(self):
        self.lands("R", 4)
        bear = self.game.enter_battlefield(self.b, BEAR)
        mine = self.game.enter_battlefield(self.a, BEAR)
        self.their_end_step()
        card_, choice = self.eot("Electrodominance")
        self.assertIsNotNone(choice)
        self.assertEqual(choice[0].name, card_.name)
        self.assertNotIn(mine, choice[1])
        self.assertTrue(self.game.cast(self.a, choice[0], choice[1]))
        self.game.settle()
        self.assertTrue(bear not in self.b.battlefield or self.b.life < 20)
        self.assertIn(mine, self.a.battlefield)


class SynchronizedEviction(Base):
    def test_tucks_their_best_permanent(self):
        self.lands("U", 5)
        angel = self.game.enter_battlefield(self.b, ANGEL)
        mine = self.game.enter_battlefield(self.a, WURM)
        self.their_end_step()
        _, choice = self.eot("Synchronized Eviction")
        self.assertIsNotNone(choice)
        self.assertEqual(choice[1], [angel])
        self.assertTrue(self.game.cast(self.a, choice[0], choice[1]))
        self.game.settle()
        self.assertNotIn(angel, self.b.battlefield)
        self.assertEqual(self.b.library[-2].name, "Test Angel")
        self.assertIn(mine, self.a.battlefield)


class RimeChill(Base):
    def test_taps_and_stuns_theirs_at_end_step(self):
        self.lands("U", 7)
        wurm, bear = self.game.enter_battlefield(self.b, WURM), self.game.enter_battlefield(self.b, BEAR)
        mine = self.game.enter_battlefield(self.a, WURM)
        self.their_end_step()
        _, choice = self.eot("Rime Chill")
        self.assertIsNotNone(choice)
        chosen = [t for t in choice[1] if t is not None]
        self.assertEqual(set(map(id, chosen)), {id(wurm), id(bear)})
        self.assertTrue(self.game.cast(self.a, choice[0], choice[1]))
        self.game.settle()
        self.assertEqual((wurm.counters.get("stun"), bear.counters.get("stun")), (1, 1))
        self.assertFalse(mine.tapped)

    def test_not_for_a_lone_small_creature(self):
        self.lands("U", 7)
        self.game.enter_battlefield(self.b, card("Test Elf", "{G}", "Creature — Elf", "", 1, 1))
        self.their_end_step()
        _, choice = self.eot("Rime Chill")
        self.assertIsNone(choice)


if __name__ == "__main__":
    unittest.main()
