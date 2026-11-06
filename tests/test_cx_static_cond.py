"""Devotion and most-common-color conditions, and "~ isn't a creature" (mtgsim/cx_static_cond.py)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.cx_condlib import parse
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, card

MERFOLK = card("Test Merfolk", "{U}{U}", "Creature — Merfolk", "", 2, 2)
HYBRID = card("Test Hybrid", "{1}{W/B}{W/B}", "Creature — Spirit", "", 2, 2)
KNIGHT = card("Test Knight", "{B}", "Creature — Knight", "", 1, 1)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class StaticConditions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [BEAR] * 20, HeuristicAI())
        self.b = Player("b", [BEAR] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=False)
        for p in (self.a, self.b):
            p.library = list(p.deck)
        self.game.turn, self.game.step = 3, "main1"

    def put(self, c, who=None, full=True):
        if isinstance(c, str):
            c = self.db.get(c)
            if full:
                self.assertEqual(c.unsupported, [], c.name)
        return self.game.enter_battlefield(who or self.a, c)

    def test_parse_codes(self):
        self.assertTrue(parse("your devotion to blue is less than five"))
        self.assertTrue(parse("your devotion to white and black is less than seven"))
        self.assertTrue(parse("your devotion to red is three or greater"))
        self.assertTrue(parse("black is the most common color among all permanents or is tied for most common"))

    def test_god_needs_devotion(self):
        thassa = self.put("Thassa, God of the Sea")       # {2}{U}: devotion 1 by itself
        self.assertFalse(thassa.is_creature)
        self.assertNotIn(thassa, self.a.creatures)
        self.put(MERFOLK)
        self.assertFalse(thassa.is_creature)              # 1 + 2 = 3
        self.put(MERFOLK)
        self.assertTrue(thassa.is_creature)               # 5 is no longer less than five
        self.assertIn(thassa, self.a.creatures)

    def test_two_color_devotion_counts_hybrid_once(self):
        from mtgsim.cx_static_cond import devotion
        self.put(HYBRID)                                  # {W/B}{W/B}
        self.put(KNIGHT)
        self.assertEqual(devotion(self.a, ["W"]), 2)
        self.assertEqual(devotion(self.a, ["B"]), 3)
        self.assertEqual(devotion(self.a, ["B", "W"]), 3)

    def test_two_color_god(self):
        perm = self.put("Athreos, God of Passage", full=False)     # its dies trigger is another lane's line
        self.assertFalse(perm.is_creature)
        for _ in range(3):
            self.put(HYBRID)                              # 2 + 3 * 2 = 8
        self.assertTrue(perm.is_creature)

    def test_god_attacks_only_with_devotion(self):
        thassa = self.put("Thassa, God of the Sea")
        thassa.sick = False
        self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 20)                 # not a creature: it can't attack
        for _ in range(2):
            self.put(MERFOLK)
        self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 20 - thassa.power)

    def test_most_common_color(self):
        djinn = self.put("Goham Djinn")                   # gets -2/-2 while black is (tied for) most common
        base = (djinn.card.power, djinn.card.toughness)
        self.assertEqual((djinn.power, djinn.toughness), (base[0] - 2, base[1] - 2))   # it is the only black one
        self.put(BEAR, self.b)
        self.assertEqual((djinn.power, djinn.toughness), (base[0] - 2, base[1] - 2))   # tied
        self.put(BEAR, self.b)
        self.assertEqual((djinn.power, djinn.toughness), base)                       # green is most common


    def test_devotion_quantity(self):
        disciple = self.db.get("Nylea's Disciple")            # {2}{G}{G}: gain life equal to your devotion to green
        self.assertEqual(disciple.unsupported, [])
        self.put(BEAR)                                          # {1}{G}
        self.put(disciple)                                      # 2 more
        life = self.a.life
        for eff in disciple.etb_effects:
            self.game.resolve(self.a, eff, None, None)
        self.assertEqual(self.a.life, life + 3)

    def test_devotion_pump_and_draw(self):
        hydra = self.db.get("Aspect of Hydra")                  # target creature gets +X/+X, X = devotion to green
        self.assertEqual(hydra.unsupported, [])
        bear = self.put(BEAR)
        self.put(BEAR)
        self.game.resolve(self.a, hydra.spell_effects[0], bear, None)
        self.assertEqual(bear.power, 4)
        sang = self.db.get("Sanguimancy")                       # draw X, lose X life, X = devotion to black
        self.put(KNIGHT)
        hand, life = len(self.a.hand), self.a.life
        for eff in sang.spell_effects:
            self.game.resolve(self.a, eff, None, None)
        self.assertEqual((len(self.a.hand) - hand, life - self.a.life), (1, 1))

    def rebuff(self, devotion, lands):
        """Thassa's Rebuff over the opponent's Grizzly Bears spell: counter unless they pay {X}, X = devotion to blue."""
        rebuff = self.db.get("Thassa's Rebuff")
        self.assertEqual(rebuff.unsupported, [])
        forest = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
        for _ in range(lands):
            self.put(forest, self.b)
        for _ in range(devotion // 2):
            self.put(MERFOLK)                                   # {U}{U}
        from mtgsim.engine.state import StackItem
        spell = StackItem(self.b, list(BEAR.spell_effects), [], card=BEAR, name=BEAR.name, kind="spell")
        self.game.stack.append(spell)
        self.game.resolve(self.a, rebuff.spell_effects[0], spell, None)
        return spell in self.game.stack

    def test_rebuff_devotion_zero_keeps_spell(self):
        self.assertTrue(self.rebuff(0, 2))                     # pays {0}: the spell stays

    def test_rebuff_counters_when_they_cannot_pay(self):
        self.assertFalse(self.rebuff(4, 2))                    # owes {4} with two lands

    def test_rebuff_they_pay(self):
        self.assertTrue(self.rebuff(2, 4))                     # owes {2}, two lands left over

if __name__ == "__main__":
    unittest.main()
