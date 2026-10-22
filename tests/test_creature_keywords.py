"""Echo, unleash, evolve, renown, mentor, battle cry, riot, bloodthirst, fabricate, living weapon, heroic,
"as long as it's attacking", and the tuck / sacrifice / tutor one-liners."""
import random
import unittest

from mtgsim.engine import Game, Player, can_block
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, MOUNTAIN, PLAINS, SWAMP, card

GRUNTS = card("Test Grunts", "{2}{G}", "Creature — Ape", "Flash\nEcho {2}{G}", 3, 4)
THUG = card("Test Thug", "{1}{R}", "Creature — Human Warrior", "First strike\nUnleash", 2, 2)
RAPTOR = card("Test Cloudfin", "{U}", "Creature — Bird Mutant", "Flying\nEvolve", 0, 1)
ORACLE = card("Test Oracle", "{2}{W}", "Creature — Human Cleric", "Lifelink\nRenown 1", 2, 2)
HERO = card("Test Hero", "{2}{R}", "Creature — Human Knight", "Haste\nBattle cry", 3, 2)
MENTOR = card("Test Mentor", "{1}{W}", "Creature — Human Soldier", "Mentor", 3, 3)
RIOTER = card("Test Rioter", "{1}{R}", "Creature — Goblin", "Riot", 2, 2)
LANCER = card("Test Bloodthirsty", "{1}{R}", "Creature — Human Knight", "Bloodthirst 2", 1, 1)
STEED = card("Test Steed", "{4}", "Artifact Creature — Construct", "Haste\nFabricate 1", 2, 2)
GERM_SWORD = card("Test Strandwalker", "{5}", "Artifact — Equipment",
                  "Living weapon\nEquipped creature gets +2/+4 and has reach.\nEquip {4}")
BRIGONE = card("Test Heroic", "{W}", "Creature — Human Soldier",
               "Heroic — Whenever you cast a spell that targets ~, put a +1/+1 counter on ~.", 1, 1)
CELEBRANT = card("Test Celebrant", "{1}{B}", "Creature — Vampire", "~ has first strike as long as it's attacking.", 2, 1)
GIFT = card("Test Gift", "{W}", "Instant", "Target creature gets +1/+1 until end of turn.")
RETREAT = card("Test Retreat", "{2}{U}", "Sorcery", "Put target creature on top of its owner's library.")
PETITION = card("Test Petition", "{3}{B}{B}", "Sorcery", "Search your library for a card, put that card into your hand, "
                                                          "then shuffle.")
ABOMINATION = card("Test Abomination", "{2}{B}", "Creature — Eldrazi",
                   "At the beginning of your upkeep, sacrifice a creature.", 4, 3)


