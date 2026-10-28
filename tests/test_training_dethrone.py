"""Attack-time checks and independent stack triggers for training and dethrone."""
import dataclasses
import random
import unittest

from mtgsim.cards import make_token
from mtgsim.engine import Game, Player
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card


TRAINING = card("Apprentice Sharpshooter", "{2}{G}", "Creature — Human Archer",
                "Reach\nTraining (Whenever this creature attacks with another creature with greater power, "
                "put a +1/+1 counter on this creature.)", 1, 4)
DETHRONE = card("Enraged Revolutionary", "{2}{R}", "Creature — Human Warrior",
                "Dethrone (Whenever this creature attacks the player with the most life or tied for most life, "
                "put a +1/+1 counter on this creature.)", 2, 1)


class AttackCounterKeywords(unittest.TestCase):
    def setUp(self):
        self.a = Player("a", [], Scripted())
        self.b = Player("b", [], Scripted())
        self.game = Game(self.a, self.b, random.Random(0))
        self.game.turn, self.game.step = 2, "main1"
        for p in (self.a, self.b):
            p.library = [ISLAND] * 20
            p.ai.attack, p.ai.block = (), {}

    def put(self, definition=TRAINING, who=None):
        perm = self.game.enter_battlefield(who or self.a, definition)
        perm.sick = False
        self.game.settle()
        return perm

    def creature(self, power, text="", who=None):
        return self.put(card("Test Ally", "{2}", "Creature — Human", text, power, 5), who)

    def attack(self, attackers):
        self.a.ai.attack = attackers
        self.game.combat(self.a, self.b)
        self.game.settle()

    def declare(self, attackers, defender=None):
        """Leave attack triggers pending so responses can change the battlefield."""
        self.game.attackers = attackers
        self.game.attack_targets = {a: defender or self.b for a in attackers}
        for a in attackers:
            self.game.fire(self.a, "attacks", a)

    def test_oracle_templates_and_combined_keyword_lines(self):
        for definition in (TRAINING, DETHRONE,
                           card("Combined", "{2}", "Creature", "Flying, training, dethrone", 1, 1)):
            with self.subTest(card=definition.name):
                self.assertEqual(definition.unsupported, [])

    def test_training_counter_is_added_before_combat_damage(self):
        trainee, ally = self.put(), self.creature(2)
        self.attack([trainee, ally])
        self.assertEqual(trainee.p1, 1)
        self.assertEqual(self.b.life, 16)

    def test_training_requires_strictly_greater_attacking_power(self):
        trainee, equal = self.put(), self.creature(1)
        self.creature(4)                         # a stronger creature that does not attack
        self.creature(5, who=self.b)             # an opponent's creature
        self.attack([trainee, equal])
        self.assertEqual(trainee.p1, 0)

    def test_training_does_not_trigger_alone(self):
        trainee = self.put()
        self.attack([trainee])
        self.assertEqual(trainee.p1, 0)

    def test_training_triggers_once_with_several_stronger_attackers(self):
        trainee, a, b = self.put(), self.creature(2), self.creature(3)
        self.attack([trainee, a, b])
        self.assertEqual(trainee.p1, 1)

    def test_training_instances_stack_and_use_declaration_power(self):
        trainee = self.creature(1, "Training\nTraining")
        ally = self.creature(2)
        self.attack([trainee, ally])
        self.assertEqual(trainee.p1, 2)           # the second trigger does not recheck power

    def test_training_partner_can_leave_before_resolution(self):
        trainee, ally = self.put(), self.creature(2)
        self.declare([trainee, ally])
        self.game.leave_battlefield(ally, "graveyard")
        self.game.settle()
        self.assertEqual(trainee.p1, 1)

    def test_training_does_not_trigger_retroactively(self):
        trainee, ally = self.put(), self.creature(1)
        self.declare([trainee, ally])
        ally.pump_p += 2
        self.game.settle()
        self.assertEqual(trainee.p1, 0)

    def test_training_multiple_trainees_check_before_triggers_resolve(self):
        a, b, ally = self.creature(1, "Training"), self.creature(2, "Training"), self.creature(3)
        self.attack([a, b, ally])
        self.assertEqual((a.p1, b.p1), (1, 1))

    def test_dethrone_life_comparison_includes_the_attacker(self):
        for attacker_life, defender_life, expected in ((20, 20, 1), (10, 20, 1), (20, 10, 0)):
            with self.subTest(attacker_life=attacker_life, defender_life=defender_life):
                self.a.life, self.b.life = attacker_life, defender_life
                attacker = self.put(DETHRONE)
                self.attack([attacker])
                self.assertEqual(attacker.p1, expected)

    def test_dethrone_does_not_trigger_when_attacking_a_planeswalker(self):
        attacker = self.put(DETHRONE)
        walker = self.put(dataclasses.replace(card("Test Walker", "{2}{U}", "Planeswalker — Test"), loyalty=5), self.b)
        self.a.ai.choose_attack_targets = lambda game, me, attackers: {attacker: walker}
        self.attack([attacker])
        self.assertEqual(attacker.p1, 0)
        self.assertEqual(walker.loyalty, 3)

    def test_dethrone_does_not_recheck_life_on_resolution(self):
        attacker = self.put(DETHRONE)
        self.declare([attacker])
        self.b.life = 10
        self.game.settle()
        self.assertEqual(attacker.p1, 1)

    def test_dethrone_multiple_instances_stack(self):
        attacker = self.creature(1, "Dethrone\nDethrone")
        self.attack([attacker])
        self.assertEqual(attacker.p1, 2)

    def test_source_leaving_does_not_put_counters_on_a_new_object(self):
        for definition in (TRAINING, DETHRONE):
            with self.subTest(card=definition.name):
                source, ally = self.put(definition), self.creature(4)
                self.declare([source, ally])
                self.game.leave_battlefield(source, "graveyard")
                self.a.graveyard.remove(definition)
                returned = self.game.enter_battlefield(self.a, definition)
                self.game.settle()
                self.assertEqual(source.p1, 0)
                self.assertEqual(returned.p1, 0)

    def test_tokens_and_temporary_grants_generate_triggers(self):
        trainee = self.put(make_token("Human Soldier", 1, 1, keywords={"training"}))
        ally = self.creature(2)
        ally.temp_kw.add("dethrone")
        self.attack([trainee, ally])
        self.assertEqual((trainee.p1, ally.p1), (1, 1))

    def test_native_and_equipment_granted_instances_stack(self):
        trainee = self.put()
        equipment = self.put(card("Test Equipment", "{1}", "Artifact — Equipment",
                                  "Equipped creature has training.\nEquip {1}"))
        equipment.attached_to = trainee
        trainee.equipment.append(equipment)
        ally = self.creature(2)
        self.attack([trainee, ally])
        self.assertEqual(trainee.p1, 2)

    def test_losing_granted_keyword_after_trigger_does_not_remove_trigger(self):
        trainee, ally = self.creature(1), self.creature(2)
        trainee.temp_kw.add("training")
        self.declare([trainee, ally])
        trainee.temp_kw.clear()
        self.game.settle()
        self.assertEqual(trainee.p1, 1)

    def test_silenced_source_has_no_keyword_trigger(self):
        trainee, ally, suppressor = self.put(), self.creature(2), self.creature(3, who=self.b)
        trainee.silenced_by = suppressor
        self.attack([trainee, ally])
        self.assertEqual(trainee.p1, 0)

    def test_token_creation_preserves_training(self):
        spell = card("Test Recruitment", "{2}{G}", "Sorcery",
                     "Create a 1/1 green and white Human Soldier creature token with training.")
        self.assertEqual(spell.unsupported, [])
        self.game.resolve(self.a, spell.spell_effects[0], None)
        token = self.a.creatures[-1]
        token.sick = False
        ally = self.creature(2)
        self.attack([token, ally])
        self.assertEqual(token.p1, 1)


if __name__ == "__main__":
    unittest.main()
