"""Copy exceptions that grant a quoted ability: 'except it has "{T}: Add {U}."' (#340 slice 5, copies.quoted_grant).
The quoted ability becomes a copiable value of the copy (rule 707.9a)."""
import dataclasses
import os
import random
import unittest

from mtgsim import copies
from mtgsim.ai import HeuristicAI
from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

LEGEND = card("Test Legend", "{3}{G}", "Legendary Creature — Elf Warrior", "Trample", 5, 4)
BEAR = card("Test Bear", "{1}{G}", "Creature — Bear", "", 2, 2)
LORD = card("Test Lord", "{2}{G}", "Creature — Elf", "When ~ enters, you gain 2 life.", 3, 3)
BOLT = card("Test Bolt", "{R}", "Instant", "Test Bolt deals 1 damage to target creature.")


class Parse(unittest.TestCase):
    def test_grants(self):
        mods = copies.parse_except('it has haste and "At the beginning of the end step, exile ~."')
        self.assertEqual(mods["keywords"], frozenset({"haste"}))
        self.assertEqual([t.event for t in mods["grant"]["triggers"]], ["each_end_step"])
        mods = copies.parse_except('it\'s an artifact and it has "{T}: Add {U}."')
        self.assertEqual(mods["set_types"], frozenset({"Artifact"}))
        self.assertEqual(mods["grant"], {"produces": frozenset({"U"})})
        mods = copies.parse_except('it has "{2}{U}{U}: Return ~ to its owner\'s hand."')
        self.assertEqual(len(mods["grant"]["activated"]), 1)

    def test_refusals(self):
        for text in ('it has "Other creatures with the same name as ~ are goaded."',      # quote not parsed
                     'it has "{U}{B}, {T}: Flurble target creature with the same name as ~."',
                     'it has "~ is the best creature."',
                     'it has haste and "flurble"',
                     'it has "{T}: Add {U}." and it wobbles'):
            self.assertIsNone(copies.parse_except(text), text)

    def test_clone_lines_ending_in_a_quote(self):
        line = 'You may have ~ enter as a copy of any creature on the battlefield, except it has "Whenever ~ attacks, it connives."'
        spec = copies.parse_line(line)["clone"]
        self.assertEqual([t.event for t in spec["mods"]["grant"]["triggers"]], ["attacks"])
        self.assertIsNone(copies.parse_line(line[:-2] + ' and flurbles."'))

    def test_same_name_trigger_requires_an_unambiguous_source(self):
        from mtgsim.cx_events import compile_head
        self.assertIsNotNone(compile_head("Whenever ~ or another creature with the same name deals combat damage to a player"))
        self.assertIsNone(compile_head("Whenever another creature with the same name deals combat damage to a player"))

    def test_copy_exiled_this_way_requires_preceding_exile(self):
        from mtgsim.cards.parse import _parse_effects
        _, bad = _parse_effects("If you exiled a card this way, create a token that's a copy of that card, "
                                "except it's 5/5.")
        self.assertTrue(bad)


