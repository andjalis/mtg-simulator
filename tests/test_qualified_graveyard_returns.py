"""#328: qualified graveyard targets, resolution choices, and combat entry."""
import dataclasses
import unittest

from mtgsim.cards import Effect
from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, ISLAND, card

BIG = card("Return Giant", "{4}", "Creature — Giant", "", 4, 4)
ROCK = card("Return Rock", "{2}", "Artifact", "")
ETB = card("Return Healer", "{2}", "Creature — Cleric", "When ~ enters, you gain 3 life.", 2, 2)


class QualifiedReturns(Base):
    def resolve_ability(self, text, source, target):
        effects = parse_sentence(text)
        self.assertIsNotNone(effects)
        item = StackItem(self.a, effects, [target], source=source, kind="trigger")
        self.game.stack.append(item)
        self.game.resolve_top()
        return item

    def test_dynamic_bound_at_selection_and_resolution(self):
        source = self.perm(BEAR, self.a)
        self.a.graveyard.extend([BEAR, BIG, ROCK])
        text = "Return target creature card with mana value less than or equal to ~'s power from your graveyard to the battlefield."
        eff = parse_sentence(text)[0]
        with self.game.targeting(source):
            self.assertEqual(self.game.legal_targets(self.a, eff), [self.a.graveyard[0]])
            source.pump_p = 2
            self.assertEqual(self.game.legal_targets(self.a, eff), list(self.a.graveyard[:2]))
        target = self.a.graveyard[1]
        source.pump_p = 0
        item = self.resolve_ability(text, source, target)
        self.assertFalse(item.resolved)
        self.assertIn(target, self.a.graveyard)

    def test_dynamic_exact_boundary_returns_and_fires_etb(self):
        source = self.perm(BEAR, self.a)
        self.a.graveyard.append(ETB)
        self.resolve_ability("Return target creature card with mana value less than or equal to ~'s power from your graveyard to the battlefield.",
                             source, self.a.graveyard[0])
        self.game.settle()
        self.assertEqual([p.card.name for p in self.a.creatures], [BEAR.name, ETB.name])
        self.assertEqual(self.a.life, 23)

    def test_negative_source_bound_does_not_admit_zero_mana_creature(self):
        source = self.perm(BEAR, self.a)
        source.pump_p = -3
        self.a.graveyard.append(card("Free Body", "", "Creature", "", 1, 1))
        eff = parse_sentence("Return target creature card with mana value less than or equal to ~'s power from your graveyard to the battlefield.")[0]
        with self.game.targeting(source):
            self.assertEqual(self.game.legal_targets(self.a, eff), [])
        self.assertEqual(self.game.legal_targets(self.a, eff), [])  # no source is not a zero bound

    def test_numeric_strict_and_equal_thresholds(self):
        self.a.graveyard.extend([BEAR, BIG, ROCK])
        for relation, expected in (("less than 4", [BEAR]), ("equal to 4", [BIG]),
                                   ("greater than 2", [BIG]), ("greater than or equal to 2", [BEAR, BIG])):
            eff = parse_sentence(f"Return target creature card with power {relation} from your graveyard to your hand.")[0]
            self.assertEqual([c.name for c in self.game.legal_targets(self.a, eff)], [c.name for c in expected])

    def test_strict_source_power_boundary_and_ai_choice(self):
        source = self.perm(BIG, self.a)
        self.a.graveyard.extend([BEAR, BIG, ROCK])
        eff = parse_sentence("Return target creature card with power less than ~'s power from your graveyard to the battlefield.")[0]
        with self.game.targeting(source):
            picked = self.a.ai.choose_target(self.game, self.a, eff)
        self.assertIs(picked, self.a.graveyard[0])

    def test_another_target_excludes_dead_source_but_not_same_named_copy(self):
        source = self.game.enter_battlefield(self.a, BIG)
        self.game.destroy(source)
        self.a.graveyard.append(BIG)
        eff = parse_sentence("Return another target creature card with mana value less than or equal to ~'s power from your graveyard to the battlefield.")[0]
        with self.game.targeting(source):
            self.assertEqual(self.game.legal_targets(self.a, eff), [self.a.graveyard[1]])
        optional = parse_sentence("Return up to one other target creature card from your graveyard to the battlefield.")[0]
        self.assertTrue(optional.data["optional_target"])
        with self.game.targeting(source):
            self.assertEqual(self.game.legal_targets(self.a, optional), [self.a.graveyard[1]])

    def test_empty_graveyard_wrong_type_and_illegal_target(self):
        spell = self.spell("Return target creature card with power 2 or less from your graveyard to the battlefield tapped and attacking.")
        eff = spell.spell_effects[0]
        self.assertEqual(self.game.legal_targets(self.a, eff), [])
        self.a.graveyard.extend([ROCK, BIG])
        self.assertEqual(self.game.legal_targets(self.a, eff), [])
        self.cast(spell, [self.a.graveyard[0]])
        self.assertEqual(self.a.battlefield, [])
        self.assertEqual(len(self.a.graveyard), 3)  # includes resolved instant

    def test_target_that_left_and_returned_is_not_replaced(self):
        spell = card("Return Spell", "", "Sorcery", "Return target creature card with power 2 or less from your graveyard to the battlefield tapped and attacking.")
        self.a.graveyard.extend([BEAR, BEAR])
        target, other = self.a.graveyard
        from mtgsim.counter_mechanics import protect_graveyard_targets
        effects = protect_graveyard_targets(self.game, spell.spell_effects, [target])
        self.game.stack.append(StackItem(self.a, effects, [target], card=spell))
        self.game.move_card(target, self.a.graveyard, self.a.hand)
        self.game.move_card(target, self.a.hand, self.a.graveyard)
        self.game.resolve_top()
        self.assertEqual(self.a.battlefield, [])
        self.assertTrue(any(c is other for c in self.a.graveyard))

    def test_stolen_creature_is_returned_to_its_owners_hand(self):
        stolen = self.perm(BEAR, self.b)
        self.b.battlefield.remove(stolen)
        stolen.controller = self.a
        self.a.battlefield.append(stolen)
        self.game.destroy(stolen)
        target = self.b.graveyard[0]
        self.cast(self.spell("Return target creature card with power equal to 2 from a graveyard to its owner's hand."), [target])
        self.assertTrue(any(c is target for c in self.b.hand))
        self.assertEqual(self.a.hand, [])

    def test_tapped_attacking_entry_etb_and_no_attack_trigger(self):
        entrant = dataclasses.replace(ETB, triggers=ETB.triggers + [
            dataclasses.replace(ETB.triggers[0], event="attacks", effects=[Effect("gain_life", 10)])])
        self.game.step = "declare_attackers"
        self.a.graveyard.append(entrant)
        self.cast(self.spell("Return target creature card with power 2 or less from your graveyard to the battlefield tapped and attacking."),
                  [self.a.graveyard[0]])
        self.game.settle()
        perm = self.a.creatures[0]
        self.assertTrue(perm.tapped)
        self.assertIn(perm, self.game.attackers)
        self.assertIs(self.game.attack_targets[perm], self.b)
        self.assertEqual(self.a.life, 23)

    def test_attacking_rider_outside_combat_or_on_opponents_turn(self):
        for active, step in ((0, "main1"), (1, "declare_attackers")):
            with self.subTest(active=active, step=step):
                self.game.active_idx, self.game.step = active, step
                self.a.graveyard.append(BEAR)
                self.cast(self.spell("Return target creature card with power 2 or less from your graveyard to the battlefield tapped and attacking."),
                          [self.a.graveyard[-1]])
                self.assertTrue(self.a.creatures[-1].tapped)
                self.assertNotIn(self.a.creatures[-1], self.game.attackers)

    def test_alternate_order_preserves_bounds_and_entry(self):
        self.a.graveyard.extend([BEAR, BIG])
        spell = self.spell("Return from your graveyard to the battlefield target creature card with mana value 2 or less tapped.")
        self.assertEqual(self.game.legal_targets(self.a, spell.spell_effects[0]), [self.a.graveyard[0]])
        self.cast(spell, [self.a.graveyard[0]])
        self.assertTrue(self.a.creatures[0].tapped)
        self.assertIn(BIG, self.a.graveyard)


