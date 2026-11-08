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
