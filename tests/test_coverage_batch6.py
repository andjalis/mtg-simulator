"""Coverage batch: exert triggers and riders, damage prevention (Circles, Spheres, Phantoms, self shields),
coloured spell taxes, two-word cost reductions and land Auras."""
import random
import unittest

from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

TWINS = card("Test Twins", "{4}{R}", "Creature — Jackal Warrior", "You may exert ~ as it attacks.\nWhenever you exert a "
             "creature, creatures you control get +1/+0 until end of turn.", 4, 4)
CHAMPION = card("Test Champion", "{2}{R}{W}", "Creature — Human Warrior", "You may exert ~ as it attacks. When you do, untap "
                "all other creatures you control.", 4, 4)
GLORY = card("Test Glory", "{3}{R}{R}", "Creature — Dragon", "Flying, haste\nYou may exert ~ as it attacks. When you do, it "
             "deals 4 damage to target non-Dragon creature an opponent controls.", 4, 4)
AVENGER = card("Test Avenger", "{1}{W}", "Creature — Human Warrior", "You may exert ~ as it attacks. When you do, prevent all "
               "combat damage that would be dealt to it this turn.", 3, 1)
COP = card("Test Circle", "{1}{W}", "Enchantment", "{1}: The next time a red source of your choice would deal damage to you "
           "this turn, prevent that damage.")
SPHERE = card("Test Sphere", "{3}", "Artifact", "If a red source would deal damage to you, prevent 2 of that damage.")
PHANTOM = card("Test Phantom", "{3}{G}", "Creature — Spirit", "~ enters with three +1/+1 counters on it.\nIf damage would be "
               "dealt to ~, prevent that damage. Remove a +1/+1 counter from ~.", 0, 0)
KNIGHT = card("Test Oathsworn", "{1}{B}{B}", "Creature — Human Knight", "~ enters with four +1/+1 counters on it.\nIf damage "
              "would be dealt to ~ while it has a +1/+1 counter on it, prevent that damage and remove a +1/+1 counter from it.",
              1, 1)
DAWN = card("Test Dawn", "{W}{W}{W}{W}", "Creature — Elemental", "Flying\nPrevent all damage that would be dealt to ~.", 3, 3)
PALM = card("Test Palm", "{W}", "Instant", "The next time a source of your choice would deal damage to you this turn, prevent "
            "that damage.")
LEECH = card("Test Leech", "{1}{R}", "Creature — Leech", "Red spells you cast cost {R} more to cast.", 2, 2)
MONUMENT = card("Test Monument", "{3}", "Legendary Artifact", "White creature spells you cast cost {1} less to cast.")
SEAS = card("Test Seas", "{1}{U}", "Enchantment — Aura", "Enchant land\nEnchanted land is an Island.")
GROWTH = card("Test Growth", "{G}", "Enchantment — Aura", "Enchant land\nEnchanted land has \"{T}: Add one mana of any color.\"")
BOLT = card("Test Bolt", "{R}", "Instant", "~ deals 3 damage to any target.")
ALL = (TWINS, CHAMPION, GLORY, AVENGER, COP, SPHERE, PHANTOM, KNIGHT, DAWN, PALM, LEECH, MONUMENT, SEAS, GROWTH)


