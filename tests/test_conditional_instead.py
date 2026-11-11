"""Conditional upgrades select exactly one branch, using offline Oracle fixtures."""
import unittest

from mtgsim.cards import Effect
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import StackItem
from tests.test_cx_grammar import Base, DB_FILE
from tests.test_templates import BEAR, ISLAND, card


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class OracleCards(Base):
    def setUp(self):
        super().setUp()
        from mtgsim.carddb import CardDB
        self.db = CardDB(offline=True)

    def resolve_card(self, name, targets=None, **facts):
        c = self.db.get(name)
        self.assertEqual(c.unsupported, [], name)
        item = StackItem(self.a, list(c.spell_effects), targets or [None] * len(c.spell_effects), card=c)
        for key, value in facts.items():
            setattr(item, key, value)
        self.game.stack.append(item)
        self.game.resolve_top()
        return item


class BargainGift(OracleCards):
    def test_candy_grapple_one_pump_on_same_target(self):
        for bargained, power in ((False, 7), (True, 5)):
            with self.subTest(bargained=bargained):
                victim = self.perm(card("Giant", "{5}", "Creature — Giant", "", 10, 10), self.b)
                self.resolve_card("Candy Grapple", [victim, None], bargained=bargained)
                self.assertEqual(victim.power, power)

    def test_destroy_replaces_damage(self):
        for bargained, damage in ((False, 3), (True, 0)):
            with self.subTest(bargained=bargained):
                victim = self.perm(card("Giant", "{5}", "Creature — Giant", "Indestructible", 10, 10), self.b)
                self.game.attackers = [victim]
                self.resolve_card("Kellan's Lightblades", [victim, None], bargained=bargained)
                self.assertEqual(victim.damage, damage)
                self.assertIn(victim, self.b.battlefield)

    def test_gift_replacement_group_does_not_double_mass_damage(self):
        for gifted in (False, True):
            with self.subTest(gifted=gifted):
                victim = self.perm(card("Giant", "{5}", "Creature — Giant", "", 10, 10), self.b)
                before = self.b.life
                self.resolve_card("Wildfire Howl", [None, self.b, None], gifted=gifted)
                self.assertEqual(victim.damage, 2)
                self.assertEqual(before - self.b.life, int(gifted))
                self.b.battlefield.remove(victim)

    def test_different_kind_without_a_reference_stays_unmatched(self):
        effects, bad = _parse_effects("Draw a card. If the gift was promised, you gain 3 life instead.", opts=True)
        self.assertTrue(bad)
        self.assertEqual(len(effects), 1)
        self.assertEqual(effects[0].cond, "")


