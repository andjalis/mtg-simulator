"""HeuristicAI follow-ups: graveyard returns valued over every legal graveyard, the least X that
does the job, and a precombat kill planner that counts copies and pays the cheaper cost."""
import random
import unittest

from mtgsim.ai import BaselineAI, HeuristicAI
from mtgsim import engine
from mtgsim.engine import Game, GraveyardTarget, Permanent, Player
from tests.test_templates import ISLAND, MOUNTAIN, card

THIEF = card("Test Grave Thief", "{R}", "Sorcery", "Return target creature card from an opponent's graveyard to "
             "the battlefield under your control.")
ANY_GY = card("Test Any Grave", "{R}", "Sorcery",
              "Return target creature card from a graveyard to the battlefield under your control.")
RECALL = card("Test Recall", "{R}", "Sorcery",
              "Return up to two target creature cards from your graveyard to your hand.")
THIEF_MODES = card("Test Grave Command", "{R}", "Sorcery", "Choose one —\n• Return target creature card from an "
                   "opponent's graveyard to the battlefield under your control.\n• You gain 1 life.")
DIGGER = card("Test Gravedigger", "{R}", "Creature — Zombie",
              "When this creature enters, return target creature card from a graveyard to your hand.", 1, 1)
HULK = card("Test Hulk", "{1}{G}", "Creature — Beast", "", 5, 5)       # mana value 2, card value 7
CLERK = card("Test Clerk", "{2}{W}", "Creature — Human", "", 1, 1)     # mana value 3, card value 4
ELF = card("Test Elf", "{G}", "Creature — Elf", "", 1, 1)

BLAST = card("Test Blast", "{X}{R}", "Sorcery", "Test Blast deals X damage to any target.")
OGRE = card("Test Ogre", "{2}{R}", "Creature — Ogre", "", 3, 3)
GOLEM = card("Test Golem", "{3}", "Artifact Creature — Golem", "", 3, 3)
BEAR = card("Test Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
STONE = card("Test Stone Bear", "{1}{G}", "Creature — Bear", "Indestructible", 2, 2)
WITHER = card("Test Wither", "{X}{B}", "Sorcery", "Target creature gets -X/-X until end of turn.")
BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")
SPARK = card("Test Spark", "{R}", "Instant", "Test Spark deals 2 damage to any target.")
BIG_SHOT = card("Test Big Shot", "{1}{R}", "Instant", "Test Big Shot deals 3 damage to any target.")
ECHO_BOLT = card("Test Echo Bolt", "{3}{R}", "Instant", "Test Echo Bolt deals 3 damage to any target.\n"
                 "Flashback {R}")
ATTACKER = card("Test Attacker", "{1}{R}", "Creature", "", 2, 2)


class Base(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], BaselineAI())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 1, "main1"
        self.a.library = [ISLAND] * 20
        self.b.library = [ISLAND] * 20
        self.b.ai.respond = lambda game, me: None

    def lands(self, n):
        self.a.battlefield += [Permanent(MOUNTAIN, self.a) for _ in range(n)]

    def creature(self, c, who):
        perm = Permanent(c, who)
        perm.sick = False
        who.battlefield.append(perm)
        return perm

    def untapped_lands(self):
        return sum(1 for x in self.a.battlefield if x.card is MOUNTAIN and not x.tapped)


class GraveyardTargetValue(Base):
    def test_opponent_graveyard_return_is_valued_by_its_best_entry(self):
        self.b.graveyard.extend([ELF, HULK])
        self.lands(1)
        value, targets = self.a.ai.plan_spell(self.game, self.a, THIEF)
        self.assertIsInstance(targets[0], GraveyardTarget)
        self.assertIs(targets[0].controller, self.b)
        self.assertIs(targets[0].card, HULK)
        self.assertAlmostEqual(value, 7 + 0.5 * 2)      # Hulk's value plus the mana it saves
        self.a.hand = [THIEF]
        self.assertTrue(self.game.cast(self.a, THIEF, targets))
        self.assertEqual([x.card for x in self.a.creatures], [HULK])
        self.assertEqual(list(self.b.graveyard), [ELF])

    def test_nothing_legal_in_the_opponents_graveyard_holds_the_spell(self):
        self.a.graveyard.append(HULK)          # ours, but the spell only reaches theirs
        self.lands(1)
        self.assertIsNone(self.a.ai.plan_spell(self.game, self.a, THIEF))

    def test_any_graveyard_picks_the_most_valuable_entry_not_the_highest_mana_value(self):
        self.a.graveyard.append(CLERK)
        self.b.graveyard.append(HULK)
        self.lands(1)
        _, targets = self.a.ai.plan_spell(self.game, self.a, ANY_GY)
        self.assertIs(targets[0].card, HULK)
        self.assertIs(targets[0].controller, self.b)
        # The default policy (highest mana value) would take Clerk; triggers use the AI's choice too.
        self.assertIs(engine.default_choose_target(self.game, self.a, ANY_GY.spell_effects[0]).card, CLERK)
        eff = DIGGER.triggers[0].effects[0]
        self.assertIs(self.a.ai.choose_target(self.game, self.a, eff).card, HULK)

    def test_up_to_two_returns_take_the_two_best_entries(self):
        self.a.graveyard.extend([ELF, CLERK, HULK])
        self.lands(1)
        value, targets = self.a.ai.plan_spell(self.game, self.a, RECALL)
        self.assertEqual({t.card.name for t in targets[0]}, {HULK.name, CLERK.name})
        self.assertAlmostEqual(value, 7 + 4)

    def test_modal_return_values_the_opponents_graveyard(self):
        self.b.graveyard.append(HULK)
        modes = THIEF_MODES.modes
        self.assertGreater(engine._mode_value(self.game, self.a, modes[0]), 1)
        self.assertEqual(engine.default_choose_modes(self.game, self.a, modes, 1, False), [0])


