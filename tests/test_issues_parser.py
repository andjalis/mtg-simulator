"""Parser issues: #260 (compound split keeps the player subject), #282 (optional targets, qualifier combos)."""
import unittest

from mtgsim.cards import parse as P

from tests.test_cx_grammar import BEAR, Base
from tests.test_templates import card


class CompoundSubject(Base):
    """#260: "Target player <A> and <B>": both verbs belong to the target player, not the caster."""

    def test_second_verb_not_split_off(self):
        for text in ("Target player loses 2 life and mills two cards.",
                     "Target opponent discards a card and loses 2 life."):
            effs, bad = P._parse_effects(text)
            self.assertEqual(bad, [], text)
            self.assertEqual([e.kind for e in effs], ["cx_players"], text)

    def test_own_subject_second_piece_still_splits(self):
        effs, bad = P._parse_effects("Each opponent loses 1 life and you gain 1 life.")
        self.assertEqual(bad, [])
        self.assertEqual([e.kind for e in effs], ["drain", "gain_life"])

    def test_you_compound_still_splits(self):
        effs, bad = P._parse_effects("You gain 3 life and draw a card.")
        self.assertEqual(bad, [])
        self.assertEqual(len(effs), 2)

    def test_game_target_player_does_both(self):
        c = self.spell("Target player loses 2 life and mills two cards.", "Sorcery")
        self.a.library = [c] * 5
        self.b.library = [c] * 5
        life_a, life_b = self.a.life, self.b.life
        self.cast(c, targets=[self.b])
        self.assertEqual(self.b.life, life_b - 2)
        self.assertEqual(len(self.b.library), 3)
        self.assertEqual(self.a.life, life_a)
        self.assertEqual(len(self.a.library), 5)

    def test_game_where_x_is_zombies_you_control(self):
        """Lich Lord of Unx: both effects hit the chosen player and scale with the caster's Zombies."""
        c = self.spell("Target player loses X life and mills X cards, where X is the number of Zombies you control.",
                       "Sorcery")
        zombie = card("Zed", "{1}{B}", "Creature — Zombie", "", 1, 1)
        self.perm(zombie, self.a)
        self.perm(zombie, self.a)
        self.perm(BEAR, self.a)
        self.a.library = [c] * 5
        self.b.library = [c] * 5
        life_a, life_b = self.a.life, self.b.life
        self.cast(c, targets=[self.b])
        self.assertEqual(self.b.life, life_b - 2)
        self.assertEqual(len(self.b.library), 3)
        self.assertEqual(self.a.life, life_a)
        self.assertEqual(len(self.a.library), 5)


class OptionalTargets(Base):
    """#282: "up to one target ..." stays optional."""

    def test_optional_flag_parsed(self):
        for text in ("Tap up to one target creature.", "Tap up to one target creature an opponent controls.",
                     "Destroy up to one target land.", "Destroy up to one target artifact or enchantment.",
                     "Return up to one target creature to its owner's hand.",
                     "~ deals 3 damage to up to one target creature."):
            effs, bad = P._parse_effects(text)
            self.assertEqual(bad, [], text)
            self.assertTrue(effs[0].data.get("optional_target"), text)

    def test_mandatory_stays_mandatory(self):
        for text in ("Tap target creature.", "Destroy target land.", "Destroy target artifact or enchantment.",
                     "Return target creature to its owner's hand.", "~ deals 3 damage to target creature."):
            effs, bad = P._parse_effects(text)
            self.assertEqual(bad, [], text)
            self.assertFalse(effs[0].data.get("optional_target"), text)

    def test_game_resolves_with_no_target(self):
        for text in ("Tap up to one target creature.", "Destroy up to one target land.",
                     "Return up to one target creature to its owner's hand."):
            self.setUp()
            c = self.spell(text)
            mine = self.perm(BEAR, self.a)
            theirs = self.perm(BEAR, self.b)
            self.assertTrue(self.game.legal_target(self.a, c.spell_effects[0], None), text)
            self.cast(c, targets=[None])
            self.assertIn(mine, self.a.battlefield)
            self.assertIn(theirs, self.b.battlefield)
            self.assertFalse(theirs.tapped, text)

    def test_game_optional_target_still_hits_a_target(self):
        c = self.spell("Tap up to one target creature an opponent controls.")
        theirs = self.perm(BEAR, self.b)
        self.cast(c, targets=[theirs])
        self.assertTrue(theirs.tapped)

    def test_mandatory_rejects_no_target(self):
        c = self.spell("Tap target creature.")
        self.assertFalse(self.game.legal_target(self.a, c.spell_effects[0], None))


class QualifierCombos(Base):
    """#282: a controller qualifier together with another filter, and stacked adjectives."""

    def targets(self, text, setup):
        c = self.spell(text)
        perms = setup()
        found = self.game.legal_targets(self.a, c.spell_effects[0])
        return {name for name, x in perms.items() if x in found}

    def test_tapped_creature_an_opponent_controls(self):
        def setup():
            p = {k: self.perm(BEAR, o) for k, o in (("my_tapped", self.a), ("their_tapped", self.b),
                                                    ("their_untapped", self.b))}
            p["my_tapped"].tapped = p["their_tapped"].tapped = True
            return p
        self.assertEqual(self.targets("Destroy target tapped creature an opponent controls.", setup),
                         {"their_tapped"})

    def test_nonblack_creature_an_opponent_controls(self):
        black = card("Blk", "{B}", "Creature — Zombie", "", 2, 2)

        def setup():
            return {"my_bear": self.perm(BEAR, self.a), "their_bear": self.perm(BEAR, self.b),
                    "their_black": self.perm(black, self.b)}
        self.assertEqual(self.targets("Destroy target nonblack creature an opponent controls.", setup),
                         {"their_bear"})

    def test_nonwhite_attacking_creature_needs_both(self):
        white = card("Wht", "{W}", "Creature — Human", "", 2, 2)

        def setup():
            p = {"bear_att": self.perm(BEAR, self.b), "bear_idle": self.perm(BEAR, self.b),
                 "white_att": self.perm(white, self.b), "white_idle": self.perm(white, self.b)}
            self.game.attackers = [p["bear_att"], p["white_att"]]
            return p
        self.assertEqual(self.targets("Destroy target nonwhite attacking creature.", setup), {"bear_att"})

    def test_adjective_or_still_alternates(self):
        from mtgsim.cx_events import _object_subject
        self.assertEqual(_object_subject("a white or blue instant or sorcery")["alts"],
                         [("white", "instant"), ("white", "sorcery"), ("blue", "instant"), ("blue", "sorcery")])
        self.assertEqual(_object_subject("a red or blue creature")["alts"], [("red", "creature"), ("blue", "creature")])


