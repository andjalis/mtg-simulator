"""#313: real Oracle text and last-known statistics of cards and permanents."""
import random
import unittest

from mtgsim.carddb import CardDB
from mtgsim.cards import Effect, _parse_effects
from mtgsim.engine import Game, Player, StackItem
from tests.test_combat_triggers import Scripted
from tests.test_templates import ISLAND, card

ELF = card("Referent Elf", "{3}{G}", "Creature — Elf", "", 4, 6)


class ReferentStats(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], Scripted()), Player("b", [], Scripted())
        self.g = Game(self.a, self.b, random.Random(13))
        self.g.turn, self.g.step = 2, "main1"
        for p in self.g.players:
            p.library = [ISLAND] * 30
            p.ai.respond = p.ai.respond_extras = lambda *args: None
        self.db = CardDB(offline=True)
        if self.db._all is not None:
            self.addCleanup(self.db._all.close)

    def resolve(self, effects, targets=None, source=None, context=None, controller=None):
        item = StackItem(controller or self.a, effects, targets or [None] * len(effects),
                         source=source, context=context, kind="trigger")
        self.g.stack.append(item)
        self.g.resolve_top()
        return item

    def test_mirkwood_elk_returns_elf_and_gains_its_power(self):
        elk = self.db.get("Mirkwood Elk")
        self.assertFalse(elk.unsupported)
        self.a.graveyard.append(ELF)
        self.resolve(elk.triggers[0].effects)
        self.assertIn(ELF, self.a.hand)
        self.assertEqual(self.a.life, 24)

    def test_failed_return_gains_nothing_and_clears_previous_card(self):
        effects = self.db.get("Mirkwood Elk").triggers[0].effects
        self.a.graveyard.append(ELF)
        item = self.resolve(effects)
        self.assertEqual(self.a.life, 24)
        for eff in effects:
            self.g.resolve(self.a, eff, None, item)
        self.assertEqual(self.a.life, 24)

    def test_rotfeaster_can_exile_from_own_graveyard_and_reads_toughness(self):
        maggot = self.db.get("Rotfeaster Maggot")
        self.assertFalse(maggot.unsupported)
        self.a.graveyard.append(ELF)
        target = self.a.graveyard[-1]
        effects = maggot.triggers[0].effects
        self.assertIn(target, self.g.legal_targets(self.a, effects[0]))
        self.resolve(effects, [target, None])
        self.assertIn(target, self.a.exile)
        self.assertEqual(self.a.life, 26)

    def test_rotfeaster_does_not_replace_illegal_target_with_same_name_copy(self):
        effects = self.db.get("Rotfeaster Maggot").triggers[0].effects
        self.b.graveyard.extend([ELF, ELF])
        gone = self.b.graveyard.pop()
        self.b.hand.append(gone)
        self.resolve(effects, [gone, None])
        self.assertEqual(self.a.life, 20)
        self.assertEqual(len(self.b.graveyard), 1)

    def test_daxos_uses_damaged_players_top_card_and_keeps_permission_unmatched(self):
        daxos = self.db.get("Daxos of Meletis")
        self.assertEqual(len(daxos.unsupported), 1)
        self.assertIn("you may cast that card", daxos.unsupported[0])
        self.b.library.append(ELF)
        self.resolve(daxos.triggers[0].effects, context=self.b)
        self.assertIn(ELF, self.b.exile)
        self.assertEqual(self.a.life, 24)
        self.assertEqual(len(self.a.exile), 0)

    def test_card_stats_are_frozen_before_reanimation(self):
        effects, bad = _parse_effects("Return target Elf card from your graveyard to the battlefield. "
                                    "You gain life equal to that card's power.")
        self.assertFalse(bad)
        self.a.graveyard.append(ELF)
        item = StackItem(self.a, effects, [None, None])
        self.g.resolve(self.a, effects[0], None, item)
        self.a.creatures[-1].pump_p = 10
        self.g.resolve(self.a, effects[1], None, item)
        self.assertEqual(self.a.life, 24)

    def test_unlinked_card_power_stays_unmatched(self):
        effects, bad = _parse_effects("You gain life equal to that card's power.")
        self.assertFalse(effects)
        self.assertTrue(bad)

    def test_negative_card_power_gains_zero(self):
        negative = card("Negative Elf", "{G}", "Creature — Elf", "", -2, 3)
        self.a.graveyard.append(negative)
        self.resolve(self.db.get("Mirkwood Elk").triggers[0].effects)
        self.assertEqual(self.a.life, 20)

    def test_later_reveal_replaces_earlier_card_reference(self):
        effects, bad = _parse_effects("Return target Elf card from your graveyard to your hand. "
                                    "Reveal the top card of your library. You gain life equal to that card's mana value.")
        self.assertFalse(bad)
        self.a.graveyard.append(ELF)
        self.resolve(effects)
        self.assertEqual(self.a.life, 20)  # the revealed land, not the four-mana Elf

    def test_twisted_justice_draws_last_known_power_of_sacrificed_creature(self):
        justice = self.db.get("Twisted Justice")
        self.assertFalse(justice.unsupported)
        victim = self.g.enter_battlefield(self.b, ELF)
        victim.pump_p = 3
        victim.counters["+1/+1"] = 2
        self.resolve(justice.spell_effects, [self.b, None])
        self.assertNotIn(victim, self.b.battlefield)
        self.assertEqual(len(self.a.hand), 9)

    def test_twisted_justice_can_target_its_caster(self):
        victim = self.g.enter_battlefield(self.a, ELF)
        self.resolve(self.db.get("Twisted Justice").spell_effects, [self.a, None])
        self.assertNotIn(victim, self.a.battlefield)
        self.assertEqual(len(self.a.hand), 4)

    def test_twisted_justice_no_sacrifice_draws_nothing(self):
        self.resolve(self.db.get("Twisted Justice").spell_effects, [self.b, None])
        self.assertFalse(self.a.hand)

    def test_twisted_justice_negative_power_draws_nothing(self):
        victim = self.g.enter_battlefield(self.b, ELF)
        victim.pump_p = -10
        self.resolve(self.db.get("Twisted Justice").spell_effects, [self.b, None])
        self.assertFalse(self.a.hand)

    def test_avatar_destiny_mills_hosts_last_known_power(self):
        avatar = self.db.get("Avatar Destiny")
        self.assertEqual(len(avatar.unsupported), 2)
        host = self.g.enter_battlefield(self.a, ELF)
        aura = self.g.enter_battlefield(self.a, avatar)
        from mtgsim.auras import attach
        attach(self.g, aura, host)
        host.pump_p = 3
        host.counters["+1/+1"] = 2
        before = len(self.a.library)
        self.g.sacrifice(host)
        self.g.settle()
        self.assertEqual(len(self.a.library), before - 9)

    def test_ignition_excludes_source_and_uses_real_damage(self):
        ignition = self.db.get("Chandra's Ignition")
        self.assertFalse(ignition.unsupported)
        source = self.g.enter_battlefield(self.a, ELF)
        source.temp_kw.add("lifelink")
        mine = self.g.enter_battlefield(self.a, ELF)
        theirs = self.g.enter_battlefield(self.b, ELF)
        source.pump_p = 1
        self.resolve(ignition.spell_effects, [source, None])
        self.assertEqual(source.damage, 0)
        self.assertEqual((mine.damage, theirs.damage), (5, 5))
        self.assertEqual(self.b.life, 15)
        self.assertEqual(self.a.life, 35)

    def test_nibelheim_aflame_uses_chosen_creature_not_spell(self):
        aflame = self.db.get("Nibelheim Aflame")
        self.assertFalse(aflame.unsupported)
        source = self.g.enter_battlefield(self.a, ELF)
        other = self.g.enter_battlefield(self.b, ELF)
        self.resolve(aflame.spell_effects, [source, None, None, None])
        self.assertEqual(source.damage, 0)
        self.assertEqual(other.damage, 4)
        self.assertEqual(self.b.life, 20)

    def test_ignition_lost_target_fizzles(self):
        source = self.g.enter_battlefield(self.a, ELF)
        self.g.sacrifice(source)
        self.resolve(self.db.get("Chandra's Ignition").spell_effects, [source, None])
        self.assertEqual(self.b.life, 20)

    def test_mill_defaults_to_trigger_source_without_subject(self):
        source = self.g.enter_battlefield(self.a, ELF)
        effects, bad = _parse_effects("Mill cards equal to its power.")
        self.assertFalse(bad)
        self.resolve(effects, source=source)
        self.assertEqual(len(self.a.library), 26)

    def test_board_damage_uses_departed_creatures_last_known_power(self):
        source = self.g.enter_battlefield(self.a, ELF)
        source.pump_p = 1
        other = self.g.enter_battlefield(self.b, ELF)
        effects, bad = _parse_effects("Destroy target creature. It deals damage equal to its power to each other creature.")
        self.assertFalse(bad)
        self.resolve(effects, [source, None])
        self.assertEqual(other.damage, 5)

    def test_broken_visage_token_keeps_last_known_stats_and_dies_at_end_step(self):
        visage = self.db.get("Broken Visage")
        self.assertFalse(visage.unsupported)
        victim = self.g.enter_battlefield(self.b, ELF)
        victim.attacking = True
        self.g.attackers.append(victim)
        victim.pump_p, victim.pump_t = 3, 1
        victim.counters["+1/+1"] = 2
        victim.regeneration_shields = 1     # "can't be regenerated" still destroys
        self.resolve(visage.spell_effects, [victim, None])
        self.assertNotIn(victim, self.b.battlefield)
        spirit = self.a.creatures[-1]
        self.assertTrue(spirit.card.is_token)
        self.assertEqual(spirit.card.colors, frozenset({"B"}))
        self.assertEqual((spirit.power, spirit.toughness), (9, 9))
        self.assertIn((spirit, "sacrifice"), self.g.end_cleanup)

    def test_token_stats_still_read_surviving_indestructible_creature(self):
        victim = self.g.enter_battlefield(self.b, ELF)
        victim.temp_kw.add("indestructible")
        victim.attacking = True
        self.g.attackers.append(victim)
        self.resolve(self.db.get("Broken Visage").spell_effects, [victim, None])
        self.assertIn(victim, self.b.battlefield)
        token = self.a.creatures[-1]
        self.assertEqual((token.power, token.toughness), (4, 6))

    def test_yearling_sets_only_base_power_and_preserves_counters_and_pump(self):
        yearling = self.g.enter_battlefield(self.a, self.db.get("Belligerent Yearling"))
        self.g.add_continuous_effect(yearling, "set_base", power=1, toughness=8)
        yearling.counters["+1/+1"] = 2
        yearling.pump_p, yearling.pump_t = 1, 3
        dinosaur = card("Referent Dinosaur", "{4}{G}", "Creature — Dinosaur", "", 5, 7)
        subject = self.g.enter_battlefield(self.a, dinosaur)
        self.g.settle()
        self.assertEqual((yearling.power, yearling.toughness), (8, 13))
        subject.pump_p = 10
        self.assertEqual(yearling.power, 8)  # frozen on resolution
        self.g.add_continuous_effect(yearling, "set_base", power=None, toughness=4, until_eot=True)
        self.assertEqual((yearling.power, yearling.toughness), (8, 9))
        self.g.expire_continuous_effects()
        self.assertEqual((yearling.power, yearling.toughness), (4, 13))

    def test_yearling_reads_departed_trigger_subjects_last_known_power(self):
        yearling = self.g.enter_battlefield(self.a, self.db.get("Belligerent Yearling"))
        subject = self.g.enter_battlefield(self.a, ELF)
        subject.pump_p = 3
        self.g.sacrifice(subject)
        self.resolve(yearling.card.triggers[0].effects, source=yearling, context=subject)
        self.assertEqual((yearling.power, yearling.toughness), (7, 2))

    def test_yearling_effect_does_not_apply_to_reentered_source(self):
        definition = self.db.get("Belligerent Yearling")
        yearling = self.g.enter_battlefield(self.a, definition)
        subject = self.g.enter_battlefield(self.a, ELF)
        self.resolve(definition.triggers[0].effects, source=yearling, context=subject)
        self.g.leave_battlefield(yearling, "hand")
        self.a.hand.remove(yearling.front)
        new = self.g.enter_battlefield(self.a, yearling.front)
        self.assertEqual((new.power, new.toughness), (3, 2))

    def test_shape_stealer_copies_both_stats_on_actual_block_event(self):
        shape = self.g.enter_battlefield(self.a, self.db.get("Shape Stealer"))
        other = self.g.enter_battlefield(self.b, ELF)
        shape.counters["+1/+1"] = 1
        self.g.fire(self.a, "blocks", shape, context=other)
        self.g.settle()
        self.assertEqual((shape.power, shape.toughness), (5, 7))

    def test_kalitas_death_condition_is_still_unmatched(self):
        kalitas = self.db.get("Kalitas, Bloodchief of Ghet")
        self.assertTrue(kalitas.unsupported)
        self.assertFalse(kalitas.activated)

    def test_set_base_without_referent_does_nothing(self):
        source = self.g.enter_battlefield(self.a, ELF)
        self.resolve([Effect("set_base_referent", target="self", data={"stat": "power"})], source=source)
        self.assertEqual((source.power, source.toughness), (4, 6))

    def test_too_greedily_damages_with_the_reanimated_creature(self):
        too = self.db.get("Too Greedily, Too Deep")
        self.assertFalse(too.unsupported)
        self.a.graveyard.append(ELF)
        mine = self.g.enter_battlefield(self.a, ELF)
        other = self.g.enter_battlefield(self.b, ELF)
        self.resolve(too.spell_effects)
        reanimated = self.a.creatures[-1]
        self.assertEqual(reanimated.damage, 0)      # the source excludes itself
        self.assertEqual((mine.damage, other.damage), (4, 4))

    def test_waltz_of_rage_hits_creatures_but_not_opponents(self):
        waltz = self.db.get("Waltz of Rage")
        self.assertEqual(len(waltz.unsupported), 1)    # the "whenever ... dies" clause stays unmatched
        source = self.g.enter_battlefield(self.a, ELF)
        mine = self.g.enter_battlefield(self.a, ELF)
        theirs = self.g.enter_battlefield(self.b, ELF)
        source.pump_p = 2                            # power 6
        self.resolve(waltz.spell_effects, [source, None, None])
        self.assertEqual(source.damage, 0)
        self.assertEqual((mine.damage, theirs.damage), (6, 6))
        self.assertEqual(self.b.life, 20)            # no "and each opponent" rider

    def test_nova_flame_without_resolved_referent_deals_nothing(self):
        nova = self.db.get("Nova Flame")
        self.assertEqual(len(nova.unsupported), 1)    # the X-counters sentence stays unmatched
        other = self.g.enter_battlefield(self.b, ELF)
        self.resolve(nova.spell_effects)
        self.assertEqual(other.damage, 0)
