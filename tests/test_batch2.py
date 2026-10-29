"""Library and hand effects: tucking, shuffling a graveyard, wheels, halving life."""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem
from tests.test_batch1 import Batch1, BIG
from tests.test_templates import ISLAND
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

    def test_damage_immunity(self):
        rock = self.put(card("Test Rock", "{2}", "Creature — Golem", "Prevent all damage that would be dealt to ~.", 1, 1), self.b)
        self.g.deal_damage(rock, 5, self.a)
        self.assertEqual(rock.damage, 0)

    def test_sacrifice_at_end_step(self):
        perm = self.put(BIG, self.b)
        self.g.resolve(self.a, self.apply_effects("Gain control of target creature an opponent controls until end of turn.")[0], perm,
                       StackItem(self.a, [], []))
        effects = self.apply_effects("Sacrifice it at the beginning of the next end step.")
        self.g.resolve(self.a, effects[0], None, StackItem(self.a, effects, []), prev=perm)
        self.g.begin_end_step(self.a)
        self.g.settle()
        self.assertNotIn(perm, self.a.battlefield)

    def test_damage_per_land(self):
        for _ in range(3):
            self.put(card("Mountain", "", "Basic Land — Mountain", "", None, None))
        victim = self.put(BIG, self.b)
        self.apply("~ deals damage to target creature equal to the number of lands you control.", [victim])
        self.assertEqual(victim.damage, 3)

    def test_group_destroy_and_damage(self):
        mine, theirs = self.put(BIG), self.put(BIG, self.b)
        self.apply("Destroy each creature you don't control.")
        self.assertIn(mine, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)

    def test_overload_cast(self):
        from mtgsim.cards import parse_mana_cost
        rift = card("Test Rift", "{1}{U}", "Instant", "Return target nonland permanent to its owner's hand.\nOverload {3}{U}{U}", None, None)
        self.assertEqual([a.kind for a in rift.alt_costs], ["alt"])
        self.assertEqual(rift.alt_costs[0].effects[0].kind, "group_remove")
        self.assertEqual(rift.alt_costs[0].cost, parse_mana_cost("{3}{U}{U}"))

    def test_overload_resolves_on_each(self):
        from tests.test_templates import ISLAND
        rift = card("Test Rift", "{1}{U}", "Instant", "Return target nonland permanent to its owner's hand.\nOverload {3}{U}{U}", None, None)
        for _ in range(6):
            self.put(ISLAND)
        one, two = self.put(BIG, self.b), self.put(BIG, self.b)
        self.a.hand.append(rift)
        variant = next(v for v in self.g.spell_options(self.a) if self.g._origin(v)[1] == "alt")
        self.g.cast(self.a, variant)
        self.g.settle()
        self.assertNotIn(one, self.b.battlefield)
        self.assertNotIn(two, self.b.battlefield)

    def test_conspire_copies_spell(self):
        from tests.test_templates import MOUNTAIN
        bolt = card("Test Burn", "{R}", "Instant", "~ deals 2 damage to any target.\nConspire", None, None)
        for _ in range(2):
            self.put(card("Test Red Cub", "{R}", "Creature — Goblin", "", 1, 1))
        self.put(MOUNTAIN)
        self.a.hand.append(bolt)
        self.b.life = 20
        self.g.cast(self.a, bolt)
        self.g.settle()
        self.assertEqual(self.b.life, 16)

    def test_hideaway(self):
        land = card("Test Knoll", "", "Land", "Hideaway 4\n{G}, {T}: You may play the exiled card without paying its mana cost if "
                    "creatures you control have total power 10 or greater.", None, None)
        gem = card("Test Gem", "{4}", "Artifact", "", None, None)
        self.a.library[-4:] = [ISLAND, ISLAND, gem, ISLAND]
        perm = self.put(land)
        self.assertEqual(perm.hidden.name, "Test Gem")
        self.assertIn(perm.hidden, self.a.exile)
        self.put(BIG), self.put(BIG), self.put(BIG)
        item = StackItem(self.a, [], [], source=perm)
        self.g.resolve(self.a, land.activated[0].effects[0], None, item)
        self.g.settle()
        self.assertTrue(any(x.card.name == "Test Gem" for x in self.a.battlefield))

    def test_tribute_counters(self):
        giant = self.put(card("Test Giant Tribute", "{4}{R}", "Creature — Giant", "Tribute 2\nWhen ~ enters, if tribute wasn't paid, ~ deals 5 damage to each opponent.", 4, 4))
        self.assertEqual(giant.p1, 2)
        self.assertEqual(self.b.life, 20)

    def test_draw_each_two(self):
        self.apply("You and target opponent each draw two cards.")
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (2, 2))

    def test_bestow_aura_then_creature(self):
        from tests.test_templates import PLAINS
        spirit = card("Test Eidolon", "{1}{W}", "Enchantment Creature — Spirit",
                      "Bestow {3}{W}\nEnchanted creature gets +3/+3.", 2, 2)
        for _ in range(5):
            self.put(PLAINS)
        host = self.put(card("Test Host", "{1}", "Creature — Human", "", 1, 1))
        self.a.hand.append(spirit)
        variant = next(v for v in self.g.spell_options(self.a) if self.g._origin(v)[1] == "bestow")
        self.g.cast(self.a, variant)
        self.g.settle()
        self.assertEqual(host.power, 4)
        aura = next(x for x in self.a.battlefield if x.card.name.startswith("Test Eidolon"))
        self.assertFalse(aura.is_creature)
        self.g.destroy(host)
        self.g.settle()
        self.assertTrue(aura.is_creature and aura in self.a.battlefield)

    def test_ravenous(self):
        hydra = card("Test Hydra", "{X}{G}", "Creature — Hydra", "Ravenous", 0, 0)
        self.a.library = [ISLAND] * 5
        perm = self.g.enter_battlefield(self.a, hydra, x=5)
        self.g.settle()
        self.assertEqual(perm.p1, 5)
        self.assertEqual(len(self.a.hand), 1)
        small = self.g.enter_battlefield(self.a, hydra, x=3)
        self.g.settle()
        self.assertEqual((small.p1, len(self.a.hand)), (3, 1))


if __name__ == "__main__":
    unittest.main()
