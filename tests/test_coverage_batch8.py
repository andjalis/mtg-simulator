"""Coverage batch: Mana Batteries, two-mana land Auras, "that much" amounts from life gain and damage, creature-type
combat damage triggers, battalion, and graveyard-targeting exile and shuffles."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, card

BATTERY = card("Test Battery", "{4}", "Artifact", "{2}, {T}: Put a charge counter on ~.\n{T}, Remove any number of charge "
               "counters from ~: Add {B}, then add an additional {B} for each charge counter removed this way.")
HORIZONS = card("Test Horizons", "{2}{G}", "Enchantment — Aura", "Enchant land\nWhen ~ enters, you may put a land card from "
                "your hand onto the battlefield.\nEnchanted land has \"{T}: Add two mana of any one color.\"")
BOND = card("Test Bond", "{3}{B}{B}", "Enchantment", "Whenever you gain life, target opponent loses that much life.")
SPITE = card("Test Spite", "{2}{R/G}{R/G}{R/G}", "Creature — Elemental", "Whenever ~ is dealt damage, it deals that much "
             "damage to any target.", 6, 5)
ALTISAUR = card("Test Altisaur", "{2}{G}{U}", "Creature — Dinosaur", "Flying\nWhenever a Dinosaur you control deals combat "
                "damage to a player, draw a card.", 3, 3)
SKYJEK = card("Test Skyjek", "{1}{W}", "Creature — Human Knight", "Battalion — Whenever ~ and at least two other creatures "
              "attack, ~ gains flying until end of turn.", 3, 1)
SHRED = card("Test Shred", "{1}{B}", "Instant", "Exile up to four target cards from a single graveyard.")
RENEWAL = card("Test Renewal", "{3}{G}", "Sorcery", "Target player shuffles up to four target cards from their graveyard into "
               "their library.")
ALL = (BATTERY, HORIZONS, BOND, SPITE, ALTISAUR, SKYJEK, SHRED, RENEWAL)


class CoverageBatch8(unittest.TestCase):
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

    def test_templates(self):
        for c in ALL:
            self.assertEqual(c.unsupported, [], c.name)
        self.assertIn("two mana of any one color: the land makes two mana of any colours", HORIZONS.approximations)

    def test_mana_battery(self):
        from mtgsim import storage
        battery = self.put(self.a, BATTERY)
        self.assertEqual(battery.card.produces, frozenset("B"))
        battery.counters["charge"] = 2
        self.assertEqual(len(storage.stored_sources(self.a)), 2)
        self.assertTrue(self.game.can_pay(self.a, {"B": 3}))

    def test_two_mana_aura(self):
        from mtgsim import auras
        forest = self.put(self.a, FOREST)
        auras.attach(self.game, self.put(self.a, HORIZONS), forest)
        self.assertEqual(forest.card.mana_amount, 2)
        self.assertTrue(self.game.can_pay(self.a, {"U": 2}))

    def test_that_much(self):
        self.put(self.a, BOND)
        self.game.change_life(self.a, 3, "test")
        self.game.settle()
        self.assertEqual(self.b.life, 17)
        spite = self.put(self.a, SPITE)
        self.game.deal_damage(spite, 4, by=self.b, source=self.put(self.b, BEAR))
        self.game.settle()
        self.assertTrue(self.b.life == 13 or not self.b.creatures)

    def test_subtype_combat_damage_and_battalion(self):
        trig = ALTISAUR.triggers[0]
        self.assertEqual((trig.event, trig.filter), ("ally_combat_damage", "ally_sub:Dinosaur"))
        self.put(self.a, ALTISAUR)
        self.game.fire(self.a, "ally_combat_damage", subject=self.put(self.a, BEAR))
        self.game.settle()
        self.assertEqual(len(self.a.hand), 0)
        dino = self.put(self.a, card("Test Raptor", "{1}{R}", "Creature — Dinosaur", "", 2, 1))
        self.game.fire(self.a, "ally_combat_damage", subject=dino)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual(SKYJEK.triggers[0].filter, "count>=3")
        skyjek = self.put(self.a, SKYJEK)
        self.game.attackers = [skyjek, self.put(self.a, BEAR)]
        self.game.fire(self.a, "attacks", skyjek)
        self.game.settle()
        self.assertFalse(skyjek.has("flying"))
        self.game.attackers.append(self.put(self.a, BEAR))
        self.game.fire(self.a, "attacks", skyjek)
        self.game.settle()
        self.assertTrue(skyjek.has("flying"))

    def test_graveyard_targets(self):
        self.b.graveyard[:] = [BEAR] * 5
        self.game.resolve(self.a, SHRED.spell_effects[0], None)
        self.assertEqual(len(self.b.graveyard), 1)
        self.a.graveyard[:] = [BEAR] * 6
        self.game.resolve(self.a, RENEWAL.spell_effects[0], self.a)
        self.assertEqual((len(self.a.graveyard), len(self.a.library)), (2, 24))


if __name__ == "__main__":
    unittest.main()
