"""First qualifying casts, exclusive mana modes/pools, and Bankbuster rewards."""
from mtgsim.cards import Effect
from mtgsim.engine import StackItem, find_payment, payable
from tests.test_templates import Base, ISLAND, SWAMP, BEAR, card

MOMO = card("Momo, Friendly Flier", "{W}", "Legendary Creature — Lemur", "Flying\nThe first non-Lemur creature "
            "spell with flying you cast during each of your turns costs {1} less to cast.", 1, 1)
FLIER = card("Flier", "{1}{U}", "Creature — Bird", "Flying", 2, 2)
LEMUR = card("Flying Lemur", "{1}{U}", "Creature — Lemur", "Flying", 2, 2)
TABLET = card("Tablet of Discovery", "{1}", "Artifact", "{T}: Add {R}.\n{T}: Add {R}{R}. Spend this mana only to "
              "cast instant and sorcery spells.")
BUSTER = card("Reckoner Bankbuster", "{2}", "Artifact — Vehicle", "This Vehicle enters with three charge counters "
              "on it.\n{2}, {T}, Remove a charge counter from this Vehicle: Draw a card. Then if there are no charge "
              "counters on this Vehicle, create a Treasure token and a 1/1 colorless Pilot creature token with "
              "\"This token crews Vehicles as though its power were 2 greater.\"\nCrew 3", 4, 4)
INSTANT = card("Two red", "{R}{R}", "Instant", "You gain 1 life.")
RED_CREATURE = card("Red creature", "{R}{R}", "Creature", "", 2, 2)


