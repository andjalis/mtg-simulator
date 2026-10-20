"""Rewards depend on the current spell or ability's mill, even after recovery."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import BEAR, ISLAND, card


LESSON = card("Test Lesson", "{1}", "Sorcery — Lesson", "Draw a card.")
ELF = card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)


class MillingRewards(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.a.library = [ISLAND] * 10
        self.b.library = [BEAR] * 10

    def cast(self, text):
        spell = card("Test Reward", types="Sorcery", text=text)
        self.assertEqual(spell.unsupported, [])
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, []))
        self.game.settle()

    def test_postfix_reward_when_lesson_milled(self):
        self.a.library = [LESSON]
        self.cast("Mill a card. You gain 2 life if a Lesson card is milled this way.")
        self.assertEqual(self.a.life, 22)

    def test_postfix_reward_does_not_use_other_graveyard_cards(self):
        self.a.graveyard.append(LESSON)
        self.cast("Mill a card. You gain 2 life if a Lesson card is milled this way.")
        self.assertEqual(self.a.life, 20)

    def test_prefix_condition_applies_to_every_part_of_reward(self):
        self.a.library = [ISLAND, LESSON]
        self.cast("Mill a card. If a Lesson card was milled this way, draw a card and you gain 2 life.")
        self.assertEqual(self.a.hand, [ISLAND])
        self.assertEqual(self.a.life, 22)

    def test_failed_condition_skips_every_part(self):
        self.cast("Mill a card. If a Lesson card was milled this way, draw a card and you gain 2 life.")
        self.assertEqual(self.a.hand, [])
        self.assertEqual(self.a.life, 20)

    def test_condition_remembers_recovered_card(self):
        self.a.library = [ELF]
        self.cast("Mill a card. Put an Elf card milled this way into your hand. If an Elf card was milled this way, you gain 3 life.")
        self.assertEqual(self.a.hand, [ELF])
        self.assertEqual(self.a.life, 23)
        self.assertNotIn(ELF, self.a.graveyard)

    def test_you_milled_wording(self):
        self.a.library = [ELF]
        self.cast("Mill a card. If you milled an Elf card this way, you gain 3 life.")
        self.assertEqual(self.a.life, 23)

    def test_minimum_matching_count(self):
        for library, expected in (([BEAR, ISLAND], 20), ([BEAR, ELF], 23)):
            with self.subTest(library=library):
                self.a.life = 20
                self.a.library = library[:]
                self.cast("Mill two cards. If two or more creature cards were milled this way, you gain 3 life.")
                self.assertEqual(self.a.life, expected)

    def test_union_does_not_count_a_multitype_card_twice(self):
        both = card("Test Golem", "{2}", "Artifact Creature — Golem", "", 2, 2)
        self.a.library = [ISLAND, both]
        self.cast("Mill two cards. If two or more artifact or creature cards were milled this way, you gain 3 life.")
        self.assertEqual(self.a.life, 20)

    def test_earlier_resolution_cannot_satisfy_condition(self):
        self.a.library = [LESSON]
        self.cast("Mill a card.")
        self.cast("You gain 2 life if a Lesson card is milled this way.")
        self.assertEqual(self.a.life, 20)

    def test_latest_mill_within_resolution_is_used(self):
        self.a.library = [ISLAND, LESSON]
        self.cast("Mill a card. Mill a card. You gain 2 life if a Lesson card is milled this way.")
        self.assertEqual(self.a.life, 20)

    def test_activated_mill_with_lesson_reward(self):
        c = card("Test Scholar", "{1}", "Creature — Human", "{T}: Mill a card. You may put a land card milled this way into your hand. You gain 2 life if a Lesson card is milled this way.", 1, 1)
        self.assertEqual(c.unsupported, [])
        self.a.library = [LESSON]
        perm = self.game.enter_battlefield(self.a, c)
        perm.sick = False
        self.assertTrue(self.game.activate(self.a, perm, "ability:0"))
        self.game.settle()
        self.assertEqual(self.a.life, 22)
        self.assertEqual(self.a.hand, [])

    def test_each_player_condition_uses_controllers_cards(self):
        self.a.library = [ISLAND]
        self.b.library = [LESSON]
        self.cast("Each player mills a card. You gain 2 life if a Lesson card is milled this way.")
        self.assertEqual(self.a.life, 20)

    def test_mill_memory_is_attached_to_stack_item(self):
        self.a.library = [LESSON]
        spell = card("Test Snapshot", types="Sorcery", text="Mill a card. You gain 2 life if a Lesson card is milled this way.")
        item = StackItem(self.a, spell.spell_effects, [None, None], card=spell)
        self.game.resolve(self.a, spell.spell_effects[0], None, item)
        self.a.milled_last = [ISLAND]
        self.assertTrue(self.game.check_cond(self.a, spell.spell_effects[1], item, None))

    def test_unknown_reward_or_condition_remains_visible(self):
        for text in ("If a Lesson card was milled this way, you may cast a copy of it.",
                     "You gain 2 life if cards with different names were milled this way.",
                     "If a noncreature card was milled this way, you gain 2 life."):
            with self.subTest(text=text):
                self.assertTrue(card("Test Unsupported", types="Sorcery", text=text).unsupported)


if __name__ == "__main__":
    unittest.main()
