"""Scaling Equipment bonuses ("for each <thing> you control") and "Equip worthy" restrictions."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.cards import Effect, EquipCost
from mtgsim.engine import Game, Permanent, Player
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

RED_LEGEND = card("Red Legend", "{1}{R}", "Legendary Creature — Human Warrior", "", 2, 2)
WHITE_LEGEND = card("White Legend", "{1}{W}", "Legendary Creature — Human Soldier", "", 2, 2)
GREEN_LEGEND = card("Green Legend", "{1}{G}", "Legendary Creature — Elf", "", 2, 2)
RED_VILLAIN = card("Red Villain", "{1}{R}", "Legendary Creature — Human Villain", "", 2, 2)
RED_NONLEGEND = card("Red Plain", "{1}{R}", "Creature — Human", "", 2, 2)
HYBRID_LEGEND = card("Hybrid Legend", "{R/G}{R/G}", "Legendary Creature — Human", "", 2, 2)
CREATURE_EQUIP = card("Test Pennon", "{1}", "Artifact — Equipment",
                      "Equipped creature gets +1/+1 for each creature you control.\nEquip {2}")
ODD_EQUIP = card("Test Odd", "{1}", "Artifact — Equipment",
                 "Equipped creature gets +1/+1 for each artifact and/or enchantment you control.\nEquip {2}")


class ScalingBonusParsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ALL_CARDS.exists():
            raise unittest.SkipTest("card database not built")
        cls.db = CardDB(offline=True)

    def test_real_cards_parse_the_counted_thing_and_scale(self):
        cases = {"Blackblade Reforged": ("land", (1, 1)), "Helm of the Gods": ("enchantment", (1, 1)),
                 "Crown of Gondor": ("creature", (1, 1)), "Pennon Blade": ("creature", (1, 1)),
                 "Adaptive Omnitool": ("artifact", (1, 1)), "Cranial Plating": ("artifact", (1, 0)),
                 "Machinist's Arsenal": ("artifact", (2, 2))}
        for name, (what, scale) in cases.items():
            with self.subTest(name=name):
                c = self.db.get(name)
                if name == "Machinist's Arsenal":
                    continue          # also says "is an Artificer": stays unsupported, not scaled
                self.assertEqual((c.equip_per, c.equip_scale), (what, scale))
                self.assertFalse(any(s.startswith("Equipped creature gets") for s in c.unsupported))

    def test_unsupported_scaling_wording_stays_visible(self):
        for name in ("Bearded Axe", "Nettlecyst", "Banshee's Blade", "Civic Saber", "Conqueror's Flail",
                     "Glaive of the Guildpact", "Manaforce Mace"):
            with self.subTest(name=name):
                c = self.db.get(name)
                self.assertEqual(c.equip_per, "")
                self.assertTrue(any("Equipped creature gets" in s for s in c.unsupported), c.unsupported)
        self.assertEqual(ODD_EQUIP.equip_per, "")
        self.assertTrue(any("Equipped creature gets" in s for s in ODD_EQUIP.unsupported))

    def test_mjolnir_worthy_is_supported_other_text_visible(self):
        c = self.db.get("Mjölnir, Hammer of Thor")
        self.assertEqual(c.equip_abilities, (EquipCost({"generic": 1}, False, "worthy"),))
        self.assertFalse(any(s.startswith("Equip worthy") for s in c.unsupported))
        self.assertIn("Double all damage equipped creature would deal.", c.unsupported)
        self.assertTrue(any("Discard this card" in s for s in c.unsupported))


class ScalingBonusGameTests(unittest.TestCase):
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

    def test_blackblade_tracks_land_count_continuously(self):
        eq, host = self.perm("Blackblade Reforged"), self.perm(BEAR)
        eq.attached_to = host
        self.assertEqual((host.power, host.toughness), (2, 2))
        lands = [self.perm(MOUNTAIN) for _ in range(3)]
        self.assertEqual((host.power, host.toughness), (5, 5))
        self.perm(MOUNTAIN)
        self.assertEqual((host.power, host.toughness), (6, 6))
        self.a.battlefield.remove(lands[0])
        self.assertEqual((host.power, host.toughness), (5, 5))
        self.perm(MOUNTAIN, self.b)                  # opponent's lands are not counted
        self.assertEqual((host.power, host.toughness), (5, 5))
        eq.attached_to = None
        self.assertEqual((host.power, host.toughness), (2, 2))

    def test_creature_count_includes_the_host_and_combines_with_other_bonuses(self):
        eq, host = self.perm(CREATURE_EQUIP), self.perm(BEAR)
        eq.attached_to = host
        self.assertEqual(host.power, 3)
        self.perm(BEAR)
        self.perm(BEAR)
        self.assertEqual((host.power, host.toughness), (5, 5))
        plate = self.perm("Plate Armor")
        plate.attached_to = host
        self.assertEqual(host.power, 8)

    def test_equipment_controller_counts_when_creature_changes_control(self):
        eq, host = self.perm("Blackblade Reforged"), self.perm(BEAR)
        for _ in range(4):
            self.perm(MOUNTAIN)
        for _ in range(2):
            self.perm(MOUNTAIN, self.b)
        eq.attached_to = host
        self.assertEqual(host.power, 6)
        self.a.battlefield.remove(host)              # the opponent gains control of the creature
        self.b.battlefield.append(host)
        host.controller = self.b
        self.assertEqual(host.power, 6)              # still the Equipment controller's four lands
        self.perm(MOUNTAIN, self.b)
        self.assertEqual(host.power, 6)
        self.perm(MOUNTAIN)
        self.assertEqual(host.power, 7)

    def test_equipment_controlled_by_opponent_counts_its_controllers_lands(self):
        eq, host = self.perm("Blackblade Reforged", self.b), self.perm(BEAR)
        for _ in range(3):
            self.perm(MOUNTAIN, self.b)
        self.perm(MOUNTAIN)
        eq.attached_to = host
        self.assertEqual(host.power, 5)


class WorthyTests(unittest.TestCase):
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

    def test_worthy_eligibility(self):
        fits = Game.equip_target_fits
        ok = (RED_LEGEND, WHITE_LEGEND)
        bad = (GREEN_LEGEND, RED_VILLAIN, RED_NONLEGEND, BEAR)
        for c in ok:
            with self.subTest(c=c.name):
                self.assertTrue(fits("worthy", Permanent(c, self.a)))
        for c in bad:
            with self.subTest(c=c.name):
                self.assertFalse(fits("worthy", Permanent(c, self.a)))
        self.assertTrue(fits("worthy", Permanent(HYBRID_LEGEND, self.a)))   # {R/G} is red

    def test_mjolnir_equip_targets_only_worthy_creatures(self):
        eq = self.perm("Mjölnir, Hammer of Thor")
        red, green, villain = self.perm(RED_LEGEND), self.perm(GREEN_LEGEND), self.perm(RED_VILLAIN)
        self.perm(RED_LEGEND, self.b)
        effect = Effect("equip", target="creature_mine", filter="worthy")
        self.assertEqual(self.game.legal_targets(self.a, effect), [red])
        for _ in range(2):
            self.perm(MOUNTAIN)
        self.assertEqual(self.game.equip_choices(self.a, eq, green), [])
        self.assertEqual(self.game.equip_choices(self.a, eq, villain), [])
        self.assertTrue(self.game.equip_choices(self.a, eq, red))
        self.assertFalse(self.game.equip(self.a, eq, green))
        self.assertFalse(any(x.tapped for x in self.a.battlefield if x.card.is_land))


if __name__ == "__main__":
    unittest.main()
