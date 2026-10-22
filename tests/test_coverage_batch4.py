"""Coverage batch: twice-per-turn activations, Vivid lands, two-target pumps, color-filtered removal, Fling,
creature-and-player damage, tucks, tokens for each Elf, divided damage, two-type cost reductions and Aura grants."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, card

BATS = card("Test Bats", "{B}", "Creature — Bat", "{B}: ~ gets +1/+0 until end of turn. Activate no more than twice each "
            "turn.", 0, 1)
SWAMP = card("Swamp", "", "Basic Land — Swamp", "({T}: Add {B}.)")
VIVID = card("Test Vivid", "", "Land", "~ enters tapped with two charge counters on it.\n{T}: Add {R}.\n{T}, Remove a "
             "charge counter from ~: Add one mana of any color.")
DECREE = card("Test Decree", "{1}{W}", "Sorcery", "Destroy target creature or planeswalker that's red or green.")
FLING = card("Test Fling", "{1}{R}", "Instant", "As an additional cost to cast this spell, sacrifice a creature.\n~ deals "
             "damage equal to the sacrificed creature's power to any target.")
LUNGE = card("Test Lunge", "{2}{R}", "Instant", "~ deals 2 damage to target creature and 2 damage to target player or "
             "planeswalker.")
OUST = card("Test Oust", "{W}", "Sorcery", "Put target creature into its owner's library second from the top.")
PROMENADE = card("Test Promenade", "{2}{G}", "Sorcery", "Create a 1/1 green Elf Warrior creature token for each Elf you control.")
ELF = card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)
FAMILIAR = card("Test Familiar", "{3}{U}", "Creature — Bird", "Black spells and red spells you cast cost {1} less to cast.", 1, 1)
RUNEMARK = card("Test Runemark", "{2}{W}", "Enchantment — Aura", "Enchant creature\nEnchanted creature has first strike as "
                "long as you control a red or white permanent.")
OGRE = card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)
KNIGHT = card("Test Knight", "{1}{W}", "Creature — Knight", "As long as ~ is equipped, it gets +1/+1.", 2, 2)
NOMAD = card("Test Nomad", "{1}{G}", "Creature — Human", "Threshold — As long as seven or more cards are in your graveyard, "
             "~ gets +2/+2.", 1, 1)
STALKER = card("Test Stalker", "{1}{B}", "Creature — Horror", "Delirium — ~ has flying as long as there are four or more "
               "card types among cards in your graveyard.", 2, 2)
ANGER = card("Test Anger", "{2}{R}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +2/+2 and attacks "
             "each combat if able.")
VOW = card("Test Vow", "{1}{W}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +1/+1, has flying, and "
           "can't attack you or planeswalkers you control.")
SHACKLE = card("Test Shackle", "{R}", "Enchantment — Aura", "Enchant creature\nEnchanted creature gets +2/+0 and can't block.")


class CoverageBatch4(unittest.TestCase):
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
        for c in (BATS, VIVID, DECREE, FLING, LUNGE, OUST, PROMENADE, FAMILIAR, RUNEMARK):
            self.assertEqual(c.unsupported, [], c.name)

    def test_twice_per_turn(self):
        bats = self.put(self.a, BATS)
        self.put(self.a, SWAMP, 3)
        self.assertTrue(self.game.activate_ability(self.a, bats, 0))
        self.assertTrue(self.game.activate_ability(self.a, bats, 0))
        self.assertFalse(self.game.activate_ability(self.a, bats, 0))
        self.game.settle()
        self.assertEqual(bats.power, 2)

    def test_vivid_land(self):
        land = self.game.enter_battlefield(self.a, VIVID)
        self.assertTrue(land.tapped)
        self.assertEqual(land.counters["charge"], 2)

    def test_color_filter_and_fling(self):
        ogre, bear = self.put(self.b, OGRE), self.put(self.b, card("Test White Bear", "{1}{W}", "Creature — Bear", "", 2, 2))
        legal = self.game.legal_targets(self.a, DECREE.spell_effects[0])
        self.assertIn(ogre, legal)
        self.assertNotIn(bear, legal)
        self.put(self.a, OGRE)
        self.put(self.a, MOUNTAIN, 2)
        self.a.hand[:] = [FLING]
        self.assertTrue(self.game.cast(self.a, FLING, [self.b]))
        self.game.settle()
        self.assertEqual(self.b.life, 17)

    def test_lunge_and_oust(self):
        bear = self.put(self.b, BEAR)
        for e, t in zip(LUNGE.spell_effects, (bear, self.b)):
            self.game.resolve(self.a, e, t)
        self.game.settle()
        self.assertEqual(self.b.life, 18)
        self.assertNotIn(bear, self.b.battlefield)
        ogre = self.put(self.b, OGRE)
        self.game.resolve(self.a, OUST.spell_effects[0], ogre)
        self.assertEqual(self.b.library[-2].name, OGRE.name)

    def test_token_per_elf_and_familiar(self):
        self.put(self.a, ELF, 2)
        self.game.resolve(self.a, PROMENADE.spell_effects[0], None)
        self.assertEqual(sum(x.is_creature for x in self.a.battlefield), 4)
        self.put(self.a, FAMILIAR)
        black_red = card("Test Rakdos", "{2}{B}{R}", "Sorcery", "Draw a card.")
        self.assertEqual(self.game.cost_of(self.a, black_red)["generic"], 1)    # once, not twice

    def test_runemark(self):
        from mtgsim import auras
        bear = self.put(self.a, BEAR)
        auras.attach(self.game, self.put(self.a, RUNEMARK), bear)
        self.assertTrue(bear.has("first strike"))               # the Runemark is itself white
        self.put(self.a, OGRE)
        self.assertTrue(bear.has("first strike"))

    def test_self_conditions(self):
        for c in (KNIGHT, NOMAD, STALKER, ANGER, VOW, SHACKLE):
            self.assertEqual(c.unsupported, [], c.name)
        nomad, stalker = self.put(self.a, NOMAD), self.put(self.a, STALKER)
        self.assertEqual(nomad.power, 1)
        self.assertFalse(stalker.has("flying"))
        self.a.graveyard[:] = [ISLAND] * 4 + [BEAR, FLING, RUNEMARK, BATS]
        self.assertEqual(nomad.power, 3)
        self.assertTrue(stalker.has("flying"))          # land, creature, instant, enchantment

    def test_aura_drawbacks(self):
        from mtgsim import auras
        from mtgsim.engine.state import can_block
        self.assertFalse(ANGER.aura_hostile or VOW.aura_hostile or SHACKLE.aura_hostile)
        bear, ogre = self.put(self.a, BEAR), self.put(self.b, OGRE)
        auras.attach(self.game, self.put(self.a, ANGER), bear)
        self.assertTrue(auras.must_attack(bear))
        self.assertEqual(bear.power, 4)
        auras.attach(self.game, self.put(self.a, SHACKLE), bear)
        self.assertFalse(can_block(bear, ogre))
        auras.attach(self.game, self.put(self.a, VOW), ogre)       # a's Vow on b's creature: it can't attack a
        self.assertFalse(ogre.can_attack())
        self.assertTrue(ogre.has("flying"))
        mine = self.put(self.b, OGRE)
        auras.attach(self.game, self.put(self.b, VOW), mine)       # its own controller's Vow doesn't stop it
        self.assertTrue(mine.can_attack())


if __name__ == "__main__":
    unittest.main()
