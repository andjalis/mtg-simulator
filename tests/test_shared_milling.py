"""Shared card types, and bounded mill/check/draw processes such as The Tale of Tamiyo."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, SHOCK, card


PROCESS = "Mill two cards. If two cards that share a card type were milled this way, draw a card and repeat this process."


class SharedMilling(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"

    def cast(self, text, library):
        spell = card("Test Shared Mill", types="Sorcery", text=text)
        self.assertEqual(spell.unsupported, [])
        self.a.library = library[:]
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, []))
        self.game.settle()

    def test_shared_type_reward_accepts_duplicate_cards(self):
        self.cast("Mill two cards. If two cards that share a card type were milled this way, you gain 3 life.", [BEAR, BEAR])
        self.assertEqual(self.a.life, 23)

    def test_multitype_card_can_share_either_type(self):
        both = card("Test Golem", types="Artifact Creature — Golem", power=2, toughness=2)
        artifact = card("Test Relic", types="Artifact")
        self.cast("Mill two cards. If two cards that share a card type were milled this way, you gain 3 life.", [both, artifact])
        self.assertEqual(self.a.life, 23)

    def test_supertype_and_subtype_do_not_count(self):
        pairs = ([card("Relic", types="Legendary Snow Artifact"), card("Shrine", types="Legendary Snow Enchantment")],
                 [card("Lesson One", types="Instant — Lesson"), card("Lesson Two", types="Sorcery — Lesson")])
        for pair in pairs:
            with self.subTest(pair=pair):
                self.a.life = 20
                self.cast("Mill two cards. If two cards that share a card type were milled this way, you gain 3 life.", pair)
                self.assertEqual(self.a.life, 20)

    def test_kindred_and_legacy_tribal_are_same_card_type(self):
        a = card("Kindred One", types="Kindred Instant — Elf")
        b = card("Kindred Two", types="Tribal Sorcery — Goblin")
        self.cast("Mill two cards. If two cards that share a card type were milled this way, you gain 3 life.", [a, b])
        self.assertEqual(self.a.life, 23)

    def test_three_cards_need_one_common_type(self):
        a = card("Test A", types="Artifact Creature", power=1, toughness=1)
        b = card("Test B", types="Artifact Enchantment")
        c = card("Test C", types="Enchantment Creature", power=1, toughness=1)
        self.cast("Mill three cards. If three cards that share a card type were milled this way, you gain 3 life.", [a, b, c])
        self.assertEqual(self.a.life, 20)

    def test_empty_and_short_library_do_not_make_a_pair(self):
        for library in ([], [BEAR]):
            with self.subTest(library=library):
                self.cast(PROCESS, library)
                self.assertEqual(self.a.hand, [])
                self.assertFalse(self.a.lost)

    def test_process_stops_on_mismatched_pair(self):
        self.cast(PROCESS, [ISLAND, BEAR, SHOCK])
        self.assertEqual(self.a.hand, [])
        self.assertEqual(self.a.library, [ISLAND])

    def test_repeated_process_draws_between_mills(self):
        elf = card("Test Elf", types="Creature — Elf", power=1, toughness=1)
        self.cast(PROCESS, list(reversed([BEAR, BEAR, SHOCK, ISLAND, ISLAND, elf, BEAR, SHOCK, ISLAND])))
        self.assertEqual(self.a.hand, [SHOCK, elf])
        self.assertEqual(self.a.library, [ISLAND])
        self.assertEqual(self.a.milled_last, [BEAR, SHOCK])

    def test_process_draw_from_empty_library_loses(self):
        self.cast(PROCESS, [BEAR, BEAR])
        self.assertTrue(self.a.lost)

    def test_process_without_a_preceding_mill_stays_unsupported(self):
        spell = card("Test Missing Process", types="Sorcery", text=PROCESS.split(". ", 1)[1])
        self.assertTrue(spell.unsupported)

    def test_unrecognised_repetition_stays_unsupported(self):
        spell = card("Test Unknown Process", types="Sorcery", text="Mill two cards. If two cards that share a card type were milled this way, create a Treasure token and repeat this process.")
        self.assertTrue(spell.unsupported)

    def test_saga_chapter_runs_the_process(self):
        saga = card("Test Mill Saga", "{2}", "Enchantment — Saga", "I, II, III — " + PROCESS + "\nIV — Draw a card.")
        self.assertEqual(saga.unsupported, [])
        self.a.library = list(reversed([BEAR, BEAR, SHOCK, BEAR, ISLAND, ISLAND]))
        self.game.enter_battlefield(self.a, saga)
        self.game.settle()
        self.assertEqual(self.a.hand, [SHOCK])
        self.assertEqual(self.a.library, [ISLAND])


if __name__ == "__main__":
    unittest.main()
