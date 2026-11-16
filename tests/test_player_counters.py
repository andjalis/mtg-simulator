"""#629: experience and poison counters given by "<player> gets N <kind> counters" and read by "for each <kind> counter
you have / your opponents have" (cx_grammar_life player_counter, cx_grammar_quantity pcounters)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Aang, Airbending Master", "Atreus, Impulsive Son", "Decimator Web", "Kalemne, Disciple of Iroas",
        "Katara, Waterbending Master", "Kelsien, the Plague", "Mycosynth Fiend", "Otharri, Suns' Glory",
        "Phyrexian Swarmlord", "Toph, Earthbending Master", "Vishgraz, the Doomhive", "Vraska's Fall")
GAIN = card("Test Lesson", "{W}", "Instant", "You get two experience counters.")
POISON = card("Test Dart", "{B}", "Instant", "Target player gets two poison counters.")
VETERAN = card("Test Veteran", "{2}", "Creature — Human", "~ gets +1/+1 for each experience counter you have.", 1, 1)
FIEND = card("Test Fiend", "{2}", "Creature — Horror", "~ gets +1/+1 for each poison counter your opponents have.", 1, 1)


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


def cast(g, p, c, targets=None):
    effects = list(c.spell_effects)
    targets = g.auto_targets(p, effects, None) if targets is None else targets
    g.stack.append(StackItem(p, effects, targets, card=c, name=c.name))
    g.resolve_top()
    g.settle()
    return targets


class Parse(unittest.TestCase):
    def test_shapes(self):
        for c in (GAIN, VETERAN, FIEND):
            self.assertEqual(c.unsupported, [], c.name)
        inner = GAIN.spell_effects[0].data["effects"][0]
        self.assertEqual((inner.kind, inner.amount, inner.data["counter"]), ("player_counter", 2, "experience"))

    def test_rad_counters_are_not_read(self):
        # rad counters have a turn-based rule the engine doesn't have: giving them would be a no-op counted full
        self.assertTrue(card("Test Rads", "{B}", "Sorcery", "Target player gets four rad counters.").unsupported)


class Resolve(unittest.TestCase):
    def test_experience_feeds_the_pump(self):
        g, a, b = game()
        vet = g.enter_battlefield(a, VETERAN)
        self.assertEqual(vet.power, 1)
        cast(g, a, GAIN, [None])
        self.assertEqual(a.counters.get("experience"), 2)
        self.assertEqual(vet.power, 3)

    def test_opponents_poison_feeds_the_pump_and_ai_aims_poison_at_them(self):
        g, a, b = game()
        fiend = g.enter_battlefield(a, FIEND)
        targets = cast(g, a, POISON)
        self.assertIs(targets[0], b)
        self.assertEqual((b.counters.get("poison"), a.counters.get("poison", 0)), (2, 0))
        self.assertEqual(fiend.power, 3)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in FULL:
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)

    def test_vraskas_fall_poisons_each_opponent(self):
        g, a, b = game()
        theirs = g.enter_battlefield(b, card("Bear", "{1}", "Creature — Bear", "", 2, 2))
        cast(g, a, self.db.get("Vraska's Fall"), [None])
        self.assertNotIn(theirs, b.battlefield)
        self.assertEqual((b.counters.get("poison"), a.counters.get("poison", 0)), (1, 0))


if __name__ == "__main__":
    unittest.main()
