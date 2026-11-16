""""You can't play lands or cast spells from your hand." (#326, Experimental Frenzy): "from your hand" covers both
halves, so lands and spells from the top of the library stay playable."""
import unittest

from tests.test_cx_grammar import BEAR, DB_FILE, ISLAND, Base, card

FRENZY = card("Test Frenzy", "{3}{R}", "Enchantment", "You may look at the top card of your library any time.\n"
              "You may play lands and cast spells from the top of your library.\n"
              "You can't play lands or cast spells from your hand.")
FOREST = card("Test Forest", "", "Land — Forest", "({T}: Add {G}.)")


class Rules(Base):
    def setUp(self):
        super().setUp()
        self.assertEqual(FRENZY.unsupported, [])
        self.frenzy = self.perm(FRENZY, self.a)
        for _ in range(2):
            self.perm(FOREST, self.a).sick = False

    def test_no_spells_from_hand(self):
        self.a.hand = [BEAR]
        self.assertFalse(self.game.can_cast_now(self.a, BEAR))

    def test_no_land_from_hand(self):
        self.a.hand = [ISLAND]
        lands = len(self.a.battlefield)
        self.game.play_land(self.a, ISLAND)
        self.assertEqual(len(self.a.battlefield), lands)
        self.assertIn(ISLAND, self.a.hand)

    def test_land_from_the_top(self):
        self.a.hand, self.a.library = [ISLAND], [BEAR] * 5 + [FOREST]
        lands = len(self.a.battlefield)
        self.game.play_land(self.a, FOREST)
        self.assertEqual(len(self.a.battlefield), lands + 1)

    def test_only_its_controller(self):
        self.b.hand = [BEAR]
        for _ in range(2):
            self.perm(FOREST, self.b).sick = False
        self.game.active_idx = 1
        self.assertTrue(self.game.can_cast_now(self.b, BEAR))

    def test_lock_ends_when_it_leaves(self):
        self.a.battlefield.remove(self.frenzy)
        self.a.hand = [BEAR]
        self.assertTrue(self.game.can_cast_now(self.a, BEAR))


class DefaultAI(Base):
    def test_ai_plays_the_top_land_not_a_hand_land(self):
        self.perm(FRENZY, self.a)
        self.a.hand, self.a.library = [ISLAND], [BEAR] * 5 + [FOREST]
        self.a.ai.play_land(self.game, self.a)
        self.assertIn(ISLAND, self.a.hand)
        self.assertTrue(any(x.card.name == FOREST.name for x in self.a.battlefield))

    def test_ai_doesnt_try_hand_lands_without_a_top_land(self):
        self.perm(FRENZY, self.a)
        self.a.hand, self.a.library = [ISLAND], [BEAR] * 5
        self.a.ai.play_land(self.game, self.a)
        self.assertIn(ISLAND, self.a.hand)


@unittest.skipUnless(DB_FILE.exists(), "card database not built")
class RealCards(unittest.TestCase):
    def test_card_parses_fully(self):
        from mtgsim.carddb import CardDB
        from mtgsim.coverage import FULL, card_coverage
        row = card_coverage(CardDB().get("Experimental Frenzy"))
        self.assertEqual(row.status, FULL, row.ignored)


if __name__ == "__main__":
    unittest.main()