class CostManaTests(Base):
    def cast_card(self, c, p=None):
        p = p or self.a
        p.hand.append(c)
        actual = p.hand[-1]
        self.assertTrue(self.game.cast(p, actual))
        return actual

    def test_templates(self):
        self.assertFalse(MOMO.unsupported)
        self.assertFalse(TABLET.unsupported)
        self.assertFalse(BUSTER.unsupported)
        self.assertEqual(BUSTER.etb_named_counters, ("charge", 3))
        self.assertEqual(BUSTER.crew, 3)
        self.assertEqual((TABLET.mana_amount, TABLET.restricted_mana_amount), (1, 2))

    def test_momo_two_fliers_in_real_game(self):
        self.perm(MOMO, self.a)
        lands = [self.perm(ISLAND, self.a) for _ in range(3)]
        self.assertEqual(self.game.cost_of(self.a, FLIER), {"generic": 0, "U": 1})
        self.cast_card(FLIER)
        self.assertEqual(sum(x.tapped for x in lands), 1)
        self.assertEqual(self.game.cost_of(self.a, FLIER), {"generic": 1, "U": 1})
        self.cast_card(FLIER)
        self.assertEqual(sum(x.tapped for x in lands), 3)
        self.assertEqual(len([x for x in self.a.creatures if x.card.name == FLIER.name]), 2)

    def test_nonqualifying_spells_do_not_consume_momo(self):
        self.perm(MOMO, self.a)
        for _ in range(6):
            self.perm(ISLAND, self.a)
        self.cast_card(card("Ground", "{0}", power=1, toughness=1))
        self.cast_card(LEMUR)
        changeling = card("Shapeshifter", "{U}", "Creature — Shapeshifter", "Changeling\nFlying", 1, 1)
        self.cast_card(changeling)
        self.assertEqual(self.game.cost_of(self.a, FLIER)["generic"], 0)

    def test_first_cast_is_historical_even_if_countered_and_reducer_enters_later(self):
        self.perm(ISLAND, self.a)
        self.perm(ISLAND, self.a)
        self.game._priority_depth += 1
        try:
            first = self.cast_card(FLIER)
            spell = self.game.stack[-1]
            self.game.counter(self.b, Effect("counter"), spell)
        finally:
            self.game._priority_depth -= 1
        self.assertIn(first, self.a.graveyard)
        self.perm(MOMO, self.a)
        self.assertEqual(self.game.cost_of(self.a, FLIER)["generic"], 1)

    def test_failed_illegal_cast_does_not_consume_first(self):
        self.perm(MOMO, self.a)
        self.a.hand.append(FLIER)
        self.assertFalse(self.game.cast(self.a, self.a.hand[-1]))
        self.perm(ISLAND, self.a)
        self.assertEqual(self.game.cost_of(self.a, FLIER)["generic"], 0)
        self.assertTrue(self.game.cast(self.a, self.a.hand[-1]))

    def test_own_turn_only_and_reset(self):
        self.perm(MOMO, self.a)
        flash_flier = card("Flash Bird", "{1}{U}", "Creature — Bird", "Flying, flash", 2, 2)
        self.game.active_idx = 1
        self.assertEqual(self.game.cost_of(self.a, flash_flier)["generic"], 1)
        self.game.active_idx = 0
        self.perm(ISLAND, self.a)
        self.cast_card(FLIER)
        self.assertEqual(self.game.cost_of(self.a, FLIER)["generic"], 1)
        self.game.turn += 2
        self.assertEqual(self.game.cost_of(self.a, FLIER)["generic"], 0)

    def test_first_filter_family_and_stacking(self):
        for text, spell in [("creature", BEAR), ("artifact", TABLET), ("instant or sorcery", INSTANT),
                            ("Dragon", card("Dragon spell", "{2}{R}", "Creature — Dragon", "Flying", 3, 3))]:
            with self.subTest(filter=text):
                reducer = card("Reducer", text=f"The first {text} spell you cast each turn costs {{2}} less to cast.",
                               power=1, toughness=1)
                self.assertFalse(reducer.unsupported)
                source = self.perm(reducer, self.a)
                self.assertEqual(self.game.cost_of(self.a, spell).get("generic", 0), 0)
                self.a.battlefield.remove(source)
        self.perm(MOMO, self.a)
        self.perm(MOMO, self.a)
        bigger = card("Bigger Bird", "{3}{U}", "Creature — Bird", "Flying", 3, 3)
        self.assertEqual(self.game.cost_of(self.a, bigger)["generic"], 1)

    def test_tablet_restricted_two_or_unrestricted_one(self):
        tablet = self.perm(TABLET, self.a)
        self.a.hand.extend([INSTANT, RED_CREATURE])
        instant, creature = self.a.hand
        self.assertTrue(self.game.can_cast_now(self.a, instant))
        self.assertTrue(self.a.ai._can_cast(self.game, self.a, instant))
        self.assertFalse(self.game.can_cast_now(self.a, creature))
        self.assertFalse(self.a.ai._can_cast(self.game, self.a, creature))
        self.assertIsNone(self.game.pay(self.a, {"generic": 2}))
        self.assertFalse(tablet.tapped)
        self.assertTrue(self.game.cast(self.a, instant))
        self.assertTrue(tablet.tapped)
        self.assertEqual(self.a.life, 21)
        tablet.tapped = False
        red_one = card("One red", "{R}", "Creature", "", 1, 1)
        self.cast_card(red_one)
        self.assertTrue(tablet.tapped)

    def test_mana_modes_are_exclusive_and_keep_colors(self):
        dual = card("Mode artifact", "{1}", "Artifact", "{T}: Add {C}.\n{T}: Add {R}{R}. Spend this mana only "
                    "to cast instant and sorcery spells.")
        source = self.perm(dual, self.a)
        sources = self.game.mana_sources(self.a, spell=INSTANT)
        self.assertFalse(payable(sources, {"C": 1, "R": 1}))
        self.assertFalse(payable(sources, {"generic": 3}))
        self.assertTrue(payable(sources, {"R": 2}))
        self.assertTrue(payable(sources, {"C": 1}))
        self.assertEqual(find_payment(sources, {"R": 2}), [source])

    def test_restricted_pool_keeps_restriction_for_payer_and_ai(self):
        effs_card = card("Pool spell", "{0}", "Instant", "Add {R}{R}. Spend this mana only to cast instant and "
                         "sorcery spells.")
        self.assertFalse(effs_card.unsupported)
        for effect in effs_card.spell_effects:
            self.game.resolve(self.a, effect, None)
        self.assertEqual(len(self.a.pool), 2)
        self.a.hand.extend([INSTANT, RED_CREATURE])
        instant, creature = self.a.hand
        self.assertTrue(self.a.ai._can_cast(self.game, self.a, instant))
        self.assertFalse(self.a.ai._can_cast(self.game, self.a, creature))
        self.assertIsNone(self.game.pay(self.a, {"R": 1}))
        self.assertTrue(self.game.cast(self.a, instant))
        self.assertTrue(all(x.tapped for x in self.a.pool))

    def test_mixed_color_restricted_mana_uses_an_explicit_pool_ability(self):
        producer = card("Mixed producer", types="Artifact", text="{T}: Add {R}{G}. Spend this mana only to cast artifact spells.")
        self.assertFalse(producer.unsupported)
        source = self.perm(producer, self.a)
        self.assertTrue(self.game.activate_ability(self.a, source, 0))
        self.assertEqual({tuple(x.card.restricted_produces) for x in self.a.pool}, {("R",), ("G",)})
        artifact = card("Multicolor relic", "{R}{G}", "Artifact")
        self.assertTrue(self.game.spell_payable(self.a, artifact))
        self.assertFalse(self.game.spell_payable(self.a, card("RG bear", "{R}{G}", power=2, toughness=2)))
        self.cast_card(artifact)

    def test_restricted_pool_cannot_pay_an_optional_gate(self):
        spell = card("Restricted pool", "{0}", "Instant", "Add {R}{R}. Spend this mana only to cast instant and sorcery spells.")
        self.game.resolve(self.a, spell.spell_effects[0], None)
        effects = [Effect("pay_gate", data={"cost": {"generic": 2}}), Effect("gain_life", 5, cond="paid")]
        self.game.stack.append(StackItem(self.a, effects, [None, None]))
        self.game.settle()
        self.assertEqual(self.a.life, 20)
        self.assertTrue(all(not x.tapped for x in self.a.pool))

    def test_restricted_pool_allows_either_of_two_spell_types(self):
        producer = card("Geosurge", "{R}{R}{R}{R}", "Sorcery", "Add {R}{R}{R}{R}{R}{R}{R}. Spend this mana only "
                        "to cast artifact or creature spells.")
        self.assertFalse(producer.unsupported)
        self.game.resolve(self.a, producer.spell_effects[0], None)
        self.assertTrue(self.game.spell_payable(self.a, RED_CREATURE))
        self.assertTrue(self.game.spell_payable(self.a, TABLET))
        self.assertFalse(self.game.spell_payable(self.a, INSTANT))
        self.cast_card(RED_CREATURE)
        self.assertEqual(sum(not x.tapped for x in self.a.pool), 5)

    def test_other_simple_type_restrictions(self):
        for what, spell in [("artifact", TABLET), ("enchantment", card("Aura", "{1}", "Enchantment")),
                            ("planeswalker", card("Walker", "{1}", "Planeswalker", "", cmc=1))]:
            with self.subTest(type=what):
                source = card("Source", types="Artifact", text=f"{{T}}: Add {{C}}{{C}}. Spend this mana only to cast {what} spells.")
                perm = self.perm(source, self.a)
                self.assertFalse(source.unsupported)
                self.assertTrue(self.game.spell_payable(self.a, spell))
                self.assertFalse(payable(self.game.mana_sources(self.a, spell=RED_CREATURE), {"generic": 1}))
                self.a.battlefield.remove(perm)

    def test_bankbuster_third_draw_rewards_and_pilot_crews_without_combat_buff(self):
        bank = self.game.enter_battlefield(self.a, BUSTER)
        lands = [self.perm(SWAMP, self.a) for _ in range(2)]
        for remaining in (2, 1, 0):
            bank.tapped = False
            for land in lands:
                land.tapped = False
            self.assertTrue(self.game.activate_ability(self.a, bank, 0))
            self.assertEqual(bank.counters["charge"], remaining)
            self.assertEqual(len(self.a.hand), 3 - remaining)
            self.assertEqual(len([x for x in self.a.creatures if "Pilot" in x.card.subtypes]), int(remaining == 0))
        self.assertEqual(len([x for x in self.a.battlefield if x.card.token_kind == "treasure"]), 1)
        pilot = next(x for x in self.a.creatures if "Pilot" in x.card.subtypes)
        self.assertEqual((pilot.power, pilot.toughness, pilot.card.crew_bonus), (1, 1, 2))
        bank.tapped = False
        bank.sick = False
        self.assertFalse(self.game.can_activate(self.a, bank, 0))
        self.assertTrue(self.game.activate(self.a, bank, "crew"))
        self.assertTrue(bank.is_creature)
        self.assertTrue(pilot.tapped)
        self.assertEqual(pilot.power, 1)

    def test_bankbuster_reward_tests_counters_at_resolution(self):
        bank = self.game.enter_battlefield(self.a, BUSTER)
        bank.counters["charge"] = 1
        for _ in range(2):
            self.perm(SWAMP, self.a)
        self.game._priority_depth += 1
        try:
            self.assertTrue(self.game.activate_ability(self.a, bank, 0))
            bank.counters["charge"] = 1
        finally:
            self.game._priority_depth -= 1
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)
        self.assertFalse(self.a.creatures)
        self.assertFalse(any(x.card.token_kind == "treasure" for x in self.a.battlefield))

    def test_bankbuster_tokens_use_normal_doubling(self):
        doubler = card("Doubler", types="Enchantment", text="If one or more tokens would be created under your "
                       "control, twice that many of those tokens are created instead.")
        self.perm(doubler, self.a)
        bank = self.game.enter_battlefield(self.a, BUSTER)
        bank.counters["charge"] = 1
        for _ in range(2):
            self.perm(SWAMP, self.a)
        self.assertTrue(self.game.activate_ability(self.a, bank, 0))
        self.assertEqual(len([x for x in self.a.creatures if "Pilot" in x.card.subtypes]), 2)
        self.assertEqual(len([x for x in self.a.battlefield if x.card.token_kind == "treasure"]), 2)

    def test_unsupported_qualifiers_stay_visible(self):
        for text in ["The first face-down creature spell you cast each turn costs {3} less to cast.",
                     "The first creature spell you cast each turn costs {2} less to cast and can be cast as though "
                     "it had flash.",
                     "{T}: Add {R}{G}. Spend this mana only to activate abilities of artifacts.",
                     "{T}: Add {R}{R}. Spend this mana only to cast spells from your graveyard."]:
            parsed = card("Unknown qualifier", types="Artifact", text=text)
            self.assertTrue(parsed.unsupported)
