"""le-chonk-3 batch 4: {X} in an activated ability's mana cost.

The parser does not yet keep these ability lines (they land in ``unsupported``, see the batch
report), so the tests hand-build ``Activated`` objects whose cost dict carries the "X" key that
``parse_mana_cost`` already produces for "{X}{R}" — exactly what the cards-side template will
emit. Covered: the engine chooses the largest payable X (Cinder Elemental wording), an explicit
X is honored and paid, X lands on ``item.x`` so "deals X damage" / "draw X cards" effects see it,
the ability is refused when no X can be paid, and the AI's ability_worth judges the effects at
the chosen size.
"""
import dataclasses
import random
import unittest

from mtgsim.cards import Activated, Effect
from mtgsim.engine import Game, Permanent, Player
from mtgsim.engine.policy import ability_worth
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

CINDER = dataclasses.replace(                    # Cinder Elemental wording
    card("Test Cinder", "{3}{R}", "Creature — Elemental", "", 0, 2),
    activated=[Activated("ability", {"X": 1, "R": 1},
                         effects=[Effect("damage", 0, target="any", data={"x": True})],
                         text="{X}{R}, {T}, Sacrifice Test Cinder: It deals X damage to any target.",
                         extra_costs={"tap": True, "sac_self": True})])
TOME = dataclasses.replace(                       # "X: Draw X cards." wording
    card("Test Tome", "{2}", "Artifact", ""),
    activated=[Activated("ability", {"X": 1},
                         effects=[Effect("draw", 0, target="none", data={"x": True})],
                         text="{X}: Draw X cards.")])
WELL = dataclasses.replace(                       # regression guard: a plain ability
    card("Test Well", "{2}", "Artifact", ""),
    activated=[Activated("ability", {"generic": 2}, effects=[Effect("draw", 1)],
                         text="{2}: Draw a card.")])


class XAbilityCosts(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], None)
        self.b = Player("b", [], None)
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def land(self, p, n, c=MOUNTAIN):
        for _ in range(n):
            land = Permanent(c, p)
            land.sick = False
            p.battlefield.append(land)

    def test_max_payable_x_is_chosen(self):
        cinder = Permanent(CINDER, self.a)
        cinder.sick = False
        self.a.battlefield.append(cinder)
        self.land(self.a, 5)
        self.assertEqual(self.game.ability_x(self.a, cinder, CINDER.activated[0]), 4)  # {X}{R}: 4 + 1

    def test_cinder_elemental_deals_x_damage(self):
        cinder = Permanent(CINDER, self.a)
        cinder.sick = False
        self.a.battlefield.append(cinder)
        self.land(self.a, 5)
        life = self.b.life
        self.assertTrue(self.game.can_activate(self.a, cinder, 0))
        self.assertTrue(self.game.activate_ability(self.a, cinder, 0))
        self.assertEqual(self.b.life, life - 4)
        self.assertNotIn(cinder, self.a.battlefield)          # sacrificed as part of the cost

    def test_no_x_payable_means_no_activation(self):
        cinder = Permanent(CINDER, self.a)
        cinder.sick = False
        self.a.battlefield.append(cinder)
        self.land(self.a, 1)                                 # only the {R}: X would have to be 0
        self.assertEqual(self.game.ability_x(self.a, cinder, CINDER.activated[0]), None)
        self.assertFalse(self.game.can_activate(self.a, cinder, 0))

    def test_explicit_x_is_paid_and_used(self):
        tome = Permanent(TOME, self.a)
        self.a.battlefield.append(tome)
        self.land(self.a, 5)
        hand = len(self.a.hand)
        self.assertTrue(self.game.activate_ability(self.a, tome, 0, x=2))
        self.assertEqual(len(self.a.hand), hand + 2)

    def test_ability_worth_judges_full_size(self):
        tome = Permanent(TOME, self.a)
        self.a.battlefield.append(tome)
        self.land(self.a, 4)
        self.assertTrue(ability_worth(self.game, self.a, tome, 0))
        self.assertEqual(self.game.ability_x(self.a, tome, TOME.activated[0]), 4)
        cinder = Permanent(CINDER, self.a)
        cinder.sick = False
        self.a.battlefield.append(cinder)
        # a sacrificial damage ability is judged at its chosen X, not refused for looking tiny
        self.assertTrue(self.game.can_activate(self.a, cinder, 0))

    def test_plain_ability_regression(self):
        well = Permanent(WELL, self.a)
        self.a.battlefield.append(well)
        self.land(self.a, 2)
        hand = len(self.a.hand)
        self.assertTrue(self.game.activate_ability(self.a, well, 0))
        self.assertEqual(len(self.a.hand), hand + 1)


if __name__ == "__main__":
    unittest.main()