if __name__ == "__main__":
    unittest.main()


class FalseFullXQuantities(unittest.TestCase):
    """Player clauses whose X the engine can't read yet stay unmatched instead of counting the wrong thing."""

    def test_named_card_count_not_full(self):
        c = card("Mind Burst", "{1}{B}", "Sorcery", "Target player discards X cards, where X is one plus the number "
                 "of cards named Mind Burst in all graveyards.")
        self.assertTrue(c.unsupported)

    def test_that_spells_mana_value_not_full(self):
        _, bad = P._parse_effects("You may have target player mill X cards, where X is that spell's mana value.")
        self.assertTrue(bad)


class OneOrTwoTargets(Base):
    """#312: "one or two target <np>" = a required target plus an optional second one."""

    def test_parse_flags(self):
        effs, bad = P._parse_effects("One or two target creatures each gain haste until end of turn.")
        self.assertEqual(bad, [])
        self.assertEqual(len(effs), 2)
        self.assertFalse(effs[0].data.get("optional_target"))
        self.assertTrue(effs[1].data.get("optional_target"))

    def test_up_to_one_or_two_stays_unmatched(self):
        _, bad = P._parse_effects("Up to one or two target creatures each gain haste until end of turn.")
        self.assertTrue(bad)

    def test_game_second_target_omitted(self):
        c = self.spell("One or two target creatures each gain haste until end of turn.")
        mine = self.perm(BEAR, self.a)
        self.assertFalse(self.game.legal_target(self.a, c.spell_effects[0], None))
        self.assertTrue(self.game.legal_target(self.a, c.spell_effects[1], None))
        self.cast(c, targets=[mine, None])
        self.assertTrue(mine.has("haste"))

    def test_object_position(self):
        effs, bad = P._parse_effects("Return one or two target attacking creatures to their owner's hand.")
        self.assertEqual(bad, [])
        self.assertEqual([bool(e.data.get("optional_target")) for e in effs], [False, True])


class DamageToEachOfTargets(Base):
    """#320: "deals N damage to each of two targets" and "... each of up to two other targets"."""

    def test_two_targets_deal_damage(self):
        c = self.spell("~ deals 2 damage to each of two targets.")
        x, y = self.perm(BEAR, self.b), self.perm(BEAR, self.b)
        life = self.b.life
        self.cast(c, targets=[x, y])
        self.assertEqual((x.damage, y.damage, self.b.life), (2, 2, life))

    def test_same_target_twice_is_rejected(self):
        c = self.spell("~ deals 2 damage to each of two targets.")
        x = self.perm(BEAR, self.b)
        self.cast(c, targets=[x, x])
        self.assertEqual(x.damage, 2)               # only one of the two hits lands

    def test_any_target_then_other_targets(self):
        c = self.spell("~ deals 4 damage to any target and 3 damage to each of up to two other targets.")
        self.assertEqual(len(c.spell_effects), 3)
        self.assertEqual([bool(e.data.get("optional_target")) for e in c.spell_effects], [False, True, True])
        x = self.perm(BEAR, self.b)
        life = self.b.life
        self.cast(c, targets=[self.b, x, None])
        self.assertEqual((self.b.life, x.damage), (life - 4, 3))

    def test_other_without_first_target_unmatched(self):
        _, bad = P._parse_effects("~ deals 2 damage to each of two other targets.")
        self.assertTrue(bad)

    def test_variable_count_unmatched(self):
        _, bad = P._parse_effects("~ deals 4 damage to each of X targets.")
        self.assertTrue(bad)


class MayHaveItDeal(Base):
    """#319: "you may have it deal ... / fight ..." (base-form verb after "have")."""

    def test_parses(self):
        for text in ("You may have ~ deal 2 damage to target creature.",
                     "You may have it deal 3 damage to target creature.",
                     "You may have it deal damage equal to its power to target creature.",
                     "You may have it fight target creature you don't control."):
            effs, bad = P._parse_effects(text)
            self.assertEqual(bad, [], text)
            self.assertTrue(effs, text)

    def test_still_optional(self):
        effs, _ = P._parse_effects("You may have it deal 3 damage to target creature.")
        self.assertTrue(any(e.kind == "pay_gate" or e.data.get("may_hostile") for e in effs))

    def test_other_verbs_unmatched(self):
        _, bad = P._parse_effects("You may have it explode violently.")
        self.assertTrue(bad)
    def test_that_spells_mana_value_reads_the_referenced_spell(self):
        effs, bad = P._parse_effects("You may have target player mill X cards, where X is that spell's mana value.")
        self.assertEqual(bad, [])
        wrapper = next(e for e in effs if e.kind == "cx_players")
        self.assertEqual(wrapper.data["xq"], ("spell", "mana value"))
