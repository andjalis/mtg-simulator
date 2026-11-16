"""#627: "<permanents> of the chosen type" reads the creature type chosen as the source entered
(permanent_templates selector key ``chosen_type``, mtgsim.cx_chosen_type)."""
import random
import unittest
from pathlib import Path

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from mtgsim.permanent_templates import selector
from tests.test_templates import ISLAND, MOUNTAIN, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("An-Zerrin Ruins", "Chronicle of Victory", "Cover of Darkness", "Doom Cannon", "Door of Destinies",
        "Engineered Plague", "Etchings of the Chosen", "Kindred Boon", "Plague Engineer", "Shared Triumph",
        "Steely Resolve")
GOB = card("Goblin", "{1}", "Creature — Goblin", "", 2, 2)
ELF = card("Elf", "{1}", "Creature — Elf", "", 2, 2)
TRIUMPH = card("Test Triumph", "{1}{W}", "Enchantment", "As ~ enters, choose a creature type.\nCreatures of the "
                                                        "chosen type get +1/+1.")
PLAGUE = card("Test Plague", "{2}{B}", "Enchantment", "As ~ enters, choose a creature type.\nAll creatures of the "
                                                      "chosen type get -1/-1.")


class Parse(unittest.TestCase):
    def test_selector(self):
        self.assertEqual(selector("creatures you control of the chosen type", plural=True),
                         {"chosen_type": True, "controller": "mine", "types_all": ["creature"]})
        self.assertEqual(selector("creatures of the chosen type your opponents control", plural=True),
                         {"chosen_type": True, "controller": "opp", "types_all": ["creature"]})

    def test_static_and_hostile_flag(self):
        self.assertEqual(TRIUMPH.unsupported, [])
        self.assertEqual(TRIUMPH.choose_type, "creature")
        self.assertFalse(TRIUMPH.advanced_rules.get("choose_opp_type"))
        self.assertEqual(PLAGUE.unsupported, [])
        self.assertTrue(PLAGUE.advanced_rules.get("choose_opp_type"))

    def test_choice_on_resolution_is_refused(self):
        c = card("Test Roar", "{2}{R}", "Sorcery", "Choose a creature type. ~ deals damage to any target equal to the "
                                                   "number of permanents you control of the chosen type.")
        self.assertTrue(any("no stored choice" in u for u in c.unsupported))
        c = card("Test Fear", "{B}", "Instant", "Choose a creature type. Creatures you control of the chosen type "
                                                "get +1/+0 until end of turn.")
        self.assertTrue(c.unsupported)


class Resolve(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [GOB] * 20, HeuristicAI()), Player("b", [ELF] * 20, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 3, "main1"
        self.a.library = self.b.library = [ISLAND] * 10
        self.gob = self.g.enter_battlefield(self.a, GOB)
        self.elf = self.g.enter_battlefield(self.b, ELF)
        self.their_gob = self.g.enter_battlefield(self.b, GOB)

    def test_anthem_names_your_own_type_and_reaches_every_one(self):
        src = self.g.enter_battlefield(self.a, TRIUMPH)
        self.g.settle()
        self.assertEqual(src.chosen_type, "Goblin")
        self.assertEqual((self.gob.power, self.their_gob.power, self.elf.power), (3, 3, 2))

    def test_hostile_card_names_the_opponents_type(self):
        src = self.g.enter_battlefield(self.a, PLAGUE)
        self.g.settle()
        self.assertEqual(src.chosen_type, "Elf")
        self.assertEqual((self.gob.power, self.elf.power), (2, 1))

    def test_no_choice_matches_nothing(self):
        from mtgsim.permanent_templates import matches
        self.assertFalse(matches(self.g, self.gob, {"chosen_type": True, "types_all": ["creature"]}, self.a, None))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def setUp(self):
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def game(self):
        a, b = Player("a", [GOB] * 20, HeuristicAI()), Player("b", [ELF] * 20, HeuristicAI())
        g = Game(a, b, random.Random(0), log=True)
        g.turn, g.step = 3, "main1"
        a.library = b.library = [ISLAND] * 10
        return g, a, b

    def test_full(self):
        from mtgsim.coverage import card_coverage
        for name in FULL:
            self.assertEqual(card_coverage(self.db.get(name)).status, "full", name)

    def test_an_zerrin_ruins_locks_the_opponents_type(self):
        g, a, b = self.game()
        elf, gob = g.enter_battlefield(b, ELF), g.enter_battlefield(b, GOB)
        ruins = g.enter_battlefield(a, self.db.get("An-Zerrin Ruins"))
        g.settle()
        elf.tapped = gob.tapped = True
        g.untap_step(b)
        self.assertEqual((ruins.chosen_type, elf.tapped, gob.tapped), ("Elf", True, False))

    def test_doom_cannon_sacrifices_only_the_chosen_type(self):
        g, a, b = self.game()
        elf = g.enter_battlefield(a, ELF)
        for _ in range(4):
            g.enter_battlefield(a, MOUNTAIN)
        cannon = g.enter_battlefield(a, self.db.get("Doom Cannon"))
        cannon.sick = False
        g.settle()
        self.assertFalse(g.activate_ability(a, cannon, 0))       # only an Elf to sacrifice
        gob = g.enter_battlefield(a, GOB)
        self.assertTrue(g.activate_ability(a, cannon, 0))
        g.settle()
        self.assertNotIn(gob, a.battlefield)
        self.assertIn(elf, a.battlefield)

    def test_kindred_boon_targets_only_the_chosen_type(self):
        g, a, b = self.game()
        gob, elf = g.enter_battlefield(a, GOB), g.enter_battlefield(a, ELF)
        boon = g.enter_battlefield(a, self.db.get("Kindred Boon"))
        g.settle()
        eff = boon.card.activated[0].effects[0]
        with g.targeting(boon):
            self.assertEqual([g.legal_target(a, eff, x) for x in (gob, elf)], [True, False])


if __name__ == "__main__":
    unittest.main()
