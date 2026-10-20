"""Cast and cycle triggers of the card itself, "when enchanted / equipped creature dies", color and historic cast
triggers, any creature entering, "one or more creatures you control deal combat damage", each draw step, scry,
end of combat, monstrosity and protection from multicolored."""
import random
import unittest

from mtgsim.engine import Game, Player, StackItem, can_block
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

GYRE = card("Test Gyre", "{11}", "Legendary Creature — Eldrazi", "When you cast ~, destroy target permanent.", 11, 11)
MAMMOTH = card("Test Mammoth", "{5}{R}{R}", "Creature — Elephant",
               "Cycling {2}{R}\nWhen you cycle ~, ~ deals 2 damage to any target.", 9, 7)
PACT = card("Test Pact", "{1}{W}", "Enchantment — Aura", "Enchant creature\nWhen enchanted creature dies, draw a card.")
SCYTHE = card("Test Scythe", "{1}", "Artifact — Equipment", "Whenever equipped creature dies, you gain 3 life.\nEquip {1}")
PYRO = card("Test Pyro", "{1}{R}", "Enchantment", "Whenever you cast a multicolored spell, ~ deals 2 damage to any target.")
CHARM = card("Test Charm", "{U}{R}", "Instant", "Draw a card.")
TRAPPER = card("Test Trapper", "{3}{W}", "Creature — Human Archer",
               "Whenever you cast a historic spell, tap target creature an opponent controls.", 2, 3)
RELIC = card("Test Relic", "{1}", "Artifact", "")
WATCHER = card("Test Watcher", "{1}{B}", "Creature — Human", "Whenever a creature enters, you gain 1 life.", 1, 1)
BANNER = card("Test Banner", "{2}", "Artifact", "Whenever one or more creatures you control deal combat damage to a "
                                                "player, draw a card.")
LOREMASTER = card("Test Loremaster", "{2}{U}", "Creature — Human Wizard",
                  "At the beginning of each player's draw step, you gain 1 life.", 1, 1)
SEER = card("Test Seer", "{2}{U}", "Enchantment", "Whenever you scry, you gain 2 life.")
SCRY = card("Test Scry", "{U}", "Sorcery", "Scry 2.")
DRAGSTER = card("Test Dragster", "{3}", "Artifact", "At end of combat, you gain 1 life.")
MONSTER = card("Test Monster", "{2}{R}", "Creature — Dragon",
               "{1}: Monstrosity 3.\nWhen ~ becomes monstrous, ~ deals 3 damage to any target.", 2, 2)
LIEUTENANT = card("Test Lieutenant", "{3}{W}", "Creature — Human Knight", "Vigilance, protection from multicolored", 3, 4)
GOLD = card("Test Gold", "{G}{W}", "Creature — Human", "", 2, 2)


class TriggerHeads2(unittest.TestCase):
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

    def fight(self, attackers, blocks=None):
        self.a.ai.attack = attackers
        self.b.ai.block = blocks or {}
        self.game.combat(self.a, self.b)
        self.game.settle()

    def test_templates(self):
        for c in (GYRE, MAMMOTH, PACT, SCYTHE, PYRO, TRAPPER, WATCHER, BANNER, LOREMASTER, SEER, DRAGSTER, MONSTER,
                  LIEUTENANT):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertTrue(GYRE.cast_self_triggers and not GYRE.triggers)
        self.assertTrue(MAMMOTH.cycle_self_triggers)

    def test_cast_trigger_resolves_first(self):
        relic = self.put(self.b, RELIC)
        self.put(self.a, ISLAND, 11)
        self.a.hand.append(GYRE)
        self.assertTrue(self.game.cast(self.a, GYRE))
        self.game.settle()
        self.assertNotIn(relic, self.b.battlefield)

    def test_cycle_trigger(self):
        self.put(self.a, MOUNTAIN, 3)
        self.a.hand.append(MAMMOTH)
        self.game.cycle_spare(self.a)
        self.game.settle()
        self.assertEqual(self.b.life, 18)

    def test_enchanted_and_equipped_creature_dies(self):
        bear = self.put(self.a, BEAR)
        self.game._aura_host = bear
        self.put(self.a, PACT)
        scythe = self.put(self.a, SCYTHE)
        scythe.attached_to = bear
        hand = len(self.a.hand)
        self.game.destroy(bear)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 1)
        self.assertEqual(self.a.life, 23)

    def test_multicolored_and_historic_cast_triggers(self):
        self.put(self.a, PYRO)
        trapper = self.put(self.a, TRAPPER)
        bear = self.put(self.b, BEAR)
        self.a.hand += [CHARM, RELIC]
        self.put(self.a, ISLAND)
        self.put(self.a, MOUNTAIN, 2)
        self.assertTrue(self.game.cast(self.a, CHARM))
        self.game.settle()
        self.assertTrue(self.b.life == 18 or bear not in self.b.battlefield)
        self.assertTrue(self.game.cast(self.a, RELIC))
        self.game.settle()
        self.assertTrue(bear.tapped or bear not in self.b.battlefield)
        self.assertIn(trapper, self.a.battlefield)

    def test_any_creature_enters_and_draw_step(self):
        self.put(self.a, WATCHER)
        self.put(self.b, BEAR)
        self.assertEqual(self.a.life, 22)                 # itself, then the opponent's bear
        self.put(self.a, LOREMASTER)
        life = self.a.life
        self.game.take_turn(self.b)
        self.assertGreaterEqual(self.a.life, life + 1)

    def test_combat_damage_once_and_end_of_combat(self):
        self.put(self.a, BANNER)
        self.put(self.a, DRAGSTER)
        bears = [self.put(self.a, BEAR) for _ in range(2)]
        hand = len(self.a.hand)
        self.fight(bears)
        self.assertEqual(len(self.a.hand), hand + 1)       # one trigger for both hits
        self.assertEqual(self.a.life, 21)

    def test_scry_trigger(self):
        self.put(self.a, SEER)
        self.put(self.a, ISLAND)
        self.a.hand.append(SCRY)
        self.assertTrue(self.game.cast(self.a, SCRY))
        self.game.settle()
        self.assertEqual(self.a.life, 22)

    def test_monstrosity_once(self):
        monster = self.put(self.a, MONSTER)
        self.put(self.a, MOUNTAIN, 2)
        self.assertTrue(self.game.activate_ability(self.a, monster, 0))
        self.game.settle()
        self.assertEqual(monster.p1, 3)
        self.assertEqual(self.b.life, 17)
        self.game.activate_ability(self.a, monster, 0)
        self.game.settle()
        self.assertEqual(monster.p1, 3)

    def test_protection_from_multicolored(self):
        lieutenant = self.put(self.a, LIEUTENANT)
        self.assertFalse(can_block(self.put(self.b, GOLD), lieutenant))
        self.assertTrue(can_block(self.put(self.b, BEAR), lieutenant))
        self.game.stack.append(StackItem(self.b, list(CHARM.spell_effects), [None], card=CHARM))
        with self.game.targeting(CHARM):
            self.assertFalse(self.game.targetable(lieutenant, self.b))


if __name__ == "__main__":
    unittest.main()
