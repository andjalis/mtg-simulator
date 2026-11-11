"""AI valuation of #297's attacker-relative defending player."""
import random
import unittest

from mtgsim.ai import HeuristicAI, LETHAL
from mtgsim.cards import CardDef, Effect
from mtgsim.engine import Game, Player, StackItem


class AIDefendingPlayerTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0))
        bear = CardDef(name="Attacker", mana_cost={}, cmc=2, types=frozenset({"Creature"}), power=2, toughness=2)
        self.attacker = self.game.enter_battlefield(self.a, bear)
        self.eff = Effect("cx_players", data={"who": "defending", "effects": [Effect("lose_life", 2)]})
        self.card = CardDef(name="Player effect", mana_cost={}, cmc=0, types=frozenset({"Sorcery"}), spell_effects=[self.eff])

    def value(self, player):
        return player.ai._players_plan(self.game, player, self.eff, self.card, False)[1]

    def test_source_attacker_names_attacked_player_from_either_perspective(self):
        self.game.attack_targets[self.attacker] = self.b
        self.game.resolving_item = StackItem(self.b, [self.eff], [], source=self.attacker)
        self.assertGreater(self.value(self.a), 0)
        self.assertLess(self.value(self.b), 0)

    def test_event_context_attacker(self):
        self.game.attack_targets[self.attacker] = self.b
        item = StackItem(self.b, [self.eff], [], context=self.attacker)
        with self.game.targeting(item):
            self.assertLess(self.value(self.b), 0)

    def test_attacked_planeswalker_names_controller(self):
        walker = self.game.enter_battlefield(self.b, CardDef(
            name="Walker", mana_cost={}, cmc=4, types=frozenset({"Planeswalker"}), loyalty=4))
        self.game.attack_targets[self.attacker] = walker
        self.game.resolving_item = StackItem(self.b, [self.eff], [], source=self.attacker)
        self.assertLess(self.value(self.b), 0)

    def test_no_attacker_keeps_opponent_fallback(self):
        self.assertGreater(self.value(self.a), 0)
        self.assertGreater(self.value(self.b), 0)

    def test_unrelated_source_uses_attacker_context(self):
        self.game.attack_targets[self.attacker] = self.b
        other = self.game.enter_battlefield(self.b, self.attacker.card)
        self.game.resolving_item = StackItem(self.b, [self.eff], [], source=other, context=self.attacker)
        self.assertLess(self.value(self.b), 0)

    def test_self_damage_is_not_lethal_opponent_bonus(self):
        self.b.life = 2
        self.game.attack_targets[self.attacker] = self.b
        self.game.resolving_item = StackItem(self.b, [self.eff], [], source=self.attacker)
        self.assertEqual(self.value(self.a), LETHAL)
        self.assertLess(self.value(self.b), 0)


if __name__ == "__main__":
    unittest.main()
