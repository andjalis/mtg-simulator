"""Physical copies, stale zone objects, and supported replacement interactions."""
import dataclasses
import random
import unittest

from mtgsim.ai import BaselineAI
from mtgsim.cards import Effect
from mtgsim.engine import Game, Player
from mtgsim.identity import CardInstance
from mtgsim.rules_events import MoveIntent, Replacement, replace_event
from tests.test_templates import BEAR, ISLAND, card


class IdentityEvents(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], BaselineAI()), Player("b", [], BaselineAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step, self.g._priority_depth = 2, "main1", 1

    def test_duplicate_definition_creates_distinct_physical_cards(self):
        self.a.hand = [BEAR, BEAR]
        first, second = self.a.hand
        self.assertIsInstance(first, CardInstance)
        self.assertNotEqual(first.physical_id, second.physical_id)
        self.assertNotEqual(first, second)
        self.assertEqual(len(set(self.a.hand)), 2)
        self.a.hand.remove(second)
        self.assertIs(self.a.hand[0], first)
        self.assertNotIn(second, self.a.hand)
        self.assertFalse(hasattr(BEAR, "physical_id"))
        token_blueprint = dataclasses.replace(first, is_token=True)
        token_a = self.g.enter_battlefield(self.a, token_blueprint)
        token_b = self.g.enter_battlefield(self.a, token_blueprint)
        self.assertNotEqual(token_a.front.physical_id, token_b.front.physical_id)

    def test_zone_reference_expires_after_leave_and_return(self):
        self.a.hand = [BEAR]
        physical = self.a.hand[0]
        ref = self.a.hand.reference(physical)
        self.g.move_card(physical, self.a.hand, self.a.exile)
        self.g.move_card(physical, self.a.exile, self.a.hand)
        self.assertIsNone(ref.find(self.a.hand))
        self.assertIs(self.a.hand[0], physical)
        self.assertEqual(physical.physical_id, ref.physical_id)

    def test_reordering_preserves_zone_objects(self):
        self.a.library = [BEAR, ISLAND, BEAR]
        refs = [self.a.library.reference(c) for c in self.a.library]
        self.a.library.shuffle(random.Random(1))
        self.a.library.reverse()
        self.assertTrue(all(ref.find(self.a.library) is not None for ref in refs))

    def test_slice_and_bulk_moves_track_every_copy(self):
        self.a.hand.extend([BEAR, BEAR])
        first, second = self.a.hand
        ref = self.a.hand.reference(second)
        self.a.hand[1:2] = [ISLAND, BEAR]
        self.assertIsNone(ref.find(self.a.hand))
        self.assertIs(self.a.hand[0], first)
        self.assertEqual(len({c.physical_id for c in self.a.hand}), 3)
        self.a.exile += [self.a.hand.pop()]
        self.assertEqual(len(self.a.hand), 2)

    def test_cast_resolve_die_preserves_physical_identity(self):
        definition = card("Free creature", types="Creature", power=2, toughness=2)
        self.a.hand = [definition]
        physical = self.a.hand[0]
        before = physical.generation
        self.assertTrue(self.g.cast(self.a, physical))
        self.assertIs(self.g.stack[-1].physical_card, physical)
        self.g.resolve_top()
        permanent = self.a.creatures[0]
        self.assertIs(permanent.front, physical)
        self.g.destroy(permanent)
        self.assertIs(self.a.graveyard[0], physical)
        self.assertGreater(physical.generation, before)

    def test_duplicate_alternate_options_bind_exact_origins(self):
        definition = card("Flashback draw", types="Sorcery", text="Draw a card.\nFlashback {0}")
        self.a.graveyard = [definition, definition]
        first, second = self.a.graveyard
        options = [c for c in self.g.spell_options(self.a) if self.g._origin(c)[1] == "flashback"]
        self.assertEqual(len(options), 2)
        self.assertIsNot(options[0], options[1])
        self.assertIs(self.g._origin(options[0])[0], first)
        self.assertIs(self.g._origin(options[1])[0], second)
        self.a.library = [ISLAND]
        self.assertTrue(self.g.cast(self.a, options[1]))
        self.g.resolve_top()
        self.assertIn(first, self.a.graveyard)
        self.assertNotIn(second, self.a.graveyard)
        self.assertIn(second, self.a.exile)

    def test_stale_alternate_option_cannot_cast_returned_object(self):
        definition = card("Flashback draw", types="Sorcery", text="Draw a card.\nFlashback {0}")
        self.a.graveyard = [definition]
        physical = self.a.graveyard[0]
        option = next(c for c in self.g.spell_options(self.a) if self.g._origin(c)[1] == "flashback")
        self.g.move_card(physical, self.a.graveyard, self.a.exile)
        self.g.move_card(physical, self.a.exile, self.a.graveyard)
        self.assertFalse(self.g.cast(self.a, option))
        fresh = next(c for c in self.g.spell_options(self.a) if self.g._origin(c)[1] == "flashback")
        self.assertTrue(self.g.can_cast_now(self.a, fresh))

    def test_graveyard_ability_cannot_follow_leave_and_return(self):
        definition = card("Returner", types="Creature", power=2, toughness=2,
                          text="{0}: Return this card from your graveyard to the battlefield.")
        self.a.graveyard = [definition]
        physical = self.a.graveyard[0]
        self.assertTrue(self.g.activate_graveyard(self.a, physical))
        self.g.move_card(physical, self.a.graveyard, self.a.exile)
        self.g.move_card(physical, self.a.exile, self.a.graveyard)
        self.g.resolve_top()
        self.assertEqual(self.a.creatures, [])
        self.assertIn(physical, self.a.graveyard)

    def test_graveyard_trigger_snapshot_taken_when_queued(self):
        self.a.graveyard = [BEAR]
        physical = self.a.graveyard[0]
        self.g.queue_trigger(self.a, [Effect("return_self_gy")], context=physical)
        self.g.move_card(physical, self.a.graveyard, self.a.exile)
        self.g.move_card(physical, self.a.exile, self.a.graveyard)
        self.g.flush_triggers()
        self.g.resolve_top()
        self.assertEqual(self.a.creatures, [])

    def test_owner_survives_reanimation_by_opponent(self):
        self.a.graveyard = [BEAR]
        physical = self.a.graveyard.pop()
        permanent = self.g.enter_battlefield(self.b, physical)
        self.assertIs(permanent.owner, self.a)
        self.g.destroy(permanent)
        self.assertIn(physical, self.a.graveyard)
        self.assertNotIn(physical, self.b.graveyard)

    def test_regeneration_preserves_object_and_emits_event(self):
        permanent = self.g.enter_battlefield(self.a, BEAR)
        generation = permanent.front.generation
        permanent.regeneration_shields = 1
        permanent.damage = 2
        self.g.destroy(permanent)
        self.assertIn(permanent, self.a.battlefield)
        self.assertEqual(permanent.front.generation, generation)
        event = next(e for e in self.g.rule_events.history if e.kind == "destruction_replaced")
        self.assertEqual(event.replacements, ("regeneration",))
        self.assertEqual(event.before.physical_id, permanent.front.physical_id)

    def test_replacement_choice_and_no_false_death_flags(self):
        permanent = self.g.enter_battlefield(self.a, BEAR)
        permanent.counters["finality"] = 1
        permanent.exile_turn = self.g.turn
        self.a.ai.choose_replacement = lambda game, me, choices, intent: "exile-if-dies-this-turn"
        self.g.destroy(permanent)
        event = next(e for e in self.g.rule_events.history if e.kind == "zone_change" and e.destination == "exile")
        self.assertEqual(event.replacements, ("exile-if-dies-this-turn",))
        self.assertEqual(event.destination, "exile")
        self.assertFalse(self.a.creature_died_turn)
        self.assertFalse(self.g.creature_died_turn)
        self.assertIn(permanent.front, self.a.exile)

    def test_zone_event_retains_last_known_counters(self):
        permanent = self.g.enter_battlefield(self.a, BEAR)
        permanent.counters["+1/+1"] = 2
        self.g.destroy(permanent)
        event = next(e for e in self.g.rule_events.history if e.kind == "zone_change" and e.destination == "graveyard")
        permanent.counters.clear()
        self.assertEqual(event.before.counters, (("+1/+1", 2),))
        self.assertEqual(event.before.power, 4)

    def test_each_replacement_applies_at_most_once(self):
        rules = [Replacement("a", lambda e: True, lambda e: dataclasses.replace(e, destination="hand")),
                 Replacement("b", lambda e: True, lambda e: dataclasses.replace(e, destination="graveyard"))]
        event = replace_event(MoveIntent("graveyard"), rules, lambda choices, e: choices[0])
        self.assertEqual(event.applied, ("a", "b"))

    def test_event_bus_delivers_draw_then_trigger(self):
        observed = []
        self.g.rule_events.listeners.append(observed.append)
        self.a.library = [ISLAND]
        physical = self.a.library[-1]
        self.g.draw(self.a)
        self.assertIs(self.a.hand[-1], physical)
        self.assertEqual([e.kind for e in observed], ["zone_change", "you_draw", "opp_draw"])

    def test_token_dies_even_though_no_card_remains_in_graveyard(self):
        token = dataclasses.replace(BEAR, is_token=True)
        permanent = self.g.enter_battlefield(self.a, token)
        self.g.destroy(permanent)
        self.assertEqual(self.a.graveyard, [])
        self.assertTrue(self.a.creature_died_turn)
        self.assertTrue(any(e.kind == "dies" for e in self.g.rule_events.history))

    def test_library_look_and_put_back_preserve_unmoved_objects(self):
        self.a.library = [BEAR, ISLAND, BEAR]
        physical = list(self.a.library)
        refs = [self.a.library.reference(c) for c in physical]
        self.a.ai.scry = lambda game, me, cards: cards
        self.g.scry(self.a, 2)
        self.assertTrue(all(ref.find(self.a.library) is c for ref, c in zip(refs, physical)))
        self.a.ai.choose_dig = lambda game, me, cards, keep: [cards[-1]]
        chosen = self.a.library[-2]
        remaining = [self.a.library.reference(c) for c in self.a.library if c is not chosen]
        self.g.dig(self.a, 2, 1)
        self.assertIs(self.a.hand[-1], chosen)
        self.assertTrue(all(ref.find(self.a.library) is not None for ref in remaining))

    def test_rebinding_transformed_front_preserves_owner(self):
        self.a.exile = [BEAR]
        physical = self.a.exile.pop()
        face = self.g.enter_battlefield(self.b, ISLAND)
        face.front = physical
        self.assertIs(face.owner, self.a)
        self.g.leave_battlefield(face, "hand")
        self.assertIn(physical, self.a.hand)
        self.assertNotIn(physical, self.b.hand)