@unittest.skipUnless(os.path.exists(ALL_CARDS), "card database not built")
class Games(unittest.TestCase):
    FULL = ("Moritte of the Frost", "Ardyn, the Usurper", "Face Yourself", "Estrid's Invocation", "Gigantoplasm", "Pirated Copy", "Evil Twin", "Callidus Assassin", "Progenitor Mimic", "Phantasmal Image", "Mercurial Pretender", "Copycrook", "Machine God's Effigy", "Sakashima the Impostor",
            "Colossal Clone Master", "Heat Shimmer", "Cephalid Facetaker", "Aggressive Biomancy")
    STILL_PARTIAL = ("Mocking Doppelganger",)

    def setUp(self):
        self.db = CardDB(offline=True)
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}
            p.ai.respond = p.ai.respond_extras = lambda *args: None

    def test_status(self):
        for name in self.FULL:
            self.assertEqual(self.db.get(name).unsupported, [], name)
        for name in self.STILL_PARTIAL:
            self.assertTrue(self.db.get(name).unsupported, name)

    def clone(self, name, who=None):
        perm = self.g.enter_battlefield(who or self.a, self.db.get(name))
        self.g.settle()
        return perm

    def test_nontoken_upkeep_grant_is_inherited_but_does_not_trigger_on_tokens(self):
        self.g.enter_battlefield(self.b, BEAR)
        mimic = self.clone("Progenitor Mimic")
        self.g.fire(self.a, "upkeep", source=mimic)
        self.g.settle()
        tokens = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual(len(tokens), 1)
        token = tokens[0]
        self.assertEqual(token.card.name, BEAR.name)
        self.assertTrue(any(t.intervening_if for t in token.card.triggers))
        self.g.fire(self.a, "upkeep", source=token)
        self.assertFalse(self.g.pending)
        self.assertEqual(len([x for x in self.a.battlefield if x.card.is_token]), 1)

    def test_nontoken_upkeep_condition_is_rechecked_on_resolution(self):
        self.g.enter_battlefield(self.b, BEAR)
        mimic = self.clone("Progenitor Mimic")
        self.g.fire(self.a, "upkeep", source=mimic)
        self.g.flush_triggers()
        self.assertTrue(self.g.stack)
        mimic.card = dataclasses.replace(mimic.card, is_token=True)
        self.g.settle()
        self.assertEqual(len(self.a.battlefield), 1)

    def test_evil_twin_targets_current_name_and_uses_last_known_name(self):
        bear = self.g.enter_battlefield(self.b, BEAR)
        twin = self.clone("Evil Twin")
        wrong = self.g.enter_battlefield(self.b, card("Different", types="Creature — Cat", power=1, toughness=1))
        effect = twin.activated[-1].effects[0]
        with self.g.targeting(twin):
            self.assertTrue(self.g.legal_target(self.a, effect, bear))
            self.assertTrue(self.g.legal_target(self.a, effect, twin))
            self.assertFalse(self.g.legal_target(self.a, effect, wrong))
        twin.sick = False
        for land in (ISLAND, card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")):
            self.g.enter_battlefield(self.a, land).sick = False
        self.assertFalse(self.g.activate_ability(self.a, twin, len(twin.activated) - 1, [wrong]))
        settle = self.g.settle
        self.g.settle = lambda: None
        try:
            self.assertTrue(self.g.activate_ability(self.a, twin, len(twin.activated) - 1, [bear]))
        finally:
            self.g.settle = settle
        self.g.destroy(twin)
        self.g.settle()
        self.assertNotIn(bear, self.b.battlefield)

    def test_callidus_etb_only_targets_another_creature_with_same_name(self):
        bear = self.g.enter_battlefield(self.b, BEAR)
        assassin = self.g.enter_battlefield(self.a, self.db.get("Callidus Assassin"))
        effect = next(t.effects[0] for t in assassin.card.triggers if t.event == "etb")
        wrong = self.g.enter_battlefield(self.b, card("Different", types="Creature — Cat", power=1, toughness=1))
        with self.g.targeting(assassin):
            self.assertTrue(self.g.legal_target(self.a, effect, bear))
            self.assertFalse(self.g.legal_target(self.a, effect, assassin))
            self.assertFalse(self.g.legal_target(self.a, effect, wrong))
            self.assertTrue(self.g.legal_target(self.a, effect, None))
        self.g.settle()
        self.assertNotIn(bear, self.b.battlefield)
        self.assertIn(wrong, self.b.battlefield)

    def test_name_constraint_is_checked_again_when_ability_resolves(self):
        bear = self.g.enter_battlefield(self.b, BEAR)
        twin = self.clone("Evil Twin")
        twin.sick = False
        for land in (ISLAND, card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)")):
            self.g.enter_battlefield(self.a, land).sick = False
        settle = self.g.settle
        self.g.settle = lambda: None
        try:
            self.assertTrue(self.g.activate_ability(self.a, twin, len(twin.activated) - 1, [bear]))
        finally:
            self.g.settle = settle
        bear.card = dataclasses.replace(bear.card, name="Renamed")
        self.g.settle()
        self.assertIn(bear, self.b.battlefield)

    def test_pirated_copy_watches_its_own_and_other_same_name_combat_damage(self):
        bear = self.g.enter_battlefield(self.b, BEAR)
        pirate = self.clone("Pirated Copy")
        another = self.g.enter_battlefield(self.a, BEAR)
        wrong = self.g.enter_battlefield(self.b, card("Different", types="Creature — Cat", power=1, toughness=1))
        for dealer, player in ((pirate, self.a), (bear, self.b), (another, self.a)):
            before = len(self.a.hand)
            self.g.fire(player, "combat_damage_player", source=dealer, context=self.b)
            self.g.settle()
            self.assertEqual(len(self.a.hand), before + 1)
        before = len(self.a.hand)
        self.g.fire(self.b, "combat_damage_player", source=wrong, context=self.a)
        self.g.fire(self.b, "combat_damage_creature", source=bear, context=pirate)
        self.g.settle()
        self.assertEqual(len(self.a.hand), before)

    def test_gigantoplasm_base_power_and_toughness_are_lasting_and_layered(self):
        self.g.enter_battlefield(self.b, BEAR)
        giant = self.clone("Gigantoplasm")
        for _ in range(5):
            self.g.enter_battlefield(self.a, ISLAND).sick = False
        giant.counters["+1/+1"] = 1
        idx = next(i for i, a in enumerate(giant.activated) if "base power" in a.text)
        self.assertTrue(self.g.activate_ability(self.a, giant, idx, x=3))
        self.assertEqual((giant.power, giant.toughness), (4, 4))
        self.g.expire_continuous_effects()
        self.assertEqual((giant.power, giant.toughness), (4, 4))
        self.assertTrue(self.g.activate_ability(self.a, giant, idx, x=2))
        self.assertEqual((giant.power, giant.toughness), (3, 3))

    def test_gigantoplasm_zero_x_can_cause_death(self):
        self.g.enter_battlefield(self.b, BEAR)
        giant = self.clone("Gigantoplasm")
        idx = next(i for i, a in enumerate(giant.activated) if "base power" in a.text)
        self.assertTrue(self.g.activate_ability(self.a, giant, idx, x=0))
        self.assertNotIn(giant, self.a.battlefield)

    def test_estrid_upkeep_blink_can_be_declined_or_return_as_a_new_object(self):
        enchantment = card("Test Enchantment", "{2}", "Enchantment", "")
        self.g.enter_battlefield(self.a, enchantment)
        invocation = self.clone("Estrid's Invocation")
        self.a.ai.pay_optional = lambda game, player, cost, what: False
        self.g.fire(self.a, "upkeep", source=invocation)
        self.g.settle()
        self.assertIn(invocation, self.a.battlefield)
        self.a.ai.pay_optional = lambda game, player, cost, what: True
        self.g.fire(self.a, "upkeep", source=invocation)
        self.g.settle()
        self.assertNotIn(invocation, self.a.battlefield)
        returned = [x for x in self.a.battlefield if x.front.name == "Estrid's Invocation"]
        self.assertEqual(len(returned), 1)
        self.assertEqual(returned[0].card.name, "Test Enchantment")

    def test_face_yourself_targets_either_player_and_conditional_sacrifice(self):
        self.g.enter_battlefield(self.a, BEAR)
        self.g.enter_battlefield(self.b, LORD)
        self.g.settle()
        spell = self.db.get("Face Yourself")
        eff = spell.spell_effects[0]
        self.assertEqual(eff.target, "player")
        shield = dataclasses.replace(card("Shield", types="Enchantment"),
                                     advanced_rules={"player_hexproof": True})
        protected = self.g.enter_battlefield(self.b, shield)
        with self.g.targeting(spell):
            self.assertTrue(self.g.legal_target(self.a, eff, self.a))
            self.assertFalse(self.g.legal_target(self.a, eff, self.b))
        self.g.leave_battlefield(protected, "graveyard")
        item = StackItem(self.a, [eff], [self.a], card=spell, name=spell.name)
        self.g.stack.append(item)
        self.g.resolve_top()
        token = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertEqual(token.card.name, BEAR.name)
        self.assertTrue(token.has("haste"))
        walker = dataclasses.replace(card("Test Walker", types="Planeswalker — Test"), loyalty=3)
        pw = self.g.enter_battlefield(self.a, walker)
        self.g.fire(self.a, "each_end_step", source=token)
        self.assertFalse(self.g.pending)
        self.g.leave_battlefield(pw, "graveyard")
        self.g.fire(self.a, "each_end_step", source=token)
        self.g.flush_triggers()
        pw = self.g.enter_battlefield(self.a, walker)
        self.g.settle()
        self.assertIn(token, self.a.battlefield)
        self.g.leave_battlefield(pw, "graveyard")
        self.g.fire(self.a, "each_end_step", source=token)
        self.g.settle()
        self.assertNotIn(token, self.a.battlefield)

        item = StackItem(self.a, [eff], [self.b], card=spell, name=spell.name)
        self.g.stack.append(item)
        self.g.resolve_top()
        self.assertEqual([x.card.name for x in self.a.battlefield if x.card.is_token], [LORD.name])

    def test_ardyn_copies_the_specific_card_exiled_and_can_choose_no_target(self):
        ardyn = self.g.enter_battlefield(self.a, self.db.get("Ardyn, the Usurper"))
        self.b.graveyard.extend([BEAR, BEAR])
        chosen, other = self.b.graveyard
        effects = next(t.effects for t in ardyn.triggers if t.event == "begin_combat")
        self.g.stack.append(StackItem(self.a, effects, [chosen, None], source=ardyn, kind="trigger"))
        self.g.resolve_top()
        self.assertIs(self.b.exile[0], chosen)
        self.assertIs(self.b.graveyard[0], other)
        tokens = [x for x in self.a.battlefield if x.card.is_token]
        self.assertEqual(len(tokens), 1)
        token = tokens[0]
        self.assertEqual((token.card.name, token.power, token.toughness, token.card.colors),
                         (BEAR.name, 5, 5, frozenset({"B"})))
        self.assertIn("Demon", token.card.subtypes)
        self.g.stack.append(StackItem(self.a, effects, [None, None], source=ardyn, kind="trigger"))
        self.g.resolve_top()
        self.assertEqual(len([x for x in self.a.battlefield if x.card.is_token]), 1)

    def test_ardyn_does_not_copy_a_target_that_left_its_graveyard(self):
        ardyn = self.g.enter_battlefield(self.a, self.db.get("Ardyn, the Usurper"))
        self.b.graveyard.append(BEAR)
        chosen = self.b.graveyard[0]
        effects = next(t.effects for t in ardyn.triggers if t.event == "begin_combat")
        self.g.stack.append(StackItem(self.a, effects, [chosen, None], source=ardyn, kind="trigger"))
        self.g.move_card(chosen, self.b.graveyard, self.b.hand)
        self.g.resolve_top()
        self.assertFalse(any(x.card.is_token for x in self.a.battlefield))

    def test_exiled_card_reference_does_not_follow_a_later_zone_change(self):
        ardyn = self.g.enter_battlefield(self.a, self.db.get("Ardyn, the Usurper"))
        self.b.graveyard.append(BEAR)
        chosen = self.b.graveyard[0]
        effects = next(t.effects for t in ardyn.triggers if t.event == "begin_combat")
        item = StackItem(self.a, effects, [chosen, None], source=ardyn, kind="trigger")
        self.g.resolve(self.a, effects[0], chosen, item)
        self.g.move_card(chosen, self.b.exile, self.b.hand)
        self.g.move_card(chosen, self.b.hand, self.b.exile)
        self.g.resolve(self.a, effects[1], None, item)
        self.assertFalse(any(x.card.is_token for x in self.a.battlefield))

    def test_moritte_copies_creatures_with_snow_changeling_and_counters(self):
        self.g.enter_battlefield(self.a, BEAR)
        moritte = self.clone("Moritte of the Frost")
        self.assertEqual(moritte.card.name, BEAR.name)
        self.assertTrue(moritte.card.legendary)
        self.assertTrue(moritte.card.snow)
        self.assertTrue(moritte.card.changeling)
        self.assertEqual(moritte.counters.get("+1/+1"), 2)
        self.assertEqual((moritte.power, moritte.toughness), (4, 4))

    def test_moritte_copies_a_noncreature_without_creature_only_changes(self):
        artifact = card("Expensive Relic", "{6}", "Artifact", "")
        self.g.enter_battlefield(self.a, artifact)
        moritte = self.clone("Moritte of the Frost")
        self.assertEqual(moritte.card.name, artifact.name)
        self.assertTrue(moritte.card.legendary)
        self.assertTrue(moritte.card.snow)
        self.assertFalse(moritte.card.changeling)
        self.assertNotIn("+1/+1", moritte.counters)

    def test_phantasmal_image_is_an_illusion_and_dies_when_targeted(self):
        self.g.enter_battlefield(self.b, LEGEND)
        image = self.clone("Phantasmal Image")
        self.assertEqual((image.card.name, image.power, image.toughness), ("Test Legend", 5, 4))
        self.assertIn("Illusion", image.card.subtypes)
        self.assertIn("Elf", image.card.subtypes)
        self.assertIn("trample", image.card.keywords)
        self.b.hand = [BOLT]
        self.g.enter_battlefield(self.b, card("Mountain", types="Basic Land — Mountain",
                                              text="({T}: Add {R}.)")).sick = False
        self.assertTrue(self.g.cast(self.b, BOLT, [image]))
        self.g.settle()
        self.assertNotIn(image, self.a.battlefield)
        self.assertIn("Phantasmal Image", [c.name for c in self.a.graveyard])     # it dies as itself

    def test_mercurial_pretender_can_return_itself(self):
        self.g.enter_battlefield(self.a, LORD)
        pretender = self.clone("Mercurial Pretender")
        self.assertEqual(pretender.card.name, "Test Lord")
        self.assertEqual(self.a.life, 24)                       # the copied ETB fired
        for _ in range(4):
            self.g.enter_battlefield(self.a, ISLAND).sick = False
        idx = next(i for i, act in enumerate(pretender.activated) if "Return ~" in act.text)
        self.assertTrue(self.g.activate_ability(self.a, pretender, idx))
        self.g.settle()
        self.assertIn("Mercurial Pretender", [c.name for c in self.a.hand])

    def test_machine_gods_effigy_is_a_mana_artifact_not_a_creature(self):
        self.g.enter_battlefield(self.b, LEGEND)
        effigy = self.clone("Machine God's Effigy")
        self.assertEqual(effigy.card.name, "Test Legend")
        self.assertFalse(effigy.is_creature)
        self.assertEqual(effigy.card.types, frozenset({"Artifact"}))
        self.assertIn("U", effigy.card.produces)
        effigy.sick = False
        self.assertIn(effigy, self.g.mana_sources(self.a))

    def test_colossal_clone_master_counts_differently_named_lands(self):
        self.g.enter_battlefield(self.b, LEGEND)
        for land in (ISLAND, ISLAND, card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")):
            self.g.enter_battlefield(self.a, land)
        master = self.clone("Colossal Clone Master")
        self.assertEqual(master.card.name, "Test Legend")
        self.assertFalse(master.card.legendary)
        self.assertIn("trample", master.card.keywords)
        self.assertEqual((master.power, master.toughness), (2, 2))      # not the copied 5/4
        self.g.enter_battlefield(self.a, card("Swamp", types="Basic Land — Swamp", text="({T}: Add {B}.)"))
        self.assertEqual((master.power, master.toughness), (3, 3))

    def test_awakened_amalgam_counts_names_not_lands(self):
        """cx_cda: "differently named lands" counted every land as unknown (0) before; it counts distinct names."""
        for land in (ISLAND, ISLAND, card("Forest", types="Basic Land — Forest", text="({T}: Add {G}.)")):
            self.g.enter_battlefield(self.a, land)
        amalgam = self.clone("Awakened Amalgam")
        self.assertIn(amalgam, self.a.battlefield)
        self.assertEqual((amalgam.power, amalgam.toughness), (2, 2))

    def test_copycrook_connives_on_attack(self):
        self.g.enter_battlefield(self.a, BEAR)
        crook = self.clone("Copycrook")
        crook.sick = False
        self.a.hand = [card("Test Spell", "{1}", "Sorcery", "Draw a card.")]
        self.a.ai.attack = (crook,)
        self.g.step = "main1"
        self.g.combat(self.a, self.b)
        self.g.settle()
        self.assertEqual(crook.counters.get("+1/+1", 0), 1)      # discarded a nonland card

    def test_heat_shimmer_token_hastes_then_exiles(self):
        bear = self.g.enter_battlefield(self.a, LORD)
        for _ in range(3):
            self.g.enter_battlefield(self.a, card("Mountain", types="Basic Land — Mountain",
                                                  text="({T}: Add {R}.)")).sick = False
        shimmer = self.db.get("Heat Shimmer")
        self.a.hand = [shimmer]
        self.assertTrue(self.g.cast(self.a, shimmer, [bear]))
        self.g.settle()
        token = next(x for x in self.a.battlefield if x.card.is_token)
        self.assertTrue(token.has("haste"))
        self.g.begin_end_step(self.a)
        self.g.settle()
        self.assertNotIn(token, self.a.battlefield)
        self.assertIn(bear, self.a.battlefield)

    def test_ai_casts_a_quoted_clone(self):
        self.a.ai = HeuristicAI()
        for _ in range(4):
            self.g.enter_battlefield(self.a, ISLAND).sick = False
        self.g.enter_battlefield(self.b, LEGEND)
        self.a.hand = [self.db.get("Phantasmal Image")]
        self.a.ai.main_phase(self.g, self.a)
        self.g.settle()
        image = next(x for x in self.a.battlefield if not x.card.is_land)
        self.assertEqual(image.card.name, "Test Legend")
        self.assertIn("Illusion", image.card.subtypes)


if __name__ == "__main__":
    unittest.main()
