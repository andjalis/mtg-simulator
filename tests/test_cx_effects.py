"""cx_effects.py: disjunctive targets, opponent draws, graveyard-to-top, random returns, exile-this-turn,
opponent hand counts."""
import random
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, SHOCK, card

VEHICLE = card("Test Wagon", "{2}", "Artifact — Vehicle", "Crew 1", 3, 3)
LAND = card("Test Waste", "", "Land", "")


def effects(text):
    effs, bad = _parse_effects(text)
    assert not bad, bad
    return effs


class Effects(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 10

    def run_effects(self, text, p=None):
        p = p or self.a
        effs = effects(text)
        targets = self.game.auto_targets(p, effs)
        for e, t in zip(effs, targets):
            self.game.resolve(p, e, t)
        self.game.settle()
        return targets

    def test_disjunctive_target_finds_vehicle(self):
        wagon = self.game.enter_battlefield(self.b, VEHICLE)
        self.game.enter_battlefield(self.b, LAND)
        eff = effects("Destroy target creature or Vehicle.")[0]
        self.assertEqual(self.game.legal_targets(self.a, eff), [wagon])

    def test_opponent_draws(self):
        self.run_effects("Target opponent draws two cards.")
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (0, 2))

    def test_graveyard_card_to_top(self):
        self.a.graveyard.extend([BEAR, SHOCK])
        self.run_effects("Put target instant or sorcery card from your graveyard on top of your library.")
        self.assertEqual(self.a.library[-1].name, SHOCK.name)
        self.assertEqual([c.name for c in self.a.graveyard], [BEAR.name])

    def test_random_return(self):
        self.a.graveyard.extend([BEAR, SHOCK, ISLAND])
        self.run_effects("Return a creature card at random from your graveyard to your hand.")
        self.assertEqual([c.name for c in self.a.hand], [BEAR.name])

    def test_exile_this_turn(self):
        bear = self.game.enter_battlefield(self.b, BEAR)
        self.run_effects("If a creature would die this turn, exile it instead.")
        self.game.destroy(bear)
        self.assertEqual((len(self.b.graveyard), len(self.b.exile)), (0, 1))

    def test_opponent_hand_count(self):
        self.b.hand.extend([ISLAND, ISLAND, ISLAND])
        self.run_effects("You gain 1 life for each card in target opponent's hand.")
        self.assertEqual(self.a.life, 23)


if __name__ == "__main__":
    unittest.main()
