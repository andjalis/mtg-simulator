"""Upkeep costs (pay or sacrifice, cumulative upkeep, vanishing, fading), modular, soulshift, annihilator, rampage,
backup, dash, unearth, madness, damage prevention shields and "each creature and each player" damage."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, MOUNTAIN, PLAINS, card

MIST = card("Test Mist", "{2}{G}", "Creature — Elemental",
            "At the beginning of your upkeep, sacrifice ~ unless you pay {G}{G}.", 6, 2)
REMORA = card("Test Remora", "{U}", "Enchantment", "Cumulative upkeep {1}")
RIFT = card("Test Riftwatcher", "{2}{W}", "Creature — Bird", "Flying\nVanishing 2", 2, 3)
DERM = card("Test Blastoderm", "{2}{G}{G}", "Creature — Beast", "Shroud\nFading 1", 5, 5)
WORKER = card("Test Worker", "{1}", "Artifact Creature — Construct", "Modular 2", 0, 0)
DRONE = card("Test Drone", "{2}", "Artifact Creature — Construct", "", 1, 1)
SPIRIT = card("Test Spirit", "{1}{B}", "Creature — Spirit", "Soulshift 3", 1, 1)
OLD_SPIRIT = card("Test Old Spirit", "{2}{B}", "Creature — Spirit", "", 2, 2)
CRUSHER = card("Test Crusher", "{8}", "Creature — Eldrazi", "Annihilator 2", 8, 8)
GIANT = card("Test Rampager", "{4}{G}", "Creature — Giant", "Rampage 2", 3, 3)
WARRIOR = card("Test Backup", "{2}{G}", "Creature — Human Warrior", "Backup 1\nTrample", 2, 2)
CUTTER = card("Test Heelcutter", "{3}{R}", "Creature — Goblin", "Dash {2}{R}", 3, 2)
STINGER = card("Test Hellspark", "{1}{R}", "Creature — Elemental", "Trample\nUnearth {1}{R}", 3, 1)
HUNTER = card("Test Madness", "{4}{B}", "Creature — Vampire", "Madness {B}", 5, 3)
ARCHER = card("Test Archer", "{1}{W}", "Creature — Human Cleric",
              "{T}: Prevent the next 1 damage that would be dealt to any target this turn.", 0, 2)
QUAKE = card("Test Quake", "{2}{R}", "Sorcery", "~ deals 2 damage to each creature without flying and each player.")
BIRD = card("Test Bird", "{U}", "Creature — Bird", "Flying", 1, 1)


class UpkeepKeywords(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c, n=1):
        for _ in range(n):
            perm = self.game.enter_battlefield(who, c)
            perm.sick = False
        self.game.settle()
        return perm

    def upkeep(self, p=None):
        for perm in (p or self.a).battlefield:
            perm.tapped = False
        self.game.begin_upkeep(p or self.a)
        self.game.settle()

    def fight(self, attackers, blocks=None):
        self.a.ai.attack = attackers
        self.b.ai.block = blocks or {}
        self.game.combat(self.a, self.b)
        self.game.settle()

    def test_templates(self):
        for c in (MIST, REMORA, RIFT, DERM, WORKER, SPIRIT, CRUSHER, GIANT, CUTTER, ARCHER, QUAKE):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(STINGER.unsupported, [])
        self.assertTrue(STINGER.approximations)

    def test_pay_or_sacrifice(self):
        mist = self.put(self.a, MIST)
        self.put(self.a, FOREST, 2)
        self.upkeep()
        self.assertIn(mist, self.a.battlefield)
        for x in self.a.battlefield:
            if x.card is FOREST:
                self.game.leave_battlefield(x, "hand")
        self.upkeep()
        self.assertNotIn(mist, self.a.battlefield)

    def test_cumulative_upkeep_grows(self):
        remora = self.put(self.a, REMORA)
        self.put(self.a, ISLAND, 2)
        self.upkeep()                                       # pays {1}
        self.upkeep()                                       # pays {2}
        self.assertIn(remora, self.a.battlefield)
        self.upkeep()                                       # {3}: can't
        self.assertNotIn(remora, self.a.battlefield)

    def test_vanishing_and_fading(self):
        rift, derm = self.put(self.a, RIFT), self.put(self.a, DERM)
        self.assertEqual(rift.counters["time"], 2)
        self.upkeep()
        self.assertIn(rift, self.a.battlefield)
        self.assertIn(derm, self.a.battlefield)            # fade 1 -> 0
        self.upkeep()
        self.assertNotIn(rift, self.a.battlefield)          # last time counter removed
        self.assertNotIn(derm, self.a.battlefield)          # no fade counter to remove

    def test_modular_moves_counters(self):
        worker, drone = self.put(self.a, WORKER), self.put(self.a, DRONE)
        self.assertEqual(worker.power, 2)
        self.game.destroy(worker)
        self.game.settle()
        self.assertEqual(drone.p1, 2)

    def test_soulshift(self):
        spirit = self.put(self.a, SPIRIT)
        self.a.graveyard.append(OLD_SPIRIT)
        self.game.destroy(spirit)
        self.game.settle()
        self.assertIn(OLD_SPIRIT, self.a.hand)

    def test_annihilator(self):
        crusher = self.put(self.a, CRUSHER)
        self.put(self.b, ISLAND, 3)
        self.fight([crusher])
        self.assertEqual(len(self.b.battlefield), 1)

    def test_rampage(self):
        giant = self.put(self.a, GIANT)
        bears = [self.put(self.b, BEAR), self.put(self.b, BEAR)]
        self.fight([giant], {giant: bears})
        self.assertIn(giant, self.a.battlefield)            # 5/5 against two 2/2s

    def test_backup_on_another_creature(self):
        bear = self.put(self.a, BEAR)
        self.put(self.a, WARRIOR)
        self.assertEqual(bear.p1, 1)
        self.assertTrue(bear.has("trample"))

    def test_dash_returns_to_hand(self):
        self.game.active_idx = 0
        self.put(self.a, MOUNTAIN, 3)
        self.a.hand.append(CUTTER)
        dash = next(o for o in self.game.spell_options(self.a) if self.game._origin(o)[1] == "dash")
        self.assertTrue(self.game.cast(self.a, dash))
        self.game.settle()
        perm = next(x for x in self.a.battlefield if x.card.name == CUTTER.name)
        perm.sick = True
        self.assertTrue(perm.has("haste"))
        self.game.take_turn(self.a)                         # its end step returns it
        self.assertIn(CUTTER, self.a.hand)
        self.assertFalse(any(x.card.name == CUTTER.name for x in self.a.battlefield))

    def test_unearth_from_graveyard_then_exile(self):
        self.game.active_idx = 0
        self.put(self.a, MOUNTAIN, 2)
        self.a.graveyard.append(STINGER)
        option = next(o for o in self.game.spell_options(self.a) if self.game._origin(o)[1] == "unearth")
        self.assertTrue(self.game.cast(self.a, option))
        self.game.settle()
        perm = next(x for x in self.a.battlefield if x.card.name == STINGER.name)
        self.assertTrue(perm.has("haste"))
        self.game.destroy(perm)
        self.assertIn(STINGER, self.a.exile)
        self.assertNotIn(STINGER, self.a.graveyard)

    def test_madness_after_discard(self):
        self.game.active_idx = 0
        self.put(self.a, PLAINS, 1)
        self.a.hand.append(HUNTER)
        self.assertFalse(any(self.game._origin(o)[1] == "mayhem" for o in self.game.spell_options(self.a)))
        self.game.discard_card(self.a, HUNTER)
        self.assertTrue(any(self.game._origin(o)[1] == "mayhem" for o in self.game.spell_options(self.a)))

    def test_prevention_shield(self):
        archer = self.put(self.a, ARCHER)
        self.game.resolve(self.a, ARCHER.activated[0].effects[0], archer)
        self.game.deal_damage(archer, 3, by=self.b)
        self.assertEqual(archer.damage, 2)
        self.game.resolve(self.a, ARCHER.activated[0].effects[0], self.a)
        self.game.deal_damage(self.a, 3, by=self.b)
        self.assertEqual(self.a.life, 18)

    def test_earthquake(self):
        bear, bird = self.put(self.b, BEAR), self.put(self.b, BIRD)
        self.put(self.a, MOUNTAIN, 3)
        self.a.hand.append(QUAKE)
        self.assertTrue(self.game.cast(self.a, QUAKE))
        self.game.settle()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertIn(bird, self.b.battlefield)
        self.assertEqual((self.a.life, self.b.life), (18, 18))


if __name__ == "__main__":
    unittest.main()
