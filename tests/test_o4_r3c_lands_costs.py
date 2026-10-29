"""Channel discounts, ability counters, Case permissions, and land entry wordings."""
from mtgsim import cost_mana
from mtgsim.cards import Effect
from mtgsim.engine import StackItem
from mtgsim.engine.policy import ability_worth, use_abilities
from tests.test_templates import Base, card, BEAR, ISLAND, PLAINS, SWAMP

EIGANJO = card("Eiganjo, Seat of the Empire", types="Legendary Land", text="{T}: Add {W}.\nChannel — {2}{W}, "
               "Discard this card: It deals 4 damage to target attacking or blocking creature. This ability costs "
               "{1} less to activate for each legendary creature you control.")
OTAWARA = card("Otawara, Soaring City", types="Legendary Land", text="{T}: Add {U}.\nChannel — {3}{U}, Discard "
               "this card: Return target artifact, creature, enchantment, or planeswalker to its owner's hand. "
               "This ability costs {1} less to activate for each legendary creature you control.")
TIDEBINDER = card("Tishana's Tidebinder", "{1}{U}{U}", "Creature — Merfolk Wizard", "Flash\nWhen this creature "
                  "enters, counter up to one target activated or triggered ability. If an ability of an artifact, "
                  "creature, or planeswalker is countered this way, that permanent loses all abilities for as "
                  "long as this creature remains on the battlefield.", 3, 2)
CASE = card("Case of the Uneaten Feast", "{W}", "Enchantment — Case", "Whenever a creature you control enters, "
            "you gain 1 life.\nTo solve — You've gained 5 or more life this turn.\nSolved — Sacrifice this Case: "
            "Creature cards in your graveyard gain \"You may cast this card from your graveyard\" until end of turn.")
BOUNCE_LAND = card("Simic Growth Chamber", types="Land", text="This land enters tapped.\nWhen this land enters, "
                   "return a land you control to its owner's hand.\n{T}: Add {G}{U}.")
BASIC_CHECK = card("Cinder Glade", types="Land — Mountain Forest", text="This land enters tapped unless you "
                   "control two or more basic lands.")
OPPONENT_CHECK = card("Sea of Clouds", types="Land", text="This land enters tapped unless you have two or more "
                      "opponents.\n{T}: Add {W} or {U}.")
FREE_CREATURE = card("Free creature", "{0}", power=1, toughness=1)


