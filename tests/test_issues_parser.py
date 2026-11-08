"""Parser issues: #260 (compound split keeps the player subject), #282 (optional targets, qualifier combos)."""
import unittest

from mtgsim.cards import parse as P

from tests.test_cx_grammar import Base


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


if __name__ == "__main__":
    unittest.main()
