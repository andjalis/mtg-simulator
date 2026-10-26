"""Coverage batch: enchanted-creature damage triggers, Basilisks, devotion and greatest-power cost reductions,
targeting taxes, permanent keyword grants, plural creature-type statics, player shroud and smaller templates."""
import random
import unittest

from mtgsim.engine import Game, Player
from mtgsim.engine.state import StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, card

LINK = card("Test Link", "{W}", "Enchantment — Aura", "Enchant creature\nWhenever enchanted creature deals damage, you gain that "
            "much life.")
CURIOSITY = card("Test Curiosity", "{U}", "Enchantment — Aura", "Enchant creature\nWhenever enchanted creature deals damage to "
                 "an opponent, you may draw a card.")
BASILISK = card("Test Basilisk", "{3}{G}{G}", "Creature — Basilisk", "Whenever ~ blocks or becomes blocked by a non-Wall "
                "creature, destroy that creature at end of combat.", 2, 4)
TITAN = card("Test Titan", "{6}{B}", "Creature — Giant", "~ costs {X} less to cast, where X is your devotion to black.", 6, 5)
GHALTA = card("Test Ghalta", "{10}{G}{G}", "Legendary Creature — Elder Dinosaur", "Trample\n~ costs {X} less to cast, where X is "
              "the greatest power among creatures you control.", 12, 12)
BOREAL = card("Test Boreal", "{4}{U}", "Creature — Elemental", "Flying\nSpells your opponents cast that target ~ cost {2} more "
              "to cast.", 3, 4)
AVACYN = card("Test Avacyn", "{5}{W}{W}{W}", "Legendary Creature — Angel", "Flying, vigilance, indestructible\nOther permanents "
              "you control have indestructible.", 8, 8)
WARG = card("Test Warg", "{2}{B}", "Creature — Orc Warrior", "Other Orcs and Goblins you control have menace.", 3, 2)
MASK = card("Test Mask", "{2}{W}{W}", "Enchantment", "You have shroud.")
FAITH = card("Test Faithmender", "{3}{W}", "Creature — Rhino Monk", "Lifelink\nIf you would gain life, you gain twice that "
             "much life instead.", 1, 5)
WRAPPINGS = card("Test Wrappings", "{1}{U}", "Enchantment — Aura", "Enchant creature\nEnchanted creature has base power and "
                 "toughness 0/2.")
LASHES = card("Test Lashes", "{2}{B}{B}", "Enchantment — Aura", "Enchant creature\nEnchanted creature can't attack or block.\n"
              "At the beginning of the upkeep of enchanted creature's controller, that player loses 1 life.")
MOGG = card("Test Mogg", "{1}{R}", "Creature — Goblin", "Haste\nWhen ~ enters, tap all other creatures.", 1, 1)
OFFERING = card("Test Offering", "{1}{W}", "Instant", "Destroy target artifact. You gain life equal to its mana value.")
WHACK = card("Test Whack", "{3}{B}", "Instant", "~ costs {3} less to cast if it targets a white creature.\nTarget creature gets "
             "-4/-4 until end of turn.")
OX = card("Test Ox", "{3}{R}", "Creature — Ox", "When ~ enters, if you have one or fewer cards in hand, discard your hand, then "
          "draw three cards.", 4, 2)
ALL = (LINK, CURIOSITY, BASILISK, TITAN, GHALTA, BOREAL, AVACYN, WARG, MASK, FAITH, WRAPPINGS, LASHES, MOGG, OFFERING, WHACK)


class CoverageBatch11(unittest.TestCase):
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

    def test_enchanted_damage_triggers(self):
        from mtgsim import auras
        bear = self.put(self.a, BEAR)
        auras.attach(self.game, self.put(self.a, LINK), bear)
        auras.attach(self.game, self.put(self.a, CURIOSITY), bear)
        self.game.deal_damage(self.b, 2, by=self.a, source=bear, combat=True)
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life, len(self.a.hand)), (22, 18, 1))

    def test_basilisk(self):
        basilisk, bear = self.put(self.a, BASILISK), self.put(self.b, BEAR)
        wall = self.put(self.b, card("Test Wall", "{1}", "Creature — Wall", "Defender", 0, 4))
        self.game.fire(self.a, "blocked_by", basilisk, context=bear)
        self.game.fire(self.a, "blocked_by", basilisk, context=wall)
        self.game.settle()
        self.assertEqual(len(self.game.end_combat_effects), 1)
        p, effects, source, subject = self.game.end_combat_effects[0]
        self.assertIs(subject, bear)

    def test_cost_reductions_and_target_tax(self):
        self.put(self.a, card("Test Black", "{B}{B}", "Creature — Zombie", "", 2, 2))
        self.assertEqual(self.game.cost_of(self.a, TITAN)["generic"], 4)
        self.put(self.a, card("Test Big", "{5}", "Creature — Beast", "", 5, 5))
        self.assertEqual(self.game.cost_of(self.a, GHALTA)["generic"], 5)
        boreal = self.put(self.b, BOREAL)
        bolt = card("Test Bolt", "{R}", "Instant", "~ deals 3 damage to any target.")
        self.put(self.a, card("Mountain", "", "Basic Land — Mountain", "({T}: Add {R}.)"), 2)
        self.a.hand[:] = [bolt]
        self.assertFalse(self.game.cast(self.a, bolt, [boreal]))      # {R} plus {2}: not enough mana
        self.assertTrue(self.game.cast(self.a, bolt, [self.b]))

    def test_grants_and_shroud(self):
        self.put(self.a, AVACYN)
        land = self.put(self.a, ISLAND)
        self.assertTrue(land.has("indestructible"))
        self.put(self.a, WARG)
        goblin = self.put(self.a, card("Test Goblin", "{R}", "Creature — Goblin", "", 1, 1))
        self.assertTrue(goblin.has("menace"))
        self.put(self.a, MASK)
        self.assertFalse(self.game.targetable(self.a, self.a))
        self.assertFalse(self.game.targetable(self.a, self.b))

    def test_life_doubling_base_aura_and_lashes(self):
        from mtgsim import auras
        self.put(self.a, FAITH)
        self.game.change_life(self.a, 3, "test")
        self.assertEqual(self.a.life, 26)
        ogre = self.put(self.b, card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 4, 4))
        self.assertTrue(WRAPPINGS.aura_hostile)
        auras.attach(self.game, self.put(self.a, WRAPPINGS), ogre)
        self.assertEqual((ogre.power, ogre.toughness), (0, 2))
        trig = LASHES.triggers[0]
        self.assertEqual(trig.event, "opp_upkeep")
        self.game.resolve(self.a, trig.effects[0], None, item=StackItem(self.a, [], [], context=self.b))
        self.assertEqual(self.b.life, 19)

    def test_small_templates(self):
        mogg_target = self.put(self.b, BEAR)
        mine = self.put(self.a, BEAR)
        mogg = self.put(self.a, MOGG)
        self.assertTrue(mogg_target.tapped and mine.tapped)
        self.assertFalse(mogg.tapped)
        relic = self.put(self.b, card("Test Relic", "{4}", "Artifact", ""))
        prev = None
        for e in OFFERING.spell_effects:
            self.game.resolve(self.a, e, relic, prev=prev)
            prev = relic
        self.assertEqual(self.a.life, 24)
        knight = card("Test White Knight", "{1}{W}", "Creature — Knight", "", 2, 2)
        self.put(self.b, knight)
        self.assertEqual(self.game.cost_of(self.a, WHACK)["generic"], 0)


if __name__ == "__main__":
    unittest.main()