class ResolutionChoices(Base):
    def test_choices_are_untargeted_and_can_see_cards_milled_during_resolution(self):
        spell = self.spell("Mill two cards. Then return up to two creature cards from your graveyard to your hand.")
        self.assertTrue(all(e.target == "none" for e in spell.spell_effects))
        self.a.library = [BEAR, ETB]
        self.cast(spell)
        self.assertCountEqual([c.name for c in self.a.hand], [BEAR.name, ETB.name])

    def test_empty_and_wrong_type_choices_do_nothing(self):
        spell = self.spell("Return up to two creature cards from your graveyard to your hand.")
        self.cast(spell)
        self.a.graveyard.append(ROCK)
        self.cast(spell)
        self.assertEqual(self.a.hand, [])
        self.assertIn(ROCK, self.a.graveyard)

    def test_choices_never_use_opponents_graveyard(self):
        self.b.graveyard.append(BIG)
        self.a.graveyard.extend([BEAR, ETB])
        self.cast(self.spell("You return up to two creature cards from your graveyard to your hand."))
        self.assertCountEqual([c.name for c in self.a.hand], [BEAR.name, ETB.name])
        self.assertEqual([c.name for c in self.b.graveyard], [BIG.name])

    def test_optional_decline_is_honored(self):
        self.a.graveyard.append(BEAR)
        self.a.ai.choose_dig = lambda *args: []
        self.cast(self.spell("Return up to two creature cards from your graveyard to your hand."))
        self.assertEqual(self.a.hand, [])
        self.assertIn(BEAR, self.a.graveyard)

    def test_mandatory_choice_returns_available_cards(self):
        self.a.graveyard.append(BEAR)
        self.a.ai.choose_dig = lambda *args: []
        self.cast(self.spell("Return two creature cards with power equal to 2 from your graveyard to your hand."))
        self.assertEqual([c.name for c in self.a.hand], [BEAR.name])

    def test_invalid_duplicate_and_extra_choices_are_filtered(self):
        self.a.graveyard.extend([BEAR, BEAR, ETB])
        first, second, third = self.a.graveyard
        self.a.ai.choose_dig = lambda *args: [ROCK, first, first, second, third]
        self.cast(self.spell("Return up to two creature cards from your graveyard to your hand."))
        self.assertEqual(self.a.hand, [first, second])
        self.assertTrue(any(c is third for c in self.a.graveyard))

    def test_qualified_choice_enters_tapped_and_fires_etb(self):
        self.a.graveyard.extend([ETB, BIG, ROCK])
        self.cast(self.spell("Return up to two creature cards with power 2 or less from your graveyard to the battlefield tapped."))
        self.game.settle()
        self.assertEqual([p.card.name for p in self.a.creatures], [ETB.name])
        self.assertTrue(self.a.creatures[0].tapped)
        self.assertEqual(self.a.life, 23)
        self.assertIn(BIG, self.a.graveyard)

    def test_instant_and_or_sorcery_is_a_single_choice_pool(self):
        instant = card("Return Instant", "{U}", "Instant", "Draw a card.")
        sorcery = card("Return Sorcery", "{U}", "Sorcery", "Draw a card.")
        self.a.graveyard.extend([instant, sorcery, BEAR])
        self.cast(self.spell("Return up to two instant and/or sorcery cards from your graveyard to your hand."))
        self.assertCountEqual([c.name for c in self.a.hand], [instant.name, sorcery.name])
        self.assertIn(BEAR, self.a.graveyard)

    def test_ai_casts_choice_spell_with_legal_cards(self):
        self.a.graveyard.extend([BIG, BEAR, ROCK])
        spell = card("Choice Spell", "{U}", "Sorcery", "Return up to two creature cards from your graveyard to your hand.")
        self.perm(ISLAND, self.a)
        self.a.hand = [spell]
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand)
        self.assertIn(BIG, self.a.hand)
        self.assertIn(BEAR, self.a.hand)
        self.assertIn(ROCK, self.a.graveyard)

    def test_ai_holds_choice_spell_without_eligible_cards(self):
        spell = card("Choice Spell", "{U}", "Sorcery", "Return up to two creature cards from your graveyard to your hand.")
        self.a.graveyard.append(ROCK)
        self.perm(ISLAND, self.a)
        self.a.hand = [spell]
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn(spell, self.a.hand)


