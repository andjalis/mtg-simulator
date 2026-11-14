"""#359: "deals N damage to target creature or planeswalker" can hit a planeswalker (it was read as target creature)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player
from mtgsim.cards import card_from_scryfall
from tests.test_templates import MOUNTAIN, card

PLAIN = card("Test Zap", "{1}{R}", "Instant", "Test Zap deals 3 damage to target creature or planeswalker.")
THEIRS = card("Test Jab", "{R}", "Instant",
              "Test Jab deals 2 damage to target creature or planeswalker an opponent controls.")
CREATURE_ONLY = card("Test Poke", "{R}", "Instant", "Test Poke deals 2 damage to target creature.")
WALKER = card_from_scryfall({"name": "Test Walker", "mana_cost": "{2}{W}", "cmc": 3, "loyalty": "3",
                             "type_line": "Legendary Planeswalker — Ajani", "oracle_text": "+1: You gain 1 life."})


def game():
    a, b = Player("a", [], HeuristicAI()), Player("b", [], HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 3, "main1"
    a.library = b.library = [MOUNTAIN] * 10
    for _ in range(3):
        g.enter_battlefield(a, MOUNTAIN).sick = False
    walker = g.enter_battlefield(b, WALKER)
    g.settle()
    assert walker in b.battlefield and walker.loyalty == 3
    return g, a, b, walker


class DamageCreatureOrPlaneswalker(unittest.TestCase):
    def test_targets(self):
        self.assertEqual([e.target for e in PLAIN.spell_effects], ["creature_pw"])
        self.assertEqual([(e.target, e.filter) for e in THEIRS.spell_effects], [("creature_pw", "opp")])
        self.assertEqual([e.target for e in CREATURE_ONLY.spell_effects], ["creature"])

    def test_planeswalker_is_legal_and_takes_the_damage(self):
        g, a, b, walker = game()
        self.assertIn(walker, g.legal_targets(a, PLAIN.spell_effects[0]))
        self.assertNotIn(walker, g.legal_targets(a, CREATURE_ONLY.spell_effects[0]))
        a.hand.append(PLAIN)
        self.assertTrue(g.cast(a, PLAIN, targets=[walker]))
        g.settle()
        self.assertNotIn(walker, b.battlefield)

    def test_opponents_only_wording(self):
        g, a, b, walker = game()
        mine = g.enter_battlefield(a, card("Mine", "{1}", "Creature — Human", "", 1, 1))
        legal = g.legal_targets(a, THEIRS.spell_effects[0])
        self.assertIn(walker, legal)
        self.assertNotIn(mine, legal)

    def test_ai_burns_the_planeswalker(self):
        g, a, b, walker = game()           # a sorcery: the AI holds instant removal for the opponent's turn
        zap = card("Test Blast", "{1}{R}", "Sorcery", "Test Blast deals 3 damage to target creature or planeswalker.")
        a.hand.append(zap)
        g.main_phase(a)
        g.settle()
        self.assertNotIn(walker, b.battlefield)


if __name__ == "__main__":
    unittest.main()
