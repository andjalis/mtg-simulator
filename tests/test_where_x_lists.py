"""#324 tail: compound "..., where X is <Q>" sentences. "A, B, and C" with a subject of its own in every part splits
into its parts (Together as One; also Intimidation Campaign, Lord of Tresserhorn), and "return up to X permanent
cards" singularises its noun when X is read as one (Uncle's Musings), so where-X scales every part."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_templates import BEAR, ISLAND, card


class WhereXLists(unittest.TestCase):
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

    def test_real_cards_are_full(self):
        for name in ("Together as One", "Uncle's Musings", "Intimidation Campaign", "Lord of Tresserhorn"):
            with self.subTest(card=name):
                self.assertEqual(self.real(name).unsupported, [])

    def test_list_splits_and_where_x_scales_every_part(self):
        effects, bad = _parse_effects("Target player draws X cards, ~ deals X damage to any target, and you gain X "
                                      "life, where X is the number of creatures you control.")
        self.assertFalse(bad)
        self.assertEqual([e.kind for e in effects], ["draw", "damage", "gain_life"])
        self.assertTrue(all(e.data.get("xq") for e in effects))

    def test_list_refusals(self):
        for text in ("Target player draws a card, discards a card, and loses 1 life.",   # parts share one subject
                     "You gain 1 life, foo the bar, and you draw a card.",                # a part that doesn't parse
                     "You gain 1 life, you draw a card."):                                # no final "and"
            with self.subTest(text=text):
                effects, bad = _parse_effects(text)
                self.assertTrue(bad, effects)

    def resolve(self, c, colours, targets=None):
        effects = list(c.spell_effects)
        item = StackItem(self.a, effects, targets or [None] * len(effects), card=c)
        item.mana_colors = set(colours)
        self.g.stack.append(item)
        self.g.resolve_top()
        self.g.settle()

    def test_together_as_one_three_colours(self):
        one = self.real("Together as One")
        self.resolve(one, "WUB", targets=[self.a, self.b, None])
        self.assertEqual((len(self.a.hand), self.b.life, self.a.life), (3, 17, 23))

    def test_uncles_musings_returns_up_to_converge(self):
        perms = [card(f"Relic {i}", "{1}", "Artifact", "") for i in range(4)]
        self.a.graveyard = list(perms)
        self.resolve(self.real("Uncle's Musings"), "WU")
        self.assertEqual(len(self.a.hand), 2)
        self.assertEqual(len(self.a.graveyard), 2)

    def test_intimidation_campaign_etb(self):
        c = self.real("Intimidation Campaign")
        self.g.enter_battlefield(self.a, c)
        self.g.settle()
        self.assertEqual((self.b.life, self.a.life, len(self.a.hand)), (19, 21, 1))

    def test_ai_aims_together_as_one(self):
        one = self.real("Together as One")
        with self.g.targeting(one):
            self.g.target_source = one
            draw_to = self.a.ai.choose_target(self.g, self.a, one.spell_effects[0], one)
            hit = self.a.ai.choose_target(self.g, self.a, one.spell_effects[1], one)
        self.assertIs(draw_to, self.a)
        self.assertIsNot(hit, self.a)
        self.assertFalse(isinstance(hit, Permanent) and hit.controller is self.a)


if __name__ == "__main__":
    unittest.main()
