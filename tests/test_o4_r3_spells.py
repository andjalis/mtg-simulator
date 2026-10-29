"""O4 round 3 spell riders: positive, negative and real-stack interactions."""
import dataclasses
from unittest.mock import patch

from mtgsim.cards import Effect, _parse_effects
from mtgsim.engine import StackItem
from tests.test_templates import Base, BEAR, DRAGON3, ISLAND, SHOCK, card

BOUNCE = card("Spell Return", "{U}", "Instant", "Return target spell or permanent to its owner's hand.")
PUSH = card("Fatal Push", "{B}", "Instant", "Destroy target creature if it has mana value 2 or less.\n"
            "Revolt — Destroy that creature if it has mana value 4 or less instead if a permanent left the "
            "battlefield under your control this turn.")
AMALIA = card("Amalia", types="Creature", text="Whenever you gain life, Amalia explores. Then destroy all other "
              "creatures if its power is exactly 20.", power=2, toughness=2)
RELIQUARY = card("Roadside Reliquary", types="Land", text="{T}: Add {C}.\n{2}, {T}, Sacrifice this land: "
                 "Draw a card if you control an artifact. Draw a card if you control an enchantment.")
MASTER = card("Master of Barbs", types="Creature", text="Whenever one or more opponents are dealt noncombat "
              "damage, creatures you control get +1/+0 until end of turn.", power=2, toughness=1)
TUTOR = card("Random Tutor", types="Sorcery", text="Search your library for a card, put it into your hand, "
             "shuffle, then discard a card at random.")


