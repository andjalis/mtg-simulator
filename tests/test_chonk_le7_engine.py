"""le-chonk-7 engine + foundation + AI batch.

- check_cond: the "initiative" ("if you have the initiative") and "dungeon_complete"
  ("if you've completed a dungeon") conditions (Undercellar Sweep, White Plume, ...)
- untap_step fires "becomes_untapped" when a tapped permanent untaps, so the parsed
  Dungeon Map trigger resolves at the upkeep settle
- HeuristicAI.choose_stay_tapped records the "you may choose not to untap ~" choice
  while a freeze/'doesn't untap' lock on one of the opponent's permanents stays active
- policy._mode_value consults dungeon_mechanics.effect_value alongside the
  residual/batch1 chain, and the dungeon kinds default to a conservative 1
- the PaymentPlan planner prefers a high-stat graveyard card when the payout reads the
  exiled card (Molten-Tail Masticore, Corpse Lunge)
"""
import random
import unittest

from mtgsim import dungeon_mechanics
from mtgsim import costs as planner
from mtgsim.ai import BaselineAI, HeuristicAI
from mtgsim.cards import Activated, Effect, Trigger
from mtgsim.engine import Game, Permanent, Player, StackItem
from mtgsim.engine.policy import _mode_value
from tests.test_templates import BEAR, MOUNTAIN, card

FREEZE_LOCK = card("Test Lock", "{2}", "Artifact", "")


def masticore_ability():
    return Activated("ability", {"generic": 1},
                     effects=[Effect("damage", 0, target="creature",
                                     data={"xq": ("exiled_gy", "power"), "x": True})],
                     text="{1}, Exile a creature card from your graveyard: "
                          "Test Masticore deals damage equal to the exiled card's power to target creature.",
                     extra_costs={"exile_gy_card": "creature"})


