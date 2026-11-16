"""#397 slice: conditions in the positions the leading "If C, B." reader didn't see. "Then if C, B." and "B if C."
become the leading form when the condition library reads C and the result parses; conditions or effects naming a
referent ("it", "that player", ...) are refused. Also: irregular subtype plurals in conditions ("no Leeches")."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_templates import BEAR, ISLAND, card

BEAR_CARD = card("Test Bear", "{1}{G}", "Creature — Bear", "", 2, 2)


class ConditionPositions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    @classmethod
    def tearDownClass(cls):
        if cls.db._all is not None:
            cls.db._all.close()

    def real(self, name):
        if self.db._all is None:
            self.skipTest("card database not built")
        return self.db.get(name)

    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick = p.tapped = False
        owner.battlefield.append(p)
        return p

    def resolve(self, text, targets=None):
        effects, bad = _parse_effects(text)
        self.assertFalse(bad, bad)
        item = StackItem(self.a, effects, targets or [None] * len(effects))
        self.g.stack.append(item)
        self.g.resolve_top()
        self.g.settle()
        return effects

    def test_real_cards_are_full(self):
        for name in ("Beorn the Fierce", "Hour of Promise", "Court of Garenbrig", "Calming Verse", "Idle Thoughts",
                     "Sonar Strike", "Cindercone Smite", "Plan the Heist", "Banishing Slash", "Furgul, Quag Nurturer"):
            with self.subTest(card=name):
                self.assertEqual(self.real(name).unsupported, [])

    def test_shapes(self):
        for text, kinds in (("Draw a card. Then if you control three or more Bears, draw two cards.", ["draw", "draw"]),
                            ("Draw a card if you control an enchantment.", ["draw"]),
                            ("You gain 4 life if an opponent has more life than you.", ["gain_life"]),
                            # a compound condition the library reads (#556 refused it before this reader existed)
                            ("You gain 3 life if you control a Forest and {G} was spent to cast ~.", ["gain_life"])):
            with self.subTest(text=text):
                effects, bad = _parse_effects(text)
                self.assertFalse(bad)
                self.assertEqual([e.kind for e in effects], kinds)
                self.assertTrue(effects[-1].cond)

    def test_refusals(self):
        for text in ("Then draw a card if it has seven or more phyresis counters on it.",          # "it": a referent
                     "Put a +1/+1 counter on enchanted creature. Then if it has three or more +1/+1 counters on it, "
                     "sacrifice ~.",
                     "Return target nonland permanent to its owner's hand. Then that player discards a card if you "
                     "control a Zombie.",                                                            # "that player"
                     "~ attacks each combat if able.",
                     "Draw a card if you control a frobnicator."):                                   # unknown condition
            with self.subTest(text=text):
                effects, bad = _parse_effects(text)
                self.assertTrue(bad, effects)

    def test_then_if_reads_the_state_after_the_effects_before_it(self):
        # the first draw happens, then the condition is checked: no Bears yet, so no second draw
        self.resolve("Draw a card. Then if you control three or more Bears, draw two cards.")
        self.assertEqual(len(self.a.hand), 1)
        for _ in range(3):
            self.perm(BEAR_CARD, self.a)
        self.resolve("Draw a card. Then if you control three or more Bears, draw two cards.")
        self.assertEqual(len(self.a.hand), 4)

    def test_suffix_if(self):
        self.resolve("You gain 4 life if an opponent has more life than you.")
        self.assertEqual(self.a.life, 20)
        self.b.life = 25
        self.resolve("You gain 4 life if an opponent has more life than you.")
        self.assertEqual(self.a.life, 24)

    def test_sonar_strike_bat_rider(self):
        strike = self.real("Sonar Strike")
        target = self.perm(card("Big", "{4}", "Creature — Giant", "", 9, 9), self.b)
        target.tapped = True
        effects = list(strike.spell_effects)
        item = StackItem(self.a, effects, [target] + [None] * (len(effects) - 1), card=strike)
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertEqual((target.damage, self.a.life), (4, 20))
        self.perm(card("Test Bat", "{B}", "Creature — Bat", "Flying", 1, 1), self.a)
        item = StackItem(self.a, effects, [target] + [None] * (len(effects) - 1), card=strike)
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertEqual(self.a.life, 23)

    def test_irregular_plural_subtype(self):
        from mtgsim.cx_condlib import parse
        self.assertEqual(parse("you control no Leeches"), 'lib:["ctl","you",{"sub":["Leech"]},"==",0]')
        self.assertIn('"Elf"', parse("you control two or more Elves"))

    def test_furgul_otherwise(self):
        furgul = self.real("Furgul, Quag Nurturer")
        effects = list(furgul.triggers[0].effects)
        leech = self.perm(card("Test Leech", "{B}", "Creature — Leech", "", 1, 1), self.a)
        item = StackItem(self.a, effects, [None] * len(effects))
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertEqual(leech.counters.get("+1/+1", 0), 1)       # a Leech already: counters, no conjure
        self.assertEqual(len([x for x in self.a.creatures if x.card.name == "Slimy Dualleech"]), 0)


if __name__ == "__main__":
    unittest.main()
