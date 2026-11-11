"""#297: 'defending player' is the player (or planeswalker controller) the relevant attacker is attacking,
not the effect controller's opponent."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cx_grammar import players
from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem

from tests.test_templates import BEAR


class DefendingPlayer(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "declare_attackers"
        self.attacker = self.game.enter_battlefield(self.a, BEAR)
        self.game.attackers = [self.attacker]

    def item(self, controller, source, context=None):
        return StackItem(controller, [], [], source=source, context=context)

    def test_attacker_controllers_trigger_names_the_attacked_player(self):
        self.game.attack_targets = {self.attacker: self.b}
        item = self.item(self.a, self.attacker)
        self.assertEqual(players(self.game, self.a, "defending", item, None), [self.b])

    def test_other_players_trigger_on_an_attacker_still_names_the_attacked_player(self):
        """b controls the trigger ('whenever a creature attacks, defending player ...'); a's creature attacks b."""
        self.game.attack_targets = {self.attacker: self.b}
        item = self.item(self.b, self.attacker)
        self.assertEqual(players(self.game, self.b, "defending", item, None), [self.b])

    def test_attacked_planeswalker_names_its_controller(self):
        walker = self.game.enter_battlefield(self.b, BEAR)
        self.game.attack_targets = {self.attacker: walker}
        item = self.item(self.b, self.attacker)
        self.assertEqual(players(self.game, self.b, "defending", item, None), [self.b])

    def test_trigger_context_attacker(self):
        self.game.attack_targets = {self.attacker: self.b}
        item = self.item(self.b, None, context=self.attacker)
        self.assertEqual(players(self.game, self.b, "defending", item, None), [self.b])


if __name__ == "__main__":
    unittest.main()
