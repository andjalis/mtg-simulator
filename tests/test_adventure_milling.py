"""Recover physical Adventure cards, preserving both playable faces."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import card_from_scryfall
from mtgsim.engine import Game, Player
from tests.test_templates import BEAR, ISLAND, card


def adventurer(name="Test Adventurer", types="Creature — Giant"):
    return card_from_scryfall({
        "name": name + " // Test Journey", "layout": "adventure", "cmc": 2,
        "card_faces": [
            {"name": name, "mana_cost": "{2}", "type_line": types, "oracle_text": "", "power": "2", "toughness": "2"},
            {"name": "Test Journey", "mana_cost": "{0}", "type_line": "Sorcery — Adventure", "oracle_text": "Draw a card."},
        ],
    })


class AdventureMilling(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"

    def cast(self, text):
        spell = card("Test Adventure Recovery", types="Sorcery", text=text)
        self.assertEqual(spell.unsupported, [])
        self.a.hand.append(spell)
        self.assertTrue(self.game.cast(self.a, spell, []))
        self.game.settle()

    def test_all_adventures_include_noncreatures_and_duplicates(self):
        creature, artifact = adventurer(), adventurer("Test Adventuring Relic", "Artifact")
        self.a.library = [creature, artifact, creature, BEAR, ISLAND]
        self.cast("Mill five cards. Put all cards that have an Adventure from among the milled cards into your hand.")
        self.assertCountEqual(self.a.hand, [creature, creature, artifact])
        self.assertIn(BEAR, self.a.graveyard)
        self.assertIn(ISLAND, self.a.graveyard)

    def test_existing_adventures_in_graveyard_stay_there(self):
        old = adventurer()
        self.a.graveyard.append(old)
        self.a.library = [BEAR]
        self.cast("Mill a card. Then put all cards that have an Adventure from among the milled cards into your hand.")
        self.assertEqual(self.a.hand, [])
        self.assertIn(old, self.a.graveyard)

    def test_empty_library_is_safe(self):
        self.cast("Mill seven cards. Put all cards that have an Adventure from among the milled cards into your hand.")
        self.assertEqual(self.a.hand, [])
        self.assertFalse(self.a.lost)

    def test_up_to_two_selection(self):
        adventure = adventurer()
        self.a.library = [adventure] * 3
        self.cast("Mill three cards. You may put up to two cards that have an Adventure from among them into your hand.")
        self.assertEqual(self.a.hand, [adventure, adventure])
        self.assertEqual(self.a.graveyard.count(adventure), 1)

    def test_recovered_adventure_can_be_cast(self):
        adventure = adventurer()
        self.a.library = [ISLAND, adventure]
        self.cast("Mill a card. Put a card that has an Adventure milled this way into your hand.")
        option = next(c for c in self.game.spell_options(self.a) if c.name == "Test Journey")
        self.assertTrue(self.game.cast(self.a, option, []))
        self.game.settle()
        self.assertIn(ISLAND, self.a.hand)
        self.assertEqual(self.a.on_adventure, [adventure])
        self.assertTrue(any(self.game._origin(c)[:2] == (adventure, "from_adventure")
                            for c in self.game.spell_options(self.a)))

    def test_another_back_face_does_not_count_as_adventure(self):
        transformed = card_from_scryfall({"name": "Front // Back", "cmc": 1, "card_faces": [
            {"name": "Front", "mana_cost": "{1}", "type_line": "Creature — Human", "oracle_text": "", "power": "1", "toughness": "1"},
            {"name": "Back", "type_line": "Creature — Beast", "oracle_text": "", "power": "2", "toughness": "2"},
        ]})
        self.assertIsNotNone(transformed.back)
        self.a.library = [transformed]
        self.cast("Mill a card. Put all cards that have an Adventure from among the milled cards into your hand.")
        self.assertEqual(self.a.hand, [])
        self.assertIn(transformed, self.a.graveyard)


if __name__ == "__main__":
    unittest.main()
