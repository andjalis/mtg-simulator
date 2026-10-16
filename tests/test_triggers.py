"""New trigger events: beginning of combat, second draw / second spell each turn, mana value N or greater,
"enters or dies". Card text is written out."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, ISLAND, SHOCK, card

DRILL = card("Drill Sergeant", "{1}{W}", "Creature — Human", (
    "At the beginning of combat on your turn, put a +1/+1 counter on ~."), 1, 1)
SECOND = card("Quick Study", "{1}{U}", "Creature — Wizard", (
    "Whenever you draw your second card each turn, put a +1/+1 counter on ~."), 1, 1)
CASTER = card("Spell Student", "{1}{R}", "Creature — Wizard", (
    "Whenever you cast your second spell each turn, put a +1/+1 counter on ~."), 1, 1)
BIGCAST = card("Big Spender", "{2}{R}", "Creature — Wizard", (
    "Whenever you cast a spell with mana value 3 or greater, put a +1/+1 counter on ~."), 1, 1)
BOTH = card("Twice Blessed", "{2}{W}", "Creature — Angel", "When ~ enters or dies, you gain 2 life.", 2, 2)


class TriggerTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c):
        p = Permanent(c, self.a)
        p.sick = False
        self.a.battlefield.append(p)
        return p

    def test_templates_match(self):
        for c in (DRILL, SECOND, CASTER, BIGCAST, BOTH):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])

    def test_beginning_of_combat(self):
        d = self.perm(DRILL)
        self.game.combat(self.a, self.b)
        self.assertEqual(d.counters.get("+1/+1"), 1)

    def test_second_draw_each_turn(self):
        s = self.perm(SECOND)
        self.game.draw(self.a)
        self.game.settle()
        self.assertFalse(s.counters)
        self.game.draw(self.a)
        self.game.settle()
        self.assertEqual(s.counters.get("+1/+1"), 1)
        self.game.draw(self.a)
        self.game.settle()
        self.assertEqual(s.counters.get("+1/+1"), 1)

    def test_second_spell_each_turn(self):
        s = self.perm(CASTER)
        for _ in range(3):
            self.perm(ISLAND)
        self.a.hand = [SHOCK, SHOCK]
        for _ in range(2):
            self.perm(card("Mountain", "", "Basic Land — Mountain", "{T}: Add {R}."))
        self.game.cast(self.a, SHOCK, [self.b])
        self.assertFalse(s.counters)
        self.game.cast(self.a, SHOCK, [self.b])
        self.assertEqual(s.counters.get("+1/+1"), 1)

    def test_enters_or_dies(self):
        self.game.enter_battlefield(self.a, BOTH)
        self.game.settle()
        self.assertEqual(self.a.life, 22)
        perm = [x for x in self.a.battlefield if x.card is BOTH][0]
        self.game.destroy(perm)
        self.game.settle()
        self.assertEqual(self.a.life, 24)


if __name__ == "__main__":
    unittest.main()