class Refusals(unittest.TestCase):
    def test_unsupported_semantics_stay_visible(self):
        for text in (
            "Return target creature card with mana value less than X from your graveyard to the battlefield.",
            "Return target creature card with mana value less than or equal to its power from your graveyard to the battlefield.",
            "Return target creature card with lesser toughness from your graveyard to your hand.",
            "Return up to two creature cards at random from your graveyard to your hand.",
            "Return a nonland card of an opponent's choice from your graveyard to your hand.",
            "Return up to two creature cards of that type from your graveyard to the battlefield.",
            "Return target creature card from your graveyard to the battlefield tapped and attacking with a shield counter on it.",
            "Return target artifact card from your graveyard to the battlefield tapped and attacking.",
            "Return target creature card from your graveyard to your hand tapped and attacking.",
            "Return two creature card from your graveyard to your hand.",
            "Return a creature cards from your graveyard to your hand.",
            "Return from your graveyard to the battlefield any number of target creature cards that each have a different mana value X or less.",
            "For each color, return up to one target card of that color from your graveyard to your hand.",
            "Return up to one creature card from your graveyard to your hand until end of turn.",
        ):
            with self.subTest(text=text):
                self.assertIsNone(parse_sentence(text))

    @unittest.skipUnless(DB_FILE.exists(), "card database not built")
    def test_real_cards_and_dependency_bound_residuals(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        self.addCleanup(db._all.close)
        for name in ("Alesha, Who Laughs at Fate", "Alesha, Who Smiles at Death", "Another Chance", "Bond of Insight", "Unseal the Necropolis"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, "full", (name, row.ignored))
        for name in ("Aether Rift", "Agadeem's Awakening", "All Suns' Dawn"):
            self.assertTrue(card_coverage(db.get(name)).ignored, name)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealAbilities(Base):
    def setUp(self):
        super().setUp()
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)
        self.addCleanup(self.db._all.close)

    def test_alesha_raid_checks_attack_history_and_current_power(self):
        source = self.game.enter_battlefield(self.a, self.db.get("Alesha, Who Laughs at Fate"))
        self.a.graveyard.append(BIG)
        self.game.step = "end_step"
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertIn(BIG, self.a.graveyard)
        self.a.attacked_with = 1
        source.counters["+1/+1"] = 2  # printed power 2, now exactly the four-mana boundary
        self.game.fire(self.a, "end_step")
        self.game.settle()
        self.assertIn(BIG.name, [p.card.name for p in self.a.creatures])

    def test_alesha_payment_gate_controls_attacking_return(self):
        source = self.game.enter_battlefield(self.a, self.db.get("Alesha, Who Smiles at Death"))
        self.a.graveyard.append(ETB)
        self.game.step = "declare_attackers"
        effects = source.card.triggers[0].effects
        self.game.stack.append(StackItem(self.a, effects, [None, self.a.graveyard[0]], source=source, kind="trigger"))
        self.game.resolve_top()
        self.assertIn(ETB, self.a.graveyard)
        plains = self.db.get("Plains")
        self.perm(plains, self.a)
        self.perm(plains, self.a)
        self.game.stack.append(StackItem(self.a, effects, [None, self.a.graveyard[0]], source=source, kind="trigger"))
        self.game.resolve_top()
        self.game.settle()
        returned = next(p for p in self.a.creatures if p.card.name == ETB.name)
        self.assertTrue(returned.tapped)
        self.assertIn(returned, self.game.attackers)
        self.assertEqual(self.a.life, 23)

    def test_gurgling_anointer_uses_last_known_power(self):
        source = self.game.enter_battlefield(self.a, self.db.get("Gurgling Anointer"))
        self.a.graveyard.append(BIG)
        source.counters["+1/+1"] = 4  # printed power 0
        self.game.destroy(source)
        self.game.settle()
        self.assertIn(BIG.name, [p.card.name for p in self.a.creatures])
        self.assertIn(source.front, self.a.graveyard)

    def test_entry_lock_preserves_graveyard_card_and_identity(self):
        self.game.enter_battlefield(self.b, self.db.get("Grafdigger's Cage"))
        self.a.graveyard.append(ETB)
        target = self.a.graveyard[0]
        generation = target.generation
        self.cast(self.spell("Return target creature card with power 2 or less from your graveyard to the battlefield tapped and attacking."),
                  [target])
        self.game.settle()
        self.assertIs(self.a.graveyard[0], target)
        self.assertEqual(target.generation, generation)
        self.assertEqual(self.a.creatures, [])
        self.assertEqual(self.a.life, 20)


if __name__ == "__main__":
    unittest.main()
