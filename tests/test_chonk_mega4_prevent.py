"""mega-batch4 (5): prevention shields with "If damage is prevented this way" riders.

Acolyte's Reward — "Prevent the next X damage that would be dealt to target creature this
turn, where X is your devotion to white. If damage is prevented this way, ~ deals that much
damage to any target." — parses into one ``prevent_shield`` effect carrying the rider. The
kind sizes the shield (literal, devotion or the X paid), adds ``prevent_next`` to the
shielded permanent, and installs the rider as a temporary ``damage_prevented`` trigger there;
the le-batch5 event (fired to the shield holder with event_amount) then deals "that much".
"""
import unittest

from mtgsim.cards import Effect, Trigger, _parse_effects
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_batch1 import Batch1
from tests.test_templates import BEAR, ISLAND, card

REWARD = card("Test Reward", "{1}{W}", "Instant",
              "Prevent the next X damage that would be dealt to target creature this turn, "
              "where X is your devotion to white. If damage is prevented this way, "
              "Test Reward deals that much damage to any target.")
DEVOTEE = card("Test Devotee", "{W}{W}", "Creature — Cleric", "", 1, 2)


class PreventShieldParse(unittest.TestCase):
    def test_acolytes_reward_wording(self):
        self.assertEqual(REWARD.unsupported, [])
        (shield,) = REWARD.spell_effects
        self.assertEqual(shield.kind, "prevent_shield")
        self.assertEqual(shield.target, "creature")
        self.assertEqual(shield.data["devotion"], "W")
        (rider,) = shield.data["rider"]
        self.assertEqual((rider.kind, rider.target, rider.data["that_much"]),
                         ("damage", "any", True))

    def test_literal_shield_with_rider(self):
        effects, bad = _parse_effects(
            "Prevent the next 3 damage that would be dealt to target creature this turn. "
            "If damage is prevented this way, ~ deals that much damage to target creature.")
        self.assertFalse(bad, bad)
        (shield,) = effects
        self.assertEqual((shield.kind, shield.amount), ("prevent_shield", 3))
        self.assertEqual(shield.data["rider"][0].target, "creature")

    def test_player_shield_with_rider(self):
        effects, bad = _parse_effects(
            "Prevent the next X damage that would be dealt to you this turn. "
            "If damage is prevented this way, ~ deals that much damage to target player.")
        self.assertFalse(bad, bad)
        (shield,) = effects
        self.assertEqual((shield.kind, shield.target, shield.data["x"]),
                         ("prevent_shield", "none", True))


class PreventShieldBehavior(Batch1):
    def setUp(self):
        super().setUp()
        self.effects, bad = _parse_effects(
            "Prevent the next X damage that would be dealt to target creature this turn, "
            "where X is your devotion to white. If damage is prevented this way, "
            "~ deals that much damage to any target.")
        self.assertFalse(bad, bad)

    def resolve_reward(self, target):
        item = StackItem(self.a, self.effects, [target], card=REWARD)
        self.g.resolve(self.a, self.effects[0], target, item)
        return item

    def test_shield_sized_by_devotion(self):
        self.g.enter_battlefield(self.a, DEVOTEE)
        bear = self.g.enter_battlefield(self.a, BEAR)
        self.resolve_reward(bear)
        self.assertEqual(bear.prevent_next, 2)      # two {W} among permanents a controls

    def test_rider_deals_the_prevented_amount(self):
        self.g.enter_battlefield(self.a, DEVOTEE)
        bear = self.g.enter_battlefield(self.a, BEAR)
        self.resolve_reward(bear)
        attacker = self.g.enter_battlefield(self.b, BEAR)
        life = self.b.life
        self.g.deal_damage(bear, 5, by=self.b, cause="test", source=attacker, combat=True)
        self.assertEqual(bear.damage, 3)            # 5 minus the 2 prevented
        self.assertEqual(bear.prevent_next, 0)
        self.g.flush_triggers()
        while self.g.stack:
            self.g.resolve_top()
            self.g.settle()
        total = attacker.damage + (life - self.b.life)
        self.assertEqual(total, 2)                  # the rider dealt that much damage

    def test_rider_stays_until_end_of_turn_and_shield_exhausts(self):
        bear = self.g.enter_battlefield(self.a, BEAR)
        self.g.enter_battlefield(self.a, DEVOTEE)
        self.resolve_reward(bear)
        attacker = self.g.enter_battlefield(self.b, BEAR)
        self.g.deal_damage(bear, 1, by=self.b, cause="test", source=attacker, combat=True)
        self.g.flush_triggers()
        while self.g.stack:
            self.g.resolve_top()
            self.g.settle()
        life = self.b.life
        self.g.deal_damage(bear, 2, by=self.b, cause="test", source=attacker, combat=True)
        self.g.flush_triggers()
        while self.g.stack:
            self.g.resolve_top()
            self.g.settle()
        self.assertEqual(self.b.life, life - 1)     # one more point prevented, then exhausted

    def test_player_shield_from_an_activated_x(self):
        archon = self.g.enter_battlefield(self.a, card(
            "Test Archon", "{4}{W}{W}{W}", "Creature — Archon", "", 7, 7))
        effects, bad = _parse_effects("Prevent the next X damage that would be dealt to you "
                                      "this turn. If damage is prevented this way, ~ deals "
                                      "that much damage to target player.")
        self.assertFalse(bad, bad)
        item = StackItem(self.a, effects, [None], source=archon)
        item.x = 3                                   # the X paid for the ability
        life = self.b.life
        self.g.resolve(self.a, effects[0], None, item)
        self.assertEqual(self.a.prevent_next, 3)
        attacker = self.g.enter_battlefield(self.b, BEAR)
        self.g.deal_damage(self.a, 2, by=self.b, cause="test", source=attacker, combat=True)
        self.assertEqual(self.a.life, 20)
        self.g.flush_triggers()
        while self.g.stack:
            self.g.resolve_top()
            self.g.settle()
        self.assertEqual(self.b.life, life - 2)       # the rider hit the source's controller


class PreventShieldDatabase(unittest.TestCase):

    def test_acolytes_reward_is_full(self):
        try:
            from mtgsim.carddb import CardDB
            from mtgsim.coverage import FULL, card_coverage
            db = CardDB()
        except Exception:
            self.skipTest("card database not built")
        if db._all is None:
            self.skipTest("card database not built")
        row = card_coverage(db.get("Acolyte's Reward"))
        self.assertEqual(row.status, FULL, row.ignored)


if __name__ == "__main__":
    unittest.main()
