"""Opponent-library searches: Bribery steals, Sadistic Sacrament / Denying Wind library
exiles, Quiet Speculation graveyard mills and the Lost Legacy / Infinite Obliteration
name-extraction cluster (the AI names the most valuable card in the victim's zones)."""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.carddb import ALL_CARDS, CardDB
from tests.test_batch1 import Batch1
from tests.test_templates import ISLAND, card

DRAGON = card("Test Dragon", "{3}{R}", "Creature — Dragon", "Flying", 2, 2)
ROCK = card("Test Rock", "{2}", "Artifact", "")


def _flashback(carddef):
    from mtgsim.cards import AltCost
    carddef.alt_costs = [AltCost("flashback", {"generic": 1, "U": 1})]
    return carddef


class Mega2SearchParse(unittest.TestCase):
    def parse(self, text):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        return effects

    def test_bribery_steal(self):
        (eff,) = self.parse("Search target opponent's library for a creature card and put that "
                            "card onto the battlefield under your control. Then that player shuffles.")
        self.assertEqual((eff.kind, eff.target, eff.data["dest"], eff.data["n"]),
                         ("search", "player", "battlefield_mine", 1))
        self.assertEqual(eff.data["what"], "a creature card")

    def test_library_exile(self):
        (eff,) = self.parse("Search target player's library for up to three cards, exile them, "
                            "then that player shuffles.")
        self.assertEqual((eff.data["dest"], eff.data["n"]), ("exile", 3))
        (eff2,) = self.parse("Search target player's library for up to seven cards and exile them.")
        self.assertEqual((eff2.data["dest"], eff2.data["n"]), ("exile", 7))

    def test_quiet_speculation_gy(self):
        (eff,) = self.parse("Search target player's library for up to three cards with flashback "
                            "and put them into that player's graveyard. Then the player shuffles.")
        self.assertEqual((eff.data["dest"], eff.data["n"], eff.data["what"]),
                         ("gy", 3, "a flashback card"))

    def test_name_extraction(self):
        (eff,) = self.parse("Choose a card name. Search target opponent's graveyard, hand, and "
                            "library for any number of cards with that name and exile them. "
                            "Then that player shuffles.")
        self.assertEqual((eff.data["name"], eff.data["n"], eff.data.get("name_filter")),
                         (True, 0, ""))
        (eff2,) = self.parse("Choose a nonland card name. Search target player's graveyard, hand, "
                             "and library for any number of cards with that name and exile them. "
                             "Then that player shuffles.")
        self.assertEqual(eff2.data["name_filter"], "nonland")


class Mega2SearchBehavior(Batch1):
    def test_bribery_steals_the_best_creature(self):
        self.b.library = [ISLAND, DRAGON, ROCK, ISLAND]
        self.apply("Search target opponent's library for a creature card and put that card "
                   "onto the battlefield under your control. Then that player shuffles.", [self.b])
        self.assertEqual([x.card.name for x in self.a.creatures], ["Test Dragon"])
        self.assertEqual(len(self.b.library), 3)
        self.assertNotIn(DRAGON, self.b.library)

    def test_exiles_up_to_n_cards_from_their_library(self):
        self.b.library = [DRAGON, DRAGON, ROCK, ISLAND, ISLAND]
        self.apply("Search target player's library for up to three cards, exile them, then "
                   "that player shuffles.", [self.b])
        self.assertEqual(len(self.b.library), 2)
        self.assertEqual(len(self.b.exile), 3)

    def test_quiet_speculation_mills_only_flashback_cards(self):
        flashy = _flashback(card("Test Flashback", "{1}{U}", "Sorcery", ""))
        self.b.library = [ISLAND, flashy, DRAGON, ISLAND]
        self.apply("Search target player's library for up to three cards with flashback and put "
                   "them into that player's graveyard. Then the player shuffles.", [self.b])
        self.assertIn(flashy, self.b.graveyard)
        self.assertNotIn(DRAGON, self.b.graveyard)

    def test_lost_legacy_exiles_every_copy_of_the_named_card(self):
        self.b.hand = [DRAGON]
        self.b.library = [DRAGON, ROCK, ISLAND]
        self.apply("Choose a card name. Search target opponent's graveyard, hand, and library "
                   "for any number of cards with that name and exile them. Then that player "
                   "shuffles.", [self.b])
        self.assertEqual(len(self.b.exile), 2)
        self.assertNotIn(DRAGON, self.b.hand)
        self.assertNotIn(DRAGON, self.b.library)
        self.assertIn(ROCK, self.b.library)

    def test_name_extraction_respects_the_nonland_filter(self):
        self.b.hand = [ISLAND, ISLAND]
        self.b.library = [DRAGON, ISLAND]
        self.apply("Choose a nonland card name. Search target player's graveyard, hand, and "
                   "library for any number of cards with that name and exile them. Then that "
                   "player shuffles.", [self.b])
        self.assertEqual([c.name for c in self.b.exile], ["Test Dragon"])

    def test_database_cards_parse_fully(self):
        if not ALL_CARDS.exists():
            self.skipTest("card database not built")
        db = CardDB()
        for name in ("Bribery", "Acquire", "Denying Wind", "Quiet Speculation",
                     "Infinite Obliteration", "Dispossess", "Cranial Extraction", "Memoricide",
                     "Slaughter Games", "Ancient Vendetta", "Amrou Scout"):
            card_def = db.get(name)
            self.assertFalse(card_def.unsupported, (name, card_def.unsupported))


if __name__ == "__main__":
    unittest.main()
