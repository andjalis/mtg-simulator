"""Copy effects select a specific spell and recheck its restrictions on resolution."""
import dataclasses
import random
import unittest

from mtgsim import copies
from mtgsim.carddb import CardDB
from mtgsim.engine import Game, Permanent, Player, StackItem
from tests.test_templates import BEAR, ISLAND, SHOCK, card

TWINCAST = card("Twincast", "{U}{U}", "Instant", "Copy target instant or sorcery spell. You may choose new targets for the copy.")
OWN = card("Own Copy", "{U}{U}", "Instant", "Copy target instant or sorcery spell you control.")
EXPANSION = card("Expansion", "{U}{R}", "Instant", "Copy target instant or sorcery spell with mana value 4 or less.")
MIRROR = card("Mirror Sheen", "{1}{U}{R}", "Enchantment", "{1}{U/R}{U/R}: Copy target instant or sorcery spell that targets you.")
ERRANT = card("Errant", "{U}", "Creature — Human", "{1}{U}, {T}: Copy target spell you control that wasn't cast.", 0, 3)


class SpellCopyTargetTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Player("a", [], None), Player("b", [], None)
        self.game = Game(self.a, self.b, random.Random(0), log=True)
        self.a.library, self.b.library = [ISLAND] * 20, [ISLAND] * 20

    def spell(self, c=SHOCK, controller=None, targets=None, kind="spell"):
        it = StackItem(controller or self.b, list(c.spell_effects), targets or [self.a], card=c, kind=kind)
        self.game.stack.append(it)
        return it

    def copy(self, c, target):
        item = StackItem(self.a, c.spell_effects, [target], card=c)
        self.game.stack.append(item)
        self.game.resolve_top()
        return item

    def test_templates(self):
        for c in (TWINCAST, OWN, EXPANSION, MIRROR, ERRANT):
            self.assertEqual(c.unsupported, [], c.name)

    def test_copy_opponents_spell_under_our_control(self):
        spell = self.spell()
        self.copy(TWINCAST, spell)
        cp = self.game.stack[-1]
        self.assertIsNot(cp, spell)
        self.assertIs(cp.controller, self.a)
        self.assertEqual(cp.kind, "copy")
        self.game.resolve_top()
        self.assertEqual((self.a.life, self.b.life), (20, 18))
        self.assertIn(spell, self.game.stack)

    def test_cast_checks_copy_targets_without_requiring_a_counter_effect(self):
        self.game.turn, self.game.step = 1, "main1"
        for _ in range(2):
            self.a.battlefield.append(Permanent(ISLAND, self.a))
        self.a.hand = [TWINCAST]
        self.assertFalse(self.game.can_cast_now(self.a, TWINCAST))
        spell = self.spell()
        self.assertTrue(self.game.can_cast_now(self.a, TWINCAST))
        self.assertTrue(self.game.cast(self.a, TWINCAST, [spell]))
        self.assertEqual((self.a.life, self.b.life), (18, 18))

    def test_copy_uses_selected_spell_not_last_or_biggest_spell(self):
        chosen = self.spell()
        newer = self.spell(card("Newer", "{5}{R}", "Instant", "Draw three cards."), self.a)
        self.copy(TWINCAST, chosen)
        self.assertEqual(self.game.stack[-1].card.name, SHOCK.name)
        self.assertIn(newer, self.game.stack)

    def test_own_scope_excludes_opponents_and_abilities(self):
        self.spell()
        mine = self.spell(controller=self.a)
        self.game.stack.append(StackItem(self.a, [], [], kind="ability"))
        self.assertEqual(self.game.legal_targets(self.a, OWN.spell_effects[0]), [mine])
        self.assertEqual(self.game.auto_targets(self.a, OWN.spell_effects), [mine])

    def test_type_restriction_and_uncounterable_spell(self):
        creature = self.spell(BEAR)
        spell = self.spell(dataclasses.replace(SHOCK, uncounterable=True))
        legal = self.game.legal_targets(self.a, TWINCAST.spell_effects[0])
        self.assertNotIn(creature, legal)
        self.assertIn(spell, legal)

    def test_missing_target_fizzles_without_picking_a_replacement(self):
        gone = self.spell()
        self.game.stack.remove(gone)
        other = self.spell(controller=self.a)
        item = self.copy(TWINCAST, gone)
        self.assertFalse(item.resolved)
        self.assertEqual(self.game.stack, [other])

    def test_controller_change_rechecks_you_control(self):
        original = self.spell(controller=self.a)
        original.controller = self.b
        item = self.copy(OWN, original)
        self.assertFalse(item.resolved)
        self.assertEqual(self.game.stack, [original])

    def test_mana_value_limit_counts_stack_x(self):
        s = self.spell(card("X spell", "{X}{X}{U}", "Instant", cmc=1))
        eff = EXPANSION.spell_effects[0]
        s.x = 1
        self.assertEqual(self.game.legal_targets(self.a, eff), [s])
        s.x = 2
        self.assertEqual(self.game.legal_targets(self.a, eff), [])

    def test_only_spells_targeting_you_qualify(self):
        yours = self.spell(targets=[self.a])
        self.spell(targets=[self.b])
        self.assertEqual(self.game.legal_targets(self.a, MIRROR.activated[0].effects[0]), [yours])
        yours.targets = [self.b]
        self.assertEqual(self.game.legal_targets(self.a, MIRROR.activated[0].effects[0]), [])

    def test_not_cast_restricts_to_your_spell_copies(self):
        self.spell(controller=self.a)
        self.spell(kind="copy")
        own_copy = self.spell(controller=self.a, kind="copy")
        self.assertEqual(self.game.legal_targets(self.a, ERRANT.activated[0].effects[0]), [own_copy])

    def test_artifact_and_permanent_spell_types(self):
        rock = self.spell(card("Rock", "{2}", "Artifact"), self.a)
        bear = self.spell(BEAR, self.a)
        self.spell(SHOCK, self.a)
        c = card("Drafna", "{U}", "Creature — Human", "{3}, {T}: Copy target artifact spell you control.", 2, 1)
        eff = c.activated[0].effects[0]
        self.assertEqual(self.game.legal_targets(self.a, eff), [rock])
        copies.resolve(self.game, self.a, eff, rock)
        self.game.resolve_top()
        self.assertTrue(self.a.battlefield[-1].card.is_token)
        c = card("Engine", "{4}", "Artifact", "{4}, {T}: Copy target permanent spell you control.")
        self.assertEqual(self.game.legal_targets(self.a, c.activated[0].effects[0]), [rock, bear])

    def test_copy_of_copy_spell_preserves_its_chosen_spell_target(self):
        original = self.spell(controller=self.a)
        twin = self.spell(TWINCAST, self.a, targets=[original])
        self.copy(TWINCAST, twin)
        self.assertIs(self.game.stack[-1].targets[0], original)
        self.game.resolve_top()
        self.assertEqual(self.game.stack[-1].card.name, SHOCK.name)

    def test_replacement_that_spell_uses_initial_target(self):
        c = card("Increasing Vengeance", "{R}{R}", "Instant", "Copy target instant or sorcery spell you control. "
                 "If this spell was cast from a graveyard, copy that spell twice instead. You may choose new targets for the copies.")
        original = self.spell(controller=self.a)
        item = StackItem(self.a, c.spell_effects, [original, None], card=c)
        item.cast_zone = "graveyard"
        self.game.stack.append(item)
        self.game.resolve_top()
        self.assertEqual(sum(s.kind == "copy" for s in self.game.stack), 2)

    def test_fork_copy_is_red_and_original_keeps_its_color(self):
        fork = card("Fork", "{R}{R}", "Instant", "Copy target instant or sorcery spell, except that the copy is red. You may choose new targets for the copy.")
        blue = card("Blue spell", "{U}", "Instant", "Draw a card.")
        original = self.spell(blue)
        self.assertEqual(fork.unsupported, [])
        self.copy(fork, original)
        cp = self.game.stack[-1]
        self.assertEqual(cp.card.colors, frozenset("R"))
        self.assertEqual(original.card.colors, frozenset("U"))
        self.assertEqual(cp.card.mana_cost, original.card.mana_cost)
        # The red exception remains a copiable characteristic.
        self.copy(TWINCAST, cp)
        self.assertEqual(self.game.stack[-1].card.colors, frozenset("R"))

    def test_double_major_creates_a_nonlegendary_token(self):
        major = card("Double Major", "{G}{U}", "Instant", "Copy target creature spell you control, except it isn't legendary if the spell is legendary.")
        legendary = dataclasses.replace(BEAR, legendary=True)
        original = self.spell(legendary, self.a)
        self.assertEqual(major.unsupported, [])
        self.copy(major, original)
        self.game.resolve_top()
        token = self.a.battlefield[-1]
        self.assertTrue(token.card.is_token)
        self.assertFalse(token.card.legendary)
        self.assertTrue(original.card.legendary)

    def test_unknown_copy_restrictions_stay_visible(self):
        c = card("Restricted", "{U}", "Instant", "Copy target instant or sorcery spell that targets a commander.")
        self.assertTrue(c.unsupported)

    def test_real_database_candidates(self):
        db = CardDB(offline=True)
        if db._all is None:
            self.skipTest("offline card database is missing")
        for n in ("Expansion // Explosion", "Drafna, Founder of Lat-Nam", "Errant, Street Artist", "Mirror Sheen", "Izzet Guildmage", "Lithoform Engine", "Fork", "Double Major"):
            self.assertEqual(db.get(n).unsupported, [], n)


if __name__ == "__main__":
    unittest.main()
