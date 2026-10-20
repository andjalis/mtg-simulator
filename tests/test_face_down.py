"""Real-card regressions for the shared face-down system and priority actions."""
import random
import unittest

from mtgsim import facedown
from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.cards import Effect, card_from_scryfall
from mtgsim.coverage import FULL, card_coverage
from mtgsim.engine import Game, Permanent, Player, StackItem


@unittest.skipUnless(ALL_CARDS.exists(), "build the offline card database")
class FaceDownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDB(offline=True)

    def setUp(self):
        forest = self.db.get("Forest")
        self.a = Player("a", [forest] * 30, HeuristicAI())
        self.b = Player("b", [forest] * 30, HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(5), log=True)
        self.game.turn, self.game.step = 1, "main1"
        self.game._priority_depth = 1  # explicit decisions in rules tests
        self.a.library = self.b.library = [forest] * 30

    def lands(self, name, n):
        return [self.game.enter_battlefield(self.a, self.db.get(name)) for _ in range(n)]

    def drain(self):
        while self.game.stack or self.game.pending:
            self.game.flush_triggers()
            if self.game.stack:
                self.game.resolve_top()

    def down(self, name, kind="morph", player=None):
        return facedown.enter(self.game, player or self.a, self.db.get(name), kind)

    def cast_down(self, name, kind="morph"):
        card = self.db.get(name)
        self.a.hand.append(card)
        variant = next(c for c in self.game.spell_options(self.a) if self.game._origin(c)[1] == kind)
        self.assertTrue(self.game.can_cast_now(self.a, variant))
        self.assertTrue(self.game.cast(self.a, variant))
        self.game.resolve_top()
        return next(x for x in self.a.battlefield if x.hidden is card)

    def test_real_templates(self):
        for name in ("Canyon Lurkers", "Ainok Survivalist", "Stratus Dancer", "Fathom Seer",
                     "Zombie Cutthroat", "Soul Summons", "Ethereal Ambush", "Fierce Invocation",
                     "Formless Nurturing", "Hide in Plain Sight", "Hauntwoods Shrieker",
                     "Mastery of the Unseen", "Zoetic Cavern", "They Came from the Pipes"):
            with self.subTest(name=name):
                self.assertEqual(card_coverage(self.db.get(name)).status, FULL)

    def test_morph_is_nameless_colorless_textless_spell_and_permanent(self):
        self.lands("Forest", 3)
        card = self.db.get("Canyon Lurkers")
        self.a.hand = [card]
        spell = next(c for c in self.game.spell_options(self.a) if self.game._origin(c)[1] == "morph")
        self.assertEqual((spell.name, spell.mana_cost, spell.cmc), ("", {}, 0))
        self.assertEqual(spell.subtypes, frozenset())
        self.assertFalse(spell.triggers or spell.keywords or spell.produces)
        self.assertEqual(self.game.cost_of(self.a, spell), {"generic": 3})
        self.assertTrue(self.game.cast(self.a, spell))
        self.assertNotIn(card.name, str(self.game.stack[-1]))
        self.game.resolve_top()
        perm = self.a.creatures[0]
        self.assertEqual((perm.power, perm.toughness, perm.card.name, perm.ward), (2, 2, "", 0))
        self.assertFalse(perm.card.is_token)
        self.assertIs(facedown.visible_card(perm, self.a), card)
        self.assertIs(facedown.visible_card(perm, self.b), perm.card)
        self.assertNotIn(card.name, repr(perm))

    def test_disguise_suppresses_printed_etb_and_keywords(self):
        self.lands("Forest", 3)
        perm = self.cast_down("Granite Witness", "disguise")
        self.assertEqual((perm.power, perm.toughness, perm.ward), (2, 2, 2))
        self.assertFalse(perm.has("flying") or perm.has("vigilance"))
        self.assertEqual(self.game.pending, [])

    def test_disguise_ignores_printed_enters_tapped(self):
        self.lands("Forest", 3)
        perm = self.cast_down("Alley Assailant", "disguise")
        self.assertFalse(perm.tapped)
        self.assertEqual((self.a.life, self.b.life), (20, 20))

    def test_disguise_hybrid_cost_can_use_both_colors(self):
        perm = self.down("Granite Witness", "disguise")
        self.lands("Plains", 1)
        self.lands("Island", 1)
        self.assertTrue(self.game.turn_face_up(self.a, perm))
        self.assertTrue(perm.has("flying") and perm.has("vigilance"))

    def test_face_up_another_target_does_not_choose_itself(self):
        perm = self.down("Guardian Shield-Bearer", "megamorph")
        self.lands("Forest", 4)
        self.assertTrue(self.game.turn_face_up(self.a, perm))
        self.drain()
        self.assertEqual(perm.p1, 1)

    def test_morph_can_be_offered_even_when_normal_cast_is_affordable(self):
        self.lands("Forest", 6)
        self.a.hand = [self.db.get("Woolly Loxodon")]
        self.assertTrue(any(self.game._origin(c)[1] == "morph" for c in self.game.spell_options(self.a)))

    def test_countered_morph_reveals_and_puts_underlying_card_in_graveyard(self):
        self.lands("Forest", 3)
        card = self.db.get("Woolly Loxodon")
        self.a.hand = [card]
        variant = next(c for c in self.game.spell_options(self.a) if self.game._origin(c)[1] == "morph")
        self.assertTrue(self.game.cast(self.a, variant))
        spell = self.game.stack[-1]
        self.game.counter(self.b, Effect("counter", target="spell"), spell)
        self.assertIn(card, self.a.graveyard)
        self.assertNotIn(spell, self.game.stack)
        self.assertTrue(any("reveals Woolly Loxodon" in e for e in self.game.events))

    def test_morph_uses_global_creature_cost_discount_and_not_printed_color(self):
        source = card_from_scryfall({"name": "Discount", "type_line": "Enchantment", "mana_cost": "{G}",
                                    "oracle_text": "Creature spells you cast cost {1} less to cast."})
        self.game.enter_battlefield(self.a, source)
        card = self.db.get("Woolly Loxodon")
        variant = self.game._variant(card, "morph")
        self.assertEqual(self.game.cost_of(self.a, variant), {"generic": 2})

    def test_controller_change_preserves_owner_and_lets_new_controller_turn_up(self):
        perm = self.down("Canyon Lurkers")
        self.a.battlefield.remove(perm)
        perm.controller = self.b
        self.b.battlefield.append(perm)
        for _ in range(4):
            self.game.enter_battlefield(self.b, self.db.get("Mountain"))
        self.assertFalse(self.game.turn_face_up(self.a, perm))
        self.assertTrue(self.game.turn_face_up(self.b, perm))
        self.game.leave_battlefield(perm, "hand")
        self.assertIn(perm.front, self.a.hand)
        self.assertNotIn(perm.front, self.b.hand)

    def test_noncreature_morph_land_can_be_cast_and_turned_up(self):
        self.lands("Forest", 3)
        perm = self.cast_down("Zoetic Cavern")
        for land in self.a.battlefield:
            land.tapped = False
        self.assertTrue(self.game.turn_face_up(self.a, perm))
        self.assertTrue(perm.card.is_land)
        self.assertFalse(perm.is_creature)
        self.assertEqual(self.a.lands_played, 0)

    def test_disguise_land_cast_option(self):
        self.lands("Forest", 3)
        perm = self.cast_down("Branch of Vitu-Ghazi", "disguise")
        self.assertEqual((perm.power, perm.ward), (2, 2))

    def test_failed_payment_and_wrong_controller_do_nothing(self):
        perm = self.down("Canyon Lurkers")
        self.lands("Forest", 4)
        self.assertFalse(self.game.turn_face_up(self.a, perm))
        self.assertFalse(any(x.tapped for x in self.a.battlefield))
        self.assertFalse(self.game.turn_face_up(self.b, perm))
        self.assertIsNotNone(perm.hidden)

    def test_turn_up_preserves_object_combat_attachments_and_damage(self):
        perm = self.down("Woolly Loxodon")
        perm.tapped, perm.sick, perm.damage = True, False, 1
        perm.counters["+1/+1"] = 2
        self.game.attackers = [perm]
        self.game.attack_targets = {perm: self.b}
        equipment = self.game.enter_battlefield(self.a, self.db.get("Bonesplitter"))
        equipment.attached_to = perm
        self.lands("Forest", 6)
        self.assertTrue(self.game.turn_face_up(self.a, perm))
        self.assertIs(equipment.attached_to, perm)
        self.assertIn(perm, self.game.attackers)
        self.assertEqual((perm.tapped, perm.sick, perm.damage, perm.p1), (True, False, 1, 2))
        self.assertEqual((perm.power, perm.toughness), (10, 9))
        self.assertEqual(self.game.pending, [])

    def test_face_up_special_action_does_not_use_stack(self):
        perm = self.down("Canyon Lurkers")
        self.lands("Mountain", 4)
        spell = StackItem(self.b, [Effect("damage", 2, target="creature")], [perm], name="hit", kind="ability")
        self.game.stack.append(spell)
        self.assertTrue(self.game.do_action(self.a, ("turn_face_up", perm)))
        self.assertEqual(self.game.stack, [spell])
        self.assertEqual(perm.power, 5)

    def test_megamorph_counter_precedes_face_up_trigger(self):
        perm = self.down("Ainok Survivalist", "megamorph")
        artifact = self.game.enter_battlefield(self.b, self.db.get("Sol Ring"))
        self.lands("Forest", 2)
        self.assertTrue(self.game.turn_face_up(self.a, perm))
        self.assertEqual((perm.power, perm.toughness, perm.p1), (3, 2, 1))
        self.assertIn(artifact, self.b.battlefield)
        self.assertEqual(self.game.pending[0][1][0].kind, "destroy")
        self.drain()
        self.assertIn(artifact.front, self.b.graveyard)

    def test_face_up_counterspell_trigger_targets_existing_spell(self):
        perm = self.down("Stratus Dancer", "megamorph")
        self.lands("Island", 2)
        spell = StackItem(self.b, [Effect("draw", 1)], [None], card=self.db.get("Opt"))
        self.game.stack.append(spell)
        self.assertTrue(self.game.turn_face_up(self.a, perm))
        self.game.flush_triggers()
        self.assertEqual(self.game.stack[-1].targets, [spell])
        self.game.resolve_top()
        self.assertNotIn(spell, self.game.stack)
        self.assertIn(spell.card, self.b.graveyard)

    def test_priority_policy_turns_up_on_opponents_turn(self):
        perm = self.down("Woolly Loxodon")
        self.lands("Forest", 6)
        self.game.active_idx = 1
        self.game.step = "declare_blockers"
        self.assertTrue(self.game.give_priority(self.a))
        self.assertIsNone(perm.hidden)
        self.assertEqual(self.game.stack, [])

    def test_reveal_on_leaving_uses_true_card_and_not_printed_death_trigger(self):
        for zone in ("hand", "graveyard", "exile"):
            with self.subTest(zone=zone):
                perm = self.down("Hooded Hydra")
                self.game.leave_battlefield(perm, zone)
                self.assertIn(perm.front, getattr(self.a, zone))
                self.assertTrue(any("reveals Hooded Hydra" in e for e in self.game.events))
                self.assertEqual(self.game.pending, [])

    def test_manifest_dread_creature_has_mana_cost_turn_up(self):
        self.a.library = [self.db.get("Woolly Loxodon"), self.db.get("Grizzly Bears")]
        self.game.resolve(self.a, self.db.get("Manifest Dread").spell_effects[0], None)
        perm = self.a.creatures[0]
        self.assertIs(perm.hidden, self.db.get("Grizzly Bears"))
        self.assertIn(self.db.get("Woolly Loxodon"), self.a.graveyard)
        self.lands("Forest", 2)
        self.assertTrue(self.game.turn_face_up(self.a, perm, "mana_cost"))
        self.assertEqual(perm.card.name, "Grizzly Bears")

    def test_manifest_dread_one_card_and_empty_library_do_not_deck_player(self):
        self.a.library = [self.db.get("Forest")]
        eff = self.db.get("Manifest Dread").spell_effects[0]
        self.game.resolve(self.a, eff, None)
        self.game.resolve(self.a, eff, None)
        self.assertEqual(len(self.a.creatures), 1)
        self.assertFalse(self.a.lost)
        self.assertEqual(self.a.graveyard, [])

    def test_manifest_noncreature_cannot_pay_mana_cost_to_turn_up(self):
        for name in ("Forest", "Lightning Bolt", "Sol Ring"):
            with self.subTest(name=name):
                perm = self.down(name, "manifest")
                self.lands("Forest", 5)
                self.assertFalse(self.game.turn_face_up(self.a, perm, "mana_cost"))
                self.assertIsNotNone(perm.hidden)

    def test_countered_spell_controller_manifests_dread(self):
        spell = StackItem(self.b, [], [], card=self.db.get("Grizzly Bears"))
        self.game.stack.append(spell)
        self.game.enter_battlefield(self.a, self.db.get("Fear of Impostors"))
        self.drain()
        self.assertNotIn(spell, self.game.stack)
        self.assertEqual(len(self.b.creatures), 1)
        self.assertIsNotNone(self.b.creatures[0].hidden)
        self.assertEqual(self.a.creatures[0].card.name, "Fear of Impostors")

    def test_destroyed_creature_controller_manifests_dread(self):
        bear = self.game.enter_battlefield(self.b, self.db.get("Grizzly Bears"))
        card = self.db.get("Unwanted Remake")
        self.game.stack.append(StackItem(self.a, card.spell_effects, [bear, None], card=card))
        self.drain()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertEqual(len(self.b.creatures), 1)
        self.assertIsNotNone(self.b.creatures[0].hidden)

    def test_manifested_megamorph_has_independent_cost_options(self):
        first = self.down("Ainok Survivalist", "manifest")
        second = self.down("Ainok Survivalist", "manifest")
        self.lands("Forest", 4)
        self.assertTrue(self.game.turn_face_up(self.a, first, "mana_cost"))
        self.assertEqual(first.p1, 0)
        self.assertTrue(self.game.turn_face_up(self.a, second, "megamorph"))
        self.assertEqual(second.p1, 1)

    def test_morph_cast_does_not_grant_manifest_mana_cost_option(self):
        perm = self.down("Canyon Lurkers")
        self.lands("Mountain", 5)
        self.assertFalse(self.game.turn_face_up(self.a, perm, "mana_cost"))

    def test_no_mana_cost_creature_cannot_be_turned_up_for_free(self):
        perm = self.down("Ancestral Vision", "manifest")
        perm.hidden = card_from_scryfall({"name": "No Cost", "type_line": "Creature", "power": "3", "toughness": "3"})
        self.assertFalse(self.game.turn_face_up(self.a, perm))
        zero = self.down("Ornithopter", "manifest")
        self.assertTrue(self.game.turn_face_up(self.a, zero))

    def test_cloak_ward_and_mana_cost_turn_up(self):
        perm = self.down("Grizzly Bears", "cloak")
        self.assertEqual(perm.ward, 2)
        self.lands("Forest", 2)
        self.assertTrue(self.game.turn_face_up(self.a, perm, "mana_cost"))
        self.assertEqual(perm.ward, 0)

    def test_cloak_ward_triggers_on_opposing_spell(self):
        perm = self.down("Grizzly Bears", "cloak")
        spell = StackItem(self.b, [Effect("damage", 3, target="any")], [perm], card=self.db.get("Lightning Bolt"))
        self.game.stack.append(spell)
        self.game.check_ward(spell)
        self.drain()
        self.assertIn(perm, self.a.battlefield)
        self.assertIn(spell.card, self.b.graveyard)

    def test_manifest_twice_and_counter_rider(self):
        self.a.library = [self.db.get("Forest")] * 5
        eff = self.db.get("Ethereal Ambush").spell_effects[0]
        self.game.resolve(self.a, eff, None)
        self.assertEqual(len(self.a.creatures), 2)
        self.game.resolve(self.a, self.db.get("Fierce Invocation").spell_effects[0], None)
        self.assertEqual(self.a.creatures[-1].p1, 2)

    def test_hide_in_plain_sight_keeps_two_cloaked_and_bottoms_rest(self):
        self.a.library = [self.db.get("Forest")] * 7
        self.game.resolve(self.a, self.db.get("Hide in Plain Sight").spell_effects[0], None)
        self.assertEqual(len(self.a.creatures), 2)
        self.assertEqual(len(self.a.library), 5)
        self.assertTrue(all(x.ward == 2 for x in self.a.creatures))

    def test_cryptic_coat_attaches_to_exact_cloaked_object(self):
        self.a.library = [self.db.get("Forest")]
        coat = self.game.enter_battlefield(self.a, self.db.get("Cryptic Coat"))
        self.drain()
        self.assertIs(coat.attached_to, self.a.creatures[0])
        self.assertEqual(coat.attached_to.ward, 2)

    def test_policy_can_play_manifest_and_cloak_spells(self):
        for name in ("Soul Summons", "Manifest Dread", "Hide in Plain Sight"):
            with self.subTest(name=name):
                plan = self.a.ai.plan_spell(self.game, self.a, self.db.get(name), precombat=True)
                self.assertIsNotNone(plan)
                self.assertGreater(plan[0], 0)

    def test_face_up_observer_triggers_but_not_etb(self):
        self.game.enter_battlefield(self.a, self.db.get("Mastery of the Unseen"))
        perm = self.down("Canyon Lurkers")
        self.lands("Mountain", 4)
        self.assertTrue(self.game.turn_face_up(self.a, perm))
        self.drain()
        self.assertEqual(self.a.life, 21)

    def test_secret_plans_only_boosts_face_down_bodies_and_draws_on_turnup(self):
        self.game.enter_battlefield(self.a, self.db.get("Secret Plans"))
        bear = self.game.enter_battlefield(self.a, self.db.get("Grizzly Bears"))
        perm = self.down("Canyon Lurkers")
        self.assertEqual((bear.toughness, perm.toughness), (2, 3))
        self.lands("Mountain", 4)
        self.assertTrue(self.game.turn_face_up(self.a, perm))
        self.drain()
        self.assertEqual(perm.toughness, 2)
        self.assertEqual(len(self.a.hand), 1)

    def test_bookworm_draw_discard_unless_face_down_event_this_turn(self):
        source = self.game.enter_battlefield(self.a, self.db.get("Oblivious Bookworm"))
        self.game.fire(self.a, "end_step", source)
        self.drain()
        self.assertEqual(len(self.a.hand), 0)
        self.down("Woolly Loxodon", "manifest")
        self.game.fire(self.a, "end_step", source)
        self.drain()
        self.assertEqual(len(self.a.hand), 1)
        self.game.turn += 1
        self.game.fire(self.a, "end_step", source)
        self.drain()
        self.assertEqual(len(self.a.hand), 1)

    def test_bookworm_face_up_event_counts_for_controller_only(self):
        source = self.game.enter_battlefield(self.a, self.db.get("Oblivious Bookworm"))
        perm = self.down("Canyon Lurkers")
        self.game.turn += 1
        self.lands("Mountain", 4)
        self.assertTrue(self.game.turn_face_up(self.a, perm))
        self.game.fire(self.a, "end_step", source)
        self.drain()
        self.assertEqual(len(self.a.hand), 1)
        self.assertEqual(getattr(self.b, "face_up_turn", -1), -1)

    def test_nonmana_life_cost(self):
        perm = self.down("Zombie Cutthroat")
        self.assertTrue(self.game.turn_face_up(self.a, perm))
        self.assertEqual(self.a.life, 15)
        self.assertEqual(perm.power, 3)

    def test_nonmana_return_cost_and_trigger(self):
        perm = self.down("Fathom Seer")
        lands = self.lands("Island", 2)
        self.assertTrue(self.game.turn_face_up(self.a, perm))
        self.assertTrue(all(x not in self.a.battlefield for x in lands))
        self.assertEqual(len(self.a.hand), 2)
        self.drain()
        self.assertEqual(len(self.a.hand), 4)

    def test_nonmana_discard_is_validated_before_revealing(self):
        perm = self.down("Gathan Raiders")
        self.assertFalse(self.game.turn_face_up(self.a, perm))
        forest = self.db.get("Forest")
        self.a.hand = [forest]
        self.assertTrue(self.game.turn_face_up(self.a, perm))
        self.assertIn(forest, self.a.graveyard)

    def test_reveal_cost_checks_card_colors_and_reveals_only_payment(self):
        perm = self.down("Temur Charger")
        forest = self.db.get("Forest")
        self.a.hand = [forest]
        self.assertFalse(self.game.turn_face_up(self.a, perm))
        self.a.hand.append(self.db.get("Dryad Arbor"))
        self.assertTrue(self.game.turn_face_up(self.a, perm))
        self.assertTrue(any("reveals Dryad Arbor for morph" in e for e in self.game.events))
        self.assertEqual(len(self.a.hand), 2)

    def test_nonmana_morph_has_minimal_priority_policy(self):
        perm = self.down("Zombie Cutthroat")
        self.assertTrue(self.game.give_priority(self.a))
        self.assertIsNone(perm.hidden)
        self.assertEqual(self.a.life, 15)

    def test_subtype_payments_accept_changeling(self):
        raptor = self.down("Putrid Raptor")
        automaton = self.db.get("Universal Automaton")
        self.a.hand = [automaton]
        self.assertTrue(self.game.turn_face_up(self.a, raptor))
        self.assertIn(automaton, self.a.graveyard)
        initiate = self.down("Raven Guild Initiate")
        bird = self.game.enter_battlefield(self.a, automaton)
        self.assertTrue(self.game.turn_face_up(self.a, initiate))
        self.assertNotIn(bird, self.a.battlefield)
        self.assertIn(automaton, self.a.hand)

    def test_hauntwoods_reveal_turnup_is_an_activated_stack_ability(self):
        source = self.game.enter_battlefield(self.a, self.db.get("Hauntwoods Shrieker"))
        perm = self.down("Woolly Loxodon", "manifest")
        self.lands("Forest", 2)
        self.assertTrue(self.game.activate(self.a, source, "ability:0", [perm]))
        self.assertIsNotNone(perm.hidden)
        self.drain()
        self.assertIsNone(perm.hidden)
        self.assertEqual(perm.power, 6)

    def test_manifest_dread_twice_creates_two_and_mills_two(self):
        self.game.enter_battlefield(self.a, self.db.get("They Came from the Pipes"))
        self.drain()
        self.assertEqual(len(self.a.creatures), 2)
        self.assertEqual(len(self.a.graveyard), 2)
        self.assertTrue(all(not x.card.is_token for x in self.a.creatures))
        self.assertEqual(len(self.a.hand), 2)
        self.game.enter_battlefield(self.a, self.db.get("Grizzly Bears"))
        self.drain()
        self.assertEqual(len(self.a.hand), 2)

    def test_modified_death_manifest_uses_characteristics_before_detachment(self):
        self.game.enter_battlefield(self.a, self.db.get("Guardian of the Forgotten"))
        bear = self.game.enter_battlefield(self.a, self.db.get("Grizzly Bears"))
        self.game.dies(bear)
        self.drain()
        self.assertEqual(len(self.a.creatures), 1)
        bear = self.game.enter_battlefield(self.a, self.db.get("Grizzly Bears"))
        equipment = self.game.enter_battlefield(self.a, self.db.get("Bonesplitter"))
        equipment.attached_to = bear
        self.game.dies(bear)
        self.drain()
        self.assertEqual(len(self.a.creatures), 2)
        self.assertEqual(self.a.creatures[-1].face_down_kind, "manifest")
        self.assertIsNone(equipment.attached_to)

    def test_unknown_costs_and_unimplemented_riders_remain_visible(self):
        self.assertTrue(self.db.get("Willbender").unsupported)
        self.assertTrue(self.db.get("Bane of the Living").unsupported)
        self.assertTrue(self.db.get("Cryptic Coat").unsupported)


if __name__ == "__main__":
    unittest.main()
