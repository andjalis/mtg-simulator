"""Granted flashback, "as though it had flash if you pay {N} more", and Peat Bog-style depletion lands."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Permanent, Player

DB = CardDB(offline=True)


class FlashFixture(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.step = "main1"
        for p in (self.a, self.b):
            p.library = [DB.get("Island")] * 20

    def perm(self, name, owner=None):
        p = Permanent(DB.get(name), owner or self.a)
        p.sick = False
        p.tapped = False
        (owner or self.a).battlefield.append(p)
        return p


class Parsing(unittest.TestCase):
    def test_cards_fully_parse(self):
        from mtgsim.coverage import card_coverage
        for name in ("Rout", "Ghitu Fire", "Past in Flames", "Backdraft Hellkite", "Peat Bog", "Hickory Woodlot",
                     "Saprazzan Skerry", "Deep Analysis", "Acorn Harvest", "Lava Dart"):
            self.assertEqual(card_coverage(DB.get(name)).ignored, [], name)

    def test_flash_tax_cost(self):
        (alt,) = [a for a in DB.get("Rout").alt_costs if a.kind == "flash_tax"]
        self.assertEqual(alt.cost, {"generic": 2})


class LifeFlashback(FlashFixture):
    def test_pay_life_flashback_parses_and_costs_life(self):
        deep = DB.get("Deep Analysis")
        (fb,) = [a for a in deep.alt_costs if a.kind == "flashback"]
        self.assertEqual((fb.cost, fb.life), ({"generic": 1, "U": 1}, 3))
        for _ in range(2):
            self.perm("Island")
        self.a.graveyard = [deep]
        flash = [c for c in self.game.spell_options(self.a) if c.name == "Deep Analysis (flashback)"]
        self.assertEqual(len(flash), 1)
        self.assertTrue(self.game.cast(self.a, flash[0]))
        self.assertEqual(self.a.life, 17)


class OtherFlashbackCosts(FlashFixture):
    def test_lava_dart_sacrifices_a_mountain(self):
        dart = DB.get("Lava Dart")
        mountain = self.perm("Mountain")
        self.a.graveyard = [dart]
        opts = [c for c in self.game.spell_options(self.a) if c.name == "Lava Dart (flashback)"]
        self.assertEqual(len(opts), 1)
        self.assertTrue(self.game.cast(self.a, opts[0]))
        self.assertNotIn(mountain, self.a.battlefield)

    def test_lier_gives_every_graveyard_spell_flashback(self):
        self.perm("Lier, Disciple of the Drowned")
        for _ in range(3):
            self.perm("Mountain")
        bolt = DB.get("Lightning Bolt")
        self.a.graveyard = [bolt]
        names = [c.name for c in self.game.spell_options(self.a)]
        self.assertIn("Lightning Bolt (flashback)", names)


class Behaviour(FlashFixture):
    def test_rout_gains_flash_for_two_more(self):
        for _ in range(5):
            self.perm("Plains")
        rout = DB.get("Rout")
        self.a.hand = [rout]
        self.game.active_idx = 1          # not our turn: only the taxed copy can be cast
        opts = [c for c in self.game.spell_options(self.a) if c.name.startswith("Rout")]
        self.assertEqual([c.mana_cost for c in opts if c.instant_speed], [{"generic": 5, "W": 2}])

    def test_peat_bog_two_mana_then_sacrificed(self):
        bog = self.perm("Peat Bog")
        self.assertEqual(bog.card.mana_amount, 2)
        bog.counters["depletion"] = 2
        self.assertIsNotNone(self.game.pay(self.a, {"B": 2}))
        self.assertIn(bog, self.a.battlefield)
        bog.tapped = False
        self.game.pay(self.a, {"B": 2})
        self.assertNotIn(bog, self.a.battlefield)

    def test_past_in_flames_grants_every_spell(self):
        bolt, lore = DB.get("Lightning Bolt"), DB.get("Ancestral Recall")
        self.a.graveyard = [bolt, lore]
        eff = DB.get("Past in Flames").spell_effects[0]
        self.game.resolve(self.a, eff, None, None)
        self.assertCountEqual(self.a.granted_fb, [bolt, lore])


if __name__ == "__main__":
    unittest.main()
