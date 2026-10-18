import unittest

from mtgsim.decklist import parse_full


class ParserSessionQATests(unittest.TestCase):
    def test_arena_companion_precedes_deck(self):
        deck = parse_full("Companion\n1 Jegantha, the Wellspring\n\n"
                          "Deck\n60 Mountain\n\nSideboard\n2 Shock")
        self.assertEqual(deck.main, {"Mountain": 60})
        self.assertEqual(deck.sideboard, {"Jegantha, the Wellspring": 1, "Shock": 2})

    def test_empty_color_preserves_sideboard_note_column(self):
        deck = parse_full("Deck\n60 Mountain\nSideboard\n2\tDuress\t\tControl")
        self.assertEqual(deck.sideboard, {"Duress": 2})
        self.assertEqual(deck.bring_in, {"Duress": "Control"})

    def test_missing_table_name_is_not_a_color_card(self):
        deck = parse_full("Deck\n2\t\tBlack\tControl\n4\tShock\tRed")
        self.assertEqual(deck.main, {"Shock": 4})

    def test_sb_prefix_does_not_change_following_main_cards(self):
        deck = parse_full("4 Shock\nSB: 2 Duress\n20 Mountain")
        self.assertEqual(deck.main, {"Shock": 4, "Mountain": 20})
        self.assertEqual(deck.sideboard, {"Duress": 2})

    def test_mtgo_blank_separator_and_comment(self):
        deck = parse_full("60 Mountain\n# main deck complete\n\n2 Shock")
        self.assertEqual(deck.main, {"Mountain": 60})
        self.assertEqual(deck.sideboard, {"Shock": 2})