class LandsCostsTests(Base):
    def legends(self, n=2):
        return [self.perm(card(f"Legend {i}", "{0}", "Legendary Creature", "", 1, 1), self.a) for i in range(n)]

    def channel(self, c=EIGANJO):
        self.a.hand.append(c)
        return next(x for x in self.game.spell_options(self.a) if self.game._origin(x)[1] == "channel")

    def solve(self):
        case = self.game.enter_battlefield(self.a, CASE)
        self.game.change_life(self.a, 5, "test life gain")
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertTrue(case.solved)
        return case

    def test_templates_and_tidebinder_rider_stays_unsupported(self):
        for c in (EIGANJO, OTAWARA, CASE, BOUNCE_LAND, BASIC_CHECK, OPPONENT_CHECK):
            self.assertEqual(c.unsupported, [], c.name)
        self.assertEqual(len(TIDEBINDER.triggers), 1)
        self.assertEqual(TIDEBINDER.triggers[0].effects[0].kind, "counter_ability")
        self.assertEqual(len(TIDEBINDER.unsupported), 1)
        self.assertIn("loses all abilities", TIDEBINDER.unsupported[0])

    def test_eiganjo_channels_for_white_with_two_legends(self):
        legends = self.legends()
        land = self.perm(PLAINS, self.a)
        channel = self.channel()
        self.assertEqual(self.game.cost_of(self.a, channel), {"generic": 0, "W": 1})
        victim = self.perm(card("Attacker", "{0}", power=4, toughness=4), self.b)
        self.game.attackers = [victim]
        self.assertTrue(self.game.cast(self.a, channel, [victim]))
        self.assertTrue(land.tapped)
        self.assertNotIn(victim, self.b.battlefield)
        self.assertEqual(self.a.graveyard[0].name, EIGANJO.name)
        self.assertTrue(all(x in self.a.battlefield for x in legends))
        self.assertEqual(self.game.spells_cast if hasattr(self.game, "spells_cast") else {}, {})

    def test_channel_cost_dynamic_floor_and_legend_type(self):
        channel = self.channel()
        self.perm(card("Relic", types="Legendary Artifact"), self.a)
        self.perm(card("Land", types="Legendary Land"), self.a)
        self.assertEqual(self.game.cost_of(self.a, channel)["generic"], 2)
        legends = self.legends(3)
        self.assertEqual(self.game.cost_of(self.a, channel), {"generic": 0, "W": 1})
        for legend in legends[1:]:
            self.a.battlefield.remove(legend)
        self.assertEqual(self.game.cost_of(self.a, channel), {"generic": 1, "W": 1})
        self.assertEqual(channel.mana_cost, {"generic": 2, "W": 1})

    def test_illegal_channel_does_not_discard_or_pay(self):
        self.legends()
        land = self.perm(PLAINS, self.a)
        channel = self.channel()
        self.perm(BEAR, self.b)  # neither attacking nor blocking
        self.assertFalse(self.game.cast(self.a, channel))
        self.assertFalse(land.tapped)
        self.assertIn(EIGANJO, self.a.hand)
        self.assertFalse(self.a.graveyard)

    def test_channel_is_not_a_spell_for_costs_or_restricted_mana(self):
        reducer = card("Reducer", types="Enchantment", text="Instant and sorcery spells you cast cost {2} less to cast.")
        self.perm(reducer, self.a)
        channel = self.channel()
        self.assertEqual(self.game.cost_of(self.a, channel)["generic"], 2)
        self.legends()
        producer = card("Restricted white", types="Artifact", text="{T}: Add {W}. Spend this mana only to cast "
                        "instant and sorcery spells.")
        self.perm(producer, self.a)
        self.assertFalse(self.game.spell_payable(self.a, channel))
        self.perm(PLAINS, self.a)
        self.assertTrue(self.game.spell_payable(self.a, channel))

    def test_channel_works_during_opponents_turn_under_spell_lock(self):
        self.game.active_idx = 1
        locker = card("Lock", types="Creature", text="Your opponents can't cast spells during your turn.", power=2, toughness=2)
        self.perm(locker, self.b)
        self.legends()
        self.perm(PLAINS, self.a)
        channel = self.channel()
        victim = self.perm(BEAR, self.b)
        self.game.blocks = {self.a.creatures[0]: [victim]}
        self.assertTrue(self.game.can_cast_now(self.a, channel))
        self.assertTrue(self.game.cast(self.a, channel, [victim]))

    def test_otawara_and_ordinary_ability_reductions(self):
        self.legends(3)
        self.perm(ISLAND, self.a)
        channel = self.channel(OTAWARA)
        target = self.perm(BEAR, self.b)
        self.assertEqual(self.game.cost_of(self.a, channel)["generic"], 0)
        self.assertTrue(self.game.cast(self.a, channel, [target]))
        self.assertEqual(self.b.hand[0].name, BEAR.name)
        draw = card("Scaled drawer", text="{3}: Draw a card. This ability costs {1} less to activate for each "
                    "creature you control.", power=1, toughness=1)
        self.assertFalse(draw.unsupported)
        self.assertFalse(draw.approximations)
        source = self.perm(draw, self.a)
        self.assertEqual(self.game.ability_cost(self.a, source, draw.activated[0])["generic"], 0)
        self.assertTrue(ability_worth(self.game, self.a, source, 0))
        self.assertTrue(self.game.activate_ability(self.a, source, 0))
        self.assertEqual(len(self.a.hand), 1)

    def test_nonland_multiple_channel_modes_are_distinct_and_playable(self):
        source = card("Two modes", "{2}", "Creature", "Channel — {1}{U}, Discard this card: Draw two cards.\n"
                      "Channel — {R}, Discard this card: It deals 2 damage to target creature.", 2, 2)
        self.assertFalse(source.unsupported)
        self.a.hand.append(source)
        modes = [c for c in self.game.spell_options(self.a) if self.game._origin(c)[1] == "channel"]
        self.assertEqual(len(modes), 2)
        self.assertIsNot(modes[0], modes[1])
        self.assertNotEqual(modes[0].name, modes[1].name)
        self.assertEqual([c.spell_effects[0].kind for c in modes], ["draw", "damage"])
        red = card("Mountain", types="Basic Land — Mountain")
        self.perm(red, self.a)
        victim = self.perm(FREE_CREATURE, self.b)
        self.assertTrue(self.game.cast(self.a, modes[1], [victim]))
        self.assertNotIn(victim, self.b.battlefield)
        self.assertEqual(self.a.graveyard[0].name, source.name)

    def test_channel_cost_and_target_layers_not_available_stay_unsupported(self):
        for text in ["Channel — {X}{X}{G}, Discard this card: Draw a card.",
                     "Channel — {G}, Discard this card: Return target creature card from your graveyard to your hand."]:
            source = card("Needs another layer", "{2}{G}", "Creature", text, 2, 2)
            self.assertTrue(source.unsupported)
            self.assertFalse(source.alt_costs)

    def test_tidebinder_counters_an_opponents_etb_trigger_in_real_game(self):
        healer = card("Healer", text="When this creature enters, you gain 5 life.", power=1, toughness=1)
        source = self.game.enter_battlefield(self.b, healer)
        self.game.flush_triggers()
        trigger = self.game.stack[0]
        for _ in range(3):
            self.perm(ISLAND, self.a)
        self.a.hand.append(TIDEBINDER)
        self.assertTrue(self.game.cast(self.a, self.a.hand[-1]))
        self.assertEqual(self.b.life, 20)
        self.assertNotIn(trigger, self.game.stack)
        self.assertIn(source, self.b.battlefield)
        self.assertEqual(self.a.creatures[0].card.name, TIDEBINDER.name)

    def test_ability_counter_preserves_paid_costs_and_permanent_source(self):
        drawer = card("Drawer", text="{1}, {T}: Draw a card.", power=1, toughness=1)
        source = self.perm(drawer, self.b)
        land = self.perm(ISLAND, self.b)
        self.game._priority_depth += 1
        try:
            self.assertTrue(self.game.activate_ability(self.b, source, 0))
            ability = self.game.stack[-1]
            effect = TIDEBINDER.triggers[0].effects[0]
            self.assertTrue(self.game.legal_target(self.a, effect, ability))
            self.game.resolve(self.a, effect, ability)
        finally:
            self.game._priority_depth -= 1
        self.assertIn(source, self.b.battlefield)
        self.assertTrue(source.tapped and land.tapped)
        self.assertFalse(self.b.hand)
        self.assertFalse(self.game.stack)

    def test_spell_and_mana_ability_are_not_ability_counter_targets(self):
        effect = TIDEBINDER.triggers[0].effects[0]
        spell = StackItem(self.b, [], [], card=FREE_CREATURE)
        mana = StackItem(self.b, [Effect("add_mana", data={"colors": ["U"]})], [None], kind="ability")
        loyalty = StackItem(self.b, [Effect("add_mana", data={"colors": ["U"]})], [None], kind="loyalty")
        self.game.stack = [spell, mana, loyalty]
        self.assertFalse(self.game.legal_target(self.a, effect, spell))
        self.assertFalse(self.game.legal_target(self.a, effect, mana))
        self.assertTrue(self.game.legal_target(self.a, effect, loyalty))
        self.assertFalse(self.game.can_counter(Effect("counter", target="spell"), loyalty, self.a))
        own = StackItem(self.a, [Effect("draw", 1)], [None], kind="ability")
        self.game.stack = [own]
        required = Effect("counter_ability", target="ability")
        self.assertEqual(self.game.auto_targets(self.a, [required]), [own])
        self.assertEqual(self.game.auto_targets(self.a, [effect]), [None])
        self.game.stack = [spell, mana, loyalty]
        self.game.resolve(self.a, effect, spell)
        self.assertIn(spell, self.game.stack)

    def test_counter_ability_filters_and_optional_zero_targets(self):
        mandatory = card("Stop ability", "{0}", "Instant", "Counter target activated ability.")
        optional = card("Maybe stop ability", "{0}", "Instant", "Counter up to one target activated or triggered ability.")
        self.a.hand.extend([mandatory, optional])
        self.assertFalse(self.game.can_cast_now(self.a, self.a.hand[0]))
        trigger = StackItem(self.b, [Effect("gain_life", 5)], [None], kind="trigger")
        self.game.stack.append(trigger)
        self.assertFalse(self.game.legal_target(self.a, mandatory.spell_effects[0], trigger))
        self.assertTrue(self.game.cast(self.a, self.a.hand[1], [None]))
        self.assertEqual(self.b.life, 25)  # explicitly chose zero targets, so the trigger resolved

    def test_case_solves_only_at_own_end_step_and_checks_both_times(self):
        source = self.game.enter_battlefield(self.a, CASE)
        self.assertFalse(self.game.can_activate(self.a, source, 0))
        self.game.change_life(self.a, 4, "test life gain")
        self.game.fire(self.a, "end_step")
        self.assertFalse(self.game.pending)
        self.game.change_life(self.a, 1, "test life gain")
        self.game.fire(self.b, "end_step")
        self.assertFalse(self.game.pending)
        self.game.fire(self.a, "end_step")
        self.game.flush_triggers()
        self.a.life_gained_turn = 4
        self.game.resolve_top()
        self.assertFalse(source.solved)
        self.a.life_gained_turn = 5
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertTrue(source.solved)
        self.game.fire(self.a, "end_step")
        self.assertFalse(self.game.pending)

    def test_case_real_turn_creature_entries_solve_it(self):
        source = self.game.enter_battlefield(self.a, CASE)
        def main(player):
            if self.game.step == "main1":
                for _ in range(5):
                    self.game.enter_battlefield(player, FREE_CREATURE)
                self.game.settle()
        self.game.main_phase = main
        self.a.ai.choose_attackers = lambda g, me, opp: []
        self.game.take_turn(self.a)
        self.assertEqual(self.a.life_gained_turn, 5)
        self.assertTrue(source.solved)

    def test_case_sacrifices_to_grant_normal_graveyard_cast_not_flashback(self):
        source = self.solve()
        self.a.graveyard.append(FREE_CREATURE)
        creature = self.a.graveyard[-1]
        self.a.graveyard.append(card("Not a creature", "{0}", "Instant", "Draw a card."))
        self.assertTrue(self.game.activate_ability(self.a, source, 0))
        self.assertNotIn(source, self.a.battlefield)
        options = [c for c in self.game.spell_options(self.a) if self.game._origin(c)[1] == "graveyard_cast"]
        self.assertEqual(len(options), 1)
        self.game._priority_depth += 1
        try:
            self.assertTrue(self.game.cast(self.a, options[0]))
            self.game.counter(self.b, Effect("counter"), self.game.stack[-1])
        finally:
            self.game._priority_depth -= 1
        self.assertIn(creature, self.a.graveyard)
        self.assertFalse(self.a.exile)
        self.assertFalse(cost_mana.graveyard_cast_options(self.game, self.a))
        self.assertFalse(self.game.can_cast_now(self.a, options[0]))

    def test_ai_keeps_solved_case_until_permission_can_be_used(self):
        source = self.solve()
        self.a.graveyard.append(FREE_CREATURE)
        self.game.step = "end_step"
        self.assertTrue(self.game.can_activate(self.a, source, 0))
        self.assertFalse(ability_worth(self.game, self.a, source, 0))
        self.game.step = "main1"
        other = self.game.enter_battlefield(self.a, CASE)
        other.solved = True
        use_abilities(self.game, self.a)
        self.assertNotIn(source, self.a.battlefield)
        self.assertIn(other, self.a.battlefield)
        self.assertEqual(len(self.a.creatures), 1)
        self.assertEqual(self.a.creatures[0].card.name, FREE_CREATURE.name)

    def test_case_permission_is_snapshot_and_expires(self):
        source = self.solve()
        self.a.graveyard.append(FREE_CREATURE)
        original = self.a.graveyard[-1]
        self.assertTrue(self.game.activate_ability(self.a, source, 0))
        later = card("Later creature", "{0}", power=2, toughness=2)
        self.a.graveyard.append(later)
        self.assertEqual(cost_mana.graveyard_cast_options(self.game, self.a), [original])
        self.game.turn += 1
        self.assertFalse(cost_mana.graveyard_cast_options(self.game, self.a))

    def test_countering_solve_trigger_keeps_case_unsolved(self):
        source = self.game.enter_battlefield(self.a, CASE)
        self.game.change_life(self.a, 5, "test life gain")
        self.game.fire(self.a, "end_step")
        self.game.flush_triggers()
        self.game.resolve(self.b, TIDEBINDER.triggers[0].effects[0], self.game.stack[-1])
        self.assertFalse(source.solved)
        self.assertFalse(self.game.can_activate(self.a, source, 0))

    def test_bounce_land_returns_an_existing_land_or_itself(self):
        old = self.perm(ISLAND, self.a)
        old.tapped = True
        entered = self.game.enter_battlefield(self.a, BOUNCE_LAND)
        self.game.settle()
        self.assertTrue(entered.tapped)
        self.assertIn(entered, self.a.battlefield)
        self.assertNotIn(old, self.a.battlefield)
        self.assertEqual(self.a.hand[0].name, ISLAND.name)
        self.game.leave_battlefield(entered, "graveyard")
        alone = self.game.enter_battlefield(self.a, BOUNCE_LAND)
        self.game.settle()
        self.assertNotIn(alone, self.a.battlefield)
        self.assertEqual(self.a.hand[-1].name, BOUNCE_LAND.name)

    def test_two_basic_land_condition_counts_basics_not_land_types(self):
        self.perm(PLAINS, self.a)
        self.perm(card("Typed nonbasic", types="Land — Forest Mountain"), self.a)
        one_basic = self.game.enter_battlefield(self.a, BASIC_CHECK)
        self.assertTrue(one_basic.tapped)
        self.perm(card("Snow-Covered Island", types="Basic Snow Land — Island"), self.a)
        two_basics = self.game.enter_battlefield(self.a, BASIC_CHECK)
        self.assertFalse(two_basics.tapped)

    def test_multiplayer_wording_is_always_tapped_in_duel(self):
        for _ in range(3):
            self.perm(SWAMP, self.a)
        entered = self.game.enter_battlefield(self.a, OPPONENT_CHECK)
        self.assertTrue(entered.tapped)

    def test_out_of_scope_conditions_and_riders_remain_unsupported(self):
        for text in ["To solve — Three or more creatures died this turn.",
                     "Channel — {2}{W}, Discard this card: Draw a card. This ability costs {1} less to activate "
                     "for each attraction you've visited this turn.",
                     "This land enters tapped unless you control three or more basic lands."]:
            unsupported = card("Unimplemented condition", types="Land", text=text)
            self.assertTrue(unsupported.unsupported)
