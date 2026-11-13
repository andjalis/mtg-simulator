"""#337: counts that come from a draw earlier in the same resolution (Laquatus's Creativity, Ancient Excavation,
"for each card drawn this way")."""
import unittest

from mtgsim.cards import parse as P
from mtgsim.cx_grammar import parse_sentence
from mtgsim.engine import StackItem

from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import BEAR, ISLAND, card

LAQUATUS = "Target player draws cards equal to the number of cards in their hand, then discards that many cards."
DOUBLER = card("Test Doubler", "{3}", "Enchantment", "If you would draw a card, draw two cards instead.")
EXCAVATION = "Draw cards equal to the number of cards in your hand, then discard a card for each card drawn this way."


class Parsing(unittest.TestCase):
    def test_shapes(self):
        e = parse_sentence(LAQUATUS)[0]
        self.assertEqual((e.data["who"], e.data["xq"], e.data["xq_rel"], [x.kind for x in e.data["effects"]]),
                         ("target", ("hand",), True, ["draw", "discard"]))
        e = parse_sentence(EXCAVATION)[0]
        self.assertEqual((e.data["who"], e.data["xq"], e.data.get("xq_rel"), [x.kind for x in e.data["effects"]]),
                         ("you", ("hand",), None, ["draw", "cx_discard_drawn"]))
        effs, bad = P._parse_effects("Draw three cards. You lose 1 life for each card drawn this way.")
        self.assertEqual((bad, effs[1].data["xq"]), ([], ("this_way", "drawn", "card")))

    def test_refusals(self):
        for s in ("Draw cards equal to the number of cards in their hand, then discard that many cards.",
                  "Target player draws cards equal to the number of cards in their hand, then discard that many cards.",
                  "Target player draws cards equal to the number of cards in your hand, then discards that many cards.",
                  "Draw cards equal to the number of cards in your hand, then discard a card for each land drawn "
                  "this way."):
            self.assertIsNone(parse_sentence(s), s)


class Behaviour(Base):
    def resolve(self, text, target=None):
        c = self.spell(text, "Sorcery")
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [target] * len(c.spell_effects), card=c,
                                         name=c.name))
        self.game.resolve_top()

    def test_laquatus_on_the_target(self):
        self.a.hand, self.b.hand = [BEAR], [BEAR] * 3
        self.resolve(LAQUATUS, self.b)
        self.assertEqual((len(self.a.hand), len(self.b.hand), len(self.b.graveyard)), (1, 3, 3))

    def test_laquatus_hand_size_read_before_drawing(self):
        self.b.hand = [BEAR] * 3            # draws three (not more as the hand grows), then discards three
        self.resolve(LAQUATUS, self.b)
        self.assertEqual((len(self.b.hand), len(self.b.graveyard)), (3, 3))

    def test_zero(self):
        self.resolve(LAQUATUS, self.b)
        self.assertEqual((len(self.b.hand), len(self.b.graveyard)), (0, 0))

    def test_excavation_discards_what_was_drawn(self):
        self.a.hand = [BEAR] * 2
        self.resolve(EXCAVATION)
        self.assertEqual((len(self.a.hand), len(self.a.graveyard)), (2, 3))      # two discarded and the spell

    def test_excavation_counts_actual_draws(self):
        # a replacement doubles each draw: two draw instructions, four cards actually drawn and discarded
        self.perm(DOUBLER, self.a)
        self.a.hand = [BEAR] * 2
        self.resolve(EXCAVATION)
        self.assertEqual((len(self.a.hand), len(self.a.graveyard)), (2, 5))

    def test_laquatus_that_many_ignores_the_replacement(self):
        self.perm(DOUBLER, self.b)
        self.b.hand = [BEAR] * 2
        self.resolve(LAQUATUS, self.b)      # draws four, discards the two it was told to draw
        self.assertEqual((len(self.b.hand), len(self.b.graveyard)), (4, 2))

    def test_lose_life_for_each_card_drawn_this_way(self):
        self.resolve("Draw three cards. You lose 1 life for each card drawn this way.")
        self.assertEqual(self.a.life, 17)
        self.perm(DOUBLER, self.a)
        self.resolve("Draw two cards. You lose 1 life for each card drawn this way.")
        self.assertEqual(self.a.life, 13)


class DefaultAI(Base):
    def test_casts_excavation_with_cards_in_hand(self):
        spell = card("Test Spell", "{U}", "Sorcery", EXCAVATION)
        self.assertEqual(spell.unsupported, [])
        self.perm(ISLAND, self.a)
        self.a.hand = [spell, BEAR, BEAR, BEAR]
        self.game.step = "main2"
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(spell, self.a.hand)
        self.assertEqual(len(self.a.hand), 3)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Laquatus's Creativity", "Ancient Excavation"):
            self.assertEqual(card_coverage(db.get(name)).ignored, [], name)


if __name__ == "__main__":
    unittest.main()
