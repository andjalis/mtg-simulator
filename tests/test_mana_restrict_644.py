"""#644: more "Spend this mana only ..." wordings read by mtgsim.cx_abil_mana: the singular "activate an ability [of an
<X> source]", the reversed "to activate an ability or cast ...", "or to activate", and "<Subtype> creature spell".
The restriction is enforced in payment (Game.mana_allowed) and the AI only spends the mana where it may."""
import random
import unittest
from pathlib import Path

from mtgsim import cx_abil_mana as M
from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

DB_FILE = Path(__file__).resolve().parents[1] / "mtgsim" / "data" / "cards.sqlite3"

FULL = ("Ambulatory Reactor", "Automated Artificer", "Avengers Tower", "Base Camp", "Cargo Ship",
        "Guidelight Optimizer", "Haven of the Spirit Dragon", "Isolinear Processor", "Ixalli's Lorekeeper",
        "Jasmine Dragon Tea Shop", "Oaken Siren", "Osgood, Operation Double", "Primal Beyond", "Purple Dragon Punks",
        "Sage of the Unknowable")
SHIP = card("Test Ship", "{1}", "Artifact", "{T}: Add {C}. Spend this mana only to cast an artifact spell or activate "
                                            "an ability of an artifact source.")
ARTIFICER = card("Test Artificer", "{2}", "Artifact Creature — Construct",
                 "{T}: Add {C}. Spend this mana only to activate an ability or cast an artifact spell.", 1, 1)
HAVEN = card("Test Haven", "", "Land", "{T}: Add {C}{C}. Spend this mana only to cast a Dragon creature spell.")
DRAGON = card("Test Dragon", "{2}", "Creature — Dragon", "", 2, 2)
DRAGON_SPELL = card("Test Breath", "{2}", "Kindred Instant — Dragon", "You gain 1 life.")
RELIC = card("Test Relic", "{2}", "Artifact", "{1}: You gain 1 life.")
PUMP = card("Test Pump", "{1}", "Creature — Human", "{1}: You gain 1 life.", 1, 1)


def game(ai=Scripted):
    a, b = Player("a", [], ai()), Player("b", [], ai())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 2, "main1"
    a.library = b.library = [ISLAND] * 10
    return g, a, b


class Parse(unittest.TestCase):
    def test_wordings(self):
        for text, code in (
                ("to cast an artifact spell or activate an ability of an artifact source",
                 {"s": ["t:artifact"], "a": ["t:artifact"]}),
                ("to cast an artifact spell or activate an ability of an artifact", {"s": ["t:artifact"],
                                                                                     "a": ["t:artifact"]}),
                ("to activate an ability or cast an artifact spell", {"s": ["t:artifact"], "a": True}),
                ("to cast a colorless spell or to activate an ability", {"s": ["k:colorless"], "a": True}),
                ("to cast a hero spell or to activate an ability of a hero source", {"s": ["s:hero"],
                                                                                     "a": ["s:hero"]}),
                ("to cast a dragon creature spell", {"s": ["sc:dragon"], "a": []})):
            with self.subTest(text=text):
                self.assertEqual(M._spec(M.parse(text)), code)

    def test_refusals(self):
        for text in ("to cast a time lord or alien spell or activate an ability of a time lord or alien",
                     "to cast an elemental spell or a chandra planeswalker spell",
                     "to cast a creature spell of the chosen type",
                     "to cast a legendary creature spell", "to cast a nonland creature spell",
                     "to activate an ability of a creature you control",
                     "to cast spells from exile"):
            with self.subTest(text=text):
                self.assertIsNone(M.parse(text))

    def test_cards_parse(self):
        for c in (SHIP, ARTIFICER, HAVEN):
            self.assertEqual(c.unsupported, [], c.name)
            self.assertTrue(c.mana_restriction.startswith("pred:"), c.name)


class Pay(unittest.TestCase):
    def test_artifact_source_mana(self):
        g, a, b = game()
        ship = g.enter_battlefield(a, SHIP)
        relic = g.enter_battlefield(a, RELIC)
        pump = g.enter_battlefield(a, PUMP)
        for x in (ship, relic, pump):
            x.sick = False
        self.assertTrue(g.mana_allowed(ship, RELIC))
        self.assertFalse(g.mana_allowed(ship, BEAR))
        self.assertTrue(g.mana_allowed(ship, M.AbilityPayment(relic)))
        self.assertFalse(g.mana_allowed(ship, M.AbilityPayment(pump)))
        self.assertTrue(g.can_activate(a, relic, 0))           # the Ship's {C} pays the relic's {1}
        self.assertFalse(g.can_activate(a, pump, 0))           # but not a creature's ability
        self.assertTrue(g.activate_ability(a, relic, 0))
        g.settle()
        self.assertTrue(ship.tapped)
        self.assertEqual(a.life, 21)

    def test_any_ability_or_artifact_spell(self):
        g, a, b = game()
        art = g.enter_battlefield(a, ARTIFICER)
        pump = g.enter_battlefield(a, PUMP)
        for x in (art, pump):
            x.sick = False
        self.assertTrue(g.mana_allowed(art, M.AbilityPayment(pump)))
        self.assertTrue(g.mana_allowed(art, RELIC))
        self.assertFalse(g.mana_allowed(art, BEAR))
        a.hand = [BEAR]
        self.assertFalse(g.spell_payable(a, BEAR))

    def test_subtype_and_creature_both(self):
        g, a, b = game()
        haven = g.enter_battlefield(a, HAVEN)
        self.assertTrue(g.mana_allowed(haven, DRAGON))
        self.assertFalse(g.mana_allowed(haven, DRAGON_SPELL))  # a Dragon, but not a creature spell
        self.assertFalse(g.mana_allowed(haven, BEAR))          # a creature, but not a Dragon
        self.assertFalse(g.mana_allowed(haven, M.AbilityPayment(haven)))


class AI(unittest.TestCase):
    def test_spends_the_haven_on_the_dragon_only(self):
        g, a, b = game(HeuristicAI)
        g.enter_battlefield(a, HAVEN).sick = False
        a.hand = [DRAGON_SPELL, BEAR]
        a.ai.main_phase(g, a)
        self.assertEqual(a.hand, [DRAGON_SPELL, BEAR])         # neither may use the Haven's mana
        self.assertEqual(a.pool, [])
        g2, a2, b2 = game(HeuristicAI)
        g2.enter_battlefield(a2, HAVEN).sick = False
        a2.hand = [DRAGON]
        a2.ai.main_phase(g2, a2)
        self.assertIn(DRAGON, [x.card for x in a2.creatures])


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
