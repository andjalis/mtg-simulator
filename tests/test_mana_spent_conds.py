"""#324: mana-spent conditions. A trailing "<effect> if {G} was spent to cast ~" (and the paired
"A if {R} ... and B if {G} ..." form, with the verb left out of the second half) is read as a leading
condition; "at least three mana of the same color", "two or more colors of mana", "{U}{B} was spent",
and "~ enters with ... unless ..." / "if it wasn't cast or no mana was spent to cast it" conditions."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_templates import BEAR, DRAGON, ISLAND, MOUNTAIN, PLAINS, card

FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")


class ManaSpentConditions(unittest.TestCase):
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

    def lands(self, *cards):
        for c in cards:
            c = self.real("Wastes") if c == "Wastes" else c
            self.perm(c, self.a)

    def cast(self, c, targets=None):
        # a hybrid spell with spent-colour effects is cast as one variant per colour: the payable one
        self.a.hand = [c]
        options = [v for v in self.g._hand_options(self.a, c) if self.g.spell_payable(self.a, v)]
        self.assertTrue(options)
        self.assertTrue(self.g.cast(self.a, options[0], targets))
        self.g.settle()

    # parser
    def test_real_cards_are_full(self):
        for name in ("Firespout", "Repel Intruders", "Torrent of Souls", "Invert the Skies", "Unnerving Assault",
                     "Batwing Brume", "Dawnglow Infusion", "Henge Walker", "Clockwork Servant", "Steel Exemplar",
                     "Freestrider Commando", "Mythos of Brokkos", "Moonhold"):
            with self.subTest(card=name):
                self.assertEqual(self.real(name).unsupported, [])

    def test_trailing_condition_parses_as_leading(self):
        effects, bad = _parse_effects("You gain 3 life if {G} was spent to cast ~.")
        self.assertFalse(bad)
        self.assertEqual([(e.kind, e.cond) for e in effects], [("gain_life", 'lib:["spent_color","G"]')])

    def test_near_misses_refused(self):
        for text in (
            "You gain 3 life if {G} was spent to cast another spell.",
            "Destroy target creature if it's a creature or if {G}{W} was spent to cast ~.",
        ):
            with self.subTest(text=text):
                effects, bad = _parse_effects(text)
                self.assertTrue(bad, effects)

    def test_wasnt_cast_on_a_trigger_is_not_the_source(self):
        # "if it wasn't cast" on another creature's entry names that creature: left unmatched as on main
        self.assertTrue(self.real("Preston, the Vanisher").unsupported)

    # game: colours of the payment decide each half
    def test_firespout_red_hits_only_nonflyers(self):
        bear, dragon = self.perm(BEAR, self.b), self.perm(DRAGON, self.b)
        self.lands(MOUNTAIN, MOUNTAIN, MOUNTAIN)
        self.cast(self.real("Firespout"))
        self.assertNotIn(bear, self.b.battlefield)
        self.assertIn(dragon, self.b.battlefield)

    def test_firespout_green_hits_only_flyers(self):
        bear, dragon = self.perm(BEAR, self.b), self.perm(DRAGON, self.b)
        self.lands(FOREST, FOREST, FOREST)
        self.cast(self.real("Firespout"))
        self.assertIn(bear, self.b.battlefield)
        self.assertNotIn(dragon, self.b.battlefield)

    def test_repel_intruders_white_only_makes_tokens(self):
        self.lands(PLAINS, PLAINS, PLAINS, PLAINS)
        self.cast(self.real("Repel Intruders"))
        self.assertEqual(len([x for x in self.a.creatures if x.card.is_token]), 2)

    def test_dawnglow_both_colours_gain_twice(self):
        dawn = self.real("Dawnglow Infusion")
        item = StackItem(self.a, dawn.spell_effects, [None] * len(dawn.spell_effects), card=dawn)
        item.x, item.mana_colors = 2, {"G", "W"}
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertEqual(self.a.life, 24)
        item = StackItem(self.a, dawn.spell_effects, [None] * len(dawn.spell_effects), card=dawn)
        item.x, item.mana_colors = 2, {"G"}
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertEqual(self.a.life, 26)

    # entering permanents
    def test_henge_walker_same_colour(self):
        walker = self.real("Henge Walker")
        self.lands(MOUNTAIN, MOUNTAIN, MOUNTAIN)
        self.cast(walker)
        perm = [x for x in self.a.creatures if x.card.name == walker.name][0]
        self.assertEqual(perm.counters.get("+1/+1", 0), 1)

    def test_henge_walker_mixed_colours(self):
        walker = self.real("Henge Walker")
        self.lands(MOUNTAIN, FOREST, PLAINS)
        self.cast(walker)
        perm = [x for x in self.a.creatures if x.card.name == walker.name][0]
        self.assertEqual(perm.counters.get("+1/+1", 0), 0)

    def test_steel_exemplar_colourless_gets_counters(self):
        ex = self.real("Steel Exemplar")
        self.lands("Wastes", "Wastes", "Wastes", "Wastes", "Wastes")
        self.cast(ex)
        perm = [x for x in self.a.creatures if x.card.name == ex.name][0]
        self.assertEqual(perm.counters.get("+1/+1", 0), 2)

    def test_steel_exemplar_two_colours_no_counters(self):
        ex = self.real("Steel Exemplar")
        self.lands(MOUNTAIN, FOREST, "Wastes", "Wastes", "Wastes")
        self.cast(ex)
        perm = [x for x in self.a.creatures if x.card.name == ex.name][0]
        self.assertEqual(perm.counters.get("+1/+1", 0), 0)

    def test_freestrider_not_cast_gets_counters_cast_does_not(self):
        c = self.real("Freestrider Commando")
        put = self.g.enter_battlefield(self.a, c)
        self.g.settle()
        self.assertEqual(put.counters.get("+1/+1", 0), 2)
        self.lands(FOREST, FOREST, FOREST)
        self.cast(c)
        cast = [x for x in self.a.creatures if x is not put][0]
        self.assertEqual(cast.counters.get("+1/+1", 0), 0)


if __name__ == "__main__":
    unittest.main()
