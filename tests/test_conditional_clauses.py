"""Compositional conditions and trigger timing, using the offline Oracle database."""
import random
import unittest

from mtgsim import conditions
from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.cards import Effect, _parse_effects, card_from_scryfall, make_token
from mtgsim.engine import Game, Permanent, Player, StackItem

DB = CardDB(offline=True)


def card(text, types="Instant", name="Conditional Test"):
    return card_from_scryfall({"name": name, "mana_cost": "", "cmc": 0, "type_line": types,
                              "oracle_text": text, "power": "2", "toughness": "2"})


@unittest.skipUnless(ALL_CARDS.exists(), "build the offline card database")
class ConditionalClauses(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], HeuristicAI())
        self.b = Player("b", [], HeuristicAI())
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.game.turn, self.game.step = 1, "main1"
        for p in self.game.players:
            p.library = [DB.get("Island")] * 30

    def perm(self, name, p=None):
        p = p or self.a
        c = DB.get(name) if isinstance(name, str) else name
        perm = Permanent(c, p)
        perm.sick = False
        p.battlefield.append(perm)
        return perm

    def run_effects(self, text, source=None, targets=None):
        effects, bad = _parse_effects(text)
        self.assertEqual(bad, [])
        if targets is None:
            targets = self.game.auto_targets(self.a, effects, source)
        item = StackItem(self.a, effects, targets, source=source)
        self.game.stack.append(item)
        self.game.resolve_top()
        return item

    def test_real_cards_recognized_without_approximations(self):
        for name in ("Coati Scavenger", "Crypt Feaster", "Foot Mystic", "Malamet Veteran", "Stinging Cave Crawler",
                     "Tidecaller Mentor", "Insatiable Skittermaw", "Interceptor Mechan", "Kavaron Skywarden",
                     "Michelangelo, Game Master", "Donatello, Turtle Techie", "Dundoolin Weaver", "Starlit Soothsayer",
                     "Jem Lightfoote, Sky Explorer", "Ash, Party Crasher", "Belligerent of the Ball", "Feed the Cauldron",
                     "Demonic Counsel", "Withering Curse", "You're Not Alone", "Plunder the Trollshaws",
                     "Primal Witchstalker", "Faebloom Trick", "Yathan Roadwatcher", "Earthbender Ascension",
                     "Sun-Blessed Healer", "Shoreline Looter", "Moseo, Vein's New Dean"):
            with self.subTest(card=name):
                c = DB.get(name)
                self.assertEqual((c.unsupported, c.approximations), ([], []))

    def test_unknown_conditions_and_reflexive_actions_stay_visible(self):
        for text in ("If you control a creature with a hat, draw a card.",
                     "If you control a creature and the moon is blue, draw a card.",
                     "When you do, draw a card.",
                     "If you paid a secret cost, draw two cards instead."):
            with self.subTest(text=text):
                self.assertTrue(card(text).unsupported)
        self.assertTrue(DB.get("Eden, Seat of the Sanctum").unsupported)  # 'another' graveyard target needs identity
        # A previous paragraph with several effects needs an explicit replacement binding.
        self.assertTrue(card("You gain 2 life. Draw a card.\nIf it's your turn, draw two cards instead.").unsupported)

    def test_graveyard_type_count_counts_distinct_card_types(self):
        self.a.graveyard = [DB.get("Ornithopter"), DB.get("Ornithopter"), DB.get("Island")]
        cond = conditions.parse("there are three or more card types among cards in your graveyard")
        self.assertTrue(conditions.evaluate(self.game, self.a, cond))
        self.assertFalse(conditions.evaluate(self.game, self.a, conditions.parse(
            "there are four or more card types among cards in your graveyard")))
        self.a.graveyard.append(DB.get("Lightning Bolt"))
        self.assertTrue(conditions.evaluate(self.game, self.a, conditions.parse(
            "there are four or more card types among cards in your graveyard")))
        self.assertFalse(conditions.evaluate(self.game, self.a, conditions.parse(
            "there are four or more permanent types among cards in your graveyard")))

    def test_control_grammar_excludes_source_and_counts_attacking_tapped(self):
        src = self.perm("Grizzly Bears")
        item = StackItem(self.a, [], [], source=src)
        cond = conditions.parse("you control another creature")
        self.assertFalse(conditions.evaluate(self.game, self.a, cond, item))
        other = self.perm("Grizzly Bears")
        self.assertTrue(conditions.evaluate(self.game, self.a, cond, item))
        self.game.attackers = [src, other]
        other.tapped = True
        for phrase, expected in (("you control two or more attacking creatures", True),
                                 ("you control two or more tapped creatures", False),
                                 ("you control a tapped creature", True)):
            self.assertEqual(conditions.evaluate(self.game, self.a, conditions.parse(phrase), item), expected)
        self.perm("Plains")
        self.assertTrue(conditions.evaluate(self.game, self.a, conditions.parse("you control a Plains"), item))

    def test_life_hand_x_turn_and_boolean_conditions(self):
        self.a.life = 5
        self.a.hand = [DB.get("Island")]
        item = StackItem(self.a, [], [])
        item.x = 3
        for phrase, expected in (("your life total is 5 or less", True), ("you have two or fewer cards in hand", True),
                                 ("you have no cards in hand", False), ("X is 3 or greater", True),
                                 ("it's your turn", True), ("it's not your turn", False),
                                 ("you gained or lost life this turn", True),
                                 ("it's your turn and you have no cards in hand", False),
                                 ("it's your turn or you have no cards in hand", True)):
            with self.subTest(condition=phrase):
                cond = conditions.parse(phrase)
                self.assertTrue(cond)
                self.assertEqual(conditions.evaluate(self.game, self.a, cond, item), expected)

    def test_intervening_if_false_does_not_trigger_or_consume_once(self):
        c = card("At the beginning of your end step, if you control an artifact, draw a card. "
                 "This ability triggers only once each turn.", "Enchantment")
        src = self.perm(c)
        self.game.fire(self.a, "end_step")
        self.assertEqual(self.game.pending, [])
        self.perm("Ornithopter")
        self.game.fire(self.a, "end_step")
        self.assertEqual(len(self.game.pending), 1)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)
        self.game.fire(self.a, "end_step")
        self.assertEqual(self.game.pending, [])
        self.assertTrue(src.ability_turns)

    def test_intervening_if_rechecked_at_resolution(self):
        src = self.perm("Stinging Cave Crawler")
        self.a.graveyard = [DB.get("Island")] * 4
        self.game.fire(self.a, "attacks", src)
        self.game.flush_triggers()
        self.a.graveyard.pop()
        self.game.resolve_top()
        self.assertEqual((len(self.a.hand), self.a.life), (0, 20))

    def test_intervening_if_checked_once_before_all_effects(self):
        src = self.perm(card("At the beginning of your end step, if you have no cards in hand, draw two cards. "
                             "You gain 3 life.", "Enchantment"))
        self.game.fire(self.a, "end_step", src)
        self.game.settle()
        self.assertEqual((len(self.a.hand), self.a.life), (2, 23))

    def test_conditional_instruction_checked_once_before_compound_effect(self):
        self.a.life = 5
        self.run_effects("If your life total is 5 or less, you gain 3 life and draw two cards.")
        self.assertEqual((self.a.life, len(self.a.hand)), (8, 2))

    def test_trailing_if_is_resolution_only(self):
        src = self.perm("Scalestorm Summoner")
        self.game.fire(self.a, "attacks", src)
        self.assertEqual(len(self.game.pending), 1)
        self.perm("Colossal Dreadmaw")
        self.game.settle()
        self.assertEqual(sum(x.card.is_token for x in self.a.creatures), 1)

    def test_replacement_branch_uses_original_target(self):
        victim = self.perm("Colossal Dreadmaw", self.b)
        self.perm(card("", "Artifact — Spacecraft"))
        spell = DB.get("Invasive Maneuvers")
        self.game.stack.append(StackItem(self.a, spell.spell_effects,
            [None, victim, None, None], card=spell))
        self.game.resolve_top()
        self.assertEqual(victim.damage, 5)

    def test_replacement_branch_snapshots_condition(self):
        self.a.life = 5
        self.run_effects("You gain 3 life. If your life total is 7 or more, draw two cards instead.")
        self.assertEqual((self.a.life, len(self.a.hand)), (8, 0))

    def test_real_replacement_wrath_does_not_apply_base_debuff(self):
        victim = self.perm("Darksteel Myr", self.b)
        self.a.life_gained_turn = 1
        spell = DB.get("Withering Curse")
        self.game.stack.append(StackItem(self.a, spell.spell_effects,
            self.game.auto_targets(self.a, spell.spell_effects), card=spell))
        self.game.resolve_top()
        self.assertIn(victim, self.b.battlefield)  # indestructible, not given -2/-2
        self.assertEqual(victim.toughness, 1)

    def test_delirium_search_replaces_subtype_search(self):
        self.a.library = [DB.get("Colossal Dreadmaw")]
        self.a.graveyard = [DB.get("Ornithopter"), DB.get("Island"), DB.get("Lightning Bolt")]
        spell = DB.get("Demonic Counsel")
        self.game.stack.append(StackItem(self.a, spell.spell_effects, [None] * len(spell.spell_effects), card=spell))
        self.game.resolve_top()
        self.assertEqual([c.name for c in self.a.hand], ["Colossal Dreadmaw"])

    def test_void_tracks_either_players_nonland_leave_but_not_land(self):
        src = self.perm("Insatiable Skittermaw")
        land = self.perm("Island", self.b)
        self.game.leave_battlefield(land, "hand")
        self.game.fire(self.a, "end_step", src)
        self.assertEqual(self.game.pending, [])
        other = self.perm("Ornithopter", self.b)
        self.game.leave_battlefield(other, "exile")
        self.game.fire(self.a, "end_step", src)
        self.game.settle()
        self.assertEqual(src.p1, 1)
        self.game.turn += 1
        self.game.fire(self.a, "end_step", src)
        self.assertEqual(self.game.pending, [])

    def test_celebration_counts_tokens_and_resets_on_opponents_turn(self):
        src = self.perm("Ash, Party Crasher")
        for _ in range(2):
            self.game.enter_battlefield(self.a, make_token("Food", 0, 0, kind="food", artifact=True))
        self.game.fire(self.a, "attacks", src)
        self.game.settle()
        self.assertEqual(src.p1, 1)
        self.game.turn += 1
        self.game.active_idx = 1
        self.game.fire(self.a, "attacks", src)
        self.assertEqual(self.game.pending, [])

    def test_no_hand_spell_condition_counts_cast_even_if_countered(self):
        src = self.perm("Jem Lightfoote, Sky Explorer")
        c = card("You gain 1 life.")
        self.a.hand = [c]
        self.assertTrue(self.game.cast(self.a, c))
        self.game.stack.clear()
        self.game.fire(self.a, "end_step", src)
        self.assertEqual(self.game.pending, [])
        self.game.turn += 1
        self.game.fire(self.a, "end_step", src)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_flashback_conditional_replacement_uses_cast_zone(self):
        spell = DB.get("Plunder the Trollshaws")
        self.a.graveyard = [spell]
        for _ in range(4):
            self.perm("Island")
        variant = next(c for c in self.game.spell_options(self.a) if self.game._origin(c)[1] == "flashback")
        self.assertTrue(self.game.cast(self.a, variant))
        self.game.settle()
        self.assertEqual(len(self.a.hand), 2)
        self.assertIn(spell, self.a.exile)

    def test_kicked_etb_flags_available_before_triggering(self):
        spell = DB.get("Sun-Blessed Healer")
        rock = DB.get("Ornithopter")
        self.a.hand, self.a.graveyard = [spell], [rock]
        for _ in range(4):
            self.perm("Plains")
        variant = next(c for c in self.game.spell_options(self.a) if self.game._origin(c)[1] == "kicker")
        self.assertTrue(self.game.cast(self.a, variant))
        self.game.settle()
        self.assertTrue(any(x.card.name == rock.name for x in self.a.battlefield))

    def test_reanimation_does_not_satisfy_cast_etb(self):
        src = self.game.enter_battlefield(self.a, DB.get("Yathan Roadwatcher"))
        self.assertFalse(src.was_cast)
        self.assertEqual(self.game.pending, [])

    def test_mill_reflexive_selects_card_after_milling_and_allows_response(self):
        bear = DB.get("Grizzly Bears")
        self.a.library = [bear] + [DB.get("Island")] * 3
        src = self.game.enter_battlefield(self.a, DB.get("Primal Witchstalker"))
        self.game.flush_triggers()
        self.game.resolve_top()
        self.assertEqual(len(self.game.pending), 1)
        self.assertEqual(len(self.a.graveyard), 4)
        self.game.flush_triggers()
        item = self.game.stack[-1]
        selected = item.targets[0]
        self.assertTrue(selected.card.is_land)
        self.a.graveyard.pop(selected.index())
        self.game.resolve_top()
        self.assertEqual(len([x for x in self.a.battlefield if x.card.is_land]), 0)
        self.assertIn(src, self.a.battlefield)

    def test_empty_mill_does_not_make_reflexive_trigger(self):
        self.a.library = []
        self.a.graveyard = [DB.get("Island")]
        self.game.enter_battlefield(self.a, DB.get("Primal Witchstalker"))
        self.game.flush_triggers()
        self.game.resolve_top()
        self.assertEqual(self.game.pending, [])

    def test_token_reflexive_chooses_targets_after_creating_tokens(self):
        spell = DB.get("Faebloom Trick")
        victim = self.perm("Grizzly Bears", self.b)
        self.game.stack.append(StackItem(self.a, spell.spell_effects, [None] * len(spell.spell_effects), card=spell))
        self.game.resolve_top()
        self.assertEqual(len(self.a.creatures), 2)
        self.assertFalse(victim.tapped)
        self.game.flush_triggers()
        self.assertEqual(self.game.stack[-1].targets, [victim])
        self.game.resolve_top()
        self.assertTrue(victim.tapped)

    def test_discard_reflexive_is_separate_and_failure_does_not_trigger(self):
        text = "You may discard a card. When you do, you gain 3 life. Draw a card."
        self.run_effects(text)
        self.assertEqual(self.game.pending, [])
        self.a.hand = [DB.get("Island")] * 4
        self.run_effects(text)
        self.assertEqual((self.a.life, len(self.a.hand)), (20, 3))
        self.assertEqual(len(self.game.pending), 1)
        self.game.settle()
        self.assertEqual((self.a.life, len(self.a.hand)), (23, 4))

    def test_pay_reflexive_success_and_failure(self):
        text = "You may pay {1}. When you do, draw two cards."
        self.run_effects(text)
        self.assertEqual(self.game.pending, [])
        self.perm("Island")
        self.run_effects(text)
        self.assertEqual(len(self.game.pending), 1)
        self.assertEqual(self.a.hand, [])
        self.game.settle()
        self.assertEqual(len(self.a.hand), 2)

    def test_sacrifice_reflexive_is_not_targeted_until_payment(self):
        src = self.perm(card("", "Enchantment"))
        text = "You may sacrifice another creature. When you do, return target creature card from your graveyard to your hand."
        self.run_effects(text, src)
        self.assertEqual(self.game.pending, [])
        victim = self.perm(make_token("Citizen", 1, 1))
        bear = DB.get("Grizzly Bears")
        self.a.graveyard = [bear]
        self.run_effects(text, src)
        self.assertNotIn(victim, self.a.battlefield)
        self.assertEqual(len(self.game.pending), 1)
        self.game.settle()
        self.assertEqual(self.a.hand, [bear])

    def test_life_payment_reflexive_requires_actual_payment(self):
        self.a.life = 1
        self.run_effects("You may pay 2 life. When you do, draw a card.")
        self.assertEqual(self.game.pending, [])
        self.a.life = 3
        self.run_effects("You may pay 2 life. When you do, draw a card.")
        self.assertEqual(self.a.life, 1)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_reflexive_intervening_counter_condition_checks_twice(self):
        src = self.perm("Earthbender Ascension")
        src.counters["quest"] = 3
        bear = self.perm("Grizzly Bears")
        self.game.fire(self.a, "land_enters")
        self.game.flush_triggers()
        self.game.resolve_top()
        self.assertEqual(src.counters["quest"], 4)
        self.assertEqual(len(self.game.pending), 1)
        self.game.flush_triggers()
        src.counters["quest"] = 2
        self.game.resolve_top()
        self.assertEqual(bear.p1, 0)
        self.assertFalse(bear.has("trample"))

    def test_unless_graveyard_threshold_changes_discard(self):
        src = self.perm("Shoreline Looter")
        self.a.graveyard = [DB.get("Island")] * 7
        self.game.fire(self.a, "combat_damage_player", src)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)
        self.a.graveyard = []
        self.game.fire(self.a, "combat_damage_player", src)
        self.game.settle()
        self.assertEqual(len(self.a.hand), 1)

    def test_life_based_graveyard_limit_binds_mana_value_not_card_count(self):
        src = self.perm("Moseo, Vein's New Dean")
        bear = DB.get("Grizzly Bears")
        self.a.graveyard = [bear]
        self.a.life_gained_turn = 2
        self.game.fire(self.a, "end_step", src)
        self.game.flush_triggers()
        item = self.game.stack[-1]
        self.assertEqual(len(item.targets), 1)
        self.assertEqual(item.targets[0].card, bear)
        self.game.resolve_top()
        self.assertEqual(len([p for p in self.a.creatures if p.card is bear]), 1)

    def test_etb_pronoun_binds_self_for_conditional_counter_instruction(self):
        self.a.life_gained_turn = 1
        src = self.game.enter_battlefield(self.a, DB.get("Old-Growth Educator"))
        self.game.settle()
        self.assertEqual(src.p1, 2)

    def test_bargain_and_gift_intervening_if_use_cast_flags_at_entry(self):
        for keyword, phrase, attr in (("Bargain", "it was bargained", "bargained"),
                                      ("Gift a card", "the gift was promised", "gifted")):
            c = card(keyword + "\nWhen ~ enters, if " + phrase + ", you gain 3 life.", "Enchantment")
            src = self.game.enter_battlefield(self.a, c)
            self.assertEqual(self.game.pending, [])
            cast_item = StackItem(self.a, [], [], card=c)
            setattr(cast_item, attr, True)
            self.game.enter_battlefield(self.a, c, cast_item=cast_item)
            self.assertEqual(len(self.game.pending), 1)
            self.game.settle()
        self.assertEqual(self.a.life, 26)

    def test_real_cast_only_mill_reflexive_resolves_after_spell_entry(self):
        c = DB.get("Yathan Roadwatcher")
        bear = DB.get("Grizzly Bears")
        self.a.library = [bear] + [DB.get("Island")] * 3
        self.a.hand = [c]
        for name in ("Plains", "Swamp", "Forest", "Forest"):
            self.perm(name)
        self.assertTrue(self.game.cast(self.a, c))
        self.game.settle()
        self.assertTrue(any(x.card is bear for x in self.a.creatures))

    def test_copied_permanent_was_not_cast(self):
        c = DB.get("Yathan Roadwatcher")
        copy = StackItem(self.a, [], [], card=c, kind="copy")
        self.game.stack.append(copy)
        self.game.resolve_top()
        self.assertEqual(self.game.pending, [])

    def test_successful_reflexive_counter_bonus_and_missing_source(self):
        src = self.perm("Earthbender Ascension")
        src.counters["quest"] = 3
        bear = self.perm("Grizzly Bears")
        self.game.fire(self.a, "land_enters")
        self.game.settle()
        self.assertEqual(bear.p1, 1)
        self.assertTrue(bear.has("trample"))
        self.game.fire(self.a, "land_enters")
        self.game.flush_triggers()
        self.game.leave_battlefield(src, "exile")
        self.game.resolve_top()
        self.assertEqual(self.game.pending, [])

    def test_conditional_mana_keeps_automatic_payment_gap_visible(self):
        c = DB.get("Raucous Audience")
        self.assertTrue(c.approximations)


if __name__ == "__main__":
    unittest.main()
