"""le-chonk batch 2: "the sacrificed creature's stat" X-amounts, add_mana amounts and that_much draws.

Covers the engine side of the batch: ``item.sac_stats`` (play.cast) and ``last_sacrificed``
(abilities) recorded when a sacrifice cost is paid, the ("sac", stat) and
("stat", who, "mana value") X-quantities in CostsMixin.x_quantity, the amount multiplication
of the add_mana kind, and the draw/discard "that many cards" effects of that_much.py.
"""
import random
import unittest

from mtgsim.cards import Effect
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, PLAINS, SWAMP, card

BEAST = card("Test Beast", "{2}{G}", "Creature — Beast", "", 3, 3)          # power/toughness 3, mana value 3
FLING = card("Test Fling", "{1}{R}", "Sorcery",
             "As an additional cost to cast this spell, sacrifice a creature.\n"
             "Test Fling deals damage equal to the sacrificed creature's power to any target.")
SAC_RITUAL = card("Test Sac Ritual", "{1}{B}", "Sorcery",
                  "As an additional cost to cast this spell, sacrifice a creature.\n"
                  "Add an amount of {B} equal to the sacrificed creature's mana value.")
THOUGHTS = card("Test Thoughts", "{2}{B}", "Sorcery",
                "As an additional cost to cast this spell, sacrifice a creature.\n"
                "Target player discards a number of cards equal to the sacrificed creature's power.")
POACHER = card("Test Poacher", "{2}{B}", "Creature — Human Rogue",
               "{1}, {T}, Sacrifice another creature: You gain life equal to the sacrificed "
               "creature's toughness. Draw a card.", 2, 2)
MUTATION = card("Test Mutation", "{1}{G}", "Sorcery",
                "Return target creature to its owner's hand. Create X 1/1 green Saproling creature "
                "tokens, where X is that creature's mana value.")
CRADLE_DUDE = card("Test Cradle Dude", "{2}{G}", "Creature — Plant",
                   "{2}: Add an amount of {G} equal to this creature's power.", 3, 2)
SPROUT = card("Test Sprout", "{1}{G}", "Creature — Plant",
              "{2}: Add an amount of {G} equal to this creature's power.", 0, 2)
FOREST = card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")
LEDGER = card("Test Ledger", "{2}{U}", "Artifact", "Whenever you gain life, draw that many cards.")
PENANCE = card("Test Penance", "{2}{B}", "Enchantment", "Whenever you gain life, discard that many cards.")
FODDER = card("Test Fodder", "{0}", "Creature — Plant", "", 1, 1)

TEMPLATES = (FLING, SAC_RITUAL, THOUGHTS, POACHER, MUTATION, CRADLE_DUDE, SPROUT, LEDGER, PENANCE)


