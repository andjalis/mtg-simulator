"""Multiple Equip abilities, mixed mana/sacrifice costs, cost choice, discounts and responses."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI
from mtgsim.cards import EquipCost
from mtgsim.engine import Game, Permanent, Player, equip_all
from tests.test_templates import BEAR, DRAGON3, ISLAND, MOUNTAIN, card


def equipment(name, text, bonus="Equipped creature gets +1/+1."):
    return card(name, "{1}", "Artifact — Equipment", f"{bonus}\n{text}")


MIXED = equipment("Test Mixed Blade", "Equip—{1}{R}, Sacrifice a creature.")
MIXED_AFTER = equipment("Test Mixed After", "Equip—Sacrifice a creature, {1}.")
CHOICE = equipment("Test Choice Blade", "Equip {3}\nEquip—Sacrifice a creature.")
SAC_FIRST = equipment("Test Sac First", "Equip—Sacrifice a creature.\nEquip {2}")
TWO_MANA = equipment("Test Two Mana", "Equip {4}\nEquip {1}{R}")
MAULER = card("Test Mauler", "{2}{R}", "Creature — Dwarf",
              "Equip abilities you activate that target ~ cost {2} less to activate.", 3, 3)
SAC_MANA = card("Test Sac Mana", "{G}", "Creature — Elf", "{T}, Sacrifice ~: Add one mana of any color.", 1, 1)
BOUNCE = card("Test Bounce", "{U}", "Instant", "Return target creature to its owner's hand.")
SHOCK = card("Test Shock", "{R}", "Instant", "Test Shock deals 2 damage to any target.")


class EquipCostParsingTests(unittest.TestCase):
    def test_mixed_mana_and_sacrifice_in_either_order(self):
        self.assertEqual(MIXED.unsupported, [])
        self.assertEqual(MIXED.equip_costs, (EquipCost({"generic": 1, "R": 1}, True),))
        self.assertEqual(MIXED_AFTER.unsupported, [])
        self.assertEqual(MIXED_AFTER.equip_costs, (EquipCost({"generic": 1}, True),))

    def test_multiple_abilities_kept_in_printed_order_with_legacy_first(self):
        self.assertEqual(CHOICE.unsupported, [])
        self.assertEqual(CHOICE.equip_costs, (EquipCost({"generic": 3}, False), EquipCost({}, True)))
        self.assertEqual(CHOICE.equip_cost, {"generic": 3})
        self.assertFalse(CHOICE.equip_sacrifice)
        self.assertEqual(SAC_FIRST.equip_costs[0], EquipCost({}, True))
        self.assertEqual(SAC_FIRST.equip_cost, {})
        self.assertTrue(SAC_FIRST.equip_sacrifice)
        self.assertEqual(len(TWO_MANA.equip_costs), 2)

    def test_restricted_and_unknown_lines_stay_visible_beside_supported_ones(self):
        cases = {
            "Equip commander {1}": "Equip commander {1}",
            "Equip worthy creature {W}": "Equip worthy creature {W}",
            "Equip—{2}, Pay 2 life.": "Equip—{2}, Pay 2 life.",
            "Equip—{1}, Sacrifice an artifact.": "Equip—{1}, Sacrifice an artifact.",
            "Equip—{1}, Sacrifice two creatures.": "Equip—{1}, Sacrifice two creatures.",
            "Equip—{1}, Sacrifice a creature. Activate only once each turn.":
                "Equip—{1}, Sacrifice a creature. Activate only once each turn.",
            "Equip {1} or {2}": "Equip {1} or {2}",
            "Equip {E}{E}": "Equip {E}{E}",
            "Equip {2}{S}": "Equip {2}{S}",
            "Equip {X}": "Equip {X}",
        }
        for text, line in cases.items():
            with self.subTest(text=text):
                c = equipment("Test Restricted", f"{text}\nEquip {{3}}")
                self.assertIn(line, c.unsupported)
                self.assertEqual(c.equip_costs, (EquipCost({"generic": 3}, False),))
                self.assertEqual(c.equip_cost, {"generic": 3})
                alone = equipment("Test Restricted Alone", text)
                self.assertEqual(alone.equip_costs, ())
                self.assertIsNone(alone.equip_cost)

    def test_self_reduction_keeps_full_base_cost_as_visible_approximation(self):
        reduction = "Equip {3}. This ability costs {1} less to activate for each other Equipment you control."
        c = equipment("Test Plate", f"{reduction}\nEquip—Sacrifice a creature.")
        self.assertEqual(c.unsupported, [])
        self.assertEqual(c.equip_costs, (EquipCost({"generic": 3}, False), EquipCost({}, True)))
        self.assertEqual(c.equip_cost, {"generic": 3})
        self.assertTrue(any("less to activate" in a for a in c.approximations))
        restricted = equipment("Test Leather", "Equip {0}. Activate only once each turn.")
        self.assertEqual(restricted.equip_costs, ())
        self.assertTrue(restricted.unsupported)

    def test_equip_discount_lines_are_not_equip_costs(self):
        c = equipment("Test Whip", "Equip abilities you activate of other Equipment cost {1} less to activate.\n"
                                   "Equip {3}{R}{W}")
        self.assertEqual(c.equip_costs, (EquipCost({"generic": 3, "R": 1, "W": 1}, False),))
        self.assertTrue(c.unsupported)


class EquipCostGameTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 30, HeuristicAI())
        self.b = Player("b", [ISLAND] * 30, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.a.library = [ISLAND] * 30
        self.b.library = [ISLAND] * 30

    def perm(self, c, p=None):
        p = self.a if p is None else p
        x = Permanent(c, p)
        x.sick = False
        p.battlefield.append(x)
        return x

    def lands(self, n, p=None):
        return [self.perm(MOUNTAIN, p) for _ in range(n)]

    def assert_nothing_paid(self, eq, victim, lands=()):
        self.assertIsNone(eq.attached_to)
        self.assertIn(victim, self.a.battlefield)
        self.assertEqual(self.a.sacrificed_turn, 0)
        self.assertFalse(any(x.tapped for x in lands))
        self.assertEqual(self.game.stack, [])

    # Mixed mana + sacrifice

    def test_mixed_cost_pays_both_parts(self):
        eq, host, victim = self.perm(MIXED), self.perm(DRAGON3), self.perm(BEAR)
        lands = self.lands(2)
        self.assertTrue(self.game.equip(self.a, eq, host, sacrifice=victim))
        self.assertTrue(all(x.tapped for x in lands))
        self.assertNotIn(victim, self.a.battlefield)
        self.assertIs(eq.attached_to, host)
        self.assertEqual((host.power, host.toughness), (4, 4))

    def test_mixed_cost_without_mana_does_not_sacrifice(self):
        eq, host, victim = self.perm(MIXED), self.perm(DRAGON3), self.perm(BEAR)
        lands = self.lands(1)    # {1}{R} needs two
        self.assertFalse(self.game.equip(self.a, eq, host, sacrifice=victim))
        self.assertFalse(self.game.equip(self.a, eq, host))
        self.assert_nothing_paid(eq, victim, lands)

    def test_mixed_cost_with_illegal_sacrifice_does_not_tap_mana(self):
        eq, host, victim = self.perm(MIXED), self.perm(DRAGON3), self.perm(BEAR)
        lands = self.lands(2)
        for invalid in (self.perm(BEAR, self.b), eq, lands[0]):
            with self.subTest(invalid=invalid):
                self.assertFalse(self.game.equip(self.a, eq, host, sacrifice=invalid))
                self.assert_nothing_paid(eq, victim, lands)

    def test_mixed_cost_with_no_creature_to_sacrifice_but_target(self):
        eq, host = self.perm(MIXED), self.perm(DRAGON3)
        lands = self.lands(2)
        equip_all(self.game, self.a)    # the policy keeps its only creature
        self.assertIn(host, self.a.battlefield)
        self.assertFalse(any(x.tapped for x in lands))
        self.assertTrue(self.game.equip(self.a, eq, host, sacrifice=host))   # legal, ability fizzles
        self.assertNotIn(host, self.a.battlefield)
        self.assertIsNone(eq.attached_to)

    def test_sacrifice_for_mana_creature_cannot_pay_twice(self):
        eq, host, elf = self.perm(MIXED_AFTER), self.perm(DRAGON3), self.perm(SAC_MANA)
        self.assertFalse(self.game.equip(self.a, eq, host, sacrifice=elf))
        self.assertIn(elf, self.a.battlefield)
        self.assertFalse(elf.tapped)
        self.assertEqual(self.a.sacrificed_turn, 0)
        land = self.perm(MOUNTAIN)
        self.assertTrue(self.game.equip(self.a, eq, host, sacrifice=elf))
        self.assertTrue(land.tapped)
        self.assertNotIn(elf, self.a.battlefield)
        self.assertIs(eq.attached_to, host)

    def test_sacrifice_for_mana_creature_can_pay_mana_while_another_is_sacrificed(self):
        eq, host = self.perm(MIXED_AFTER), self.perm(DRAGON3)
        elf, victim = self.perm(SAC_MANA), self.perm(BEAR)
        self.assertTrue(self.game.equip(self.a, eq, host, sacrifice=victim))
        self.assertNotIn(elf, self.a.battlefield)     # sacrificed for its mana
        self.assertNotIn(victim, self.a.battlefield)
        self.assertIs(eq.attached_to, host)

    def test_mixed_cost_paid_before_real_priority_response(self):
        eq, host, victim = self.perm(MIXED), self.perm(DRAGON3), self.perm(BEAR)
        lands = self.lands(2)
        self.perm(ISLAND, self.b)
        self.b.hand = [BOUNCE]
        test = self

        class BounceAI(HeuristicAI):
            def respond(inner, game, me):
                if BOUNCE in me.hand and any(e.kind == "equip" for i in game.stack for e in i.effects):
                    test.assertTrue(all(x.tapped for x in lands))
                    test.assertNotIn(victim, test.a.battlefield)
                    test.assertIsNone(eq.attached_to)
                    return BOUNCE, [host]
                return None

        self.b.ai = BounceAI()
        self.assertTrue(self.game.equip(self.a, eq, host, sacrifice=victim))
        self.assertIn(DRAGON3, self.a.hand)
        self.assertIn(BEAR, self.a.graveyard)
        self.assertIsNone(eq.attached_to)

    # Choosing among several Equip abilities

    def test_default_prefers_payable_mana_only_ability(self):
        eq, host, victim = self.perm(CHOICE), self.perm(DRAGON3), self.perm(BEAR)
        lands = self.lands(3)
        self.assertTrue(self.game.equip(self.a, eq, host))
        self.assertTrue(all(x.tapped for x in lands))
        self.assertIn(victim, self.a.battlefield)
        self.assertEqual(self.a.sacrificed_turn, 0)
        self.assertIs(eq.attached_to, host)

    def test_default_falls_back_to_sacrifice_when_mana_is_short(self):
        eq, host, victim = self.perm(CHOICE), self.perm(DRAGON3), self.perm(BEAR)
        lands = self.lands(2)
        self.assertTrue(self.game.equip(self.a, eq, host))
        self.assertFalse(any(x.tapped for x in lands))
        self.assertNotIn(victim, self.a.battlefield)
        self.assertIs(eq.attached_to, host)

    def test_default_picks_cheapest_payable_mana_ability(self):
        eq, host = self.perm(TWO_MANA), self.perm(DRAGON3)
        lands = self.lands(4)
        self.assertTrue(self.game.equip(self.a, eq, host))
        self.assertEqual(sum(x.tapped for x in lands), 2)
        self.assertIs(eq.attached_to, host)

    def test_explicit_ability_index_is_honoured(self):
        eq, host, victim = self.perm(CHOICE), self.perm(DRAGON3), self.perm(BEAR)
        lands = self.lands(3)
        self.assertTrue(self.game.equip(self.a, eq, host, ability=1))
        self.assertFalse(any(x.tapped for x in lands))
        self.assertNotIn(victim, self.a.battlefield)
        self.assertIs(eq.attached_to, host)

    def test_explicit_unpayable_ability_does_not_fall_back(self):
        eq, host, victim = self.perm(CHOICE), self.perm(DRAGON3), self.perm(BEAR)
        lands = self.lands(2)
        self.assertFalse(self.game.equip(self.a, eq, host, ability=0))
        self.assert_nothing_paid(eq, victim, lands)

    def test_invalid_ability_index_fails_cleanly(self):
        eq, host, victim = self.perm(CHOICE), self.perm(DRAGON3), self.perm(BEAR)
        lands = self.lands(3)
        for idx in (2, -1, 99):
            with self.subTest(idx=idx):
                self.assertFalse(self.game.equip(self.a, eq, host, ability=idx))
                self.assert_nothing_paid(eq, victim, lands)

    def test_explicit_sacrifice_selects_a_sacrifice_ability(self):
        eq, host, victim = self.perm(CHOICE), self.perm(DRAGON3), self.perm(BEAR)
        lands = self.lands(3)
        self.assertTrue(self.game.equip(self.a, eq, host, sacrifice=victim))
        self.assertFalse(any(x.tapped for x in lands))
        self.assertNotIn(victim, self.a.battlefield)

    def test_explicit_sacrifice_with_mana_only_ability_is_rejected(self):
        eq, host, victim = self.perm(CHOICE), self.perm(DRAGON3), self.perm(BEAR)
        lands = self.lands(3)
        self.assertFalse(self.game.equip(self.a, eq, host, sacrifice=victim, ability=0))
        self.assert_nothing_paid(eq, victim, lands)

    def test_activate_dispatches_ability_index(self):
        eq, host, victim = self.perm(CHOICE), self.perm(DRAGON3), self.perm(BEAR)
        lands = self.lands(3)
        self.assertTrue(self.game.activate(self.a, eq, "equip:1", host))
        self.assertFalse(any(x.tapped for x in lands))
        self.assertNotIn(victim, self.a.battlefield)
        victim = self.perm(BEAR)
        self.assertTrue(self.game.activate(self.a, eq, "equip:0", host))
        self.assertTrue(all(x.tapped for x in lands))
        self.assertIn(victim, self.a.battlefield)
        self.assertFalse(self.game.activate(self.a, eq, "equip:5", host))

    def test_plain_equip_activation_still_works(self):
        eq, host = self.perm(CHOICE), self.perm(DRAGON3)
        self.lands(3)
        self.assertTrue(self.game.activate(self.a, eq, "equip", host))
        self.assertIs(eq.attached_to, host)

    def test_timing_still_checked_for_every_ability(self):
        eq, host, victim = self.perm(CHOICE), self.perm(DRAGON3), self.perm(BEAR)
        lands = self.lands(3)
        self.game.step = "declare_attackers"
        for idx in (None, 0, 1):
            self.assertFalse(self.game.equip(self.a, eq, host, ability=idx))
        self.assert_nothing_paid(eq, victim, lands)

    # Discounts

    def test_discount_reduces_generic_only_and_keeps_colour_and_sacrifice(self):
        eq, mauler = self.perm(MIXED), self.perm(MAULER)
        self.assertEqual(self.game.equip_cost(eq, mauler), {"generic": 0, "R": 1})
        victim = self.perm(BEAR)
        land = self.perm(MOUNTAIN)
        self.assertTrue(self.game.equip(self.a, eq, mauler))
        self.assertTrue(land.tapped)
        self.assertNotIn(victim, self.a.battlefield)
        self.assertIs(eq.attached_to, mauler)

    def test_discount_applies_per_ability(self):
        eq, mauler, victim = self.perm(CHOICE), self.perm(MAULER), self.perm(BEAR)
        self.assertEqual(self.game.equip_cost(eq, mauler, 0).get("generic"), 1)
        self.assertEqual(self.game.equip_cost(eq, mauler, 1).get("generic", 0), 0)
        land = self.perm(MOUNTAIN)
        self.assertTrue(self.game.equip(self.a, eq, mauler))   # {3}-2 is payable: no sacrifice
        self.assertTrue(land.tapped)
        self.assertIn(victim, self.a.battlefield)

    def test_discount_does_not_make_other_targets_cheaper(self):
        eq, host, victim = self.perm(CHOICE), self.perm(DRAGON3), self.perm(BEAR)
        self.perm(MAULER)
        lands = self.lands(1)
        self.assertTrue(self.game.equip(self.a, eq, host, ability=1))
        self.assertFalse(lands[0].tapped)
        self.assertEqual(self.game.equip_cost(eq, host, 0), {"generic": 3})

    # The default equip_all policy

    def test_equip_all_uses_mana_alternative_when_affordable(self):
        eq, host, victim = self.perm(CHOICE), self.perm(DRAGON3), self.perm(BEAR)
        self.lands(3)
        equip_all(self.game, self.a)
        self.assertIs(eq.attached_to, host)
        self.assertIn(victim, self.a.battlefield)

    def test_equip_all_respects_reserve_across_alternatives(self):
        eq, host, victim = self.perm(CHOICE), self.perm(DRAGON3), self.perm(BEAR)
        lands = self.lands(3)
        self.a.hand = [SHOCK]     # keeps {1} open, so {3} is not spare
        equip_all(self.game, self.a)
        self.assertIs(eq.attached_to, host)
        self.assertFalse(any(x.tapped for x in lands))
        self.assertNotIn(victim, self.a.battlefield)

    def test_equip_all_mixed_cost_respects_reserve(self):
        eq, host, victim = self.perm(MIXED), self.perm(DRAGON3), self.perm(BEAR)
        lands = self.lands(2)
        self.a.hand = [SHOCK]
        equip_all(self.game, self.a)
        self.assert_nothing_paid(eq, victim, lands)
        self.a.hand = []
        equip_all(self.game, self.a)
        self.assertIs(eq.attached_to, host)
        self.assertNotIn(victim, self.a.battlefield)

    def test_equip_all_keeps_sole_creature_with_sacrifice_alternatives(self):
        eq, host = self.perm(CHOICE), self.perm(DRAGON3)
        lands = self.lands(2)
        equip_all(self.game, self.a)
        self.assertIn(host, self.a.battlefield)
        self.assertIsNone(eq.attached_to)
        self.assertFalse(any(x.tapped for x in lands))

    def test_pending_equip_blocks_second_ability(self):
        eq, host, victim = self.perm(CHOICE), self.perm(DRAGON3), self.perm(BEAR)
        self.lands(3)
        with patch.object(self.game, "settle"):
            self.assertTrue(self.game.equip(self.a, eq, host, ability=0))
            self.assertFalse(self.game.equip(self.a, eq, host, ability=1))
        self.assertIn(victim, self.a.battlefield)


class RealEquipmentCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        from mtgsim import carddb
        path = os.path.join(os.path.dirname(carddb.__file__), "data", "cards.sqlite3")
        if not os.path.exists(path):
            raise unittest.SkipTest("card database not built")
        cls.db = carddb.CardDB(offline=True)

    def test_restricted_alternatives_keep_their_own_target_filters(self):
        bat = self.db.get("Ace's Baseball Bat")
        self.assertEqual(bat.equip_costs, (EquipCost({"generic": 1}, False, "legendary"),
                                          EquipCost({"generic": 3})))
        self.assertNotIn("Equip legendary creature {1}", bat.unsupported)
        blade = self.db.get("Veteran's Powerblade")
        self.assertEqual(blade.equip_costs, (EquipCost({"generic": 0, "W": 1}, False, "subtype:Soldier"),
                                            EquipCost({"generic": 2})))
        self.assertNotIn("Equip Soldier {W}", blade.unsupported)

    def test_transform_faces_keep_their_own_equip_cost(self):
        heirloom = self.db.get("Neglected Heirloom")
        self.assertEqual(heirloom.equip_costs, (EquipCost({"generic": 1}, False),))
        self.assertEqual(heirloom.back.equip_costs, (EquipCost({"generic": 3}, False),))

    def test_plate_armor_pays_full_printed_cost(self):
        plate = self.db.get("Plate Armor")
        self.assertEqual(plate.equip_costs, (EquipCost({"generic": 3}, False),))
        self.assertTrue(any("less to activate" in a for a in plate.approximations))

    def test_unsupported_real_costs_stay_visible(self):
        for name in ("Piston Sledge", "Shredder's Armor", "My Precious", "Inventor's Axe"):
            with self.subTest(name=name):
                c = self.db.get(name)
                self.assertEqual(c.equip_costs, ())
                self.assertTrue(any(line.startswith("Equip") for line in c.unsupported))


if __name__ == "__main__":
    unittest.main()
