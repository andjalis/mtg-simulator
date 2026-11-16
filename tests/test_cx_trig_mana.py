"""Triggered mana abilities on tapping for mana (mtgsim/cx_trig_mana.py, #860 item 6). They resolve at once, inside
the payment that tapped the source (CR 605.1b, 605.4a): the extra mana pays the same cost."""
import os
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.cx_trig_mana import parse
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND

HAVE_DB = os.path.exists("mtgsim/data/cards.sqlite3")
DB = CardDB() if HAVE_DB else None


class Lines(unittest.TestCase):
    def test_parse(self):
        r = parse("Whenever a Forest is tapped for mana, its controller adds an additional {G}.")
        self.assertEqual((r["scope"], r["alts"], r["extra"]), ("all", [("Forest",)], frozenset("G")))
        r = parse("Whenever you tap a permanent for {C}, add an additional {C}.")
        self.assertEqual((r["scope"], r["need"]), ("you", "C"))
        r = parse("Whenever you tap a land for mana while you're the monarch, add an additional one mana of any color.")
        self.assertTrue(r["monarch"])
        self.assertEqual(parse("Whenever you tap a nonland permanent for mana, add one mana of any type that "
                               "permanent produced.")["extra"], "same")
        self.assertEqual(parse("Whenever enchanted Forest is tapped for mana, its controller adds an additional one "
                               "mana of the chosen color.")["scope"], "host")

    def test_refusals(self):
        for line in ("Whenever enchanted land is tapped for mana, its controller adds an additional {G}.",  # batch1's
                     "Whenever enchanted land is tapped for mana, its controller adds an additional {G} for each Elf "
                     "on the battlefield.",
                     "Whenever a land is tapped for mana, return it to its owner's hand.",
                     "Whenever a Forest is tapped for mana, its controller adds an additional one mana of that color.",
                     "Whenever you tap a frobnicator for mana, add an additional {G}.",
                     "Whenever you tap a permanent for {C}, add one mana of any type that permanent produced."):
            self.assertIsNone(parse(line), line)


@unittest.skipUnless(HAVE_DB, "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        for n in ("Utopia Sprawl", "Gauntlet of Power", "Gauntlet of Might", "Vernal Bloom", "Leyline of Abundance",
                  "Badgermole Cub", "Forsaken Monument", "Kinnan, Bonder Prodigy", "Groundchuck & Dirtbag",
                  "Roxanne, Starfall Savant", "Regal Behemoth", "Wild Growth"):
            self.assertEqual(DB.get(n).unsupported, [], n)


@unittest.skipUnless(HAVE_DB, "card database not built")
class Payments(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step, self.game.active_idx = 3, "main1", 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def put(self, who, name):
        perm = self.game.enter_battlefield(who, DB.get(name))
        perm.sick = False
        self.game.settle()
        return perm

    def test_leyline_doubles_a_mana_creature_in_the_same_payment(self):
        elves = self.put(self.a, "Llanowar Elves")
        self.assertFalse(self.game.can_pay(self.a, {"G": 2}))
        self.put(self.a, "Leyline of Abundance")
        self.assertTrue(self.game.can_pay(self.a, {"G": 2}))
        self.assertEqual(self.game.pay(self.a, {"G": 2}), [elves])      # one tap, two mana
        self.assertTrue(elves.tapped)
        self.assertFalse(self.game.can_pay(self.a, {"G": 1}))

    def test_leyline_ignores_lands_and_the_opponents_creatures(self):
        self.put(self.a, "Forest")
        self.put(self.b, "Llanowar Elves")
        self.put(self.a, "Leyline of Abundance")
        self.assertFalse(self.game.can_pay(self.a, {"G": 2}))
        self.assertFalse(self.game.can_pay(self.b, {"G": 2}))

    def test_vernal_bloom_is_symmetric(self):
        self.put(self.a, "Vernal Bloom")
        self.put(self.b, "Forest")
        self.put(self.b, "Island")
        self.assertTrue(self.game.can_pay(self.b, {"G": 2, "U": 1}))    # "its controller adds"
        self.assertFalse(self.game.can_pay(self.b, {"U": 2}))

    def test_utopia_sprawl_chosen_color(self):
        forest = self.put(self.a, "Forest")
        self.game._aura_host = forest
        sprawl = self.put(self.a, "Utopia Sprawl")
        self.game._aura_host = None
        self.assertIn(sprawl, forest.auras)
        color = sprawl.chosen_color
        self.assertIn(color, "WUBRG")
        self.assertTrue(self.game.can_pay(self.a, {"G": 1, color: 1} if color != "G" else {"G": 2}))
        self.assertFalse(self.game.can_pay(self.a, {"generic": 3}))

    def test_gauntlet_of_power_needs_the_chosen_color(self):
        gauntlet = self.put(self.a, "Gauntlet of Power")
        gauntlet.chosen_color = "R"
        self.assertNotIn(gauntlet, self.game.mana_sources(self.a))      # no mana of its own
        self.put(self.b, "Mountain")
        self.put(self.b, "Island")
        self.assertTrue(self.game.can_pay(self.b, {"R": 2, "U": 1}))    # the opponent's basic Mountain too
        self.assertFalse(self.game.can_pay(self.b, {"U": 2}))           # Island: not the chosen colour

    def test_forsaken_monument_colorless_sources_only(self):
        self.put(self.a, "Forsaken Monument")
        self.put(self.a, "Mind Stone")
        self.put(self.a, "Forest")
        self.assertTrue(self.game.can_pay(self.a, {"C": 2, "G": 1}))
        self.assertFalse(self.game.can_pay(self.a, {"G": 2}))

    def test_regal_behemoth_only_while_monarch(self):
        self.put(self.a, "Regal Behemoth")
        self.put(self.a, "Forest")
        self.game.monarch = self.b
        self.assertFalse(self.game.can_pay(self.a, {"generic": 2}))
        self.game.monarch = self.a
        self.assertTrue(self.game.can_pay(self.a, {"G": 1, "U": 1}))

    def test_kinnan_nonland_sources_same_type(self):
        self.put(self.a, "Kinnan, Bonder Prodigy")
        self.put(self.a, "Llanowar Elves")
        self.put(self.a, "Island")
        self.assertTrue(self.game.can_pay(self.a, {"G": 2, "U": 1}))
        self.assertFalse(self.game.can_pay(self.a, {"U": 2}))

    def test_heuristic_ai_casts_with_the_extra_mana(self):
        from mtgsim.ai import HeuristicAI
        a = Player("a", [], HeuristicAI())
        b = Player("b", [], HeuristicAI())
        game = Game(a, b, random.Random(1))
        game.turn, game.step, game.active_idx = 3, "main1", 0
        a.library, b.library = [ISLAND] * 10, [ISLAND] * 10
        for name in ("Llanowar Elves", "Leyline of Abundance"):
            perm = game.enter_battlefield(a, DB.get(name))
            perm.sick = False
        game.settle()
        a.hand = [DB.get("Grizzly Bears")]
        game.main_phase(a) if hasattr(game, "main_phase") else game.ai_main(a)
        self.assertTrue(any(x.card.name == "Grizzly Bears" for x in a.battlefield))


if __name__ == "__main__":
    unittest.main()
