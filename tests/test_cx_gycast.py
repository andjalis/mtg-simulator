"""Graveyard-cast wordings added after the gy_cast kind: non-targeting casts, "until end of turn" and the
"this turn" form of the exile rider."""
import unittest

from mtgsim.cards import _parse_effects


class GyCastWordings(unittest.TestCase):
    def parse(self, text):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        return effects

    def test_non_targeting_with_cap_after_graveyard(self):
        (cast,) = self.parse("You may cast an instant or sorcery spell from your graveyard with mana value 4 or less "
                             "without paying its mana cost. If that spell would be put into your graveyard, exile it "
                             "instead.")
        self.assertEqual((cast.kind, cast.data["max_cmc"], cast.data["free"], cast.data["gy_instead"]),
                         ("gy_cast", 4, True, "exile"))

    def test_opponents_graveyard_and_this_turn_rider(self):
        (cast,) = self.parse("You may cast an instant or sorcery spell from that player's graveyard without paying "
                             "its mana cost. If that spell would be put into a graveyard this turn, exile it instead.")
        self.assertEqual((cast.data["gy"], cast.data["gy_instead"]), ("context", "exile"))

    def test_until_end_of_turn(self):
        (cast,) = self.parse("Until end of turn, you may cast target instant or sorcery card from your graveyard "
                             "without paying its mana cost. If that spell would be put into your graveyard this turn, "
                             "exile it instead.")
        self.assertEqual(cast.kind, "gy_cast")


if __name__ == "__main__":
    unittest.main()
