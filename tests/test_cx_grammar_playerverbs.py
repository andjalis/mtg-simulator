"""Grammar player verbs (mtgsim.cx_grammar_playerverbs): imperative draws / discards / mills, random discards and
whole-hand discards for player subjects."""
import unittest

from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import StackItem

from tests.test_cx_grammar import BEAR, DB_FILE, ISLAND, Base, card


class Parsing(unittest.TestCase):
    def kinds(self, s):
        effs = parse_sentence(s)
        return None if effs is None else [e.kind for e in effs]

    def test_imperative(self):
        self.assertEqual(self.kinds("Draw two cards, then discard a card."), ["draw", "discard"])
        self.assertEqual(self.kinds("Draw four cards, then discard three cards at random."),
                         ["draw", "cx_discard_random"])
        self.assertEqual(self.kinds("Discard your hand."), ["cx_discard_hand"])
        self.assertEqual(self.kinds("Mill three cards."), ["mill"])

    def test_player_subjects(self):
        effs = parse_sentence("Target player discards two cards at random.")
        self.assertEqual((effs[0].kind, effs[0].target, effs[0].data["side"]), ("cx_players", "player", "theirs"))
        self.assertEqual([e.kind for e in effs[0].data["effects"]], ["cx_discard_random"])
        effs = parse_sentence("Each player discards their hand, then draws seven cards.")
        self.assertEqual([e.kind for e in effs[0].data["effects"]], ["cx_discard_hand", "draw"])

    def test_rejections(self):
        for s in ("Draw a cards.", "Draw two card.", "Each player discards your hand.", "Discard their hand.",
                  "Target player draws X cards.", "Draw two cards until end of turn.",
                  "Discard two cards at random this turn."):
            self.assertIsNone(parse_sentence(s), s)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_cards_parse_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        db = CardDB()
        for name in ("Goblin Lore", "Control of the Court", "Drastic Revelation", "Hymn to Tourach", "Mind Twist",
                     "Mind Shatter", "Wit's End", "Sire of Insanity", "Mindslicer"):
            row = card_coverage(db.get(name))
            self.assertEqual(row.status, FULL, (name, row.ignored))


class Resolving(Base):
    def test_draw_then_discard_at_random(self):
        self.a.hand = []
        self.cast(self.spell("Draw four cards, then discard three cards at random.", "Sorcery"))
        self.assertEqual((len(self.a.hand), len(self.a.graveyard)), (1, 4))      # three discarded + the spell

    def test_target_player_random_discard_with_x(self):
        self.b.hand = [BEAR] * 5
        c = self.spell("Target player discards X cards at random.", "Sorcery")
        item = StackItem(self.a, list(c.spell_effects), [self.b], card=c, name=c.name)
        item.x = 3
        self.game.stack.append(item)
        self.game.resolve_top()
        self.assertEqual((len(self.b.hand), len(self.b.graveyard)), (2, 3))

    def test_wheel(self):
        self.a.hand, self.b.hand = [BEAR] * 2, [BEAR] * 4
        self.cast(self.spell("Each player discards their hand, then draws seven cards.", "Sorcery"))
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (7, 7))
        self.assertEqual(len(self.b.graveyard), 4)

    def test_discard_your_hand_is_only_yours(self):
        self.a.hand, self.b.hand = [BEAR] * 3, [BEAR] * 3
        self.cast(self.spell("Discard your hand."))
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (0, 3))


class DefaultAI(Base):
    """The default AI casts the new shapes and aims them at the right player."""
    def main_phase(self, text, cost="{U}", lands=1):
        spell = card("Test Spell", cost, "Sorcery", text)
        self.assertEqual(spell.unsupported, [], text)
        for _ in range(lands):
            self.perm(ISLAND, self.a)
        self.a.hand = [spell]
        self.b.hand = [BEAR] * 4
        self.game.step = "main2"
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand, "the AI didn't cast it")

    def test_random_discard_at_the_opponent(self):
        self.main_phase("Target player discards two cards at random.")
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (0, 2))

    def test_x_random_discard_pays_x(self):
        self.main_phase("Target player discards X cards at random.", cost="{X}{U}", lands=4)
        self.assertEqual(len(self.b.hand), 1)

    def test_target_player_discards_their_hand(self):
        self.main_phase("Target player discards their hand.")
        self.assertEqual(len(self.b.hand), 0)

    def test_draw_then_discard_at_random_for_itself(self):
        self.main_phase("Draw four cards, then discard three cards at random.")
        self.assertEqual((len(self.a.hand), len(self.b.hand)), (1, 4))


if __name__ == "__main__":
    unittest.main()
