"""Independent cost/target pairs for real cards with multiple Equip abilities."""
import dataclasses
import random
import unittest
from unittest.mock import patch

from mtgsim import copies
from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.cards import Effect, EquipCost, make_token
from mtgsim.engine import Game, Permanent, Player, equip_all
from tests.test_templates import BEAR, DRAGON3, ISLAND, MOUNTAIN, card

LEGEND = card("Test Legendary", "{W}", "Legendary Creature — Human Soldier", "", 2, 2)
SOLDIER = card("Test Soldier", "{W}", "Creature — Human Soldier", "", 1, 1)
KNIGHT = card("Test Knight", "{W}", "Creature — Human Knight", "", 1, 1)
PLAINS = card("Plains", "", "Basic Land — Plains", "{T}: Add {W}.")
BOUNCE = card("Test Bounce", "{U}", "Instant", "Return target creature to its owner's hand.")


class EquipTargetParsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ALL_CARDS.exists():
            raise unittest.SkipTest("card database not built")
        cls.db = CardDB(offline=True)

    def test_real_restricted_abilities_keep_printed_order_and_costs(self):
        cases = {
            "Ace's Baseball Bat": ("legendary", 1, 3),
            "Blackblade Reforged": ("legendary", 3, 7),
            "Brotherhood Regalia": ("legendary", 1, 3),
            "Wrecking Ball Arm": ("legendary", 3, 7),
            "Steelclaw Lance": ("subtype:Knight", 1, 3),
            "Bilbo's Ring": ("subtype:Halfling", 1, 4),
            "Ceremonial Groundbreaker": ("subtype:Citizen", 1, 3),
            "Dúnedain Blade": ("subtype:Human", 1, 3),
            "Hulkbuster Armor": ("subtype:Hero", 3, 6),
            "Lothlórien Blade": ("subtype:Elf", 2, 5),
            "Pirate Hat": ("subtype:Pirate", 1, 2),
            "Thinking Cap": ("subtype:Detective", 1, 3),
            "Wizard's Staff": ("subtype:Wizard", 1, 3),
            "Team Pennant": ("token", 1, 3),
        }
        for name, (restriction, cheap, normal) in cases.items():
            with self.subTest(name=name):
                c = self.db.get(name)
                self.assertEqual(c.equip_abilities, (EquipCost({"generic": cheap}, False, restriction),
                                                    EquipCost({"generic": normal})))
                self.assertFalse(any(s.startswith("Equip ") for s in c.unsupported))
        c = self.db.get("Excalibur, Sword of Eden")
        self.assertEqual(c.equip_abilities, (EquipCost({"generic": 2}, False, "legendary"),))
        c = self.db.get("Robe of the Archmagi")
        self.assertEqual(c.equip_abilities, (EquipCost({"generic": 4}),
                          EquipCost({"generic": 1}, False, "subtype:Shaman|Warlock|Wizard")))
        self.assertEqual(self.db.get("Veteran's Powerblade").equip_abilities,
                         (EquipCost({"generic": 0, "W": 1}, False, "subtype:Soldier"),
                          EquipCost({"generic": 2})))

    def test_unknown_restrictions_and_payment_components_stay_visible(self):
        for line in ("Equip commander {1}", "Equip worthy creature {1}", "Equip creature with flying {1}",
                     "Equip Soldier with power 2 or less {1}", "Equip Mystery {1}",
                     "Equip legendary creature {1}. Activate only once each turn.",
                     "Equip Soldier {E}", "Equip Knight {W/U}", "Equip Soldier {X}",
                     "Equip legendary creature {1} or {2}"):
            with self.subTest(line=line):
                c = card("Unknown restriction", "", "Artifact — Equipment", line + "\nEquip {3}")
                self.assertIn(line, c.unsupported)
                self.assertEqual(c.equip_abilities, (EquipCost({"generic": 3}),))
        for name in ("Commander's Plate", "Unstable Molecule Suit"):
            c = self.db.get(name)
            self.assertTrue(any(s.startswith("Equip commander") for s in c.unsupported))

    def test_legendary_metadata_and_copy_exceptions(self):
        c = self.db.get("Isamaru, Hound of Konda")
        self.assertTrue(c.legendary)
        self.assertFalse(BEAR.legendary)
        self.assertTrue(copies.make_copy(c, {}).legendary)
        for text in ("it isn't legendary", "it is not legendary", "it's not legendary"):
            self.assertFalse(copies.make_copy(c, copies.parse_except(text)).legendary)
        self.assertTrue(copies.make_copy(BEAR, copies.parse_except("it's legendary")).legendary)
        mods = copies.parse_except("it's a 2/2 legendary Human")
        self.assertIsNotNone(mods)
        self.assertTrue(copies.make_copy(BEAR, mods).legendary)


class EquipTargetGameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ALL_CARDS.exists():
            raise unittest.SkipTest("card database not built")
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [ISLAND] * 30, HeuristicAI())
        self.b = Player("b", [ISLAND] * 30, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"

    def perm(self, c, p=None):
        p = self.a if p is None else p
        x = Permanent(self.db.get(c) if isinstance(c, str) else c, p)
        x.sick = False
        p.battlefield.append(x)
        return x

    def lands(self, n, c=MOUNTAIN, p=None):
        return [self.perm(c, p) for _ in range(n)]

    def pending(self, eq, host, ability=None):
        with patch.object(self.game, "settle"):
            self.assertTrue(self.game.equip(self.a, eq, host, ability=ability))
        self.assertIs(self.game.stack[-1].targets[0], host)
        return self.game.stack[-1]

    def test_legendary_host_pays_cheap_cost(self):
        eq, host = self.perm("Ace's Baseball Bat"), self.perm(LEGEND)
        lands = self.lands(3)
        self.assertTrue(self.game.equip(self.a, eq, host))
        self.assertEqual(sum(x.tapped for x in lands), 1)
        self.assertIs(eq.attached_to, host)

    def test_target_enumeration_applies_restrictions_and_controller(self):
        host = self.perm(LEGEND)
        self.perm(BEAR)
        self.perm(LEGEND, self.b)
        effect = Effect("equip", target="creature_mine", filter="legendary")
        self.assertEqual(self.game.legal_targets(self.a, effect), [host])

    def test_ordinary_host_pays_unrestricted_cost(self):
        eq, host = self.perm("Ace's Baseball Bat"), self.perm(BEAR)
        lands = self.lands(3)
        self.assertTrue(self.game.equip(self.a, eq, host))
        self.assertTrue(all(x.tapped for x in lands))
        self.assertIs(eq.attached_to, host)

    def test_illegal_cheap_target_does_not_pay_or_fall_back(self):
        eq, host = self.perm("Steelclaw Lance"), self.perm(SOLDIER)
        lands = self.lands(3)
        self.assertFalse(self.game.equip(self.a, eq, host, ability=0))
        self.assertFalse(any(x.tapped for x in lands))
        self.assertEqual(self.game.stack, [])
        self.assertIsNone(eq.attached_to)

    def test_matching_type_pays_cheap_cost(self):
        eq, host = self.perm("Steelclaw Lance"), self.perm(KNIGHT)
        lands = self.lands(3)
        self.assertTrue(self.game.equip(self.a, eq, host))
        self.assertEqual(sum(x.tapped for x in lands), 1)
        self.assertIs(eq.attached_to, host)

    def test_coloured_cost_and_unrestricted_fallback_are_independent(self):
        eq, host = self.perm("Veteran's Powerblade"), self.perm(SOLDIER)
        red = self.lands(1)
        self.assertFalse(self.game.equip(self.a, eq, host))
        self.assertFalse(red[0].tapped)
        white = self.perm(PLAINS)
        self.assertTrue(self.game.equip(self.a, eq, host))
        self.assertTrue(white.tapped)
        self.assertFalse(red[0].tapped)
        white.tapped = True
        red += self.lands(1)
        self.assertTrue(self.game.equip(self.a, eq, host))
        self.assertTrue(all(x.tapped for x in red))

    def test_routed_activation_uses_requested_ability(self):
        eq, host = self.perm("Steelclaw Lance"), self.perm(KNIGHT)
        lands = self.lands(3)
        self.assertTrue(self.game.activate(self.a, eq, "equip:1", host))
        self.assertTrue(all(x.tapped for x in lands))

    def test_no_target_selects_payable_legal_host_over_stronger_ineligible_creature(self):
        eq, host = self.perm("Steelclaw Lance"), self.perm(KNIGHT)
        self.perm(DRAGON3)
        self.lands(1)
        self.assertTrue(self.game.equip(self.a, eq))
        self.assertIs(eq.attached_to, host)

    def test_no_target_respects_explicit_ability_index(self):
        eq, host = self.perm("Steelclaw Lance"), self.perm(KNIGHT)
        self.perm(DRAGON3)
        self.lands(3)
        self.assertTrue(self.game.equip(self.a, eq, ability=0))
        self.assertIs(eq.attached_to, host)

    def test_equip_all_selects_affordable_restricted_pair(self):
        eq, host = self.perm("Ace's Baseball Bat"), self.perm(LEGEND)
        self.perm(DRAGON3)
        self.lands(1)
        equip_all(self.game, self.a)
        self.assertIs(eq.attached_to, host)

    def test_equip_all_reserve_filters_host_before_ranking(self):
        eq, host = self.perm("Ace's Baseball Bat"), self.perm(LEGEND)
        self.perm(DRAGON3)
        lands = self.lands(3)
        with patch("mtgsim.engine._reserve", return_value=2):
            equip_all(self.game, self.a)
        self.assertIs(eq.attached_to, host)
        self.assertEqual(sum(x.tapped for x in lands), 1)

    def test_custom_hook_cannot_bypass_restriction(self):
        eq, host = self.perm("Steelclaw Lance"), self.perm(BEAR)
        self.perm(KNIGHT)
        lands = self.lands(1)
        self.a.ai.choose_equip_target = lambda game, me, equipment: host
        equip_all(self.game, self.a)
        self.assertFalse(self.game.equip(self.a, eq))
        self.assertFalse(any(x.tapped for x in lands))
        self.assertIsNone(eq.attached_to)

    def test_token_restriction_uses_object_status_and_falls_back(self):
        eq, host = self.perm("Team Pennant"), self.perm(BEAR)
        token = self.perm(copies.make_copy(BEAR, {}))
        lands = self.lands(1)
        self.assertFalse(self.game.equip(self.a, eq, host))
        self.assertTrue(self.game.equip(self.a, eq, token))
        self.assertTrue(lands[0].tapped)
        self.assertIs(eq.attached_to, token)
        self.lands(3)
        self.assertTrue(self.game.equip(self.a, eq, host))
        self.assertIs(eq.attached_to, host)

    def test_token_looking_manifest_is_not_a_token(self):
        eq, host = self.perm("Team Pennant"), self.perm(make_token("Manifest", 2, 2))
        host.front = BEAR
        self.lands(1)
        self.assertFalse(self.game.equip(self.a, eq, host))

    def test_multi_subtype_or_and_changeling(self):
        eq = self.perm("Robe of the Archmagi")
        land = self.perm(MOUNTAIN)
        for subtype in ("Shaman", "Warlock", "Wizard", "Knight"):
            host = self.perm(card("Test " + subtype, "", "Creature — " + subtype, "", 1, 1))
            self.assertEqual(bool(self.game.equip_choices(self.a, eq, host)), subtype != "Knight")
        host = self.perm(card("Test Changeling", "", "Creature — Shapeshifter", "Changeling", 1, 1))
        self.assertTrue(self.game.equip(self.a, eq, host))
        self.assertTrue(land.tapped)
        self.assertFalse(host.card.legendary)

    def test_target_discount_does_not_remove_restriction(self):
        eq = self.perm("Steelclaw Lance")
        host = self.perm(dataclasses.replace(BEAR, equip_discount=4))
        self.assertFalse(self.game.equip(self.a, eq, host, ability=0))
        self.assertTrue(self.game.equip(self.a, eq, host, ability=1))
        self.assertIs(eq.attached_to, host)

    def test_target_loses_restriction_in_response_no_retarget_or_fallback(self):
        for name, definition in (("Ace's Baseball Bat", LEGEND), ("Steelclaw Lance", KNIGHT)):
            with self.subTest(name=name):
                self.setUp()
                eq, host = self.perm(name), self.perm(definition)
                other = self.perm(definition)
                lands = self.lands(3)
                item = self.pending(eq, host)
                host.card = BEAR
                self.game.settle()
                self.assertIsNone(eq.attached_to)
                self.assertEqual(sum(x.tapped for x in lands), 1)
                self.assertIs(item.targets[0], host)
                self.assertIn(other, self.a.battlefield)

    def test_unrestricted_activation_stays_unrestricted_when_host_changes_type(self):
        eq, host = self.perm("Steelclaw Lance"), self.perm(KNIGHT)
        self.lands(3)
        item = self.pending(eq, host, ability=1)
        self.assertEqual(item.effects[0].filter, "")
        host.card = BEAR
        self.game.settle()
        self.assertIs(eq.attached_to, host)

    def test_chosen_restriction_is_stored_independently_of_source_definition(self):
        eq, host = self.perm("Steelclaw Lance"), self.perm(KNIGHT)
        self.lands(1)
        item = self.pending(eq, host)
        self.assertEqual(item.effects[0].filter, "subtype:Knight")
        eq.card = dataclasses.replace(eq.card, equip_costs=(EquipCost({}),))
        host.card = BEAR
        self.game.settle()
        self.assertIsNone(eq.attached_to)

    def test_failed_re_equip_preserves_previous_attachment(self):
        eq, old, host = self.perm("Steelclaw Lance"), self.perm(BEAR), self.perm(KNIGHT)
        eq.attached_to = old
        self.lands(1)
        self.pending(eq, host)
        host.card = BEAR
        self.game.settle()
        self.assertIs(eq.attached_to, old)

    def test_restriction_only_applies_to_targeting_not_attachment(self):
        eq, host = self.perm("Ace's Baseball Bat"), self.perm(LEGEND)
        self.lands(1)
        self.assertTrue(self.game.equip(self.a, eq, host))
        host.card = BEAR
        self.game.state_based_actions()
        self.assertIs(eq.attached_to, host)

    def test_real_priority_bounce_does_not_retarget(self):
        eq, host = self.perm("Steelclaw Lance"), self.perm(KNIGHT)
        self.lands(1)
        self.lands(1, ISLAND, self.b)
        self.b.hand = [BOUNCE]
        class BounceAI(HeuristicAI):
            def respond(inner, game, me):
                if BOUNCE in me.hand and any(e.kind == "equip" for i in game.stack for e in i.effects):
                    return BOUNCE, [host]
                return None
        self.b.ai = BounceAI()
        other = self.perm(KNIGHT)
        self.assertTrue(self.game.equip(self.a, eq, host))
        self.assertIn(KNIGHT, self.a.hand)
        self.assertIsNone(eq.attached_to)
        self.assertIn(other, self.a.battlefield)

    def test_same_name_reentry_control_and_creature_type_are_rechecked(self):
        for change in ("reentry", "control", "noncreature"):
            with self.subTest(change=change):
                self.setUp()
                eq, host = self.perm("Steelclaw Lance"), self.perm(KNIGHT)
                self.lands(1)
                self.pending(eq, host)
                if change == "reentry":
                    self.game.leave_battlefield(host, "hand")
                    self.perm(KNIGHT)
                elif change == "control":
                    self.a.battlefield.remove(host)
                    self.b.battlefield.append(host)
                    host.controller = self.b
                else:
                    host.card = dataclasses.replace(KNIGHT, types=frozenset({"Artifact"}))
                self.game.settle()
                self.assertIsNone(eq.attached_to)


if __name__ == "__main__":
    unittest.main()
