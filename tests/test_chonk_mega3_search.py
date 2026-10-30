"""Life's Finale and friends: searching an opponent's library for <desc> cards
and putting them into their graveyard (the Quiet Speculation shape generalized
from "cards with <characteristic>" to "<desc> cards")."""
import unittest

from mtgsim.cards import _parse_effects
from tests.test_batch1 import Batch1
from tests.test_templates import BEAR, ISLAND, card

SPELL = card("Test Sorcery", "{1}{B}", "Sorcery", "")
FINALE = card("Test Finale", "{4}{B}{B}", "Sorcery",
              "Destroy all creatures, then search target opponent's library for up to "
              "three creature cards and put them into their graveyard. Then that player "
              "shuffles.")


class OppGraveyardSearchParse(unittest.TestCase):
    def test_desc_cards_go_to_their_graveyard(self):
        effects, ignored = _parse_effects(
            "Search target opponent's library for up to three creature cards and put "
            "them into their graveyard. Then that player shuffles.")
        self.assertFalse(ignored, ignored)
        (eff,) = effects
        self.assertEqual(eff.kind, "search")
        self.assertEqual((eff.target, eff.data["n"], eff.data["dest"]), ("player", 3, "gy"))
        self.assertEqual(eff.data["what"], "a creature card")
        self.assertTrue(eff.data["opp_library"])

    def test_quiet_speculation_still_parses(self):
        effects, ignored = _parse_effects(
            "Search target opponent's library for up to three cards with flashback and "
            "put them into that player's graveyard.")
        self.assertFalse(ignored, ignored)
        self.assertEqual(effects[0].data["what"], "a flashback card")


class OppGraveyardSearchBehavior(Batch1):
    def test_creatures_leave_their_library_into_their_graveyard(self):
        self.b.library = [BEAR, ISLAND, BEAR, ISLAND]
        self.apply("Search target opponent's library for up to three creature cards "
                   "and put them into their graveyard. Then that player shuffles.", [self.b])
        self.assertEqual([c.name for c in self.b.graveyard], ["Grizzly Bears"] * 2)
        self.assertEqual(len(self.b.library), 2)


class OppGraveyardSearchDatabase(unittest.TestCase):
    def test_lifes_finale_fully_parses(self):
        try:
            from mtgsim.carddb import CardDB
            from mtgsim.coverage import FULL, card_coverage
            db = CardDB()
        except Exception:
            self.skipTest("card database not built")
        if db._all is None:
            self.skipTest("card database not built")
        row = card_coverage(db.get("Life's Finale"))
        self.assertEqual(row.status, FULL, (row.ignored, row.simplified))


if __name__ == "__main__":
    unittest.main()
