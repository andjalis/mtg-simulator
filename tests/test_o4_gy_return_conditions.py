"""Conditional graveyard self-return: trigger timing, costs and entry riders."""
from mtgsim import graveyard
from tests.test_templates import Base, BEAR, MOUNTAIN, SWAMP, card


def phoenix(name, condition, event="At the beginning of combat on your turn", body=None):
    body = body or "return this card from your graveyard to the battlefield."
    return card(name, "{3}{R}", "Creature — Phoenix", f"Flying, haste\n{event}, if {condition}, {body}", 3, 2)


ARCLIGHT = phoenix("Arclight Phoenix", "you've cast three or more instant and sorcery spells this turn")
DARKLIGHT = phoenix("Darklight Phoenix", "two or more creatures died this turn")
GHOUL = phoenix("Silversmote Ghoul", "you gained 3 or more life this turn", "At the beginning of your end step",
                "return this card from your graveyard to the battlefield tapped.")
FLAMEWAKE = phoenix("Flamewake Phoenix", "you control a creature with power 4 or greater", body=
                    "you may pay {R}. If you do, return this card from your graveyard to the battlefield.")
VENGEVINE = phoenix("Vengevine", "it's the second creature spell you cast this turn", "Whenever you cast a spell",
                   "you may return this card from your graveyard to the battlefield.")
CHAMPION = card("Bloodsoaked Champion", "{B}", text="Raid — {1}{B}: Return this card from your graveyard to the "
                "battlefield. Activate only if you attacked this turn.", power=2, toughness=1)
CONSCRIPT = card("Cult Conscript", "{B}", text="This creature enters tapped.\n{1}{B}: Return this card from your "
                 "graveyard to the battlefield. Activate only if a non-Skeleton creature died under your control "
                 "this turn.", power=2, toughness=1)
HAUNT = card("Haunt of the Dead Marshes", "{B}", text="{2}{B}: Return this card from your graveyard to the "
             "battlefield tapped. Activate only if you control a legendary creature.", power=1, toughness=1)
KULDOTHA = card("Kuldotha Phoenix", "{2}{R}{R}{R}", text="Flying, haste\nMetalcraft — {4}: Return this card from "
                "your graveyard to the battlefield. Activate only during your upkeep and only if you control "
                "three or more artifacts.", power=4, toughness=4)
PUPPETS = card("Coffin Puppets", "{3}{B}{B}", text="Sacrifice two lands: Return this card from your graveyard to "
               "the battlefield. Activate only during your upkeep and only if you control a Swamp.", power=3, toughness=3)
CHICK = card("Phoenix Chick", "{R}", text="Flying, haste\nWhenever you attack with three or more creatures, you "
             "may pay {R}{R}. If you do, return this card from your graveyard to the battlefield tapped and "
             "attacking with a +1/+1 counter on it.", power=1, toughness=1)
WARCRY = card("Warcry Phoenix", "{3}{R}", text="Flying, haste\nWhenever you attack with three or more creatures, "
              "you may pay {2}{R}. If you do, return this card from your graveyard to the battlefield tapped and "
              "attacking.", power=2, toughness=2)
WOLFBAT = card("Wolfbat", "{B}", text="Flying\nWhenever you draw your second card each turn, you may pay {B}. "
               "If you do, return this card from your graveyard to the battlefield with a finality counter on it.",
               power=1, toughness=1)
CANTRIP = card("Test spell", "{0}", "Instant", "You gain 1 life.")
FREE_CREATURE = card("Test creature", "{0}", power=1, toughness=1)
BIG = card("Big creature", "{0}", power=4, toughness=4)


