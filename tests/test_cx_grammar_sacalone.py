"""#337: "Sacrifice any number of <types>." on its own, then "... for each permanent sacrificed this way" (Reprocess,
Renounce)."""
import unittest

from mtgsim.cards import make_token
from mtgsim.cards import parse as P
from mtgsim.engine import StackItem

from tests.test_cx_grammar import DB_FILE, Base
from tests.test_templates import BEAR, ISLAND, card

REPROCESS = ("Sacrifice any number of artifacts, creatures, and/or lands. Draw a card for each permanent sacrificed "
             "this way.")
RENOUNCE = "Sacrifice any number of permanents. You gain 2 life for each permanent sacrificed this way."


def clue():
    return make_token("", 0, 0, kind="clue")


class Parsing(unittest.TestCase):
    def test_shapes(self):
        effs, bad = P._parse_effects(REPROCESS)
        self.assertEqual(bad, [])
        self.assertEqual(effs[0].data["effects"][0].data, {"mode": "sac_any", "alone": True,
                                                           "sac": {"types": ["artifact", "creature", "land"],
                                                                   "other": False}})
        self.assertEqual(effs[1].data["xq"], ("this_way", "sacrificed", "permanent"))

    def test_refusals(self):
        for s in ("Sacrifice any number of Goblins. Draw a card for each Goblin sacrificed this way.",
                  "Sacrifice any number of lands. Search your library for up to that many land cards, put them onto "
                  "the battlefield tapped, then shuffle."):
            self.assertNotEqual(P._parse_effects(s)[1], [], s)


class Behaviour(Base):
    def resolve(self, text):
        c = self.spell(text, "Sorcery")
        self.game.stack.append(StackItem(self.a, list(c.spell_effects), [None] * len(c.spell_effects), card=c,
                                         name=c.name))
        self.game.resolve_top()

    def test_reprocess_draws_for_each(self):
        for _ in range(3):
            self.perm(clue(), self.a)
        bear = self.perm(BEAR, self.a)
        self.resolve(REPROCESS)
        self.assertEqual((len(self.a.hand), sum(x.card.is_token for x in self.a.battlefield)), (3, 0))
        self.assertIn(bear, self.a.battlefield)

    def test_renounce_lands_beyond_seven(self):
        for _ in range(9):
            self.perm(ISLAND, self.a)
        self.resolve(RENOUNCE)
        self.assertEqual(self.a.life, 24)

    def test_nothing_given_up_nothing_gained(self):
        self.perm(BEAR, self.a)
        self.resolve(RENOUNCE)
        self.assertEqual((self.a.life, len(self.a.battlefield)), (20, 1))

    def test_a_narrower_noun_than_the_list_counts_nothing(self):
        # one count for "artifacts and creatures": "for each creature sacrificed this way" can't be read off it
        self.a.ai.choose_sac_any = lambda game, me, cands: list(cands)
        self.perm(clue(), self.a)
        self.perm(BEAR, self.a)
        self.resolve("Sacrifice any number of artifacts and/or creatures. You gain 3 life for each creature "
                     "sacrificed this way.")
        self.assertEqual((self.a.life, len(self.a.battlefield)), (20, 0))

    def test_a_single_type_list_counts(self):
        self.a.ai.choose_sac_any = lambda game, me, cands: list(cands)
        for _ in range(2):
            self.perm(BEAR, self.a)
        self.resolve("Sacrifice any number of creatures. You gain 3 life for each creature sacrificed this way.")
        self.assertEqual(self.a.life, 26)


class DefaultAI(Base):
    def setUp(self):
        super().setUp()
        self.spell_card = card("Test Spell", "{U}", "Sorcery", REPROCESS)
        self.assertEqual(self.spell_card.unsupported, [])
        self.perm(ISLAND, self.a)
        self.a.hand = [self.spell_card]
        self.game.step = "main2"

    def test_casts_with_clues(self):
        for _ in range(3):
            self.perm(clue(), self.a)
        self.a.ai.main_phase(self.game, self.a)
        self.assertNotIn(self.spell_card, self.a.hand)
        self.assertEqual(len(self.a.hand), 3)

    def test_holds_it_with_nothing_to_give_up(self):
        self.perm(BEAR, self.a)
        self.a.ai.main_phase(self.game, self.a)
        self.assertIn(self.spell_card, self.a.hand)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_full(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import card_coverage
        db = CardDB(offline=True)
        for name in ("Reprocess", "Renounce"):
            self.assertEqual(card_coverage(db.get(name)).ignored, [], name)


if __name__ == "__main__":
    unittest.main()
