"""Library and hand effects: tucking, shuffling a graveyard, wheels, halving life."""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem
from tests.test_batch1 import Batch1, BIG
from tests.test_templates import card

SPELL = card("Test Spell", "{1}", "Sorcery", "", None, None)


class Batch2(Batch1):
    def apply_effects(self, text):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        return effects

    def test_tuck_second_from_top(self):
        perm = self.put(BIG, self.b)
        self.apply("Put target creature into its owner's library second from the top.", [perm])
        self.assertNotIn(perm, self.b.battlefield)
        self.assertEqual(self.b.library[-2].name, "Test Giant")

    def test_tuck_nonland_on_top(self):
        perm = self.put(BIG, self.b)
        self.apply("Put target nonland permanent on top of its owner's library.", [perm])
        self.assertEqual(self.b.library[-1].name, "Test Giant")

    def test_shuffle_graveyard(self):
        self.a.graveyard.extend([SPELL, SPELL])
        n = len(self.a.library)
        self.apply("Target player shuffles their graveyard into their library.", [self.a])
        self.assertEqual((len(self.a.graveyard), len(self.a.library)), (0, n + 2))

    def test_wheel(self):
        self.a.hand[:] = [SPELL]
        self.b.hand[:] = [SPELL, SPELL]
        self.apply("Each player discards their hand, then draws seven cards.")
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (7, 7))
        self.assertEqual(len(self.a.graveyard), 1)

    def test_time_reversal(self):
        self.a.hand[:] = [SPELL]
        self.a.graveyard[:] = [SPELL]
        self.apply("Each player shuffles their hand and graveyard into their library, then draws seven cards.")
        self.assertEqual((len(self.a.hand), len(self.a.graveyard)), (7, 0))

    def test_half_life(self):
        self.b.life = 15
        self.apply("Target player loses half their life, rounded up.", [self.b])
        self.assertEqual(self.b.life, 7)

    def test_bounce_permanent(self):
        perm = self.put(BIG)
        self.apply("Return a permanent you control to its owner's hand.")
        self.assertNotIn(perm, self.a.battlefield)

    def test_poison(self):
        self.apply("Each opponent gets a poison counter.")
        self.assertEqual(self.b.counters["poison"], 1)

    def test_destroy_nonartifact_creatures(self):
        art = self.put(card("Test Golem", "{3}", "Artifact Creature — Golem", "", 3, 3))
        bear = self.put(BIG, self.b)
        self.apply("Destroy all nonartifact creatures.")
        self.assertIn(art, self.a.battlefield)
        self.assertNotIn(bear, self.b.battlefield)

    def test_destroy_islands(self):
        isl = self.put(card("Island", "", "Basic Land — Island", "", None, None), self.b)
        self.apply("Destroy all Islands.")
        self.assertNotIn(isl, self.b.battlefield)

    def test_double_power(self):
        perm = self.put(BIG)
        self.apply("Double target creature's power until end of turn.", [perm])
        self.assertEqual(perm.power, 8)

    def test_discard_hand(self):
        self.a.hand[:] = [SPELL, SPELL]
        self.apply("Discard your hand.")
        self.assertEqual(len(self.a.hand), 0)

    def test_sacrifice_two_each(self):
        self.put(BIG), self.put(BIG)
        self.put(BIG, self.b), self.put(BIG, self.b)
        self.apply("Each player sacrifices two creatures.")
        self.assertFalse(self.a.creatures or self.b.creatures)

    def test_return_another_creature(self):
        keep, other = self.put(BIG), self.put(card("Test Cub", "{1}", "Creature — Bear", "", 1, 1))
        self.g.resolve(self.a, self.apply_effects("Return another creature you control to its owner's hand.")[0], None,
                       StackItem(self.a, [], [], source=keep))
        self.assertIn(keep, self.a.battlefield)
        self.assertNotIn(other, self.a.battlefield)

    def test_gain_control_until_end_of_turn(self):
        perm = self.put(BIG, self.b)
        self.apply("Gain control of target creature an opponent controls until end of turn.", [perm])
        self.assertIn(perm, self.a.battlefield)

    def test_destroy_tapped_creatures(self):
        up, down = self.put(BIG), self.put(BIG, self.b)
        down.tapped = True
        self.apply("Destroy all tapped creatures.")
        self.assertIn(up, self.a.battlefield)
        self.assertNotIn(down, self.b.battlefield)

    def test_lose_half_self(self):
        self.a.life = 9
        self.apply("You lose half your life, rounded up.")
        self.assertEqual(self.a.life, 4)

    def test_discard_random_target(self):
        self.b.hand[:] = [SPELL]
        self.apply("Target opponent discards a card at random.", [self.b])
        self.assertEqual(len(self.b.hand), 0)

    def test_counter_by_type(self):
        from mtgsim.cards import _parse_effects as parse
        eff = parse("Counter target sorcery spell.")[0][0]
        self.assertEqual(eff.filter, "types:Sorcery")

    def test_evasion_by_color(self):
        from mtgsim.engine import can_block
        wall = card("Test Knight", "{1}{W}", "Creature — Knight", "", 2, 2)
        raider = card("Test Raider", "{1}{B}", "Creature — Rogue", "~ can't be blocked by white creatures.", 2, 2)
        shade = card("Test Shade", "{1}{B}", "Creature — Shade", "~ can't be blocked except by black creatures.", 2, 2)
        blocker, black = self.put(wall, self.b), self.put(card("Test Imp", "{B}", "Creature — Imp", "", 1, 1), self.b)
        self.assertFalse(can_block(blocker, self.put(raider)))
        self.assertTrue(can_block(black, self.put(raider)))
        self.assertFalse(can_block(blocker, self.put(shade)))
        self.assertTrue(can_block(black, self.put(shade)))
        flyer = self.put(card("Test Scout", "{G}", "Creature — Elf", "~ can't be blocked except by creatures with flying.", 1, 1))
        self.assertFalse(can_block(blocker, flyer))

    def test_color_anthem(self):
        self.put(card("Test Druid", "{1}{G}", "Creature — Druid", "Other green creatures you control get +1/+1.", 1, 1))
        green = self.put(card("Test Elk", "{G}", "Creature — Elk", "", 2, 2))
        blue = self.put(card("Test Fish", "{U}", "Creature — Fish", "", 2, 2))
        self.assertEqual((green.power, blue.power), (3, 2))

    def test_no_lifegain(self):
        self.put(card("Test Mute", "{2}", "Creature — Wizard", "Your opponents can't gain life.", 1, 1))
        self.g.change_life(self.b, 3, "test")
        self.g.change_life(self.a, 3, "test")
        self.assertEqual((self.a.life, self.b.life), (23, 20))

    def test_spell_tax(self):
        self.put(card("Test Warden", "{1}{W}", "Creature — Human", "Noncreature spells cost {1} more to cast.", 2, 2))
        self.assertEqual(self.g.cost_of(self.a, SPELL).get("generic"), 2)
        self.assertEqual(self.g.cost_of(self.a, BIG).get("generic"), 4)

    def test_opponent_spell_tax(self):
        self.put(card("Test Jailer", "{1}{W}", "Creature — Human", "Spells your opponents cast cost {1} more to cast.", 2, 2))
        self.assertEqual(self.g.cost_of(self.a, SPELL).get("generic"), 1)
        self.assertEqual(self.g.cost_of(self.b, SPELL).get("generic"), 2)

    def test_generic_discount(self):
        self.put(card("Test Fountain", "{1}{U}", "Creature — Wizard", "Spells you cast cost {1} less to cast.", 2, 2))
        self.assertEqual(self.g.cost_of(self.a, BIG).get("generic"), 3)


if __name__ == "__main__":
    unittest.main()
