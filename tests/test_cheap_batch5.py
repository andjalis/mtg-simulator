"""Recruit, Increment, discard costs, tapped-target discounts and other cheap lines."""
import unittest

from mtgsim.cards import make_token

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, PLAINS, card
from tests.test_empower_discover import Base

GARRISON = card("Test Garrison", "{2}{W}", "Creature — Human Soldier",
                "When this creature enters, recruit. (Draw a card, then discard a card.)", 2, 2)
COLONY = card("Test Colony", "{3}{U}", "Creature — Crab",
              "Flying\nIncrement", 2, 2)
LAUGH = card("Test Laughing", "{2}{R}", "Instant", "As an additional cost to cast this spell, discard a card.\nDraw two cards.")
RESPONSE = card("Test Response", "{4}{W}", "Instant",
                "This spell costs {3} less to cast if it targets a tapped creature.\nDestroy target creature.")
PUP = card("Test Pup", "{1}{U}", "Creature — Frog",
           "When Test Pup enters, return up to one other target permanent you control to its owner's hand.", 2, 2)
WINGS = card("Test Wings", "{1}{G}", "Instant", "Destroy target artifact, enchantment, or creature with flying.")
FIGHT_ON = card("Test Fight On", "{2}{B}", "Sorcery",
                "Return up to two target creature cards from your graveyard to your hand.")
HAVEN = card("Test Haven", "", "Land", "This land enters tapped. As it enters, choose a color.\n"
                                       "{T}: Add one mana of the chosen color.")
STORM = card("Test Dragonstorm", "{3}{R}", "Enchantment",
             "When a Dragon you control enters, return this enchantment to its owner's hand.")
TALE = card("Test Tale", "{3}{W}", "Enchantment", "Enchanted creatures you control get +2/+2.")
SKIN = card("Test Skin", "{3}", "Artifact", "Untap this artifact during each other player's untap step.\n"
                                           "{T}: Add one mana of any color.")


class CheapBatch(Base):
    def test_templates(self):
        for c in (GARRISON, COLONY, LAUGH, RESPONSE, PUP, WINGS, FIGHT_ON, HAVEN, STORM, TALE, SKIN):
            self.assertEqual(c.unsupported, [], c.name)

    def test_recruit_loots_and_makes_a_soldier_for_a_nonland_discard(self):
        self.a.library = [ISLAND, ISLAND]
        self.a.hand = [BEAR]
        self.game.enter_battlefield(self.a, GARRISON)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual(len(self.a.graveyard), 1)
        soldiers = sum(x.card.name == "Human Soldier token" for x in self.a.battlefield)
        self.assertEqual(soldiers, 0 if self.a.graveyard[0].is_land else 1)

    def test_increment_counter_when_mana_spent_exceeds_both_stats(self):
        col = self.perm(COLONY)
        for _ in range(3):
            self.perm(MOUNTAIN)
        spell = card("Three Drop", "{2}{R}", "Sorcery", "Draw a card.")
        self.a.hand.append(spell)
        self.game.cast(self.a, spell, [])
        self.game.settle()
        self.assertEqual(col.power, 3)
        cheap = card("Two Drop", "{R}", "Sorcery", "Draw a card.")
        self.perm(MOUNTAIN)
        self.a.hand.append(cheap)
        self.game.cast(self.a, cheap, [])
        self.game.settle()
        self.assertEqual(col.power, 3)

    def test_discard_cost_needs_another_card(self):
        for _ in range(3):
            self.perm(MOUNTAIN)
        self.a.hand = [LAUGH]
        self.assertFalse(self.game.can_cast_now(self.a, LAUGH))
        self.a.hand = [LAUGH, BEAR]
        self.assertTrue(self.game.can_cast_now(self.a, LAUGH))
        self.assertTrue(self.game.cast(self.a, LAUGH, []))
        self.game.settle()
        self.assertEqual(self.a.graveyard.count(BEAR), 1)
        self.assertEqual(len(self.a.hand), 2)

    def test_tapped_target_discount(self):
        for _ in range(2):
            self.perm(PLAINS)
        bear = self.perm(BEAR, self.b)
        self.a.hand = [RESPONSE]
        self.assertFalse(self.game.can_cast_now(self.a, RESPONSE))
        bear.tapped = True
        self.assertTrue(self.game.can_cast_now(self.a, RESPONSE))
        self.assertTrue(self.game.cast(self.a, RESPONSE, [bear]))
        self.game.settle()
        self.assertNotIn(bear, self.b.battlefield)

    def test_destroy_flying_creature_or_artifact_not_ground_creature(self):
        flyer = self.perm(card("Bird", "{1}", "Creature — Bird", "Flying", 1, 1), self.b)
        ground = self.perm(BEAR, self.b)
        eff = WINGS.spell_effects[0]
        legal = self.game.legal_targets(self.a, eff)
        self.assertIn(flyer, legal)
        self.assertNotIn(ground, legal)

    def test_regrow_two(self):
        self.a.graveyard.extend([BEAR, BEAR, BEAR])
        effect = FIGHT_ON.spell_effects[0]
        target = self.game.bind_graveyard_targets(self.a, [effect])[0]     # targets are chosen before resolution
        self.assertEqual(len(target), 2)
        self.game.resolve(self.a, effect, target)
        self.assertEqual(self.a.hand.count(BEAR), 2)

    def test_choose_color_land(self):
        land = self.game.enter_battlefield(self.a, HAVEN)
        self.assertTrue(land.tapped)
        self.assertEqual(len(land.card.produces), 1)

    def test_enchanted_anthem(self):
        self.perm(TALE)
        bear = self.perm(BEAR)
        other = self.perm(BEAR)
        aura = self.perm(card("Aura", "{1}", "Enchantment — Aura", "Enchant creature"))
        self.assertEqual(bear.power, 2)
        bear.auras.append(aura)
        self.assertEqual(bear.power, 4)
        self.assertEqual(other.power, 2)

    def test_dragon_entering_returns_dragonstorm(self):
        storm = self.perm(STORM)
        self.game.enter_battlefield(self.a, BEAR)
        self.game.settle()
        self.assertIn(storm, self.a.battlefield)
        self.game.enter_battlefield(self.a, card("Whelp", "{2}{R}", "Creature — Dragon", "Flying", 2, 2))
        self.game.settle()
        self.assertNotIn(storm, self.a.battlefield)
        self.assertIn(STORM, self.a.hand)

    def test_untap_during_each_other_untap_step(self):
        skin = self.perm(SKIN)
        skin.tapped = True
        self.game.take_turn(self.b)
        self.assertFalse(skin.tapped)


if __name__ == "__main__":
    unittest.main()