class SacAmounts(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 2, "main1"
        self.game.active_idx = 0
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, c, n=1, who=None):
        for _ in range(n):
            perm = self.game.enter_battlefield(who or self.a, c)
            perm.sick = False
        self.game.settle()
        return perm

    def black_mana(self, p):
        return sum(1 for m in p.pool if "B" in m.card.produces)

    def test_templates(self):
        for c in TEMPLATES:
            self.assertEqual(c.unsupported, [], c.name)
            self.assertEqual(c.approximations, [], c.name)

    def test_damage_equal_to_sacrificed_power(self):
        self.put(MOUNTAIN, 2)
        victim = self.put(BEAST)                 # 3/3
        target = self.put(BEAR, who=self.b)      # 2/2
        self.a.hand = [FLING]
        self.assertTrue(self.game.cast(self.a, FLING, targets=[target]))
        self.game.settle()
        self.assertNotIn(victim, self.a.battlefield)   # sacrificed
        self.assertNotIn(target, self.b.battlefield)   # dealt 3 damage

    def test_add_mana_equal_to_sacrificed_mana_value(self):
        self.put(SWAMP, 2)
        victim = self.put(BEAST)                 # mana value 3
        self.a.hand = [SAC_RITUAL]
        self.assertTrue(self.game.cast(self.a, SAC_RITUAL))
        self.game.settle()
        self.assertNotIn(victim, self.a.battlefield)
        self.assertEqual(self.black_mana(self.a), 3)

    def test_discard_equal_to_sacrificed_power(self):
        self.put(SWAMP, 3)
        victim = self.put(BEAR)                  # power 2
        self.b.hand = [ISLAND] * 4
        self.a.hand = [THOUGHTS]
        self.assertTrue(self.game.cast(self.a, THOUGHTS, targets=[self.b]))
        self.game.settle()
        self.assertNotIn(victim, self.a.battlefield)
        self.assertEqual(len(self.b.hand), 2)

    def test_ability_life_equal_to_sacrificed_toughness(self):
        poacher = self.put(POACHER)
        victim = self.put(BEAST)                 # toughness 3
        self.put(SWAMP, 2)
        self.a.hand = []
        self.assertTrue(self.game.activate_ability(self.a, poacher, 0))
        self.game.settle()
        self.assertNotIn(victim, self.a.battlefield)
        self.assertEqual(self.a.life, 23)        # 20 + the sacrificed creature's toughness
        self.assertEqual(len(self.a.hand), 1)   # ... and draw a card

    def test_ability_uses_last_sacrificed_only_with_sac_cost(self):
        poacher = self.put(POACHER)
        self.put(SWAMP, 2)
        poacher.last_sacrificed = (5, 5, 5)      # stale stats from an earlier sacrifice
        self.assertFalse(self.game.can_activate(self.a, poacher, 0))   # no creature to sacrifice

    def test_prev_creature_mana_value_x(self):
        self.put(FOREST, 3)
        beast = self.put(BEAST, who=self.b)      # mana value 3
        self.a.hand = [MUTATION]
        self.assertTrue(self.game.cast(self.a, MUTATION, targets=[beast]))
        self.game.settle()
        self.assertIn(beast.card, self.b.hand)   # returned to its owner's hand
        self.assertEqual(sum(1 for x in self.a.battlefield if x.card.is_token), 3)   # X = 3

    def test_add_mana_amount_multiplies_color(self):
        dude = self.put(CRADLE_DUDE)             # power 3
        self.put(FOREST, 2)                      # pay the {2} cost
        self.assertTrue(self.game.activate_ability(self.a, dude, 0))
        self.game.settle()
        self.assertEqual(sum(1 for m in self.a.pool if "G" in m.card.produces), 3)

    def test_add_mana_amount_zero_adds_nothing(self):
        sprout = self.put(SPROUT)                # power 0
        self.put(FOREST, 2)
        self.assertTrue(self.game.activate_ability(self.a, sprout, 0))
        self.game.settle()
        self.assertEqual(list(self.a.pool), [])

    def test_add_mana_without_amount_adds_one(self):
        self.game.resolve(self.a, Effect("add_mana", data={"colors": ["R", "R"]}), None, None)
        self.assertEqual(len(self.a.pool), 2)    # "add {R}{R}": amount 0 means one of each color

    def test_that_much_draw(self):
        self.put(LEDGER)
        self.a.hand = [ISLAND] * 2
        self.game.change_life(self.a, 3, "test")
        self.game.settle()
        self.assertEqual(len(self.a.hand), 5)   # 2 + that many (3) cards drawn

    def test_that_much_discard(self):
        self.put(PENANCE)
        self.a.hand = [ISLAND] * 4
        self.game.change_life(self.a, 2, "test")
        self.game.settle()
        self.assertEqual(len(self.a.hand), 2)   # 4 - that many (2) cards discarded

    def test_gate_sac_stats_feed_sac_xq(self):
        source = self.put(BEAST)
        victim = self.put(FODDER)                # 1/1: gate fodder
        gate = Effect("pay_gate", data={"gate": ("sac", "other creature")})
        gain = Effect("gain_life", 1, data={"xq": ("sac", "power")})
        item = StackItem(self.a, [gate, gain], [None, None], source=source)
        self.game.stack.append(item)
        self.game.settle()
        self.assertNotIn(victim, self.a.battlefield)
        self.assertEqual(self.a.life, 21)        # "If you do, gain life equal to its power"

    def test_x_quantity_sac(self):
        item = StackItem(self.a, [Effect("gain_life", 1)], [], card=BEAST)
        item.sac_stats = (4, 5, 6)
        for stat, expect in (("power", 4), ("toughness", 5), ("mana value", 6)):
            self.assertEqual(self.game.x_quantity(self.a, ("sac", stat), item, None), expect)

    def test_x_quantity_sac_from_ability_source(self):
        poacher = self.put(POACHER)
        poacher.last_sacrificed = (2, 7, 3)
        item = StackItem(self.a, [Effect("gain_life", 1)], [], source=poacher)
        self.assertEqual(self.game.x_quantity(self.a, ("sac", "toughness"), item, None), 7)

    def test_x_quantity_stat_mana_value(self):
        beast = self.put(BEAST)
        # "that creature's mana value": the previous effect's target, a permanent
        self.assertEqual(self.game.x_quantity(self.a, ("stat", "prev", "mana value"), None, beast), 3)
        # "~'s mana value" on the spell itself
        item = StackItem(self.a, [], [], card=BEAST)
        self.assertEqual(self.game.x_quantity(self.a, ("stat", "self", "mana value"), item, None), 3)
        # the source permanent's stat
        item = StackItem(self.a, [], [], source=beast)
        self.assertEqual(self.game.x_quantity(self.a, ("stat", "self", "power"), item, None), 3)


if __name__ == "__main__":
    unittest.main()