class CoverageBatch6(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c, n=1):
        for _ in range(n):
            perm = self.game.enter_battlefield(who, c)
            perm.sick = False
        self.game.settle()
        return perm

    def attack_trigger(self, perm, target=None):
        item = StackItem(self.a, [], [], source=perm)
        for e in perm.card.triggers[0].effects:
            self.game.resolve(self.a, e, target if e.target not in ("self", "none") else perm, item=item)
        self.game.settle()

    def test_templates(self):
        for c in ALL:
            self.assertEqual(c.unsupported, [], c.name)
        self.assertIn("exert: always exerted when it attacks", TWINS.approximations)

    def test_exert_trigger_and_riders(self):
        twins, bear = self.put(self.a, TWINS), self.put(self.a, BEAR)
        self.attack_trigger(twins)
        self.assertEqual((twins.skip_untap, bear.power), (1, 3))
        champion = self.put(self.a, CHAMPION)
        bear.tapped = champion.tapped = True
        self.attack_trigger(champion)
        self.assertFalse(bear.tapped)
        self.assertTrue(champion.tapped)
        glory = self.put(self.a, GLORY)
        eff = GLORY.triggers[0].effects[1]
        mine, dragon = self.put(self.a, BEAR), self.put(self.b, card("Test Drake", "{2}", "Creature — Dragon", "", 2, 2))
        theirs = self.put(self.b, BEAR)
        self.assertEqual(self.game.legal_targets(self.a, eff), [theirs])
        self.assertNotIn(mine, self.game.legal_targets(self.a, eff))
        self.assertNotIn(dragon, self.game.legal_targets(self.a, eff))
        self.assertIsNotNone(glory)

    def test_combat_shield(self):
        avenger = self.put(self.a, AVENGER)
        self.attack_trigger(avenger)
        self.game.deal_damage(avenger, 3, by=self.b, source=self.put(self.b, BEAR), combat=True)
        self.assertIn(avenger, self.a.battlefield)

    def test_player_prevention(self):
        self.put(self.a, SPHERE)
        self.game.deal_damage(self.a, 3, by=self.b, source=BOLT)
        self.assertEqual(self.a.life, 19)
        self.game.deal_damage(self.a, 3, by=self.b, source=BEAR)      # green: the Sphere doesn't care
        self.assertEqual(self.a.life, 16)
        self.put(self.a, COP)
        self.put(self.a, MOUNTAIN)
        self.game.deal_damage(self.a, 5, by=self.b, source=BOLT)
        self.assertEqual(self.a.life, 16)
        self.game.deal_damage(self.a, 5, by=self.b, source=BOLT)      # no mana left for the Circle
        self.assertEqual(self.a.life, 13)
        self.game.resolve(self.a, PALM.spell_effects[0], None)
        self.game.deal_damage(self.a, 4, by=self.b, source=BEAR)
        self.assertEqual(self.a.life, 13)

    def test_self_prevention(self):
        phantom, knight, dawn = self.put(self.a, PHANTOM), self.put(self.a, KNIGHT), self.put(self.a, DAWN)
        for x in (phantom, knight, dawn):
            self.game.deal_damage(x, 3, by=self.b, source=BOLT)
        self.game.settle()
        self.assertEqual((phantom.p1, knight.p1, dawn.damage), (2, 3, 0))

    def test_coloured_tax_and_two_word_discount(self):
        self.put(self.a, LEECH)
        self.assertEqual(self.game.cost_of(self.a, BOLT).get("R"), 2)
        self.put(self.a, MONUMENT)
        knight = card("Test White Knight", "{2}{W}", "Creature — Knight", "", 2, 2)
        self.assertEqual(self.game.cost_of(self.a, knight)["generic"], 1)
        self.assertEqual(self.game.cost_of(self.a, card("Test Ghost", "{2}{B}", "Creature — Spirit", "", 2, 2))["generic"], 2)

    def test_land_auras(self):
        from mtgsim import auras
        mountain = self.put(self.b, MOUNTAIN)
        seas = self.put(self.a, SEAS)
        auras.attach(self.game, seas, mountain)
        self.assertEqual(mountain.card.produces, frozenset("U"))
        self.assertIn("Island", mountain.card.subtypes)
        auras.detach(seas)
        self.assertEqual(mountain.card.produces, frozenset("R"))
        land = self.put(self.a, ISLAND)
        auras.attach(self.game, self.put(self.a, GROWTH), land)
        self.assertEqual(land.granted_mana(), frozenset("WUBRG"))
        self.assertFalse(GROWTH.aura_hostile)
        self.assertTrue(SEAS.aura_hostile)


if __name__ == "__main__":
    unittest.main()
