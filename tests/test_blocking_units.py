import unittest

from mtgsim.blocking_units import norm, units


class BlockingUnitsTest(unittest.TestCase):
    def test_norm_masks_numbers_mana_and_colors(self):
        self.assertEqual(norm("Red creature spells you cast cost {1}{R} less to cast."),
                         "COLOR creature spells you cast cost {M} less to cast")
        self.assertEqual(norm("It gets +2/+2 until end of turn."), "it gets N/N until end of turn")

    def test_keyword_line_is_a_mechanic(self):
        self.assertEqual(units("Banding"), [("mechanic", "banding")])

    def test_activated_ability_blames_only_the_unknown_effect(self):
        got = units("{T}: Target creature phases in and does a little dance.")     # an effect no template reads
        self.assertEqual(got, [("ability", "target creature phases in and does a little dance")])

    def test_trigger_with_known_effect_blames_the_head(self):
        got = units("Whenever you surveil, you gain 1 life.")
        self.assertEqual(got, [("trigger", "whenever you surveil")])


if __name__ == "__main__":
    unittest.main()
