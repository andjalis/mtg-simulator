"""smol-chonk-3 batch 4: the spell-graveyard rider ("If that spell would be put into a graveyard,
exile it instead") attaches to the previous effect's data as gy_instead.

The rider follows the cast-from-a-graveyard wordings (Wrexial, Toshiro Umezawa, Dire Fleet
Daredevil, ...), whose base effects are still cross-area parser gaps — so the rider only consumes
the sentence once its base parsed, and stays in ``unsupported`` otherwise (verified here for the
real Wrexial wording).
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

    def test_stays_unmatched_when_the_base_effect_is_missing(self):
        # Wrexial's real wording: the "you may cast ... from a graveyard" base is not parsed yet,
        # so the rider must not mis-attach to an earlier, unrelated effect.
        effects, bad = _parse_effects("you may cast target instant or sorcery card from that "
                                      "player's graveyard without paying its mana cost. If that "
                                      "spell would be put into a graveyard, exile it instead.")
        self.assertEqual(effects, [])
        self.assertEqual(len(bad), 2)


class CardDatabase(unittest.TestCase):
    def test_wrexial_still_partial_until_the_gy_cast_template_lands(self):
        row = sqlite3.connect("mtgsim/data/cards.sqlite3").execute(
            "select data from cards where name = 'Wrexial, the Risen Deep'").fetchone()
        if row is None:                                   # card DB not built: skip
            self.skipTest("cards.sqlite3 is missing")
        from mtgsim import cards
        cdef = cards.card_from_scryfall(json.loads(row[0]))
        self.assertTrue(cdef.unsupported)                 # both sentences remain visible, not hidden


if __name__ == "__main__":
    unittest.main()
