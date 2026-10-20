"""Buyback, surge, prototype and suspend; Phyrexian mana in ability costs; "return target permanent"."""
import random
import unittest

from mtgsim import alt_casts
from mtgsim.cards.parse import _parse_ability
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, SWAMP, card

BURIAL = card("Test Burial", "{1}{B}", "Sorcery", "Buyback {3}\nYou gain 1 life.")
FREERUNNER = card("Test Freerunner", "{3}{R}", "Creature — Goblin Warrior", "Surge {1}{R}\nMenace", 3, 2)
SHOCK = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to any target.")
THOPTER = card("Test Thopter", "{8}", "Artifact Creature — Thopter", "Prototype {3}{U} — 2/3\nFlying", 6, 7)
RIFT = card("Test Rift Bolt", "{2}{R}", "Sorcery", "~ deals 3 damage to any target.\nSuspend 1—{R}")
VISION = card("Test Vision", "", "Sorcery", "Suspend 2—{U}\nDraw three cards.")
WAVE = card("Test Wave", "{2}{U}", "Instant", "Return target permanent to its owner's hand.")
JUMP = card("Test Jump", "{1}{R}", "Sorcery", "~ deals 2 damage to any target.\nJump-start")
CHIMERA = card("Test Chimera", "{2}{G}", "Creature — Chimera", "Escape—{4}{G}, Exile three other cards from your "
                                                               "graveyard.\n~ escapes with a +1/+1 counter on it.", 3, 3)
ATTENDANT = card("Test Attendant", "{3}{W}", "Creature — Bird Soldier", "Flying\nEmbalm {1}{W}", 3, 1)
WITNESS = card("Test Witness", "{2}{G}", "Creature — Human Shaman", "Eternalize {1}{G}", 2, 1)
SCORPION = card("Test Scorpion", "{2}{B}", "Creature — Scorpion", "Deathtouch\nScavenge {1}", 2, 2)


class AltCasts(unittest.TestCase):
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

    def option(self, p, kind):
        return next((o for o in self.game.spell_options(p) if self.game._origin(o)[1] == kind), None)

    def test_templates(self):
        for c in (BURIAL, FREERUNNER, THOPTER, RIFT, VISION, WAVE, JUMP, CHIMERA, ATTENDANT, WITNESS, SCORPION):
            self.assertEqual(c.unsupported, [], c.name)

    def test_buyback_returns_to_hand(self):
        self.put(self.a, MOUNTAIN, 4)
        self.put(self.a, SWAMP)
        self.a.hand.append(BURIAL)
        burial = self.option(self.a, "buyback")
        self.assertEqual(burial.mana_cost, {"generic": 4, "B": 1})
        self.assertTrue(self.game.cast(self.a, burial))
        self.game.settle()
        self.assertIn(BURIAL, self.a.hand)
        self.assertNotIn(BURIAL, self.a.graveyard)

    def test_surge_after_another_spell(self):
        self.put(self.a, MOUNTAIN, 3)
        self.a.hand += [FREERUNNER, SHOCK]
        self.assertIsNone(self.option(self.a, "surge"))
        self.assertTrue(self.game.cast(self.a, SHOCK, [self.b]))
        self.game.settle()
        surge = self.option(self.a, "surge")
        self.assertIsNotNone(surge)
        self.assertTrue(self.game.cast(self.a, surge))
        self.game.settle()
        self.assertTrue(any(x.card.name == FREERUNNER.name for x in self.a.battlefield))

    def test_prototype_is_smaller(self):
        self.put(self.a, ISLAND, 4)
        self.a.hand.append(THOPTER)
        self.assertTrue(self.game.cast(self.a, self.option(self.a, "prototype")))
        self.game.settle()
        perm = next(x for x in self.a.battlefield if x.card.name == THOPTER.name)
        self.assertEqual((perm.power, perm.toughness), (2, 3))
        self.assertTrue(perm.has("flying"))

    def test_suspend_casts_when_the_last_counter_goes(self):
        self.put(self.a, MOUNTAIN)
        self.a.hand.append(RIFT)
        self.assertTrue(alt_casts.suspend(self.game, self.a, RIFT))
        self.assertIn(RIFT, self.a.exile)
        self.game.begin_upkeep(self.a)
        self.game.settle()
        self.assertEqual(self.b.life, 17)
        self.assertIn(RIFT, self.a.graveyard)

    def test_cardless_cost_is_always_suspended(self):
        self.put(self.a, ISLAND)
        self.a.hand.append(VISION)
        self.assertTrue(alt_casts.worth_suspending(self.game, self.a, VISION))
        alt_casts.suspend(self.game, self.a, VISION)
        hand = len(self.a.hand)
        self.game.begin_upkeep(self.a)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand)
        self.game.begin_upkeep(self.a)
        self.game.settle()
        self.assertEqual(len(self.a.hand), hand + 3)

    def test_phyrexian_ability_cost(self):
        act = _parse_ability("{5}{B/P}: Transform ~. Activate only as a sorcery.", [])
        self.assertEqual(act.cost, {"generic": 5, "B": 1})

    def test_jump_start_discards_then_exiles(self):
        self.put(self.a, MOUNTAIN, 2)
        self.a.graveyard.append(JUMP)
        self.a.hand.append(ISLAND)
        option = self.option(self.a, "jump_start")
        self.assertTrue(self.game.cast(self.a, option, [self.b]))
        self.game.settle()
        self.assertEqual(self.b.life, 18)
        self.assertIn(JUMP, self.a.exile)
        self.assertEqual(self.a.hand, [])

    def test_escape_exiles_other_cards_and_adds_counters(self):
        from tests.test_templates import FOREST
        self.put(self.a, FOREST, 5)
        self.a.graveyard.extend([CHIMERA, ISLAND, ISLAND])
        self.assertIsNone(self.option(self.a, "escape"))
        self.a.graveyard.append(ISLAND)
        self.assertTrue(self.game.cast(self.a, self.option(self.a, "escape")))
        self.game.settle()
        perm = next(x for x in self.a.battlefield if x.card.name == CHIMERA.name)
        self.assertEqual(perm.p1, 1)
        self.assertEqual(len(self.a.graveyard), 0)

    def test_embalm_eternalize_scavenge(self):
        from tests.test_templates import FOREST, PLAINS
        self.put(self.a, PLAINS, 2)
        self.put(self.a, FOREST, 2)
        self.put(self.a, SWAMP, 1)
        self.a.graveyard.extend([ATTENDANT, WITNESS, SCORPION])
        alt_casts.graveyard_actions(self.game, self.a)
        tokens = {x.card.name: x for x in self.a.battlefield if x.card.is_token}
        bird, witness = tokens[ATTENDANT.name + " token"], tokens[WITNESS.name + " token"]
        self.assertEqual((bird.card.colors, bird.has("flying"), "Zombie" in bird.card.subtypes), ({"W"}, True, True))
        self.assertEqual((witness.card.power, witness.card.toughness, witness.card.colors), (4, 4, {"B"}))
        self.assertEqual(sum(x.p1 for x in self.a.creatures), 2)        # scavenged: the scorpion's power
        self.assertEqual(self.a.graveyard, [])

    def test_return_target_permanent(self):
        bear = self.put(self.b, BEAR)
        self.put(self.a, ISLAND, 3)
        self.a.hand.append(WAVE)
        self.assertTrue(self.game.cast(self.a, WAVE, [bear]))
        self.game.settle()
        self.assertIn(BEAR, self.b.hand)


if __name__ == "__main__":
    unittest.main()
