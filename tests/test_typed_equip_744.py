"""#744: "Equip <type> {N}" beside a plain "Equip {M}" is a second, cheaper equip for that type, not a limit on every
equip. A card with only the typed equip keeps the restriction."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player

from tests.test_cx_grammar import DB_FILE
from tests.test_templates import BEAR, ISLAND, card

PIRATE = card("Test Pirate", "{1}{U}", "Creature — Human Pirate", "", 2, 2)
LEGEND = card("Test Legend", "{1}{W}", "Legendary Creature — Human Knight", "", 2, 2)


def db(name):
    from mtgsim.carddb import CardDB
    return CardDB(offline=True).get(name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class TypedEquip(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 3, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def equip(self, name, host, lands):
        for _ in range(lands):
            self.game.enter_battlefield(self.a, ISLAND)
        eq = self.game.enter_battlefield(self.a, db(name))
        creature = self.game.enter_battlefield(self.a, host)
        cost = self.game.equip_cost(eq, creature)
        ok = self.game.equip(self.a, eq, creature)
        self.game.settle()
        return ok, cost, creature

    def test_pirate_hat_plain_equip_on_any_creature(self):
        ok, cost, bear = self.equip("Pirate Hat", BEAR, 2)
        self.assertTrue(ok)
        self.assertEqual(cost.get("generic"), 2)
        self.assertEqual(bear.power, 3)

    def test_pirate_hat_typed_equip_is_cheaper(self):
        ok, cost, pirate = self.equip("Pirate Hat", PIRATE, 1)
        self.assertTrue(ok)
        self.assertEqual(cost.get("generic"), 1)

    def test_blackblade_legendary_discount(self):
        self.assertEqual(self.equip("Blackblade Reforged", LEGEND, 3)[1].get("generic"), 3)

    def test_parse(self):
        hat = db("Pirate Hat")
        self.assertEqual(hat.equip_cost, {"generic": 2})
        self.assertNotIn("equip_restriction", hat.advanced_rules)
        self.assertEqual(hat.advanced_rules["equip_typed"], ("Pirate", {"generic": 1}))


if __name__ == "__main__":
    unittest.main()