class Chonk7(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        self.g.active_idx = 0
        for p in (self.a, self.b):
            p.ai.attack, p.ai.block = (), {}

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def land(self, p, n, c=MOUNTAIN):
        out = []
        for _ in range(n):
            land = Permanent(c, p)
            land.sick = False
            out.append(land)
            p.battlefield.append(land)
        return out

    def cond(self, name):
        return self.g.check_cond(self.a, Effect("condition", cond=name),
                                 StackItem(self.a, [], []), None)


class InitiativeCond(Chonk7):
    def test_false_when_nobody_has_the_initiative(self):
        self.assertFalse(self.cond("initiative"))

    def test_true_only_for_the_holder(self):
        self.g.initiative = self.a
        self.assertTrue(self.cond("initiative"))
        self.assertFalse(self.g.check_cond(self.b, Effect("condition", cond="initiative"),
                                           StackItem(self.b, [], []), None))

    def test_taking_the_initiative_flips_the_condition(self):
        dungeon_mechanics.take_initiative(self.g, self.a)
        self.assertTrue(self.cond("initiative"))


class DungeonCompleteCond(Chonk7):
    def test_false_before_any_dungeon_is_completed(self):
        dungeon_mechanics.take_initiative(self.g, self.a)     # enters a dungeon, completes none
        self.assertFalse(self.cond("dungeon_complete"))

    def test_true_after_completing_a_dungeon(self):
        dungeon_mechanics.completed(self.g, self.a).add("Dungeon of the Mad Mage")
        self.assertTrue(self.cond("dungeon_complete"))

    def test_opponents_completions_do_not_count(self):
        dungeon_mechanics.completed(self.g, self.b).add("Lost Mine of Phandelver")
        self.assertFalse(self.cond("dungeon_complete"))


class BecomesUntapped(Chonk7):
    def _map_with_trigger(self):
        map_ = self.perm(FREEZE_LOCK, self.a)
        map_.temp_triggers.append(Trigger(event="becomes_untapped", effects=[Effect("gain_life", 2)]))
        return map_

    def test_untapping_fires_the_becomes_untapped_trigger(self):
        map_ = self._map_with_trigger()
        map_.tapped = True
        self.g.untap_step(self.a)
        self.g.settle()
        self.assertFalse(map_.tapped)
        self.assertEqual(self.a.life, 22)

    def test_an_already_untapped_permanent_does_not_fire(self):
        self._map_with_trigger()
        self.g.untap_step(self.a)
        self.g.settle()
        self.assertEqual(self.a.life, 20)

    def test_a_permanent_kept_tapped_does_not_fire(self):
        map_ = self._map_with_trigger()
        map_.tapped = True
        map_.stay_tapped = True
        self.g.untap_step(self.a)
        self.g.settle()
        self.assertTrue(map_.tapped)
        self.assertEqual(self.a.life, 20)


class StayTappedAI(Chonk7):
    def test_lock_on_the_opponent_keeps_the_source_tapped(self):
        lock = self.perm(FREEZE_LOCK, self.a)
        lock.tapped = True
        victim = self.perm(BEAR, self.b)
        victim.frozen_by = lock
        self.g.untap_step(self.a)
        self.assertTrue(lock.tapped)                        # chose not to untap
        victim.frozen_by = None
        self.g.untap_step(self.a)
        self.assertFalse(lock.tapped)                       # no lock left: untaps again

    def test_choose_stay_tapped_without_a_lock_does_nothing(self):
        lock = self.perm(FREEZE_LOCK, self.a)
        lock.tapped = True
        self.a.ai.choose_stay_tapped(self.g, self.a)
        self.assertFalse(getattr(lock, "stay_tapped", False))

    def test_baseline_ai_is_not_required_to_choose(self):
        self.a.ai = BaselineAI()
        lock = self.perm(FREEZE_LOCK, self.a)
        lock.tapped = True
        victim = self.perm(BEAR, self.b)
        victim.frozen_by = lock
        self.g.untap_step(self.a)                           # no attribute: tolerated
        self.assertFalse(lock.tapped)


class DungeonEffectValues(Chonk7):
    def tearDown(self):
        if "effect_value" in dungeon_mechanics.__dict__ and \
                not hasattr(dungeon_mechanics, "_own_effect_value"):
            del dungeon_mechanics.effect_value

    def test_dungeon_kinds_default_to_one(self):
        for kind in ("venture", "take_initiative", "die_roll", "die_amount", "die_check"):
            self.assertEqual(_mode_value(self.g, self.a, [Effect(kind, 1)]), 1)

    def test_the_module_hook_is_consulted_when_it_lands(self):
        if "effect_value" not in dungeon_mechanics.__dict__:
            dungeon_mechanics.effect_value = \
                lambda game, player, effect, target: 3 if effect.kind == "venture" else None
        self.assertEqual(_mode_value(self.g, self.a, [Effect("venture", 1)]), 3)


class GyExilePreference(Chonk7):
    def setUp(self):
        super().setUp()
        self.small = card("Test Whelp", "{R}", "Creature — Dragon", "", 1, 1)
        self.big = card("Test Dragon", "{4}{R}{R}", "Creature — Dragon", "", 7, 7)
        self.land(self.a, 3)
        self.a.graveyard = [self.small, self.big]        # the player copies these on storage

    def test_a_plain_cost_exiles_the_least_valuable_candidate(self):
        ability = Activated("ability", {"generic": 1}, effects=[Effect("draw", 1)],
                           text="{1}, Exile a creature card from your graveyard: Draw a card.",
                           extra_costs={"exile_gy_card": "creature"})
        perm = self.perm(FREEZE_LOCK, self.a)
        plan = planner.ability_plan(self.g, self.a, perm, ability, {"generic": 1})
        self.assertEqual(plan.exile_gy_card.name, self.small.name)

    def test_a_power_payout_exiles_the_biggest_candidate(self):
        perm = self.perm(FREEZE_LOCK, self.a)
        plan = planner.ability_plan(self.g, self.a, perm, masticore_ability(), {"generic": 1})
        self.assertEqual(plan.exile_gy_card.name, self.big.name)

    def test_a_spell_payout_exiles_the_biggest_candidate(self):
        lunge = card("Test Lunge", "{2}", "Instant", "")
        lunge.extra_exile_gy = "creature"
        lunge.spell_effects = [Effect("damage", 0, target="creature",
                                      data={"xq": ("exiled_gy", "power"), "x": True})]
        self.a.hand = [lunge]
        plan = planner.spell_plan(self.g, self.a, lunge, {"generic": 2})
        self.assertEqual(plan.exile_gy_card.name, self.big.name)


if __name__ == "__main__":
    unittest.main()
