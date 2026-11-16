"""Threshold statics (#323): 'As long as there are seven or more cards in your graveyard, ~ has "<ability>"'."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND, card

DB = os.path.join(os.path.dirname(__file__), "..", "mtgsim", "data", "cards.sqlite3")


class Wordings(unittest.TestCase):
    def test_inner_abilities(self):
        c = card("X", "{1}", "Creature — Bear", "At the beginning of your upkeep, you may put another +1/+1 counter "
                 "on ~.", 1, 1)
        self.assertEqual(c.unsupported, [])
        self.assertEqual([e.kind for e in c.triggers[0].effects][-1], "p1_counters")
        c = card("X", "{1}", "Creature — Bear", "At the beginning of your end step, exile two cards from your "
                 "graveyard.", 1, 1)
        self.assertEqual((c.triggers[0].effects[0].kind, c.triggers[0].effects[0].amount), ("exile_own_gy_n", 2))


@unittest.skipUnless(os.path.exists(DB), "card database not built")
class RealCards(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in ("Pardic Arsonist", "Teroh's Vanguard", "Possessed Centaur", "Repentant Vampire",
                     "Stone-Tongue Basilisk", "Hunting Grounds", "Chlorophant", "Bloodcurdler"):
            with self.subTest(name):
                self.assertEqual(card_coverage(self.db.get(name)).status, "full")

    def granted(self, perm, event):
        return [t for t in perm.triggers if t.event == event]

    def test_chlorophant_only_with_threshold(self):
        plant = self.game.enter_battlefield(self.a, self.db.get("Chlorophant"))
        self.a.graveyard = [ISLAND] * 6
        self.assertEqual(len(self.granted(plant, "upkeep")), 1)         # its own upkeep counter only
        self.a.graveyard = [ISLAND] * 7
        ups = self.granted(plant, "upkeep")
        self.assertEqual(len(ups), 2)
        extra = ups[1:]
        before = plant.counters.get("+1/+1", 0)
        for e in extra[0].effects:
            if e.kind == "p1_counters":
                self.game.resolve(self.a, e, plant)
        self.assertEqual(plant.counters.get("+1/+1", 0), before + 1)

    def test_bloodcurdler_exiles_two_of_its_own_cards(self):
        bc = self.game.enter_battlefield(self.a, self.db.get("Bloodcurdler"))
        self.a.graveyard = [ISLAND] * 6 + [BEAR]
        p0 = bc.power
        self.assertEqual(p0, bc.card.power + 1)                          # +1/+1 with threshold
        end = [t for t in bc.triggers if t.event not in [x.event for x in bc.card.triggers]]
        self.assertEqual(len(end), 1)
        for e in end[0].effects:
            self.game.resolve(self.a, e, None)
        self.assertEqual(len(self.a.graveyard), 5)
        self.assertIn(BEAR, self.a.graveyard)                            # keeps the creature card
        self.assertEqual(len(self.a.exile), 2)
        self.assertEqual(bc.power, bc.card.power)                        # threshold lost


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(os.path.exists(DB), "card database not built")
class OptionalExile(unittest.TestCase):
    """"You may exile two cards from your graveyard. If you do / When you do, ...": all or nothing."""
    def setUp(self):
        RealCards.setUp(self)

    def run_trigger(self, name, gy):
        from mtgsim.engine import StackItem
        perm = self.game.enter_battlefield(self.a, self.db.get(name))
        self.game.stack.clear() if hasattr(self.game.stack, "clear") else None
        self.a.graveyard = list(gy)
        trig = next(t for t in perm.card.triggers if any(e.kind == "exile_own_gy_n" for e in t.effects))
        self.game.stack.append(StackItem(self.a, list(trig.effects), [None] * len(trig.effects), source=perm,
                                         name=name))
        self.game.resolve_top()
        return perm

    def test_aegis_sculptor_needs_two_cards(self):
        perm = self.run_trigger("Aegis Sculptor", [ISLAND])
        self.assertEqual((len(self.a.graveyard), perm.counters.get("+1/+1", 0)), (1, 0))
        perm = self.run_trigger("Aegis Sculptor", [ISLAND, ISLAND, ISLAND])
        self.assertEqual((len(self.a.graveyard), perm.counters.get("+1/+1", 0)), (1, 1))

    def test_young_necromancer_needs_two_cards(self):
        self.run_trigger("Young Necromancer", [BEAR])
        self.assertEqual(self.a.graveyard, [BEAR])           # nothing exiled, nothing returned
