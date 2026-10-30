"""Bottom-of-library dig riders: the wording variants the cards/clauses.py sentinels
miss — "put that card into your hand", "reveal up to two <desc> cards", "any number of
<desc> cards" and "put (up to) <desc> cards onto the battlefield (tapped)".
"""
import unittest

from mtgsim.cards import _parse_effects
from tests.test_batch1 import Batch1
from tests.test_templates import BEAR, DRAGON3, ISLAND, card

LAND = card("Test Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")


class DigBottomParse(unittest.TestCase):
    def parse(self, text):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        return effects

    def test_that_card_into_hand(self):
        (eff,) = self.parse("Look at the top three cards of your library. You may reveal a land "
                            "card from among them and put that card into your hand. Put the rest "
                            "on the bottom of your library in a random order.")
        self.assertEqual((eff.kind, eff.amount, eff.amount2, eff.data["filter"]),
                         ("dig", 3, 1, "a land card"))

    def test_reveal_up_to_two(self):
        (eff,) = self.parse("Look at the top five cards of your library. You may reveal up to "
                            "two creature cards from among them and put them into your hand. "
                            "Put the rest on the bottom of your library in a random order.")
        self.assertEqual((eff.kind, eff.amount, eff.amount2, eff.data["filter"]),
                         ("dig", 5, 2, "a creature"))

    def test_any_number_revealed(self):
        (eff,) = self.parse("Look at the top five cards of your library. You may reveal any "
                            "number of artifact cards from among them and put the revealed "
                            "cards into your hand. Put the rest on the bottom of your library "
                            "in a random order.")
        self.assertEqual((eff.kind, eff.amount, eff.amount2, eff.data["filter"]),
                         ("dig", 5, 5, "an artifact"))

    def test_any_number_into_hand(self):
        (eff,) = self.parse("Look at the top four cards of your library. You may put any number "
                            "of Dwarf cards from among them into your hand. Put the rest on the "
                            "bottom of your library in a random order.")
        self.assertEqual((eff.kind, eff.amount, eff.amount2, eff.data["filter"]),
                         ("dig", 4, 4, "a Dwarf"))

    def test_up_to_two_lands_tapped(self):
        (eff,) = self.parse("Look at the top six cards of your library. Put up to two land cards "
                            "from among them onto the battlefield tapped and the rest on the "
                            "bottom of your library in a random order.")
        self.assertEqual((eff.kind, eff.amount, eff.amount2), ("dig_put_filter", 6, 2))
        self.assertEqual(eff.data, {"filter": "a land", "tapped": True, "max_cmc": None, "rest": "bottom"})

    def test_one_land_tapped(self):
        (eff,) = self.parse("Look at the top six cards of your library. You may put a land card "
                            "from among them onto the battlefield tapped. Put the rest on the "
                            "bottom of your library in a random order.")
        self.assertEqual((eff.kind, eff.amount, eff.amount2), ("dig_put_filter", 6, 1))
        self.assertTrue(eff.data["tapped"])

    def test_reveal_all_matching_to_hand_mill_rest(self):
        (eff,) = self.parse("Reveal the top four cards of your library. Put all land cards "
                            "revealed this way into your hand and the rest into your "
                            "graveyard.")
        self.assertEqual((eff.kind, eff.amount), ("dig_all", 4))
        self.assertEqual(eff.data, {"keep": "hand", "rest": "gy", "filter": "a land"})

    def test_reveal_all_matching_bottom_rest(self):
        (eff,) = self.parse("Reveal the top four cards of your library. Put all Zombie "
                            "cards revealed this way into your hand and the rest on the "
                            "bottom of your library in any order.")
        self.assertEqual(eff.data, {"keep": "hand", "rest": "bottom", "filter": "a Zombie"})

    def test_reveal_all_to_graveyard_bottom_rest(self):
        (eff,) = self.parse("Reveal the top five cards of your library. Put all Demon "
                            "cards revealed this way into your graveyard and the rest on "
                            "the bottom of your library in a random order.")
        self.assertEqual(eff.data, {"keep": "gy", "rest": "bottom", "filter": "a Demon"})

    def test_up_to_two_with_mana_bound(self):
        (eff,) = self.parse("Look at the top six cards of your library. Put up to two "
                            "creature cards with mana value 3 or less from among them "
                            "onto the battlefield. Put the rest on the bottom of your "
                            "library in any order.")
        self.assertEqual((eff.kind, eff.amount, eff.amount2), ("dig_put_filter", 6, 2))
        self.assertEqual(eff.data["max_cmc"], 3)

    def test_any_number_onto_battlefield_rest_to_hand(self):
        (eff,) = self.parse("Look at the top five cards of your library. Put any number of "
                            "permanent cards from among them onto the battlefield and the "
                            "rest into your hand.")
        self.assertEqual((eff.kind, eff.amount, eff.amount2), ("dig_put_filter", 5, 5))
        self.assertEqual(eff.data["rest"], "hand")

    def test_fourteen_stays_a_readable_line(self):
        effects, ignored = _parse_effects(
            "Reveal the top fourteen cards of your library. Put all Doctor cards revealed "
            "this way into your graveyard and the rest on the bottom of your library in a "
            "random order.")
        self.assertEqual(effects, [])
        self.assertEqual(len(ignored), 2)

    def test_chosen_type_stays_ignored(self):
        effects, ignored = _parse_effects(
            "Look at the top six cards of your library. You may reveal any number of cards "
            "of the chosen type from among them and put the revealed cards into your hand. "
            "Put the rest on the bottom of your library in a random order.")
        self.assertEqual(effects, [])
        self.assertTrue(ignored)


