"""O4 round four: deck spells, optional targets, cast provenance and ETB riders."""
import dataclasses
from unittest.mock import patch

from mtgsim.carddb import CardDB
from mtgsim.cards import Effect, _parse_effects
from mtgsim.engine import StackItem
from tests.test_templates import Base, BEAR, DRAGON3, ISLAND, MOUNTAIN, SHOCK, card

DB = CardDB()
MIND_ROT = DB.get("Mind Rot")
BOUNCE = DB.get("Bounce Off")
PLUNDER = DB.get("Plunder the Trollshaws")
DISSECTION = DB.get("Dissection Practice")
LORAN = DB.get("Loran of the Third Path")
INVOKE = DB.get("Invoke Despair")
BAT = DB.get("Deep-Cavern Bat")
TERSA = DB.get("Tersa Lightshatter")
VILLAGE = DB.get("Rockface Village")


class SpellRiders(Base):
    def spell(self, c, targets, p=None):
        item = StackItem(p or self.a, c.spell_effects, targets, card=c)
        self.game.stack.append(item)
        self.game.resolve_top()
        return item

    def test_all_nine_templates(self):
        for c in (MIND_ROT, BOUNCE, PLUNDER, DISSECTION, LORAN, INVOKE, BAT, TERSA, VILLAGE):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])

    def test_unknown_shapes_remain_unsupported(self):
        for text in ("Target player discards half their hand.",
                     "Up to one target creature gets +2/-1 until end of turn.",
                     "Return target creature or Battle to its owner's hand.",
                     "Look at target opponent's hand. You may exile a land card from it until ~ leaves the battlefield.",
                     "Target opponent sacrifices a creature. If they can't, they lose 2 life and you draw a card. "
                     "Then repeat this process for each artifact."):
            self.assertTrue(_parse_effects(text)[1], text)

    def test_mind_rot_opponent_discards_two_or_remaining_one(self):
        for cards in ([BEAR, SHOCK, ISLAND], [BEAR], []):
            with self.subTest(cards=cards):
                self.b.hand = cards
                before = len(self.b.graveyard)
                self.spell(MIND_ROT, [self.b])
                self.assertEqual(len(self.b.hand), max(0, len(cards) - 2))
                self.assertEqual(len(self.b.graveyard) - before, min(2, len(cards)))

    def test_mind_rot_can_target_self(self):
        self.a.hand = [BEAR, SHOCK]
        self.b.hand = [ISLAND]
        self.spell(MIND_ROT, [self.a])
        self.assertFalse(self.a.hand)
        self.assertEqual(self.b.hand, [ISLAND])

    def test_bounce_creature_and_uncrewed_vehicle(self):
        for c in (BEAR, card("Cart", types="Artifact — Vehicle")):
            target = self.perm(c, self.b)
            self.assertTrue(self.game.legal_target(self.a, BOUNCE.spell_effects[0], target))
            self.spell(BOUNCE, [target])
            self.assertIn(c, self.b.hand)
            self.assertNotIn(target, self.b.battlefield)
        artifact = self.perm(card("Relic", types="Artifact"), self.b)
        self.assertFalse(self.game.legal_target(self.a, BOUNCE.spell_effects[0], artifact))

    def test_bounce_allows_animated_land_and_respects_hexproof(self):
        land_creature = self.perm(dataclasses.replace(BEAR, types=frozenset({"Land", "Creature"})), self.b)
        self.assertTrue(self.game.legal_target(self.a, BOUNCE.spell_effects[0], land_creature))
        land_creature.temp_kw.add("hexproof")
        self.assertFalse(self.game.legal_target(self.a, BOUNCE.spell_effects[0], land_creature))

    def test_plunder_cast_from_hand_draws_one(self):
        self.a.hand = [PLUNDER]
        self.perm(ISLAND, self.a)
        self.perm(ISLAND, self.a)
        before = len(self.a.library)
        self.assertTrue(self.game.cast(self.a, self.a.hand[0]))
        self.game.settle()
        self.assertEqual(len(self.a.library), before - 1)
        self.assertEqual(len(self.a.hand), 1)
        self.assertIn(PLUNDER, self.a.graveyard)

    def test_plunder_flashback_draws_two_and_exiles(self):
        self.a.graveyard = [PLUNDER]
        for _ in range(4):
            self.perm(ISLAND, self.a)
        before = len(self.a.library)
        variant = next(c for c in self.game.spell_options(self.a) if self.game._origin(c)[0].name == PLUNDER.name)
        self.assertTrue(self.game.cast(self.a, variant))
        self.game.settle()
        self.assertEqual(len(self.a.library), before - 2)
        self.assertEqual(len(self.a.hand), 2)
        self.assertIn(PLUNDER, self.a.exile)
        self.assertNotIn(PLUNDER, self.a.graveyard)

    def test_plunder_copy_was_not_cast_from_graveyard(self):
        item = StackItem(self.a, PLUNDER.spell_effects, [None, None], card=PLUNDER, kind="copy")
        item.cast_from_graveyard = True  # Even a copied flag cannot make the copy a cast spell.
        self.game.stack.append(item)
        self.game.resolve_top()
        self.assertEqual(len(self.a.hand), 1)

    def test_dissection_chooses_zero_targets_and_still_drains(self):
        item = self.spell(DISSECTION, [self.b, None, None, None])
        self.assertTrue(item.resolved)
        self.assertEqual((self.a.life, self.b.life), (21, 19))

    def test_optional_zero_targets_preserved_when_cast(self):
        self.a.hand = [DISSECTION]
        for _ in range(2):
            self.perm(DB.get("Swamp"), self.a)
        self.perm(BEAR, self.a)
        self.perm(BEAR, self.b)
        self.assertTrue(self.game.cast(self.a, self.a.hand[0], [self.b, None, None, None]))
        self.game.settle()
        self.assertEqual((self.a.life, self.b.life), (21, 19))
        self.assertEqual(self.a.creatures[0].power, 2)
        self.assertEqual(self.b.creatures[0].toughness, 2)

    def test_dissection_can_target_same_creature_and_opposing_creature(self):
        ally = self.perm(BEAR, self.a)
        enemy = self.perm(BEAR, self.b)
        self.spell(DISSECTION, [self.b, None, ally, enemy])
        self.assertEqual((ally.power, ally.toughness), (3, 3))
        self.assertEqual((enemy.power, enemy.toughness), (1, 1))
        other = self.perm(DRAGON3, self.b)
        self.spell(DISSECTION, [self.b, None, other, other])
        self.assertEqual((other.power, other.toughness), (3, 3))

    def test_dissection_other_targets_resolve_when_creature_is_gone(self):
        victim = self.perm(BEAR, self.b)
        self.game.stack.append(StackItem(self.a, DISSECTION.spell_effects, [self.b, None, None, victim], card=DISSECTION))
        self.game.leave_battlefield(victim, "hand")
        self.game.resolve_top()
        self.assertEqual((self.a.life, self.b.life), (21, 19))

    def test_optional_single_target_fizzles_if_chosen_target_is_gone(self):
        effects, bad = _parse_effects("Up to one target creature gets +1/+1 until end of turn.")
        self.assertFalse(bad)
        victim = self.perm(BEAR, self.a)
        item = StackItem(self.a, effects, [victim])
        self.game.stack.append(item)
        self.game.leave_battlefield(victim, "hand")
        self.game.resolve_top()
        self.assertFalse(item.resolved)
        zero = StackItem(self.a, effects, [None])
        self.game.stack.append(zero)
        self.game.resolve_top()
        self.assertTrue(zero.resolved)

    def test_loran_short_name_enters_destroys_artifact(self):
        artifact = self.perm(card("Relic", types="Artifact"), self.b)
        self.game.enter_battlefield(self.a, LORAN)
        self.game.settle()
        self.assertNotIn(artifact, self.b.battlefield)

    def test_loran_may_choose_no_target_and_draws_for_both(self):
        loran = self.perm(LORAN, self.a)
        effects = LORAN.triggers[0].effects
        self.game.queue_trigger(self.a, effects, loran, targets=[None])
        self.game.settle()
        before = len(self.a.hand), len(self.b.hand)
        self.assertTrue(self.game.activate_ability(self.a, loran, 0, [self.b]))
        self.game.settle()
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (before[0]+1, before[1]+1))

    def test_loran_draw_rejects_self_target(self):
        loran = self.perm(LORAN, self.a)
        self.assertFalse(self.game.activate_ability(self.a, loran, 0, [self.a]))
        self.assertFalse(loran.tapped)

    def test_invoke_empty_board_loses_six_draws_three(self):
        self.spell(INVOKE, [self.b])
        self.assertEqual(self.b.life, 14)
        self.assertEqual(len(self.a.hand), 3)

    def test_invoke_missing_enchantment_loses_two_draws_one(self):
        creature = self.perm(BEAR, self.b)
        walker = self.perm(dataclasses.replace(card("Walker", types="Planeswalker"), loyalty=3), self.b)
        walker.counters["loyalty"] = 3
        self.spell(INVOKE, [self.b])
        self.assertNotIn(creature, self.b.battlefield)
        self.assertNotIn(walker, self.b.battlefield)
        self.assertEqual(self.b.life, 18)
        self.assertEqual(len(self.a.hand), 1)

    def test_invoke_overlapping_types_consumed_in_order_and_victim_chooses(self):
        both = self.perm(dataclasses.replace(BEAR, types=frozenset({"Creature", "Enchantment"})), self.b)
        spare = self.perm(DRAGON3, self.b)
        self.b.ai.choose_sacrifice = lambda game, player, candidates: both
        self.spell(INVOKE, [self.b])
        self.assertNotIn(both, self.b.battlefield)
        self.assertIn(spare, self.b.battlefield)
        self.assertEqual(self.b.life, 16)
        self.assertEqual(len(self.a.hand), 2)

    def test_bat_exiles_nonland_then_dies_returns_same_physical_card_to_hand(self):
        self.b.hand = [ISLAND, SHOCK]
        physical = self.b.hand[1]
        bat = self.game.enter_battlefield(self.a, BAT)
        self.game.settle()
        self.assertIs(self.b.exile[0], physical)
        self.assertEqual(self.b.hand, [ISLAND])
        self.game.destroy(bat)
        self.game.settle()
        self.assertIs(self.b.hand[-1], physical)
        self.assertFalse(self.b.exile)
        self.assertNotIn(SHOCK, [x.card for x in self.b.battlefield])

    def test_bat_leaves_before_etb_does_not_exile(self):
        self.b.hand = [SHOCK]
        bat = self.game.enter_battlefield(self.a, BAT)
        self.game.leave_battlefield(bat, "hand")
        self.game.settle()
        self.assertEqual(self.b.hand, [SHOCK])
        self.assertFalse(self.b.exile)

    def test_bat_ignores_lands_and_may_decline(self):
        self.b.hand = [ISLAND]
        self.game.enter_battlefield(self.a, BAT)
        self.game.settle()
        self.assertEqual(self.b.hand, [ISLAND])
        self.b.hand = [SHOCK]
        original = self.game.hook
        with patch.object(self.game, "hook", side_effect=lambda p, name:
                          (lambda *args: None) if name == "choose_discard_from" else original(p, name)):
            self.game.enter_battlefield(self.a, BAT)
            self.game.settle()
        self.assertEqual(self.b.hand, [SHOCK])

    def test_bat_stale_exile_reference_does_not_return_reentered_card(self):
        self.b.hand = [SHOCK]
        bat = self.game.enter_battlefield(self.a, BAT)
        self.game.settle()
        physical = self.b.exile[0]
        self.game.move_card(physical, self.b.exile, self.b.graveyard)
        self.game.move_card(physical, self.b.graveyard, self.b.exile)
        self.game.leave_battlefield(bat, "hand")
        self.assertIn(physical, self.b.exile)
        self.assertFalse(self.b.hand)

    def test_bat_duplicate_names_do_not_substitute_for_exiled_card(self):
        self.b.hand = [SHOCK, SHOCK]
        bat = self.game.enter_battlefield(self.a, BAT)
        self.game.settle()
        exiled = self.b.exile[0]
        other = self.b.hand[0]
        self.game.move_card(exiled, self.b.exile, self.b.graveyard)
        self.game.move_card(other, self.b.hand, self.b.exile)
        self.game.leave_battlefield(bat, "hand")
        self.assertIn(other, self.b.exile)
        self.assertFalse(self.b.hand)

    def test_tersa_random_gy_card_play_permission_and_expiry(self):
        tersa = self.perm(TERSA, self.a)
        self.a.graveyard = [SHOCK] + [BEAR]*6
        physical = self.a.graveyard[0]
        with patch.object(self.game.rng, "choice", side_effect=lambda cards: cards[0]) as choice:
            self.game.fire(self.a, "attacks", tersa)
            self.game.settle()
        choice.assert_called_once()
        self.assertIn(physical, self.a.exile)
        self.assertIn(physical, self.game.impulse_cards(self.a))
        self.game.turn += 1
        self.assertNotIn(physical, self.game.impulse_cards(self.a))

    def test_tersa_seven_card_condition_on_trigger_and_resolution(self):
        tersa = self.perm(TERSA, self.a)
        self.a.graveyard = [BEAR]*6
        self.game.fire(self.a, "attacks", tersa)
        self.assertFalse(self.game.pending)
        self.a.graveyard.append(BEAR)
        self.game.fire(self.a, "attacks", tersa)
        self.game.flush_triggers()
        self.a.graveyard.pop()
        self.game.resolve_top()
        self.assertFalse(self.a.exile)
        self.assertFalse(self.a.impulse)

    def test_tersa_can_play_exiled_land_and_cast_exiled_spell_normally(self):
        tersa = self.perm(TERSA, self.a)
        self.a.graveyard = [ISLAND] + [BEAR]*6
        with patch.object(self.game.rng, "choice", side_effect=lambda cards: cards[0]):
            self.game.fire(self.a, "attacks", tersa)
            self.game.settle()
        physical = self.a.exile[0]
        self.game.play_land(self.a, physical)
        self.assertIs(self.a.battlefield[-1].front, physical)
        self.a.graveyard = [SHOCK] + [BEAR]*6
        self.perm(MOUNTAIN, self.a)
        with patch.object(self.game.rng, "choice", side_effect=lambda cards: cards[0]):
            self.game.fire(self.a, "attacks", tersa)
            self.game.settle()
        option = next(c for c in self.game.spell_options(self.a) if self.game._origin(c)[0].name == "Shock")
        self.assertTrue(self.game.cast(self.a, option, [self.b]))
        self.game.settle()
        self.assertEqual(self.b.life, 18)

    def test_rockface_subtypes_control_sorcery_and_mana(self):
        village = self.perm(VILLAGE, self.a)
        self.perm(MOUNTAIN, self.a)
        for subtype in ("Lizard", "Mouse", "Otter", "Raccoon"):
            ally = self.perm(card(subtype, types="Creature — " + subtype, power=1, toughness=1), self.a)
            self.assertTrue(self.game.legal_target(self.a, VILLAGE.activated[0].effects[0], ally))
        target = self.a.creatures[0]
        bear = self.perm(BEAR, self.a)
        enemy = self.perm(target.card, self.b)
        eff = VILLAGE.activated[0].effects[0]
        self.assertFalse(self.game.legal_target(self.a, eff, bear))
        self.assertFalse(self.game.legal_target(self.a, eff, enemy))
        self.game.step = "combat_damage"
        self.assertFalse(self.game.activate_ability(self.a, village, 0, [target]))
        self.game.step = "main1"
        self.assertTrue(self.game.activate_ability(self.a, village, 0, [target]))
        self.game.settle()
        self.assertEqual(target.power, 2)
        self.assertTrue(target.has("haste"))
        self.assertTrue(village.tapped)

    def test_rockface_changeling_and_unrelated_lizard_shaped_noncreature(self):
        eff = VILLAGE.activated[0].effects[0]
        shapeshifter = self.perm(dataclasses.replace(BEAR, changeling=True), self.a)
        relic = self.perm(card("Lizard Statue", types="Artifact — Lizard"), self.a)
        self.assertTrue(self.game.legal_target(self.a, eff, shapeshifter))
        self.assertFalse(self.game.legal_target(self.a, eff, relic))

    def test_plunder_other_graveyard_cast_permission_draws_two(self):
        from mtgsim.cards import AltCost
        definition = dataclasses.replace(PLUNDER, alt_costs=[AltCost("mayhem", {"U": 1}, zone="graveyard")])
        self.a.hand = [definition]
        self.game.discard_card(self.a, self.a.hand[0])
        self.perm(ISLAND, self.a)
        variant = next(c for c in self.game.spell_options(self.a) if self.game._origin(c)[1] == "mayhem")
        self.assertTrue(self.game.cast(self.a, variant))
        self.game.settle()
        self.assertEqual(len(self.a.hand), 2)
        self.assertIn(PLUNDER, self.a.graveyard)

    def test_plunder_countered_spell_does_not_draw(self):
        self.a.hand = [PLUNDER]
        self.perm(ISLAND, self.a)
        self.perm(ISLAND, self.a)
        self.game._priority_depth += 1
        try:
            self.assertTrue(self.game.cast(self.a, self.a.hand[0]))
            self.game.counter(self.b, Effect("counter", target="spell"), self.game.stack[-1])
        finally:
            self.game._priority_depth -= 1
        self.assertFalse(self.a.hand)
        self.assertIn(PLUNDER, self.a.graveyard)

    def test_optional_target_hook_can_choose_zero_with_legal_candidates(self):
        target = self.perm(BEAR, self.a)
        effect = DISSECTION.spell_effects[2]
        original = self.game.hook
        with patch.object(self.game, "hook", side_effect=lambda p, name:
                          (lambda *args: None) if name == "choose_target" else original(p, name)):
            self.assertEqual(self.game.auto_targets(self.a, [effect]), [None])
        self.assertTrue(self.game.legal_target(self.a, effect, target))

    def test_short_legendary_title_normalization_does_not_apply_to_nonlegendary(self):
        legend = card("Aldra of the Dawn", types="Legendary Creature", text="When Aldra enters, draw a card.",
                      power=2, toughness=2)
        other = card("Aldra of the Dawn", types="Creature", text="When Aldra enters, draw a card.", power=2, toughness=2)
        self.assertFalse(legend.unsupported)
        self.assertTrue(other.unsupported)
        self.game.enter_battlefield(self.a, legend)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_invoke_all_types_sacrificed_including_indestructible(self):
        creature = self.perm(dataclasses.replace(BEAR, keywords={"indestructible"}), self.b)
        enchantment = self.perm(card("Curse", types="Enchantment"), self.b)
        walker = self.perm(dataclasses.replace(card("Walker", types="Planeswalker"), loyalty=3), self.b)
        walker.counters["loyalty"] = 3
        self.spell(INVOKE, [self.b])
        self.assertFalse(self.b.battlefield)
        self.assertEqual(self.b.life, 20)
        self.assertFalse(self.a.hand)
        self.assertEqual(len(self.b.graveyard), 3)
        self.assertNotIn(creature, self.b.battlefield)
        self.assertNotIn(enchantment, self.b.battlefield)

    def test_invoke_opponent_target_constraint(self):
        effect = INVOKE.spell_effects[0]
        self.assertTrue(self.game.legal_target(self.a, effect, self.b))
        self.assertFalse(self.game.legal_target(self.a, effect, self.a))
        self.spell(INVOKE, [self.a])
        self.assertEqual(self.a.life, 20)
        self.assertFalse(self.a.hand)

    def test_bat_bounce_returns_card_before_replay(self):
        self.b.hand = [SHOCK]
        physical = self.b.hand[0]
        bat = self.game.enter_battlefield(self.a, BAT)
        self.game.settle()
        self.game.leave_battlefield(bat, "hand")
        self.assertIs(self.b.hand[0], physical)
        self.assertIn(BAT, self.a.hand)
        self.assertFalse(self.b.exile)

    def test_rockface_restricted_red_cannot_pay_for_ability(self):
        village = self.perm(VILLAGE, self.a)
        self.perm(VILLAGE, self.a)
        lizard = self.perm(card("Newt", types="Creature — Lizard", power=1, toughness=1), self.a)
        self.assertFalse(self.game.activate_ability(self.a, village, 0, [lizard]))
        self.assertFalse(village.tapped)

    def test_tersa_unknown_free_cast_rider_stays_unsupported(self):
        unknown = card("Random Raider", types="Creature", text="Whenever Random Raider attacks, if there are "
                       "seven or more cards in your graveyard, exile a card at random from your graveyard. "
                       "You may cast that card without paying its mana cost.", power=3, toughness=3)
        self.assertTrue(unknown.unsupported)

    def test_mind_rot_ai_plan_targets_opponent_and_casts(self):
        self.a.hand = [MIND_ROT]
        self.b.hand = [BEAR, SHOCK, ISLAND]
        for _ in range(3):
            self.perm(DB.get("Swamp"), self.a)
        plan = self.a.ai.plan_spell(self.game, self.a, self.a.hand[0])
        self.assertIsNotNone(plan)
        self.assertEqual(plan[0], 1.6)
        self.assertEqual(plan[1], [self.b])
        self.assertTrue(self.game.cast(self.a, self.a.hand[0], plan[1]))
        self.game.settle()
        self.assertEqual(len(self.b.hand), 1)
        self.assertEqual(len(self.a.hand), 0)

    def test_discard_ai_empty_opponent_and_self_discard_values(self):
        for hand, value in (([], 0), ([BEAR], 0.8)):
            self.b.hand = hand
            plan = self.a.ai.plan_spell(self.game, self.a, MIND_ROT)
            self.assertEqual(plan, (value, [self.b]))
        cost = card("Voluntary Loss", types="Sorcery", text="Discard two cards.")
        self.assertFalse(cost.unsupported)
        self.assertEqual(self.a.ai.plan_spell(self.game, self.a, cost), (-1.6, [None]))

    def test_newly_matched_consult_draw_mode_targets_the_chosen_player(self):
        definition = DB.get("Consult the Necrosages")
        self.assertFalse(definition.unsupported)
        effects = definition.modes[0]
        self.assertEqual(effects[0].target, "player")
        self.game.stack.append(StackItem(self.a, effects, [self.b]))
        self.game.resolve_top()
        self.assertEqual(len(self.b.hand), 2)
        self.assertFalse(self.a.hand)

    def test_newly_matched_explosive_entry_can_choose_zero_for_both_targets(self):
        definition = DB.get("Explosive Entry")
        self.assertFalse(definition.unsupported)
        item = self.spell(definition, [None, None])
        self.assertTrue(item.resolved)
        enemy = self.perm(BEAR, self.b)
        self.spell(definition, [None, enemy])
        self.assertEqual(enemy.p1, 1)

    def test_newly_matched_aggressive_sabotage_kicker_hits_discard_target(self):
        definition = DB.get("Aggressive Sabotage")
        self.a.hand = [definition]
        self.b.hand = [BEAR, ISLAND]
        for _ in range(3):
            self.perm(DB.get("Swamp"), self.a)
        self.perm(MOUNTAIN, self.a)
        variant = next(c for c in self.game.spell_options(self.a) if self.game._origin(c)[1] == "kicker")
        self.assertTrue(self.game.cast(self.a, variant, [self.b]))
        self.game.settle()
        self.assertFalse(self.b.hand)
        self.assertEqual(self.b.life, 17)
        self.assertEqual(self.a.life, 20)

    def test_newly_matched_shredder_draw_and_loss_both_follow_target(self):
        definition = DB.get("Shredder's Revenge")
        self.assertFalse(definition.unsupported)
        effects = definition.modes[1]
        self.game.stack.append(StackItem(self.a, effects, [self.b, None]))
        self.game.resolve_top()
        self.assertEqual(len(self.b.hand), 2)
        self.assertFalse(self.a.hand)
        self.assertEqual((self.a.life, self.b.life), (20, 18))
        self.game.stack.append(StackItem(self.a, effects, [self.a, None]))
        self.game.resolve_top()
        self.assertEqual((self.a.life, self.b.life), (18, 18))
        self.assertEqual(len(self.a.hand), 2)