class SpellRiders(Base):
    def resolve_spell(self, c, targets, player=None):
        p = player or self.a
        self.game.stack.append(StackItem(p, c.spell_effects, targets, card=c))
        self.game.resolve_top()

    def test_templates(self):
        for c in (BOUNCE, PUSH, AMALIA, RELIQUARY, MASTER, TUTOR):
            with self.subTest(c=c.name):
                self.assertEqual(c.unsupported, [])
        self.assertEqual(PUSH.spell_effects[0].kind, "destroy_mv")
        self.assertEqual([e.kind for e in TUTOR.spell_effects], ["tutor", "discard"])

    def test_unknown_shapes_remain_unsupported(self):
        for text in ("Destroy all other creatures if its toughness is exactly 20.",
                     "Draw a card if you control a battle.",
                     "Return target spell or permanent to the top of its owner's library.",
                     "Revolt — Destroy that creature if it has mana value 4 or less instead if a creature died this turn."):
            self.assertTrue(_parse_effects(text)[1], text)

    def test_return_uncounterable_spell(self):
        spell = dataclasses.replace(SHOCK, uncounterable=True)
        pending = StackItem(self.b, spell.spell_effects, [self.a], card=spell)
        self.game.stack.append(pending)
        self.assertIn(pending, self.game.legal_targets(self.a, BOUNCE.spell_effects[0]))
        self.assertIs(self.game.auto_targets(self.a, BOUNCE.spell_effects)[0], pending)
        self.resolve_spell(BOUNCE, [pending])
        self.assertFalse(self.game.stack)
        self.assertIn(spell, self.b.hand)
        self.assertEqual(self.a.life, 20)
        self.assertNotIn(spell, self.b.graveyard)

    def test_return_land_and_own_spell_and_reject_ability(self):
        land = self.perm(ISLAND, self.b)
        self.resolve_spell(BOUNCE, [land])
        self.assertIn(ISLAND, self.b.hand)
        own = StackItem(self.a, SHOCK.spell_effects, [self.b], card=SHOCK)
        ability = StackItem(self.b, [Effect("draw", 1)], [None])
        self.game.stack.extend([own, ability])
        self.assertNotIn(ability, self.game.legal_targets(self.a, BOUNCE.spell_effects[0]))
        self.resolve_spell(BOUNCE, [own])
        self.assertIn(SHOCK, self.a.hand)
        self.assertEqual(self.game.stack, [ability])

    def test_return_copy_disappears_and_flashback_exiles(self):
        for kind, hand, exile in (("copy", False, False), ("spell", True, False)):
            target = StackItem(self.b, SHOCK.spell_effects, [self.a], card=SHOCK, kind=kind)
            self.game.stack.append(target)
            self.resolve_spell(BOUNCE, [target])
            self.assertEqual(SHOCK in self.b.hand, hand)
            self.assertEqual(SHOCK in self.b.exile, exile)
        from mtgsim.cards import AltCost
        variant = self.game._variant(SHOCK, "flashback", AltCost("flashback", {"R": 1}))
        pending = StackItem(self.b, variant.spell_effects, [self.a], card=variant)
        self.game.stack.append(pending)
        self.resolve_spell(BOUNCE, [pending])
        self.assertIn(SHOCK, self.b.exile)

    def test_amalia_19_does_not_sweep_and_20_does(self):
        amalia = self.perm(AMALIA, self.a)
        other = self.perm(BEAR, self.a)
        enemy = self.perm(BEAR, self.b)
        amalia.counters["+1/+1"] = 17
        self.game.change_life(self.a, 1, "test")
        self.game.settle()  # Land on top: explore doesn't increase power.
        self.assertIn(other, self.a.battlefield)
        self.assertIn(enemy, self.b.battlefield)
        amalia.counters["+1/+1"] = 18
        self.game.change_life(self.a, 1, "test")
        self.game.settle()
        self.assertEqual(self.a.creatures, [amalia])
        self.assertFalse(self.b.creatures)

    def test_amalia_explore_reaches_20(self):
        amalia = self.perm(AMALIA, self.a)
        amalia.counters["+1/+1"] = 17
        self.a.library = [BEAR]
        enemy = self.perm(BEAR, self.b)
        self.game.change_life(self.a, 1, "test")
        self.game.settle()
        self.assertEqual(amalia.power, 20)
        self.assertNotIn(enemy, self.b.battlefield)

    def test_push_without_revolt_and_opponent_leaving(self):
        victim = self.perm(DRAGON3, self.b)
        self.game.leave_battlefield(self.perm(ISLAND, self.b), "hand")
        self.resolve_spell(PUSH, [victim])
        self.assertIn(victim, self.b.battlefield)
        self.assertTrue(self.game.legal_target(self.a, PUSH.spell_effects[0], victim))
        small = self.perm(BEAR, self.b)
        self.resolve_spell(PUSH, [small])
        self.assertNotIn(small, self.b.battlefield)

    def test_push_checks_revolt_on_resolution(self):
        victim = self.perm(DRAGON3, self.b)
        self.game.stack.append(StackItem(self.a, PUSH.spell_effects, [victim], card=PUSH))
        self.game.sacrifice(self.perm(ISLAND, self.a))
        self.game.resolve_top()
        self.assertNotIn(victim, self.b.battlefield)
        big = self.perm(dataclasses.replace(DRAGON3, cmc=5), self.b)
        self.resolve_spell(PUSH, [big])
        self.assertIn(big, self.b.battlefield)
        plain = Effect("destroy", target="creature", filter="max_cmc:2")
        self.assertFalse(self.game.legal_target(self.a, plain, self.perm(DRAGON3, self.b)))

    def test_reliquary_zero_one_two_and_after_sacrifice(self):
        for types, expected in (([], 0), (["Artifact"], 1), (["Enchantment"], 1),
                                (["Artifact", "Enchantment"], 2)):
            with self.subTest(types=types):
                self.a.battlefield.clear()
                for typ in types:
                    self.perm(card(typ, types=typ), self.a)
                land = self.perm(RELIQUARY, self.a)
                self.perm(ISLAND, self.a)
                self.perm(ISLAND, self.a)
                before = len(self.a.hand)
                self.assertTrue(self.game.activate_ability(self.a, land, 0))
                self.game.settle()
                self.assertNotIn(land, self.a.battlefield)
                self.assertEqual(len(self.a.hand) - before, expected)
        self.a.battlefield.clear()
        land = self.perm(dataclasses.replace(RELIQUARY, types=frozenset({"Land", "Artifact"})), self.a)
        self.perm(ISLAND, self.a)
        self.perm(ISLAND, self.a)
        before = len(self.a.hand)
        self.assertTrue(self.game.activate_ability(self.a, land, 0))
        self.game.settle()
        self.assertEqual(len(self.a.hand), before)

    def test_random_discard_after_tutor_uses_rng(self):
        self.a.hand = [ISLAND]
        self.a.library = [DRAGON3]
        with patch.object(self.game.rng, "choice", side_effect=lambda hand: hand[-1]) as choose:
            self.resolve_spell(TUTOR, [None, None])
        choose.assert_called_once()
        self.assertEqual(self.a.hand, [ISLAND])
        self.assertIn(DRAGON3, self.a.graveyard)
        self.assertFalse(self.a.library)

    def test_master_from_burn_once_per_damage_event(self):
        master = self.perm(MASTER, self.a)
        ally = self.perm(BEAR, self.a)
        self.resolve_spell(SHOCK, [self.b])
        self.assertEqual(len(self.game.pending), 1)
        self.assertEqual(ally.power, 2)
        self.game.settle()
        self.assertEqual((master.power, ally.power), (3, 3))
        self.resolve_spell(SHOCK, [self.b])
        self.game.settle()
        self.assertEqual(ally.power, 4)

    def test_master_ignores_combat_life_loss_self_and_creature_damage(self):
        self.perm(MASTER, self.a)
        ally = self.perm(BEAR, self.a)
        for target, combat in ((self.b, True), (self.a, False), (ally, False)):
            self.game.deal_damage(target, 1, by=self.a, combat=combat)
        self.game.change_life(self.b, -1, "test")
        self.assertFalse(self.game.pending)

    def test_master_triggers_for_opponents_own_source_and_infect(self):
        self.perm(MASTER, self.a)
        self.game.deal_damage(self.b, 1, by=self.b, source=dataclasses.replace(SHOCK, keywords={"infect"}))
        self.assertEqual(self.b.counters["poison"], 1)
        self.assertEqual(len(self.game.pending), 1)

    def test_each_player_damage_triggers_each_master_once(self):
        self.perm(MASTER, self.a)
        self.perm(MASTER, self.b)
        self.game.resolve(self.a, Effect("damage_each_player", 1), None)
        self.assertEqual(len(self.game.pending), 2)
        self.game.settle()
        self.assertEqual(self.a.creatures[0].power, 3)
        self.assertEqual(self.b.creatures[0].power, 3)

    def test_reliquary_artifact_removed_in_response(self):
        land = self.perm(RELIQUARY, self.a)
        artifact = self.perm(card("Relic", types="Artifact"), self.a)
        self.perm(ISLAND, self.a)
        self.perm(ISLAND, self.a)
        before = len(self.a.hand)
        self.game._priority_depth += 1
        try:
            self.assertTrue(self.game.activate_ability(self.a, land, 0))
            self.game.leave_battlefield(artifact, "graveyard")
            self.game.resolve_top()
        finally:
            self.game._priority_depth -= 1
        self.assertEqual(len(self.a.hand), before)

    def test_actual_revelation_bounces_spell_and_resolves_rest(self):
        from mtgsim.carddb import CardDB
        revelation = CardDB().get("Jeskai Revelation")
        pending = StackItem(self.b, SHOCK.spell_effects, [self.a], card=SHOCK)
        self.game.stack.append(pending)
        self.resolve_spell(revelation, [pending, self.b, None, None, None])
        self.assertIn(SHOCK, self.b.hand)
        self.assertEqual((self.a.life, self.b.life), (24, 16))
        self.assertEqual(len(self.a.hand), 2)
        self.assertEqual(len(self.a.creatures), 2)

    def test_cool_but_rude_level_trigger_discards_tutored_card_and_burns(self):
        from mtgsim.carddb import CardDB
        cool = self.perm(CardDB().get("Cool but Rude"), self.a)
        cool.counters["level"] = 3
        self.a.library = [DRAGON3]
        self.a.hand = []
        self.game.fire(self.a, "class_level", cool, subject=3)
        self.game.settle()
        self.assertFalse(self.a.hand)
        self.assertIn(DRAGON3, self.a.graveyard)
        self.assertEqual(self.b.life, 18)

    def test_empty_library_still_discards_and_empty_hand_is_safe(self):
        self.a.library = []
        self.a.hand = [ISLAND]
        self.resolve_spell(TUTOR, [None, None])
        self.assertFalse(self.a.hand)
        self.assertIn(ISLAND, self.a.graveyard)
        self.resolve_spell(TUTOR, [None, None])
        self.assertFalse(self.a.hand)

    def test_return_respects_hexproof_and_stale_targets(self):
        creature = self.perm(dataclasses.replace(BEAR, keywords={"hexproof"}), self.b)
        self.assertFalse(self.game.legal_target(self.a, BOUNCE.spell_effects[0], creature))
        pending = StackItem(self.b, SHOCK.spell_effects, [self.a], card=SHOCK)
        self.game.stack.append(pending)
        self.game.stack.append(StackItem(self.a, BOUNCE.spell_effects, [pending], card=BOUNCE))
        self.game.stack.remove(pending)
        self.game.resolve_top()
        self.assertNotIn(SHOCK, self.b.hand)

    def test_amalia_uses_last_known_power_and_preserves_indestructible(self):
        amalia = self.perm(AMALIA, self.a)
        amalia.counters["+1/+1"] = 18
        survivor = self.perm(dataclasses.replace(BEAR, keywords={"indestructible"}), self.b)
        other = self.perm(BEAR, self.b)
        self.game.change_life(self.a, 1, "test")
        self.game.leave_battlefield(amalia, "graveyard")
        self.game.settle()
        self.assertEqual(self.b.creatures, [survivor])
        self.assertNotIn(other, self.b.battlefield)

    def test_spell_self_return_precedes_random_discard(self):
        from mtgsim.carddb import CardDB
        blast = CardDB().get("Hanabi Blast")
        self.assertFalse(blast.unsupported)
        self.a.hand = []
        self.resolve_spell(blast, [self.b, None, None])
        self.assertEqual(self.b.life, 18)
        self.assertFalse(self.a.hand)
        self.assertEqual(sum(c.name == "Hanabi Blast" for c in self.a.graveyard), 1)

    def test_spell_self_return_stays_in_hand_without_discard(self):
        spell = card("Recursive Flame", types="Instant", text="Return Recursive Flame to its owner's hand.")
        self.resolve_spell(spell, [None])
        self.assertIn(spell, self.a.hand)
        self.assertNotIn(spell, self.a.graveyard)
