"""HeuristicAI plays grammar effects: group sweeps, threaten, distinct targets, X, registered values."""
import unittest

from mtgsim import cx_grammar as G
from mtgsim.cx_grammar import parse_sentence

from tests.test_cx_grammar import DB_FILE, GOBLIN, WOLF, Base
from tests.test_templates import BEAR, ISLAND, card


class Planning(Base):
    def main(self, c, lands=1, land=ISLAND):
        for _ in range(lands):
            self.perm(land, self.a)
        self.a.hand = [c]
        self.a.ai.main_phase(self.game, self.a)
        return c not in self.a.hand

    def test_untargeted_group_sweep_is_cast_when_it_kills(self):
        spell = card("Test Sweep", "{U}", "Sorcery", "Nonblack creatures get -1/-1 until end of turn.")
        goblins = [self.perm(GOBLIN, self.b) for _ in range(3)]
        self.assertTrue(self.main(spell))
        self.assertFalse(any(g in self.b.battlefield for g in goblins))

    def test_untargeted_group_sweep_is_kept_when_it_hurts_us(self):
        spell = card("Test Sweep", "{U}", "Sorcery", "Nonblack creatures get -1/-1 until end of turn.")
        for _ in range(3):
            self.perm(GOBLIN, self.a)
        self.assertFalse(self.main(spell))

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_act_of_treason_steals_the_best_attacker(self):
        from mtgsim.carddb import CardDB
        from tests.test_templates import MOUNTAIN
        act = CardDB().get("Act of Treason")
        wolf, bear = self.perm(WOLF, self.b), self.perm(BEAR, self.b)
        wolf.tapped = True
        self.game.step = "main1"
        for _ in range(3):
            self.perm(MOUNTAIN, self.a)
        plan = self.a.ai.plan_spell(self.game, self.a, act, precombat=True)
        self.assertIsNotNone(plan)
        self.assertIn(plan[1][0], (wolf, bear))
        self.assertIsNone(self.a.ai.plan_spell(self.game, self.a, act, precombat=False))

    def test_distinct_targets_are_different(self):
        spell = card("Test Tired", "{B}", "Instant", "Two target creatures each get -1/-1 until end of turn.")
        x, y = self.perm(GOBLIN, self.b), self.perm(GOBLIN, self.b)
        self.perm(BEAR, self.a)
        plan = self.a.ai.plan_spell(self.game, self.a, spell, precombat=True)
        if plan is not None:            # instants may wait; when planned, the two targets differ
            picked = [t for t in plan[1] if t is not None]
            self.assertEqual(len(picked), len(set(map(id, picked))))
        with self.game.targeting(spell):
            self.assertFalse(self.game.valid_action_targets(self.a, spell.spell_effects, [x, x], spell))
            self.assertTrue(self.game.valid_action_targets(self.a, spell.spell_effects, [x, y], spell))

    def test_x_reaches_inner_player_effects(self):
        effs = parse_sentence("Each opponent mills X cards.") or []
        if not effs:
            self.skipTest("no X player verb registered in this family set")
        self.assertTrue(effs[0].data.get("x"))

    def test_registered_value_is_used(self):
        @G.ai_value("cx_test_kind")
        def value(game, me, eff, obj):
            return 7.0
        try:
            self.assertEqual(G.member_value(self.game, self.a, G._effect("cx_test_kind"), self.a)[0], 7.0)
        finally:
            del G.AI_VALUES["cx_test_kind"]


class CounterNames(Base):
    def test_for_each_counter_on_it_counts_the_stored_name(self):
        self.assertEqual(G._count_spec("soot counter on ~"), ("counters", "soot"))


if __name__ == "__main__":
    unittest.main()


class SpellBar(Base):
    def test_an_empty_second_group_doesnt_stop_the_sweep(self):
        spell = card("Test Sweep", "{U}", "Sorcery", "Goblins your opponents control get -1/-1 until end of turn. "
                                                     "Elves your opponents control get -1/-1 until end of turn.")
        self.assertEqual(spell.unsupported, [])
        for _ in range(3):
            self.perm(GOBLIN, self.b)
        self.perm(ISLAND, self.a)
        self.a.hand = [spell]
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand)

    def test_wrapper_x_is_handed_to_inner_parts_when_planning(self):
        from mtgsim.ai import _sized_inner
        inner = G._effect("lose_life", 0, target="that_controller", data={"x": True})
        wrapper = G._effect("cx_players", 3, data={"who": "opponents", "x": True, "effects": [inner]})
        self.assertEqual([e.amount for e in _sized_inner(self.game, self.a, wrapper)], [3])
