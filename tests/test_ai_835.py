"""#835: the AI answers removal aimed at its creature with a protection grant that makes the removal's source illegal
(Apostle's Blessing, Razor Barrier, Eldritch Immunity), and doesn't spend it on a harmless spell."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"
DOOM = card("Test Doom", "{1}{B}", "Instant", "Destroy target creature.")
PUMP = card("Test Pump", "{G}", "Instant", "Target creature gets +1/+1 until end of turn.")
GOLEM_RAY = card("Test Ray", "{3}", "Artifact", "{T}: Destroy target creature.")


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class ProtectionAnswers(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def board(self, answer):
        a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [ISLAND] * 10
        for name in ("Plains", "Plains", "Plains", "Plains", "Wastes"):       # Eldritch Immunity costs {C}
            g.enter_battlefield(a, self.db.get(name)).sick = False
        angel = g.enter_battlefield(a, self.db.get("Serra Angel"))
        g.settle()
        a.hand = [self.db.get(answer)]
        g.active_idx = 1
        return g, a, b, angel

    def respond_to(self, g, a, b, item):
        g.stack.append(item)
        play = a.ai.respond(g, a)
        if play:
            g.cast(a, play[0], play[1])
        g.settle()
        return play

    def test_saves_the_angel_from_coloured_removal(self):
        for name in ("Apostle's Blessing", "Razor Barrier", "Eldritch Immunity"):
            g, a, b, angel = self.board(name)
            play = self.respond_to(g, a, b, StackItem(b, list(DOOM.spell_effects), [angel], card=DOOM, name=DOOM.name))
            self.assertIsNotNone(play, name)
            self.assertIn(angel, a.battlefield, name)

    def test_artifacts_option_answers_an_artifact_source(self):
        for name, saves in (("Apostle's Blessing", True), ("Eldritch Immunity", False)):
            g, a, b, angel = self.board(name)
            ray = g.enter_battlefield(b, GOLEM_RAY)
            g.settle()
            item = StackItem(b, list(GOLEM_RAY.activated[0].effects), [angel], source=ray, name="ray")
            self.assertEqual(self.respond_to(g, a, b, item) is not None, saves, name)

    def test_not_spent_on_a_harmless_spell(self):
        g, a, b, angel = self.board("Apostle's Blessing")
        self.assertIsNone(self.respond_to(g, a, b, StackItem(b, list(PUMP.spell_effects), [angel], card=PUMP,
                                                             name=PUMP.name)))
        self.assertEqual(len(a.hand), 1)


if __name__ == "__main__":
    unittest.main()
