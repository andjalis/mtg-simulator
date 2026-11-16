"""#317 slice 2: "if that spell's mana value / power is N or greater" and "if that spell has mana value N or greater"
read the spell a cast trigger fired on or a counterspell countered. Before, prev_is only looked at permanents, so
Prismari Pianist always made one token and Reject Imperfection never proliferated."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card


def game():
    a, b = Player("a", [ISLAND] * 10, HeuristicAI()), Player("b", [ISLAND] * 10, HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    for p in (a, b):
        p.library = [ISLAND] * 20
    return g, a, b


class Parse(unittest.TestCase):
    def test_conditions(self):
        for text in ("If that spell's power is 4 or greater, draw a card.",
                     "If that spell has mana value 5 or greater, draw a card.",
                     "If that spell's mana value is 5 or greater, draw a card."):
            effects, bad = _parse_effects(text)
            self.assertEqual(bad, [], text)
            self.assertIn("prev_is", effects[0].cond, text)


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class Cards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def cast_with(self, host, spell):
        g, a, b = game()
        for _ in range(8):
            g.enter_battlefield(a, ISLAND)
        perm = g.enter_battlefield(a, self.db.get(host))
        a.hand = [spell]
        self.assertTrue(g.cast(a, spell))
        g.settle()
        return g, a, perm

    def elementals(self, a):
        return sum(1 for x in a.battlefield if x.card.name.startswith("Elemental"))

    def test_pianist(self):
        g, a, _ = self.cast_with("Prismari Pianist", card("Big", "{4}{U}", "Sorcery", "Draw a card."))
        self.assertEqual(self.elementals(a), 3)
        g, a, _ = self.cast_with("Prismari Pianist", card("Small", "{1}{U}", "Sorcery", "Draw a card."))
        self.assertEqual(self.elementals(a), 1)

    def test_x_counts_in_the_mana_value(self):
        g, a, b = game()
        for _ in range(8):
            g.enter_battlefield(a, ISLAND)
        g.enter_battlefield(a, self.db.get("Prismari Pianist"))
        blast = card("Blast", "{X}{U}", "Sorcery", "Draw X cards.", cmc=1)      # X counts 0 off the stack
        a.hand = [blast]
        g.stack.append(StackItem(a, list(blast.spell_effects), [None], card=blast, name=blast.name))
        item = g.stack[-1]
        item.x = 4
        from mtgsim.cx_condlib import _spell_ok
        self.assertTrue(_spell_ok(item, {"mv": [">=", 5]}))
        item.x = 3
        self.assertFalse(_spell_ok(item, {"mv": [">=", 5]}))

    def test_apprentice(self):
        g, a, perm = self.cast_with("Prismari Apprentice", card("Big", "{4}{U}", "Instant", "Draw a card."))
        self.assertEqual(perm.counters.get("+1/+1", 0), 1)
        g, a, perm = self.cast_with("Prismari Apprentice", card("Small", "{U}", "Instant", "Draw a card."))
        self.assertEqual(perm.counters.get("+1/+1", 0), 0)

    def counter(self, name, cost):
        g, a, b = game()
        bear = g.enter_battlefield(a, card("Bear", "{1}{G}", "Creature — Bear", "", 2, 2))
        bear.counters["+1/+1"] = 1
        spell = card("Theirs", cost, "Sorcery", "Draw a card.")
        target = StackItem(b, list(spell.spell_effects), [None], card=spell, name=spell.name)
        g.stack.append(target)
        rider = self.db.get(name)
        g.stack.append(StackItem(a, list(rider.spell_effects), [target] + [None] * (len(rider.spell_effects) - 1),
                                 card=rider, name=rider.name))
        g.resolve_top()
        return bear

    def test_reject_imperfection(self):
        self.assertEqual(self.counter("Reject Imperfection", "{1}{U}").counters["+1/+1"], 2)      # proliferated
        self.assertEqual(self.counter("Reject Imperfection", "{3}{U}").counters["+1/+1"], 1)

    def test_full(self):
        for name in ("Prismari Pianist", "Prismari Apprentice", "Reject Imperfection", "Sound the Trumpets"):
            self.assertEqual(self.db.get(name).unsupported, [], name)


if __name__ == "__main__":
    unittest.main()
