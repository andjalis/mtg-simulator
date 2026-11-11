"""Attack and block restrictions with a condition (mtgsim/cx_static_combat.py)."""
import os
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player
from mtgsim.engine.state import can_block
from tests.test_templates import BEAR, card

VAMPIRE = card("Test Vampire", "{1}{B}", "Creature — Vampire", "", 2, 2)
BIRD = card("Test Bird", "{U}", "Creature — Bird", "Flying", 1, 1)
RELIC = card("Test Relic", "{2}", "Artifact", "")


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class CombatUnless(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        self.a = Player("a", [BEAR] * 20, HeuristicAI())
        self.b = Player("b", [BEAR] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=False)
        for p in (self.a, self.b):
            p.library = list(p.deck)
        self.game.turn, self.game.step, self.game.active_idx = 3, "main1", 0

    def put(self, c, who=None):
        if isinstance(c, str):
            c = self.db.get(c)
            self.assertEqual(c.unsupported, [], c.name)
        perm = self.game.enter_battlefield(who or self.a, c)
        perm.sick = False
        return perm

    def test_attack_needs_a_creature_spell_this_turn(self):
        cohort = self.put("Goblin Cohort")
        self.assertFalse(cohort.can_attack())
        self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 20)
        for _ in range(2):
            self.put(card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)"))
        raider = card("Test Raider", "{1}{R}", "Creature — Goblin", "", 2, 1)
        self.a.hand = [raider]
        self.assertTrue(self.game.cast(self.a, raider))
        self.assertTrue(cohort.can_attack())
        self.game.combat(self.a, self.b)
        self.assertEqual(self.b.life, 20 - cohort.power)

    def test_attack_needs_defending_players_permanent(self):
        dragon = self.put("Lurking Green Dragon")         # only if defending player controls a creature with flying
        self.assertFalse(dragon.can_attack())
        self.put(BIRD, self.b)
        self.assertTrue(dragon.can_attack())

    def test_another_permanent(self):
        mouser = self.put("Mouser Mark III")              # another artifact
        self.assertFalse(mouser.can_attack())
        self.put(RELIC)
        self.assertTrue(mouser.can_attack())

    def test_block_only(self):
        null = self.put("Mindless Null")                  # can't block unless you control a Vampire
        attacker = self.put(BEAR, self.b)
        self.assertTrue(null.can_attack())
        self.assertFalse(can_block(null, attacker))
        self.put(VAMPIRE)
        self.assertTrue(can_block(null, attacker))

    def test_block_in_combat(self):
        null = self.put("Mindless Null")
        self.put(BEAR, self.b)
        self.game.active_idx = 1
        self.game.combat(self.b, self.a)
        self.assertNotIn(null, [x for bl in self.game.blocks.values() for x in bl])

    def test_more_creatures_than_the_other_player(self):
        goon = self.put("Goblin Goon")                    # attack and block: more creatures than that player
        self.put(BEAR, self.b)
        self.assertFalse(goon.can_attack())               # one each
        self.put(BEAR)
        self.assertTrue(goon.can_attack())

    def test_or_carries_the_determiner(self):
        wolf = self.put("Howlpack Wolf")                  # can't block unless you control another Wolf or Werewolf
        attacker = self.put(BEAR, self.b)
        self.assertFalse(can_block(wolf, attacker))
        self.put(card("Test Werewolf", "{1}{G}", "Creature — Human Werewolf", "", 2, 2))
        self.assertTrue(can_block(wolf, attacker))

    def test_if_form_stops_while_condition_holds(self):
        orgg = self.put("Orgg")           # can't attack if defending player controls an untapped creature with power 3+
        self.assertTrue(orgg.can_attack())
        big = self.put(card("Test Ogre", "{3}", "Creature — Ogre", "", 3, 3), self.b)
        self.assertFalse(orgg.can_attack())
        big.tapped = True
        self.assertTrue(orgg.can_attack())

    def test_if_form_on_block_uses_own_lands(self):
        bl = self.put("Branded Brawlers")  # can't block if you control an untapped land
        attacker = self.put(BEAR, self.b)
        land = self.put(card("Mountain", types="Basic Land — Mountain", text="({T}: Add {R}.)"))
        self.assertFalse(can_block(bl, attacker))
        land.tapped = True
        self.assertTrue(can_block(bl, attacker))

    def test_defending_player_is_the_monarch(self):
        hireling = self.put("Crown-Hunter Hireling")
        self.assertFalse(hireling.can_attack())
        self.game.monarch = self.b
        self.assertTrue(hireling.can_attack())

    def test_cards_in_exile_total(self):
        ket = self.put(card("Test Ket", "{2}{B}", "Creature — Spirit",
                            "~ can't attack or block unless there are seven or more cards in exile.", 2, 2))
        self.assertFalse(ket.can_attack())
        self.a.exile += [BEAR] * 4
        self.b.exile += [BEAR] * 3
        self.assertTrue(ket.can_attack())

    def test_prices_stay_unparsed(self):
        self.assertTrue(self.db.get("Qal Sisma Behemoth").unsupported)


if __name__ == "__main__":
    unittest.main()
