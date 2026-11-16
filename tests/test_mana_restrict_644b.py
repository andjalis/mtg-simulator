"""#644: more restricted mana: "<Subtype> <card type> spell" (a Chandra planeswalker spell), two-word subtypes (Time
Lord), "a creature spell of the chosen type [or an ability of a creature source of the chosen type]", and "Spend only
mana produced by basic lands / creatures to cast this spell" (mtgsim.cx_mana_from). Enforced in payment; the AI
plans with it."""
import random
import unittest
from pathlib import Path

from mtgsim import cx_abil_mana as M
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Chandra's Embercat", "Gallifrey Council Chamber", "Imperiosaur", "Myr Superion", "Pillar of Origins",
        "Secluded Courtyard", "Unclaimed Territory")
TERRITORY = card("Test Territory", "", "Land", "As this land enters, choose a creature type.\n{T}: Add one mana of any "
                 "color. Spend this mana only to cast a creature spell of the chosen type.")
COURTYARD = card("Test Courtyard", "", "Land", "As this land enters, choose a creature type.\n{T}: Add one mana of any "
                 "color. Spend this mana only to cast a creature spell of the chosen type or activate an ability of a "
                 "creature source of the chosen type.")
SAUR = card("Test Saur", "{2}{G}{G}", "Creature — Dinosaur",
            "Spend only mana produced by basic lands to cast this spell.", 6, 6)
MYR = card("Test Superion", "{2}", "Artifact Creature — Myr", "Spend only mana produced by creatures to cast this spell.",
           5, 6)
ELF = card("Test Elf", "{1}{G}", "Creature — Elf", "{1}: You gain 1 life.", 2, 2)
GOBLIN = card("Test Goblin", "{1}{R}", "Creature — Goblin", "{1}: You gain 1 life.", 2, 2)
CHANDRA = card("Test Chandra", "{2}{R}", "Legendary Planeswalker — Chandra", "+1: You gain 1 life.")
JACE = card("Test Jace", "{2}{U}", "Legendary Planeswalker — Jace", "+1: You gain 1 life.")
FOREST = card("Forest", "", "Basic Land — Forest", "({T}: Add {G}.)")
GROVE = card("Test Grove", "", "Land", "{T}: Add {G}.")
DORK = card("Test Dork", "{G}", "Creature — Elf Druid", "{T}: Add {G}.", 1, 1)


def game(ai=Scripted):
    a, b = Player("a", [], ai()), Player("b", [], ai())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 2, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


def ready(g, p, *cards):
    out = []
    for c in cards:
        perm = g.enter_battlefield(p, c)
        perm.sick = False
        out.append(perm)
    return out


class Parse(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(M._spec(M.parse("to cast an elemental spell or a chandra planeswalker spell")),
                         {"s": ["s:elemental", "st:chandra/planeswalker"], "a": []})
        self.assertEqual(M._spec(M.parse("to cast a time lord or alien spell or activate an ability of a time lord or "
                                         "alien")), {"s": ["s:time lord", "s:alien"], "a": ["s:time lord", "s:alien"]})
        self.assertEqual((TERRITORY.mana_restriction, COURTYARD.mana_restriction), ("chosen_type", "chosen_type_abil"))
        self.assertEqual((SAUR.advanced_rules["mana_from"], MYR.advanced_rules["mana_from"]), ("basic_land", "creature"))
        for c in (TERRITORY, COURTYARD, SAUR, MYR):
            self.assertEqual(c.unsupported, [], c.name)

    def test_refusals(self):
        self.assertTrue(card("Test Rhox", "{2}", "Creature — Rhino", "Spend only mana produced by Treasures to cast "
                             "this spell.", 2, 2).unsupported)
        self.assertIsNone(M.parse("to cast a time lord spell from exile"))


class Pay(unittest.TestCase):
    def test_chandra_planeswalker(self):
        g, a, b = game()
        src = ready(g, a, card("Test Cat", "{2}", "Creature — Elemental Cat", "{T}: Add {R}. Spend this mana only to "
                                "cast an Elemental spell or a Chandra planeswalker spell.", 1, 1))[0]
        self.assertTrue(g.mana_allowed(src, CHANDRA))
        self.assertFalse(g.mana_allowed(src, JACE))

    def test_chosen_type(self):
        g, a, b = game()
        territory, courtyard = ready(g, a, TERRITORY, COURTYARD)
        elf, goblin = ready(g, a, ELF, GOBLIN)
        territory.chosen_type = courtyard.chosen_type = "Elf"
        self.assertTrue(g.mana_allowed(territory, ELF))
        self.assertFalse(g.mana_allowed(territory, GOBLIN))
        self.assertFalse(g.mana_allowed(territory, M.AbilityPayment(elf)))       # spells only
        self.assertTrue(g.mana_allowed(courtyard, M.AbilityPayment(elf)))       # and abilities of an Elf
        self.assertFalse(g.mana_allowed(courtyard, M.AbilityPayment(goblin)))
        self.assertTrue(g.mana_allowed(courtyard, ELF))

    def test_basic_lands_only(self):
        g, a, b = game()
        ready(g, a, FOREST, FOREST, FOREST, GROVE)
        a.hand = [SAUR]
        self.assertFalse(g.spell_payable(a, SAUR))            # the nonbasic land's mana can't help
        ready(g, a, FOREST)
        self.assertTrue(g.spell_payable(a, SAUR))

    def test_creatures_only(self):
        g, a, b = game()
        ready(g, a, FOREST, FOREST, DORK)
        a.hand = [MYR]
        self.assertFalse(g.spell_payable(a, MYR))
        ready(g, a, DORK)
        self.assertTrue(g.spell_payable(a, MYR))


class AI(unittest.TestCase):
    def test_casts_the_saur_only_from_basic_lands(self):
        g, a, b = game(HeuristicAI)
        ready(g, a, FOREST, FOREST, FOREST, GROVE)
        a.hand = [SAUR]
        a.ai.main_phase(g, a)
        self.assertEqual(a.hand, [SAUR])
        g2, a2, b2 = game(HeuristicAI)
        lands = ready(g2, a2, FOREST, FOREST, FOREST, FOREST, GROVE)
        a2.hand = [SAUR]
        a2.ai.main_phase(g2, a2)
        self.assertIn(SAUR, [x.card for x in a2.creatures])
        self.assertFalse(lands[-1].tapped)                    # the nonbasic land stays untapped

    def test_territory_mana_goes_to_the_chosen_type(self):
        g, a, b = game(HeuristicAI)
        territory, island = ready(g, a, TERRITORY, ISLAND)
        territory.chosen_type = "Elf"
        a.hand = [GOBLIN, ELF]
        a.ai.main_phase(g, a)
        self.assertIn(ELF, [x.card for x in a.creatures])
        self.assertIn(GOBLIN, a.hand)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in FULL:
            self.assertEqual(card_coverage(db.get(name)).status, "full", name)


if __name__ == "__main__":
    unittest.main()
