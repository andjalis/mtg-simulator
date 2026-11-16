"""'attack a player' / 'attack a player or planeswalker' heads: where the creatures attack matters (#538)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_trigger
from mtgsim.engine import Game, Player

from tests.test_templates import BEAR, ISLAND, card


def events(line):
    out = _parse_trigger(line)
    return None if out is None or out[1] else [t.event for t in out[0]]


class AttackPlayer(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 5, HeuristicAI())
        self.b = Player("b", [BEAR] * 5, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "declare_attackers"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        self.walker = self.game.enter_battlefield(self.b, card("Test Walker", "{3}", "Legendary Planeswalker — Test", ""))
        self.battle = self.game.enter_battlefield(self.b, card("Test Battle", "{3}", "Battle — Siege", ""))

    def attack(self, attackers, target):
        self.game.attackers = list(attackers)
        for x in attackers:
            self.game.attack_targets[x] = target
        for x in attackers:
            self.game.fire(self.a, "attacks", x)
        self.game.fire(self.a, "you_attack")
        self.game.settle()

    def test_parse(self):
        self.assertEqual(events("Whenever one or more Halflings you control attack a player, draw a card."),
                         ["ev:attacks"])
        self.assertEqual(events("Whenever you attack a player or planeswalker with one or more creatures with power 1 "
                                "or less, draw a card."), ["ev:you_attack"])

    def test_one_or_more_attack_a_player(self):
        self.game.enter_battlefield(self.a, card("Watcher", "{2}", "Creature — Human", "Whenever one or more "
                                                 "Halflings you control attack a player, you gain 1 life.", 1, 1))
        hob = self.game.enter_battlefield(self.a, card("Hob", "{1}", "Creature — Halfling", "", 1, 1))
        hob2 = self.game.enter_battlefield(self.a, card("Hob2", "{1}", "Creature — Halfling", "", 1, 1))
        self.attack([hob, hob2], self.walker)               # a planeswalker is not a player
        self.assertEqual(self.a.life, 20)
        self.game.step = "declare_blockers"                 # a new batch
        self.attack([hob, hob2], self.b)
        self.assertEqual(self.a.life, 21)                   # once for the batch

    def test_you_attack_a_player_or_planeswalker_with(self):
        self.game.enter_battlefield(self.a, card("Rigo", "{2}", "Creature — Human", "Whenever you attack a player or "
                                                 "planeswalker with one or more creatures with power 1 or less, you "
                                                 "gain 1 life.", 2, 2))
        small = self.game.enter_battlefield(self.a, card("Small", "{1}", "Creature — Rat", "", 1, 1))
        self.attack([small], self.battle)                   # a battle: neither
        self.assertEqual(self.a.life, 20)
        self.attack([small], self.walker)
        self.assertEqual(self.a.life, 21)
        big = self.game.enter_battlefield(self.a, BEAR)
        self.attack([big], self.b)                          # power 2: no
        self.assertEqual(self.a.life, 21)


if __name__ == "__main__":
    unittest.main()