class DigBottomBehavior(Batch1):
    def test_reveal_up_to_two_keeps_two_creatures(self):
        self.a.library = [ISLAND] * 15 + [BEAR, DRAGON3, ISLAND, ISLAND, ISLAND]
        self.apply("Look at the top five cards of your library. You may reveal up to two "
                   "creature cards from among them and put them into your hand. Put the rest "
                   "on the bottom of your library in a random order.")
        self.assertEqual({c.name for c in self.a.hand}, {"Grizzly Bears", "Big Dragon"})
        self.assertEqual(len(self.a.library), 18)
        self.assertEqual(len(self.a.graveyard), 0)

    def test_any_number_keeps_all_lands(self):
        self.a.library = [BEAR] * 4 + [ISLAND, ISLAND]
        self.apply("Look at the top four cards of your library. You may put any number of "
                   "land cards from among them into your hand. Put the rest on the bottom of "
                   "your library in a random order.")
        self.assertEqual({c.name for c in self.a.hand}, {"Island", "Island"})
        self.assertEqual(sorted(c.name for c in self.a.library), ["Grizzly Bears"] * 4)

    def test_reveal_all_lands_to_hand_dragons_milled(self):
        self.a.library = [BEAR, BEAR, ISLAND, ISLAND, DRAGON3, ISLAND]
        self.apply("Reveal the top four cards of your library. Put all land cards "
                   "revealed this way into your hand and the rest into your graveyard.")
        self.assertEqual([c.name for c in self.a.hand], ["Island", "Island", "Island"])
        self.assertEqual([c.name for c in self.a.graveyard], ["Big Dragon"])
        self.assertEqual(len(self.a.library), 2)

    def test_battlefield_puts_take_all_permanents(self):
        self.a.library = [ISLAND, ISLAND, BEAR, DRAGON3, BEAR, BEAR]
        self.apply("Look at the top five cards of your library. Put any number of "
                   "permanent cards from among them onto the battlefield and the rest "
                   "into your hand.")
        self.assertEqual(len(self.a.battlefield), 5)
        self.assertEqual(len(self.a.library), 1)

    def test_bounded_creature_put_respects_mana_value(self):
        self.a.library = [ISLAND, ISLAND, ISLAND, DRAGON3, BEAR, BEAR]
        self.apply("Look at the top six cards of your library. Put up to two creature "
                   "cards with mana value 1 or less from among them onto the "
                   "battlefield. Put the rest on the bottom of your library in any order.")
        self.assertEqual(self.a.battlefield, [])
        self.assertEqual(len(self.a.library), 6)

    def test_up_to_two_lands_enter_tapped(self):
        self.a.library = [BEAR, BEAR, BEAR, BEAR, LAND, LAND]
        self.apply("Look at the top six cards of your library. Put up to two land cards from "
                   "among them onto the battlefield tapped and the rest on the bottom of your "
                   "library in a random order.")
        lands = [x for x in self.a.battlefield if x.card.is_land]
        self.assertEqual(len(lands), 2)
        self.assertTrue(all(x.tapped for x in lands))
        self.assertEqual([c.name for c in self.a.library], ["Grizzly Bears"] * 4)
        self.assertEqual(self.a.hand, [])


class DigBottomDatabase(unittest.TestCase):
    def test_cards_fully_parse(self):
        try:
            from mtgsim.carddb import CardDB
            from mtgsim.coverage import FULL, card_coverage
            db = CardDB()
        except Exception:
            self.skipTest("card database not built")
        if db._all is None:
            self.skipTest("card database not built")
        for name in ("Director Nick Fury", "Pictures of Spider-Man", "Reality Heist",
                     "Forging the Anchor", "Wandering Mind"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored, row.simplified))


if __name__ == "__main__":
    unittest.main()
