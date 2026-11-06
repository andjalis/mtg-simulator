"""cx_mech: Undaunted, Escalate, and Buyback paid with a sacrifice or discard."""
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, BEAR


class Costs(unittest.TestCase):
    def setUp(self):
        self.db = CardDB()
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def lands(self, *names):
        for n in names:
            self.game.enter_battlefield(self.a, self.db.get(n))
        self.game.settle()

    def options(self, card, prefix):
        return [v for v in self.game.spell_options(self.a) if v.name.startswith(prefix)]

    def test_parse_clean(self):
        for n in ("Coastal Breach", "Borrowed Grace", "Constant Mists", "Pegasus Stampede", "Demonic Collusion",
                  "Forbid"):
            self.assertEqual(self.db.get(n).unsupported, [], n)

    def test_undaunted_costs_one_less_per_opponent(self):
        card = self.db.get("Coastal Breach")
        self.assertEqual(self.game.cost_of(self.a, card)["generic"], card.mana_cost["generic"] - 1)

    def test_escalate_pays_per_extra_mode(self):
        card = self.db.get("Borrowed Grace")
        mine = self.game.enter_battlefield(self.a, BEAR)
        self.game.settle()
        self.a.hand = [card]
        self.lands("Plains", "Plains", "Plains", "Plains", "Plains")
        base_pt = (mine.power, mine.toughness)
        self.assertTrue(self.game.cast(self.a, next(v for v in self.game.spell_options(self.a)
                                                    if v.name.endswith("(escalate_1)"))))
        self.game.settle()
        self.assertEqual((mine.power, mine.toughness), (base_pt[0] + 2, base_pt[1] + 2))

    def test_plain_cast_chooses_one_mode(self):
        card = self.db.get("Borrowed Grace")
        mine = self.game.enter_battlefield(self.a, BEAR)
        self.game.settle()
        self.a.hand = [card]
        self.lands("Plains", "Plains", "Plains")
        base_pt = (mine.power, mine.toughness)
        self.assertTrue(self.game.cast(self.a, card))
        self.game.settle()
        self.assertEqual(mine.power + mine.toughness, sum(base_pt) + 2)

    def test_buyback_sacrifice_a_land_returns_the_card(self):
        card = self.db.get("Pegasus Stampede")
        self.a.hand = [card]
        self.lands("Plains", "Plains", "Plains")
        v = self.options(card, "Pegasus Stampede (buyback)")
        self.assertEqual(len(v), 1)
        self.assertTrue(self.game.cast(self.a, v[0]))
        self.game.settle()
        self.assertIn(card, self.a.hand)
        self.assertEqual(sum(x.card.is_land for x in self.a.battlefield), 2)
        self.assertTrue(any(x.card.is_token for x in self.a.battlefield))

    def test_buyback_discard_two_cards(self):
        card = self.db.get("Demonic Collusion")
        self.a.hand = [card, ISLAND, ISLAND, ISLAND]
        self.lands("Swamp", "Swamp", "Swamp", "Swamp", "Swamp")
        v = self.options(card, "Demonic Collusion (buyback)")
        self.assertEqual(len(v), 1)
        self.assertTrue(self.game.cast(self.a, v[0]))
        self.game.settle()
        self.assertIn(card, self.a.hand)
        self.assertEqual(len(self.a.graveyard), 2)


if __name__ == "__main__":
    unittest.main()
