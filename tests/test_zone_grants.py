"""#633: keywords granted to cards in your graveyard or hand (mtgsim.zone_grants)."""
import unittest

from mtgsim.coverage import card_coverage
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, FOREST, ISLAND, card

HISTORIAN = card("Test Historian", "{3}{G}", "Creature — Elf Druid",
                 "Merfolk and Druid cards in your graveyard have retrace.", 2, 2)
SLIVER_LORD = card("Test Sliver Lord", "{2}{B}", "Creature — Sliver",
                   "Each Sliver creature card in your graveyard has unearth {2}.", 2, 2)
MYSTIC = card("Test Mystic", "{2}{U}", "Creature — Human Wizard", "Each creature card in your hand has cycling {1}{U}.",
              2, 2)
SIX = card("Test Six", "{2}{G}", "Creature — Treefolk",
           "During your turn, nonland permanent cards in your graveyard have retrace.", 2, 4)
FLASHER = card("Test Flasher", "{3}", "Artifact", "Instant and sorcery cards in your graveyard have flashback.")
DRUID = card("Test Druid", "{1}{G}", "Creature — Elf Druid", "", 2, 1)
SLIVER = card("Test Sliver", "{3}", "Creature — Sliver", "", 3, 3)
DRAW = card("Test Draw", "{U}", "Sorcery", "Draw a card.")


class Parsing(unittest.TestCase):
    def test_lines(self):
        for c in (HISTORIAN, SLIVER_LORD, MYSTIC, SIX, FLASHER):
            self.assertEqual(c.unsupported, [], c.name)
        zone, specs, kw, cost, turn = SLIVER_LORD.advanced_rules["zone_grants"][0]
        self.assertEqual((zone, kw, cost, turn), ("graveyard", "unearth", {"generic": 2}, False))
        self.assertTrue(SIX.advanced_rules["zone_grants"][0][4])

    def test_refusals(self):
        for text in ("Each instant card in your hand has miracle {2}.",
                     "Creature cards in your graveyard have unearth.",                 # unearth needs a cost
                     "Creature cards in your hand have retrace.",
                     "Each creature card in your graveyard that's a Rogue has unearth {1}{B}."):
            c = card("Test Refused", "{3}", "Artifact", text)
            self.assertTrue(c.unsupported, text)


class Engine(Base):
    def gy_options(self, name):
        return [c for c in self.game.spell_options(self.a) if c.name.startswith(name)]

    def test_retrace_for_the_filter_only(self):
        self.perm(HISTORIAN, self.a)
        for _ in range(2):
            self.perm(FOREST, self.a)
        self.a.graveyard = [DRUID, BEAR]
        self.a.hand = [FOREST, FOREST]
        self.assertEqual([c.name for c in self.gy_options("Test Druid")], ["Test Druid (retrace)"])
        self.assertFalse(self.gy_options("Grizzly"))
        self.assertTrue(self.game.cast(self.a, self.gy_options("Test Druid")[0]))
        self.assertIn("Test Druid", [x.card.name for x in self.a.creatures])
        self.assertEqual(len(self.a.hand), 1)                              # a land discarded for retrace

    def test_unearth_cost(self):
        self.perm(SLIVER_LORD, self.a)
        for _ in range(2):
            self.perm(ISLAND, self.a)
        self.a.graveyard = [SLIVER]
        option = [c for c in self.gy_options("Test Sliver") if "unearth" in c.name]
        self.assertEqual(len(option), 1)
        self.assertTrue(self.game.cast(self.a, option[0]))
        self.game.settle()
        self.assertIn("Test Sliver", [x.card.name for x in self.a.creatures])

    def test_flashback_own_cost_and_exile(self):
        self.perm(FLASHER, self.a)
        self.perm(ISLAND, self.a)
        self.a.graveyard = [DRAW]
        option = self.gy_options("Test Draw")
        self.assertEqual(len(option), 1)
        self.assertTrue(self.game.cast(self.a, option[0]))
        self.game.settle()
        self.assertEqual([c.name for c in self.a.exile], ["Test Draw"])     # flashback exiles it

    def test_during_your_turn_only(self):
        self.perm(SIX, self.a)
        self.a.graveyard = [BEAR]
        self.a.hand = [FOREST, FOREST]
        self.assertTrue(self.gy_options("Grizzly"))
        self.game.active_idx = 1
        self.assertFalse(self.gy_options("Grizzly"))

    def test_granted_cycling(self):
        self.perm(MYSTIC, self.a)
        for _ in range(2):
            self.perm(ISLAND, self.a)
        giant = card("Test Giant", "{7}", "Creature — Giant", "", 7, 7)
        self.a.hand = [giant, DRAW]
        self.a.library = [ISLAND] * 3
        self.game.cycle_spare(self.a)
        self.assertIn("Test Giant", [c.name for c in self.a.graveyard])       # the creature cycled
        self.assertIn("Test Draw", [c.name for c in self.a.hand])            # not a creature card


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_are_full(self):
        from mtgsim.carddb import CardDB
        db = CardDB(offline=True)
        for name in ("Deeproot Historian", "Dregscape Sliver", "Sedris, the Traitor King", "Six", "Jo Grant",
                     "Rhet-Tomb Mystic", "Tectonic Reformation"):
            cov = card_coverage(db.get(name))
            self.assertEqual(cov.status, "full", (name, cov.ignored))


if __name__ == "__main__":
    unittest.main()
