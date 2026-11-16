"""#845: "each of up to N target ..." is 0..N targets. Several templates made every slot required, so the spell or
ability couldn't be cast or activated with fewer legal targets (Travel Preparations, Gird for Battle, Ajani's +1)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


def slots(c):
    effs = list(c.spell_effects) + [e for t in c.triggers for e in t.effects] + \
        [e for _, es in c.loyalty_abilities for e in es]
    return [bool(e.data.get("optional_target")) for e in effs if e.data.get("distinct")]


LAND = {c: card(n, types=f"Basic Land — {n}", text=f"({{T}}: Add {{{c}}}.)") for c, n in
        [("W", "Plains"), ("U", "Island"), ("R", "Mountain"), ("G", "Forest")]}


class Parse(unittest.TestCase):
    def test_up_to_slots_are_optional(self):
        for text in ("Put a +1/+1 counter on each of up to two target creatures.",
                     "Return up to two target creatures to their owners' hands.",
                     "Up to two target creatures can't block this turn.",
                     "Up to three target creatures each get +1/+1 until end of turn.",
                     "~ deals 1 damage to each of up to two target creatures."):
            with self.subTest(text=text):
                c = card("Test Spell", "{1}", "Sorcery", text)
                self.assertTrue(c.fully_supported)
                self.assertTrue(slots(c) and all(slots(c)), slots(c))

    def test_one_or_two_keeps_one_required(self):
        for text in ("One or two target creatures each get +2/+2 until end of turn.",
                     "One or two target creatures can't block this turn."):
            with self.subTest(text=text):
                self.assertEqual(slots(card("Test Spell", "{1}", "Instant", text)), [False, True])

    def test_exact_counts_stay_required(self):
        for text in ("Destroy two target creatures.", "~ deals 2 damage to each of two target creatures."):
            with self.subTest(text=text):
                s = slots(card("Test Spell", "{1}", "Sorcery", text))
                self.assertTrue(s and not any(s), s)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Play(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        self.game.active_idx = 0
        self.a.my_turn, self.b.my_turn = True, False
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def put(self, p, c, n=1):
        out = [self.game.enter_battlefield(p, db(c) if isinstance(c, str) else c) for _ in range(n)]
        self.game.settle()
        return out[0] if n == 1 else out

    def lands(self, spec):
        for ch in spec:
            self.put(self.a, LAND[ch])

    def cast(self, name):
        c = db(name)
        self.a.hand.append(c)
        ok = self.game.cast(self.a, c)
        self.game.settle()
        return ok

    def test_travel_preparations_with_one_creature(self):
        bear = self.put(self.a, BEAR)
        self.lands("GG")
        self.assertTrue(self.cast("Travel Preparations"))
        self.assertEqual(bear.counters.get("+1/+1"), 1)

    def test_gird_for_battle_with_one_creature(self):
        bear = self.put(self.a, BEAR)
        self.lands("W")
        self.assertTrue(self.cast("Gird for Battle"))
        self.assertEqual(bear.counters.get("+1/+1"), 1)

    def test_ajani_plus_one_with_one_creature(self):
        pw = self.put(self.a, "Ajani, Adversary of Tyrants")
        bear = self.put(self.a, BEAR)
        start = pw.loyalty
        self.assertTrue(self.game.activate_loyalty(self.a, pw, 0))
        self.game.settle()
        self.assertEqual((bear.counters.get("+1/+1"), pw.loyalty), (1, start + 1))

    def test_two_creatures_still_get_both(self):
        bears = self.put(self.a, BEAR, 2)
        self.lands("GG")
        self.assertTrue(self.cast("Travel Preparations"))
        self.assertEqual([b.counters.get("+1/+1") for b in bears], [1, 1])

    def test_dual_shot_with_one_enemy(self):
        foe = self.put(self.b, card("Test Elf", "{G}", "Creature — Elf", "", 1, 1))
        self.lands("R")
        self.assertTrue(self.cast("Dual Shot"))
        self.assertNotIn(foe, self.b.battlefield)

    def test_ai_bounces_only_the_opponents_creature(self):
        mine = self.put(self.a, BEAR)
        foe = self.put(self.b, db("Craw Wurm"))
        self.lands("UUUU")
        self.assertTrue(self.cast("Into the Void"))
        self.assertIn(mine, self.a.battlefield)                 # the empty second slot: not its own Bear
        self.assertNotIn(foe, self.b.battlefield)

    def test_one_or_two_needs_one(self):
        self.lands("UUUU")
        self.assertFalse(self.cast("Counterintelligence"))       # no creature at all: not castable
        self.a.hand.clear()
        foe = self.put(self.b, BEAR)
        self.assertTrue(self.cast("Counterintelligence"))
        self.assertNotIn(foe, self.b.battlefield)


if __name__ == "__main__":
    unittest.main()
