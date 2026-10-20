"""Extra turns, extra land drops, putting a land from hand, temporary control, P/T changes with mixed signs,
"can't be blocked except by two or more creatures", Raid and Delirium statics, and small riders."""
import random
import unittest

from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, FOREST, ISLAND, MOUNTAIN, card

WALK = card("Test Walk", "{1}{U}", "Sorcery", "Take an extra turn after this one.")
EXPLORE = card("Test Explore", "{1}{G}", "Sorcery", "You may play an additional land this turn.\nDraw a card.")
SPIRAL = card("Test Spiral", "{G}{U}", "Instant", "Draw a card. You may put a land card from your hand onto the "
                                                  "battlefield.")
PRANK = card("Test Threaten", "{2}{R}", "Sorcery", "Gain control of target creature until end of turn.")
CONTORT = card("Test Contortion", "{1}", "Instant", "Target creature gets +3/-3 until end of turn.")
STEAL = card("Test Steal", "{B}{G}", "Instant", "Target creature gets +1/+1 until end of turn. Another target "
                                                "creature gets -1/-1 until end of turn.")
BERSERKER = card("Test Berserker", "{3}{G}{G}", "Creature — Ape", "~ can't be blocked except by three or more "
                                                                  "creatures.", 5, 3)
FLAYER = card("Test Flayer", "{B}{G}", "Creature — Human Warrior", "Delirium — ~ gets +2/+2 as long as there are four "
                                                                   "or more card types among cards in your graveyard.",
              2, 2)
RAIDER = card("Test Raider", "{1}{W}", "Creature — Human Soldier",
              "Raid — ~ enters with a +1/+1 counter on it if you attacked this turn.", 2, 2)
ARTILLERY = card("Test Artillery", "{3}{R}", "Creature — Goblin Warrior",
                 "{T}: ~ deals 2 damage to any target and 3 damage to you.", 1, 3)
SLAG = card("Test Slagwurm", "{5}{G}", "Creature — Wurm", "Whenever ~ blocks or becomes blocked by a creature, destroy "
                                                           "that creature. You gain life equal to that creature's "
                                                           "toughness.", 7, 7)
DJINN = card("Test Djinn", "{2}{U}", "Creature — Djinn", "When you control no lands, sacrifice ~.", 5, 6)
WALL = card("Test Wall", "{2}", "Creature — Wall", "", 0, 4)


class OneLiners(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 30, Scripted())
        self.b = Player("b", [ISLAND] * 30, Scripted())
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
        for c in (WALK, EXPLORE, SPIRAL, PRANK, CONTORT, STEAL, BERSERKER, FLAYER, RAIDER, ARTILLERY, SLAG, DJINN):
            self.assertEqual(c.unsupported, [], c.name)

    def test_extra_turn(self):
        self.put(self.a, ISLAND, 2)
        self.a.hand.append(WALK)
        self.assertTrue(self.game.cast(self.a, WALK))
        self.game.settle()
        self.assertEqual(self.game.extra_turns, [self.a])
        self.game.max_turns = self.game.turn + 2
        self.game.play()
        self.assertTrue(any("T3 a:" in e for e in self.game.events))       # a takes the next turn too
        self.assertFalse(any(e.startswith("T3 b:") for e in self.game.events))

    def test_extra_land_and_land_from_hand(self):
        self.put(self.a, FOREST, 2)
        self.a.hand += [EXPLORE, FOREST, FOREST]
        self.assertTrue(self.game.cast(self.a, EXPLORE))
        self.game.settle()
        self.game.play_land(self.a, FOREST)
        self.assertFalse(self.a.land_played)
        self.game.play_land(self.a, FOREST)
        self.assertTrue(self.a.land_played)
        self.put(self.a, ISLAND, 1)
        self.a.hand += [SPIRAL, MOUNTAIN]
        lands = sum(x.card.is_land for x in self.a.battlefield)
        self.assertTrue(self.game.cast(self.a, SPIRAL))
        self.game.settle()
        self.assertEqual(sum(x.card.is_land for x in self.a.battlefield), lands + 1)

    def test_threaten_and_mixed_pt(self):
        bear = self.put(self.b, BEAR)
        self.put(self.a, MOUNTAIN, 3)
        self.a.hand.append(PRANK)
        self.assertTrue(self.game.cast(self.a, PRANK, [bear]))
        self.game.settle()
        self.assertIs(bear.controller, self.a)
        wall = self.put(self.b, WALL)
        self.game.resolve(self.a, CONTORT.spell_effects[0], wall)
        self.assertEqual((wall.power, wall.toughness), (3, 1))
        effects = STEAL.spell_effects
        self.assertEqual([e.kind for e in effects], ["pump", "debuff_one"])

    def test_min_blockers(self):
        berserker = self.put(self.a, BERSERKER)
        bears = [self.put(self.b, BEAR) for _ in range(2)]
        self.fight([berserker], {berserker: bears})
        self.assertNotIn(berserker, self.game.blocks)
        self.assertEqual(self.b.life, 15)

    def test_delirium_and_raid(self):
        flayer = self.put(self.a, FLAYER)
        self.assertEqual(flayer.power, 2)
        self.a.graveyard.extend([ISLAND, BEAR, WALK, card("Test Thing", "{1}", "Artifact", "")])
        self.assertEqual(flayer.power, 4)
        self.assertEqual(self.put(self.a, RAIDER).p1, 0)
        self.a.attacked_with = 1
        self.assertEqual(self.put(self.a, RAIDER).p1, 1)

    def test_damage_to_you_and_life_equal_to_toughness(self):
        artillery = self.put(self.a, ARTILLERY)
        self.assertTrue(self.game.activate_ability(self.a, artillery, 0))
        self.game.settle()
        self.assertEqual(self.a.life, 17)
        slag, wall = self.put(self.a, SLAG), self.put(self.b, WALL)
        life = self.a.life
        self.fight([slag], {slag: [wall]})
        self.assertNotIn(wall, self.b.battlefield)
        self.assertEqual(self.a.life, life + 4)

    def test_sacrificed_without_lands(self):
        island = self.put(self.a, ISLAND)
        djinn = self.put(self.a, DJINN)
        self.game.leave_battlefield(island, "hand")
        self.game.state_based_actions()
        self.assertNotIn(djinn, self.a.battlefield)


if __name__ == "__main__":
    unittest.main()
