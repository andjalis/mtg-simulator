"""Cards from the upper rank pools: counter riders, Cut Down, flicker with a counter, type anthems with a keyword,
"up to one target creature", each-player draws, tutor and random discard, and costed mana with a color choice."""
import random
import unittest

from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import BEAR, ISLAND, MOUNTAIN, PLAINS, card

NO_MORE_LIES = card("Test No More Lies", "{W}{U}", "Instant", "Counter target spell unless its controller pays {3}. If "
                                                             "that spell is countered this way, exile it instead of "
                                                             "putting it into its owner's graveyard.")
SCATTER = card("Test Scatter", "{2}{U}", "Instant", "Counter target artifact or creature spell unless its controller "
                                                    "pays {4}.")
CUT_DOWN = card("Test Cut Down", "{B}", "Instant", "Destroy target creature with total power and toughness 5 or less.")
DAYDREAM = card("Test Daydream", "{W}", "Sorcery", "Exile target creature you control, then return that card to the "
                                                   "battlefield under its owner's control with a +1/+1 counter on it.")
CORPSES = card("Test Corpses", "{1}{B}", "Enchantment", "Skeletons you control get +1/+0 and have haste.")
SKELETON = card("Test Skeleton", "{1}{B}", "Creature — Skeleton Pirate", "", 2, 2)
PRACTICE = card("Test Practice", "{B}", "Instant", "Up to one target creature gets +1/+1 until end of turn.\nUp to one "
                                                   "target creature gets -1/-1 until end of turn.")
LORAN = card("Test Loran", "{2}{W}", "Legendary Creature — Human Artificer",
             "{T}: You and target opponent each draw a card.", 1, 3)
RUDE = card("Test Rude", "{1}{R}", "Sorcery", "Search your library for a card, put it into your hand, shuffle, then "
                                              "discard a card at random.")
CASTLE = card("Test Castle", "", "Land", "{T}: Add {C}.\n{2}, {T}: Add {U} or {R}.")
GIANT = card("Test Giant", "{4}", "Creature — Giant", "", 4, 4)
SHOCK = card("Test Shock", "{R}", "Instant", "~ deals 2 damage to any target.")


class UpperRankCards(unittest.TestCase):
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

    def test_templates(self):
        for c in (NO_MORE_LIES, SCATTER, CUT_DOWN, DAYDREAM, CORPSES, PRACTICE, LORAN, RUDE, CASTLE):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertTrue(NO_MORE_LIES.spell_effects[0].data.get("exile"))
        self.assertEqual(SCATTER.spell_effects[0].filter, "artifact_creature")

    def test_countered_spell_is_exiled(self):
        item = StackItem(self.b, list(SHOCK.spell_effects), [self.a], card=SHOCK, kind="spell")
        self.game.stack.append(item)
        self.game.counter(self.a, NO_MORE_LIES.spell_effects[0], item)
        self.assertIn(SHOCK, self.b.exile)
        self.assertNotIn(SHOCK, self.b.graveyard)

    def test_cut_down_filter(self):
        bear, giant = self.put(self.b, BEAR), self.put(self.b, GIANT)
        legal = self.game.legal_targets(self.a, CUT_DOWN.spell_effects[0])
        self.assertIn(bear, legal)
        self.assertNotIn(giant, legal)

    def test_flicker_with_counter(self):
        bear = self.put(self.a, BEAR)
        self.game.resolve(self.a, DAYDREAM.spell_effects[0], bear)
        returned = next(x for x in self.a.battlefield if x.card.name == BEAR.name)
        self.assertEqual(returned.p1, 1)
        self.assertNotIn(BEAR, self.a.exile)

    def test_type_anthem_with_keyword(self):
        self.put(self.a, CORPSES)
        skeleton = self.game.enter_battlefield(self.a, SKELETON)
        self.assertEqual(skeleton.power, 3)
        self.assertTrue(skeleton.has("haste"))
        self.assertFalse(self.put(self.a, BEAR).has("haste"))

    def test_each_draw_and_random_discard(self):
        loran = self.put(self.a, LORAN)
        hands = (len(self.a.hand), len(self.b.hand))
        self.assertTrue(self.game.activate_ability(self.a, loran, 0))
        self.game.settle()
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (hands[0] + 1, hands[1] + 1))
        self.put(self.a, MOUNTAIN, 2)
        self.a.library.append(GIANT)
        self.a.hand[:] = [RUDE]
        self.assertTrue(self.game.cast(self.a, RUDE))
        self.game.settle()
        self.assertEqual(len(self.a.hand), 0)               # tutored one card, then discarded at random
        self.assertEqual(len(self.a.graveyard), 2)

    def test_costed_mana_picks_the_color_the_hand_needs(self):
        castle = self.put(self.a, CASTLE)
        self.put(self.a, PLAINS, 2)
        self.a.hand[:] = [card("Test Red Spell", "{R}{R}", "Sorcery", "Draw a card.")]
        self.assertTrue(self.game.activate_ability(self.a, castle, 0))
        self.game.settle()
        self.assertEqual([m.card.produces for m in self.a.pool], [frozenset({"R"})])


if __name__ == "__main__":
    unittest.main()
