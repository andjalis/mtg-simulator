"""smol-chonk-3 batch 4: the spell-graveyard rider ("If that spell would be put into a graveyard,
exile it instead") attaches to the previous effect's data as gy_instead.

The rider follows the cast-from-a-graveyard wordings (Wrexial, Toshiro Umezawa, Dire Fleet
Daredevil, ...), whose base effect is the gy_cast kind; the rider only consumes the sentence once
its base parsed.
"""
import json
import sqlite3
import unittest

from mtgsim.cards.parse import _parse_effects


class SpellGraveyardRider(unittest.TestCase):
    def test_attaches_to_previous_effect(self):
        effects, bad = _parse_effects("Counter target spell. If that spell would be put into a "
                                      "graveyard, exile it instead.")
        self.assertEqual(bad, [])
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].data["gy_instead"], "exile")

    def test_bottom_of_library_variant(self):
        effects, bad = _parse_effects("Counter target spell. If that spell would be put into your "
                                      "graveyard, put it on the bottom of its owner's library instead.")
        self.assertEqual(bad, [])
        self.assertEqual(effects[0].data["gy_instead"], "bottom")

    def test_attaches_to_gy_cast(self):
        # Wrexial's real wording: the "you may cast ... from a graveyard" base is the gy_cast kind,
        # which consumes the rider.
        effects, bad = _parse_effects("you may cast target instant or sorcery card from that "
                                      "player's graveyard without paying its mana cost. If that "
                                      "spell would be put into a graveyard, exile it instead.")
        self.assertEqual(bad, [])
        self.assertEqual([e.kind for e in effects], ["gy_cast"])
        self.assertEqual(effects[0].data["gy_instead"], "exile")


class CardDatabase(unittest.TestCase):
    def test_wrexial_is_fully_matched(self):
        row = sqlite3.connect("mtgsim/data/cards.sqlite3").execute(
            "select data from cards where name = 'Wrexial, the Risen Deep'").fetchone()
        if row is None:                                   # card DB not built: skip
            self.skipTest("cards.sqlite3 is missing")
        from mtgsim import cards
        cdef = cards.card_from_scryfall(json.loads(row[0]))
        self.assertEqual(cdef.unsupported, [])


if __name__ == "__main__":
    unittest.main()
