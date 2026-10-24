"""Coverage batch: Arc Trail, "another target" grants, Hardened Scales, base P/T and Frog effects, library-top
effects, attacking-creature damage, keyword loss, Quietus Spike, Fated scry, Sandskin and smaller templates."""
import random
import unittest

from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

TRAIL = card("Test Trail", "{1}{R}", "Sorcery", "~ deals 2 damage to any target and 1 damage to any other target.")
COURSER = card("Test Courser", "{2}{W}", "Creature — Pegasus", "Flying\nWhenever ~ attacks, another target attacking creature "
               "gains flying until end of turn.", 1, 3)
SCALES = card("Test Scales", "{G}", "Enchantment", "If one or more +1/+1 counters would be put on a creature you control, that "
              "many plus one +1/+1 counters are put on it instead.")
DIMINISH = card("Test Diminish", "{U}", "Instant", "Target creature has base power and toughness 1/1 until end of turn.")
ABOUT = card("Test About Face", "{R}", "Instant", "Switch target creature's power and toughness until end of turn.")
TURN = card("Test Turn to Frog", "{1}{U}", "Instant", "Until end of turn, target creature loses all abilities and becomes a "
            "blue Frog with base power and toughness 1/1.")
FROGIFY = card("Test Frogify", "{1}{U}", "Enchantment — Aura", "Enchant creature\nEnchanted creature loses all abilities and "
               "is a blue Frog creature with base power and toughness 1/1.")
RECLAIM = card("Test Reclaim", "{G}", "Instant", "Put target card from your graveyard on top of your library.")
GUILDMAGE = card("Test Guildmage", "{U}", "Creature — Human Wizard", "{U}, {T}: Put target creature you control on top of its "
                 "owner's library.", 1, 1)
SHARDS = card("Test Shards", "{W}", "Instant", "~ deals 1 damage to each attacking creature.")
VERTIGO = card("Test Vertigo", "{R}", "Instant", "Target creature loses flying until end of turn.")
SPIKE = card("Test Spike", "{3}", "Artifact — Equipment", "Equipped creature has deathtouch.\nWhenever equipped creature deals "
             "combat damage to a player, that player loses half their life, rounded up.\nEquip {3}")
FATED = card("Test Fated", "{R}", "Instant", "~ deals 2 damage to any target.\nIf it's your turn, scry 2.")
SANDSKIN = card("Test Sandskin", "{2}{W}", "Enchantment — Aura", "Enchant creature\nPrevent all combat damage that would be "
                "dealt to and dealt by enchanted creature.")
VETERAN = card("Test Veteran", "{2}{W}", "Creature — Human Soldier", "{T}: Target creature gets +2/+2 until end of turn. "
               "Activate only during your turn, before attackers are declared.", 2, 2)
FLIER = card("Test Bird", "{W}", "Creature — Bird", "Flying", 2, 2)
ALL = (TRAIL, COURSER, SCALES, DIMINISH, ABOUT, TURN, FROGIFY, RECLAIM, GUILDMAGE, SHARDS, VERTIGO, SPIKE, FATED, SANDSKIN,
       VETERAN)


