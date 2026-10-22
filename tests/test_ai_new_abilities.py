"""AI use of the new abilities: protective activations in response to removal, turning face-down creatures up
in combat, and the unleash / riot choices."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

MOTHER = card("Test Mother", "{W}", "Creature — Human Cleric",
              "{T}: Target creature you control gains protection from the color of your choice until end of turn.", 1, 1)
HEALER = card("Test Healer", "{1}{W}", "Creature — Human Cleric",
              "{T}: Prevent the next 1 damage that would be dealt to any target this turn.", 1, 1)
BOLT = card("Test Bolt", "{R}", "Instant", "~ deals 3 damage to any target.")
MORPH = card("Test Morph", "{4}{G}{G}", "Creature — Beast", "Morph {G}", 6, 6)
THUG = card("Test Thug", "{1}{R}", "Creature — Human Warrior", "Unleash", 2, 2)
RIOTER = card("Test Rioter", "{1}{R}", "Creature — Goblin", "Riot", 2, 2)
GIANT = card("Test Giant", "{4}", "Creature — Giant", "", 4, 4)
ELF = card("Test Iron-Shield Elf", "{1}{B}", "Creature — Elf Warrior",
           "Discard a card: ~ gains indestructible until end of turn. Tap it.", 3, 1)
DOOM = card("Test Doom", "{1}{B}", "Instant", "Destroy target creature.")


class AINewAbilities(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 1
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20

    def put(self, who, c, n=1):
        for _ in range(n):
            perm = self.game.enter_battlefield(who, c)
            perm.sick = False
        self.game.settle()
        return perm

    def removal(self, spell, target):
        self.game.stack.append(StackItem(self.b, list(spell.spell_effects), [target], card=spell))
        self.game.run_priority()

    def test_mother_protects_from_colored_removal(self):
        bear = self.put(self.a, BEAR)
        self.put(self.a, MOTHER)
        self.removal(BOLT, bear)
        self.assertIn(bear, self.a.battlefield)
        self.assertTrue(bear.has("protection from red"))

    def test_prevention_shield_saves_from_exact_damage(self):
        bear = self.put(self.a, card("Test Bear 3", "{2}", "Creature — Bear", "", 2, 3))
        self.put(self.a, HEALER)
        self.removal(BOLT, bear)
        self.assertIn(bear, self.a.battlefield)
        self.assertEqual(bear.damage, 2)

    def test_self_indestructible_against_destroy(self):
        elf = self.put(self.a, ELF)
        self.a.hand[:] = [ISLAND]
        self.removal(DOOM, elf)
        self.assertIn(elf, self.a.battlefield)
        self.assertEqual(self.a.hand, [])

    def test_face_down_creature_turned_up_in_combat(self):
        self.a.ai = Scripted()
        self.b.ai = Scripted()
        self.game.active_idx = 0
        self.put(self.a, card("Test Forest", "", "Basic Land — Forest", "({T}: Add {G}.)"))
        morph = self.put(self.a, BEAR)
        morph.hidden, morph.card = MORPH, morph.card
        giant = self.put(self.b, GIANT)
        self.a.ai.attack, self.b.ai.block = [morph], {morph: [giant]}
        self.game.combat(self.a, self.b)
        self.game.settle()
        self.assertEqual(morph.card.name, MORPH.name)
        self.assertIn(morph, self.a.battlefield)
        self.assertNotIn(giant, self.b.battlefield)

    def test_unleash_keeps_a_blocker_when_low(self):
        self.assertEqual(self.put(self.a, THUG).p1, 1)
        self.a.life = 6
        self.put(self.b, GIANT)
        self.assertEqual(self.put(self.a, THUG).p1, 0)

    def test_riot_takes_the_counter_into_a_wall(self):
        self.game.active_idx = 0
        rioter = self.put(self.a, RIOTER)
        self.assertTrue(rioter.has("haste"))
        self.put(self.b, GIANT)
        rioter = self.put(self.a, RIOTER)
        self.assertEqual(rioter.p1, 1)


if __name__ == "__main__":
    unittest.main()
