"""The remainder of #317: 'counter that spell' targeted triggers, 'that spell or ability's controller',
'one or more colors' conditions, 'If you do, ... for each of that spell's colors', and the remaining
targeted-copy restrictions (an opponent controls / N times)."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.engine import Game, Permanent, Player, StackItem

from tests.test_templates import BEAR, ISLAND, MOUNTAIN, SHOCK, card

GLYPH = card("Test Glyph", "{3}{W}{U}", "Creature — Bird Wizard",
             "Whenever ~ becomes the target of a spell or ability for the first time each turn, counter that spell or ability.", 2, 2)
SLIVER = card("Test Sliver", "{1}{U}", "Creature — Sliver",
              "Whenever ~ becomes the target of a spell or ability an opponent controls, counter that spell or ability unless its controller pays {2}.", 1, 1)
VEX = card("Vex", "{2}{U}", "Instant", "Counter target spell. That spell's controller may draw a card.")
RETRO = card("Test Retro", "{2}{U}{R}", "Creature — Human Wizard",
             "Whenever ~ becomes the target of a spell or ability, ~ deals 3 damage to that spell or ability's controller.", 2, 2)
CORNUCOPIA = card("Ancient Cornucopia", "{2}{G}", "Enchantment",
                  "Whenever you cast a spell that's one or more colors, you may gain 1 life for each color that spell is.")
MOONVEIL = card("Moonveil Regent", "{5}{R}{R}", "Creature — Dragon",
                "Whenever you cast a spell, you may discard your hand. If you do, draw a card for each of that spell's colors.", 4, 4)
OPPS_COPY = card("Test Opps", "{3}{U}", "Instant", "Copy target instant or sorcery spell an opponent controls twice.")
THRICE = card("Test Thrice", "{3}{U}", "Instant", "Copy target permanent spell you control three times.")
DECREE = card("Test Decree", "{3}{W}{W}", "Enchantment",
              "Whenever a player casts a spell, counter that spell and put a depletion counter on ~.")
LUNAR = card("Test Lunar", "{2}{U}", "Enchantment", "When an opponent casts a spell, sacrifice ~ and counter that spell.")
BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 3 damage to any target.")
TWO_COLOR = card("Test Two Color", "{U}{R}", "Sorcery", "")
COLORLESS = card("Test Colorless", "{2}", "Artifact", "")


class SpellRefRemainderTests(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [BEAR] * 10, HeuristicAI())
        self.b = Player("b", [BEAR] * 10, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
        for _ in range(6):
            self.perm(MOUNTAIN, self.a)
            self.perm(ISLAND, self.a)
            self.perm(MOUNTAIN, self.b)

    def perm(self, c, owner):
        p = Permanent(c, owner)
        p.sick, p.tapped = False, False
        owner.battlefield.append(p)
        return p

    def test_templates_match(self):
        for c in (GLYPH, SLIVER, VEX, RETRO, CORNUCOPIA, MOONVEIL, OPPS_COPY, THRICE, DECREE, LUNAR):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [], c.name)

    def test_counter_that_spell_trigger_counters_the_targeting_spell(self):
        glyph = self.perm(GLYPH, self.a)
        self.b.hand = [BOLT]
        self.game.cast(self.b, BOLT, [glyph])
        self.game.settle()
        self.assertEqual(self.a.life, 20)          # the bolt was countered, not resolved
        self.assertTrue(any(c.name == BOLT.name for c in self.b.graveyard))

    def test_counter_that_spell_fires_only_once_each_turn(self):
        glyph = self.perm(GLYPH, self.a)
        self.b.hand = [BOLT, card("Test Bolt2", "{R}", "Instant", "Test Bolt2 deals 3 damage to any target.")]
        self.game.cast(self.b, BOLT, [glyph])
        self.game.settle()
        self.assertEqual(self.a.life, 20)          # first bolt countered
        self.assertTrue(any(c.name == BOLT.name for c in self.b.graveyard))
        self.game.cast(self.b, self.b.hand[0], [glyph])
        self.assertEqual(self.game.pending, [])    # "for the first time each turn": no second trigger
        self.game.settle()

    def test_counter_that_spell_unless_its_controller_pays(self):
        sliver = self.perm(SLIVER, self.a)
        self.b.hand = [BOLT]
        self.game.cast(self.b, BOLT, [sliver])     # b has no mana left after casting: cannot pay {2}
        self.game.settle()
        self.assertEqual(self.a.life, 20)

    def test_counter_that_spell_on_a_cast_trigger(self):
        decree = self.perm(DECREE, self.a)
        self.b.hand = [BOLT]
        self.game.cast(self.b, BOLT, [self.a])
        self.game.settle()
        self.assertEqual(self.a.life, 20)          # the bolt was countered
        self.assertTrue(any(c.name == BOLT.name for c in self.b.graveyard))
        self.assertEqual(decree.counters.get("depletion", 0), 1)

    def test_counter_that_spell_on_an_opponent_cast_trigger(self):
        lunar = self.perm(LUNAR, self.a)
        self.b.hand = [BOLT]
        self.game.cast(self.b, BOLT, [self.a])
        self.game.settle()
        self.assertEqual(self.a.life, 20)          # countered before resolving
        self.assertNotIn(lunar, self.a.battlefield)   # sacrificed by the trigger

    def test_vex_lets_the_countered_spells_controller_draw(self):
        spell = StackItem(card=TWO_COLOR, controller=self.b, effects=[], targets=[])
        self.game.stack.append(spell)
        self.a.hand = [VEX]
        before = len(self.b.hand)
        self.assertTrue(self.game.cast(self.a, VEX, [spell]))
        self.game.settle()
        self.assertNotIn(spell, self.game.stack)
        self.assertEqual(len(self.b.hand), before + 1)

    def test_that_spell_or_abilities_controller_takes_damage(self):
        retro = self.perm(RETRO, self.a)
        self.b.hand = [BOLT]
        self.game.cast(self.b, BOLT, [retro])
        self.game.settle()
        self.assertEqual(self.b.life, 17)          # 3 from the trigger, 3 from the bolt

    def test_one_or_more_colors_condition_scales_lifegain(self):
        self.perm(CORNUCOPIA, self.a)
        self.a.hand = [TWO_COLOR]
        self.game.cast(self.a, TWO_COLOR)
        self.game.settle()
        self.assertEqual(self.a.life, 22)

    def test_one_or_more_colors_condition_ignores_colorless_spells(self):
        self.perm(CORNUCOPIA, self.a)
        self.a.hand = [COLORLESS]
        self.game.cast(self.a, COLORLESS)
        self.game.settle()
        self.assertEqual(self.a.life, 20)

    def test_if_you_do_draws_for_each_of_that_spells_colors(self):
        self.perm(MOONVEIL, self.a)
        self.a.hand = [TWO_COLOR, BEAR, BEAR]
        self.game.cast(self.a, TWO_COLOR)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 2)       # discarded 2, drew 2 (the spell's colors)

    def test_copy_an_opponent_controls_twice(self):
        spell = StackItem(card=SHOCK, controller=self.b, effects=list(SHOCK.spell_effects), targets=[self.a])
        self.game.stack.append(spell)
        self.a.hand = [OPPS_COPY]
        self.assertTrue(self.game.cast(self.a, OPPS_COPY, [spell]))
        self.game.settle()
        self.assertEqual(self.a.life, 20 - 2)      # the original shock hit a
        self.assertEqual(self.b.life, 20 - 2 - 2)  # the two copies default to a's opponent

    def test_copy_three_times(self):
        own = StackItem(card=BEAR, controller=self.a, effects=list(BEAR.spell_effects), targets=[])
        self.game.stack.append(own)
        self.a.hand = [THRICE]
        self.assertTrue(self.game.cast(self.a, THRICE, [own]))
        self.game.settle()
        bears = [x for x in self.a.battlefield if x.card.name == BEAR.name]
        self.assertEqual(len(bears), 1 + 3)        # the original spell plus three token copies


if __name__ == "__main__":
    unittest.main()