class SmallestX(Base):
    def test_kill_spends_only_the_creatures_toughness(self):
        bear = self.creature(BEAR, self.b)
        self.lands(6)
        self.a.hand = [BLAST]
        self.b.life = 20
        self.assertEqual(self.a.ai.choose_x(self.game, self.a, BLAST, [bear], 5), 2)
        self.assertTrue(self.game.cast(self.a, BLAST, [bear]))
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(self.untapped_lands(), 3)

    def test_damaged_creature_and_planeswalker_need_less(self):
        ogre = self.creature(OGRE, self.b)
        ogre.damage = 2
        self.assertEqual(self.a.ai.choose_x(self.game, self.a, BLAST, [ogre], 5), 1)

    def test_face_takes_exact_lethal_otherwise_everything(self):
        self.b.life = 3
        self.assertEqual(self.a.ai.choose_x(self.game, self.a, BLAST, [self.b], 5), 3)
        self.b.life = 9
        self.assertEqual(self.a.ai.choose_x(self.game, self.a, BLAST, [self.b], 5), 5)

    def test_unkillable_or_out_of_reach_targets_get_the_largest_x(self):
        stone = self.creature(STONE, self.b)
        self.assertEqual(self.a.ai.choose_x(self.game, self.a, BLAST, [stone], 5), 5)
        self.assertEqual(self.a.ai.choose_x(self.game, self.a, WITHER, [stone], 5), 2)   # -X/-X ignores it
        ogre = self.creature(OGRE, self.b)
        self.assertEqual(self.a.ai.choose_x(self.game, self.a, BLAST, [ogre], 2), 2)
        self.assertEqual(self.a.ai.choose_x(self.game, self.a, BLAST, [None], 4), 4)

    def test_main_phase_kills_and_casts_a_second_spell_with_the_mana_kept(self):
        self.creature(BEAR, self.b)
        self.lands(6)
        self.a.hand = [BLAST, GOLEM]     # no coloured pips: Blast is cast first
        self.game.step = "main2"
        self.a.ai.main_phase(self.game, self.a)
        self.assertEqual(self.b.creatures, [])
        self.assertEqual([x.card for x in self.a.creatures], [GOLEM])
        self.assertEqual(self.a.hand, [])

    def test_baseline_ai_still_pays_the_largest_x(self):
        self.a.ai = BaselineAI()
        bear = self.creature(BEAR, self.b)
        self.lands(6)
        self.a.hand = [BLAST]
        self.assertTrue(self.game.cast(self.a, BLAST, [bear]))
        self.assertEqual(self.untapped_lands(), 0)


class CostAwareSetup(Base):
    def attacker(self):
        return self.creature(ATTACKER, self.a)

    def test_two_copies_of_one_burn_spell_make_a_kill(self):
        self.attacker()
        self.lands(2)
        self.a.hand = [BOLT, BOLT]
        self.b.life = 8                  # 3 + 3 burn, 2 combat damage
        self.assertTrue(self.a.ai.lethal_setup(self.game, self.a))
        self.assertEqual(self.b.life, 2)
        self.assertEqual(self.a.hand, [])

    def test_copies_aim_independently(self):
        self.creature(HULK, self.a)
        blocker = self.creature(BEAR, self.b)
        self.lands(2)
        self.a.hand = [SPARK, SPARK]
        self.b.life = 6                  # one Spark clears the 2/2 blocker, the other goes face
        self.assertTrue(self.a.ai.lethal_setup(self.game, self.a))
        self.assertNotIn(blocker, self.b.battlefield)
        self.assertEqual(self.b.life, 4)

    def test_cheapest_working_plan_by_mana_paid_not_printed_mana_value(self):
        self.attacker()
        self.lands(3)
        self.a.hand = [BIG_SHOT]
        self.a.graveyard.append(ECHO_BOLT)   # printed mana value 4, flashback {R}
        self.b.life = 5
        self.assertTrue(self.a.ai.lethal_setup(self.game, self.a))
        self.assertEqual(self.a.hand, [BIG_SHOT])
        self.assertEqual(list(self.a.exile), [ECHO_BOLT])
        self.assertEqual(self.untapped_lands(), 2)

    def test_hand_copy_and_flashback_copy_of_one_card_combine(self):
        self.attacker()
        self.lands(2)
        self.a.hand = [ECHO_BOLT]            # too expensive from hand
        self.a.graveyard.append(ECHO_BOLT)
        self.b.life = 5
        self.assertTrue(self.a.ai.lethal_setup(self.game, self.a))
        self.assertEqual(self.a.hand, [ECHO_BOLT])
        self.assertEqual(self.b.life, 2)

    def test_no_kill_keeps_the_spells(self):
        self.attacker()
        self.lands(2)
        self.a.hand = [BOLT, BOLT]
        self.b.life = 9
        self.assertFalse(self.a.ai.lethal_setup(self.game, self.a))
        self.assertEqual(self.a.hand, [BOLT, BOLT])


if __name__ == "__main__":
    unittest.main()
