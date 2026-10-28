"""Rules behavior for edicts, life from a destroyed creature, solo restrictions and the monarch."""
import random
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted, BEAR
from tests.test_templates import ISLAND, card

BIG = card("Test Giant", "{4}", "Creature — Giant", "", 4, 5)
EMBER = card("Test Ember", "{1}{R}", "Creature — Beast", "~ can't attack or block alone.", 3, 3)
CROWN = card("Test Commodore", "{2}{U}", "Creature — Pirate", "When Test Commodore enters, you become the monarch.", 1, 1)


class Batch1(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player('a', [], Scripted()), Player('b', [], Scripted())
        self.g = Game(self.a, self.b, random.Random(3))
        self.g.turn, self.g.step = 2, 'main1'
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def put(self, definition, p=None):
        perm = self.g.enter_battlefield(p or self.a, definition)
        perm.sick = False
        self.g.settle()
        return perm

    def apply(self, text, targets=()):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        targets = list(targets) + [None] * (len(effects) - len(targets))
        item = StackItem(self.a, effects, targets)
        prev = None
        for eff, target in zip(effects, targets):
            self.g.resolve(self.a, eff, target, item, prev=prev)
            prev = target

    def test_target_player_sacrifices_the_weakest_creature(self):
        weak, strong = self.put(BEAR, self.b), self.put(BIG, self.b)
        self.apply("Target player sacrifices a creature.", [self.b])
        self.assertNotIn(weak, self.b.battlefield)
        self.assertIn(strong, self.b.battlefield)

    def test_each_player_sacrifices(self):
        mine, theirs = self.put(BEAR, self.a), self.put(BEAR, self.b)
        self.apply("Each player sacrifices a creature.")
        self.assertNotIn(mine, self.a.battlefield)
        self.assertNotIn(theirs, self.b.battlefield)

    def test_gain_life_equal_to_destroyed_creatures_power(self):
        big = self.put(BIG, self.b)
        life = self.a.life
        self.apply("Destroy target creature. You gain life equal to its power.", [big])
        self.assertEqual(self.a.life, life + 4)

    def test_gain_life_equal_to_toughness(self):
        big = self.put(BIG, self.b)
        life = self.a.life
        self.apply("Destroy target creature. You gain life equal to its toughness.", [big])
        self.assertEqual(self.a.life, life + 5)

    def test_cant_attack_alone(self):
        ember = self.put(EMBER)
        self.a.ai.attack = (ember,)
        self.g.combat(self.a, self.b)
        self.assertEqual(self.b.life, 20)
        bear = self.put(BEAR)
        self.a.ai.attack = (ember, bear)
        self.g.combat(self.a, self.b)
        self.assertEqual(self.b.life, 20 - 5)

    def test_cant_block_alone(self):
        ember = self.put(EMBER, self.b)
        attacker = self.put(BEAR)
        self.a.ai.attack = (attacker,)
        self.b.ai.block = {attacker: (ember,)}
        self.g.combat(self.a, self.b)
        self.assertEqual(self.b.life, 18)
        self.assertEqual(ember.damage, 0)

    def test_monarch_draws_and_changes_on_combat_damage(self):
        self.put(CROWN)
        self.assertIs(self.g.monarch, self.a)
        hand = len(self.a.hand)
        self.g.begin_end_step(self.a)
        self.assertEqual(len(self.a.hand), hand + 1)
        hitter = self.put(BEAR, self.b)
        self.g.monarch = self.a
        self.b.ai.attack = (hitter,)
        self.g.combat(self.b, self.a)
        self.assertIs(self.g.monarch, self.b)

    def test_tap_and_freeze_two_creatures(self):
        x, y = self.put(BEAR, self.b), self.put(BIG, self.b)
        self.apply("Tap up to two target creatures. Those creatures don't untap during their controller's next untap step.", [x])
        self.assertTrue(x.tapped)
        self.assertEqual(x.skip_untap, 1)
        self.assertTrue(y.tapped)
        self.assertEqual(y.skip_untap, 1)

    def test_pump_then_untap(self):
        x = self.put(BEAR)
        x.tapped = True
        self.apply("Creatures you control get +1/+2 until end of turn. Untap those creatures.")
        self.assertFalse(x.tapped)
        self.assertEqual(x.power, 3)

    def test_gain_life_lost_this_way(self):
        self.apply("Each opponent loses 3 life. You gain life equal to the life lost this way.")
        self.assertEqual((self.a.life, self.b.life), (23, 17))

    def test_damaged_creature_is_exiled_instead_of_dying(self):
        bear = self.put(BEAR, self.b)
        self.apply("~ deals 3 damage to target creature. If a creature dealt damage this way would die this turn, exile it instead.", [bear])
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(len(self.b.graveyard), 0)
        self.assertEqual(len(self.b.exile), 1)

    def test_wrath_exiles_all_dying_creatures(self):
        self.put(BEAR, self.b)
        big = self.put(BIG)
        self.apply("~ deals 3 damage to each creature. If a creature dealt damage this way would die this turn, exile it instead.")
        self.assertEqual(len(self.b.exile), 1)
        self.assertIn(big, self.a.battlefield)

    def test_player_hexproof_blocks_opponent_targeting(self):
        aegis = card("Test Aegis", "{2}{W}", "Enchantment", "You have hexproof.")
        self.put(aegis, self.b)
        eff, _ = _parse_effects("~ deals 2 damage to any target.")
        self.assertNotIn(self.b, self.g.legal_targets(self.a, eff[0]))
        self.assertIn(self.b, self.g.legal_targets(self.b, eff[0]))

    def test_arrest_stops_combat_and_activation(self):
        arrest = card("Test Arrest", "{2}{W}", "Enchantment — Aura",
                      "Enchant creature\nEnchanted creature can't attack or block, and its activated abilities can't be activated.")
        ping = card("Test Pinger", "{1}", "Creature — Human", "{T}: ~ deals 1 damage to any target.", 1, 1)
        pinger = self.put(ping, self.b)
        self.assertTrue(self.g.can_activate(self.b, pinger, 0))
        aura = self.g.enter_battlefield(self.a, arrest)
        aura.attached_to = pinger
        pinger.auras.append(aura)
        self.assertFalse(self.g.can_activate(self.b, pinger, 0))

    def test_etb_damage_equal_to_power(self):
        redcap = self.put(card("Test Redcap", "{2}{R}", "Creature — Elemental", "", 2, 2), self.a)
        eff, bad = _parse_effects("it deals damage equal to its power to any target.")
        self.assertFalse(bad)
        life = self.b.life
        self.g.resolve(self.a, eff[0], self.b, StackItem(self.a, eff, [self.b], source=redcap))
        self.assertEqual(self.b.life, life - 2)

    def test_enters_tapped_with_charge_counters(self):
        vivid = card("Test Vivid", "", "Land", "~ enters tapped with two charge counters on it.\n{T}: Add {U}.")
        perm = self.g.enter_battlefield(self.a, vivid)
        self.assertTrue(perm.tapped)
        self.assertEqual(perm.counters["charge"], 2)

    def test_powerstone_mana_only_casts_artifacts(self):
        self.apply("Create a tapped Powerstone token.")
        stone = next(x for x in self.a.battlefield if x.card.token_kind == "powerstone")
        self.assertTrue(stone.tapped)
        stone.tapped = False
        self.assertEqual(stone.card.mana_restriction, "artifact")

    def test_provoke_untaps_and_forces_block(self):
        goblin = card("Test Provoker", "{2}{R}", "Creature — Goblin", "Provoke", 2, 2)
        attacker = self.put(goblin)
        wall = self.put(card("Test Wall", "{1}", "Creature — Wall", "", 0, 4), self.b)
        wall.tapped = True
        self.a.ai.attack = (attacker,)
        self.g.combat(self.a, self.b)
        self.assertEqual(self.b.life, 20)
        self.assertEqual(wall.damage, 2)

    def test_assign_combat_damage_as_though_unblocked(self):
        wolf = self.put(card("Test Wolf", "{2}{G}", "Creature — Wolf",
                             "You may have ~ assign its combat damage as though it weren't blocked.", 3, 3))
        wall = self.put(card("Test Wall", "{1}", "Creature — Wall", "", 0, 6), self.b)
        self.a.ai.attack = (wolf,)
        self.b.ai.block = {wolf: (wall,)}
        self.g.combat(self.a, self.b)
        self.assertEqual(self.b.life, 17)

    def test_phantom_prevents_damage_and_loses_a_counter(self):
        phantom = self.put(card("Test Phantom", "{2}{G}", "Creature — Spirit",
                                "~ enters with three +1/+1 counters on it.\n"
                                "If damage would be dealt to ~, prevent that damage. Remove a +1/+1 counter from ~.", 0, 0))
        self.assertEqual(phantom.p1, 3)
        self.g.deal_damage(phantom, 5, by=self.b)
        self.assertEqual((phantom.damage, phantom.p1), (0, 2))

    def test_converge_counts_colors_spent(self):
        crawler = card("Test Crawler", "{2}", "Artifact Creature — Construct",
                       "Converge — ~ enters with a +1/+1 counter on it for each color of mana spent to cast it.", 0, 0)
        self.assertTrue(crawler.advanced_rules.get("sunburst"))


if __name__ == '__main__':
    unittest.main()
