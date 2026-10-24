"""Coverage batch: filtered sweepers and wraths, attacking-creature grants, sweeps of nonland permanents,
"can't be blocked except by", graveyard and hand counts, and Arrest-style Auras."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

SQUALL = card("Test Squall", "{G}", "Sorcery", "~ deals 2 damage to each creature with flying.")
CANNONADE = card("Test Cannonade", "{2}{R}", "Instant", "~ deals 2 damage to each non-Pirate creature.")
CLEANSE = card("Test Cleanse", "{2}{W}{W}", "Sorcery", "Destroy all black creatures.")
NONART = card("Test Extinction", "{4}{B}", "Sorcery", "Destroy all nonartifact creatures.")
CLEANSING = card("Test Cleansing", "{3}{W}{W}{W}", "Sorcery", "Destroy all nonland permanents.")
PEGASUS = card("Test Pegasus", "{2}{W}", "Creature — Pegasus", "Flying\nWhenever ~ attacks, target attacking creature without "
               "flying gains flying until end of turn.", 2, 2)
RANGERS = card("Test Rangers", "{2}{G}", "Creature — Elf Ranger", "~ can't be blocked except by creatures with flying.", 2, 2)
NIGHTSTALKER = card("Test Nightstalker", "{3}{B}", "Creature — Nightstalker", "~ can't be blocked except by black creatures.",
                    2, 2)
ELITE = card("Test Elite", "{2}{B}", "Creature — Zombie", "~ gets +1/+1 for each creature card in your graveyard.", 1, 1)
AUGUR = card("Test Augur", "{3}{R}", "Creature — Human Shaman", "~'s power is equal to the number of instant and sorcery "
             "cards in your graveyard.", 0, 4)
ARREST = card("Test Arrest", "{2}{W}", "Enchantment — Aura", "Enchant creature\nEnchanted creature can't attack or block, and "
              "its activated abilities can't be activated.")
FORM = card("Test Form", "{U}", "Enchantment — Aura", "Enchant creature\nEnchanted creature can't be blocked.")
SEEKER = card("Test Seeker", "{3}{G}", "Instant", "~ deals damage to target player equal to the number of cards in that "
              "player's hand.")
FLIER = card("Test Bird", "{W}", "Creature — Bird", "Flying", 1, 1)
DRAKE = card("Test Black Drake", "{1}{B}", "Creature — Drake", "", 2, 2)
ALL = (SQUALL, CANNONADE, CLEANSE, NONART, CLEANSING, PEGASUS, RANGERS, NIGHTSTALKER, ELITE, AUGUR, ARREST, FORM, SEEKER)


class CoverageBatch9(unittest.TestCase):
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

    def test_filtered_sweepers(self):
        bird, bear = self.put(self.b, FLIER), self.put(self.b, BEAR)
        self.game.resolve(self.a, SQUALL.spell_effects[0], None)
        self.game.settle()
        self.assertNotIn(bird, self.b.battlefield)
        self.assertIn(bear, self.b.battlefield)
        drake = self.put(self.b, DRAKE)
        self.game.resolve(self.a, CLEANSE.spell_effects[0], None)
        self.game.settle()
        self.assertNotIn(drake, self.b.battlefield)
        self.assertIn(bear, self.b.battlefield)
        golem = self.put(self.b, card("Test Golem", "{3}", "Artifact Creature — Golem", "", 3, 3))
        self.game.resolve(self.a, NONART.spell_effects[0], None)
        self.game.settle()
        self.assertEqual(self.b.creatures, [golem])
        land = self.put(self.b, ISLAND)
        self.game.resolve(self.a, CLEANSING.spell_effects[0], None)
        self.game.settle()
        self.assertEqual(self.b.battlefield, [land])

    def test_attacking_grant_and_evasion(self):
        from mtgsim.engine.state import can_block
        bird, bear = self.put(self.a, FLIER), self.put(self.a, BEAR)
        self.game.attackers = [bird, bear]
        self.assertEqual(self.game.legal_targets(self.a, PEGASUS.triggers[0].effects[0]), [bear])
        rangers, stalker = self.put(self.a, RANGERS), self.put(self.a, NIGHTSTALKER)
        self.assertFalse(can_block(self.put(self.b, BEAR), rangers))
        self.assertTrue(can_block(self.put(self.b, FLIER), rangers))
        self.assertTrue(can_block(self.put(self.b, DRAKE), stalker))
        self.assertFalse(can_block(self.put(self.b, BEAR), stalker))

    def test_graveyard_counts(self):
        elite, augur = self.put(self.a, ELITE), self.put(self.a, AUGUR)
        bolt = card("Test Bolt", "{R}", "Instant", "Draw a card.")
        self.a.graveyard[:] = [BEAR, BEAR, bolt, ISLAND]
        self.assertEqual((elite.power, elite.toughness), (3, 3))
        self.assertEqual((augur.power, augur.toughness), (1, 4))

    def test_auras_and_hand_damage(self):
        from mtgsim import auras
        pinger = self.put(self.b, card("Test Pinger", "{1}{R}", "Creature — Human", "{T}: ~ deals 1 damage to any target.", 1, 1))
        auras.attach(self.game, self.put(self.a, ARREST), pinger)
        self.assertFalse(self.game.can_activate(self.b, pinger, 0))
        self.assertFalse(pinger.can_attack())
        bear = self.put(self.a, BEAR)
        auras.attach(self.game, self.put(self.a, FORM), bear)
        self.assertTrue(bear.has("unblockable"))
        self.b.hand[:] = [BEAR] * 4
        self.game.resolve(self.a, SEEKER.spell_effects[0], self.b)
        self.assertEqual(self.b.life, 16)


if __name__ == "__main__":
    unittest.main()
