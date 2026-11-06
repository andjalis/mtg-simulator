"""cx_effects.py: disjunctive targets, opponent draws, graveyard-to-top, random returns, exile-this-turn,
opponent hand counts."""
import random
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, MOUNTAIN, SHOCK, card

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
        prev = None
        for e, t in zip(effs, targets):
            self.game.resolve(p, e, t, prev=prev)
            prev = t if t is not None else prev
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

    def test_win_the_game(self):
        self.run_effects("You win the game.")
        self.assertTrue(self.b.lost and not self.a.lost)

    def test_no_max_hand_for_the_rest_of_the_game(self):
        from mtgsim.cx_next_turn import player_flag
        self.run_effects("You have no maximum hand size for the rest of the game.")
        self.game.turn += 3
        self.assertTrue(player_flag(self.game, self.a, "no_max_hand"))

    def test_put_self_on_top(self):
        clique = card("Test Clique", "{1}{U}", "Creature — Faerie", "{U}: Put ~ on top of its owner's library.", 2, 1)
        self.assertEqual(clique.unsupported, [])
        perm = self.game.enter_battlefield(self.a, clique)
        ab = clique.activated[0]
        from mtgsim.engine import StackItem
        for e in ab.effects:
            self.game.resolve(self.a, e, None, StackItem(self.a, ab.effects, [], source=perm))
        self.assertEqual(self.a.library[-1].name, clique.name)

    def test_target_land_stays_a_creature(self):
        land = self.game.enter_battlefield(self.a, MOUNTAIN)
        self.game.enter_battlefield(self.b, MOUNTAIN)
        effs = effects("Target Mountain becomes a 3/1 creature. It's still a land.")
        self.assertEqual(self.game.legal_targets(self.a, effs[0]), [land])
        self.run_effects("Target Mountain becomes a 3/1 creature. It's still a land.")
        self.assertTrue(land.is_creature and land.card.is_land)
        self.assertEqual((land.power, land.toughness), (3, 1))
        self.assertEqual(land.animated.text, "permanent")

    def test_snow_land_target(self):
        snowy = self.game.enter_battlefield(self.a, card("Snow Isle", "", "Basic Snow Land — Island", ""))
        self.game.enter_battlefield(self.a, MOUNTAIN)
        eff = effects("Target snow land becomes a 2/2 creature until end of turn. It's still a land.")[0]
        self.assertEqual(self.game.legal_targets(self.a, eff), [snowy])

    def test_animate_it_after_counters(self):
        land = self.game.enter_battlefield(self.a, LAND)
        self.run_effects("Put four +1/+1 counters on target land you control. It becomes a 0/0 Elemental creature "
                         "with haste. It's still a land.")
        self.assertEqual((land.power, land.toughness), (4, 4))
        self.assertTrue(land.has("haste"))

    def test_awaken(self):
        arms = card("Test Arms", "{G}", "Sorcery", "You gain 1 life.\nAwaken 2—{G}{G}")
        self.assertEqual(arms.unsupported, [])
        lands = [self.game.enter_battlefield(self.a, FOREST) for _ in range(3)]
        for x in lands:
            x.tapped = False
        self.a.hand = [arms]
        awaken = [v for v in self.game.spell_options(self.a) if v.name.endswith("(awaken)")]
        self.assertEqual(len(awaken), 1)
        targets = self.game.auto_targets(self.a, awaken[0].spell_effects)
        self.assertTrue(self.game.cast(self.a, awaken[0], targets))
        self.game.settle()
        animated = [x for x in lands if x.is_creature]
        self.assertEqual(len(animated), 1)
        self.assertEqual((animated[0].power, animated[0].toughness, self.a.life), (2, 2, 21))
        self.assertTrue(animated[0].has("haste"))


class AlchemyNames(unittest.TestCase):
    def test_rebalanced_card_names_itself(self):
        from mtgsim.cards import card_from_scryfall
        c = card_from_scryfall({"name": "A-Test Cleric", "mana_cost": "{1}{W}", "type_line": "Creature — Human",
                                "oracle_text": "When Test Cleric enters, you gain 2 life.", "power": "2",
                                "toughness": "1"})
        self.assertEqual(c.unsupported, [])


if __name__ == "__main__":
    unittest.main()
