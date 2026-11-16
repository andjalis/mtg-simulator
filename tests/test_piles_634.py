"""#634 PILES: separate into two piles, another player chooses; each player plays the split in their own interest,
and a face-down pile is judged without seeing its cards."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player, StackItem

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card

SWAMP = card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


class Parse(unittest.TestCase):
    def test_families(self):
        for name, family in (("Curator of Destinies", "libyou"), ("Riddles in the Dark", "libyou"),
                             ("Fortune's Favor", "libopp"), ("Atris, Oracle of Half-Truths", "libopp"),
                             ("Do or Die", "destroy"), ("Make an Example", "example"), ("Death or Glory", "glory")):
            c = db(name)
            effects = list(c.spell_effects) + [e for t in c.triggers for e in t.effects]
            self.assertTrue(c.fully_supported, name)
            self.assertIn(family, [e.data.get("family") for e in effects if e.kind == "piles"], name)

    def test_refusals(self):
        for text in (
                # the regeneration rider is part of the wording: without it, this isn't Do or Die's sentence set
                "Separate all creatures target player controls into two piles. Destroy all creatures in the pile of "
                "that player's choice.",
                # one card from the chosen pile, the rest on the bottom (Truth or Tale): not read
                "Reveal the top five cards of your library and separate them into two piles. An opponent chooses one "
                "of those piles. Put a card from the chosen pile into your hand, then put all other cards revealed "
                "this way on the bottom of your library in any order."):
            with self.subTest(text=text[:40]):
                self.assertTrue(_parse_effects(text)[1])


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class Game_(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def resolve(self, name, targets=()):
        c = db(name)
        effects = list(c.spell_effects)
        self.game.stack.append(StackItem(self.a, effects, list(targets) + [None] * (len(effects) - len(targets)),
                                         card=c, name=c.name))
        self.game.resolve_top()
        self.game.settle()

    def test_do_or_die_balanced_split(self):
        wurm, angel = self.game.enter_battlefield(self.b, db("Craw Wurm")), self.game.enter_battlefield(
            self.b, db("Serra Angel"))
        bears = [self.game.enter_battlefield(self.b, BEAR) for _ in range(2)]
        self.resolve("Do or Die", [self.b])
        # they lose the cheaper pile of my split: about half the value, never just one Bear
        lost = [x for x in [wurm, angel] + bears if x not in self.b.battlefield]
        self.assertGreaterEqual(len(lost), 2)
        self.assertTrue(wurm in lost or angel in lost)

    def test_make_an_example_i_take_the_bigger_pile(self):
        for name in ("Craw Wurm", "Serra Angel"):
            self.game.enter_battlefield(self.b, db(name))
        self.game.enter_battlefield(self.b, BEAR)
        self.resolve("Make an Example")
        self.assertEqual(len(self.b.creatures), 1)          # their split was {one} / {two}; I made them lose two

    def test_death_or_glory_returns_the_pile_they_leave(self):
        self.a.graveyard.extend([db("Craw Wurm"), db("Serra Angel"), BEAR, ISLAND])
        self.resolve("Death or Glory")
        back = [x.card.name for x in self.a.creatures]
        self.assertTrue(back)
        self.assertEqual(len(back) + sum(c.is_creature for c in self.a.exile), 3)
        self.assertIn(ISLAND, self.a.graveyard)

    def test_riddles_face_down_pile_is_judged_unseen(self):
        from mtgsim.piles import FACE_DOWN
        from mtgsim.ai import card_value
        top = [db("Divination"), db("Serra Angel"), ISLAND, db("Shock")]
        self.a.library = [ISLAND] * 5 + top
        self.resolve("Riddles in the Dark")
        to_hand = [c for c in self.a.hand]
        self.assertTrue(to_hand)
        self.assertEqual(len(to_hand) + sum(1 for c in self.a.graveyard if c.name != "Riddles in the Dark"), 4)
        # the chooser's view of a split never depends on which cards are face down, only on how many
        from mtgsim.piles import seen
        up = [db("Shock")]
        self.assertEqual(seen([db("Serra Angel"), db("Craw Wurm")], up), seen([ISLAND, ISLAND], up))
        self.assertEqual(seen([ISLAND], up)[0], FACE_DOWN)
        self.assertEqual(seen([], up)[1], card_value(db("Shock")))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class AI(unittest.TestCase):
    def test_casts_do_or_die_at_the_opponent(self):
        a = Player("a", [], HeuristicAI())
        b = Player("b", [], HeuristicAI())
        game = Game(a, b, random.Random(0), log=True)
        game.turn, game.step = 3, "main1"
        a.library = b.library = [ISLAND] * 20
        for _ in range(2):
            game.enter_battlefield(a, SWAMP)
        mine = game.enter_battlefield(a, BEAR)
        for name in ("Craw Wurm", "Serra Angel"):
            game.enter_battlefield(b, db(name))
        a.hand = [db("Do or Die")]
        a.ai.main_phase(game, a)
        game.settle()
        self.assertEqual(a.hand, [])
        self.assertIn(mine, a.battlefield)
        self.assertEqual(len(b.creatures), 1)


if __name__ == "__main__":
    unittest.main()