class CoverageBatch10(unittest.TestCase):
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
        self.assertIn("'before attackers are declared' is played as sorcery timing", VETERAN.approximations)

    def test_arc_trail_distinct_targets(self):
        effs = TRAIL.spell_effects
        self.assertTrue(all(e.data.get("distinct") for e in effs))
        self.put(self.b, BEAR)
        targets = self.game.auto_targets(self.a, effs, None)
        self.assertEqual(len(targets), 2)
        self.assertIsNot(targets[0], targets[1])

    def test_another_target(self):
        courser, bear = self.put(self.a, COURSER), self.put(self.a, BEAR)
        self.game.attackers = [courser, bear]
        eff = COURSER.triggers[0].effects[0]
        with self.game.targeting(courser):
            self.assertEqual(self.game.legal_targets(self.a, eff), [bear])

    def test_hardened_scales(self):
        self.put(self.a, SCALES)
        bear = self.put(self.a, BEAR)
        bear.counters["+1/+1"] = bear.p1 + 1
        self.assertEqual(bear.p1, 2)
        theirs = self.put(self.b, BEAR)
        theirs.counters["+1/+1"] = 1
        self.assertEqual(theirs.p1, 1)

    def test_base_switch_and_frogs(self):
        from mtgsim import auras
        ogre = self.put(self.b, card("Test Ogre", "{2}{R}", "Creature — Ogre", "Trample", 4, 4))
        self.game.resolve(self.a, DIMINISH.spell_effects[0], ogre)
        self.assertEqual((ogre.power, ogre.toughness), (1, 1))
        wall = self.put(self.a, card("Test Wall", "{1}", "Creature — Wall", "Defender", 0, 5))
        self.game.resolve(self.a, ABOUT.spell_effects[0], wall)
        self.assertEqual((wall.power, wall.toughness), (5, 0))
        dragon = self.put(self.b, card("Test Dragon", "{4}{R}", "Creature — Dragon", "Flying", 5, 5))
        self.game.resolve(self.a, TURN.spell_effects[0], dragon)
        self.assertEqual((dragon.power, dragon.toughness), (1, 1))
        self.assertFalse(dragon.has("flying"))
        self.assertIn("Frog", dragon.card.subtypes)
        self.game.expire_continuous_effects()
        self.assertTrue(dragon.has("flying"))
        frogify = self.put(self.a, FROGIFY)
        auras.attach(self.game, frogify, dragon)
        self.assertEqual((dragon.power, dragon.toughness), (1, 1))
        self.game.leave_battlefield(frogify, "graveyard")
        self.assertEqual((dragon.power, dragon.toughness), (5, 5))

    def test_library_top(self):
        self.a.graveyard[:] = [BEAR, ISLAND]
        self.game.resolve(self.a, RECLAIM.spell_effects[0], None)
        self.assertEqual(self.a.library[-1].name, BEAR.name)
        bear = self.put(self.a, BEAR)
        self.game.resolve(self.a, GUILDMAGE.activated[0].effects[0], bear)
        self.assertNotIn(bear, self.a.battlefield)
        self.assertEqual(self.a.library[-1].name, BEAR.name)

    def test_attacking_damage_keyword_loss_half_life(self):
        attacker, other = self.put(self.b, card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)), self.put(self.b, BEAR)
        self.game.attackers = [attacker]
        self.game.resolve(self.a, SHARDS.spell_effects[0], None)
        self.game.settle()
        self.assertNotIn(attacker, self.b.battlefield)
        self.assertIn(other, self.b.battlefield)
        bird = self.put(self.b, FLIER)
        self.game.resolve(self.a, VERTIGO.spell_effects[0], bird)
        self.assertFalse(bird.has("flying"))
        self.b.life = 15
        eff = SPIKE.host_triggers[0].effects[-1]
        self.game.resolve(self.a, eff, self.b)
        self.assertEqual(self.b.life, 7)

    def test_fated_scry_and_sandskin(self):
        from mtgsim import auras
        self.assertEqual(FATED.spell_effects[-1].cond, "my_turn")
        self.assertTrue(self.game.check_cond(self.a, FATED.spell_effects[-1], StackItem(self.a, [], []), None))
        self.assertFalse(self.game.check_cond(self.b, FATED.spell_effects[-1], StackItem(self.b, [], []), None))
        bear, ogre = self.put(self.a, BEAR), self.put(self.b, card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3))
        auras.attach(self.game, self.put(self.a, SANDSKIN), bear)
        self.game.deal_damage(bear, 3, by=self.b, source=ogre, combat=True)
        self.game.deal_damage(ogre, 2, by=self.a, source=bear, combat=True)
        self.assertEqual((bear.damage, ogre.damage), (0, 0))


if __name__ == "__main__":
    unittest.main()
