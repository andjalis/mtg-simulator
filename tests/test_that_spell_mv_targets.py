"""#317 slice: target restrictions relative to the spell a cast trigger fired on ("target creature with that
spell's mana value", "... with mana value less than or equal to that spell's mana value", "target creature card
with mana value equal to that spell's mana value from your graveyard"), and an exact "with mana value N" selector."""
import random
import unittest

from mtgsim.ai import HeuristicAI
from mtgsim.cards.parse import _parse_effects
from mtgsim.engine import Game, Player
from mtgsim.permanent_templates import selector
from tests.test_cx_grammar import DB_FILE
from tests.test_templates import ISLAND, card


def game():
    a, b = Player("a", [ISLAND] * 10, HeuristicAI()), Player("b", [ISLAND] * 10, HeuristicAI())
    g = Game(a, b, random.Random(0), log=True)
    g.turn, g.step = 1, "main1"
    for p in (a, b):
        p.library = [ISLAND] * 20
    return g, a, b


class Parse(unittest.TestCase):
    def test_exact_stat_selector(self):
        self.assertEqual(selector("creature with mana value 3"), {"stat": ["mana value", "==", 3],
                                                                   "types_all": ["creature"]})
        self.assertEqual(selector("creature with power 2 or less")["stat"], ["power", "<=", 2])

    def test_rewrites(self):
        for text, op in (("Gain control of target creature with that spell's mana value until end of turn.", "=="),
                         ("Return up to one target nonland permanent an opponent controls with mana value less than "
                          "or equal to that spell's mana value to its owner's hand.", "<=")):
            effects, bad = _parse_effects(text)
            self.assertEqual(bad, [], text)
            eff = effects[-1]
            self.assertEqual(eff.data["xq"], ("spell", "mana value"))
            self.assertEqual(eff.data["selector"]["stat"], ["mana value", op, 1])

    def test_near_misses(self):
        for text in ("Destroy all permanents with that spell's mana value.",          # a group, not a target
                     "Target player discards all cards with that spell's mana value."):
            _, bad = _parse_effects(text)
            self.assertTrue(bad, text)


@unittest.skipUnless(DB_FILE.exists(), "needs mtgsim/data/cards.sqlite3")
class Cards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mtgsim.carddb import CardDB
        cls.db = CardDB(offline=True)

    def board(self, host, spell):
        g, a, b = game()
        for name in ("Island", "Mountain"):
            for _ in range(6):
                g.enter_battlefield(a, self.db.get(name))
        g.enter_battlefield(a, self.db.get(host))
        foes = [g.enter_battlefield(b, card(f"Foe{n}", "{%d}{G}" % (n - 1), "Creature — Beast", "", n, n))
                for n in (2, 3, 5)]
        a.graveyard = [card(f"Dead{n}", "{%d}{G}" % (n - 1), "Creature — Beast", "", n, n) for n in (2, 3)]
        a.hand = [spell]
        self.assertTrue(g.cast(a, spell))
        g.settle()
        return g, a, b, foes

    def test_full(self):
        for name in ("Hammerhead Tyrant", "Skyfire Kirin", "Krile Baldesion"):
            self.assertEqual(self.db.get(name).unsupported, [], name)

    def test_hammerhead_bounces_up_to_the_spells_mana_value(self):
        g, a, b, (two, three, five) = self.board("Hammerhead Tyrant", card("Four", "{3}{U}", "Sorcery", "Draw a card."))
        self.assertNotIn(three, b.battlefield)            # the best one with mana value <= 4
        self.assertIn(five, b.battlefield)

    def test_skyfire_takes_exactly_the_spells_mana_value(self):
        g, a, b, (two, three, five) = self.board("Skyfire Kirin", card("Arc", "{2}{R}", "Sorcery — Arcane",
                                                                       "Draw a card."))
        self.assertIs(three.controller, a)
        self.assertIs(five.controller, b)
        self.assertIs(two.controller, b)

    def test_skyfire_no_match_no_target(self):
        g, a, b, foes = self.board("Skyfire Kirin", card("Arc", "{3}{R}", "Sorcery — Arcane", "Draw a card."))
        self.assertTrue(all(f.controller is b for f in foes))      # nothing with mana value 4

    def test_krile_returns_the_matching_card(self):
        g, a, b, _ = self.board("Krile Baldesion", card("Three", "{2}{U}", "Sorcery", "Draw a card."))
        self.assertIn("Dead3", [c.name for c in a.hand])
        self.assertNotIn("Dead2", [c.name for c in a.hand])


if __name__ == "__main__":
    unittest.main()
