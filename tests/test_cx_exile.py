"""Single-permanent blink selection, ownership and physical-card behavior."""
import random
import unittest

from mtgsim.ai import HeuristicAI, BaselineAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.cards import _parse_effects, make_token
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import BEAR, ISLAND, SHOCK, card

FATE = "Exile target creature or enchantment, then return it to the battlefield under its owner's control."
FLICKER = "Exile target nontoken permanent, then return it to the battlefield under its owner's control."


class SinglePermanentBlink(unittest.TestCase):
    def setUp(self):
        self.a = Player('a', [], HeuristicAI())
        self.b = Player('b', [], HeuristicAI())
        self.g = Game(self.a, self.b, random.Random(16))
        self.g.turn, self.g.step = 4, 'main1'
        for p in self.g.players:
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def effects(self, text):
        effects, ignored = _parse_effects(text)
        self.assertFalse(ignored, ignored)
        self.assertEqual(len(effects), 1)
        return effects

    def resolve(self, text, target, source=None):
        effects = self.effects(text)
        item = StackItem(self.a, effects, [target], source=source)
        self.g.check_ward(item)
        self.g.stack.append(item)
        self.g.settle()
        return item

    def test_union_targets_only_creatures_and_enchantments(self):
        creature = self.g.enter_battlefield(self.a, BEAR)
        enchantment = self.g.enter_battlefield(self.b, card('Test enchantment', '{2}', 'Enchantment'))
        artifact = self.g.enter_battlefield(self.b, card('Test artifact', '{2}', 'Artifact'))
        land = self.g.enter_battlefield(self.a, ISLAND)
        effect = self.effects(FATE)[0]
        for permanent in (creature, enchantment):
            self.assertTrue(self.g.legal_target(self.a, effect, permanent))
        for permanent in (artifact, land):
            self.assertFalse(self.g.legal_target(self.a, effect, permanent))

    def test_nontoken_permanent_includes_lands_but_excludes_tokens(self):
        land = self.g.enter_battlefield(self.a, ISLAND)
        creature = self.g.enter_battlefield(self.b, BEAR)
        token = self.g.enter_battlefield(self.a, make_token('Soldier', 1, 1))
        effect = self.effects(FLICKER)[0]
        self.assertEqual(set(self.g.legal_targets(self.a, effect)), {land, creature})
        self.assertFalse(self.g.legal_target(self.a, effect, token))

    def test_blink_keeps_physical_identity_and_resets_permanent_state(self):
        old = self.g.enter_battlefield(self.a, BEAR)
        old.tapped, old.damage = True, 1
        old.counters['+1/+1'] = 3
        physical = old.front
        generation = physical.generation
        item = self.resolve(FATE, old)
        self.assertTrue(item.resolved)
        new = next(x for x in self.a.creatures if x.front is physical)
        self.assertIsNot(old, new)
        self.assertGreater(physical.generation, generation)
        self.assertFalse(new.tapped)
        self.assertEqual((new.damage, new.p1), (0, 0))
        self.assertTrue(new.sick)
        self.assertFalse(self.a.exile)

    def test_stolen_creature_returns_under_owner_control(self):
        from mtgsim.counter_mechanics import change_control
        obj = self.g.enter_battlefield(self.b, BEAR)
        physical = obj.front
        change_control(self.g, obj, self.a)
        self.resolve("Exile target creature you control, then return that card to the battlefield under their owner's control.", obj)
        self.assertFalse(self.a.creatures)
        new = next(x for x in self.b.creatures if x.front is physical)
        self.assertIs(new.owner, self.b)
        self.assertIs(new.controller, self.b)

    def test_token_blinks_out_and_never_returns(self):
        token = self.g.enter_battlefield(self.a, make_token('Soldier', 1, 1))
        item = self.resolve(FATE, token)
        self.assertTrue(item.resolved)
        self.assertFalse(self.a.creatures)
        self.assertFalse(self.a.exile)

    def test_only_targeted_physical_duplicate_moves(self):
        first = self.g.enter_battlefield(self.a, BEAR)
        second = self.g.enter_battlefield(self.a, BEAR)
        self.a.hand.append(BEAR)
        untouched = self.a.hand[-1]
        self.resolve(FATE, second)
        self.assertIn(first, self.a.battlefield)
        self.assertIs(self.a.hand[0], untouched)
        self.assertEqual(len(self.a.creatures), 2)
        self.assertTrue(any(x.front is second.front for x in self.a.creatures))

    def test_target_that_left_and_reentered_is_not_followed(self):
        old = self.g.enter_battlefield(self.a, BEAR)
        effects = self.effects(FATE)
        item = StackItem(self.a, effects, [old])
        self.g.check_ward(item)
        self.g.leave_battlefield(old, 'exile')
        self.a.exile.remove(old.front)
        new = self.g.enter_battlefield(self.a, old.front)
        generation = new.front.generation
        self.g.stack.append(item)
        self.g.settle()
        self.assertFalse(item.resolved)
        self.assertIn(new, self.a.battlefield)
        self.assertEqual(new.front.generation, generation)

    def test_optional_zero_target_resolves(self):
        item = self.resolve("Exile up to one target artifact or creature you control, then return it to the battlefield under its owner's control.", None)
        self.assertTrue(item.resolved)
        self.assertFalse(self.a.battlefield)

    def test_another_target_excludes_ability_source(self):
        source = self.g.enter_battlefield(self.a, BEAR)
        other = self.g.enter_battlefield(self.a, BEAR)
        effect = self.effects("Exile another target creature, then return it to the battlefield under its owner's control.")[0]
        item = StackItem(self.a, [effect], [source], source=source)
        with self.g.targeting(item):
            self.assertFalse(self.g.legal_target(self.a, effect, source))
            self.assertTrue(self.g.legal_target(self.a, effect, other))

    def test_two_sentence_normalization_keeps_behavior(self):
        obj = self.g.enter_battlefield(self.a, BEAR)
        self.resolve("Exile target creature or enchantment. Return it to the battlefield under its owner's control.", obj)
        self.assertTrue(any(x.front is obj.front for x in self.a.battlefield))
        self.assertNotIn(obj, self.a.battlefield)

    def test_unsupported_variants_preserve_original_ignored_text(self):
        cases = ["Exile target creature you control, then return it to the battlefield under your control.",
                 "Exile two target creatures, then return those cards to the battlefield under their owners' control.",
                 "Exile target creature, then return it to the battlefield tapped under its owner's control.",
                 "Exile target creature that entered this turn. Return it to the battlefield under its owner's control."]
        for text in cases:
            with self.subTest(text=text):
                _, ignored = _parse_effects(text)
                self.assertTrue(ignored)
                self.assertFalse(any('CXOWNERBLINK' in line for line in ignored))

    @unittest.skipUnless(ALL_CARDS.exists(), 'offline database unavailable')
    def test_energy_self_blink_uses_existing_ability_cost(self):
        creature = CardDB(offline=True).get('Aethergeode Miner')
        self.assertFalse(creature.unsupported)
        old = self.g.enter_battlefield(self.a, creature)
        self.a.counters['energy'] = 2
        self.assertTrue(self.g.activate_ability(self.a, old, 0))
        self.assertEqual(self.a.counters['energy'], 0)
        new = next(x for x in self.a.creatures if x.front is old.front)
        self.assertIsNot(new, old)

    @unittest.skipUnless(ALL_CARDS.exists(), 'offline database unavailable')
    def test_blur_normal_cast_blinks_then_draws_for_both_pilots(self):
        spell = CardDB(offline=True).get('Blur')
        self.assertFalse(spell.unsupported)
        for pilot in (HeuristicAI, BaselineAI):
            with self.subTest(pilot=pilot.__name__):
                a, b = Player('a', [], pilot()), Player('b', [], pilot())
                g = Game(a, b, random.Random(12))
                g.turn, g.step = 3, 'main1'
                for p in g.players:
                    p.ai.respond = p.ai.respond_extras = lambda *args: None
                for _ in range(3):
                    g.enter_battlefield(a, ISLAND)
                old = g.enter_battlefield(a, BEAR)
                a.library.append(SHOCK)
                drawn = a.library[-1]
                a.hand.append(spell)
                self.assertTrue(g.cast(a, spell, [old, None]))
                self.assertIs(a.hand[-1], drawn)
                self.assertTrue(any(x.front is old.front for x in a.creatures))
                self.assertNotIn(old, a.battlefield)