class GraveyardReturnConditions(Base):
    def put_in_graveyard(self, c):
        self.a.graveyard.append(c)
        return self.a.graveyard[-1]

    def cast(self, c, player=None):
        player = player or self.a
        player.hand.append(c)
        self.assertTrue(self.game.cast(player, player.hand[-1]))

    def fire(self, event):
        self.game.fire(self.a, event)
        self.game.settle()

    def mana(self, land=SWAMP, n=4):
        return [self.perm(land, self.a) for _ in range(n)]

    def test_supported_templates(self):
        for c in (ARCLIGHT, DARKLIGHT, GHOUL, FLAMEWAKE, VENGEVINE, CHAMPION, CONSCRIPT, HAUNT,
                  KULDOTHA, PUPPETS, CHICK, WARCRY, WOLFBAT):
            with self.subTest(card=c.name):
                self.assertEqual(c.unsupported, [])
                self.assertTrue(c.gy_triggers or c.gy_activated)
                self.assertEqual(c.triggers, [])

    def test_arclight_three_real_spells_then_combat_and_haste(self):
        self.put_in_graveyard(ARCLIGHT)
        for _ in range(3):
            self.cast(CANTRIP)
        self.a.ai.choose_attackers = lambda g, me, opp: list(me.creatures)
        self.game.combat(self.a, self.b)
        returned = self.a.creatures[0]
        self.assertEqual(returned.card.name, ARCLIGHT.name)
        self.assertTrue(returned.has("haste"))
        self.assertIn(returned, self.game.attackers)
        self.assertEqual(self.b.life, 17)

    def test_arclight_counts_only_own_instants_and_sorceries_and_current_turn(self):
        self.put_in_graveyard(ARCLIGHT)
        self.cast(CANTRIP)
        self.cast(CANTRIP)
        self.cast(FREE_CREATURE)
        self.cast(CANTRIP, self.b)
        self.game.fire(self.a, "begin_combat")
        self.assertFalse(self.game.pending)
        self.cast(CANTRIP)
        self.game.turn += 2
        self.game.fire(self.a, "begin_combat")
        self.assertFalse(self.game.pending)
        self.assertIn(ARCLIGHT, self.a.graveyard)

    def test_false_at_trigger_does_not_trigger_later(self):
        self.put_in_graveyard(GHOUL)
        self.game.change_life(self.a, 2, "test gain")
        self.game.fire(self.a, "end_step")
        self.assertFalse(self.game.pending)
        self.game.change_life(self.a, 1, "test gain")
        self.game.settle()
        self.assertIn(GHOUL, self.a.graveyard)
        self.fire("end_step")
        self.assertTrue(self.a.creatures[0].tapped)

    def test_intervening_if_rechecked_before_payment_at_resolution(self):
        self.put_in_graveyard(FLAMEWAKE)
        land = self.mana(MOUNTAIN, 1)[0]
        big = self.perm(BIG, self.a)
        self.game.fire(self.a, "begin_combat")
        self.assertEqual(len(self.game.pending), 1)
        self.game.flush_triggers()
        self.game.dies(big)
        self.game.resolve_top()
        self.assertIn(FLAMEWAKE, self.a.graveyard)
        self.assertFalse(land.tapped)
        self.assertFalse(self.game.stack)

    def test_flamewake_condition_and_payment(self):
        self.put_in_graveyard(FLAMEWAKE)
        self.mana(MOUNTAIN, 1)
        self.game.fire(self.a, "begin_combat")
        self.assertFalse(self.game.pending)
        self.perm(BIG, self.a)
        self.fire("begin_combat")
        self.assertNotIn(FLAMEWAKE, self.a.graveyard)
        self.assertTrue(any(x.card.name == FLAMEWAKE.name for x in self.a.creatures))

    def test_darklight_counts_deaths_across_both_players_and_resets(self):
        self.put_in_graveyard(DARKLIGHT)
        self.game.dies(self.perm(BEAR, self.a))
        self.game.fire(self.a, "begin_combat")
        self.assertFalse(self.game.pending)
        self.game.dies(self.perm(BEAR, self.b))
        self.fire("begin_combat")
        self.assertNotIn(DARKLIGHT, self.a.graveyard)
        self.game.dies(self.a.creatures[0])
        self.game.turn += 2
        self.game.fire(self.a, "begin_combat")
        self.assertFalse(self.game.pending)

    def test_entry_and_death_condition_uses_real_events(self):
        perennial = phoenix("Perennial return", "a creature entered and a creature died this turn",
                            "At the beginning of your end step",
                            "return this card from your graveyard to the battlefield tapped.")
        self.put_in_graveyard(perennial)
        self.game.fire(self.a, "end_step")
        self.assertFalse(self.game.pending)
        creature = self.game.enter_battlefield(self.b, BEAR)
        self.game.fire(self.a, "end_step")
        self.assertFalse(self.game.pending)
        self.game.dies(creature)
        self.fire("end_step")
        self.assertEqual(self.a.creatures[0].card.name, perennial.name)
        self.assertTrue(self.a.creatures[0].tapped)

    def test_vengevine_counts_creatures_not_total_spells(self):
        self.put_in_graveyard(VENGEVINE)
        self.cast(CANTRIP)
        self.cast(FREE_CREATURE)
        self.assertIn(VENGEVINE, self.a.graveyard)
        self.cast(CANTRIP)
        self.assertIn(VENGEVINE, self.a.graveyard)
        self.cast(FREE_CREATURE)
        self.assertNotIn(VENGEVINE, self.a.graveyard)
        self.assertTrue(any(x.card.name == VENGEVINE.name for x in self.a.creatures))

    def test_vengevine_second_spell_is_historical_when_third_is_cast_in_response(self):
        self.put_in_graveyard(VENGEVINE)
        self.cast(FREE_CREATURE)
        self.game._priority_depth += 1
        try:
            self.cast(FREE_CREATURE)
            self.game.flush_triggers()
            self.cast(FREE_CREATURE)
        finally:
            self.game._priority_depth -= 1
        self.game.settle()
        self.assertNotIn(VENGEVINE, self.a.graveyard)

    def test_card_must_still_be_same_graveyard_object(self):
        source = self.put_in_graveyard(GHOUL)
        self.game.change_life(self.a, 3, "test gain")
        self.game.fire(self.a, "end_step")
        self.game.flush_triggers()
        self.a.graveyard.remove(source)
        self.a.hand.append(source)
        self.a.hand.remove(source)
        self.a.graveyard.append(source)
        self.game.resolve_top()
        self.assertIn(source, self.a.graveyard)
        self.assertFalse(self.a.creatures)

    def test_no_graveyard_card_no_trigger(self):
        self.perm(GHOUL, self.a)
        self.game.change_life(self.a, 3, "test gain")
        self.game.fire(self.a, "end_step")
        self.assertFalse(self.game.pending)

    def test_raid_activation_checks_condition_and_zone(self):
        source = self.put_in_graveyard(CHAMPION)
        self.mana(n=2)
        self.assertFalse(graveyard.activate(self.game, self.a, source, 0))
        self.a.attacked_with = 1
        self.assertTrue(graveyard.activate(self.game, self.a, source, 0))
        self.assertFalse(graveyard.can_activate(self.game, self.a, source, 0))
        self.assertEqual(self.a.creatures[0].card.name, CHAMPION.name)

    def test_legendary_creature_requirement(self):
        source = self.put_in_graveyard(HAUNT)
        self.mana(n=3)
        self.perm(card("Legendary relic", types="Legendary Artifact"), self.a)
        self.assertFalse(graveyard.can_activate(self.game, self.a, source, 0))
        self.perm(card("Legend", types="Legendary Creature", power=2, toughness=2), self.a)
        self.assertTrue(graveyard.activate(self.game, self.a, source, 0))
        self.assertTrue(next(x for x in self.a.creatures if x.card.name == HAUNT.name).tapped)

    def test_activation_condition_is_not_rechecked_on_resolution(self):
        source = self.put_in_graveyard(HAUNT)
        self.mana(n=3)
        legend = self.perm(card("Legend", types="Legendary Creature", power=2, toughness=2), self.a)
        self.game._priority_depth += 1
        try:
            self.assertTrue(graveyard.activate(self.game, self.a, source, 0))
            self.game.dies(legend)
        finally:
            self.game._priority_depth -= 1
        self.game.settle()
        self.assertEqual(self.a.creatures[0].card.name, HAUNT.name)

    def test_conscript_requires_our_non_skeleton_death_this_turn(self):
        source = self.put_in_graveyard(CONSCRIPT)
        self.mana(n=2)
        skeleton = card("Skeleton", types="Creature — Skeleton", power=1, toughness=1)
        self.game.dies(self.perm(skeleton, self.a))
        self.game.dies(self.perm(BEAR, self.b))
        self.assertFalse(graveyard.can_activate(self.game, self.a, source, 0))
        self.game.dies(self.perm(BEAR, self.a))
        self.assertTrue(graveyard.can_activate(self.game, self.a, source, 0))
        self.game.turn += 2
        self.assertFalse(graveyard.can_activate(self.game, self.a, source, 0))

    def test_metalcraft_and_upkeep_activation(self):
        source = self.put_in_graveyard(KULDOTHA)
        self.mana(n=4)
        relic = card("Relic", types="Artifact")
        for _ in range(2):
            self.perm(relic, self.a)
        self.game.step = "upkeep"
        self.assertFalse(graveyard.can_activate(self.game, self.a, source, 0))
        self.perm(relic, self.a)
        self.game.step = "main1"
        self.assertFalse(graveyard.can_activate(self.game, self.a, source, 0))
        self.game.step = "upkeep"
        self.game.active_idx = 1
        self.assertFalse(graveyard.can_activate(self.game, self.a, source, 0))
        self.game.active_idx = 0
        self.assertTrue(graveyard.activate(self.game, self.a, source, 0))
        self.assertEqual(self.a.creatures[0].card.name, KULDOTHA.name)

    def test_coffin_puppets_pays_two_lands_with_swamp_upkeep_restriction(self):
        source = self.put_in_graveyard(PUPPETS)
        self.game.step = "upkeep"
        self.mana(MOUNTAIN, 2)
        self.assertFalse(graveyard.can_activate(self.game, self.a, source, 0))
        self.mana(SWAMP, 1)
        self.assertTrue(graveyard.activate(self.game, self.a, source, 0))
        self.assertEqual(sum(x.card.is_land for x in self.a.battlefield), 1)
        self.assertEqual(self.a.creatures[0].card.name, PUPPETS.name)
        self.assertEqual(sum(c.is_land for c in self.a.graveyard), 2)

    def test_phoenix_chick_enters_attacking_with_counter(self):
        self.put_in_graveyard(CHICK)
        self.mana(MOUNTAIN, 2)
        attackers = [self.perm(BEAR, self.a) for _ in range(3)]
        self.a.ai.choose_attackers = lambda g, me, opp: attackers
        self.game.combat(self.a, self.b)
        returned = next(x for x in self.a.creatures if x.card.name == CHICK.name)
        self.assertTrue(returned.tapped)
        self.assertEqual(returned.p1, 1)
        self.assertIn(returned, self.game.attackers)
        self.assertEqual(self.b.life, 12)

    def test_attack_threshold_and_return_outside_combat(self):
        self.put_in_graveyard(WARCRY)
        self.mana(MOUNTAIN, 3)
        self.a.attacked_with = 2
        self.game.fire(self.a, "you_attack")
        self.assertFalse(self.game.pending)
        self.a.attacked_with = 3
        self.fire("you_attack")
        returned = self.a.creatures[0]
        self.assertTrue(returned.tapped)
        self.assertNotIn(returned, self.game.attackers)

    def test_attack_threshold_also_applies_to_battlefield_listeners(self):
        listener = card("Attack listener", text="Whenever you attack with three or more creatures, draw a card.",
                        power=2, toughness=2)
        self.assertFalse(listener.unsupported)
        self.perm(listener, self.a)
        self.a.attacked_with = 2
        self.game.fire(self.a, "you_attack")
        self.assertFalse(self.game.pending)
        self.a.attacked_with = 3
        self.fire("you_attack")
        self.assertEqual(len(self.a.hand), 1)

    def test_shared_condition_on_battlefield_trigger_checks_both_times(self):
        listener = card("Metalcraft listener", text="At the beginning of combat on your turn, if you control "
                        "three or more artifacts, draw a card.", power=2, toughness=2)
        self.assertFalse(listener.unsupported)
        self.perm(listener, self.a)
        self.game.fire(self.a, "begin_combat")
        self.assertFalse(self.game.pending)
        relic = card("Relic", types="Artifact")
        artifacts = [self.perm(relic, self.a) for _ in range(3)]
        self.game.settle()
        self.assertFalse(self.a.hand)
        self.game.fire(self.a, "begin_combat")
        self.game.flush_triggers()
        self.game.sacrifice(artifacts[0])
        self.game.settle()
        self.assertFalse(self.a.hand)
        self.perm(relic, self.a)
        self.fire("begin_combat")
        self.assertEqual(len(self.a.hand), 1)

    def test_shared_condition_preserves_you_create_wording(self):
        listener = card("Token listener", text="At the beginning of your end step, if you attacked this turn, "
                        "you create a Treasure token.", power=2, toughness=2)
        self.assertFalse(listener.unsupported)
        self.perm(listener, self.a)
        self.game.fire(self.a, "end_step")
        self.assertFalse(self.game.pending)
        self.a.attacked_with = 1
        self.fire("end_step")
        self.assertTrue(any(x.card.token_kind == "treasure" for x in self.a.battlefield))

    def test_finality_rider_after_pay_gate(self):
        self.put_in_graveyard(WOLFBAT)
        self.fire("draw_second")
        self.assertIn(WOLFBAT, self.a.graveyard)
        self.mana(n=1)
        self.fire("draw_second")
        returned = self.a.creatures[0]
        self.assertEqual(returned.counters.get("finality"), 1)
        self.game.sacrifice(returned)
        self.assertFalse(self.a.graveyard)
        self.assertEqual(self.a.exile[0].name, WOLFBAT.name)

    def test_out_of_scope_conditions_and_replacement_stay_unsupported(self):
        for text in ["At the beginning of combat on your turn, if you control three or more artifacts, choose one —",
                     "At the beginning of your upkeep, if it is night, return this card from your graveyard "
                     "to the battlefield.",
                     "{B}: Return this card from your graveyard to the battlefield. It perpetually gets +1/+1.",
                     "{B}: Return this card from your graveyard to the battlefield. If it would leave the "
                     "battlefield, exile it instead."]:
            c = card("Unsupported return", "{B}", text=text, power=1, toughness=1)
            self.assertTrue(c.unsupported)
            self.assertFalse(c.gy_triggers or c.gy_activated)
