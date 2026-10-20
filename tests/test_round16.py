"""Prepared rearming, explicit granted-flashback costs and Raid entry counters."""
import random
import unittest
from unittest.mock import patch

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player

from tests.test_prepared_convoke import two_faced
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, SHOCK, card


def preparer(trigger):
    return two_faced(
        {"name": "Test Scholar", "mana_cost": "{1}{R}", "cmc": 2,
         "type_line": "Creature — Wizard", "power": "2", "toughness": "2",
         "oracle_text": trigger + ", this creature becomes prepared."},
        {"name": "Test Lesson", "mana_cost": "{R}", "cmc": 1,
         "type_line": "Sorcery", "oracle_text": "Test Lesson deals 2 damage to any target."})


SCHOLAR = preparer("Whenever you cast a creature spell")
HISTORIAN = preparer("Whenever one or more cards leave your graveyard")
SHADE = preparer("At the beginning of your first main phase")
RAIDER = card("Test Raider", "{1}{R}", "Creature — Goblin",
              "Raid — This creature enters with a +1/+1 counter on it if you attacked this turn.", 2, 2)
GRANT = "Target instant or sorcery card in your graveyard gains flashback until end of turn. " \
        "The flashback cost is equal to its mana cost."
REPLAY = card("Test Replay", "{R}", "Sorcery", GRANT)
MAGE = card("Test Replay Mage", "{R}", "Creature — Wizard", "When this creature enters, " + GRANT, 1, 1)
SPARK = card("Test Spark", "{1}{R}", "Sorcery", "Test Spark deals 3 damage to any target.")


class Round16(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [ISLAND] * 20, HeuristicAI())
        self.b = Player("b", [ISLAND] * 20, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for pl in (self.a, self.b):
            pl.library = [ISLAND] * 20

    def land(self):
        perm = Permanent(MOUNTAIN, self.a)
        self.a.battlefield.append(perm)
        return perm

    def prepared_options(self):
        return [c for c in self.game.spell_options(self.a) if c.name.endswith("(prepared)")]

    def test_templates(self):
        for c in (SCHOLAR, HISTORIAN, SHADE, RAIDER, REPLAY, MAGE):
            self.assertEqual(c.unsupported, [], c.name)

    def test_cast_trigger_rearms_after_the_copy_is_spent(self):
        scholar = self.game.enter_battlefield(self.a, SCHOLAR)
        self.assertFalse(scholar.prepared)
        self.assertEqual(self.prepared_options(), [])
        self.land()
        self.a.hand = [SHOCK]
        self.assertTrue(self.game.cast(self.a, SHOCK, [self.b]))
        self.assertFalse(scholar.prepared)  # An instant is not a creature spell.
        for _ in range(5):
            self.land()
        creature = card("Test Pupil", "{R}", "Creature — Human", "", 1, 1)
        for _ in range(2):
            self.a.hand = [creature]
            self.assertTrue(self.game.cast(self.a, creature))
            self.game.settle()
            self.assertTrue(scholar.prepared)
            self.assertEqual(len(self.prepared_options()), 1)
            self.assertTrue(self.game.cast(self.a, self.prepared_options()[0], [self.b]))
            self.game.settle()
            self.assertFalse(scholar.prepared)
            self.assertEqual(self.prepared_options(), [])
        self.assertEqual(self.b.life, 14)
        self.assertFalse(any(c.name == "Test Lesson" for c in self.a.graveyard))

    def test_graveyard_departure_prepares_the_source(self):
        historian = self.game.enter_battlefield(self.a, HISTORIAN)
        self.a.graveyard.append(BEAR)
        self.a.graveyard.remove(BEAR)
        self.a.hand.append(BEAR)
        self.game.state_based_actions()
        self.game.settle()
        self.assertTrue(historian.prepared)
        self.assertEqual(len(self.prepared_options()), 1)

    def test_first_main_phase_prepares_but_second_does_not(self):
        shade = self.game.enter_battlefield(self.a, SHADE)
        self.game.fire(self.a, "main2_begin")
        self.game.settle()
        self.assertFalse(shade.prepared)
        self.game.fire(self.a, "main1_begin")
        self.game.settle()
        self.assertTrue(shade.prepared)

    def test_removed_source_cannot_prepare_a_reentered_object(self):
        old = self.game.enter_battlefield(self.a, SHADE)
        self.game.fire(self.a, "main1_begin")
        self.game.destroy(old)
        new = self.game.enter_battlefield(self.a, SHADE)
        self.game.settle()
        self.assertFalse(old.prepared)
        self.assertFalse(new.prepared)
        self.assertEqual(self.prepared_options(), [])

    def test_repeated_triggers_do_not_store_multiple_copies(self):
        shade = self.game.enter_battlefield(self.a, SHADE)
        for _ in range(2):
            self.game.fire(self.a, "main1_begin")
        self.game.settle()
        self.assertTrue(shade.prepared)
        self.assertEqual(len(self.prepared_options()), 1)
        self.land()
        self.assertTrue(self.game.cast(self.a, self.prepared_options()[0], [self.b]))
        self.assertEqual(self.prepared_options(), [])

    def test_granted_flashback_pays_the_original_cost_and_exiles(self):
        for grant in (REPLAY, MAGE):
            with self.subTest(grant=grant.name):
                self.setUp()
                self.a.graveyard.append(SPARK)
                self.a.hand = [grant]
                self.land()
                self.assertTrue(self.game.cast(self.a, grant))
                self.game.settle()
                option = next(c for c in self.game.spell_options(self.a) if c.name.startswith("Test Spark"))
                self.assertEqual(option.mana_cost, SPARK.mana_cost)
                self.land()
                self.assertFalse(self.game.cast(self.a, option, [self.b]))
                self.land()
                self.assertTrue(self.game.cast(self.a, option, [self.b]))
                self.game.settle()
                self.assertEqual(self.b.life, 17)
                self.assertNotIn(SPARK, self.a.graveyard)
                self.assertIn(SPARK, self.a.exile)

    def test_flashback_grant_expires_at_cleanup(self):
        self.a.graveyard.append(SPARK)
        self.land()
        self.a.hand = [REPLAY]
        self.assertTrue(self.game.cast(self.a, REPLAY))
        self.assertTrue(any(target.card is SPARK for target in self.a.granted_fb))
        with patch.object(self.a.ai, "main_phase"), patch.object(self.b.ai, "main_phase"):
            self.game.take_turn(self.b)
        self.assertEqual(self.a.granted_fb, [])
        self.assertFalse(any(c.name.startswith("Test Spark") for c in self.game.spell_options(self.a)))

    def test_unrelated_or_different_flashback_cost_stays_unsupported(self):
        for text in ("The flashback cost is equal to its mana cost.",
                     GRANT.replace("its mana cost", "{R}")):
            c = card("Test Other Grant", "{R}", "Sorcery", text)
            self.assertTrue(c.unsupported)

    def test_raid_checks_this_players_attack_history_on_entry(self):
        self.b.attacked_with = 1
        before = self.game.enter_battlefield(self.a, RAIDER)
        self.a.attacked_with = 1
        after = self.game.enter_battlefield(self.a, RAIDER)
        self.assertEqual((before.p1, before.power), (0, 2))
        self.assertEqual((after.p1, after.power), (1, 3))
        self.a.attacked_with = 0
        later = self.game.enter_battlefield(self.a, RAIDER)
        self.assertEqual(later.p1, 0)
        self.assertEqual(after.p1, 1)  # The existing counter does not expire.


if __name__ == "__main__":
    unittest.main()
