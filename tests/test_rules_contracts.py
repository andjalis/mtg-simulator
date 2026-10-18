"""Bounded rules scenarios: targeting, normal legend rule, normal equip.

The scenario manifest maps these tests explicitly; they do not establish complete card support.
"""
import dataclasses
import random
import unittest

from mtgsim.ai import BaselineAI
from mtgsim.carddb import CardDB
from mtgsim.cards import Effect, Trigger
from mtgsim.engine import Game, Player, StackItem
from tests.test_templates import BEAR, ISLAND, card

ISAMARU = card("Isamaru, Hound of Konda", "{W}", "Legendary Creature — Dog", "", 2, 2)
SHUKO = card("Shuko", "{1}", "Artifact — Equipment", "Equipped creature gets +1/+0.\nEquip {0}")

# Evidence runs require the DB and exercise its actual definitions. The fallbacks
# keep this regression module useful in lightweight checkouts without the inventory.
_db = CardDB(offline=True)
try:
    if _db._all is not None:
        ISAMARU, SHUKO = _db.get(ISAMARU.name), _db.get(SHUKO.name)
finally:
    if _db._all is not None:
        _db._all.close()


class RulesContracts(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], BaselineAI())
        self.b = Player("b", [], BaselineAI())
        self.g = Game(self.a, self.b, random.Random(0), log=True)
        self.g.turn, self.g.step = 2, "main1"
        self.g._priority_depth = 1  # observe state before responses/resolution

    def put(self, definition=BEAR, who=None):
        return self.g.enter_battlefield(who or self.a, definition)

    def move_control(self, permanent, who):
        permanent.controller.battlefield.remove(permanent)
        who.battlefield.append(permanent)
        permanent.controller = who

    def test_target_type_membership(self):
        land, creature = self.put(ISLAND), self.put()
        artifact = self.put(SHUKO)
        for target_type, valid, invalid in (
            ("creature", creature, land), ("artifact", artifact, creature),
            ("player", self.b, creature), ("land", land, self.a),
            ("nonland_perm", artifact, land), ("any", self.b, land),
        ):
            with self.subTest(target_type=target_type):
                effect = Effect("damage", 1, target=target_type)
                self.assertTrue(self.g.legal_target(self.a, effect, valid))
                self.assertFalse(self.g.legal_target(self.a, effect, invalid))

    def test_target_controller_shroud_presence(self):
        mine, theirs = self.put(), self.put(who=self.b)
        effect = Effect("equip", target="creature_mine")
        self.assertTrue(self.g.legal_target(self.a, effect, mine))
        self.assertFalse(self.g.legal_target(self.a, effect, theirs))
        mine.temp_kw.add("shroud")
        self.assertFalse(self.g.legal_target(self.a, effect, mine))
        mine.temp_kw.clear()
        self.g.leave_battlefield(mine, "hand")
        self.assertFalse(self.g.legal_target(self.a, effect, mine))

    def test_target_type_changes_before_resolution(self):
        creature = self.put(who=self.b)
        self.g.stack.append(StackItem(self.a, [Effect("damage", 2, target="creature")], [creature]))
        creature.card = ISLAND
        self.g.resolve_top()
        self.assertEqual(creature.damage, 0)

    def test_filtered_planeswalker_and_animated_land(self):
        pw = self.put(card("Walker", types="Planeswalker", text="", power=None))
        effect = Effect("destroy", target="creature_pw", filter="opp")
        self.assertFalse(self.g.legal_target(self.a, effect, pw))
        land = self.put(dataclasses.replace(ISLAND, types=frozenset({"Land", "Creature"}), power=2, toughness=2))
        self.assertFalse(self.g.legal_target(self.a, Effect("bounce", target="nonland_perm"), land))

    def test_invalid_explicit_cast_does_not_pay(self):
        mana = self.put(ISLAND)
        spell = card("Fixture removal", "{U}", "Instant", "Return target creature to its owner's hand.")
        self.a.hand.append(spell)
        self.assertFalse(self.g.cast(self.a, spell, [mana]))
        self.assertFalse(mana.tapped)
        self.assertEqual(self.a.hand, [spell])
        self.assertEqual(self.g.stack, [])

    def test_legend_controller_chooses(self):
        self.a.ai.choose_legend = lambda game, me, choices: choices[-1]
        first, second = self.put(ISAMARU), self.put(ISAMARU)
        self.g.state_based_actions()
        self.assertEqual(self.a.battlefield, [second])
        self.assertNotIn(first, self.a.battlefield)
        self.assertEqual(len(self.a.graveyard), 1)

    def test_legend_not_destruction_or_sacrifice(self):
        definition = dataclasses.replace(ISAMARU, keywords=frozenset({"indestructible"}),
                                         triggers=[Trigger("dies", [Effect("draw", 1)])])
        first = self.put(definition)
        first.regeneration_shields = 1
        self.a.ai.choose_legend = lambda game, me, choices: choices[-1]
        second = self.put(definition)
        self.g.state_based_actions()
        self.assertEqual(self.a.battlefield, [second])
        self.assertEqual(self.a.sacrificed_turn, 0)
        self.assertEqual(first.regeneration_shields, 1)
        self.assertTrue(any(row[1][0].kind == "draw" for row in self.g.pending))

    def test_legend_groups_and_other_controllers(self):
        self.put(ISAMARU)
        self.put(ISAMARU, self.b)
        self.put(dataclasses.replace(ISAMARU, name="Other legend"))
        self.put(BEAR)
        self.put(BEAR)
        self.g.state_based_actions()
        self.assertEqual(len(self.a.battlefield), 4)
        self.assertEqual(len(self.b.battlefield), 1)

    def test_legend_control_change_routes_to_owner(self):
        first = self.put(ISAMARU)
        stolen = self.put(ISAMARU, self.b)
        self.move_control(stolen, self.a)
        self.a.ai.choose_legend = lambda *args: first
        self.g.state_based_actions()
        self.assertEqual(self.b.graveyard, [ISAMARU])
        self.assertEqual(self.a.graveyard, [])

    def test_legend_choice_precedes_lethal_removal(self):
        first = self.put(ISAMARU)
        first.damage = first.toughness
        self.a.ai.choose_legend = lambda *args: first
        self.put(ISAMARU)
        self.g.state_based_actions()
        self.assertEqual(self.a.battlefield, [])
        self.assertEqual(len(self.a.graveyard), 2)

    def test_equip_queues_then_attaches(self):
        equipment, creature = self.put(SHUKO), self.put()
        self.assertTrue(self.g.equip(self.a, equipment, creature))
        self.assertIsNone(equipment.attached_to)
        self.assertEqual(len(self.g.stack), 1)
        self.assertFalse(self.g.stack[-1].is_spell)
        self.g.resolve_top()
        self.assertIs(equipment.attached_to, creature)
        self.assertEqual(creature.power, 3)

    def test_equip_target_removed_in_response(self):
        equipment, creature = self.put(SHUKO), self.put()
        self.g.equip(self.a, equipment, creature)
        self.g.stack.append(StackItem(self.b, [Effect("destroy", target="creature")], [creature]))
        self.g.resolve_top()
        self.g.resolve_top()
        self.assertIsNone(equipment.attached_to)
        self.assertNotIn(creature, self.a.battlefield)

    def test_equip_source_leaves_and_returns(self):
        equipment, creature = self.put(SHUKO), self.put()
        self.g.equip(self.a, equipment, creature)
        self.g.leave_battlefield(equipment, "hand")
        returned = self.put(SHUKO)
        self.g.resolve_top()
        self.assertIsNone(returned.attached_to)
        self.assertEqual(creature.power, 2)

    def test_equip_target_changes_controller(self):
        equipment, creature = self.put(SHUKO), self.put()
        self.g.equip(self.a, equipment, creature)
        self.move_control(creature, self.b)
        self.g.resolve_top()
        self.assertIsNone(equipment.attached_to)

    def test_equip_source_changes_controller(self):
        equipment, creature = self.put(SHUKO), self.put()
        self.g.equip(self.a, equipment, creature)
        self.move_control(equipment, self.b)
        self.g.resolve_top()
        self.assertIs(equipment.attached_to, creature)
        self.assertEqual(creature.power, 3)
        self.g.leave_battlefield(creature, "hand")
        self.assertIsNone(equipment.attached_to)

    def test_equip_invalid_action_preserves_state(self):
        equipment, mine, theirs = self.put(SHUKO), self.put(), self.put(who=self.b)
        equipment.attached_to = mine
        self.assertFalse(self.g.equip(self.a, equipment, theirs))
        self.assertIs(equipment.attached_to, mine)
        self.assertEqual(self.g.stack, [])
        self.g.step = "upkeep"
        self.assertFalse(self.g.equip(self.a, equipment, mine))

    def test_equip_animated_source_cannot_attach(self):
        equipment, creature = self.put(SHUKO), self.put()
        self.g.equip(self.a, equipment, creature)
        equipment.card = dataclasses.replace(SHUKO, types=frozenset({"Artifact", "Creature"}), power=1, toughness=1)
        self.g.resolve_top()
        self.assertIsNone(equipment.attached_to)
