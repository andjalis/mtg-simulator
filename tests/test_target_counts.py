"""Counts over a targeted player (#337, mtgsim/target_counts.py): the counted player is a real target, the effect
still happens to you."""
import unittest

from mtgsim.cards import _parse_effects
from mtgsim.engine import StackItem

from tests.test_cx_grammar import BEAR, DB_FILE, GOBLIN, ISLAND, Base, card

CONGREGATION = card("Test Congregation", "{W}", "Sorcery", "You gain 2 life for each creature target player controls.")
INSIGHT = card("Test Insight", "{U}", "Sorcery", "Draw cards equal to the number of cards in target opponent's hand.")
ZEALOT_LINE = "You gain 1 life for each black and/or red creature target opponent controls."
RED = card("Test Red", "{R}", "Creature — Goblin", "", 1, 1)


class Parsing(unittest.TestCase):
    def test_marker_first(self):
        effs, bad = _parse_effects(ZEALOT_LINE)
        self.assertEqual(bad, [])
        self.assertEqual((effs[0].kind, effs[0].target, effs[0].filter), ("cx_count_target", "player", "opp"))
        self.assertEqual(effs[1].data["xq"][0], "of_target")

    def test_then_splits_first(self):
        """"Draw a card, then draw a card for each ..." is the core's ", then" split: 1 plus the count."""
        effs, bad = _parse_effects("Draw a card, then draw a card for each creature target player controls.")
        self.assertEqual((bad, [e.kind for e in effs]), ([], ["draw", "cx_count_target", "draw"]))

    def test_refusals(self):
        for text in ("Target player draws a card for each creature target player controls.",
                     "You gain 2 life for each creature target player controls and each creature you control.",
                     "Destroy a creature for each creature target player controls."):
            _, bad = _parse_effects(text)
            self.assertTrue(bad, text)


class Resolving(Base):
    def cast_at(self, c, who):
        effs = list(c.spell_effects)
        self.game.stack.append(StackItem(self.a, effs, [who] + [None] * (len(effs) - 1), card=c, name=c.name))
        self.game.resolve_top()

    def test_counts_the_target_you_gain(self):
        for _ in range(3):
            self.perm(BEAR, self.b)
        self.perm(BEAR, self.a)
        self.cast_at(CONGREGATION, self.b)
        self.assertEqual((self.a.life, self.b.life), (26, 20))

    def test_targeting_yourself_counts_yours(self):
        self.perm(BEAR, self.a), self.perm(BEAR, self.b), self.perm(BEAR, self.b)
        self.cast_at(CONGREGATION, self.a)
        self.assertEqual(self.a.life, 22)

    def test_opponents_hand(self):
        self.b.hand = [ISLAND] * 4
        hand = len(self.a.hand)
        self.cast_at(INSIGHT, self.b)
        self.assertEqual(len(self.a.hand), hand + 4)

    def test_colored_filter_on_their_side(self):
        self.perm(RED, self.b), self.perm(BEAR, self.b), self.perm(RED, self.a)
        c = card("Test Zealot Spell", "{W}", "Sorcery", ZEALOT_LINE)
        self.cast_at(c, self.b)
        self.assertEqual(self.a.life, 21)

    def test_zero(self):
        self.cast_at(CONGREGATION, self.b)
        self.assertEqual(self.a.life, 20)


class DefaultAI(Base):
    def test_ai_targets_the_player_with_more_creatures(self):
        for _ in range(3):
            self.perm(GOBLIN, self.b)
        self.perm(card("Test Plains", "", "Land — Plains", "({T}: Add {W}.)"), self.a)
        self.a.life = 5
        self.a.hand = [CONGREGATION]
        self.game.step = "main2"
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(CONGREGATION, self.a.hand, "the AI didn't cast it")
        self.assertEqual(self.a.life, 11)

    def test_ai_counts_its_own_side_when_bigger(self):
        for _ in range(4):
            self.perm(GOBLIN, self.a)
        self.perm(GOBLIN, self.b)
        self.perm(card("Test Plains", "", "Land — Plains", "({T}: Add {W}.)"), self.a)
        self.a.life = 5
        self.a.hand = [CONGREGATION]
        self.game.step = "main2"
        self.a.ai.main_phase(self.game, self.a)
        self.assertEqual(self.a.life, 13)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Divine Congregation", "Recurring Insight", "Kithkin Zealot", "Honorable Scout"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


if __name__ == "__main__":
    unittest.main()
