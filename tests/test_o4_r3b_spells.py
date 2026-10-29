"""Life, discard and graveyard riders, including real-game event/target interactions."""
import dataclasses
from unittest.mock import patch

from mtgsim.carddb import CardDB
from mtgsim.cards import Effect, _parse_effects
from mtgsim.engine import StackItem
from tests.test_templates import Base, BEAR, DRAGON3, ISLAND, SHOCK, card

DB = CardDB()
LILIANA = DB.get("Liliana the Faultless")
CONFIDANT = DB.get("Enlightened Confidant")
MOSEO = DB.get("Moseo, Vein's New Dean")
MOON = DB.get("Moonshadow")
CORPSES = DB.get("Corpses of the Lost")
RAFFINE = DB.get("Raffine, Scheming Seer")


class SpellRiders(Base):
    def test_six_cards_fully_parse(self):
        for c in (LILIANA, CONFIDANT, MOSEO, MOON, CORPSES, RAFFINE):
            with self.subTest(c=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual(MOSEO.triggers[-1].effects[0].target, "graveyard_creature_life")

    def test_unknown_reward_shapes_stay_unsupported(self):
        for text in (
            "Target attacking creature connives X, where X is the amount of life you lost this turn.",
            "Draw a card. If you put a card with mana value less than or equal to the amount of life you gained "
            "this turn into your graveyard this way, put that card into your hand.",
            "Another target creature or planeswalker you control gains protection from everything until end of turn.",
            "Return up to one target creature card with mana value X or less from your graveyard to the "
            "battlefield, where X is the amount of life you lost this turn."):
            self.assertTrue(_parse_effects(text)[1], text)

    def test_liliana_discards_to_grant_other_creature_hexproof(self):
        liliana = self.perm(LILIANA, self.a)
        ally = self.perm(BEAR, self.a)
        self.perm(ISLAND, self.a)
        self.a.hand = [SHOCK]
        self.assertTrue(self.game.activate_ability(self.a, liliana, 0, [ally]))
        self.game.settle()
        self.assertTrue(liliana.tapped)
        self.assertTrue(ally.has("hexproof"))
        self.assertFalse(liliana.has("hexproof"))
        self.assertIn(SHOCK, self.a.graveyard)
        self.assertFalse(self.a.hand)

    def test_liliana_rejects_self_and_opponent_before_cost(self):
        liliana = self.perm(LILIANA, self.a)
        enemy = self.perm(BEAR, self.b)
        land = self.perm(ISLAND, self.a)
        self.a.hand = [SHOCK]
        for target in (liliana, enemy):
            self.assertFalse(self.game.activate_ability(self.a, liliana, 0, [target]))
            self.assertEqual(self.a.hand, [SHOCK])
            self.assertFalse(liliana.tapped)
            self.assertFalse(land.tapped)
        self.assertFalse(self.game.activate_ability(self.a, liliana, 0))

    def test_liliana_can_protect_planeswalker_and_needs_discard(self):
        liliana = self.perm(LILIANA, self.a)
        walker = self.perm(card("Test Walker", types="Planeswalker", text="Loyalty: 3"), self.a)
        walker.counters["loyalty"] = 3
        self.perm(ISLAND, self.a)
        self.assertFalse(self.game.activate_ability(self.a, liliana, 0, [walker]))
        self.a.hand = [ISLAND]
        self.assertTrue(self.game.activate_ability(self.a, liliana, 0, [walker]))
        self.game.settle()
        self.assertTrue(walker.has("hexproof"))

    def test_liliana_life_gain_trigger_is_still_active(self):
        self.perm(LILIANA, self.a)
        self.game.enter_battlefield(self.a, BEAR)
        self.game.settle()
        self.assertEqual(self.a.life, 21)

    def end_step(self):
        self.game.fire(self.a, "end_step")
        self.game.settle()

    def test_confidant_returns_only_survelled_card_within_life_budget(self):
        self.perm(CONFIDANT, self.a)
        self.a.graveyard = [BEAR]
        old = self.a.graveyard[0]
        self.a.library = [DRAGON3]
        self.game.change_life(self.a, 3, "test")
        original = self.game.hook
        with patch.object(self.game, "hook", side_effect=lambda p, name:
                          (lambda game, player, cards: cards) if name == "scry" else original(p, name)):
            self.end_step()
        self.assertEqual(self.a.hand, [DRAGON3])
        self.assertEqual(self.a.graveyard, [old])

    def test_confidant_no_life_no_trigger_and_over_budget_stays_in_gy(self):
        self.perm(CONFIDANT, self.a)
        self.a.library = [DRAGON3]
        self.game.fire(self.a, "end_step")
        self.assertFalse(self.game.pending)
        self.game.change_life(self.a, 2, "test")
        original = self.game.hook
        with patch.object(self.game, "hook", side_effect=lambda p, name:
                          (lambda game, player, cards: cards) if name == "scry" else original(p, name)):
            self.end_step()
        self.assertFalse(self.a.hand)
        self.assertEqual(self.a.graveyard, [DRAGON3])

    def test_confidant_cannot_pick_kept_card_or_previous_surveil(self):
        self.perm(CONFIDANT, self.a)
        self.a.graveyard = [BEAR]
        self.a.library = [ISLAND]
        self.game.change_life(self.a, 5, "test")
        original = self.game.hook
        with patch.object(self.game, "hook", side_effect=lambda p, name:
                          (lambda *args: []) if name == "scry" else original(p, name)):
            self.end_step()
        self.assertEqual(self.a.library, [ISLAND])
        self.assertFalse(self.a.hand)
        reward = CONFIDANT.triggers[0].effects[-1]
        self.game.resolve(self.a, reward, None, StackItem(self.a, [reward], [None]))
        self.assertFalse(self.a.hand)

    def test_life_gained_tracks_gross_gain_not_net_and_resets(self):
        self.game.change_life(self.a, 2, "gain")
        self.game.change_life(self.a, -5, "loss")
        self.game.change_life(self.a, 1, "gain")
        self.assertEqual(self.a.life_gained_turn, 3)
        # Stop at the first step, just after the per-turn reset.
        with patch.object(self.game, "begin_upkeep", side_effect=RuntimeError("stop")):
            with self.assertRaises(RuntimeError):
                self.game.take_turn(self.b)
        self.assertEqual(self.a.life_gained_turn, 0)

    def test_moseo_reanimates_after_life_gain_and_fires_enters(self):
        self.perm(MOSEO, self.a)
        self.perm(LILIANA, self.a)
        self.a.graveyard = [DRAGON3, BEAR]
        self.game.change_life(self.a, 3, "test")
        self.end_step()
        self.assertIn("Big Dragon", [x.card.name for x in self.a.creatures])
        self.assertEqual(self.a.graveyard, [BEAR])
        self.assertEqual(self.a.life, 24)

    def test_moseo_no_life_and_over_budget(self):
        self.perm(MOSEO, self.a)
        self.a.graveyard = [DRAGON3]
        self.game.fire(self.a, "end_step")
        self.assertFalse(self.game.pending)
        self.game.change_life(self.a, 2, "test")
        self.end_step()
        self.assertEqual(self.a.graveyard, [DRAGON3])
        self.assertEqual(len(self.a.creatures), 1)

    def test_moseo_target_removed_does_not_choose_replacement(self):
        self.perm(MOSEO, self.a)
        self.a.graveyard = [DRAGON3, BEAR]
        self.game.change_life(self.a, 3, "test")
        self.game.fire(self.a, "end_step")
        self.game.flush_triggers()
        chosen = self.game.stack[-1].targets[0]
        self.assertEqual(chosen.name, "Big Dragon")
        self.game.move_card(chosen, self.a.graveyard, self.a.exile)
        self.game.resolve_top()
        self.assertEqual(self.a.graveyard, [BEAR])
        self.assertEqual(len(self.a.creatures), 1)

    def test_moseo_same_physical_card_reentering_gy_is_new_target(self):
        self.perm(MOSEO, self.a)
        self.a.graveyard = [BEAR]
        self.game.change_life(self.a, 2, "test")
        self.game.fire(self.a, "end_step")
        self.game.flush_triggers()
        chosen = self.game.stack[-1].targets[0]
        self.game.move_card(chosen, self.a.graveyard, self.a.exile)
        self.game.move_card(chosen, self.a.exile, self.a.graveyard)
        self.game.resolve_top()
        self.assertIn(chosen, self.a.graveyard)
        self.assertEqual(len(self.a.creatures), 1)

    def moon(self, player=None):
        return self.game.enter_battlefield(player or self.a, MOON)

    def test_moonshadow_enters_with_six_and_removes_counter_on_death(self):
        moon = self.moon()
        victim = self.perm(BEAR, self.a)
        self.assertEqual((moon.m1, moon.power), (6, 1))
        self.game.destroy(victim)
        self.assertEqual(len(self.game.pending), 1)
        self.game.settle()
        self.assertEqual((moon.m1, moon.power), (5, 2))

    def test_moonshadow_permanent_discard_and_library_mill(self):
        moon = self.moon()
        self.a.hand = [BEAR]
        self.game.discard_card(self.a, self.a.hand[0])
        self.game.settle()
        self.assertEqual(moon.m1, 5)
        self.a.library = [ISLAND, BEAR, DRAGON3]
        self.game.resolve(self.a, Effect("mill", 3), None)
        self.assertEqual(len(self.game.pending), 1)
        self.game.settle()
        self.assertEqual(moon.m1, 4)

    def test_moonshadow_ignores_opponent_nonpermanent_and_token(self):
        moon = self.moon()
        self.game.destroy(self.perm(BEAR, self.b))
        self.a.hand = [SHOCK]
        self.game.discard_card(self.a, self.a.hand[0])
        self.game.destroy(self.perm(dataclasses.replace(BEAR, is_token=True), self.a))
        self.assertFalse(self.game.pending)
        self.assertEqual(moon.m1, 6)

    def test_moonshadow_no_counters_and_gone_source(self):
        moon = self.moon()
        moon.counters["-1/-1"] = 0
        self.game.destroy(self.perm(BEAR, self.a))
        self.assertFalse(self.game.pending)
        moon.counters["-1/-1"] = 2
        self.game.destroy(self.perm(BEAR, self.a))
        self.game.leave_battlefield(moon, "hand")
        self.game.settle()
        self.assertEqual(moon.m1, 2)

    def test_moonshadow_simultaneous_sba_deaths_trigger_once(self):
        moon = self.moon()
        for _ in range(2):
            victim = self.perm(BEAR, self.a)
            victim.damage = 2
        self.game.state_based_actions()
        self.assertEqual(len(self.game.pending), 1)
        self.game.settle()
        self.assertEqual(moon.m1, 5)

    def test_moonshadow_dying_in_wrath_does_not_see_anywhere_event(self):
        self.moon()
        self.perm(BEAR, self.a)
        self.game.resolve(self.a, Effect("wrath"), None)
        self.assertFalse(self.game.pending)

    def test_two_moonshadows_each_trigger_once_per_mill(self):
        a = self.moon()
        b = self.moon()
        self.a.library = [BEAR, ISLAND]
        self.game.resolve(self.a, Effect("mill", 2), None)
        self.assertEqual(len(self.game.pending), 2)
        self.game.settle()
        self.assertEqual((a.m1, b.m1), (5, 5))

    def test_corpses_lord_and_haste_end_when_source_leaves(self):
        corpses = self.game.enter_battlefield(self.a, CORPSES)
        self.game.settle()
        skeleton = self.a.creatures[0]
        bear = self.perm(BEAR, self.a)
        enemy = self.perm(skeleton.card, self.b)
        self.assertEqual(skeleton.power, 3)
        self.assertTrue(skeleton.has("haste"))
        self.assertEqual(bear.power, 2)
        self.assertFalse(bear.has("haste"))
        self.assertEqual(enemy.power, 2)
        self.assertFalse(enemy.has("haste"))
        self.game.leave_battlefield(corpses, "hand")
        self.assertEqual(skeleton.power, 2)
        self.assertFalse(skeleton.has("haste"))

    def test_corpses_descended_pay_life_return(self):
        corpses = self.game.enter_battlefield(self.a, CORPSES)
        self.game.destroy(self.perm(BEAR, self.a))
        self.end_step()
        self.assertEqual(self.a.life, 19)
        self.assertNotIn(corpses, self.a.battlefield)
        self.assertIn(CORPSES, self.a.hand)

    def test_corpses_no_descent_no_payment_and_can_decline(self):
        corpses = self.game.enter_battlefield(self.a, CORPSES)
        self.end_step()
        self.assertEqual(self.a.life, 20)
        self.assertIn(corpses, self.a.battlefield)
        self.game.destroy(self.perm(BEAR, self.a))
        original = self.game.hook
        with patch.object(self.game, "hook", side_effect=lambda p, name:
                          (lambda *args: False) if name == "pay_optional" else original(p, name)):
            self.end_step()
        self.assertEqual(self.a.life, 20)
        self.assertIn(corpses, self.a.battlefield)

    def test_raffine_connive_x_draws_all_then_discards_and_counts_nonlands(self):
        source = self.perm(RAFFINE, self.a)
        ally = self.perm(BEAR, self.a)
        self.game.attackers = [source, ally]
        self.a.library = [SHOCK, DRAGON3]
        self.a.hand = []
        seen = []
        original = self.a.ai.choose_discard
        def choose(game, player):
            seen.append(len(player.hand))
            return original(game, player)
        with patch.object(self.a.ai, "choose_discard", side_effect=choose):
            self.game.fire(self.a, "you_attack")
            self.game.settle()
        self.assertEqual(seen, [2, 1])
        self.assertFalse(self.a.hand)
        self.assertEqual(source.p1 + ally.p1, 2)
        self.assertEqual(len(self.a.graveyard), 2)

    def test_raffine_rejects_nonattacker_and_land_discard_adds_no_counter(self):
        source = self.perm(RAFFINE, self.a)
        other = self.perm(BEAR, self.a)
        effect = RAFFINE.triggers[0].effects[0]
        self.game.attackers = [source]
        self.assertFalse(self.game.legal_target(self.a, effect, other))
        self.a.library = [ISLAND]
        self.game.fire(self.a, "you_attack")
        self.game.settle()
        self.assertEqual(source.p1, 0)
        self.assertIn(ISLAND, self.a.graveyard)

    def test_raffine_target_stops_attacking_before_resolution(self):
        source = self.perm(RAFFINE, self.a)
        self.game.attackers = [source]
        self.game.fire(self.a, "you_attack")
        self.game.flush_triggers()
        self.game.attackers.clear()
        before = len(self.a.library)
        self.game.resolve_top()
        self.assertEqual(len(self.a.library), before)

    def test_moonshadow_separate_deaths_are_separate_events(self):
        moon = self.moon()
        for _ in range(2):
            self.game.destroy(self.perm(BEAR, self.a))
        self.assertEqual(len(self.game.pending), 2)
        self.game.settle()
        self.assertEqual(moon.m1, 4)

    def test_moonshadow_surveil_event_survives_confidant_reclaiming_card(self):
        moon = self.moon()
        self.perm(CONFIDANT, self.a)
        self.a.library = [BEAR]
        self.game.change_life(self.a, 2, "test")
        original = self.game.hook
        with patch.object(self.game, "hook", side_effect=lambda p, name:
                          (lambda game, player, cards: cards) if name == "scry" else original(p, name)):
            self.end_step()
        self.assertEqual(self.a.hand, [BEAR])
        self.assertFalse(self.a.graveyard)
        self.assertEqual(moon.m1, 5)

    def test_moseo_intervening_condition_is_checked_again_on_resolution(self):
        self.perm(MOSEO, self.a)
        self.a.graveyard = [BEAR]
        self.game.change_life(self.a, 2, "test")
        self.game.fire(self.a, "end_step")
        self.game.flush_triggers()
        self.a.life_gained_turn = 0
        self.game.resolve_top()
        self.assertEqual(self.a.graveyard, [BEAR])

    def test_moseo_etb_pest_gain_can_pay_next_end_step_budget(self):
        source = self.game.enter_battlefield(self.a, MOSEO)
        self.game.settle()
        pest = next(c for c in self.a.creatures if c is not source)
        self.game.fire(self.a, "attacks", pest)
        self.game.settle()
        self.assertEqual(self.a.life_gained_turn, 1)
        self.a.graveyard = [card("One Drop", "{B}", power=1, toughness=1)]
        self.end_step()
        self.assertIn("One Drop", [c.card.name for c in self.a.creatures])

    def test_moonshadow_indestructible_survives_amalia_sweep_with_one_trigger(self):
        moon = self.moon()
        moon.temp_kw.add("indestructible")
        self.perm(BEAR, self.a)
        self.perm(DRAGON3, self.a)
        source = self.perm(card("Twenty", types="Creature", power=20, toughness=20), self.b)
        item = StackItem(self.b, [], [], source=source)
        self.game.resolve(self.b, Effect("destroy_other_exact_power", 20), None, item)
        self.assertEqual(len(self.game.pending), 1)
        self.game.settle()
        self.assertEqual(moon.m1, 5)

    def test_moonshadow_groups_multi_card_discard_and_connive(self):
        moon = self.moon()
        self.a.hand = [BEAR, DRAGON3]
        self.game.resolve(self.a, Effect("discard", 2), None)
        self.assertEqual(len(self.game.pending), 1)
        self.game.settle()
        self.assertEqual(moon.m1, 5)

    def test_loyalty_source_guard_rejects_self_without_spending_loyalty(self):
        effect = LILIANA.activated[0].effects[0]
        definition = dataclasses.replace(card("Protector", types="Planeswalker"), loyalty=3,
                                         loyalty_abilities=[(1, [effect])])
        walker = self.perm(definition, self.a)
        walker.counters["loyalty"] = 3
        self.assertFalse(self.game.activate_loyalty(self.a, walker, 0, [walker]))
        self.assertEqual(walker.loyalty, 3)
        self.assertFalse(walker.loyalty_used)
        ally = self.perm(BEAR, self.a)
        self.assertTrue(self.game.activate_loyalty(self.a, walker, 0, [ally]))
        self.game.settle()
        self.assertTrue(ally.has("hexproof"))

    def test_optional_life_source_pronoun_grants_poet_flying(self):
        poet = self.perm(DB.get("Arrogant Poet"), self.a)
        self.assertFalse(poet.card.unsupported)
        self.game.fire(self.a, "attacks", poet)
        self.game.settle()
        self.assertTrue(poet.has("flying"))
        self.assertEqual(self.a.life, 18)

    def test_infusion_self_counter_pronoun_is_source(self):
        self.game.change_life(self.a, 1, "test")
        teacher = self.game.enter_battlefield(self.a, DB.get("Old-Growth Educator"))
        self.game.settle()
        self.assertFalse(teacher.card.unsupported)
        self.assertEqual(teacher.p1, 2)

    def test_optional_life_reflexive_trigger_stays_unsupported(self):
        edifice = DB.get("Ambulatory Edifice")
        self.assertTrue(edifice.unsupported)
        self.assertIn("When you do", " ".join(edifice.unsupported))
