"""Library search (mtgsim.search) and X spells (mtgsim.xspells). Card text is written out so no card DB is needed."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_templates import BEAR, DRAGON3, ISLAND, MOUNTAIN, card

RAMP = card("Test Ramp", "{2}{G}", "Sorcery", (
    "Search your library for up to two basic land cards, put them onto the battlefield tapped, then shuffle."))
SEEK = card("Test Seek", "{1}{G}", "Sorcery", (
    "You may search your library for a basic land card, reveal it, then shuffle and put that card on top."))
FETCH = card("Test Fetch", "{G}", "Sorcery", "Search your library for a Dragon card, reveal it, put it into your hand, then shuffle.")
BLAST = card("Test Blast", "{X}{R}", "Sorcery", "Test Blast deals X damage to target creature.")
DRAIN = card("Test Drain", "{X}{B}", "Sorcery", "Each opponent loses X life and you gain X life.")
HALT = card("Test Halt", "{X}{U}", "Instant", "Counter target spell unless its controller pays {X}.")


class SearchXTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.a.library = [ISLAND] * 10 + [DRAGON3]
        self.b.library = [ISLAND] * 10
        for _ in range(6):
            self.perm(MOUNTAIN, self.a)

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def test_templates_match(self):
        for c in (RAMP, SEEK, FETCH, BLAST, DRAIN, HALT):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])

    def test_search_two_basics_onto_the_battlefield_tapped(self):
        self.a.hand = [RAMP]
        lands = len(self.a.battlefield)
        self.game.cast(self.a, RAMP)       # needs {G}: Mountains can't pay, so it isn't cast
        self.assertEqual(len(self.a.battlefield), lands)
        from mtgsim.engine import StackItem
        self.game.resolve(self.a, RAMP.spell_effects[0], None, StackItem(self.a, RAMP.spell_effects, [None], card=RAMP))
        new = self.a.battlefield[lands:]
        self.assertEqual(len(new), 2)
        self.assertTrue(all(x.tapped for x in new))

    def test_search_to_top_and_to_hand(self):
        from mtgsim.engine import StackItem
        self.game.resolve(self.a, FETCH.spell_effects[0], None, StackItem(self.a, FETCH.spell_effects, [None], card=FETCH))
        self.assertEqual([c.name for c in self.a.hand], ["Big Dragon"])
        self.game.resolve(self.a, SEEK.spell_effects[0], None, StackItem(self.a, SEEK.spell_effects, [None], card=SEEK))
        self.assertEqual(self.a.library[-1].name, "Island")

    def test_x_damage_uses_all_the_mana(self):
        theirs = Permanent(DRAGON3, self.b)
        self.b.battlefield.append(theirs)
        self.a.hand = [BLAST]
        plan = self.a.ai.plan_spell(self.game, self.a, BLAST)
        self.assertIsNotNone(plan)
        self.game.cast(self.a, BLAST, plan[1])
        self.assertNotIn(theirs, self.b.battlefield)        # X = 5 kills a 3/3

    def test_x_drain(self):
        self.perm(MOUNTAIN, self.a)
        self.a.hand = [DRAIN]
        # {B} can't be paid by Mountains: resolve directly with X = 4
        from mtgsim.engine import StackItem
        item = StackItem(self.a, DRAIN.spell_effects, [None, None], card=DRAIN)
        item.x = 4
        for e in DRAIN.spell_effects:
            self.game.resolve(self.a, e, None, item)
        self.assertEqual((self.b.life, self.a.life), (16, 24))


if __name__ == "__main__":
    unittest.main()