class BranchChoice(Base):
    def test_unbound_compound_replacement_does_not_leak_an_effect(self):
        effects, bad = _parse_effects("If a creature died this turn, instead scry 3, then draw three cards.")
        self.assertTrue(bad)
        self.assertEqual(effects, [])

    def test_control_condition_uses_the_board_at_resolution(self):
        spell = self.spell("Draw a card. If you control a Wizard, draw three cards instead.")
        for enabled, count in ((False, 1), (True, 3)):
            if enabled:
                self.perm(card("Wizard", "{U}", "Creature — Wizard", "", 1, 1), self.a)
            before = len(self.a.hand)
            self.cast(spell)
            self.assertEqual(len(self.a.hand) - before, count)

    def test_morbid_damage_cannot_enable_the_other_branch(self):
        spell = self.spell("~ deals 2 damage to target creature. If a creature died this turn, it deals 5 damage instead.")
        victim = self.perm(BEAR, self.b)
        seen = []
        resolve = self.game.resolve

        def record(p, eff, *args):
            seen.append(eff.amount)
            return resolve(p, eff, *args)

        self.game.resolve = record
        self.cast(spell, [victim, None])
        self.assertEqual(seen, [2])
        self.assertTrue(self.game.creature_died_turn)

    def test_base_condition_is_preserved(self):
        effects, bad = _parse_effects("If you control a creature, draw a card. "
                                      "If a creature died this turn, draw two cards instead.")
        self.assertEqual(bad, [])
        before = len(self.a.hand)
        self.game.stack.append(StackItem(self.a, effects, [None] * len(effects)))
        self.game.resolve_top()
        self.assertEqual(len(self.a.hand), before)
        self.assertFalse(self.game.check_cond(self.a, Effect("draw", cond=effects[0].cond), None, None))


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class ThresholdMorbid(OracleCards):
    def test_real_oracle_replacement_paragraphs_parse(self):
        for name in ("Tragic Slip", "Brimstone Volley", "Thermal Blast", "Grizzly Fate", "Cabal Ritual",
                     "Far Wanderings", "Predator's Howl", "Hunger of the Howlpack", "Toxic Stench",
                     "Mirran Mettle", "Feed the Clan", "Kirtar's Wrath", "Kamahl's Sledge"):
            with self.subTest(name=name):
                self.assertEqual(self.db.get(name).unsupported, [])

    def test_morbid_and_threshold_damage(self):
        for name, attr, base, upgrade in (("Brimstone Volley", "morbid", 3, 5),
                                          ("Thermal Blast", "threshold", 3, 5)):
            for enabled in (False, True):
                with self.subTest(name=name, enabled=enabled):
                    self.game.creature_died_turn = attr == "morbid" and enabled
                    self.a.graveyard = [BEAR] * (7 if attr == "threshold" and enabled else 6)
                    victim = self.perm(card("Giant", "{5}", "Creature — Giant", "", 10, 10), self.b)
                    self.resolve_card(name, [victim, None])
                    self.assertEqual(victim.damage, upgrade if enabled else base)

    def test_threshold_tokens_and_mana_are_replaced(self):
        for size, tokens, mana in ((6, 2, 3), (7, 4, 5)):
            with self.subTest(size=size):
                self.a.graveyard = [BEAR] * size
                before = len(self.a.creatures)
                self.resolve_card("Grizzly Fate")
                self.assertEqual(len(self.a.creatures) - before, tokens)
                self.a.graveyard = [BEAR] * size
                before = len(self.a.pool)
                self.resolve_card("Cabal Ritual")
                self.assertEqual(len(self.a.pool) - before, mana)

    def test_wrath_cannot_enable_threshold_and_upgrade_blocks_regeneration(self):
        for size in (6, 7):
            with self.subTest(size=size):
                self.a.battlefield.clear()
                self.b.battlefield.clear()
                self.a.graveyard = [BEAR] * size
                victim = self.perm(BEAR, self.a)
                victim.regeneration_shields = 1
                self.resolve_card("Kirtar's Wrath")
                self.assertNotIn(victim, self.a.battlefield)
                self.assertEqual(len(self.a.creatures), 2 if size == 7 else 0)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class CastOrigin(OracleCards):
    def test_token_referent_preserves_characteristics(self):
        for zone, count in (("hand", 5), ("graveyard", 10)):
            with self.subTest(zone=zone):
                self.a.battlefield.clear()
                self.resolve_card("Increasing Devotion", cast_zone=zone)
                self.assertEqual(len(self.a.creatures), count)
                self.assertTrue(all("Human" in x.card.subtypes and x.power == x.toughness == 1
                                    and x.card.colors == frozenset({"W"}) for x in self.a.creatures))

    def test_variable_token_count_uses_graveyard_and_keeps_tapped(self):
        self.a.graveyard = [BEAR] * 3
        for zone, count in (("hand", 2), ("graveyard", 3)):
            with self.subTest(zone=zone):
                self.a.battlefield.clear()
                self.resolve_card("The Final Days", cast_zone=zone)
                self.assertEqual(len(self.a.creatures), count)
                self.assertTrue(all(x.tapped and x.power == x.toughness == 2 and "Horror" in x.card.subtypes
                                    for x in self.a.creatures))

    def test_increasing_confusion_doubles_x_only_from_graveyard(self):
        for zone, count in (("hand", 3), ("graveyard", 6)):
            with self.subTest(zone=zone):
                before = len(self.b.library)
                self.resolve_card("Increasing Confusion", [self.b, None], cast_zone=zone, x=3)
                self.assertEqual(before - len(self.b.library), count)

    def test_stonesplitter_bolt_doubles_x_only_when_bargained(self):
        for bargained, count in ((False, 3), (True, 6)):
            with self.subTest(bargained=bargained):
                victim = self.perm(card("Giant", "{5}", "Creature — Giant", "", 10, 10), self.b)
                self.resolve_card("Stonesplitter Bolt", [victim, None], bargained=bargained, x=3)
                self.assertEqual(victim.damage, count)

    def test_token_reference_without_matching_token_stays_unmatched(self):
        effects, bad = _parse_effects("Draw a card. If this spell was cast from a graveyard, create ten of those tokens instead.")
        self.assertTrue(bad)
        self.assertEqual(len(effects), 1)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class AbilityWordParagraph(OracleCards):
    def test_fateful_hour_tokens_replace_the_base(self):
        for life, tokens in ((20, 2), (5, 5)):
            with self.subTest(life=life):
                self.a.life = life
                self.a.battlefield.clear()
                before = len(self.a.creatures)
                self.resolve_card("Gather the Townsfolk")
                self.assertEqual(len(self.a.creatures) - before, tokens)

    def test_addendum_group_replaces_draw_with_scry_then_draw(self):
        c = self.db.get("Precognitive Perception")
        self.assertEqual(c.unsupported, [])
        self.assertEqual([(e.kind, e.data.get("instead_branch")) for e in c.spell_effects],
                         [("draw", False), ("scry", True), ("draw", True)])
        self.assertEqual({id(e.data["instead_gate"]) for e in c.spell_effects}, {id(c.spell_effects[0].data["instead_gate"])})
        for step in ("upkeep", "main1"):
            with self.subTest(step=step):
                self.a.hand.clear()
                self.a.library = [BEAR] * 10
                self.game.step = step
                self.resolve_card("Precognitive Perception")
                self.assertEqual(len(self.a.hand), 3)

    def test_delirium_tutor_replaces_the_base_search(self):
        zap = card("Zap", "{R}", "Instant", "")
        thoughtseize = card("Thoughtseize", "{B}", "Sorcery", "")
        self.a.library = [BEAR] * 10
        for gy, in_hand in (((BEAR, ISLAND, zap), 0), ((BEAR, ISLAND, zap, thoughtseize), 1)):
            with self.subTest(delirium=len(gy) >= 4):
                self.a.hand.clear()
                self.a.graveyard = list(gy)
                self.resolve_card("Traverse the Ulvenwald")
                self.assertEqual(len(self.a.hand), in_hand)

    def test_sea_gate_stormcaller_kicked_doubles_the_delayed_copy(self):
        c = self.db.get("Sea Gate Stormcaller")
        self.assertEqual(c.unsupported, [])
        etb = next(t for t in c.triggers if t.event == "etb")
        self.assertEqual([(e.kind, e.data.get("n"), e.data.get("instead_branch"), e.data.get("max_cmc"))
                          for e in etb.effects],
                         [("copy_next_spell", 1, False, 2), ("copy_next_spell", 2, True, 2)])