class CreatureKeywords(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, who, c, sick=False):
        perm = self.game.enter_battlefield(who, c)
        perm.sick = sick
        self.game.settle()
        return perm

    def fight(self, attackers, blocks=None):
        self.a.ai.attack = attackers
        self.b.ai.block = blocks or {}
        self.game.combat(self.a, self.b)
        self.game.settle()

    def test_templates(self):
        for c in (GRUNTS, THUG, RAPTOR, ORACLE, HERO, MENTOR, RIOTER, LANCER, STEED, GERM_SWORD, BRIGONE, CELEBRANT,
                  RETREAT, PETITION, ABOMINATION):
            self.assertEqual(c.unsupported, [], c.name)

    def test_echo_paid_or_sacrificed(self):
        grunts = self.put(self.a, GRUNTS)
        self.game.begin_upkeep(self.a)
        self.game.settle()
        self.assertNotIn(grunts, self.a.battlefield)        # no mana: sacrificed
        for _ in range(3):
            self.put(self.a, FOREST)
        grunts = self.put(self.a, GRUNTS)
        self.game.begin_upkeep(self.a)
        self.game.settle()
        self.assertIn(grunts, self.a.battlefield)
        self.game.begin_upkeep(self.a)                      # only once
        self.game.settle()
        self.assertIn(grunts, self.a.battlefield)

    def test_unleash_counter_stops_blocking(self):
        thug = self.put(self.a, THUG)
        self.assertEqual(thug.power, 3)
        self.assertFalse(can_block(thug, self.put(self.b, BEAR)))

    def test_evolve(self):
        raptor = self.put(self.a, RAPTOR)
        self.put(self.a, BEAR)
        self.assertEqual(raptor.p1, 1)
        self.put(self.a, BEAR)                              # 2/2 against a 1/2: greater power
        self.assertEqual(raptor.p1, 2)
        self.put(self.a, BEAR)                              # 2/2 vs 2/3: neither greater
        self.assertEqual(raptor.p1, 2)
        self.put(self.b, BEAR)                              # an opponent's creature
        self.assertEqual(raptor.p1, 2)

    def test_renown_once(self):
        oracle = self.put(self.a, ORACLE)
        self.fight([oracle])
        self.assertEqual(oracle.p1, 1)
        oracle.tapped = False
        self.fight([oracle])
        self.assertEqual(oracle.p1, 1)
        self.assertEqual(self.b.life, 20 - 2 - 3)

    def test_battle_cry_and_mentor(self):
        hero, mentor, bear = self.put(self.a, HERO), self.put(self.a, MENTOR), self.put(self.a, BEAR)
        self.fight([hero, mentor, bear])
        self.assertEqual(bear.p1, 1)                         # mentor: lesser power
        self.assertEqual(self.b.life, 20 - 3 - (3 + 1) - (2 + 1 + 1))

    def test_riot_haste_on_your_main_phase(self):
        self.game.active_idx = 0
        rioter = self.put(self.a, RIOTER, sick=True)
        self.assertTrue(rioter.has("haste"))
        self.assertEqual(rioter.p1, 0)
        self.game.step = "end_step"
        rioter = self.put(self.a, RIOTER, sick=True)
        self.assertEqual(rioter.p1, 1)

    def test_bloodthirst(self):
        self.assertEqual(self.put(self.a, LANCER).p1, 0)
        self.game.change_life(self.b, -1, "test")
        self.b.lost_life_turn = True
        self.assertEqual(self.put(self.a, LANCER).p1, 2)

    def test_fabricate(self):
        steed = self.put(self.a, STEED)                      # not evasive: a 1/1 Servo
        self.assertEqual(steed.p1, 0)
        self.assertTrue(any(x.card.is_token and "Servo" in x.card.subtypes for x in self.a.battlefield))
        flier = self.put(self.a, card("Test Flying Fabricator", "{3}", "Artifact Creature — Thopter",
                                      "Flying\nFabricate 2", 1, 1))
        self.assertEqual(flier.p1, 2)

    def test_living_weapon(self):
        sword = self.put(self.a, GERM_SWORD)
        germ = sword.attached_to
        self.assertIsNotNone(germ)
        self.assertIn(germ, self.a.battlefield)
        self.assertEqual((germ.power, germ.toughness), (2, 4))
        self.assertTrue(germ.has("reach"))

    def test_heroic(self):
        brigone = self.put(self.a, BRIGONE)
        self.put(self.a, PLAINS)
        self.a.hand.append(GIFT)
        self.assertTrue(self.game.cast(self.a, GIFT, [brigone]))
        self.game.settle()
        self.assertEqual(brigone.p1, 1)

    def test_first_strike_while_attacking(self):
        celebrant = self.put(self.a, CELEBRANT)
        self.assertFalse(celebrant.has("first strike"))
        self.game.attackers = [celebrant]
        self.assertTrue(celebrant.has("first strike"))

    def test_tuck_tutor_sacrifice(self):
        bear = self.put(self.b, BEAR)
        for _ in range(3):
            self.put(self.a, ISLAND)
        self.a.hand.append(RETREAT)
        self.assertTrue(self.game.cast(self.a, RETREAT, [bear]))
        self.game.settle()
        self.assertEqual(self.b.library[-1], BEAR)
        self.a.library.append(MOUNTAIN)
        for _ in range(5):
            self.put(self.a, SWAMP)
        self.a.hand.append(PETITION)
        self.assertTrue(self.game.cast(self.a, PETITION))
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)
        abomination = self.put(self.a, ABOMINATION)
        small = self.put(self.a, BEAR)
        self.game.begin_upkeep(self.a)
        self.game.settle()
        self.assertIn(abomination, self.a.battlefield)
        self.assertNotIn(small, self.a.battlefield)


if __name__ == "__main__":
    unittest.main()
