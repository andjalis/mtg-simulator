"""le-chonk-5 engine batch: the Skullcrack riders and Meddling Mage (effect kinds).

- "no_lifegain_turn" (scope all / you / opponents) feeds the turn-scoped
  game.no_lifegain_turn set from le-chonk-4; "no_prevention_turn" sets the flag
  deal_damage consults. Both expire in cleanup (tested in test_chonk_le4_lifegain).
- "choose_name" (Meddling Mage: "As ~ enters, choose a nonland card name") names the
  card the opponent runs the most copies of, and the one-line named-cast ban in
  CostsMixin.can_cast_now (Game.named_cast_banned) refuses casts of that name while
  the mage stays unsuppressed on the battlefield.
"""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards import Effect
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

BLAST = card("Test Blast", "{2}{R}", "Sorcery", "Test Blast does nothing.")


def resolve(game, p, eff, item=None):
    game.resolve(p, eff, None, item)


class RiderKindTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def test_no_lifegain_default_scope_is_all_players(self):
        resolve(self.game, self.a, Effect("no_lifegain_turn"))
        self.assertEqual(self.game.no_lifegain_turn, {self.a, self.b})
        self.game.change_life(self.a, 3, "test")
        self.game.change_life(self.b, 2, "test")
        self.assertEqual((self.a.life, self.b.life), (20, 20))

    def test_no_lifegain_you_scope_blocks_only_the_caster(self):
        resolve(self.game, self.a, Effect("no_lifegain_turn", data={"scope": "you"}))
        self.assertEqual(self.game.no_lifegain_turn, {self.a})
        self.game.change_life(self.a, 3, "test")
        self.game.change_life(self.b, 2, "test")
        self.assertEqual((self.a.life, self.b.life), (20, 22))

    def test_no_lifegain_opponents_scope_blocks_the_rest(self):
        # "Your opponents can't gain life this turn" (Atarka's Command)
        resolve(self.game, self.a, Effect("no_lifegain_turn", data={"scope": "opponents"}))
        self.assertEqual(self.game.no_lifegain_turn, {self.b})
        self.game.change_life(self.a, 3, "test")
        self.game.change_life(self.b, 2, "test")
        self.assertEqual((self.a.life, self.b.life), (23, 20))

    def test_no_prevention_turn_kind_sets_the_flag(self):
        self.a.prevent_next = 5
        resolve(self.game, self.a, Effect("no_prevention_turn"))
        attacker = Permanent(BEAR, self.b)
        attacker.sick = attacker.tapped = False
        self.b.battlefield.append(attacker)
        self.game.deal_damage(self.a, 2, by=self.b, cause="test", source=attacker, combat=True)
        self.assertEqual(self.a.life, 18)             # the shield never applied
        self.assertEqual(self.a.prevent_next, 5)


class ChooseNameTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 6 + [ISLAND] * 4, HeuristicAI())
        self.b = Player("b", [BLAST] * 4 + [MOUNTAIN] * 6, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 1
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        for _ in range(3):                            # b can pay for the Blast
            land = Permanent(MOUNTAIN, self.b)
            land.sick, land.tapped = False, False
            self.b.battlefield.append(land)
        self.b.hand.append(BLAST)

    def mage(self, name=""):
        mage = Permanent(BEAR, self.a)
        mage.sick, mage.tapped = False, False
        mage.chosen_name = name
        self.a.battlefield.append(mage)
        return mage

    def test_choose_name_picks_the_opponents_most_common_nonland(self):
        mage = self.mage()
        resolve(self.game, self.a, Effect("choose_name"), StackItem(self.a, [], [], source=mage))
        self.assertEqual(mage.chosen_name, "Test Blast")   # 4 copies beat Grizzly Bears' 0

    def test_choose_name_needs_the_source_on_the_battlefield(self):
        mage = Permanent(BEAR, self.a)                     # not put onto the battlefield
        mage.chosen_name = ""
        resolve(self.game, self.a, Effect("choose_name"), StackItem(self.a, [], [], source=mage))
        self.assertEqual(mage.chosen_name, "")

    def test_named_cast_ban_in_can_cast_now(self):
        self.assertTrue(self.game.can_cast_now(self.b, BLAST))
        mage = self.mage("Test Blast")
        self.assertFalse(self.game.can_cast_now(self.b, BLAST))
        self.a.battlefield.remove(mage)                    # the mage leaving lifts the ban
        self.assertTrue(self.game.can_cast_now(self.b, BLAST))
        self.a.battlefield.append(mage)
        self.mage("Grizzly Bears")                         # a second mage names something else
        self.assertFalse(self.game.can_cast_now(self.b, BLAST))
